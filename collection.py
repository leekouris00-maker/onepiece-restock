"""
My collection: the things you own, with what they're worth now (v2.11.4)
=========================================================================

Shown on the private auto-buy page on the PC (open_autobuy.bat → "My collection" tab). Nothing here goes to
Discord or GitHub: the list lives in collection.json and the photos in collection_photos/, next to the bot,
and both are PC-only (in .gitignore; the updater never touches them).

Each item keeps:
  - what you paid (each) and the day you got it;
  - the price on the day you added it ("start"), so you can see how it's done since;
  - one price a day from then on ("hist"), from which the page shows the change over the last 7 days.

Where a price comes from (nothing extra is fetched; it reads the bot's own records):
  - a card (card number, e.g. OP05-119, plus optional words like "alternate art" to pick the version):
    the cheapest copy in stock at Elemental Arcade / Good Games (singles_prices.json), otherwise
    TCGplayer's market price in A$ (tcgplayer_prices.json, English cards only);
  - anything sealed (words to look for in shop titles, e.g. "ts-02 tin"): the cheapest copy in stock
    across every shop the bot watches (price_history.json). Displays, cases and "set of" listings only
    count when your words ask for them. Otherwise TCGplayer's sealed market price;
  - "your estimate": a price you type in. It wins over the above when set (use it for things no shop
    sells, like a Nike DON!! card).
New items start with up to a week of history from those records, so the week's change shows at once.
"""
import json
import os
import re
import secrets
import threading
import time
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "collection.json")
PHOTOS_DIR = os.path.join(HERE, "collection_photos")

KINDS = ("Tin", "Sealed", "Card", "Promo", "Collectible", "Other")
LANGS = ("EN", "JP", "Other")
STATES = ("Sealed", "Opened", "Raw", "Graded")
STATUSES = ("have", "coming")
HIST_KEEP_DAYS = 400
BACKFILL_DAYS = 8
WEEK = 7
CACHE_SECONDS = 300
PHOTO_MAX = 1_500_000
ID_RE = re.compile(r"^[0-9a-f]{8}$")
CARD_RE = re.compile(r"^(?:(?:OP|EB|ST|PRB)\d{2}|P)-\d{3}$")
BIG_LOT_WORDS = {"display", "case", "master", "displays", "cases"}
JP_WORDS = ("japanese", "jp ver", "(jp)", "[jp]", " jp ")

_lock = threading.RLock()
_cache = {"t": 0.0, "key": None, "prices": {}}


# ---------------------------------------------------------------- small helpers
def today():
    return date.today().isoformat()


def _num(x, lo=0.0, hi=1_000_000.0):
    if x is None or (isinstance(x, str) and not x.strip()):
        return None
    try:
        v = float(str(x).replace("$", "").replace(",", "").strip())
    except ValueError:
        raise ValueError(f"'{x}' isn't a number")
    if not lo <= v <= hi:
        raise ValueError(f"{v:g} is out of range")
    return round(v, 2)


def _text(x, n):
    return re.sub(r"\s+", " ", str(x or "")).strip()[:n]


def _date(x):
    x = _text(x, 10)
    if not x:
        return ""
    try:
        return date.fromisoformat(x).isoformat()
    except ValueError:
        raise ValueError(f"'{x}' isn't a date (YYYY-MM-DD)")


def tokens(s):
    return re.findall(r"[a-z0-9]+", str(s or "").lower().replace("!!", ""))


def _words_ok(name, words):
    """Every word you gave is in the title; big lots (displays, cases, set of N) only when asked for."""
    have = set(tokens(name))
    want = tokens(words)
    if not want or not all(w in have for w in want):
        return False
    if (have & BIG_LOT_WORDS) and not (set(want) & BIG_LOT_WORDS):
        return False
    if re.search(r"\bset of \d+|\(\d+ tins?\)|\[\d+ tins?\]", name.lower()) and not (set(want) & {"set", "tins"}):
        return False
    return True


def _lang_ok(name, lang):
    jp = any(w in f" {name.lower()} " for w in JP_WORDS)
    return jp if lang == "JP" else (not jp if lang == "EN" else True)


# ---------------------------------------------------------------- the list
def load(tb):
    raw = tb.read_json(PATH, None)
    items = raw.get("items", []) if isinstance(raw, dict) else []
    return [x for x in items if isinstance(x, dict) and ID_RE.match(str(x.get("id", "")))]


def save(tb, items):
    tb.atomic_write_json(PATH, {"v": 1, "items": items}, ensure_ascii=False)


