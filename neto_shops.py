#!/usr/bin/env python3
"""
Neto (Maropost) shops for the One Piece restock bot (v2.24)
===========================================================
Some Australian shops run on Neto, which has no product feed like Shopify's or WooCommerce's. Their pages do
carry the price and stock in the page itself (schema.org "microdata"), so the bot reads those:

  * a shop's One Piece section page: every product shown there, with its price and whether it has an
    "Add to Cart" button or is "In-store only";
  * named product pages: for boxes the shop lists but leaves out of that section while they're sold out
    (Kaika's section shows in-stock items only), so the bot sees the moment they come back.

First shop: Anime Kaika (kaika.com.au, Sydney) - English booster boxes at the A$214.99 distributor RRP.
Kaika marks some boxes "Burwood Store Only": those are reported as not buyable online, with a note, and
never alert as in stock.

Polite by design: the shop's robots.txt is honoured (it allows these pages and asks for 1 second between
requests, which the bot keeps), its search is not used (robots.txt closes it), and a human-verification
page or a "slow down" is handled by the bot's usual pauses. Nothing is logged in to or added to a cart.

config.json:  "neto_shops": false  switches this off;  "extra_shops": false  does too.
Your own Neto shop:  "neto_shops": [{"name": "...", "categories": ["https://..."], "products": ["https://..."]}]
"""
import html
import re
import time
import urllib.parse

SHOPS = [
    {"name": "Anime Kaika",
     "categories": ["https://www.kaika.com.au/trading-card-games-tcg/one-piece-card-game/"],
     # listed, but sold out so not in the section: read directly (16 Nov 2026: both A$214.99, sold out)
     "products": ["https://www.kaika.com.au/pre-order-one-piece-card-game-booster-box-tba-op-1~356329",   # OP-18
                  "https://www.kaika.com.au/one-piece-card-game-booster-box-tba-op-19"]},
]
CRAWL_DELAY = 1.0           # seconds between requests to one shop (Kaika's robots.txt: Crawl-delay: 1)
MAX_PRODUCTS = 8            # named product pages read per shop per check
MAX_CATEGORIES = 3
IN_STOCK = ("in_stock", "instock", "in stock", "preorder", "pre_order", "presale", "limitedavailability", "onlineonly")
STORE_ONLY_RE = re.compile(r"\b(in[- ]?store only|store only|pick[- ]?up only)\b", re.I)
_CARD_SPLIT = re.compile(r'<div[^>]+class="[^"]*\bthumbnail\b[^"]*"[^>]*itemtype="https?://schema\.org/Product"[^>]*>', re.I)
_PRICE_NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)")
_sleep = time.sleep


def _text(s):
    return html.unescape(re.sub(r"<[^>]+>", " ", s or "")).replace("\xa0", " ").strip()


def _price(s):
    m = _PRICE_NUM.search(_text(s))
    try:
        return float(m.group(1).replace(",", "")) if m else None
    except ValueError:
        return None


def _tag_price(chunk):
    """The price in the first itemprop="price" tag: its content="" if it has one, else its text."""
    m = re.search(r'(<[^>]*itemprop="price"[^>]*>)([^<]*)', chunk or "", re.I)
    if not m:
        return None
    c = re.search(r'content="([^"]*)"', m.group(1), re.I)
    return _price(c.group(1)) if c and _price(c.group(1)) is not None else _price(m.group(2))


def _avail_word(v):
    return str(v or "").strip().rsplit("/", 1)[-1].lower()


def shops(cfg):
    """The Neto shops to read: the built-in ones plus any in config.json "neto_shops" (same name replaces)."""
    cfg = cfg or {}
    raw = cfg.get("neto_shops", True)
    if raw is False or cfg.get("extra_shops", True) is False and not isinstance(raw, list):
        return []
    out = {s["name"]: dict(s) for s in SHOPS} if cfg.get("extra_shops", True) else {}
    for s in raw if isinstance(raw, list) else []:
        if isinstance(s, dict) and s.get("name") and (s.get("categories") or s.get("products")):
            out[str(s["name"])] = {"name": str(s["name"]),
                                   "categories": [str(u) for u in s.get("categories") or [] if str(u).startswith("https://")],
                                   "products": [str(u) for u in s.get("products") or [] if str(u).startswith("https://")]}
    return list(out.values())


def warnings(cfg):
    raw = (cfg or {}).get("neto_shops")
    if raw is None or isinstance(raw, bool):
        return []
    if not isinstance(raw, list):
        return ['"neto_shops" should be false or a list like [{"name": "...", "categories": ["https://..."]}]; ignored']
    return [f'"neto_shops" entry {i + 1} needs a "name" and "categories" or "products" (https links); skipped'
            for i, s in enumerate(raw)
            if not (isinstance(s, dict) and s.get("name") and (s.get("categories") or s.get("products")))]


def hosts(cfg=None):
    """{host: shop name} for the shop-health posts and the drop rehearsal."""
    out = {}
    for s in shops(cfg):
        for u in (s.get("categories") or []) + (s.get("products") or []):
            out.setdefault(urllib.parse.urlsplit(u).netloc, s["name"])
    return out


