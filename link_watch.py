#!/usr/bin/env python3
"""
Link watch for the One Piece restock bot (/watch in Discord)
============================================================

Paste any product page with /watch add and the bot checks it on every run (every 5 minutes on the PC).
When it's buyable (in stock or pre-order open) at or under your max, it alerts once. If it sells out
and comes back, it alerts again. Leave the max out to hear about it at any price.

How a page is read (the bot only reads pages - it never buys, bids or logs in):
  1. Shopify shops (most Australian TCG stores): the product's own data at /products/<handle>.js -
     every variant's price and whether it can be bought, plus a one-click cart link.
  2. Anything else (WooCommerce, BigCommerce, big retailers): the product details shops put in the page
     for Google (schema.org "Product" in JSON-LD), then the price/stock meta tags as a last resort.
A page that blocks bots in its robots.txt isn't read, the same as every other shop the bot checks.

The list lives in watches.json next to the bot (the PC copy). /watch add, list and remove change it;
editing it by hand works too:
  {"items": [{"id": "a1b2c3d4", "url": "https://...", "name": "OP-15 booster box", "max": 160}]}

Try it any time (prints what each watched page says now; posts nothing, saves nothing):
    py -3 link_watch.py
    py -3 link_watch.py https://some-shop.com.au/products/something
"""
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
WATCH_PATH = os.path.join(HERE, "watches.json")
MAX_WATCHES = 25
WORKERS = 6
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")

BUYABLE = {"instock", "preorder", "presale", "backorder", "limitedavailability", "onlineonly", "instoreonly"}
NOT_BUYABLE = {"outofstock", "soldout", "discontinued", "oos", "out of stock"}
STATUS_WORD = {"instock": "in stock", "preorder": "pre-order open", "presale": "pre-order open",
               "backorder": "back-order", "limitedavailability": "low stock", "onlineonly": "in stock (online)",
               "instoreonly": "in store only", "outofstock": "sold out", "soldout": "sold out",
               "discontinued": "discontinued", "oos": "sold out"}

_lock = threading.Lock()


