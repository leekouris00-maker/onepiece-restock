#!/usr/bin/env python3
"""
TCGplayer prices for One Piece singles and sealed, from TCGCSV (v2.8)
=====================================================================

TCGplayer no longer gives out API keys, so this reads TCGCSV (tcgcsv.com), a free public copy of
TCGplayer's own catalog and price data that its maintainer refreshes once a day (about 20:00 UTC,
around 7am Melbourne). No key or login: just ordinary downloads.

    python tcgplayer.py               sync if TCGCSV has new prices, then post the daily report (once per update)
    python tcgplayer.py --force       sync even if TCGCSV hasn't changed
    python tcgplayer.py --repost      post the report again even if today's is already out
    python tcgplayer.py --no-post     sync only
    python tcgplayer.py --dry-run     sync and print the report; posts and saves nothing
    python tcgplayer.py --lookup OP13-120     print what TCGplayer has for a card or product

How the data is laid out (TCGplayer's four levels):
    category (the game: One Piece is 68) > group (a set, e.g. OP13) > product (a card version or a sealed
    item) > price rows. Prices sit in a separate file per set and are joined to products by productId.
    A product can have more than one price row (Normal / Foil), so a price is keyed by productId + subtype.
    Market price = TCGplayer's estimate from recent sales; low = cheapest listing. No prices per
    condition (TCGCSV doesn't share SKUs), all in US dollars.

What's kept: tcgplayer_prices.json, one product per line, with the market price whenever it changed
over the last 5 weeks (so the report can say what moved and /tcgp can show a 7-day change).

The daily report (Discord: #tcgplayer-prices, else the price-drops channel, else #singles-alerts):
  📈 movers      singles and sealed whose US market moved the most since yesterday (and this week)
  🇦🇺 cheaper here  in-stock near-mint singles at Elemental Arcade / Good Games priced well under
                 TCGplayer's market (from the restock bot's own singles_prices.json)
  📦 boxes       booster box market prices for the newest sets, vs your sealed max
  🎯 want list   TCGplayer's price for each card on your want list, vs your max

Settings (optional) in config.json under "tcgplayer" - see DEFAULTS below. TCGCSV asks for one sync a
day, a clear User-Agent and a short pause between requests; this does about 180 requests a day.
"""
import argparse
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone

import tcg_bot as tb

TCGCSV = "https://tcgcsv.com"
CATEGORY_NAME = "one piece card game"
DEFAULT_CATEGORY = 68
PATH = os.path.join(tb.HERE, "tcgplayer_prices.json")
UA = f"onepiece-restock/{tb.VERSION} (personal Discord price bot; +https://github.com/leekouris00-maker/onepiece-restock)"
GAP = 0.2                    # seconds between requests (TCGCSV asks for at least 0.1)
TIMEOUT = 30
KEEP_DAYS = 35               # market-price changes kept this long (the last one before stays as "before")
HISTORY_MIN_USD = 0.5        # below this, no history is kept (thousands of bulk commons that never matter)
MAX_FAILED_SHARE = 0.2       # more sets than this failing = don't count the sync as done; try again next run
LOCAL_FRESH = 30 * 3600      # PC copy: a local file synced this recently is used, else the repo's copy
REPO_MAX_AGE = 6 * 3600
FALLBACK_AUD = 1.45

FX_SOURCES = [   # USD -> AUD; the first that answers wins
    ("frankfurter", "https://api.frankfurter.dev/v1/latest?base=USD&symbols=AUD", lambda j: j["rates"]["AUD"]),
    ("open.er-api", "https://open.er-api.com/v6/latest/USD", lambda j: j["rates"]["AUD"]),
]

DEFAULTS = {
    "enabled": True,
    "move_min_usd": 10.0,     # movers: only products with a market price of at least this (US$)
    "move_pct": 10.0,         # ...that moved at least this much
    "movers_top": 8,
    "deal_pct": 25.0,         # cheaper here: a shop price at least this far under TCGplayer's market...
    "deal_min_aud": 10.0,     # ...for a card TCGplayer values at A$10 or more...
    "deal_min_save": 5.0,     # ...saving at least A$5
    "deals_top": 12,
    "boxes_top": 12,
    "aud_rate": None,         # set a number to use your own exchange rate instead of looking it up
}