# ---------------------------------------------------------------- reading the pages
def parse_category(page, base=""):
    """A Neto section page -> [{"name", "url", "price", "buyable", "store_only"}], one per product shown."""
    out = []
    for card in _CARD_SPLIT.split(page or "")[1:]:
        m = re.search(r'itemprop="name"[^>]*>\s*(<a\b[^>]*>)(.*?)</a>', card, re.S | re.I)
        href = re.search(r'href="([^"]+)"', m.group(1), re.I) if m else None
        if not href:
            continue
        title = re.search(r'title="([^"]*)"', m.group(1), re.I)                  # the title="" has the full name
        name = html.unescape(title.group(1)).strip() if title and title.group(1).strip() else _text(m.group(2))
        url = urllib.parse.urljoin(base, html.unescape(href.group(1)))
        price = _tag_price(card)
        form = card.split("<!-- /Purchase Logic -->")[0]
        buttons = _text(" ".join(re.findall(r"<(?:a|button)\b[^>]*\bbtn\b[^>]*>.*?</(?:a|button)>", form, re.S | re.I)))
        store_only = bool(STORE_ONLY_RE.search(buttons))
        buyable = bool(re.search(r'class="[^"]*\baddtocart\b', form, re.I)) and not store_only
        if name and url:
            out.append({"name": name, "url": url, "price": price, "buyable": buyable, "store_only": store_only})
    return out


def parse_product(page, url=""):
    """A Neto product page -> {"name", "url", "price", "currency", "buyable", "store_only", "status"}, or None
    if the page doesn't carry a product's price and stock (so a changed layout is never read as 'sold out')."""
    page = page or ""
    main = _CARD_SPLIT.split(page)[0]                    # "related products" cards come after the product itself
    nm = re.search(r'<h1[^>]*itemprop="name"[^>]*>(.*?)</h1>', main, re.S | re.I)
    off = re.search(r'itemprop="offers"[^>]*>(.*)', main, re.S | re.I)
    if not nm or not off:
        return None
    seg = off.group(1)[:6000]
    price = _tag_price(seg)
    am = re.search(r'(<[^>]*itemprop="availability"[^>]*>)([^<]*)', seg, re.I)
    val = re.search(r'(?:content|href)="([^"]*)"', am.group(1), re.I) if am else None
    if price is None or not val:
        return None
    word = _avail_word(val.group(1))
    desc = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', page, re.I)
    store_only = bool(STORE_ONLY_RE.search(html.unescape(desc.group(1)) if desc else ""))
    cur = re.search(r'itemprop="priceCurrency"[^>]*content="([^"]*)"', seg, re.I)
    in_stock = word in IN_STOCK
    return {"name": _text(nm.group(1)), "url": url, "price": price, "currency": cur.group(1) if cur else "",
            "buyable": in_stock and not store_only, "store_only": store_only,
            "status": ("in store only" if store_only and in_stock else _text(am.group(2)).lower() or word)}


def _key(url):
    return urllib.parse.urlsplit(url).path.strip("/").lower()


def read_shop(tb, shop):
    """Every product the shop shows -> (rows, pages that answered, pages asked). Product pages win over the
    section's card for the same product (they say 'store only' and exact stock)."""
    rows, ok, asked = {}, 0, 0
    cats = (shop.get("categories") or [])[:MAX_CATEGORIES]
    prods = (shop.get("products") or [])[:MAX_PRODUCTS]
    for i, url in enumerate(cats + prods):
        if asked:
            _sleep(CRAWL_DELAY)
        asked += 1
        try:
            page = tb.HTTP.fetch(url, tries=1).decode("utf-8", "replace")
        except tb.SkipHost:
            return {}, 0, asked                           # shop is in its quiet period: leave it alone entirely
        except tb.RobotsDisallowed:
            tb._say_once(("robots", tb.short(url)), f"   ! skipped {tb.short(url)}: the shop's robots.txt asks bots not to read it")
            continue
        except Exception as e:  # noqa: BLE001
            tb._fail(url, e)
            if getattr(e, "status", None) in (403, 429):
                break                                     # told to stop: don't ask this shop for more pages now
            continue
        if i < len(cats):
            found = parse_category(page, url)
            if found or "itemtype" in page:
                ok += 1
            for r in found:
                rows.setdefault(_key(r["url"]), r)
        else:
            r = parse_product(page, url)
            if r:
                ok += 1
                rows[_key(url)] = r
            else:
                tb._say_once(("neto", url), f"   ! {shop['name']}: {tb.short(url)} loaded but shows no price and stock "
                                            f"the bot can read (the page may have moved)")
    return rows, ok, asked


def boxes(tb, shop, max_price, watch=()):
    """Same answer shape as tcg_bot.woo_boxes: (finds, listings), listings None if nothing could be read."""
    rows, ok, _ = read_shop(tb, shop)
    if not ok:
        return [], None
    name_of = shop["name"]
    finds, listings = [], []
    for key, r in rows.items():
        name = r["name"]
        if "one piece" not in name.lower():
            continue
        c = tb.classify(name, watch, max_price)
        if not c:
            continue
        kind, prefix, group, limit, w = c
        price = r["price"] or 0.0
        note = ", ".join(x for x in ((w["name"] if w else ""), ("pre-order" if tb.is_preorder(name) else ""),
                                     ("in-store only, not sold online" if r.get("store_only") else "")) if x)
        listings.append({"id": f"list|{name_of}|{key}", "box_id": f"{prefix}|{name_of}|{key}", "group": group,
                         "kind": "New listing", "name": name, "shop": name_of, "price": price,
                         "available": bool(r["buyable"]), "url": r["url"], "cart": "", "note": note, "max": limit,
                         "page": 1})
        if group == "new" or not r["buyable"] or price <= 0 or price > limit:
            continue
        finds.append({"id": f"{prefix}|{name_of}|{key}", "kind": kind, "name": name, "shop": name_of, "price": price,
                      "url": r["url"], "cart": "", "note": note})
    return finds, listings
