#!/usr/bin/env python3
"""
Chain retailers for the One Piece restock bot (v2.14)
=====================================================

JB HI-FI. JB's website is a Shopify shop, but its One Piece section and its search can't be read like
the other shops' (the section feeds come back empty, and its robots.txt asks bots to stay out of
search). So the bot finds JB's One Piece card products two other ways, and then reads each one's own
stock file:

  * NEW PRODUCTS - JB's product feed lists the newest products first (about 250 every 8 hours). The bot
    reads the first page and picks out anything with "one piece" in it. These alert as new listings.
  * OLDER PRODUCTS - JB's sitemap lists every product it sells (110 files). The bot reads two files each
    round, newest first, until it has been through them all (about 9 hours), then keeps going round.
    What it finds this way is remembered quietly: it only alerts when it's buyable within your max.
  * STOCK - for each One Piece card product: /products/<handle>.js (price and in stock or not, per
    seller: JB sells some lines itself and lists others for marketplace sellers such as SuperGamers).

Only titles that say "card game", "TCG" or "trading card" count, so One Piece Blu-rays, manga and
figures are left out. Everything then goes through the same rules as every other shop (booster boxes
at or under your max, your sealed watch list, new sealed listings, English only).

How often: every 10 minutes, and every 2 minutes inside a drop window. Between those the bot reuses
what it read last, so nothing alerts twice and nothing "sells out" just because it wasn't re-read.
If JB can't be read, the last reading is kept for up to 3 hours.

Settings (config.json, optional): "chain_shops": false switches this off. "pause_shops" works for
"JB Hi-Fi" like any other shop. What it has found is kept in chain_state.json.

Not here yet: Toymate (answered 429/403 to the bot from GitHub's computers on 10 Nov 2026), Kmart,
Target and Big W (their pages show price but not stock), EB Games.
"""
import html
import json
import os
import re
import time

JB_NAME = "JB Hi-Fi"
JB_BASE = "https://www.jbhifi.com.au"
JB_FEED = JB_BASE + "/products.json?limit=250"
JB_SITEMAP = JB_BASE + "/sitemap.xml"
# known One Piece card products, so the first reading has something (found 10 Nov 2026)
JB_SEEDS = ["one-piece-card-game-extra-booster-display-heroines-edition-box-24-pack-eb-03"]

STATE_NAME = "chain_state.json"
REFRESH = 10 * 60               # read JB again this often...
FAST_REFRESH = 100              # ...or this often when the release-code sweep runs (every 2 min in a drop window)
STALE = 3 * 3600                # JB can't be read: keep the last reading this long
MAX_LIVE = 60                   # most products to read stock for in one round
MAX_NEW = 25                    # most never-seen-before products to look at in one round
BACKFILL_FILES = 2              # sitemap files read per round
GONE_AFTER = 3                  # a product that answers "not found" this many rounds running is dropped

TCG_RE = re.compile(r"card game|\btcg\b|trading card", re.I)
ONE_PIECE_RE = re.compile(r"one[\s-]*piece", re.I)
LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
PRODUCT_LOC_RE = re.compile(r"/products/([a-z0-9][a-z0-9\-_.]*)$", re.I)
SITEMAP_NO_RE = re.compile(r"sitemap_products_(\d+)\.xml")
NO_SELLER = {"", "default title", "default", "jb hi-fi", "jb hifi"}


def enabled(cfg, tb):
    if (cfg or {}).get("chain_shops", True) is False:
        return False
    return JB_NAME not in tb.paused_shops(cfg)


def hosts():
    """{host: shop name} for the shop-health posts."""
    return {"www.jbhifi.com.au": JB_NAME}


def state_path(tb):
    return os.path.join(tb.HERE, STATE_NAME)


def load_state(tb):
    st = tb.read_json(state_path(tb), {})
    return st if isinstance(st, dict) else {}


def save_state(tb, st):
    try:
        tb.atomic_write_json(state_path(tb), st, sort_keys=True)
    except OSError as e:
        print(f"   ! couldn't save {STATE_NAME} ({e})")


