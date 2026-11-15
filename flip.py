#!/usr/bin/env python3
"""
Market price and flip estimate for the One Piece restock bot (v2.22)
====================================================================
Answers "if I buy this box at this price, what's it worth?" from data the bot already has: the daily
TCGplayer prices (tcgplayer_prices.json, synced by the cloud copy from TCGCSV). No extra requests to shops.

  * Booster-box alerts get a "Market" line: TCGplayer's US market price in A$, and what's left if you
    resold at that price after your selling costs.
  * /flip <item> [price] does the same sum on demand.
  * ebay_watch.json entries can alert at a % under market (see ebay_watch.py).

READ THIS ABOUT THE NUMBERS. They are estimates to help you decide, not a forecast:
  * The market figure is TCGplayer's US market price converted at the day's exchange rate. Australian
    resale prices can sit above or below it, and it says nothing about how fast something sells.
  * Only English booster boxes are matched (by set code, e.g. OP-18). Japanese boxes, cases and anything
    without a set code get no market line rather than a wrong one.
  * Selling costs are yours to set in config.json:
        "flip": {"ebay_fee_pct": 0, "fixed_fee": 0, "postage": 12}
    ebay_fee_pct is 0 by default because, since May 2026, eBay Australia charges no transaction fee to
    Australian sellers with under A$25,000 of sales in the past 12 months. On an eBay Pro plan (or over
    that amount) it is 13.4% + A$0.30 for most categories: set "ebay_fee_pct": 13.4, "fixed_fee": 0.3.
    "postage" is what it costs YOU to send a box (a guess of A$12; change it to what you actually pay).
    "flip": false switches the whole thing off.
"""
import json
import os
import re
import time