PURPLE, GOLD, GREEN, BLUE, GREY = 0x9B5DE5, 0xE9C46A, 0x2A9D8F, 0x457B9D, 0x6C757D
CARD_NUM_RE = re.compile(r"\b(?:(?:OP|EB|ST|PRB)\d{2}|P)-\d{3}\b", re.I)
NUMISH = re.compile(r"^(?:(?:OP|EB|ST|PRB)\d{2}-\d{3}|P-\d{3}|\d{3})$", re.I)   # "(OP01-016)", "(120)": not versions
VARIANT_SYNONYMS = {"alt art": "alternate art", "parallel": "alternate art", "aa": "alternate art",
                    "special": "sp", "special art": "sp"}
SET_STOP = {"the", "of", "a", "an", "and", "card", "cards", "one", "piece", "game"}

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:  # noqa: BLE001
    pass


# ---------------------------------------------------------------- downloading
def _get(url, tries=3):
    last = None
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip",
                                                   "Accept": "application/json, text/plain, */*"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code not in (408, 425, 429, 500, 502, 503, 504):
                break
            time.sleep(5 * (attempt + 1) if e.code == 429 else 2 * (attempt + 1))
        except (OSError, ValueError) as e:
            last = str(e)
            time.sleep(2 * (attempt + 1))
    raise OSError(f"{url}: {last}")


def get_json(url):
    j = json.loads(_get(url).decode("utf-8", "replace"))
    if isinstance(j, dict) and j.get("success") is False:
        raise OSError(f"{url}: {j.get('errors')}")
    return j


def day_of(stamp):
    """'2026-10-23T20:06:07+0000' -> a day number (date.toordinal); today's UTC day if unreadable."""
    try:
        return date.fromisoformat(str(stamp)[:10]).toordinal()
    except ValueError:
        return datetime.now(timezone.utc).date().toordinal()


def day_label(d):
    return date.fromordinal(int(d)).strftime("%a %d %b").replace(" 0", " ")


# ---------------------------------------------------------------- the saved copy
def settings(cfg):
    s = dict(DEFAULTS)
    mine = (cfg or {}).get("tcgplayer")
    if isinstance(mine, dict):
        for k, v in mine.items():
            if k in DEFAULTS and v is not None:
                s[k] = v
    return s


def empty_store():
    return {"v": 1, "updated": "", "synced": 0, "day": 0, "category": DEFAULT_CATEGORY, "fx": {}, "posted": "",
            "groups": {}, "items": {}}


def load_store(path=PATH):
    s = tb.read_json(path, None)
    if not isinstance(s, dict) or s.get("v") != 1 or not isinstance(s.get("items"), dict):
        return empty_store()
    base = empty_store()
    base.update(s)
    return base


def save_store(store, path=PATH):
    """One product per line, so the daily commits of this file stay small and readable."""
    head = {k: v for k, v in store.items() if k not in ("items", "groups")}
    rows = ",\n".join(f"{json.dumps(k)}:{json.dumps(v, separators=(',', ':'), ensure_ascii=False)}"
                      for k, v in sorted(store["items"].items(), key=lambda kv: (len(kv[0]), kv[0])))
    text = (json.dumps(head, separators=(",", ":"), sort_keys=True)[:-1]
            + ',"groups":' + json.dumps(store.get("groups", {}), separators=(",", ":"), sort_keys=True, ensure_ascii=False)
            + ',"items":{\n' + rows + "\n}}\n")
    tb.atomic_write_text(path, text)
    _index_cache.clear()


def load_for(cfg=None):
    """The copy to read from: the local file if it was synced in the last 30 hours (the cloud copy, or a
    PC that runs the sync), otherwise the cloud copy's file from the GitHub repo (kept 6 hours)."""
    local = load_store()
    if local["items"] and time.time() - float(local.get("synced") or 0) < LOCAL_FRESH:
        return local
    remote = tb.repo_json(cfg or {}, "tcgplayer_prices.json", max_age=REPO_MAX_AGE)
    if isinstance(remote, dict) and remote.get("v") == 1 and isinstance(remote.get("items"), dict):
        base = empty_store()
        base.update(remote)
        if float(base.get("synced") or 0) > float(local.get("synced") or 0):
            try:
                save_store(base)
            except Exception:  # noqa: BLE001
                pass
            return base
    return local