def _text(tb, url):
    """A page's text, or None if it couldn't be read (says why once, like the other shops)."""
    try:
        return tb.HTTP.fetch(url).decode("utf-8", "replace")
    except tb.SkipHost:
        return None
    except tb.RobotsDisallowed:
        tb._say_once(("robots", tb.short(url)), f"   ! skipped {tb.short(url)}: the shop's robots.txt asks bots not to read it")
        return None
    except Exception as e:  # noqa: BLE001
        tb._fail(url, e)
        return None


def _product(tb, handle):
    """("ok", product) / ("gone", None) when JB says it doesn't exist / ("fail", None)."""
    url = f"{JB_BASE}/products/{handle}.js"
    try:
        raw = tb.HTTP.fetch(url)
    except tb.HttpError as e:
        if e.status in (404, 410):
            return "gone", None
        tb._fail(url, e)
        return "fail", None
    except (tb.SkipHost, tb.RobotsDisallowed):
        return "fail", None
    except Exception as e:  # noqa: BLE001
        tb._fail(url, e)
        return "fail", None
    try:
        p = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return "fail", None
    return ("ok", p) if isinstance(p, dict) and p.get("title") else ("fail", None)


def handles_in_sitemap(text):
    """One Piece product handles in a Shopify product sitemap."""
    out = []
    for loc in LOC_RE.findall(text or ""):
        m = PRODUCT_LOC_RE.search(html.unescape(loc).split("?", 1)[0])
        if m and ONE_PIECE_RE.search(m.group(1)):
            out.append(m.group(1))
    return out


def product_sitemaps(index_text):
    """Product sitemap addresses from the sitemap index, newest (highest number) first."""
    found = {}
    for loc in LOC_RE.findall(index_text or ""):
        url = html.unescape(loc)
        m = SITEMAP_NO_RE.search(url)
        if m:
            found[int(m.group(1))] = url
    return [found[n] for n in sorted(found, reverse=True)]


def _discover(tb, st, handles, first, now):
    """Add One Piece products the bot hasn't seen: the newest from the feed (these alert as new listings,
    except on the very first reading) and older ones from the sitemap (remembered quietly). True if the
    feed answered."""
    tb.HTTP.gzip_urls.add(JB_FEED.split("?", 1)[0])
    feed = tb.fetch_json(JB_FEED)
    feed_ok = isinstance(feed, dict)
    for p in (feed.get("products") or []) if feed_ok else []:
        h = str(p.get("handle") or "")
        if h and h not in handles and (ONE_PIECE_RE.search(h) or ONE_PIECE_RE.search(str(p.get("title") or ""))):
            handles[h] = {"q": 1} if first else {}
    if now - float(st.get("bf_ts") or 0) < REFRESH - 30:
        return feed_ok
    index = _text(tb, JB_SITEMAP)
    files = product_sitemaps(index) if index else []
    if not files:
        return feed_ok
    st["bf_ts"] = round(now)
    cursor = int(st.get("cursor") or 0)
    for _ in range(min(BACKFILL_FILES, len(files))):
        url = files[cursor % len(files)]
        tb.HTTP.gzip_urls.add(url.split("?", 1)[0])
        text = _text(tb, url)
        if text is None:
            break                                   # try this file again next round
        for h in handles_in_sitemap(text):
            handles.setdefault(h, {"q": 1})
        cursor += 1
    st["cursor"] = cursor % len(files)
    st["files"] = len(files)
    return feed_ok


def _seller(p, vid):
    """The marketplace seller of the variant the price is from, or ""."""
    if not any(str(o.get("name") or "").lower() == "seller" for o in p.get("options") or [] if isinstance(o, dict)):
        return ""
    for v in p.get("variants") or []:
        if v.get("id") == vid:
            s = str(v.get("public_title") or v.get("title") or "").strip()
            return "" if s.lower() in NO_SELLER else s
    return ""


