#!/usr/bin/env python3
"""
Fast lane, desk mode and quantity links for the One Piece restock bot (v2.6, PC copy)
=====================================================================================

FAST LANE - during a One Piece drop window the full check runs every 60 seconds. Between those
checks, the fast lane looks at just your targets every 15 seconds:
  * every listing the full check has seen for the window's release (e.g. "EB-05" for "EB-05 eve"),
    boxes and watched sealed products, at Shopify shops (sold-out ones too - that's the point), and
  * your /watch links on Shopify shops.
Each target is one small request (/products/<handle>.js). Alerts use the same ids as the full
check, so nothing alerts twice. Politeness rules, per shop:
  * a shop that answered 429 ("slow down") is left out of the fast lane until its Retry-After
    cool-down is over (the full 60-second check keeps covering it), and
  * a shop answering slowly (over 2 seconds - its server is struggling) only gets its top 2 targets
    checked, so the bot isn't part of the pile-on.
Settings (config.json, optional): "fast_lane": {"seconds": 15, "slow_ms": 2000, "slow_keep": 2,
"max_targets": 40}, or "fast_lane": false to switch it off. A drop window can list extra
release codes: {"name": "...", "codes": ["EB-05", "PRB-02"], ...}.

DESK MODE - /desk on in Discord. When a box, watched sealed product or /watch link comes in stock
within your max, the PC opens its checkout link in your default browser, so you only have to pay.
At most 2 tabs a minute, the same link at most once every 10 minutes, never for "new listing"
alerts. /desk off, or it switches itself off after the hours you gave it (12 by default).

QUANTITY LINKS - "cart_qty" in the "sealed" section of config.json (a number for every shop, or
{"default": 1, "Mayhem": 2}) and /watch add qty:N add a second "Buy N" checkout link to alerts.
Shops don't publish their per-customer limits, so you set what you know.
"""
import json
import re
import threading
import time
import urllib.parse
import webbrowser
from collections import deque

try:
    import link_watch as lw
except ImportError:
    lw = None

DEFAULTS = {"seconds": 15, "slow_ms": 2000, "slow_keep": 2, "max_targets": 40}
MIN_SECONDS = 10
DESK_MAX_PER_MIN = 2
DESK_SAME_LINK_GAP = 600
CODE_RE = re.compile(r"\b([A-Za-z]{2,3})-?(\d{2})\b")

TARGETS = []                     # set by update_targets() after each full check in a drop window
LATENCY = {}                     # host -> recent response time (ms), smoothed
STATUS = {"targets": 0, "checks": 0, "alerts": 0, "paused": [], "slow": [], "last": 0, "window": ""}
_lock = threading.Lock()
_opened = deque()
_opened_links = {}
_said = set()


def _num(x):
    if isinstance(x, bool) or x is None:
        return None
    try:
        return float(str(x).strip())
    except (TypeError, ValueError):
        return None


def settings(cfg):
    """The fast lane's settings, or None if it's switched off."""
    raw = (cfg or {}).get("fast_lane", True)
    if raw is False:
        return None
    s = dict(DEFAULTS)
    if isinstance(raw, dict):
        for k in DEFAULTS:
            v = _num(raw.get(k))
            if v is not None and v > 0:
                s[k] = v
    s["seconds"] = max(MIN_SECONDS, s["seconds"])
    s["slow_keep"] = max(1, int(s["slow_keep"]))
    s["max_targets"] = max(1, int(s["max_targets"]))
    return s


# ---------------------------------------------------------------- targets
def window_codes(drop):
    """Release codes a drop window is about: from its name ("EB-05 eve" -> EB-05) and its "codes"."""
    if not drop:
        return []
    words = [drop.get("name", "")] + [str(c) for c in drop.get("codes") or []]
    out = []
    for w in words:
        for a, n in CODE_RE.findall(w):
            code = f"{a.upper()}-{n}"
            if code not in out:
                out.append(code)
    return out


def code_pattern(codes):
    """EB-05 matches 'EB-05', 'EB05', 'eb 05' and 'EB5'; OP-18 matches 'OP-18'/'OP18' (not 'OP-180')."""
    parts = []
    for c in codes:
        a, n = c.split("-")
        num = ("0?" + str(int(n))) if n.startswith("0") else n
        parts.append(rf"{a.lower()}[\s\-]?{num}")
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b", re.I) if parts else None


def _is_shopify_page(url):
    return "/products/" in urllib.parse.urlsplit(url or "").path