# ---------------------------------------------------------------- the list
def _read(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {"items": []}
    except (OSError, ValueError) as e:
        print(f"   ! {os.path.basename(path)} couldn't be read ({e}); link watch skipped")
        return None
    return data if isinstance(data, dict) else {"items": []}


def _num(x):
    if isinstance(x, bool) or x is None:
        return None
    try:
        return float(str(x).strip().replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def load(path=None):
    """The watched links (switched-off ones left out). [] if there's no watches.json yet."""
    data = _read(path or WATCH_PATH) or {"items": []}
    out = []
    for it in data.get("items") or []:
        if not isinstance(it, dict) or it.get("enabled", True) is False:
            continue
        url = str(it.get("url") or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            continue
        mx = _num(it.get("max"))
        q = _num(it.get("qty"))
        out.append({"id": str(it.get("id") or link_id(url)), "url": url, "name": str(it.get("name") or ""),
                    "max": mx if mx and mx > 0 else None, "by": str(it.get("by") or ""),
                    "added": it.get("added"), "qty": max(1, min(10, int(q))) if q else 1})
    return out


def _write(data, path):
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".watches.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def clean_url(url):
    """Drop tracking bits (utm_..., fbclid) and #anchors; keep ?variant= so a chosen variant is watched."""
    u = urllib.parse.urlsplit(url.strip())
    keep = [(k, v) for k, v in urllib.parse.parse_qsl(u.query) if k.lower() in ("variant", "id", "sku", "p")]
    return urllib.parse.urlunsplit((u.scheme.lower(), u.netloc.lower(), u.path, urllib.parse.urlencode(keep), ""))


def link_id(url):
    return hashlib.sha1(clean_url(url).encode("utf-8")).hexdigest()[:8]


def add(url, max_price=None, name="", by="", path=None, qty=None):
    """Add a link (or update its max/name if it's already watched). Returns (item, "added"|"updated").
    Raises ValueError with a plain-English reason."""
    path = path or WATCH_PATH
    url = url.strip().strip("<>")
    if not re.match(r"https?://[^/\s]+\.[^/\s]+", url, re.I):
        raise ValueError("That doesn't look like a web link. Paste the whole product page address, "
                         "starting with https://")
    url = clean_url(url)
    mx = _num(max_price)
    if mx is not None and mx < 0:
        raise ValueError("The max can't be below $0.")
    with _lock:
        data = _read(path)
        if data is None:
            raise ValueError("watches.json couldn't be read, so nothing was changed. Fix or delete it first.")
        items = data.setdefault("items", [])
        wid = link_id(url)
        for it in items:
            if it.get("id") == wid or clean_url(str(it.get("url", ""))) == url:
                it.update({"max": mx if mx else None, "enabled": True})
                if name:
                    it["name"] = name
                if qty:
                    it["qty"] = max(1, min(10, int(qty)))
                _write(data, path)
                return dict(it), "updated"
        if sum(1 for it in items if it.get("enabled", True) is not False) >= MAX_WATCHES:
            raise ValueError(f"You're already watching {MAX_WATCHES} links. Remove one first (/watch remove).")
        it = {"id": wid, "url": url, "name": name, "max": mx if mx else None, "by": by,
              "added": time.strftime("%Y-%m-%d"), "enabled": True}
        if qty and int(qty) > 1:
            it["qty"] = max(1, min(10, int(qty)))
        items.append(it)
        _write(data, path)
        return dict(it), "added"


def set_name(wid, name, path=None):
    """Fill in a name the bot read from the page (only if none was given)."""
    path = path or WATCH_PATH
    with _lock:
        data = _read(path)
        if not data:
            return
        for it in data.get("items") or []:
            if it.get("id") == wid and not it.get("name"):
                it["name"] = name[:120]
                _write(data, path)
                return


def remove(key, path=None):
    """Stop watching a link, by id, link or (part of) its name. Returns the removed item or None."""
    path = path or WATCH_PATH
    key = str(key or "").strip()
    with _lock:
        data = _read(path)
        if not data:
            return None
        items = data.get("items") or []
        kl = key.lower()
        hit = next((it for it in items if it.get("id") == key), None)
        if hit is None and kl.startswith("http"):
            hit = next((it for it in items if clean_url(str(it.get("url", ""))) == clean_url(key)), None)
        if hit is None:
            hits = [it for it in items if kl and kl in str(it.get("name", "")).lower()]
            hit = hits[0] if len(hits) == 1 else None
        if hit is None:
            return None
        items.remove(hit)
        _write(data, path)
        return hit


# ---------------------------------------------------------------- reading a product page
def _reading(**kw):
    r = {"ok": False, "title": "", "price": None, "currency": "", "buyable": False, "status": "",
         "cart": "", "problem": "", "how": ""}
    r.update(kw)
    return r


def shopify_js_url(url):
    u = urllib.parse.urlsplit(url)
    m = re.search(r"/products/([^/?#]+)", u.path)
    if not m:
        return None
    return f"{u.scheme}://{u.netloc}/products/{m.group(1)}.js"


def parse_shopify(data, url):
    """A Shopify /products/<handle>.js reply -> reading. Prices there are in cents."""
    if not isinstance(data, dict) or not isinstance(data.get("variants"), list) or not data["variants"]:
        return None
    u = urllib.parse.urlsplit(url)
    want = dict(urllib.parse.parse_qsl(u.query)).get("variant")
    variants = [v for v in data["variants"] if isinstance(v, dict)]
    if want:
        chosen = [v for v in variants if str(v.get("id")) == str(want)]
        variants = chosen or variants

    def cents(v):
        p = _num(v.get("price"))
        return None if p is None else p / 100.0

    priced = [v for v in variants if cents(v) is not None]
    if not priced:
        return None
    live = [v for v in priced if v.get("available")]
    pick = min(live or priced, key=cents)
    title = str(data.get("title") or "")
    vt = str(pick.get("title") or "")
    if len(priced) > 1 and vt and vt.lower() not in ("default title", "default"):
        title += f" ({vt})"
    base = f"{u.scheme}://{u.netloc}"
    return _reading(ok=True, title=html.unescape(title), price=round(cents(pick), 2), currency="",
                    buyable=bool(live), status="in stock" if live else "sold out",
                    cart=f"{base}/cart/{pick['id']}:1" if live and pick.get("id") else "", how="shopify")


_LD = re.compile(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S | re.I)


def _ld_nodes(obj):
    """Every dict in a JSON-LD blob (walks @graph, lists, hasVariant, offers...)."""
    stack = [obj]
    while stack:
        o = stack.pop()
        if isinstance(o, list):
            stack.extend(o)
        elif isinstance(o, dict):
            yield o
            for k in ("@graph", "hasVariant", "mainEntity", "itemListElement", "item"):
                if k in o:
                    stack.append(o[k])


def _types(node):
    t = node.get("@type")
    return {str(x).lower() for x in (t if isinstance(t, list) else [t]) if x}


def _avail(v):
    s = str(v or "").strip().rsplit("/", 1)[-1].lower().replace("_", "").replace(" ", "")
    return s


def _offers(node):
    off = node.get("offers")
    out = []
    for o in (off if isinstance(off, list) else [off]):
        if not isinstance(o, dict):
            continue
        if "offers" in o and isinstance(o["offers"], (list, dict)):      # AggregateOffer with offers inside
            out += _offers(o)
        price = _num(o.get("price"))
        if price is None:
            spec = o.get("priceSpecification")
            spec = spec[0] if isinstance(spec, list) and spec else spec
            if isinstance(spec, dict):
                price = _num(spec.get("price"))
        if price is None:
            price = _num(o.get("lowPrice"))
        if price is not None:
            out.append({"price": price, "currency": str(o.get("priceCurrency") or ""),
                        "avail": _avail(o.get("availability"))})
    return out


def _meta(page, *names):
    for n in names:
        m = re.search(r"<meta[^>]+(?:property|name|itemprop)=[\"']" + re.escape(n) + r"[\"'][^>]*>", page, re.I)
        if m:
            c = re.search(r"content=[\"']([^\"']*)[\"']", m.group(0), re.I)
            if c:
                return html.unescape(c.group(1)).strip()
    return ""


def parse_html(page):
    """A product page's HTML -> reading, from schema.org JSON-LD, else price/stock meta tags."""
    best = None
    for raw in _LD.findall(page or ""):
        raw = raw.strip()
        try:
            blob = json.loads(raw)
        except ValueError:
            try:
                blob = json.loads(html.unescape(raw))
            except ValueError:
                continue
        for node in _ld_nodes(blob):
            if not ({"product", "productgroup", "individualproduct"} & _types(node)):
                continue
            offers = _offers(node)
            if not offers:
                continue
            live = [o for o in offers if o["avail"] in BUYABLE]
            pick = min(live or offers, key=lambda o: o["price"])
            title = html.unescape(str(node.get("name") or ""))
            cand = (bool(live), title, pick)
            if best is None or (cand[0] and not best[0]) or (cand[0] == best[0] and pick["price"] < best[2]["price"]):
                best = cand
    if best:
        live, title, pick = best
        return _reading(ok=True, title=title, price=round(pick["price"], 2), currency=pick["currency"],
                        buyable=live, status=STATUS_WORD.get(pick["avail"], "in stock" if live else
                                                             (pick["avail"] or "unknown")),
                        how="page data")
    price = _num(_meta(page, "product:price:amount", "og:price:amount", "price"))
    if price is None:
        return None
    avail = _avail(_meta(page, "product:availability", "og:availability", "availability"))
    title = _meta(page, "og:title")
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", page or "", re.S | re.I)
        title = html.unescape(m.group(1)).strip() if m else ""
    buyable = avail in BUYABLE or avail in ("instock", "in stock", "available")
    if not avail:
        return _reading(ok=True, title=title, price=price, currency=_meta(page, "product:price:currency",
                        "og:price:currency"), buyable=False, status="stock not shown", how="meta tags",
                        problem="the page shows a price but not whether it's in stock")
    return _reading(ok=True, title=title, price=price,
                    currency=_meta(page, "product:price:currency", "og:price:currency"),
                    buyable=buyable, status=STATUS_WORD.get(avail, "in stock" if buyable else avail),
                    how="meta tags")


def default_fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def _why(e):
    s = str(e) or type(e).__name__
    name = type(e).__name__
    if name == "RobotsDisallowed":
        return "the shop's robots.txt asks bots not to read this page"
    if name == "SkipHost":
        return "the shop is being skipped this check (it was failing)"
    code = getattr(e, "code", None) or getattr(e, "status", None)
    if code in (403, 401):
        return "the shop blocked the bot (HTTP %s)" % code
    if code == 404:
        return "the page wasn't found (HTTP 404) - removed, or the link is wrong"
    if code:
        return f"the shop answered with an error (HTTP {code})"
    return f"couldn't load the page ({s[:80]})"


def read(url, fetch=None):
    """What a product page says right now. Never raises; problems come back in reading["problem"]."""
    fetch = fetch or default_fetch
    js = shopify_js_url(url)
    if js:
        try:
            r = parse_shopify(json.loads(fetch(js).decode("utf-8", "replace")), url)
            if r:
                return r
        except Exception:  # noqa: BLE001  (not Shopify after all, or blocked: try the page itself)
            pass
    try:
        page = fetch(url).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return _reading(problem=_why(e))
    r = parse_html(page)
    if r:
        return r
    return _reading(problem="the page loaded, but it doesn't say a price and stock the bot can read")


# ---------------------------------------------------------------- checking the list
class Result:
    def __init__(self, finds=None, readings=None, ran=False):
        self.finds = list(finds or [])
        self.readings = dict(readings or {})       # id -> reading, for every link checked
        self.ran = ran

    def ok_ids(self):
        return {f"watch|{wid}" for wid, r in self.readings.items() if r.get("ok")}


def _money(x):
    return f"${x:,.2f}"


def shop_name(url):
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    host = re.sub(r"^(www|shop|store|tcg)\.", "", host)
    return host


def make_find(item, r):
    name = item["name"] or r["title"] or shop_name(item["url"])
    cur = f" {r['currency']}" if r.get("currency") and r["currency"].upper() != "AUD" else ""
    bits = [r["status"]]
    bits.append(f"your max {_money(item['max'])}" if item.get("max") else "any price")
    if cur:
        bits.append(f"priced in{cur}")
    note = " · ".join(b for b in bits if b)
    if r.get("title") and item["name"] and r["title"].lower() != item["name"].lower():
        note = r["title"][:200] + "\n" + note
    return {"id": f"watch|{item['id']}", "kind": "Sealed", "name": name[:200], "deck": "", "qty": 1,
            "shop": shop_name(item["url"]), "price": r["price"], "url": item["url"], "cart": r.get("cart", ""),
            "note": note[:1000], "priority": True, "link_watch": True, "cart_qty": int(item.get("qty") or 1)}


def check(cfg=None, fetch=None, path=None, items=None):
    """Read every watched link; finds = the ones buyable at or under their max. Never raises."""
    items = load(path) if items is None else items
    if not items:
        return Result()
    readings = {}

    def one(it):
        try:
            return it["id"], read(it["url"], fetch)
        except Exception as e:  # noqa: BLE001
            return it["id"], _reading(problem=f"unexpected {type(e).__name__}")
    with ThreadPoolExecutor(max_workers=min(WORKERS, len(items))) as ex:
        for wid, r in ex.map(one, items):
            readings[wid] = r
    finds = []
    for it in items:
        r = readings.get(it["id"]) or {}
        if r.get("ok") and r.get("buyable") and r.get("price") is not None:
            if it.get("max") is None or r["price"] <= it["max"] + 0.001:
                finds.append(make_find(it, r))
    bad = sum(1 for r in readings.values() if not r.get("ok"))
    print(f"   (watched links: {len(items)} checked, {len(finds)} buyable within your max"
          + (f", {bad} couldn't be read" if bad else "") + ")")
    return Result(finds, readings, ran=True)


def remember(status, res, now=None):
    """Keep each link's last reading in status.json (status["watch_last"]) so /watch list answers instantly."""
    if not res or not res.ran:
        return
    now = round(now or time.time())
    last = status.setdefault("watch_last", {})
    for wid, r in res.readings.items():
        prev = last.get(wid) or {}
        entry = {"ts": now, "ok": r.get("ok"), "buyable": r.get("buyable"), "status": r.get("status"),
                 "price": r.get("price"),
                 "title": (r.get("title") or "")[:150], "problem": r.get("problem", "")}
        entry["fails"] = 0 if r.get("ok") else int(prev.get("fails") or 0) + 1
        if not r.get("ok") and prev.get("ok"):
            entry.update(status=prev.get("status"), price=prev.get("price"), title=prev.get("title"),
                         buyable=prev.get("buyable"))
        last[wid] = entry
    for wid in list(last):
        if wid not in res.readings and len(last) > MAX_WATCHES * 2:
            last.pop(wid, None)


def describe(item, r):
    """One line for /watch list or the hand test."""
    name = item.get("name") or (r or {}).get("title") or shop_name(item["url"])
    mx = f"max {_money(item['max'])}" if item.get("max") else "any price"
    if not r:
        return f"**{name}** · {mx} · not checked yet"
    if not r.get("ok") and not r.get("price"):
        return f"**{name}** · {mx} · ⚠️ {r.get('problem') or 'not read yet'}"
    price = r.get("price")
    within = item.get("max") is None or (price is not None and price <= item["max"] + 0.001)
    icon = "✅" if r.get("buyable") else "⏳"
    if r.get("buyable") and not within:
        icon = "💸"
    p = _money(price) if price is not None else "?"
    tail = f" · ⚠️ last read failed: {r['problem']}" if not r.get("ok") and r.get("problem") else ""
    return f"{icon} **{name}** · {r.get('status') or '?'} at {p} · {mx}{tail}"


def main(argv):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    if len(argv) > 1:
        items = [{"id": link_id(a), "url": clean_url(a), "name": "", "max": None} for a in argv[1:]]
    else:
        items = load()
        if not items:
            print("Nothing watched yet. In Discord: /watch add link:<product page> max:<price>")
            return 0
    for it in items:
        r = read(it["url"])
        print(describe(it, r).replace("**", ""))
        print(f"   {it['url']}" + (f"  (read via {r['how']})" if r.get("how") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