def _rows(tb, p, max_price, watch):
    """(find or None, listing or None) for one JB product, by the same rules as shopify_boxes."""
    title = str(p.get("title") or "")
    if not TCG_RE.search(title) or not ONE_PIECE_RE.search(title):
        return None, None
    variants = [v for v in p.get("variants") or [] if isinstance(v, dict)]
    c = tb.classify(title, watch, max_price, variants)
    if not c:
        return None, None
    kind, prefix, group, limit, w = c
    handle = p.get("handle")
    page = f"{JB_BASE}/products/{handle}"
    price, vid = tb.cheapest_available(variants, cents=True)
    all_prices = [float(v["price"]) / 100 for v in tb.unit_variants(variants) if v.get("price")]
    seller = _seller(p, vid) if vid else ""
    note = ", ".join(x for x in ((w["name"] if w else ""), ("pre-order" if tb.is_preorder(title, p.get("tags", "")) else ""),
                                 (f"sold by {seller} on JB Marketplace" if seller else "")) if x)
    cart = tb.shopify_cart_link(JB_BASE, vid) if vid else ""
    listing = {"id": f"list|{JB_NAME}|{handle}", "box_id": f"{prefix}|{JB_NAME}|{handle}", "group": group,
               "kind": "New listing", "name": title, "shop": JB_NAME,
               "price": price if price is not None else (min(all_prices) if all_prices else 0.0),
               "available": price is not None, "url": page, "cart": cart, "note": note, "max": limit, "page": 1}
    find = None
    if group != "new" and price is not None and price <= limit:
        find = {"id": f"{prefix}|{JB_NAME}|{handle}", "kind": kind, "name": title, "shop": JB_NAME,
                "price": price, "url": page, "cart": cart, "note": note}
    return find, listing


def _replay(cache):
    return [dict(f) for f in cache.get("finds") or []], [dict(l) for l in cache.get("listings") or []]


def jb_boxes(tb, max_price, watch, fast=False, now=None):
    """(finds, listings) for JB Hi-Fi, like shopify_boxes; listings is None if JB couldn't be read and
    there's no recent reading to fall back on."""
    now = now or time.time()
    all_st = load_state(tb)
    st = all_st.setdefault(JB_NAME, {})
    handles = st.setdefault("handles", {})
    cache = st.get("cache") if isinstance(st.get("cache"), dict) else None
    ts = float(st.get("ts") or 0)
    if cache and now - ts < (FAST_REFRESH if fast else REFRESH):
        return _replay(cache)

    first = not ts
    for h in JB_SEEDS:
        handles.setdefault(h, {"q": 1})
    feed_ok = _discover(tb, st, handles, first, now)

    live = [h for h, e in handles.items() if e.get("ok")][:MAX_LIVE]
    fresh = [h for h, e in handles.items() if "ok" not in e][:MAX_NEW]
    todo = live + fresh
    results = dict(zip(todo, tb.pmap(lambda h: _product(tb, h), todo)))

    if any(results[h][0] == "fail" for h in live) or (not feed_ok and not any(r[0] == "ok" for r in results.values())):
        save_state(tb, all_st)                       # keep what was discovered; the reading itself isn't replaced
        if cache and now - ts < STALE:
            print(f"   ! {JB_NAME} didn't answer fully; using its reading from {int((now - ts) // 60)} min ago")
            return _replay(cache)
        return [], None

    finds, listings = [], []
    for h in todo:
        state, p = results[h]
        e = handles[h]
        if state == "gone":
            e["miss"] = int(e.get("miss") or 0) + 1
            if e["miss"] >= GONE_AFTER:
                handles[h] = {"ok": False}
            continue
        if state != "ok":
            continue                                 # a never-seen product that didn't load: look again next round
        e.pop("miss", None)
        find, listing = _rows(tb, p, max_price, watch)
        if "ok" not in e:
            e["ok"] = listing is not None
            if listing is None:
                e.pop("q", None)
                continue
        if listing is None:
            continue                                 # e.g. taken off the watch list
        if e.pop("q", None):
            listing["quiet"] = True                  # found in the back catalogue: remember it, don't announce it
        listings.append(listing)
        if find:
            finds.append(find)
    st["ts"] = round(now)
    st["cache"] = {"finds": finds, "listings": [dict(l, quiet=True) for l in listings]}
    save_state(tb, all_st)
    return finds, listings