def clean(d, old=None):
    """A checked copy of an item from the page's form."""
    it = dict(old or {})
    if "name" in d or not old:
        it["name"] = _text(d.get("name"), 80)
        if not it["name"]:
            raise ValueError("give it a name")
    for k, opts, dflt in (("kind", KINDS, "Other"), ("lang", LANGS, "EN"), ("state", STATES, "Sealed"),
                          ("status", STATUSES, "have")):
        if k in d or not old:
            v = str(d.get(k) or dflt)
            if v not in opts:
                raise ValueError(f"{k} must be one of {', '.join(opts)}")
            it[k] = v
    if "qty" in d or not old:
        q = _num(d.get("qty") or 1, 1, 999)
        it["qty"] = int(q)
    for k in ("paid", "value"):
        if k in d or not old:
            it[k] = _num(d.get(k))
    if "card" in d or not old:
        c = _text(d.get("card"), 12).upper().replace(" ", "")
        c = re.sub(r"^((?:OP|EB|ST|PRB)\d{2}|P)(\d{3})$", r"\1-\2", c)
        if c and not CARD_RE.match(c):
            raise ValueError(f"'{c}' isn't a card number like OP05-119")
        it["card"] = c
    for k, n in (("match", 80), ("grade", 20), ("notes", 300)):
        if k in d or not old:
            it[k] = _text(d.get(k), n)
    if "got" in d or not old:
        it["got"] = _date(d.get("got")) or (old or {}).get("got") or today()
    return it


def upsert(tb, d, cfg=None):
    """Add an item (no id) or change one. Returns the item."""
    with _lock:
        items = load(tb)
        iid = str(d.get("id") or "")
        old = next((x for x in items if x["id"] == iid), None) if iid else None
        if iid and not old:
            raise ValueError("that item isn't in the collection any more")
        it = clean(d, old)
        if old:
            items[items.index(old)] = it
        else:
            it.update(id=secrets.token_hex(4), added=today(), hist={}, start=None, photo=False)
            items.append(it)
        price_changed = not old or any(old.get(k) != it.get(k) for k in ("card", "match", "lang", "value"))
        if price_changed:
            _cache["t"] = 0
            if old and any(old.get(k) != it.get(k) for k in ("card", "match", "lang")):
                it["hist"] = {}           # a different thing is being priced: start its record again
                it["start"] = None
            q = quote(tb, it, cfg)
            record(it, q, backfill=True)
        save(tb, items)
        return it


def remove(tb, iid):
    with _lock:
        items = load(tb)
        left = [x for x in items if x["id"] != iid]
        if len(left) == len(items):
            raise ValueError("that item isn't in the collection any more")
        save(tb, left)
        try:
            os.remove(photo_path(iid))
        except OSError:
            pass


def photo_path(iid):
    if not ID_RE.match(str(iid)):
        raise ValueError("bad item id")
    return os.path.join(PHOTOS_DIR, f"{iid}.jpg")


def set_photo(tb, iid, data_url):
    m = re.match(r"^data:image/jpeg;base64,([A-Za-z0-9+/=]+)$", str(data_url or ""))
    if not m:
        raise ValueError("expected a JPEG picture")
    import base64
    raw = base64.b64decode(m.group(1))
    if len(raw) > PHOTO_MAX or not raw.startswith(b"\xff\xd8"):
        raise ValueError("that picture is too big or isn't a JPEG")
    with _lock:
        items = load(tb)
        it = next((x for x in items if x["id"] == iid), None)
        if not it:
            raise ValueError("that item isn't in the collection any more")
        os.makedirs(PHOTOS_DIR, exist_ok=True)
        tb.atomic_write_bytes(photo_path(iid), raw)
        it["photo"] = int(time.time())
        save(tb, items)
        return it