# ---------------------------------------------------------------- syncing
def find_category(log=print):
    try:
        cats = get_json(f"{TCGCSV}/tcgplayer/categories").get("results") or []
        for c in cats:
            if CATEGORY_NAME in f"{c.get('name', '')} {c.get('displayName', '')}".lower():
                return int(c["categoryId"])
    except Exception as e:  # noqa: BLE001
        log(f"   ! TCGplayer: couldn't read the category list ({e}); using {DEFAULT_CATEGORY}")
    return DEFAULT_CATEGORY


def extended(p):
    return {str(e.get("name")): e.get("value") for e in p.get("extendedData") or [] if isinstance(e, dict)}


def kind_of(p, ext):
    if str(ext.get("CardType") or "").upper().startswith("DON") or str(ext.get("Rarity") or "").upper().startswith("DON"):
        return "don"
    return "card" if ext.get("Number") else "sealed"


def _num(x):
    try:
        v = float(x)
        return round(v, 2) if v == v and v >= 0 else None
    except (TypeError, ValueError):
        return None


def note_price(it, day, market):
    """Add today's market price to an item's history when it changed (one point per day at most)."""
    h = it.setdefault("h", [])
    if market is None or (market < HISTORY_MIN_USD and not h):
        return
    if h and h[-1][1] == market:
        return
    if h and h[-1][0] == day:
        h[-1][1] = market
        if len(h) > 1 and h[-2][1] == market:
            h.pop()
    else:
        h.append([day, market])


def apply_group(store, group, products, prices, day, seen):
    gid = str(group["groupId"])
    store["groups"][gid] = {"n": str(group.get("name") or ""), "a": str(group.get("abbreviation") or ""),
                            "d": str(group.get("publishedOn") or "")[:10]}
    rows = {}
    for r in prices or []:
        if isinstance(r, dict) and r.get("productId") is not None:
            rows.setdefault(int(r["productId"]), []).append(r)
    items = store["items"]
    for p in products or []:
        try:
            pid = int(p["productId"])
        except (KeyError, TypeError, ValueError):
            continue
        ext = extended(p)
        pr = rows.get(pid) or []
        if not pr:
            continue
        for r in pr:
            sub = str(r.get("subTypeName") or "Normal")
            key = str(pid) if len(pr) == 1 else f"{pid}:{sub}"
            name = re.sub(r"\s+", " ", str(p.get("name") or "")).strip()
            it = items.get(key) or {}
            it.update({"n": name + ("" if len(pr) == 1 else f" ({sub})"), "g": gid, "t": kind_of(p, ext),
                       "m": _num(r.get("marketPrice")), "l": _num(r.get("lowPrice"))})
            num = str(ext.get("Number") or "").strip().upper()
            if num:
                it["num"] = num
            else:
                it.pop("num", None)
            rar = str(ext.get("Rarity") or "").strip()
            if rar:
                it["r"] = rar
            else:
                it.pop("r", None)
            note_price(it, day, it["m"])
            items[key] = it
            seen.add(key)


def prune(store, day):
    cut = day - KEEP_DAYS
    for it in store["items"].values():
        h = it.get("h") or []
        old = [pt for pt in h if pt[0] < cut]
        if old:
            it["h"] = old[-1:] + [pt for pt in h if pt[0] >= cut]