def build_targets(drop, by_shop, watch_items=(), max_targets=40):
    """What the fast lane checks: the release's listings (boxes first) and Shopify /watch links."""
    out, seen = [], set()
    for it in watch_items or []:
        js = lw.shopify_js_url(it["url"]) if lw else None
        if js:
            out.append({"id": f"watch|{it['id']}", "watch": it, "js": js, "url": it["url"],
                        "shop": lw.shop_name(it["url"]), "max": it.get("max"), "prio": 0})
    rx = code_pattern(window_codes(drop))
    if rx:
        for shop, listings in (by_shop or {}).items():
            for l in listings or []:
                if l.get("group") not in ("box", "watch") or not _is_shopify_page(l.get("url")):
                    continue
                if not rx.search(l.get("name") or ""):
                    continue
                url = l["url"].split("?")[0]
                out.append({"id": l["box_id"], "kind": "Booster box" if l["group"] == "box" else "Sealed",
                            "name": l["name"], "shop": l["shop"], "url": url, "js": url + ".js",
                            "max": l.get("max"), "note": l.get("note", ""), "prio": 1 if l["group"] == "box" else 2})
    uniq = []
    for t in sorted(out, key=lambda t: t["prio"]):
        if t["id"] not in seen:
            seen.add(t["id"])
            uniq.append(t)
    return uniq[:int(max_targets)]


def update_targets(tb, cfg, drop, by_shop):
    """After a full check: refresh the target list (keeps the old one if the sealed check didn't run)."""
    s = settings(cfg)
    op = drop if drop and "onepiece" in (drop.get("games") or ["onepiece"]) else None
    with _lock:
        if not s or not op or tb.IN_ACTIONS:
            TARGETS[:] = []
            STATUS.update(targets=0, window="")
            return TARGETS
        if by_shop is None and TARGETS:
            return TARGETS
        items = lw.load() if lw else []
        TARGETS[:] = build_targets(op, by_shop, items, s["max_targets"])
        STATUS.update(targets=len(TARGETS), window=op.get("name", ""))
        return TARGETS


# ---------------------------------------------------------------- one fast check
def _host(url):
    return (urllib.parse.urlsplit(url).hostname or "").lower()


def _read(tb, t):
    t0 = time.perf_counter()
    try:
        data = json.loads(tb.HTTP.fetch(t["js"], tries=1, memo=False).decode("utf-8", "replace"))
        err = None
    except Exception as e:  # noqa: BLE001  (429 cool-downs, robots, 404s...: skip this target this time)
        data, err = None, e
    ms = (time.perf_counter() - t0) * 1000
    return t, data, err, ms


def _find(tb, t, data):
    """(find or None, read ok) for one target's product data."""
    if not isinstance(data, dict) or not isinstance(data.get("variants"), list):
        return None, False
    if t.get("watch") and lw:
        r = lw.parse_shopify(data, t["url"])
        if not r:
            return None, False
        it = t["watch"]
        if r["buyable"] and (it.get("max") is None or r["price"] <= it["max"] + 0.001):
            f = lw.make_find(it, r)
            f["note"] = (f["note"] + "\n⚡ fast lane").strip()
            return f, True
        return None, True
    price, vid = tb.cheapest_available(data["variants"], cents=True)
    if price is None or (t.get("max") is not None and price > t["max"] + 0.001):
        return None, True
    note = ", ".join(x for x in (t.get("note"), "⚡ fast lane") if x)
    return {"id": t["id"], "kind": t["kind"], "name": t["name"], "shop": t["shop"], "price": price,
            "url": t["url"], "cart": tb.shopify_cart_link(t["url"], vid), "note": note}, True


def tick(tb, cfg, drop=None, now=None):
    """Check the targets once; alert on anything newly buyable within its max. Returns the new finds."""
    s = settings(cfg)
    with _lock:
        targets = list(TARGETS)
    if not s or not targets:
        return []
    now = now or time.time()
    by_host = {}
    for t in targets:
        by_host.setdefault(_host(t["js"]), []).append(t)
    check, paused, slow = [], [], []
    for host, ts in by_host.items():
        cool = tb.HTTP.cool.get(host)
        if cool and cool[0] > now:
            paused.append(host)                 # 429: the full check covers it until the cool-down ends
            continue
        if LATENCY.get(host, 0) > s["slow_ms"]:
            slow.append(host)
            ts = ts[:s["slow_keep"]]            # struggling server: top targets only
        check += ts
    results = tb.pmap(lambda t: _read(tb, t), check) if check else []
    finds, gone = [], []
    for t, data, err, ms in results:
        h = _host(t["js"])
        if err is None:
            LATENCY[h] = ms if h not in LATENCY else 0.6 * LATENCY[h] + 0.4 * ms
        f, ok = _find(tb, t, data) if err is None else (None, False)
        if f:
            finds.append(f)
        elif ok:
            gone.append(t["id"])                # read fine, not buyable within max: a restock alerts again
    state = tb.load_state()
    show = tb.new_only(finds, state)
    changed = False
    for k in gone:
        if k in state:
            state.pop(k)
            changed = True
    undelivered = set()
    if show:
        delivered = deliver(tb, cfg, show, drop)
        undelivered = {f["id"] for f in show} - delivered
    for f in finds:
        if f["id"] not in undelivered and state.get(f["id"]) != f["price"]:
            state[f["id"]] = f["price"]
            changed = True
    if changed and not tb.DRY_RUN[0]:
        tb.save_state(state)
    was = (STATUS.get("paused"), STATUS.get("slow"))
    STATUS.update(checks=STATUS["checks"] + 1, alerts=STATUS["alerts"] + len(show), last=round(now),
                  paused=sorted(paused), slow=sorted(slow), targets=len(targets))
    if (STATUS["paused"], STATUS["slow"]) != was and (paused or slow):
        print(f"   (fast lane: {len(check)} target(s) checked"
              + (f"; paused for a 429 cool-down: {', '.join(paused)}" if paused else "")
              + (f"; slow, top targets only: {', '.join(slow)}" if slow else "") + ")")
    return show