# ---------------------------------------------------------------- prices
def _days(n, end=None):
    end = end or date.today()
    return [(end - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def _sealed_shops(tb, it):
    """Shops (price_history.json): per day, the cheapest listing in stock (else the cheapest listed)."""
    words = it.get("match") or ""
    if not words:
        return None
    hist = tb.read_json(tb.HISTORY_PATH, {}) or {}
    rows = [v for v in hist.values() if isinstance(v, dict) and v.get("points")
            and _words_ok(str(v.get("name") or ""), words) and _lang_ok(str(v.get("name") or ""), it.get("lang"))]
    if not rows:
        return None
    days = _days(BACKFILL_DAYS)
    series = {}
    for d in days:
        stock, listed = [], []
        for v in rows:
            pt = None
            for p in v["points"]:
                if str(p[0]) <= d:
                    pt = p
            if pt and pt[1] and str(pt[0]) >= (date.fromisoformat(d) - timedelta(days=3)).isoformat():
                (stock if pt[2] else listed).append((float(pt[1]), v))
        pick = min(stock or listed, key=lambda x: x[0], default=None)
        if pick:
            series[d] = (pick[0], bool(stock), pick[1])
    if not series:
        return None
    last = series[max(series)]
    n_stock = sum(1 for v in rows if v["points"][-1][2])
    return {"price": last[0], "series": {d: v[0] for d, v in series.items()}, "url": last[2].get("url", ""),
            "where": last[2].get("shop", ""), "in_stock": last[1],
            "source": (f"cheapest in stock · {n_stock} listing{'s' if n_stock != 1 else ''}" if last[1]
                       else "sold out everywhere · last listed")}


def _singles(tb, it):
    """Shop singles (singles_prices.json): the cheapest copy in stock of that card number (and version words)."""
    num = it.get("card")
    if not num:
        return None
    store = tb.read_json(tb.DROPS_PATH, {}) or {}
    rows = []
    for key, v in (store.get("items") or {}).items():
        name = str(v.get("n") or "")
        if num not in name.upper() or not v.get("p") or v.get("gone"):
            continue
        if it.get("match") and not _words_ok(name, it["match"]):
            continue
        if not _lang_ok(name, it.get("lang")) or re.search(r"damaged|played|proxy", name, re.I):
            continue
        rows.append((key, v))
    if not rows:
        return None
    series = {}
    for d in _days(BACKFILL_DAYS):
        end = datetime.fromisoformat(d).timestamp() + 86400
        best = None
        for key, v in rows:
            pt = None
            for p in v["p"]:
                if p[0] <= end:
                    pt = p
            if pt and pt[2] and pt[1] and (best is None or pt[1] < best[0]):
                best = (float(pt[1]), key)
        if best:
            series[d] = best
    if not series or max(series) < _days(2)[0]:
        return None                       # not in stock lately: TCGplayer is a better guide
    last = series[max(series)]
    shop, _, handle = last[1].partition("|")
    base = ((store.get("shops") or {}).get(shop) or {}).get("base", "")
    return {"price": last[0], "series": {d: v[0] for d, v in series.items()}, "where": shop, "in_stock": True,
            "url": f"{base}/products/{handle}" if base else "", "source": "cheapest copy in stock"}


def _tcgplayer(tb, it, cfg):
    """TCGplayer market price in A$ (English only): the card number's version (words), or a sealed product."""
    if it.get("lang") == "JP":
        return None
    try:
        import tcgplayer as tp
        store = tp.load_for(cfg)
    except Exception:  # noqa: BLE001
        return None
    items = (store or {}).get("items") or {}
    if not items:
        return None
    if it.get("card"):
        keys = [k for k in tp.index(store).get(it["card"], []) if items[k].get("m") is not None]
        if it.get("match"):
            keys = [k for k in keys if _words_ok(f"{items[k].get('n', '')} {' '.join(tp.tcg_version(items[k].get('n')))}",
                                                 it["match"])] or []
        else:
            keys = [k for k in keys if not tp.tcg_version(items[k].get("n"))] or keys
    elif it.get("match"):
        keys = [k for k, v in items.items() if v.get("t") == "sealed" and v.get("m") is not None
                and _words_ok(str(v.get("n") or ""), it["match"])]
    else:
        return None
    if not keys:
        return None
    k = min(keys, key=lambda k: items[k]["m"])
    rate = tp.rate(store)
    h = items[k].get("h") or []
    series = {}
    for d in _days(BACKFILL_DAYS):
        o = date.fromisoformat(d).toordinal()
        v = None
        for p in h:
            if p[0] <= o:
                v = p[1]
        if v is not None:
            series[d] = round(v * rate, 2)
    now = round(items[k]["m"] * rate, 2)
    series[today()] = now
    return {"price": now, "series": series, "where": "TCGplayer", "in_stock": None,
            "url": f"https://www.tcgplayer.com/product/{k}", "source": f"TCGplayer market (US${items[k]['m']:.2f})"}


def quote(tb, it, cfg=None):
    """{price, source, where, url, series} for an item right now, or None if nothing prices it."""
    if it.get("value") is not None:
        return {"price": it["value"], "source": "your estimate", "where": "", "url": "", "series": {}, "mine": True}
    for fn in (_singles, _sealed_shops) if it.get("card") else (_sealed_shops,):
        try:
            q = fn(tb, it)
        except Exception:  # noqa: BLE001
            q = None
        if q:
            return q
    try:
        return _tcgplayer(tb, it, cfg)
    except Exception:  # noqa: BLE001
        return None


def record(it, q, backfill=False):
    """Put today's price in the item's daily record (and, for a new item, the days before from the series)."""
    if not q or q.get("price") is None:
        return False
    h = it.setdefault("hist", {})
    before = dict(h)
    if backfill:
        for d, v in (q.get("series") or {}).items():
            h.setdefault(d, v)
    h[today()] = q["price"]
    cut = (date.today() - timedelta(days=HIST_KEEP_DAYS)).isoformat()
    for d in [d for d in h if d < cut]:
        del h[d]
    it["hist"] = dict(sorted(h.items()))
    if not it.get("start"):
        got = it.get("got") or today()
        at = max((d for d in it["hist"] if d <= got), default=None) or min(it["hist"])
        it["start"] = {"date": at, "price": it["hist"][at]}
    return it["hist"] != before


def week_change(hist, now=None):
    """(old price, change %, label) over the last 7 days; with less than a week's record, since its first day."""
    if not hist:
        return None
    days = sorted(hist)
    last = days[-1]
    ref_day = (date.fromisoformat(last) - timedelta(days=WEEK)).isoformat()
    older = [d for d in days if d <= ref_day]
    base_day = older[-1] if older else days[0]
    if base_day == last:
        return None
    old, new = hist[base_day], hist[last]
    if not old:
        return None
    label = "7 days" if older else "since " + date.fromisoformat(base_day).strftime("%a %d %b").replace(" 0", " ")
    return {"from": old, "pct": round((new - old) / old * 100, 1), "label": label, "day": base_day}


def refresh(tb, cfg=None, force=False):
    """Price every item and keep today's point (at most every few minutes). Returns {id: quote}."""
    with _lock:
        if not force and time.time() - _cache["t"] < CACHE_SECONDS:
            return _cache["prices"]
        items = load(tb)
        prices, changed = {}, False
        for it in items:
            q = quote(tb, it, cfg)
            prices[it["id"]] = q
            changed |= record(it, q, backfill=not it.get("hist"))
        if changed:
            save(tb, items)
        _cache.update(t=time.time(), prices=prices)
        return prices


def snapshot(tb, cfg=None):
    """Everything the collection tab shows."""
    prices = refresh(tb, cfg)
    with _lock:
        items = load(tb)
    out, paid_t, worth_t, gain_t, wk_now, wk_then, n = [], 0.0, 0.0, 0.0, 0.0, 0.0, 0
    for it in items:
        q = prices.get(it["id"])
        h = it.get("hist") or {}
        now = q["price"] if q else (h[max(h)] if h else None)
        wk = week_change(h)
        qty = it.get("qty") or 1
        row = {k: it.get(k) for k in ("id", "name", "kind", "lang", "state", "grade", "qty", "paid", "value",
                                       "card", "match", "got", "status", "notes", "photo", "added", "start")}
        row.update(now=now, week=wk, spark=[[d, h[d]] for d in sorted(h)[-30:]],
                   source=(q or {}).get("source", "no price found yet" if not it.get("value") else ""),
                   where=(q or {}).get("where", ""), url=(q or {}).get("url", ""), in_stock=(q or {}).get("in_stock"))
        out.append(row)
        n += qty
        if it.get("paid") is not None:
            paid_t += it["paid"] * qty
        worth = now if now is not None else it.get("paid")
        if worth is not None:
            worth_t += worth * qty
        if now is not None and it.get("paid") is not None:
            gain_t += (now - it["paid"]) * qty
        if wk:
            wk_now += now * qty
            wk_then += wk["from"] * qty
    totals = {"items": n, "paid": round(paid_t, 2), "worth": round(worth_t, 2), "gain": round(gain_t, 2),
              "week_pct": round((wk_now - wk_then) / wk_then * 100, 1) if wk_then else None,
              "priced": sum(1 for r in out if r["now"] is not None),
              "no_cost": sum(1 for r in out if r["paid"] is None)}
    return {"items": out, "totals": totals, "kinds": KINDS, "langs": LANGS, "states": STATES, "today": today()}


def keep_ticking(tb, cfg_fn, every=3600):
    """Background thread (PC copy): keep each item's daily price even when the page isn't open."""
    def run():
        time.sleep(30)
        while True:
            try:
                refresh(tb, cfg_fn(), force=True)
            except Exception as e:  # noqa: BLE001
                print(f"   ! collection prices: {type(e).__name__}: {str(e)[:120]}")
            time.sleep(every)
    t = threading.Thread(target=run, name="collection prices", daemon=True)
    t.start()
    return t