def get_fx(store, cfg, log=print):
    s = settings(cfg)
    if s.get("aud_rate"):
        store["fx"] = {"rate": float(s["aud_rate"]), "date": "", "src": "config.json"}
        return store["fx"]
    for name, url, pick in FX_SOURCES:
        try:
            rate = float(pick(json.loads(_get(url, tries=2).decode("utf-8", "replace"))))
            if 0.5 < rate < 5:
                store["fx"] = {"rate": round(rate, 4), "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                               "src": name}
                return store["fx"]
        except Exception as e:  # noqa: BLE001
            log(f"   ! exchange rate from {name}: {e}")
    if not (store.get("fx") or {}).get("rate"):
        store["fx"] = {"rate": FALLBACK_AUD, "date": "", "src": "fallback"}
    return store["fx"]


def sync(store, cfg=None, force=False, log=print, sleep=time.sleep):
    """Download today's TCGplayer prices into the store. -> "same" (nothing new on TCGCSV), "done",
    or "partial" (too many sets failed: saved, but tried again next run)."""
    stamp = _get(f"{TCGCSV}/last-updated.txt").decode("utf-8", "replace").strip()
    if not force and stamp and stamp == store.get("updated"):
        log(f"   (TCGplayer: TCGCSV still has {stamp}, already synced)")
        return "same"
    cat = find_category(log)
    store["category"] = cat
    groups = get_json(f"{TCGCSV}/tcgplayer/{cat}/groups").get("results") or []
    if not groups:
        raise OSError("TCGCSV returned no sets for One Piece")
    day = day_of(stamp)
    seen, failed = set(), set()
    t0 = time.time()
    for g in groups:
        gid = g.get("groupId")
        try:
            products = get_json(f"{TCGCSV}/tcgplayer/{cat}/{gid}/products").get("results") or []
            sleep(GAP)
            prices = get_json(f"{TCGCSV}/tcgplayer/{cat}/{gid}/prices").get("results") or []
            sleep(GAP)
        except Exception as e:  # noqa: BLE001
            log(f"   ! TCGplayer: {g.get('name')}: {e}")
            failed.add(str(gid))
            continue
        apply_group(store, g, products, prices, day, seen)
    for k in [k for k, it in store["items"].items() if k not in seen and it.get("g") not in failed]:
        del store["items"][k]               # gone from TCGplayer
    prune(store, day)
    _index_cache.clear()
    get_fx(store, cfg, log)
    store["synced"] = round(time.time())
    store["day"] = day
    ok = len(failed) <= MAX_FAILED_SHARE * len(groups)
    if ok:
        store["updated"] = stamp
    log(f"   (TCGplayer: {len(seen):,} prices from {len(groups) - len(failed)}/{len(groups)} sets in "
        f"{time.time() - t0:.0f}s; US$1 = A${store['fx']['rate']:g} ({store['fx']['src']}))")
    return "done" if ok else "partial"


# ---------------------------------------------------------------- reading prices
def url(key):
    return f"https://www.tcgplayer.com/product/{str(key).split(':')[0]}"


def rate(store):
    return float((store.get("fx") or {}).get("rate") or FALLBACK_AUD)


def price_on(it, day):
    """The market price on that day (the last change on or before it), or None if the record is newer."""
    v = None
    for d, m in it.get("h") or []:
        if d <= day:
            v = m
        else:
            break
    return v


def change(it, today, days):
    """(old price, % change) over the last `days` days, or (None, None)."""
    old, now = price_on(it, today - days), it.get("m")
    if not old or now is None:
        return None, None
    return old, (now - old) / old * 100


def group_name(store, it):
    return ((store.get("groups") or {}).get(str(it.get("g"))) or {}).get("n", "")


def group_abbr(store, it):
    return ((store.get("groups") or {}).get(str(it.get("g"))) or {}).get("a", "")


def label(store, it, n=60):
    """'Sabo (120) (Parallel)' -> 'Sabo (Parallel) · OP13-120', sealed -> its name · set code."""
    name = re.sub(r"\s*\((?:\d{3}|(?:OP|EB|ST|PRB)\d{2}-\d{3}|P-\d{3})\)", "", it.get("n", ""), flags=re.I)
    name = re.sub(r"\s+-\s*(?:OP|EB|ST|PRB)\d{2}-\d{3}\b", "", name, flags=re.I).strip()
    tail = it.get("num") or group_abbr(store, it)
    return tb.link_text(f"{name} · {tail}" if tail else name, n)


def aud(store, usd):
    return None if usd is None else usd * rate(store)


def both(store, usd):
    if usd is None:
        return "no sales yet"
    return f"US${usd:,.2f} (A${aud(store, usd):,.2f})"


# ---------------------------------------------------------------- matching shop singles to TCGplayer
def _norm_version(p):
    p = re.sub(r"\s+", " ", p.strip().lower())
    return VARIANT_SYNONYMS.get(p, p)


def tcg_version(name):
    """TCGplayer name -> its version words: 'Sabo (120) (Parallel)' -> ('alternate art',),
    'Monkey.D.Luffy (Super Pre-Release) [Winner]' -> ('super pre-release', 'winner')."""
    name = str(name or "")
    parts = re.findall(r"\(([^()]*)\)", name)
    parts += re.findall(r"\[([^\]]*)\]", re.sub(r"\([^()]*\)", " ", name))
    out = {_norm_version(p) for p in parts if p.strip() and not NUMISH.match(p.strip())}
    return tuple(sorted(out))


def shop_version(name):
    """A shop title's version words (its square brackets are the set, not a version):
    'Shanks (Parallel) - OP01-120 [Romance Dawn]' -> ('alternate art',)."""
    parts = re.findall(r"\(([^()]*)\)", str(name or ""))
    out = {_norm_version(p) for p in parts if p.strip() and not NUMISH.match(p.strip())}
    return tuple(sorted(out))


def shop_set(name):
    sets = re.findall(r"\[([^\]]*)\]", str(name or ""))
    return sets[-1] if sets else ""


def set_words(s):
    return {w for w in re.findall(r"[a-z0-9]+", str(s or "").lower()) if w not in SET_STOP}


def set_score(a, b):
    """(overlap of the smaller, Jaccard) between two set names. 'Two Legends' scores (1, 1) against
    'Two Legends' and (1, 0.5) against 'Two Legends Pre-Release Cards', so the exact set wins."""
    A, B = set_words(a), set_words(b)
    if not A or not B:
        return 0.0, 0.0
    inter = len(A & B)
    return inter / min(len(A), len(B)), inter / len(A | B)


_index_cache = {}


def index(store):
    """card number -> [item keys] (cards only), cached per store."""
    hit = _index_cache.get(id(store))
    if hit and hit[0] is store:
        return hit[1]
    by = {}
    for k, it in store.get("items", {}).items():
        if it.get("t") == "card" and it.get("num"):
            by.setdefault(it["num"], []).append(k)
    _index_cache.clear()
    _index_cache[id(store)] = (store, by)
    return by


def match(store, shop_name):
    """The TCGplayer item key for a shop single's title, or None when it isn't clear which one it is.
    Same card number, same version words, and if that still leaves more than one (a card reprinted in
    another set), the one whose set name fits the shop's set name best."""
    m = CARD_NUM_RE.search(str(shop_name or ""))
    if not m:
        return None
    ver = shop_version(shop_name)
    items = store.get("items", {})
    cands = [k for k in index(store).get(m.group(0).upper(), []) if tcg_version(items[k].get("n")) == ver]
    if len(cands) == 1:
        return cands[0]
    if not cands:
        return None
    sset = shop_set(shop_name)
    if not sset:
        return None
    scored = sorted(((set_score(sset, group_name(store, items[k])), k) for k in cands), reverse=True)
    best, second = scored[0], scored[1]
    if best[0][0] < 0.5 or best[0] == second[0]:
        return None
    return best[1]


# ---------------------------------------------------------------- the daily report
def movers(store, s, days=1):
    today = int(store.get("day") or 0)
    up, down = [], []
    for k, it in store.get("items", {}).items():
        now = it.get("m")
        if now is None or now < float(s["move_min_usd"]):
            continue
        old, pct = change(it, today, days)
        if pct is None or abs(pct) < float(s["move_pct"]):
            continue
        (up if pct > 0 else down).append((pct, k, old, now))
    up.sort(key=lambda x: -x[0])
    down.sort(key=lambda x: x[0])
    n = int(s["movers_top"])
    return up[:n], down[:n]


def shop_deals(store, drops, s):
    """In-stock near-mint singles at the shops priced well under TCGplayer's market (in A$)."""
    out = []
    bases = {sh: (v or {}).get("base", "") for sh, v in (drops.get("shops") or {}).items()}
    for key, it in (drops.get("items") or {}).items():
        pts = it.get("p") or []
        if not pts or not pts[-1][2]:
            continue
        price = float(pts[-1][1])
        tk = match(store, it.get("n"))
        if not tk:
            continue
        t = store["items"][tk]
        mk = aud(store, t.get("m"))
        if mk is None or mk < float(s["deal_min_aud"]):
            continue
        save = mk - price
        pct = save / mk * 100
        if pct < float(s["deal_pct"]) or save < float(s["deal_min_save"]):
            continue
        shop, _, handle = key.partition("|")
        link = f"{bases.get(shop, '')}/products/{handle}" if bases.get(shop) else ""
        out.append({"shop": shop, "name": it.get("n"), "price": price, "url": link, "tkey": tk,
                    "market_aud": mk, "save": save, "pct": pct, "check": price < 0.35 * mk})
    out.sort(key=lambda d: -d["save"])
    return out


def is_box(it):
    n = it.get("n", "").lower()
    return it.get("t") == "sealed" and "booster box" in n and "case" not in n and "sleeved" not in n


def boxes(store, s):
    groups = store.get("groups") or {}
    out = [(k, it) for k, it in store.get("items", {}).items() if is_box(it) and it.get("m")]
    out.sort(key=lambda kv: (groups.get(str(kv[1].get("g")), {}).get("d", ""), kv[1].get("m") or 0), reverse=True)
    return out[:int(s["boxes_top"])]


def want_lines(store, cfg):
    """Each card on the want list (enabled, not owned): the cheapest TCGplayer version it would take."""
    lines = []
    idx = index(store)
    for c in ((cfg or {}).get("singles") or {}).get("cards") or []:
        if not isinstance(c, dict) or c.get("enabled") is False or not c.get("num"):
            continue
        if c.get("owned") and c.get("qty") and int(c["owned"]) >= int(c["qty"]):
            continue
        excl = [str(w).lower() for w in c.get("exclude") or []]
        opts = [(k, store["items"][k]) for k in idx.get(str(c["num"]).upper(), [])]
        opts = [(k, it) for k, it in opts if it.get("m") is not None
                and not any(w.strip() and w in it["n"].lower() for w in excl)]
        if not opts:
            continue
        key, best = min(opts, key=lambda kv: kv[1]["m"])
        mx = c.get("max")
        mark = ""
        if isinstance(mx, (int, float)):
            mark = " ✅ under your max" if aud(store, best["m"]) <= mx else f" · your max A${mx:g}"
        lines.append(f"[{label(store, best, 50)}]({url(key)}) **A${aud(store, best['m']):,.2f}**{mark}")
    return lines


def _fit(lines, limit=3900, more="…and {n} more"):
    out, size = [], 0
    for i, ln in enumerate(lines):
        if size + len(ln) > limit:
            out.append(more.format(n=len(lines) - i))
            break
        out.append(ln)
        size += len(ln) + 1
    return "\n".join(out)


def _mover_line(store, x):
    pct, k, old, now = x
    it = store["items"][k]
    arrow = "▲" if pct > 0 else "▼"
    return (f"{arrow} **{abs(pct):.0f}%** [{label(store, it, 55)}]({url(k)}) **A${aud(store, now):,.2f}** "
            f"(was A${aud(store, old):,.2f})")


def report(store, cfg, drops=None):
    """The daily report as a list of Discord embeds (one per message)."""
    s = settings(cfg)
    fx = store.get("fx") or {}
    stamp = store.get("updated") or ""
    when = day_label(day_of(stamp)) if stamp else "today"
    foot = (f"TCGplayer market prices (US) via TCGCSV, {when} · US$1 = A${rate(store):g}"
            f"{' (' + fx['src'] + ')' if fx.get('src') else ''} · A$ is the US price converted, before shipping")
    embeds = []

    up, down = movers(store, s, 1)
    wup, wdown = movers(store, s, 7)
    today = int(store.get("day") or 0)
    have_history = any((it.get("h") or [[today]])[0][0] <= today - 1 for it in store.get("items", {}).values())
    fields = []
    if up:
        fields.append({"name": "Up since yesterday", "value": _fit([_mover_line(store, x) for x in up], 1000)})
    if down:
        fields.append({"name": "Down since yesterday", "value": _fit([_mover_line(store, x) for x in down], 1000)})
    if wup:
        fields.append({"name": "Up this week", "value": _fit([_mover_line(store, x) for x in wup[:5]], 1000)})
    if wdown:
        fields.append({"name": "Down this week", "value": _fit([_mover_line(store, x) for x in wdown[:5]], 1000)})
    if not fields:
        desc = ("First day of TCGplayer prices: movers start tomorrow, once there's a yesterday to compare with."
                if not have_history else
                f"Nothing worth US${float(s['move_min_usd']):g}+ moved {float(s['move_pct']):g}% or more.")
    else:
        desc = f"Products worth US${float(s['move_min_usd']):g}+ that moved {float(s['move_pct']):g}% or more."
    embeds.append({"title": "📈 TCGplayer movers", "color": PURPLE, "description": desc, "fields": fields,
                   "footer": {"text": foot}})

    if drops is not None:
        deals = shop_deals(store, drops, s)
        lines = []
        for d in deals[:int(s["deals_top"])]:
            name = tb.link_text(d["name"], 60)
            head = f"[{name}]({d['url']})" if d["url"] else name
            warn = " ⚠️ check it's the same version" if d["check"] else ""
            lines.append(f"{head} **A${d['price']:,.2f}** at {d['shop']} · TCGplayer [A${d['market_aud']:,.2f}]"
                         f"({url(d['tkey'])}) · {d['pct']:.0f}% under{warn}")
        desc = (_fit(lines) if lines else
                f"No in-stock single at the shops is {float(s['deal_pct']):g}%+ under TCGplayer's market right now.")
        embeds.append({"title": "🇦🇺 Cheaper here than TCGplayer", "color": GREEN, "description": desc,
                       "footer": {"text": f"Near-mint, in stock at {', '.join(sorted(drops.get('shops') or {})) or 'the shops'}"
                                          f" · matched by card number, version and set · {foot}"[:2048]}})

    bx = boxes(store, s)
    if bx:
        mx = float(((cfg or {}).get("sealed") or {}).get("max_price") or 0)
        lines = []
        for k, it in bx:
            wk, pct = change(it, today, 7)
            trend = f" · {'▲' if pct > 0 else '▼'}{abs(pct):.0f}% this week" if pct is not None and abs(pct) >= 1 else ""
            under = " ✅ under your max" if mx and aud(store, it["m"]) <= mx else ""
            lines.append(f"[{label(store, it, 55)}]({url(k)}) **A${aud(store, it['m']):,.0f}** "
                         f"(US${it['m']:,.0f}){trend}{under}")
        embeds.append({"title": "📦 Booster boxes on TCGplayer", "color": BLUE, "description": _fit(lines),
                       "footer": {"text": (f"Newest sets first · your sealed max is A${mx:g} · " if mx else "") + foot}})

    wl = want_lines(store, cfg)
    if wl:
        embeds.append({"title": "🎯 Your want list on TCGplayer", "color": GOLD, "description": _fit(wl),
                       "footer": {"text": "Cheapest version each card would take (your excludes left out) · " + foot}})
    return embeds


def hook_for(cfg):
    a = (cfg or {}).get("alerts") or {}
    return (a.get("discord_webhook_prices") or a.get("discord_webhook_drops") or a.get("discord_webhook_singles")
            or a.get("discord_webhook"))


def post(store, cfg, embeds):
    alerts = (cfg or {}).get("alerts") or {}
    hook = hook_for(cfg)
    if not hook:
        print("   (TCGplayer: no Discord webhook set, report not posted)")
        return False
    ok = True
    for e in embeds:
        payload = {"username": alerts.get("bot_name") or "One Piece Restock", "embeds": [e],
                   "allowed_mentions": {"parse": []}}
        ok = tb.discord_send(alerts, hook, payload) and ok
    return ok


# ---------------------------------------------------------------- /tcgp lookups
def search(store, query, limit=12):
    q = str(query or "").strip().lower()
    if not q:
        return []
    m = CARD_NUM_RE.search(q)
    num = m.group(0).upper() if m else ""
    rest = (q[:m.start()] + " " + q[m.end():]) if m else q
    words = [w for w in re.split(r"[^a-z0-9]+", rest) if w]
    out = []
    for k, it in store.get("items", {}).items():
        if num and it.get("num") != num:
            continue
        hay = f"{it.get('n', '')} {it.get('num', '')} {group_name(store, it)} {group_abbr(store, it)}".lower()
        flat = re.sub(r"[^a-z0-9]", "", hay)
        if all(w in hay or w in flat for w in words) and (num or words):
            out.append((-(it.get("m") or 0), k))
    out.sort()
    return [k for _, k in out[:limit]]


def lookup_embed(store, query):
    if not store.get("items"):
        return {"title": "🇺🇸 TCGplayer", "color": GREY,
                "description": "No TCGplayer prices yet: the cloud copy downloads them once a day (about 7:45am)."}
    keys = search(store, query)
    if not keys:
        return {"title": f"🇺🇸 Nothing on TCGplayer matches “{query}”"[:256], "color": GREY,
                "description": "Try a card number like `OP13-120`, a name like `sabo wanted`, or a product like "
                               "`op13 booster box`."}
    today = int(store.get("day") or 0)
    lines = []
    for k in keys:
        it = store["items"][k]
        _, pct = change(it, today, 7)
        span = "this week"
        h = it.get("h") or []
        if pct is None and h and h[0][0] < today and h[0][1] and it.get("m") is not None:
            pct, span = (it["m"] - h[0][1]) / h[0][1] * 100, f"since {day_label(h[0][0])}"   # under a week of record
        trend = f" · {'▲' if pct > 0 else '▼'}{abs(pct):.0f}% {span}" if pct is not None and abs(pct) >= 1 else ""
        low = f" · lowest listing US${it['l']:,.2f}" if it.get("l") is not None else ""
        lines.append(f"[{label(store, it, 60)}]({url(k)}) · {group_name(store, it)[:40]}\n"
                     f"   market **{both(store, it.get('m'))}**{low}{trend}")
    stamp = store.get("updated") or ""
    return {"title": f"🇺🇸 TCGplayer · “{query}”"[:256], "color": PURPLE, "description": _fit(lines, 3900),
            "footer": {"text": f"US market prices via TCGCSV, {day_label(day_of(stamp)) if stamp else ''} · "
                               f"US$1 = A${rate(store):g} · no prices per condition (near-mint-ish market)"}}


def value_line(store, shop_name):
    """For /value: TCGplayer's market for the same card and version, or ''."""
    if not store or not store.get("items"):
        return ""
    k = match(store, shop_name)
    if not k:
        return ""
    it = store["items"][k]
    if it.get("m") is None:
        return ""
    return f"TCGplayer (US) market **A${aud(store, it['m']):,.2f}** (US${it['m']:,.2f}) · [view]({url(k)})"


# ---------------------------------------------------------------- command line
def main():
    ap = argparse.ArgumentParser(description="TCGplayer prices from TCGCSV for the restock bot")
    ap.add_argument("--force", action="store_true", help="sync even if TCGCSV hasn't changed")
    ap.add_argument("--repost", action="store_true", help="post the report even if it's already out today")
    ap.add_argument("--no-post", action="store_true", help="sync only")
    ap.add_argument("--dry-run", action="store_true", help="print the report; post and save nothing")
    ap.add_argument("--lookup", metavar="SEARCH", help="print what TCGplayer has for a card or product")
    a = ap.parse_args()

    cfg = tb.load_config()
    if a.dry_run:
        tb.DRY_RUN[0] = True
    store = load_store()
    if a.lookup:
        e = lookup_embed(store, a.lookup)
        print(e["title"] + "\n" + e["description"])
        return 0
    if not settings(cfg)["enabled"]:
        print("TCGplayer prices are switched off (\"tcgplayer\": {\"enabled\": false} in config.json).")
        return 0
    try:
        result = sync(store, cfg, force=a.force)
    except Exception as e:  # noqa: BLE001
        print(f"   ! TCGplayer sync failed: {e}")
        return 1
    if result != "same" and not a.dry_run:
        save_store(store)
    if a.no_post:
        return 0
    if result == "partial":
        print("   (TCGplayer: too many sets failed; the report waits for a full sync)")
        return 0
    if store.get("posted") == store.get("updated") and not (a.repost or a.dry_run):
        print("   (TCGplayer: today's report is already posted)")
        return 0
    embeds = report(store, cfg, drops=tb.load_drops_store())
    if a.dry_run:
        for e in embeds:
            print(f"\n== {e['title']} ==\n{e.get('description', '')}")
            for f in e.get("fields") or []:
                print(f"-- {f['name']}\n{f['value']}")
            print(f"[{e.get('footer', {}).get('text', '')}]")
        return 0
    if post(store, cfg, embeds):
        store["posted"] = store.get("updated")
        save_store(store)
        print(f"   (TCGplayer: posted the daily report, {len(embeds)} messages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