HERE = os.environ.get("BOT_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "tcgplayer_prices.json")
DEFAULTS = {"ebay_fee_pct": 0.0, "fixed_fee": 0.0, "postage": 12.0}
FALLBACK_AUD = 1.45
LOCAL_FRESH = 30 * 3600         # a local price file synced this recently is used as is
REPO_MAX_AGE = 6 * 3600         # otherwise the cloud copy's file is fetched from the repo at most this often
STALE = 7 * 86400               # prices older than this aren't quoted at all
CODE_RE = re.compile(r"(?<![A-Za-z0-9])(OP|EB|PRB|ST)[\s-]?0?(\d{1,2})(?!\d)", re.I)
BOX_RE = re.compile(r"\b(booster\s+box|booster\s+display|display\s+box|booster\s+display\s+box)\b", re.I)
NOT_ENGLISH_RE = re.compile(r"\b(japanese|japan|jpn?|chinese|korean|asia|asian)\b|\[jp\]", re.I)
NOT_ONE_BOX_RE = re.compile(r"\b(case|carton|sleeved|bundle|deposit)\b|\b\d+\s*x\b|\bx\s*\d+\b", re.I)

_cache = {"path": None, "mtime": None, "store": None}


def _num(x):
    if isinstance(x, bool) or x is None:
        return None
    try:
        return float(str(x).strip())
    except (TypeError, ValueError):
        return None


def settings(cfg):
    """Your selling costs, or None if "flip" is false."""
    raw = (cfg or {}).get("flip", True)
    if raw is False:
        return None
    s = dict(DEFAULTS)
    if isinstance(raw, dict):
        for k in DEFAULTS:
            v = _num(raw.get(k))
            if v is not None and v >= 0:
                s[k] = v
    s["ebay_fee_pct"] = min(s["ebay_fee_pct"], 50.0)
    return s


def warnings(cfg):
    raw = (cfg or {}).get("flip")
    if raw is None or isinstance(raw, (bool, dict)):
        return [f'"flip" → "{k}" should be a number of 0 or more; using {DEFAULTS[k]:g}'
                for k in DEFAULTS if isinstance(raw, dict) and k in raw and (_num(raw[k]) is None or _num(raw[k]) < 0)]
    return ['"flip" should be {"ebay_fee_pct": 0, "fixed_fee": 0, "postage": 12} or false; using the defaults']


# ---------------------------------------------------------------- the price file
def load_store(path=None):
    """tcgplayer_prices.json, re-read only when the file changes. {} if it isn't there or isn't usable."""
    path = path or PATH
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    if _cache["path"] == path and _cache["mtime"] == mtime:
        return _cache["store"]
    try:
        with open(path, encoding="utf-8") as f:
            store = json.load(f)
    except (OSError, ValueError):
        store = {}
    if not isinstance(store, dict) or not isinstance(store.get("items"), dict):
        store = {}
    _cache.update(path=path, mtime=mtime, store=store)
    return store


def fresh(store, now=None, limit=STALE):
    return bool(store) and (now or time.time()) - float(store.get("synced") or 0) < limit


def refresh(tb, cfg, now=None):
    """PC copy: the cloud copy syncs the prices once a day, so if the local file is over 30 hours old, take
    the newer one from the bot's GitHub repo (asked at most every 6 hours). Returns the store to use."""
    local = load_store()
    if fresh(local, now, LOCAL_FRESH) or getattr(tb, "IN_ACTIONS", False):
        return local
    remote = tb.repo_json(cfg or {}, "tcgplayer_prices.json", max_age=REPO_MAX_AGE)
    if (isinstance(remote, dict) and isinstance(remote.get("items"), dict)
            and float(remote.get("synced") or 0) > float(local.get("synced") or 0)):
        try:
            if not tb.DRY_RUN[0]:
                tb.atomic_write_json(PATH, remote)
        except Exception:  # noqa: BLE001
            pass
        _cache.update(path=None, mtime=None, store=None)
        return remote if tb.DRY_RUN[0] else (load_store() or remote)
    return local


def rate(store):
    return float((store.get("fx") or {}).get("rate") or FALLBACK_AUD)


# ---------------------------------------------------------------- matching
def codes_in(text):
    """Set codes in a title: 'OP-18', 'op18', 'OP 18', '[EB-05]' -> ['OP18', 'EB05']."""
    out = []
    for letters, digits in CODE_RE.findall(str(text or "")):
        code = f"{letters.upper()}{int(digits):02d}"
        if code not in out:
            out.append(code)
    return out


def _group_code(store, it):
    """A product's own set code from its TCGplayer set ('OP18', 'PRB-02' -> 'PRB02'; 'OP14-EB04' -> 'OP14')."""
    abbr = ((store.get("groups") or {}).get(str(it.get("g"))) or {}).get("a", "")
    found = codes_in(abbr)
    return found[0] if found else ""


def _is_box(it):
    n = str(it.get("n", "")).lower()
    return it.get("t") == "sealed" and "booster box" in n and "case" not in n and "sleeved" not in n


def _entry(store, key, it):
    usd = _num(it.get("m"))
    if not usd or usd <= 0:
        return None
    return {"key": str(key), "name": str(it.get("n", "")), "code": _group_code(store, it), "usd": usd,
            "aud": round(usd * rate(store), 2), "url": f"https://www.tcgplayer.com/product/{str(key).split(':')[0]}"}


def box_market(store, code):
    """TCGplayer's market for the English booster box of one set ('OP-18'), or None. If a set has more than
    one box (OP-01's two print waves), the cheaper one, so the estimate errs low."""
    want = codes_in(code)
    if not want or not store:
        return None
    hits = [e for e in (_entry(store, k, it) for k, it in store.get("items", {}).items()
                        if _is_box(it) and _group_code(store, it) == want[0]) if e]
    return min(hits, key=lambda e: e["usd"]) if hits else None


def listing_market(store, name):
    """The market for a shop listing, only when it's plainly ONE English booster box of ONE set. None otherwise:
    no line is better than the wrong box's price."""
    name = str(name or "")
    if not BOX_RE.search(name) or NOT_ENGLISH_RE.search(name) or NOT_ONE_BOX_RE.search(name):
        return None
    codes = codes_in(name)
    if len(codes) != 1:
        return None
    return box_market(store, codes[0])


def lookup(store, ref):
    """For /flip and ebay_watch.json: a set code ('OP-18' = that set's booster box) or a TCGplayer product
    number (the number in the product's tcgplayer.com link; 'id:subtype' also works)."""
    ref = str(ref or "").strip()
    if not ref or not store:
        return None
    items = store.get("items", {})
    if re.fullmatch(r"\d{4,}(:\w+)?", ref):
        for key in ([ref] if ref in items else []) + [k for k in items if str(k).split(":")[0] == ref.split(":")[0]]:
            e = _entry(store, key, items[key])
            if e:
                return e
        return None
    return box_market(store, ref)


# ---------------------------------------------------------------- the sum
def estimate(market_aud, buy, s):
    """Resell at the market price: what the costs are and what's left. All A$."""
    fee = market_aud * s["ebay_fee_pct"] / 100 + (s["fixed_fee"] if s["ebay_fee_pct"] or s["fixed_fee"] else 0)
    keep = market_aud - fee - s["postage"]
    out = {"market": market_aud, "fee": round(fee, 2), "postage": s["postage"], "keep": round(keep, 2),
           "break_even": round(keep, 2)}
    if buy is not None:
        out["buy"] = buy
        out["profit"] = round(keep - buy, 2)
        out["pct"] = round((keep - buy) / buy * 100, 1) if buy > 0 else None
    return out


def _money(x):
    return f"${abs(x):,.2f}"


def costs_text(s):
    fee = (f"{s['ebay_fee_pct']:g}% eBay fee" + (f" + {_money(s['fixed_fee'])}" if s["fixed_fee"] else "")
           if s["ebay_fee_pct"] or s["fixed_fee"] else "no eBay fee")
    return f"{fee}, {_money(s['postage'])} postage"


def alert_field(cfg, name, price, store=None, now=None):
    """The "Market" field for a booster-box alert, or None when there's nothing sound to say."""
    s = settings(cfg)
    if not s:
        return None
    store = load_store() if store is None else store
    if not fresh(store, now):
        return None
    m = listing_market(store, name)
    if not m:
        return None
    value = f"US market ≈ A{_money(m['aud'])} ([TCGplayer]({m['url']}), US{_money(m['usd'])})"
    buy = _num(price)
    if buy and buy > 0:
        e = estimate(m["aud"], buy, s)
        sign = "+" if e["profit"] >= 0 else "−"
        value += (f"\nResold at that: {sign}A{_money(e['profit'])}"
                  + (f" ({e['pct']:+.0f}%)" if e["pct"] is not None else "")
                  + f" after {costs_text(s)}. Estimate: AU prices can differ.")
    return {"name": "Market", "value": value[:1000], "inline": False}


def report(cfg, ref, buy=None, store=None, now=None):
    """For /flip: (title, lines). ref is a set code or a TCGplayer product number."""
    s = settings(cfg) or dict(DEFAULTS)
    store = load_store() if store is None else store
    if not store:
        return "No price data yet", ["The bot hasn't got TCGplayer prices yet (the cloud copy syncs them once a day)."]
    m = lookup(store, ref)
    if not m:
        return f"No market price for “{str(ref)[:60]}”", [
            "Give a set code for its English booster box (`OP-18`, `EB-05`, `PRB-02`), or the number from a "
            "product's tcgplayer.com link (`/tcgp` shows the link)."]
    age = (now or time.time()) - float(store.get("synced") or 0)
    e = estimate(m["aud"], _num(buy), s)
    lines = [f"**US market:** A{_money(m['aud'])} (US{_money(m['usd'])} at {rate(store):.3f}) · [TCGplayer]({m['url']})",
             f"**Your selling costs:** {costs_text(s)} = A{_money(e['fee'] + e['postage'])}",
             f"**You'd keep:** A{_money(e['keep'])} if it sold at the market price",
             f"**Break-even buy price:** A{_money(e['break_even'])}"]
    if "profit" in e:
        sign = "+" if e["profit"] >= 0 else "−"
        lines.insert(3, f"**Buying at A{_money(e['buy'])}:** {sign}A{_money(e['profit'])}"
                        + (f" ({e['pct']:+.0f}%)" if e["pct"] is not None else ""))
    lines.append("This is the US price converted, not an Australian sold price, and it says nothing about how long "
                 "it takes to sell. Check eBay's sold listings before buying to resell.")
    if age > 2 * 86400:
        lines.append(f"⚠️ These prices are {int(age // 86400)} days old.")
    return f"{m['name']} ({m['code']})" if m["code"] else m["name"], lines