def deliver(tb, cfg, finds, drop=None):
    """Post fast-lane finds the same way the full check does. Returns the ids Discord confirmed."""
    label = "⚡ Fast lane" + (f" ({drop['name']})" if drop and drop.get("name") else "")
    add_qty_links(cfg, finds)
    text = tb.report(finds, label)
    print("\n" + text)
    stamp = time.strftime("%a %d %b %Y %I:%M:%S %p")
    tb.append_text(tb.LOG_PATH, f"\n--- {stamp} (fast lane) ---\n{text}\n")
    title = tb.finds_title(finds)
    ping = tb.ping_allowed(cfg, finds)
    if ping:
        tb.push_phone(cfg, title, text[:3500])
    desk_open(tb, finds)
    alerts = cfg.get("alerts") or {}
    delivered = {f["id"] for f in finds}
    if any(alerts.get(k) for k in ("discord_webhook", "discord_webhook_boxes", "discord_webhook_singles")) \
            and not tb.DRY_RUN[0]:
        _, delivered = tb.push_discord_detailed(cfg, title, text, finds, ping=ping)
    tb.log_events([{"t": round(time.time()), "event": "alert", "id": f["id"], "kind": f.get("kind"),
                    "name": f.get("name"), "shop": f.get("shop"), "url": f.get("url"), "price": f.get("price"),
                    "copy": "pc-fast"} for f in finds if f["id"] in delivered and f.get("url")])
    return delivered


def wait(tb, cfg, seconds):
    """Instead of sleeping between full checks: in a drop window with targets, run the fast lane
    every few seconds until the next full check is due."""
    s = settings(cfg)
    if not s or tb.IN_ACTIONS or not TARGETS or not tb.active_window(cfg):
        time.sleep(seconds)
        return
    end = time.time() + seconds
    while True:
        rem = end - time.time()
        if rem <= s["seconds"] * 0.6:
            time.sleep(max(0.0, rem))
            return
        time.sleep(s["seconds"])
        if end - time.time() < 2:
            return
        try:
            tick(tb, cfg, tb.active_window(cfg))
        except Exception as e:  # noqa: BLE001  (never let the fast lane stop the full checks)
            msg = f"   ! fast lane skipped a round ({type(e).__name__}: {str(e)[:120]})"
            if msg not in _said:
                _said.add(msg)
                print(msg)


# ---------------------------------------------------------------- desk mode
def desk_until(tb):
    try:
        return float(tb.read_controls().get("desk_until", 0) or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def desk_open(tb, finds, now=None, opener=None):
    """Desk mode: open checkout links for buyable targets (boxes, watched sealed, /watch links)."""
    now = now or time.time()
    if tb.IN_ACTIONS or tb.DRY_RUN[0] or desk_until(tb) <= now:
        return []
    opener = opener or (lambda url: webbrowser.open(url, new=2))
    order = {True: 0}
    picks = [f for f in finds if f.get("cart") and f.get("kind") in ("Booster box", "Sealed")
             and f.get("game") != "pokemon"]
    picks.sort(key=lambda f: (order.get(bool(f.get("link_watch")), 1), f.get("kind") != "Booster box",
                              f.get("price") or 0))
    opened = []
    for f in picks:
        while _opened and now - _opened[0] > 60:
            _opened.popleft()
        if len(_opened) >= DESK_MAX_PER_MIN:
            break
        link = f["cart"]
        if now - _opened_links.get(link, 0) < DESK_SAME_LINK_GAP:
            continue
        try:
            opener(link)
        except Exception as e:  # noqa: BLE001
            print(f"   ! desk mode couldn't open the browser ({e})")
            break
        _opened.append(now)
        _opened_links[link] = now
        opened.append(f)
    if opened:
        print(f"   (desk mode: opened {len(opened)} checkout tab(s): {', '.join(f['name'][:40] for f in opened)})")
    return opened


# ---------------------------------------------------------------- quantity links
def qty_for(cfg, f):
    if f.get("link_watch"):
        return int(_num(f.get("cart_qty")) or 1)
    raw = ((cfg or {}).get("sealed") or {}).get("cart_qty")
    if isinstance(raw, dict):
        v = raw.get(f.get("shop")) if f.get("shop") in raw else raw.get("default", 1)
    else:
        v = raw
    q = _num(v)
    return max(1, min(10, int(q))) if q else 1


def add_qty_links(cfg, finds):
    """A second 'Buy N' checkout link on Shopify box/sealed alerts where you've set a quantity."""
    for f in finds:
        cart = f.get("cart") or ""
        if f.get("kind") not in ("Booster box", "Sealed") or not re.search(r"/cart/\d+:1$", cart):
            continue
        q = qty_for(cfg, f)
        if q > 1:
            f["cart_qty"], f["cart_n"] = q, cart[:-1] + str(q)
    return finds
