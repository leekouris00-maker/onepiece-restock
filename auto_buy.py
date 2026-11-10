#!/usr/bin/env python3
"""
Auto-checkout for the restock bot (v2.11, PC copy only)
=======================================================

When a booster box or one of your /watch links comes back in stock within your max, the PC copy
checks it out by itself in its own Chrome window: it opens the shop's checkout with the item in
the cart, reads the total, checks it against your limits, and presses "Pay now".

It uses a separate Chrome profile (the buyer_profile folder) that YOU sign in to once with
setup_autobuy.bat: Shop Pay (shop.app) and the shops you buy from, with your address and card saved
there. The bot never sees, types or stores card numbers or passwords. If a checkout ever needs
typing (card, address, a sign-in, a captcha), it stops and posts the checkout link for you instead.

WHAT IT BUYS (v2.11.1): only what's on your auto-buy list (autobuy_list.json, PC only), each item with its
own max price per box and how many you want in total. Once it has bought that many it stops buying that item.
It starts with this season's One Piece booster boxes (OP-14 to OP-18 and EB-05) at up to A$260 each, 1 of each.
    /autobuy list                                what's on it and how many it has bought of each
    /autobuy add code:OP-15 max:240 qty:2        a booster box by set code
    /autobuy add match:premium booster|prb-02 max:300   anything else, by words in the product's name
    /autobuy remove item:<item>                  /autobuy add on an item already there changes it

Turn it on from Discord (admins):
    /autobuy set mode:test   does everything except press Pay; posts a screenshot of what it would buy
    /autobuy set mode:live   really buys          /autobuy set mode:off   stops it
    /autobuy set per_order:<A$> per_day:<A$> per_week:<A$> per_month:<A$> hours:<n>
                             spend limits (hours 0 = until you turn it off)
    /autobuy try link:<product page>   a test run on any Shopify product now (never pays)
    /autobuy status          settings and the last few attempts

Safety rails (all in autobuy.json's ledger, PC only, never committed):
  * Shopify shops only, only items on your list (the "what" setting can widen that), no pre-orders
    unless "preorders": true, never "new listing" alerts, never Pokémon unless "games" includes it
  * the box price must be within that item's max, and you never get more than the item's qty in total
  * total at checkout (with postage) must be within per_order, and the spend today / this week (Mon-Sun) /
    this month plus it within per_day / per_week / per_month; at most orders_per_day orders a day;
    the same product at most once every same_product_days
  * a payment the bot pressed Pay on counts toward the day's spend even if the result is unclear,
    so a slow bank page can never lead to a second order
  * one checkout at a time; anything older than 3 minutes in the queue is dropped (it's sold out by then)
  * while the bot is buying something, desk mode doesn't open that tab too, and the Discord alert
    says "🤖 auto-buying" so nobody buys it twice by hand

Optional config.json section (Discord's /autobuy set overrides the limits):
    "auto_buy": {"per_order": 300, "per_day": 300, "per_week": 500, "per_month": 1000, "orders_per_day": 2,
                 "same_product_days": 7, "what": ["list"], "preorders": false, "games": ["onepiece"], "max_qty": 2,
                 "headless": false, "browser": "chrome", "pay_wait_seconds": 180}

Needs (once):  py -3 -m pip install playwright   then   setup_autobuy.bat
"""
import json
import os
import queue
import re
import sys
import threading
import time
import urllib.parse
from datetime import datetime

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
HERE = os.environ.get("BOT_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))   # v2.15: data folder (container)
# the signed-in browser profile never goes in the shared data folder: it stays next to the code, on the PC
PROFILE_DIR = os.path.join(CODE_DIR, "buyer_profile")
OFFERS_PATH = os.path.join(HERE, "autobuy_offers.jsonl")   # v2.15: container -> PC hand-over (see auto_buy_host.py)
OFFERS_MAX_BYTES = 512 * 1024
LEDGER_PATH = os.path.join(HERE, "autobuy.json")
LIST_PATH = os.path.join(HERE, "autobuy_list.json")
SHOTS_DIR = os.path.join(HERE, "autobuy_shots")

DEFAULTS = {"per_order": 300.0, "per_day": 300.0, "per_week": 500.0, "per_month": 1000.0, "orders_per_day": 2,
            "same_product_days": 7, "what": ["list"], "preorders": False, "games": ["onepiece"], "max_qty": 2,
            "headless": False, "browser": "chrome", "pay_wait_seconds": 180}
MODES = ("off", "test", "live")
LIMITS = ("per_order", "per_day", "per_week", "per_month")
START_LIST = [{"code": c, "max": 260.0, "qty": 1} for c in ("OP-14", "OP-15", "OP-16", "OP-17", "OP-18", "EB-05")]
STALE_SECONDS = 180
IDLE_CLOSE_SECONDS = 20 * 60
SPENT = ("paid", "paying", "bank", "unclear")          # statuses that count toward the day's spend

CART_RE = re.compile(r"^(https://[^/?#]+)/cart/(\d+):(\d+)$")
PAY_RE = re.compile(r"^\s*(pay now|complete (my )?order|place order|pay)\s*$", re.I)
MONEY = r"(?:A\$|AU\$|\$)\s*([\d,]+\.\d{2})"
TOTAL_RE = re.compile(r"(?<![A-Za-z])Total\b(?!\s*(?:sav|discount|tax|item|weight))(?:\s*\(?\s*AUD\s*\)?)?[^\n$]{0,20}?\s*(?:AUD\s*)?" + MONEY)
SUBTOTAL_RE = re.compile(r"Subtotal\b[^\n$]{0,40}?\s*" + MONEY, re.I)
DONE_RE = re.compile(r"thank you[,!]? \w*|your order is confirmed|order (is )?confirmed|order #\s*\w+", re.I)
DECLINE_RE = re.compile(r"(card|payment)[^.\n]{0,40}(declined|couldn.t be (processed|verified)|could not be "
                        r"(processed|verified)|was not (processed|authori[sz]ed))|insufficient funds|"
                        r"there was (a problem|an issue) (processing|with) (your )?payment|payment failed", re.I)
SOLD_RE = re.compile(r"sold out|out of stock|no longer available|not available|isn.t available|"
                     r"only \d+ (left|available)|exceeds? the (maximum|available)", re.I)
CAPTCHA_SEL = ('iframe[src*="hcaptcha"], iframe[src*="recaptcha"], iframe[src*="challenges.cloudflare"], '
               'iframe[title*="captcha" i]')
CARD_FRAME_HINTS = ("card-fields", "pci.shopifyinc", "checkout.pci")
BANK_FRAME_HINTS = ("3ds", "acs", "cardinal", "securecode", "challenge", "authenticat", "verifiedbyvisa")

_q = queue.Queue(maxsize=5)
_busy = set()                   # find ids queued or being checked out
_lock = threading.Lock()
_worker = [None]


def _num(x):
    if isinstance(x, bool) or x is None:
        return None
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def money(x):
    return f"${x:,.2f}"


# ---------------------------------------------------------------- settings
def settings(tb, cfg=None):
    """config.json "auto_buy" + what /autobuy set put in controls.json. mode is off/test/live."""
    s = dict(DEFAULTS)
    raw = (cfg or {}).get("auto_buy")
    if isinstance(raw, dict):
        for k in DEFAULTS:
            if k in raw:
                s[k] = raw[k]
    try:
        ctl = (tb.read_controls() or {}).get("autobuy") or {}
    except Exception:  # noqa: BLE001
        ctl = {}
    for k in LIMITS:
        if _num(ctl.get(k)) is not None:
            s[k] = ctl[k]
    for k in LIMITS + ("orders_per_day", "same_product_days", "max_qty", "pay_wait_seconds"):
        v = _num(s.get(k))
        s[k] = v if v is not None and v >= 0 else DEFAULTS[k]
    s["orders_per_day"], s["max_qty"] = int(s["orders_per_day"]), max(1, int(s["max_qty"]))
    s["pay_wait_seconds"] = max(30, s["pay_wait_seconds"])
    for k in ("what", "games"):
        v = s.get(k)
        s[k] = [str(x).lower() for x in ([v] if isinstance(v, str) else v or [])]
    mode = str(ctl.get("mode") or "off").lower()
    until = _num(ctl.get("until")) or 0
    if mode not in MODES or (until and until <= time.time()):
        mode = "off"
    s["mode"], s["until"] = mode, until
    return s


# ---------------------------------------------------------------- ledger
def load_ledger(tb):
    led = tb.read_json(LEDGER_PATH, {}) or {}
    led.setdefault("orders", [])
    return led


def save_ledger(tb, led):
    cutoff = time.time() - 60 * 86400
    led["orders"] = [o for o in led.get("orders", []) if o.get("t", 0) >= cutoff][-300:]
    tb.atomic_write_json(LEDGER_PATH, led)


def _today(ts):
    return datetime.fromtimestamp(ts).date()


def _same(period, a, b):
    da, db = _today(a), _today(b)
    if period == "day":
        return da == db
    if period == "week":                       # Monday to Sunday
        return da.isocalendar()[:2] == db.isocalendar()[:2]
    return (da.year, da.month) == (db.year, db.month)


def spent(led, period="day", now=None):
    """(A$ spent, orders) today / this week / this month. Anything the bot pressed Pay on counts."""
    now = now or time.time()
    os_ = [o for o in led.get("orders", []) if o.get("mode") == "live" and o.get("status") in SPENT
           and _same(period, o.get("t", 0), now)]
    return sum(_num(o.get("total")) or _num(o.get("expect")) or 0 for o in os_), len(os_)


def spent_today(led, now=None):
    return spent(led, "day", now)


def over_budget(led, amount, s, now=None):
    """Why spending `amount` more would break the day / week / month limit, or ""."""
    for period, key in (("day", "per_day"), ("week", "per_week"), ("month", "per_month")):
        sp, _ = spent(led, period, now)
        if sp + amount > s[key] + 0.001:
            label = {"day": "today's", "week": "this week's", "month": "this month's"}[period]
            return f"would take {label} spend past {money(s[key])} (spent {money(sp)})"
    return ""


def recently_bought(led, fid, days, now=None):
    now = now or time.time()
    return any(o.get("id") == fid and o.get("mode") == "live" and o.get("status") in SPENT
               and now - o.get("t", 0) < days * 86400 for o in led.get("orders", []))


# ---------------------------------------------------------------- the auto-buy list
CODE_RE = re.compile(r"^\s*([A-Za-z]{2,3})\s*-?\s*(\d{1,2})\s*$")


def norm_code(code):
    m = CODE_RE.match(str(code or ""))
    return f"{m.group(1).upper()}-{int(m.group(2)):02d}" if m else ""


def code_rx(code):
    """OP-15 matches 'OP-15', 'OP15', 'op 15' (not 'OP-150'); EB-05 also 'EB5'."""
    a, n = code.split("-")
    num = ("0?" + str(int(n))) if n.startswith("0") else n
    return re.compile(rf"\b{a}[\s\-]?{num}\b", re.I)


def make_item(code="", match=None, max=None, qty=1, name="", bought=0, on=True):
    code = norm_code(code)
    words = [w.strip().lower() for w in (match if isinstance(match, list) else str(match or "").split(","))
             if w and w.strip()]
    if not code and not words:
        return None
    iid = code.lower() if code else re.sub(r"[^a-z0-9]+", "-", words[0])[:40].strip("-")
    return {"id": iid, "name": name or (f"{code} booster box" if code else " + ".join(words)), "code": code,
            "match": words, "max": float(max or 0), "qty": max_int(qty, 1), "bought": max_int(bought, 0),
            "on": bool(on)}


def max_int(x, lo):
    v = _num(x)
    return max(lo, int(v)) if v is not None else lo


def load_items(tb):
    """The list (autobuy_list.json). The first time, it starts with this season's booster boxes."""
    raw = tb.read_json(LIST_PATH, None)
    if raw is None:
        items = [make_item(**x) for x in START_LIST]
        save_items(tb, items)
        return items
    out = []
    for x in raw.get("items", []) if isinstance(raw, dict) else []:
        if isinstance(x, dict):
            it = make_item(**{k: x.get(k) for k in ("code", "match", "max", "qty", "name", "bought", "on")
                              if x.get(k) is not None})
            if it:
                out.append(it)
    return out


def save_items(tb, items):
    tb.atomic_write_json(LIST_PATH, {"_help": "The auto-buy list. Change it from Discord with /autobuy add / remove.",
                                     "items": items})


def item_matches(it, f):
    text = f"{f.get('name', '')} {f.get('url', '')}"
    if it["code"]:
        if not code_rx(it["code"]).search(text):
            return False
        if not it["match"] and f.get("kind") != "Booster box":
            return False                       # a code item means the booster box, not a sleeve or deck
    t = text.lower()
    return all(any(alt.strip() in t for alt in w.split("|")) for w in it["match"])


def item_for(f, items):
    """The list item this find is for, if it's within that item's max and you still want more of it."""
    price = _num(f.get("price")) or 0
    for it in items:
        if it["on"] and it["bought"] < it["qty"] and item_matches(it, f) and price <= it["max"] + 0.001:
            return it
    return None


def item_of(f, items):
    """Like item_for, but whatever the price / count (for saying why something wasn't bought)."""
    return next((it for it in items if it["on"] and item_matches(it, f)), None)


def count_bought(tb, item_id, qty):
    items = load_items(tb)
    for it in items:
        if it["id"] == item_id:
            it["bought"] += qty
            save_items(tb, items)
            return it
    return None


# ---------------------------------------------------------------- controls (shared by Discord and the PC web page)
def _controls_update(tb, update):
    controls = tb.read_controls()
    cur = dict(controls.get("autobuy") or {})
    cur.update(update)
    controls["autobuy"] = {k: v for k, v in cur.items() if v is not None}
    tb.atomic_write_json(tb.CONTROLS_PATH, controls)


def set_mode(tb, mode, hours=None):
    """off / test / live; hours > 0 switches it off after that long, 0 or None keeps it on."""
    mode = str(mode).lower()
    if mode not in MODES:
        raise ValueError("mode is off, test or live")
    upd = {"mode": mode}
    h = _num(hours)
    upd["until"] = round(time.time() + h * 3600) if h and h > 0 and mode != "off" else 0
    _controls_update(tb, upd)


def set_limits(tb, **limits):
    upd = {}
    for k, v in limits.items():
        if k in LIMITS and v not in (None, ""):
            n = _num(v)
            if n is None or n < 0:
                raise ValueError(f"{k} should be a number of dollars")
            upd[k] = round(n, 2)
    if upd:
        _controls_update(tb, upd)
    return upd


def queue_try(tb, url):
    if not re.match(r"https://[^/\s]+/(products/|cart/\d)", str(url or "").strip()):
        raise ValueError("that needs to be a Shopify product link (https://…/products/…)")
    _controls_update(tb, {"try": str(url).strip()})


def upsert_item(tb, code="", match="", max=None, qty=1, name="", reset=False):
    """Add an item, or change the one with the same code / words. Returns (item, was it there already)."""
    if code and not norm_code(code):
        raise ValueError("the code should look like OP-15, EB-05 or PRB-02")
    if _num(max) is None or _num(max) <= 0:
        raise ValueError("give a max price above $0")
    new = make_item(code=code or "", match=match, max=_num(max), qty=qty or 1, name=name or "")
    if not new:
        raise ValueError("give a set code (like OP-15) or words from the product name")
    items = load_items(tb)
    old = next((it for it in items if it["id"] == new["id"]), None)
    if old:
        new["name"] = name or old["name"]
        new["bought"] = 0 if reset else old["bought"]
        new["on"] = old["on"]
        items[items.index(old)] = new
    else:
        items.append(new)
    save_items(tb, items)
    return new, bool(old)


def edit_item(tb, item_id, **changes):
    """remove=True, on=True/False, reset=True, or max / qty / name. Returns the item (None once removed)."""
    items = load_items(tb)
    it = next((x for x in items if x["id"] == item_id), None)
    if not it:
        raise ValueError("that item isn't on the list any more")
    if changes.get("remove"):
        save_items(tb, [x for x in items if x["id"] != item_id])
        return None
    if "on" in changes:
        it["on"] = bool(changes["on"])
    if changes.get("reset"):
        it["bought"] = 0
    if _num(changes.get("max")) is not None:
        if _num(changes["max"]) <= 0:
            raise ValueError("give a max price above $0")
        it["max"] = _num(changes["max"])
    if _num(changes.get("qty")) is not None:
        it["qty"] = max_int(changes["qty"], 1)
    if changes.get("name"):
        it["name"] = str(changes["name"])[:80]
    save_items(tb, items)
    return it


def snapshot(tb, cfg=None):
    """Everything a dashboard shows, as plain data."""
    s = settings(tb, cfg if cfg is not None else tb.load_config())
    led = load_ledger(tb)
    spend = {p: dict(zip(("spent", "orders"), spent(led, p))) for p in ("day", "week", "month")}
    shots = set(os.listdir(SHOTS_DIR)) if os.path.isdir(SHOTS_DIR) else set()
    recent = []
    for o in led.get("orders", [])[-15:][::-1]:
        recent.append({k: o.get(k) for k in ("t", "name", "shop", "mode", "status", "total", "detail")})
    return {"mode": s["mode"], "until": s["until"], "limits": {k: s[k] for k in LIMITS},
            "orders_per_day": s["orders_per_day"], "preorders": s["preorders"], "what": s["what"],
            "spend": spend, "items": load_items(tb), "recent": recent,
            "shots": sorted(shots)[-12:][::-1], "version": getattr(tb, "VERSION", "")}


# ---------------------------------------------------------------- what can be auto-bought
def is_preorder(f):
    return bool(re.search(r"pre-?order", f"{f.get('name', '')} {f.get('note', '')}", re.I))


def cart_for(f, s, item=None):
    """(checkout link, qty) for a find, or (None, why not). A list item buys what's still wanted of it."""
    m = CART_RE.match(f.get("cart") or "")
    if not m:
        return None, "not a Shopify shop (no one-item cart link)"
    qty = int(m.group(3))
    if f.get("link_watch") and int(_num(f.get("cart_qty")) or 1) > 1:
        qty = int(_num(f.get("cart_qty")))
    if item:
        qty = item["qty"] - item["bought"]
    qty = max(1, min(qty, s["max_qty"]))
    return f"{m.group(1)}/cart/{m.group(2)}:{qty}", qty


def eligible(f, s, items=None):
    """(True, "") or (False, why). Only what's on the list (or the kinds of finds "what" allows)."""
    if f.get("kind") == "New listing":
        return False, "new listings are never auto-bought"
    game = "pokemon" if f.get("game") == "pokemon" else "onepiece"
    if game not in s["games"]:
        return False, f"{game} isn't in auto_buy games"
    what = set(s["what"])
    if "list" in what and items is not None and item_for(f, items):
        ok = f.get("kind") in ("Booster box", "Sealed")
    elif f.get("link_watch"):
        ok = "watch" in what
    elif f.get("kind") == "Booster box":
        ok = "boxes" in what
    elif f.get("kind") == "Sealed":
        ok = "sealed" in what
    else:
        ok = False
    if not ok:
        return False, ("not on your auto-buy list (or over that item's max / already bought)" if "list" in what
                       else f"{f.get('kind', 'this kind')} isn't in auto_buy what")
    if is_preorder(f) and not s["preorders"]:
        return False, "pre-order (auto_buy preorders is off)"
    if not _num(f.get("price")):
        return False, "no price"
    link, _ = cart_for(f, s)
    if not link:
        return False, _
    return True, ""


def budget_ok(led, fid, expect, s, now=None):
    """Before starting a live checkout: (True, "") or (False, why). expect = item price x qty."""
    if expect > s["per_order"] + 0.001:
        return False, f"{money(expect)} is over your per-order limit of {money(s['per_order'])}"
    _, n = spent_today(led, now)
    if n >= s["orders_per_day"]:
        return False, f"already {n} order(s) today (limit {s['orders_per_day']})"
    why = over_budget(led, expect, s, now)
    if why:
        return False, why
    if recently_bought(led, fid, s["same_product_days"], now):
        return False, f"bought in the last {s['same_product_days']:g} days"
    return True, ""


def total_ok(led, total, s, now=None):
    """At checkout, with postage: (True, "") or (False, why)."""
    if total > s["per_order"] + 0.001:
        return False, f"total {money(total)} (with postage) is over your per-order limit of {money(s['per_order'])}"
    why = over_budget(led, total, s, now)
    if why:
        return False, f"total {money(total)} {why}"
    return True, ""


# ---------------------------------------------------------------- page reading
def read_amount(rx, text):
    vals = [_num(m.group(1)) for m in rx.finditer(text or "")]
    vals = [v for v in vals if v is not None]
    return vals[-1] if vals else None


def read_total(text):
    """The order total on a checkout page (the last "Total ... $x" that isn't "Subtotal")."""
    return read_amount(TOTAL_RE, text)


def read_subtotal(text):
    return read_amount(SUBTOTAL_RE, text)


# ---------------------------------------------------------------- queue
def offer(tb, cfg, finds):
    """Called with each batch of new finds (full check and fast lane). Queues the ones auto-buy may take,
    marks them so the alert and desk mode know. Returns the finds it took."""
    if tb.IN_ACTIONS or tb.DRY_RUN[0]:
        return []
    s = settings(tb, cfg)
    if s["mode"] == "off":
        return []
    taken = []
    handover = [] if getattr(tb, "IN_CONTAINER", False) else None     # v2.15: the PC does the buying, not the container
    items = load_items(tb) if "list" in s["what"] else None
    picked = set()                              # one of each list item per batch (the cheapest shop first)
    for f in sorted(finds, key=lambda f: (not f.get("link_watch"), f.get("kind") != "Booster box", f.get("price") or 0)):
        ok, _ = eligible(f, s, items)
        if not ok:
            continue
        it = item_for(f, items) if items is not None else None
        if it and it["id"] in picked:
            continue
        if handover is not None:
            handover.append(dict(f))
        else:
            with _lock:
                if f["id"] in _busy:
                    continue
                try:
                    _q.put_nowait({"f": dict(f), "t": time.time(), "mode": s["mode"], "item": it["id"] if it else None})
                except queue.Full:
                    break
                _busy.add(f["id"])
        if it:
            picked.add(it["id"])
        f["autobuy"] = True              # desk mode leaves it alone; the shared alert doesn't say (v2.11.3: private)
        taken.append(f)
    if handover:
        write_offers(tb, handover)
        print(f"   (auto-buy {s['mode']}: handed to the PC: {', '.join(f['name'][:40] for f in handover)})")
    elif taken:
        start(tb)
        print(f"   (auto-buy {s['mode']}: queued {', '.join(f['name'][:40] for f in taken)})")
    return taken


OFFER_KEYS = ("id", "kind", "name", "shop", "price", "url", "cart", "note", "link_watch", "game", "section")


def write_offers(tb, finds):
    """Container: leave finds for the PC's buyer (auto_buy_host.py) in the shared data folder."""
    line = json.dumps({"t": round(time.time(), 1),
                       "finds": [{k: f[k] for k in OFFER_KEYS if k in f} for f in finds]}, ensure_ascii=True)
    try:
        if os.path.exists(OFFERS_PATH) and os.path.getsize(OFFERS_PATH) > OFFERS_MAX_BYTES:
            os.replace(OFFERS_PATH, OFFERS_PATH + ".1")
        with open(OFFERS_PATH, "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
    except OSError as e:
        print(f"   ! auto-buy: couldn't hand over to the PC ({e})")


def read_offers(pos, known_hosts, max_age=120, now=None, path=None):
    """PC: finds left by the container since byte `pos` -> (finds, new pos). Old offers (the PC was off) and
    anything whose links aren't https links to a shop the PC's own config knows are dropped: the container
    is the less trusted side, so the PC checks what it's handed before it opens a checkout."""
    path = path or OFFERS_PATH
    now = now or time.time()
    try:
        size = os.path.getsize(path)
    except OSError:
        return [], 0
    if pos > size:
        pos = 0                                   # the file was cut over
    try:
        with open(path, "rb") as f:
            f.seek(pos)
            raw = f.read()
    except OSError:
        return [], pos
    end = raw.rfind(b"\n") + 1
    out = []
    for line in raw[:end].splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict) or now - float(d.get("t") or 0) > max_age:
            continue
        for f in d.get("finds") or []:
            if not isinstance(f, dict) or not isinstance(f.get("id"), str) or not isinstance(f.get("name"), str):
                continue
            ok = True
            for k in ("url", "cart"):
                u = urllib.parse.urlsplit(str(f.get(k) or ""))
                if f.get(k) and (u.scheme != "https" or (u.hostname or "").lower() not in known_hosts):
                    ok = False
            try:
                f["price"] = float(f.get("price"))
            except (TypeError, ValueError):
                ok = False
            if ok and f.get("cart"):
                out.append({k: f[k] for k in OFFER_KEYS if k in f})
    return out, pos + end


def start(tb):
    with _lock:
        if _worker[0] and _worker[0].is_alive():
            return
        t = threading.Thread(target=_run_worker, args=(tb,), name="auto-buy", daemon=True)
        _worker[0] = t
    t.start()


def _run_worker(tb):
    buyer = Buyer(tb)
    try:
        while True:
            try:
                job = _q.get(timeout=30)
            except queue.Empty:
                job = _try_request(tb)
                if not job:
                    if buyer.idle_for() > IDLE_CLOSE_SECONDS:
                        buyer.close()
                    continue
            try:
                buyer.handle(job)
            except Exception as e:  # noqa: BLE001  (never let a checkout stop the restock checks)
                print(f"   ! auto-buy: {type(e).__name__}: {tb.redact(str(e))[:200]}")
                buyer.close()
            finally:
                with _lock:
                    _busy.discard(job["f"].get("id"))
    finally:
        buyer.close()


def _try_request(tb):
    """/autobuy try link:<...> from Discord: a test run, picked up within 30 seconds."""
    try:
        ctl = tb.read_controls() or {}
    except Exception:  # noqa: BLE001
        return None
    ab = ctl.get("autobuy") or {}
    url = ab.pop("try", None)
    if not url:
        return None
    ctl["autobuy"] = ab
    tb.atomic_write_json(tb.CONTROLS_PATH, ctl)
    cart, price, name = resolve_cart(tb, url)
    if not cart:
        post(tb, f"🤖 **Auto-buy test** couldn't use that link: {name}", tb.AMBER)
        return None
    return {"f": {"id": f"try|{cart}", "kind": "Sealed", "name": name, "shop": urllib.parse.urlsplit(cart).netloc,
                  "price": price, "url": url, "cart": cart}, "t": time.time(), "mode": "test", "try": True}


def resolve_cart(tb, url):
    """(cart link, price, name) for a Shopify product or cart link, or (None, 0, why)."""
    url = str(url or "").strip()
    m = CART_RE.match(url)
    if m:
        return url, 0.0, "cart link"
    parts = urllib.parse.urlsplit(url)
    hm = re.search(r"/products/([^/?#]+)", parts.path)
    if parts.scheme != "https" or not hm:
        return None, 0, "it needs to be a Shopify product page (…/products/…) or cart link"
    js = f"https://{parts.netloc}/products/{hm.group(1)}.js"
    try:
        p = json.loads(tb.HTTP.fetch(js, tries=2))
    except Exception as e:  # noqa: BLE001
        return None, 0, f"couldn't read the product ({tb.redact(str(e))[:120]}); is it a Shopify shop?"
    price, vid = tb.cheapest_available(p.get("variants") or [], cents=True)
    if vid is None:
        return None, 0, "it's sold out right now, so there's nothing to check out"
    return f"https://{parts.netloc}/cart/{vid}:1", price, p.get("title") or hm.group(1)


# ---------------------------------------------------------------- reporting
_no_channel_said = [0.0]


def post(tb, text, color, shot=None, cfg=None, phone=None):
    """To the private 🔒・auto-buy channel only ("discord_webhook_autobuy"), with the screenshot when there is one.
    v2.11.3: never to the shared channels, since friends are in the server and a checkout shows your address."""
    cfg = cfg or tb.load_config()
    alerts = cfg.get("alerts") or {}
    print(f"   [auto-buy] {text}")
    if phone:
        tb.push_phone(cfg, phone, re.sub(r"[*`]", "", text)[:3000])
    hook = alerts.get("discord_webhook_autobuy")
    if tb.DRY_RUN[0]:
        return
    if not hook:
        if time.time() - _no_channel_said[0] > 6 * 3600:
            _no_channel_said[0] = time.time()
            tb.post_status(cfg, "🔒 Auto-buy has something for you, but its private channel isn't set up yet, so it's "
                                "only in bot_output.log on the PC. Open `/autobuy panel` once to make it.", tb.AMBER)
        return
    embed = {"description": text[:4000], "color": color, "footer": {"text": "Auto-buy · PC copy"}}
    payload = {"username": alerts.get("bot_name") or "One Piece Restock", "embeds": [embed],
               "allowed_mentions": {"parse": []}}
    if not shot or not os.path.exists(shot):
        tb.discord_send(alerts, hook, payload)
        return
    embed["image"] = {"url": "attachment://checkout.png"}
    boundary = f"----autobuy{int(time.time() * 1000)}"
    with open(shot, "rb") as fh:
        img = fh.read()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
            f"Content-Type: application/json\r\n\r\n{json.dumps(payload)}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[0]\"; filename=\"checkout.png\"\r\n"
            f"Content-Type: image/png\r\n\r\n").encode() + img + f"\r\n--{boundary}--\r\n".encode()
    try:
        status, _, resp = tb.HTTP.post(hook + ("&" if "?" in hook else "?") + "wait=true", body,
                                       {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        if status >= 300:
            raise RuntimeError(f"HTTP {status}: {resp[:150]!r}")
    except Exception as e:  # noqa: BLE001
        print(f"   ! auto-buy screenshot post failed ({tb.redact(str(e))[:150]}), posting text only")
        embed.pop("image", None)
        tb.discord_send(alerts, hook, payload)


# ---------------------------------------------------------------- the browser
class Buyer:
    """One Chrome window on the buyer_profile, opened when there's something to buy, closed when idle."""

    def __init__(self, tb, launcher=None):
        self.tb, self.pw, self.ctx, self.last = tb, None, None, time.time()
        self.launcher = launcher

    def idle_for(self):
        return time.time() - self.last if self.ctx else 0

    def open(self, s):
        if self.ctx:
            return self.ctx
        if self.launcher:
            self.ctx = self.launcher(s)
            return self.ctx
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Playwright isn't installed. On the PC run:  py -3 -m pip install playwright  "
                               "then setup_autobuy.bat") from None
        self.pw = sync_playwright().start()
        kw = {"user_data_dir": PROFILE_DIR, "headless": bool(s.get("headless")),
              "viewport": {"width": 1280, "height": 1000}, "locale": "en-AU", "timezone_id": "Australia/Melbourne"}
        try:
            if str(s.get("browser", "chrome")).lower() == "chrome":
                self.ctx = self.pw.chromium.launch_persistent_context(channel="chrome", **kw)
            else:
                raise RuntimeError("bundled Chromium asked for")
        except Exception:  # noqa: BLE001  (no Chrome installed: Playwright's own Chromium)
            self.ctx = self.pw.chromium.launch_persistent_context(**kw)
        return self.ctx

    def close(self):
        for x in (self.ctx, self.pw):
            try:
                if x is self.pw and x:
                    x.stop()
                elif x:
                    x.close()
            except Exception:  # noqa: BLE001
                pass
        self.ctx = self.pw = None

    def handle(self, job):
        tb, f = self.tb, job["f"]
        cfg = tb.load_config()
        s = settings(tb, cfg)
        mode = "test" if job.get("try") else s["mode"]
        if mode == "off":
            return None
        if mode == "live" and job.get("mode") == "test":
            mode = "test"                       # queued as a test: stays a test
        if time.time() - job["t"] > STALE_SECONDS:
            print(f"   (auto-buy: dropped {f['name'][:40]}, waited over {STALE_SECONDS // 60} minutes)")
            return None
        item = None
        if job.get("item"):
            item = next((it for it in load_items(tb) if it["id"] == job["item"]), None)
            if not item or item_for(f, [item]) is None:
                print(f"   (auto-buy: {f['name'][:40]} is no longer wanted on the list)")
                return None
        link, qty = cart_for(f, s, item)
        expect = (_num(f.get("price")) or 0) * qty
        led = load_ledger(tb)
        if mode == "live" and not job.get("try"):
            ok, why = budget_ok(led, f["id"], expect, s)
            if not ok:
                post(tb, f"🤖 **Didn't auto-buy** [{f['name']}]({f.get('url')}) at {f.get('shop')}: {why}.\n"
                         f"[Checkout link]({link}) if you want it anyway.", tb.AMBER, cfg=cfg)
                return {"status": "skipped", "why": why}
        self.last = time.time()
        ctx = self.open(s)
        page = ctx.new_page()
        try:
            r = checkout(page, link, expect, s, mode, led, f, tb=tb)
        finally:
            self.last = time.time()
        r["item"] = item["id"] if item else None
        self._report(f, link, qty, mode, r, led, cfg)
        try:
            page.close()
        except Exception:  # noqa: BLE001
            pass
        return r

    def _report(self, f, link, qty, mode, r, led, cfg):
        tb = self.tb
        what = f"[{f['name']}]({f.get('url')}) x{qty} at {f.get('shop')}"
        st, total = r["status"], r.get("total")
        tot = f" · total {money(total)}" if total else ""
        if mode == "live" and st not in ("test",):
            entry = next((o for o in led["orders"] if o.get("job") == r.get("job")), None)
            if entry:
                entry.update(status=st, total=total or entry.get("total"), detail=r.get("why", ""))
            else:
                led["orders"].append({"t": round(time.time()), "id": f["id"], "name": f["name"], "shop": f.get("shop"),
                                      "mode": "live", "status": st, "total": total, "expect": r.get("expect"),
                                      "detail": r.get("why", "")})
            save_ledger(tb, led)
        elif mode == "test":
            led["orders"].append({"t": round(time.time()), "id": f["id"], "name": f["name"], "shop": f.get("shop"),
                                  "mode": "test", "status": st, "total": total, "detail": r.get("why", "")})
            save_ledger(tb, led)
        done = ""
        if mode == "live" and st in ("paid", "unclear") and r.get("item"):
            it = count_bought(tb, r["item"], qty)
            if it:
                done = (f"\n📋 {it['name']}: {it['bought']}/{it['qty']} bought"
                        + (", so it's done: no more auto-buys of it (`/autobuy add` to want more)."
                           if it["bought"] >= it["qty"] else "."))
        if st == "test":
            post(tb, f"🧪 **Auto-buy test run:** would have paid for {what}{tot}. Everything was filled in, so in "
                     f"live mode it would have pressed Pay. (`/autobuy set mode:live` when you're happy.)",
                 tb.BLUE, r.get("shot"), cfg)
        elif st == "paid":
            post(tb, f"✅ **Bought it:** {what}{tot}. Check your email for the order confirmation.{done}",
                 tb.GREEN, r.get("shot"), cfg, phone=f"Bought: {f['name'][:60]}")
        elif st == "unclear":
            post(tb, f"❓ **Pressed Pay for {what}{tot}, but couldn't confirm the order.** {r.get('why', '')} "
                     f"Check your email / bank before buying it again (it counts toward your limits).{done}",
                 tb.AMBER, r.get("shot"), cfg, phone=f"Check order: {f['name'][:60]}")
        elif st == "declined":
            post(tb, f"❌ **Payment didn't go through** for {what}{tot}: {r.get('why', '')}\n[Try yourself]({link})",
                 tb.RED, r.get("shot"), cfg, phone=f"Payment failed: {f['name'][:60]}")
        else:
            post(tb, f"✋ **Auto-buy stopped** for {what}{tot}: {r.get('why', st)}\n[Finish it yourself]({link})",
                 tb.AMBER, r.get("shot"), cfg,
                 phone=f"Needs you: {f['name'][:60]}" if mode == "live" else None)


def _shot(page, tag):
    try:
        os.makedirs(SHOTS_DIR, exist_ok=True)
        for old in sorted(os.listdir(SHOTS_DIR))[:-40]:
            os.remove(os.path.join(SHOTS_DIR, old))
        path = os.path.join(SHOTS_DIR, f"{datetime.now():%Y%m%d-%H%M%S}-{tag}.png")
        page.screenshot(path=path, full_page=False)
        return path
    except Exception:  # noqa: BLE001
        return None


def _text(page):
    try:
        return page.inner_text("body", timeout=3000)
    except Exception:  # noqa: BLE001
        return ""


def _frames_like(page, hints):
    out = []
    for fr in page.frames:
        u = (fr.url or "").lower()
        if fr is not page.main_frame and any(h in u for h in hints):
            try:
                el = fr.frame_element()
                if el.is_visible():
                    out.append(fr)
            except Exception:  # noqa: BLE001
                continue
    return out


def needs_card(page):
    """Card fields showing and empty: no saved card for this checkout."""
    for fr in _frames_like(page, CARD_FRAME_HINTS):
        try:
            box = fr.locator("input[name='number'], input[autocomplete='cc-number'], input#number").first
            if box.count() and box.is_visible() and not box.input_value().strip():
                return True
        except Exception:  # noqa: BLE001
            return True                 # can't tell: don't pay into fields we can't see
    return False


def blocker(page, text):
    """Why the bot can't carry on by itself on this page, or ""."""
    url = (page.url or "").lower()
    path = urllib.parse.urlsplit(url).path
    if page.locator(CAPTCHA_SEL).count() and any(e.is_visible() for e in page.locator(CAPTCHA_SEL).all()):
        return "the shop asked for a captcha"
    if "/account/login" in path or "/challenge" in path or re.search(r"/(log-?in|sign-?in)\b", path):
        return "the shop wants you signed in (run setup_autobuy.bat and sign in to this shop)"
    if "checkpoint" in path or "throttle" in path or "/queue" in path:
        return "the shop put the checkout behind a queue / checkpoint"
    if re.search(r"verification code|enter the code|we sent a code", text, re.I) and "shop pay" in text.lower():
        return "Shop Pay wants a verification code (sign in again with setup_autobuy.bat)"
    return ""


def checkout(page, link, expect, s, mode, led, f, tb=None, timeout=30):
    """Drive one Shopify checkout. Returns {"status": test|paid|declined|unclear|stopped, ...}."""
    r = {"status": "stopped", "expect": expect, "job": f"{f.get('id')}|{time.time():.0f}"}
    t0 = time.time()
    try:
        page.goto(link, wait_until="domcontentloaded", timeout=timeout * 1000)
    except Exception as e:  # noqa: BLE001
        r["why"] = f"the checkout page didn't load ({str(e).splitlines()[0][:120]})"
        return r
    pay = page.get_by_role("button", name=PAY_RE)
    while True:
        text = _text(page)
        why = blocker(page, text)
        if why:
            r.update(why=why, shot=_shot(page, "blocked"))
            return r
        path = urllib.parse.urlsplit(page.url).path
        if "/cart" in path and "/checkouts" not in path and SOLD_RE.search(text):
            r.update(why="sold out (or over the shop's limit) before checkout", shot=_shot(page, "sold"))
            return r
        try:
            if pay.count() and pay.first.is_visible() and pay.first.is_enabled():
                break
        except Exception:  # noqa: BLE001
            pass
        if time.time() - t0 > timeout:
            r["shot"] = _shot(page, "stuck")
            if "/checkouts" not in path and "/checkout" not in path:
                r["why"] = "the cart link didn't open a checkout"
            elif re.search(r"enter (a |your )?shipping address|add (a |an )?address", text, re.I):
                r["why"] = "no saved delivery address in this checkout"
            elif needs_card(page):
                r["why"] = "no saved card in this checkout (sign in to Shop Pay with setup_autobuy.bat)"
            elif SOLD_RE.search(text):
                r["why"] = "sold out at checkout"
            else:
                r["why"] = "couldn't find the Pay button"
            return r
        page.wait_for_timeout(400)
    page.wait_for_timeout(1200)                    # shipping rates and totals settle after the button shows
    text = _text(page)
    if SOLD_RE.search(text) and "/checkouts" in page.url:
        r.update(why="the shop says it's sold out / over the limit at checkout", shot=_shot(page, "sold"))
        return r
    if needs_card(page):
        r.update(why="no saved card in this checkout (sign in to Shop Pay with setup_autobuy.bat)",
                 shot=_shot(page, "card"))
        return r
    if re.search(r"enter (a |your )?shipping address", text, re.I):
        r.update(why="no saved delivery address in this checkout", shot=_shot(page, "address"))
        return r
    total, sub = read_total(text), read_subtotal(text)
    r["total"] = total
    if total is None:
        r.update(why="couldn't read the order total, so it didn't pay", shot=_shot(page, "total"))
        return r
    if expect and sub is not None and sub > expect * 1.02 + 0.5:
        r.update(why=f"the cart subtotal {money(sub)} is more than expected ({money(expect)}): "
                     "something else is in this checkout", shot=_shot(page, "cart"))
        return r
    ok, why = total_ok(led, total, s)
    if not ok:
        r.update(why=why, shot=_shot(page, "limit"))
        return r
    if mode != "live":
        r.update(status="test", shot=_shot(page, "test"))
        return r
    # Live: the spend counts from here, whatever happens next.
    led["orders"].append({"t": round(time.time()), "id": f.get("id"), "name": f.get("name"), "shop": f.get("shop"),
                          "mode": "live", "status": "paying", "total": total, "expect": expect, "job": r["job"]})
    if tb is not None:
        save_ledger(tb, led)
    try:
        pay.first.click(timeout=8000)
    except Exception as e:  # noqa: BLE001
        r.update(status="unclear", why=f"pressing Pay failed ({str(e).splitlines()[0][:100]})", shot=_shot(page, "pay"))
        return r
    return _after_pay(page, r, s, f, tb)


def _after_pay(page, r, s, f, tb):
    t0, told = time.time(), False
    while time.time() - t0 < s["pay_wait_seconds"]:
        page.wait_for_timeout(1500)
        url = (page.url or "").lower()
        text = _text(page)
        if "thank_you" in url or "thank-you" in url or "/orders/" in url or \
                ("/checkouts" not in url and DONE_RE.search(text)) or re.search(r"your order is confirmed", text, re.I):
            r.update(status="paid", shot=_shot(page, "paid"))
            return r
        m = DECLINE_RE.search(text)
        if m:
            r.update(status="declined", why=m.group(0)[:150], shot=_shot(page, "declined"))
            return r
        bank = _frames_like(page, BANK_FRAME_HINTS)
        if not told and (bank or time.time() - t0 > 15):
            told = True
            if tb is not None:
                post(tb, f"🏦 **Approve the payment** for {f.get('name')} (total {money(r.get('total') or 0)}) in "
                         "your bank app, or the bot will give up in a few minutes.", tb.AMBER,
                     phone=f"Approve payment: {str(f.get('name'))[:50]}")
            r["status"] = "bank"
    r.update(status="unclear", why="no order confirmation came up (maybe the bank check timed out)",
             shot=_shot(page, "unclear"))
    return r


# ---------------------------------------------------------------- setup (run on the PC)
def setup(tb):
    """Open the buyer profile so you can sign in to Shop Pay and the shops. Close the window when done."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright isn't installed yet. Run:  py -3 -m pip install playwright")
        return 1
    cfg = tb.load_config()
    bases = []
    sealed = cfg.get("sealed") or {}
    for key in ("shopify_collections", "shopify_products", "shopify_search"):
        for shop in sealed.get(key) or []:
            u = shop.get("url") or shop.get("base") or ""
            if u.startswith("https://"):
                b = tb.origin(u)
                if b not in bases:
                    bases.append(b)
    print(__doc__.split("Turn it on")[0].strip())
    print("\nA Chrome window is opening on the bot's own profile (buyer_profile). In it:\n"
          "  1. shop.app tab: sign in to Shop Pay, and make sure your address and card are saved there.\n"
          "  2. Each shop tab: sign in if you have an account there (optional, Shop Pay does most shops).\n"
          "  3. Close the window when you're done. Nothing you type is read or kept by the bot.\n"
          "If it says the profile is in use, stop the bot first (restart_bot.bat stops it for a minute).")
    with sync_playwright() as pw:
        kw = {"user_data_dir": PROFILE_DIR, "headless": False, "viewport": None, "locale": "en-AU",
              "args": ["--start-maximized"]}
        try:
            ctx = pw.chromium.launch_persistent_context(channel="chrome", **kw)
        except Exception:  # noqa: BLE001
            ctx = pw.chromium.launch_persistent_context(**kw)
        first = ctx.pages[0] if ctx.pages else ctx.new_page()
        first.goto("https://shop.app/account")
        for b in bases:
            try:
                ctx.new_page().goto(b + "/account", wait_until="domcontentloaded", timeout=20000)
            except Exception:  # noqa: BLE001
                pass
        while ctx.pages:
            try:
                ctx.pages[0].wait_for_event("close", timeout=0)
            except Exception:  # noqa: BLE001
                break
        ctx.close()
    print("Saved. Now in Discord: /autobuy try link:<a product page> to check a shop works, "
          "then /autobuy set mode:test.")
    return 0


def try_now(tb, url):
    """Command line: python auto_buy.py --try <product page>: a test run, never pays."""
    cart, price, name = resolve_cart(tb, url)
    if not cart:
        print(f"Can't use that link: {name}")
        return 1
    job = {"f": {"id": f"try|{cart}", "kind": "Sealed", "name": name, "shop": urllib.parse.urlsplit(cart).netloc,
                 "price": price, "url": url, "cart": cart}, "t": time.time(), "mode": "test", "try": True}
    b = Buyer(tb)
    try:
        r = b.handle(job)
    finally:
        b.close()
    print(json.dumps({k: v for k, v in (r or {}).items() if k != "job"}, indent=1))
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    sys.path.insert(0, CODE_DIR)
    import tcg_bot
    if "--setup" in sys.argv:
        sys.exit(setup(tcg_bot))
    if "--try" in sys.argv and sys.argv.index("--try") + 1 < len(sys.argv):
        sys.exit(try_now(tcg_bot, sys.argv[sys.argv.index("--try") + 1]))
    print("Use:  py -3 auto_buy.py --setup        (sign in to Shop Pay and the shops, once)\n"
          "      py -3 auto_buy.py --try <link>   (a test checkout that never pays)")
