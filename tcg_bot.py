#!/usr/bin/env python3
"""
One Piece TCG restock bot (Lee's version)
=========================================

Checks Australian shops for:
  1. English One Piece booster boxes in stock (or buyable on pre-order) at or under your max price
  2. Singles on your want list at Elemental Arcade, Mayhem Collectables and Good Games
  3. Other English sealed products on a watch list (starter decks, double packs, illustration boxes,
     premium collections...) at or under their max price - see DEFAULT_SEALED_WATCH
  4. NEW listings: a box or watched product a shop has just added, even before it's buyable

Every find comes with a one-tap "Buy" link that puts it straight into your cart at
checkout. You still press pay yourself - the bot never buys anything or logs in.

Only needs Python 3.8+ (no extra installs).

    python tcg_bot.py                 check once, show only NEW finds since last run
    python tcg_bot.py --all           check once, show everything that currently matches
    python tcg_bot.py --loop 30       keep running, check every 30 minutes
    python tcg_bot.py --sealed        only check booster boxes
    python tcg_bot.py --singles       only check singles
    python tcg_bot.py --test-discord  post a test message to your Discord channel and stop
    python tcg_bot.py --recap         post the daily recap (the GitHub copy does this every morning)

Drop-day mode (in --loop only): add "drop_windows" to config.json, e.g.
    "drop_windows": [
      {"name": "OP-18 release", "start": "2026-11-20 18:00", "end": "2026-11-20 20:00", "every_seconds": 60}
    ]
Between start and end (your computer's local time) it checks booster boxes every
"every_seconds" (30 at the fastest) instead of the normal --loop gap. Add
"sealed_only": false to a window to check singles too.

New-listing alerts are on by default. To switch them off: "new_listings": false

Status posts (no ping) go to "discord_webhook_status" if set, otherwise the boxes channel:
bot online, drop mode on/off, a shop not loading for 3 checks / loading again, config.json
typos, failed checks, and (cloud copy) the PC going quiet or coming back.

No double posts: give both copies the same private "heartbeat_topic" (in "alerts" on the PC,
the HEARTBEAT_TOPIC secret in the cloud, plus HEARTBEAT_ROLE=listen there). The PC copy says
"I'm on" through ntfy.sh every 15 minutes; the cloud copy keeps checking and remembering, but
only posts while it hasn't heard from the PC for 20 minutes.

Alert settings can also come from environment variables, which win over config.json.
The cloud copy (GitHub Actions) uses these so the webhooks stay secret:
    DISCORD_WEBHOOK, DISCORD_WEBHOOK_BOXES, DISCORD_WEBHOOK_SINGLES, DISCORD_WEBHOOK_SEALED, DISCORD_PING,
    NTFY_TOPIC, BOT_NAME (the name the Discord posts show, e.g. "One Piece Restock (cloud)"),
    HEARTBEAT_TOPIC, HEARTBEAT_ROLE
"""
import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
STATE_PATH = os.path.join(HERE, "seen.json")
KNOWN_PATH = os.path.join(HERE, "known_products.json")
STATUS_PATH = os.path.join(HERE, "status.json")
RECAP_PATH = os.path.join(HERE, "recap.json")          # yesterday's prices, for the daily recap
PICKS_PATH = os.path.join(HERE, "market_picks.json")   # optional: value picks from the market ledger
# The ledger saves its picks (and the cloud copy its recap snapshot) to the GitHub repo; the PC copy
# reads them from there. Override with "repo_raw_url" in config.json.
REPO_RAW_URL = "https://raw.githubusercontent.com/leekouris00-maker/onepiece-restock/master"
_remote_cache = {}
LOG_PATH = os.path.join(HERE, "finds.log")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

MIN_DROP_SECONDS = 30
SHOP_DOWN_AFTER = 3             # a shop that fails this many checks in a row gets a "can't reach" status post
OFFLINE_SHARE = 0.8             # if this share of shops fail in the same check, it's the bot's connection, not the shops
OFFLINE_MIN_SHOPS = 4           # ...but only judge that when at least this many shops were checked

# per-run record of which shop websites answered: host -> [ok, failed]
_host_results = {}
_host_lock = threading.Lock()

# environment variable -> key in config.json "alerts"
ENV_ALERTS = {
    "DISCORD_WEBHOOK": "discord_webhook",
    "DISCORD_WEBHOOK_BOXES": "discord_webhook_boxes",
    "DISCORD_WEBHOOK_SINGLES": "discord_webhook_singles",
    "DISCORD_WEBHOOK_SEALED": "discord_webhook_sealed",
    "DISCORD_PING": "discord_ping",
    "NTFY_TOPIC": "ntfy_topic",
    "BOT_NAME": "bot_name",
    "DISCORD_WEBHOOK_RECAP": "discord_webhook_recap",
    "LEDGER_URL": "ledger_url",
    "HEARTBEAT_TOPIC": "heartbeat_topic",
    "HEARTBEAT_ROLE": "heartbeat_role",
}

# PC and cloud copies share a private ntfy topic. The PC says "I'm on" there now and then;
# the cloud copy reads it and stays quiet while the PC is on, so finds aren't posted twice.
HEARTBEAT_EVERY = 15 * 60       # PC sends at most one "I'm on" message every 15 minutes
HEARTBEAT_FRESH = "20m"         # cloud treats the PC as on if it heard from it in the last 20 minutes
_last_heartbeat = 0.0

# Variant words that mean "not the regular print" (used unless a card overrides it)
DEFAULT_EXCLUDE = [
    "alternate art", "alt art", "parallel", "(sp)", " sp ", "manga", "wanted", "full art",
    "treasure", "pre-release", "prerelease", "release event", "japanese", "promotion",
    "championship", "store treasure", "beginners deck", "anniversary", "sp gold", "sp silver",
    "playmat", "jumbo", "signed",
]
BOX_EXCLUDE = ["japanese", "(jp)", " jp ", "asia", "asian", "chinese", "korean",
               "case", "sleeved", "single pack", "booster pack", "display case"]

BOX_KINDS = ("Booster box", "Sealed", "New listing")

# Other English sealed products to watch (besides booster boxes). Each alerts when it's buyable at or
# under "max" (AUD), and as a new listing when a shop first lists it. Override with "sealed_watch"
# in config.json - same format. "match" is any text in the shop's product title (dashes optional).
DEFAULT_SEALED_WATCH = [
    {"name": "Starter decks ST-37 / ST-38", "match": ["ST-37", "ST-38"], "max": 45},
    {"name": "Double Pack Set DP-13", "match": ["DP-13"], "max": 35},
    {"name": "Illustration Box IB-09 / IB-10", "match": ["IB-09", "IB-10", "Illustration Box"], "max": 130},
    {"name": "Heroines Gift Collection", "match": ["Gift Collection"], "max": 120},
    {"name": "Ace, Sabo & Luffy Premium Card Collection", "match": ["Ace, Sabo", "Sabo & Luffy", "Sabo and Luffy"], "max": 150},
    {"name": "29th Anniversary Premium Card Collection", "match": ["29th Anniversary"], "max": 150},
]
# English release calendar for the recap's "coming up" section. Override with "releases" in config.json.
DEFAULT_RELEASES = [
    {"date": "2026-10-30", "name": "EB-05 Heroines Edition Vol. 2"},
    {"date": "2026-10-30", "name": "TS-03 Mini Case Set Vol. 3"},
    {"date": "2026-11-20", "name": "OP-18 The Dominance of God"},
    {"date": "2026-11-20", "name": "Heroines Gift Collection"},
    {"date": "2026-11-20", "name": "DP-13 Double Pack Set Vol. 13"},
    {"date": "2026-12-04", "name": "IB-09 / IB-10 Illustration Boxes"},
    {"date": "2026-12-18", "name": "ST-37 / ST-38 Starter Decks"},
    {"date": "2027-01-29", "name": "EB-06 Extra Booster"},
    {"date": "2027-03-01", "name": "29th Anniversary Premium Card Collection (date approx.)"},
    {"date": "2027-03-05", "name": "OP-19 Booster Set"},
    {"date": "2027-04-01", "name": "Ace, Sabo & Luffy Premium Card Collection (April, approx.)"},
]
RECAP_DAYS_AHEAD = 14
RECAP_MOVE_PCT = 5      # price changes smaller than this (%) are left out of the recap

# Extra sealed shops, added on top of config.json (skip with "extra_shops": false in config.json).
# Shops with a One Piece section are read like the others; the rest are read through their search.
EXTRA_SHOPIFY_COLLECTIONS = [
    {"name": "Alpha Gaming", "url": "https://alphagaming.com.au/collections/one-piece-sealed-products/products.json?limit=250"},
]
EXTRA_SHOPIFY_SEARCH = [
    {"name": "Grailborne", "base": "https://grailborne.com.au"},
    {"name": "Collectible Madness", "base": "https://collectiblemadness.com.au"},
    {"name": "Friendly Collectibles", "base": "https://friendlycollectibles.com.au"},
]
SEARCH_QUERIES = ["one piece booster box", "one piece booster display", "one piece card game"]

WATCH_EXCLUDE = ["japanese", "(jp)", " jp ", "chinese", "korean", "asia", "simplified", "traditional"]


# ---------------------------------------------------------------- helpers
def load_config():
    """Read config.json, then let environment variables override the alert settings."""
    cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))
    alerts = cfg.setdefault("alerts", {})
    for env, k in ENV_ALERTS.items():
        val = os.environ.get(env, "").strip()
        if val:
            alerts[k] = val
    return cfg


def fetch_json(url, tries=2):
    """GET a URL and parse JSON. Returns None on failure (and prints why)."""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=25) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            _note_host(url, True)
            return data
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    print(f"   ! couldn't read {short(url)} ({last})")
    _note_host(url, False)
    return None


def _note_host(url, ok):
    host = urllib.parse.urlparse(url).netloc
    with _host_lock:
        _host_results.setdefault(host, [0, 0])[0 if ok else 1] += 1


def short(url):
    p = urllib.parse.urlparse(url)
    return p.netloc + p.path


def origin(url):
    p = urllib.parse.urlparse(url)
    return f"{p.scheme or 'https'}://{p.netloc}"


def money(x):
    return f"${x:,.2f}"


def norm(s):
    return " " + re.sub(r"\s+", " ", (s or "").lower()) + " "


def is_excluded(title, words):
    t = norm(title)
    return any(w.lower() in t for w in words)


def is_box_title(title):
    t = (title or "").lower()
    return ("booster box" in t or "booster display" in t) and not is_excluded(title, BOX_EXCLUDE)


def watch_item(title, watch):
    """The sealed_watch entry this product title matches, or None (box titles are left to the box check)."""
    if not title or is_box_title(title) or is_excluded(title, WATCH_EXCLUDE):
        return None
    t = title.lower()
    squashed = re.sub(r"[\s\-]", "", t)
    for w in watch:
        for m in w.get("match", []):
            m = m.lower()
            if m in t or re.sub(r"[\s\-]", "", m) in squashed:
                return w
    return None


def card_num_variants(num):
    """OP13-120 -> ['op13-120', 'op13120'] (Elemental sometimes drops the dash in handles)."""
    n = num.lower()
    return [n, n.replace("-", "")]


def shopify_cart_link(base, variant_id, qty=1):
    """Shopify cart permalink: opens checkout with this item already in the cart."""
    if not variant_id:
        return ""
    return f"{origin(base)}/cart/{variant_id}:{max(1, int(qty))}"


def woo_cart_link(url, product_id, qty=1):
    """WooCommerce: add to cart and jump to checkout."""
    if not product_id:
        return ""
    return f"{origin(url)}/checkout/?add-to-cart={product_id}&quantity={max(1, int(qty))}"


def cheapest_available(variants, cents):
    """(price in dollars, variant id) of the cheapest in-stock variant, or (None, None)."""
    avail = [v for v in variants or [] if v.get("available")]
    if not avail:
        return None, None
    v = min(avail, key=lambda v: float(v.get("price") or 0))
    price = float(v.get("price") or 0)
    return (price / 100 if cents else price), v.get("id")


# ---------------------------------------------------------------- sealed
def shopify_boxes(shop_name, url, max_price, watch=()):
    """Returns (finds, listings). listings is None if the shop couldn't be read.
    Covers booster boxes and the other sealed products in the watch list."""
    data = fetch_json(url)
    if not data:
        return [], None
    base = origin(url)
    finds, listings = [], []
    for p in data.get("products", []):
        title = p.get("title", "")
        w = None if is_box_title(title) else watch_item(title, watch)
        if not is_box_title(title) and not w:
            continue
        kind, prefix, group = ("Sealed", "sealed", "watch") if w else ("Booster box", "box", "box")
        limit = w["max"] if w else max_price
        handle = p.get("handle")
        page = f"{base}/products/{handle}"
        is_pre = "pre" in (json.dumps(p.get("tags", "")) + title).lower()
        variants = p.get("variants", [])
        price, vid = cheapest_available(variants, cents=False)
        all_prices = [float(v["price"]) for v in variants if v.get("price")]
        note = ", ".join(x for x in ((w["name"] if w else ""), ("pre-order" if is_pre else "")) if x)
        listings.append({
            "id": f"list|{shop_name}|{handle}", "box_id": f"{prefix}|{shop_name}|{handle}", "group": group,
            "kind": "New listing", "name": title, "shop": shop_name,
            "price": price if price is not None else (min(all_prices) if all_prices else 0.0),
            "available": price is not None, "url": page,
            "cart": shopify_cart_link(base, vid) if vid else "",
            "note": note, "max": limit,
        })
        if price is None or price > limit:
            continue
        finds.append({
            "id": f"{prefix}|{shop_name}|{handle}", "kind": kind, "name": title, "shop": shop_name,
            "price": price, "url": page, "cart": shopify_cart_link(base, vid), "note": note,
        })
    return finds, listings


def shopify_search_boxes(shop_name, base, max_price, watch=()):
    """For shops without a One Piece section: read their search results instead.
    Returns (finds, listings) like shopify_boxes; listings is None if every search failed."""
    base = base.rstrip("/")
    products, any_ok = {}, False
    for q in SEARCH_QUERIES:
        data = fetch_json(f"{base}/search/suggest.json?q={urllib.parse.quote(q)}"
                          f"&resources[type]=product&resources[limit]=10")
        if data is None:
            continue
        any_ok = True
        for p in data.get("resources", {}).get("results", {}).get("products", []):
            products.setdefault(p.get("handle"), p)
    if not any_ok:
        return [], None
    finds, listings = [], []
    for handle, p in products.items():
        title = p.get("title", "")
        if "one piece" not in title.lower():
            continue
        w = None if is_box_title(title) else watch_item(title, watch)
        if not is_box_title(title) and not w:
            continue
        kind, prefix, group = ("Sealed", "sealed", "watch") if w else ("Booster box", "box", "box")
        limit = w["max"] if w else max_price
        page = f"{base}/products/{handle}"
        available = bool(p.get("available"))
        price = float(p.get("price") or p.get("price_min") or 0)
        is_pre = "pre" in (json.dumps(p.get("tags", "")) + title).lower()
        note = ", ".join(x for x in ((w["name"] if w else ""), ("pre-order" if is_pre else "")) if x)
        cart = ""
        if available and 0 < price <= limit:      # only look up the cart ID when it's worth alerting
            js = product_js(base, handle) or {}
            _, vid = cheapest_available(js.get("variants"), cents=True)
            cart = shopify_cart_link(base, vid)
        listings.append({"id": f"list|{shop_name}|{handle}", "box_id": f"{prefix}|{shop_name}|{handle}",
                         "group": group, "kind": "New listing", "name": title, "shop": shop_name,
                         "price": price, "available": available, "url": page, "cart": cart,
                         "note": note, "max": limit})
        if available and 0 < price <= limit:
            finds.append({"id": f"{prefix}|{shop_name}|{handle}", "kind": kind, "name": title,
                          "shop": shop_name, "price": price, "url": page, "cart": cart, "note": note})
    return finds, listings


def sealed_shops(cfg):
    """(collections, single products, woocommerce, search) shop lists, with the extra shops added."""
    s = cfg["sealed"]
    cols = list(s.get("shopify_collections", []))
    search = list(s.get("shopify_search", []))
    if cfg.get("extra_shops", True):
        have = {x["name"] for x in cols + search}
        cols += [x for x in EXTRA_SHOPIFY_COLLECTIONS if x["name"] not in have]
        search += [x for x in EXTRA_SHOPIFY_SEARCH if x["name"] not in have]
    return cols, s.get("shopify_products", []), s.get("woocommerce", []), search


def shopify_product_box(shop_name, url, max_price, watch=()):
    """A single product .js URL (Shopify prices are in cents here). Not used for new-listing alerts."""
    p = fetch_json(url)
    if not p:
        return [], []
    price, vid = cheapest_available(p.get("variants", []), cents=True)
    if price is None or price > max_price:
        return [], []
    return [{"id": f"box|{shop_name}|{p.get('handle')}", "kind": "Booster box", "name": p.get("title") or p.get("handle") or "Booster box",
             "shop": shop_name, "price": price, "url": url.replace(".js", ""),
             "cart": shopify_cart_link(url, vid), "note": ""}], []


def woo_boxes(shop_name, url, max_price, watch=()):
    data = fetch_json(url)
    if not isinstance(data, list):
        return [], None
    finds, listings = [], []
    for p in data:
        name = re.sub("<[^>]+>", "", p.get("name", ""))
        if "one piece" not in name.lower():
            continue
        w = None if is_box_title(name) else watch_item(name, watch)
        if not is_box_title(name) and not w:
            continue
        kind, prefix, group = ("Sealed", "sealed", "watch") if w else ("Booster box", "box", "box")
        limit = w["max"] if w else max_price
        prices = p.get("prices", {})
        minor = int(prices.get("currency_minor_unit", 2))
        price = int(prices.get("price", 0) or 0) / (10 ** minor)
        buyable = bool(p.get("is_in_stock") and p.get("is_purchasable", True))
        link = woo_cart_link(url, p.get("id")) if buyable else ""
        note = w["name"] if w else ""
        listings.append({
            "id": f"list|{shop_name}|{p.get('id')}", "box_id": f"{prefix}|{shop_name}|{p.get('id')}",
            "group": group, "kind": "New listing", "name": name, "shop": shop_name, "price": price,
            "available": buyable, "url": p.get("permalink"), "cart": link, "note": note, "max": limit,
        })
        if not buyable or price <= 0 or price > limit:
            continue
        finds.append({"id": f"{prefix}|{shop_name}|{p.get('id')}", "kind": kind, "name": name,
                      "shop": shop_name, "price": price, "url": p.get("permalink"), "cart": link, "note": note})
    return finds, listings


def check_sealed(cfg):
    """Returns (finds, listings_by_shop). listings_by_shop[shop] is None when that shop failed."""
    mx = cfg["sealed"]["max_price"]
    watch = cfg.get("sealed_watch", DEFAULT_SEALED_WATCH) or []
    cols, prods, woo, search = sealed_shops(cfg)
    jobs = []
    for shop in cols:
        jobs.append((shopify_boxes, shop["name"], shop["url"], mx, watch))
    for shop in prods:
        jobs.append((shopify_product_box, shop["name"], shop["url"], mx, watch))
    for shop in woo:
        jobs.append((woo_boxes, shop["name"], shop["url"], mx, watch))
    for shop in search:
        jobs.append((shopify_search_boxes, shop["name"], shop["base"], mx, watch))
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda j: (j, j[0](*j[1:])), jobs))
    finds, by_shop = [], {}
    for job, (f, listings) in results:
        finds += f
        if job[0] is shopify_product_box:
            continue
        name = job[1]
        if listings is None:
            by_shop[name] = None            # failed: don't touch what we know about this shop
        elif by_shop.get(name, []) is not None:
            by_shop.setdefault(name, []).extend(listings)
    # de-dupe (same product listed twice)
    seen, out = set(), []
    for f in finds:
        if f["id"] not in seen:
            seen.add(f["id"])
            out.append(f)
    return out, by_shop


# ---------------------------------------------------------------- new listings
def load_known():
    try:
        return json.load(open(KNOWN_PATH, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save_known(known):
    json.dump(known, open(KNOWN_PATH, "w", encoding="utf-8"), indent=1, sort_keys=True)


def new_listings(by_shop, known, box_finds):
    """Listings never seen before at that shop. The first good read of a shop only remembers
    what's there (no alerts), so a fresh install doesn't flood you."""
    finds_ids = {f["id"] for f in box_finds}
    out = []
    groups = {}
    for shop, listings in by_shop.items():
        if listings is None:
            continue
        for l in listings:
            key = shop if l.get("group", "box") == "box" else f"{shop} (other sealed)"
            groups.setdefault(key, []).append(l)
        groups.setdefault(shop, [])              # a shop with no boxes still gets remembered
    for shop, listings in groups.items():
        ids = {l["id"] for l in listings}
        if shop not in known:
            what = "other sealed" if shop.endswith("(other sealed)") else "box"
            print(f"   (remembering {len(ids)} existing {what} listing(s) at {shop.replace(' (other sealed)', '')}; new ones will alert)")
            known[shop] = sorted(ids)
            continue
        before = set(known[shop])
        for l in listings:
            if l["id"] in before or l["box_id"] in finds_ids:
                continue            # already known, or already alerting as a buyable box
            status = ("in stock" if l["available"] else "listed, not buyable yet")
            if l["available"] and l["price"] > l["max"]:
                status += f" (over your {money(l['max'])} max)"
            l = dict(l, note=(l["note"] + ", " if l["note"] else "") + status)
            out.append(l)
        known[shop] = sorted(before | ids)
    return out


# ---------------------------------------------------------------- singles
def suggest(base, q):
    url = (f"{base}/search/suggest.json?q={urllib.parse.quote(q)}"
           f"&resources[type]=product&resources[limit]=10")
    data = fetch_json(url)
    if not data:
        return []
    return data.get("resources", {}).get("results", {}).get("products", [])


def product_js(base, handle):
    return fetch_json(f"{base}/products/{handle}.js")


def elemental_card(card, base):
    """Elemental titles include the card number, e.g. 'Sabo - OP13-120 [Carrying On His Will]'."""
    excl = card.get("exclude", DEFAULT_EXCLUDE)
    out = []
    for p in suggest(base, card["num"]):
        title = p.get("title", "")
        if not any(n in title.lower() or n in p.get("handle", "") for n in card_num_variants(card["num"])):
            continue
        if is_excluded(title, excl):
            continue
        if not p.get("available"):
            continue
        price = float(p.get("price_min") or p.get("price") or 0)
        if price <= 0 or price > card["max"]:
            continue
        # search results don't always carry variant IDs; the product .js always does
        _, vid = cheapest_available(p.get("variants"), cents=False)
        if not vid:
            js = product_js(base, p["handle"]) or {}
            _, vid = cheapest_available(js.get("variants"), cents=True)
        out.append(single_find(card, "Elemental Arcade", price, base + "/products/" + p["handle"], title,
                               shopify_cart_link(base, vid, card.get("qty", 1))))
    return out


def js_matches_number(p, num):
    blob = json.dumps(p).lower()
    return any(n in blob for n in card_num_variants(num))


def nm_price(p):
    """(near-mint available price in dollars, variant id). Mayhem/GG .js prices are cents."""
    avail = [v for v in p.get("variants", []) if v.get("available")]
    if not avail:
        return None, None
    nm = [v for v in avail if "near mint" in (v.get("title") or "").lower()]
    v = min(nm or avail, key=lambda v: v["price"])
    return v["price"] / 100, v.get("id")


def handle_shop_card(card, shop_name, base):
    excl = card.get("exclude", DEFAULT_EXCLUDE)
    handles = list(card.get("handles", {}).get(shop_name, []))
    if not handles:  # search by name and confirm number below
        for p in suggest(base, card.get("search", card["name"])):
            if not is_excluded(p.get("title", ""), excl):
                handles.append(p["handle"])
        handles = handles[:8]
    out = []
    for h in handles:
        p = product_js(base, h)
        if not p or not js_matches_number(p, card["num"]):
            continue
        if is_excluded(p.get("title", ""), excl):
            continue
        price, vid = nm_price(p)
        if price is None or price > card["max"]:
            continue
        out.append(single_find(card, shop_name, price, f"{base}/products/{h}", p.get("title", ""),
                               shopify_cart_link(base, vid, card.get("qty", 1))))
    return out


def single_find(card, shop, price, url, title, cart=""):
    return {"id": f"card|{shop}|{card['num']}|{url.rsplit('/', 1)[-1]}", "kind": "Single",
            "name": f"{card['name']} {card['num']}".strip(), "deck": card.get("deck", ""), "qty": card.get("qty", 1),
            "shop": shop, "price": price, "url": url, "cart": cart, "note": title,
            "priority": card.get("priority", False)}


MAX_VALUE_PICKS = 15


def repo_json(cfg, name, max_age=1800):
    """A JSON file from the bot's GitHub repo (cached for max_age seconds). None if unavailable."""
    url = f"{(cfg or {}).get('repo_raw_url', REPO_RAW_URL).rstrip('/')}/{name}"
    hit = _remote_cache.get(url)
    if hit and time.time() - hit[0] < max_age:
        return hit[1]
    data = None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        data = None      # not there yet (e.g. before the ledger's first run) - that's fine
    _remote_cache[url] = (time.time(), data)
    return data


def load_picks_file(cfg=None):
    """market_picks.json: the local copy if it's today's (the cloud copy has it from the repo),
    otherwise the latest one from GitHub (the PC copy)."""
    local = None
    try:
        local = json.load(open(PICKS_PATH, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    if isinstance(local, dict) and local.get("date") == f"{datetime.now():%Y-%m-%d}":
        return local
    remote = repo_json(cfg, "market_picks.json")
    if isinstance(remote, dict):
        try:
            json.dump(remote, open(PICKS_PATH, "w", encoding="utf-8"), indent=1)
        except Exception:  # noqa: BLE001
            pass
        return remote
    return local


def load_value_picks(cfg=None):
    """Cards the daily market ledger thinks are good value, from market_picks.json:
    {"watch": [{"name", "product_url", "max", "market", "note"}, ...]}. Missing file = none."""
    data = load_picks_file(cfg)
    if not data:
        return []
    out = []
    for x in (data.get("watch", []) if isinstance(data, dict) else [])[:MAX_VALUE_PICKS]:
        try:
            if x["product_url"].startswith("https://") and float(x["max"]) > 0:
                out.append(x)
        except (KeyError, TypeError, ValueError):
            continue
    return out


def value_pick_card(pick):
    """Check one value pick's product page; returns a find if it's buyable at or under its max."""
    url = pick["product_url"].split("?")[0].rstrip("/")
    p = fetch_json(url + ".js")
    if not p:
        return []
    price, vid = nm_price(p)
    if price is None or price > float(pick["max"]):
        return []
    card = {"name": pick.get("name", p.get("title", "Value pick")), "num": "", "qty": 1, "max": float(pick["max"]),
            "deck": "value pick", "priority": False}
    host = urllib.parse.urlparse(url).netloc
    shop = {"elementalarcade.com.au": "Elemental Arcade", "tcg.goodgames.com.au": "Good Games"}.get(
        host, "Mayhem" if "mayhem" in host else host)
    f = single_find(card, shop, price, url, p.get("title", ""), shopify_cart_link(url, vid))
    f["id"] = f"card|pick|{url}"
    f["kind"] = "Single"
    f["value_pick"] = True
    market = pick.get("market")
    f["note"] = (p.get("title", "") + (f" · US market ≈ {money(float(market))}" if market else "") +
                 (f" · {pick['note']}" if pick.get("note") else ""))
    return [f]


def check_singles(cfg):
    shops = cfg["singles"]["shops"]
    cards = [c for c in cfg["singles"]["cards"] if c.get("enabled", True)]
    jobs = []
    for c in cards:
        if "Elemental Arcade" in shops:
            jobs.append((elemental_card, c, shops["Elemental Arcade"]))
        for name in ("Mayhem", "Good Games"):
            if name in shops:
                jobs.append((handle_shop_card, c, name, shops[name]))
    if cfg.get("value_picks", True):
        for pick in load_value_picks(cfg):
            jobs.append((value_pick_card, pick))
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda j: j[0](*j[1:]), jobs))
    return [f for r in results for f in r]


# ---------------------------------------------------------------- drop-day mode
def parse_windows(cfg):
    out = []
    for w in cfg.get("drop_windows", []) or []:
        try:
            start = datetime.strptime(w["start"], "%Y-%m-%d %H:%M")
            end = datetime.strptime(w["end"], "%Y-%m-%d %H:%M")
        except (KeyError, ValueError) as e:
            print(f"   ! drop window {w.get('name', '?')} skipped: use \"YYYY-MM-DD HH:MM\" ({e})")
            continue
        if end <= start:
            continue
        every = max(MIN_DROP_SECONDS, int(w.get("every_seconds", 60)))
        out.append({"name": w.get("name", "drop"), "start": start, "end": end, "every": every,
                    "sealed_only": w.get("sealed_only", True)})
    return out


def active_window(cfg, now=None):
    now = now or datetime.now()
    for w in parse_windows(cfg):
        if w["start"] <= now < w["end"]:
            return w
    return None


def seconds_until_next_check(cfg, normal_minutes, now=None):
    """Normal gap, the drop-window gap while one is on, or a short wait so a window starts on time."""
    now = now or datetime.now()
    w = active_window(cfg, now)
    if w:
        return min(w["every"], max(1.0, (w["end"] - now).total_seconds()))
    normal = normal_minutes * 60
    starts = [x["start"] for x in parse_windows(cfg) if x["start"] > now]
    if starts:
        wait = (min(starts) - now).total_seconds()
        if wait < normal:
            return max(1.0, wait)
    return normal


# ---------------------------------------------------------------- PC/cloud hand-off
def heartbeat_role(cfg):
    a = cfg.get("alerts") or {}
    if not a.get("heartbeat_topic"):
        return None
    return (a.get("heartbeat_role") or "send").lower()


def send_heartbeat(cfg):
    """PC copy: tell the cloud copy we're on (at most every 15 minutes)."""
    global _last_heartbeat
    if time.time() - _last_heartbeat < HEARTBEAT_EVERY:
        return
    topic = cfg["alerts"]["heartbeat_topic"]
    try:
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=b"pc-on",
                                     headers={"User-Agent": UA, "Cache": "yes"})
        urllib.request.urlopen(req, timeout=15).read()
        _last_heartbeat = time.time()
    except Exception as e:  # noqa: BLE001
        print(f"   ! couldn't tell the cloud copy the PC is on ({e})")


def pc_is_on(cfg):
    """Cloud copy: has the PC copy checked in recently? If ntfy can't be read, assume not
    (a doubled alert is better than a missed one)."""
    topic = cfg["alerts"]["heartbeat_topic"]
    try:
        req = urllib.request.Request(f"https://ntfy.sh/{topic}/json?poll=1&since={HEARTBEAT_FRESH}",
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            lines = r.read().decode("utf-8", "replace").splitlines()
        return any(json.loads(l).get("event") == "message" for l in lines if l.strip())
    except Exception as e:  # noqa: BLE001
        print(f"   ! couldn't check whether the PC is on ({e}), posting anyway")
        return False


# ---------------------------------------------------------------- status posts
# Short, no-ping Discord posts about the bot itself (not finds). They go to "discord_webhook_status"
# if you add one, otherwise to the booster-boxes channel.
GREEN, AMBER, RED, BLUE, GREY = 0x2A9D8F, 0xF4A261, 0xE63946, 0x457B9D, 0x6C757D


def load_status():
    try:
        return json.load(open(STATUS_PATH, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save_status(status):
    json.dump(status, open(STATUS_PATH, "w", encoding="utf-8"), indent=1, sort_keys=True)


def post_status(cfg, text, color=GREY):
    alerts = (cfg or {}).get("alerts") or {}
    hook = alerts.get("discord_webhook_status") or alerts.get("discord_webhook_boxes") or alerts.get("discord_webhook")
    print(f"   [status] {text}")
    if not hook:
        return
    payload = {"username": alerts.get("bot_name") or "One Piece Restock",
               "embeds": [{"description": text[:4000], "color": color,
                           "footer": {"text": f"Sent by the {copy_label(cfg)}"}}],
               "allowed_mentions": {"parse": []}}
    try:
        req = urllib.request.Request(hook, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "User-Agent": UA})
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:  # noqa: BLE001
        print(f"   ! status post failed: {e}")


def copy_label(cfg):
    """Which copy of the bot is running: the cloud one (GitHub Actions) or the PC one."""
    if os.environ.get("GITHUB_ACTIONS") == "true" or heartbeat_role(cfg) == "listen":
        return "cloud copy (GitHub)"
    return "PC copy"


def shop_names(cfg):
    names = {}
    for group in sealed_shops(cfg):
        for shop in group:
            names.setdefault(urllib.parse.urlparse(shop.get("url") or shop.get("base")).netloc, shop["name"])
    for name, base in cfg.get("singles", {}).get("shops", {}).items():
        names.setdefault(urllib.parse.urlparse(base).netloc, name)
    return names


def shop_health(cfg, status):
    """Compare this run's shop results with earlier runs. Returns (text, color) posts for
    shops that just went down (failed SHOP_DOWN_AFTER checks in a row) or just came back."""
    names = shop_names(cfg)
    fails = status.setdefault("shop_fails", {})
    down = set(status.get("shop_down", []))
    posts = []
    with _host_lock:
        results = dict(_host_results)

    # Nearly every shop failing in the same check means the bot lost its connection (or got
    # blocked), not that the shops went down. Post one message about that instead of one per shop,
    # and leave the per-shop counters alone so they don't all fire once the connection is back.
    failed = [h for h, (ok, bad) in results.items() if bad and not ok]
    if len(results) >= OFFLINE_MIN_SHOPS and len(failed) >= OFFLINE_SHARE * len(results):
        streak = status.get("offline_streak", 0) + 1
        status["offline_streak"] = streak
        if streak == SHOP_DOWN_AFTER:
            posts.append((f"📡 **The bot can't reach the shops.** {len(failed)} of {len(results)} sites failed "
                          f"for {streak} checks in a row, so this is the bot's internet connection (or it's being "
                          f"blocked), not the shops. Stock isn't being watched until it's back. You'll get a post "
                          f"when it is.", RED))
        status["shop_down"] = sorted(down)
        return posts
    if status.get("offline_streak", 0) >= SHOP_DOWN_AFTER:
        posts.append(("📡 **Connection is back**, so the bot can see the shops again.", GREEN))
    status["offline_streak"] = 0

    for host, (ok, bad) in results.items():
        name = names.get(host, host)
        if ok:
            fails[host] = 0
            if host in down:
                down.discard(host)
                posts.append((f"✅ **{name}** is loading again, so it's back on watch.", GREEN))
        elif bad:
            fails[host] = fails.get(host, 0) + 1
            if fails[host] >= SHOP_DOWN_AFTER and host not in down:
                down.add(host)
                posts.append((f"⚠️ **{name}** hasn't loaded for {fails[host]} checks in a row, so the bot "
                              f"can't see its stock right now. You'll get a post when it's back.", AMBER))
    status["shop_down"] = sorted(down)
    return posts


# ---------------------------------------------------------------- state + alerts
def load_state():
    try:
        return json.load(open(STATE_PATH))
    except Exception:  # noqa: BLE001
        return {}


def save_state(state):
    json.dump(state, open(STATE_PATH, "w"), indent=1, sort_keys=True)


def new_only(finds, state):
    """New = not seen in stock last time, or cheaper than last time."""
    out = []
    for f in finds:
        prev = state.get(f["id"])
        if prev is None or f["price"] < prev - 0.001:
            out.append(f)
    return out


def push_phone(cfg, title, body):
    topic = (cfg.get("alerts") or {}).get("ntfy_topic")
    if not topic:
        return
    try:
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
                                     headers={"Title": title, "User-Agent": UA})
        urllib.request.urlopen(req, timeout=15).read()
        print("   (sent to your phone via ntfy)")
    except Exception as e:  # noqa: BLE001
        print(f"   ! phone alert failed: {e}")


def push_discord(cfg, title, body, finds=None):
    """Post to Discord through webhook URLs. Boxes and new listings go to the boxes channel,
    singles to the singles channel. One embed per find (up to 10, Discord's limit)."""
    alerts = cfg.get("alerts") or {}
    default = alerts.get("discord_webhook")
    boxes_hook = alerts.get("discord_webhook_boxes") or default
    singles_hook = alerts.get("discord_webhook_singles") or default
    sealed_hook = alerts.get("discord_webhook_sealed") or boxes_hook
    if not (default or boxes_hook or singles_hook):
        return False
    if finds is None:  # test message: post to every channel that's set up
        ok = True
        for hook in dict.fromkeys(h for h in (boxes_hook, singles_hook, sealed_hook, default) if h):
            ok = _discord_post(alerts, hook, title, [{"title": title[:256], "description": body[:4000],
                                                       "color": 0x2A9D8F}], 0) and ok
        return ok
    groups = {}
    for f in finds:
        if f["kind"] == "Sealed" or (f["kind"] == "New listing" and f.get("group") == "watch"):
            hook = sealed_hook               # other sealed products: their own channel if set up
        elif f["kind"] in BOX_KINDS:
            hook = boxes_hook
        else:
            hook = singles_hook
        if hook:
            groups.setdefault(hook, []).append(f)
    ok = True
    for hook, group in groups.items():
        n_box = sum(1 for f in group if f["kind"] == "Booster box")
        n_new = sum(1 for f in group if f["kind"] == "New listing")
        t = f"{len(group)} new find(s)" + (f", {n_box} box(es)" if n_box else "") + \
            (f", {n_new} new listing(s)" if n_new else "")
        ok = _discord_post(alerts, hook, t, _discord_embeds(group), max(0, len(group) - 10)) and ok
    return ok


def _discord_embeds(finds):
    embeds = []
    for f in finds[:10]:
        kind = f["kind"]
        fields = [{"name": "Price", "value": money(f["price"]), "inline": True},
                  {"name": "Shop", "value": f["shop"], "inline": True}]
        if kind == "Single":
            fields.append({"name": "Want", "value": f"x{f['qty']}" + (f" ({f['deck']})" if f.get("deck") else ""),
                           "inline": True})
        if f.get("cart"):
            qty = f" (x{f['qty']})" if kind == "Single" and f.get("qty", 1) > 1 else ""
            fields.append({"name": "⚡ Buy", "value": f"[Add to cart → checkout{qty}]({f['cart']})", "inline": False})
        if f.get("note"):
            fields.append({"name": "Status" if kind == "New listing" else "Listing",
                           "value": str(f["note"])[:1000], "inline": False})
        if kind == "Booster box":
            icon, color = "📦 ", 0xF4A261
        elif kind == "Sealed":
            icon, color = "🎁 ", 0x2A9D8F
        elif kind == "New listing":
            icon, color = "🆕 ", 0x9B5DE5
        elif f.get("value_pick"):
            icon, color = "💎 Value pick: ", 0x9B5DE5
        else:
            icon, color = ("⭐ ", 0xE63946) if f.get("priority") else ("🃏 ", 0x457B9D)
        embeds.append({"title": (icon + f["name"])[:256], "url": f["url"], "color": color, "fields": fields})
    return embeds


def _discord_post(alerts, hook, title, embeds, extra):
    content = alerts.get("discord_ping", "") + (f" {title}" if title else "")
    if extra > 0:
        content += f" (+{extra} more, see finds.log)"
    payload = {"username": alerts.get("bot_name") or "One Piece Restock",
               "content": content.strip()[:2000], "embeds": embeds,
               "allowed_mentions": {"parse": ["roles", "users", "everyone"]}}
    try:
        req = urllib.request.Request(hook, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "User-Agent": UA})
        urllib.request.urlopen(req, timeout=15).read()
        print("   (posted to Discord)")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"   ! Discord alert failed: {e}")
        return False


def desktop_beep():
    try:
        if sys.platform.startswith("win"):
            import winsound
            winsound.MessageBeep()
        else:
            print("\a", end="", flush=True)
    except Exception:  # noqa: BLE001
        pass


def best_single_shop(finds):
    by = {}
    for f in finds:
        if f["kind"] == "Single":
            by.setdefault(f["shop"], set()).add(f["name"])
    if not by:
        return None
    shop, names = max(by.items(), key=lambda kv: len(kv[1]))
    return shop, len(names)


def report(finds, label):
    boxes = [f for f in finds if f["kind"] == "Booster box"]
    sealed = [f for f in finds if f["kind"] == "Sealed"]
    listed = [f for f in finds if f["kind"] == "New listing"]
    singles = sorted([f for f in finds if f["kind"] == "Single"],
                     key=lambda f: (not f.get("priority"), f["name"], f["price"]))
    lines = []
    if boxes:
        lines.append("BOOSTER BOXES")
        for f in sorted(boxes, key=lambda f: f["price"]):
            lines.append(f"  {f['name']}  {money(f['price'])}  @ {f['shop']} {f['note']}".rstrip())
            lines.append(f"    {f['url']}")
            if f.get("cart"):
                lines.append(f"    BUY: {f['cart']}")
    if sealed:
        lines.append("OTHER SEALED")
        for f in sorted(sealed, key=lambda f: f["price"]):
            lines.append(f"  {f['name']}  {money(f['price'])}  @ {f['shop']}  ({f['note']})")
            lines.append(f"    {f['url']}")
            if f.get("cart"):
                lines.append(f"    BUY: {f['cart']}")
    if listed:
        lines.append("NEW LISTINGS")
        for f in listed:
            lines.append(f"  {f['name']}  {money(f['price'])}  @ {f['shop']}  ({f['note']})")
            lines.append(f"    {f['url']}")
            if f.get("cart"):
                lines.append(f"    BUY: {f['cart']}")
    if singles:
        lines.append("SINGLES")
        for f in singles:
            star = "*" if f.get("priority") else " "
            deck = f" [{f['deck']}]" if f.get("deck") else ""
            lines.append(f" {star}{f['name']} x{f['qty']}{deck}  {money(f['price'])}  @ {f['shop']}")
            lines.append(f"    {f['url']}")
            if f.get("cart"):
                lines.append(f"    BUY: {f['cart']}")
        b = best_single_shop(singles)
        if b and b[1] > 1:
            lines.append(f"  Tip: {b[0]} has {b[1]} of these cards - one order saves shipping.")
    if not lines:
        return f"{label}: nothing new in stock."
    return f"{label}:\n" + "\n".join(lines)


# ---------------------------------------------------------------- daily recap
def _lines(items, limit=8):
    out = "\n".join(items[:limit])
    if len(items) > limit:
        out += f"\n…and {len(items) - limit} more"
    return out[:1020] or "-"


def _short(name, n=60):
    name = name or "(no name)"
    return name if len(name) <= n else name[:n - 1] + "…"


def run_recap(cfg, now=None, post=True, save=True):
    """One Discord post summing up the day: what's buyable within your limits, price moves and
    new listings since yesterday's recap, what's coming up, and shops that are down.
    Returns the embed (the /recap command replies with it instead of posting)."""
    now = now or datetime.now()
    print(f"\n=== Daily recap - {now:%a %d %b %Y %I:%M %p} ===")
    box_finds, by_shop = check_sealed(cfg)
    singles = check_singles(cfg)

    # today's snapshot: every box / watched listing (in stock or not) plus in-stock singles
    snap = {}
    for listings in by_shop.values():
        for l in listings or []:
            snap[l["id"]] = {"name": l["name"], "shop": l["shop"], "price": round(l["price"], 2),
                             "available": l["available"], "url": l["url"]}
    for f in singles:
        snap[f["id"]] = {"name": f["name"], "shop": f["shop"], "price": round(f["price"], 2),
                         "available": True, "url": f["url"]}
    try:
        prev = json.load(open(RECAP_PATH, encoding="utf-8")).get("snapshot", {})
    except Exception:  # noqa: BLE001
        remote = repo_json(cfg, "recap.json")       # the PC copy compares with the cloud's last recap
        prev = remote.get("snapshot") if isinstance(remote, dict) else None

    fields = []
    # 1. buyable now within your limits
    order = {"Booster box": 0, "Sealed": 1, "Single": 2}
    buy = sorted(box_finds + singles, key=lambda f: (order[f["kind"]], not f.get("priority"), f["price"]))
    icon = {"Booster box": "📦", "Sealed": "🎁", "Single": "🃏"}
    lines = [f"{icon[f['kind']]} [{_short(f['name'])}]({f.get('cart') or f['url']}) **{money(f['price'])}** · {f['shop']}"
             for f in buy]
    fields.append({"name": f"🛒 Buyable now within your limits ({len(buy)})",
                   "value": _lines(lines) if lines else "Nothing on your list is in stock under your max right now."})

    # 2. price moves, restocks and new listings since the last recap
    if prev is not None:
        moves, back, new = [], [], []
        for k, v in snap.items():
            p = prev.get(k)
            if not p:
                new.append(f"[{_short(v['name'])}]({v['url']}) {money(v['price'])} · {v['shop']}")
                continue
            if v["available"] and not p.get("available"):
                back.append(f"[{_short(v['name'])}]({v['url']}) {money(v['price'])} · {v['shop']}")
            if p.get("price") and v["price"] and abs(v["price"] - p["price"]) >= 1:
                pct = (v["price"] - p["price"]) / p["price"] * 100
                if abs(pct) >= RECAP_MOVE_PCT:
                    moves.append((pct, f"{'📉' if pct < 0 else '📈'} [{_short(v['name'], 50)}]({v['url']}) "
                                       f"{money(p['price'])} → **{money(v['price'])}** ({pct:+.0f}%) · {v['shop']}"))
        moves.sort(key=lambda m: m[0])           # biggest drops first
        fields.append({"name": "💸 Price changes since yesterday",
                       "value": _lines([m[1] for m in moves]) if moves else "No moves of 5% or more."})
        if back:
            fields.append({"name": "🔁 Back in stock", "value": _lines(back)})
        if new:
            fields.append({"name": "🆕 Newly listed", "value": _lines(new)})
    else:
        fields.append({"name": "💸 Price changes", "value": "First recap: price changes start showing from tomorrow."})

    # 3. market value picks from the ledger, if they've been shared with the bot
    try:
        picks = load_picks_file(cfg) or {}
        if isinstance(picks, dict):
            picks = picks.get("picks", [])
        pl = [f"⭐ [{_short(x['name'])}]({x.get('url', '')}) **{money(float(x['price']))}** · {x.get('shop', '')}"
              + (f" · {x['note']}" if x.get("note") else "") for x in picks if x.get("name") and x.get("price")]
        if pl:
            fields.append({"name": "📊 Worth a look (vs US market)", "value": _lines(pl, 6)})
    except Exception:  # noqa: BLE001
        pass

    # 4. coming up: releases and drop windows in the next two weeks
    soon = []
    for r in cfg.get("releases", DEFAULT_RELEASES) or []:
        try:
            d = datetime.strptime(r["date"], "%Y-%m-%d")
        except (KeyError, ValueError):
            continue
        days = (d.date() - now.date()).days
        if 0 <= days <= RECAP_DAYS_AHEAD:
            soon.append((d, f"📅 **{d:%a %d %b}** {r['name']}" + (" (today!)" if days == 0 else f" (in {days} days)")))
    for w in parse_windows(cfg):
        if now < w["end"] and (w["start"] - now).days <= RECAP_DAYS_AHEAD:
            soon.append((w["start"], f"🚨 Drop mode: {w['name']}, {w['start']:%a %d %b %I:%M %p}"))
    soon.sort(key=lambda x: x[0])
    fields.append({"name": f"🗓️ Next {RECAP_DAYS_AHEAD} days",
                   "value": _lines([x[1] for x in soon]) if soon else "No releases in the next two weeks."})

    # 5. shops the bot can't see
    down = load_status().get("shop_down", [])
    if down:
        names = shop_names(cfg)
        fields.append({"name": "⚠️ Not loading", "value": ", ".join(names.get(h, h) for h in down)})

    alerts = cfg.get("alerts") or {}
    ledger = alerts.get("ledger_url") or cfg.get("ledger_url")
    embed = {"title": f"☀️ Daily recap · {now:%A %d %B}", "color": 0xE9C46A, "fields": fields[:25]}
    if ledger:
        embed["description"] = f"Full market report (US prices, PSA, movers): [Grand Line Ledger]({ledger})"
        embed["url"] = ledger
    hook = alerts.get("discord_webhook_recap") or alerts.get("discord_webhook_status") or \
        alerts.get("discord_webhook_boxes") or alerts.get("discord_webhook")
    for fld in fields:
        print(f"\n{fld['name']}\n{fld['value']}")
    if hook and post:
        payload = {"username": alerts.get("bot_name") or "One Piece Restock", "embeds": [embed],
                   "allowed_mentions": {"parse": []}}
        try:
            req = urllib.request.Request(hook, data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json", "User-Agent": UA})
            urllib.request.urlopen(req, timeout=15).read()
            print("\n   (recap posted to Discord)")
        except Exception as e:  # noqa: BLE001
            print(f"\n   ! recap post failed: {e}")
    if save:
        json.dump({"date": f"{now:%Y-%m-%d}", "snapshot": snap}, open(RECAP_PATH, "w", encoding="utf-8"), indent=1)
    return embed


# ---------------------------------------------------------------- main
def run_once(cfg, args, drop=None):
    stamp = datetime.now().strftime("%a %d %b %Y %I:%M:%S %p")
    with _host_lock:
        _host_results.clear()
    tag = f" [DROP MODE: {drop['name']}]" if drop else ""
    print(f"\n=== One Piece restock check - {stamp}{tag} ===")
    do_sealed = not args.singles
    do_singles = not args.sealed and not (drop and drop["sealed_only"])
    finds, listed = [], []
    if do_sealed:
        print(" checking booster boxes...")
        box_finds, by_shop = check_sealed(cfg)
        finds += box_finds
        if cfg.get("new_listings", True):
            known = load_known()
            listed = new_listings(by_shop, known, box_finds)
            save_known(known)
    if do_singles:
        print(" checking singles...")
        finds += check_singles(cfg)

    state = load_state()
    show = finds if args.all else new_only(finds, state)
    show = show + listed
    text = report(show, "Everything currently matching" if args.all else "New since last check")
    print("\n" + text)

    # remember what's in stock now (items that sold out drop off, so a restock counts as new).
    # Keep entries for whatever this run didn't check (e.g. singles during drop mode).
    checked = {"Booster box"} if do_sealed else set()
    if do_singles:
        checked.add("Single")
    kept = {k: v for k, v in state.items()
            if not ((k.startswith(("box|", "sealed|")) and "Booster box" in checked) or (k.startswith("card|") and "Single" in checked))}
    kept.update({f["id"]: f["price"] for f in finds})
    save_state(kept)

    role = heartbeat_role(cfg)
    if role == "send":
        send_heartbeat(cfg)
    pc_on = pc_is_on(cfg) if role == "listen" else False

    # status posts: shop health, and (cloud copy) the PC going quiet or coming back
    status = load_status()
    status["last_check"] = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
    status["last_found"] = len(finds)
    posts = shop_health(cfg, status)
    if role == "listen":
        before = status.get("pc_on")
        if before is True and not pc_on:
            posts.append(("🖥️ Your PC copy has gone quiet (off or asleep). The **cloud copy** is posting alerts now.", BLUE))
        elif before is False and pc_on:
            post_status(cfg, "🖥️ Your PC copy is back on and posting alerts. The cloud copy is going quiet.", BLUE)
        status["pc_on"] = pc_on
    save_status(status)
    if not pc_on:            # while the PC is on, it reports these itself
        for text, color in posts:
            post_status(cfg, text, color)

    if show and not args.all and pc_on:
        print("   (your PC copy is on and posts these itself - cloud copy staying quiet)")
        return

    if show and not args.all:
        desktop_beep()
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"\n--- {stamp} ---\n{text}\n")
        n_box = sum(1 for f in show if f["kind"] in ("Booster box", "Sealed"))
        n_new = sum(1 for f in show if f["kind"] == "New listing")
        title = f"One Piece: {len(show)} new find(s)" + (f", {n_box} box(es)" if n_box else "") + \
            (f", {n_new} new listing(s)" if n_new else "")
        push_phone(cfg, title, text[:3500])
        # boxes first, then new listings, then priority singles, so the important ones fill Discord's 10 slots
        order = {"Booster box": 0, "Sealed": 1, "New listing": 2, "Single": 3}
        ordered = sorted(show, key=lambda f: (order[f["kind"]], not f.get("priority"), f["price"]))
        push_discord(cfg, title, text, ordered)


def main():
    # Windows writes bot_output in an old encoding that has no emoji; don't let that crash the bot
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="One Piece TCG restock bot")
    ap.add_argument("--all", action="store_true", help="show everything matching, not just new finds")
    ap.add_argument("--loop", type=float, metavar="MINUTES", help="keep checking every N minutes")
    ap.add_argument("--sealed", action="store_true", help="only booster boxes")
    ap.add_argument("--singles", action="store_true", help="only singles")
    ap.add_argument("--test-discord", action="store_true", help="post a test message to Discord and stop")
    ap.add_argument("--recap", action="store_true", help="post the daily recap to Discord and stop")
    args = ap.parse_args()

    try:
        cfg = load_config()
    except FileNotFoundError:
        sys.exit(f"config.json not found next to {os.path.basename(__file__)}")
    except json.JSONDecodeError as e:
        sys.exit(f"config.json has a typo: {e}")

    if args.test_discord:
        if not any((cfg.get("alerts") or {}).get(k) for k in ("discord_webhook", "discord_webhook_boxes", "discord_webhook_singles")):
            sys.exit('No "discord_webhook" in the "alerts" section of config.json yet.')
        ok = push_discord(cfg, "Test from your One Piece restock bot",
                          "If you can see this, Discord alerts are working.")
        sys.exit(0 if ok else 1)

    if args.recap:
        run_recap(cfg)
        return

    if not args.loop:
        run_once(cfg, args)
        return
    print(f"Running every {args.loop:g} minutes (faster inside drop windows). Press Ctrl+C to stop.")
    every = f"{args.loop:g} minute" + ("" if args.loop == 1 else "s")
    windows = [w for w in parse_windows(cfg) if w["end"] > datetime.now()]
    nxt = f" Next drop window: **{windows[0]['name']}**, {windows[0]['start']:%a %d %b %I:%M %p}." if windows else ""
    post_status(cfg, f"🟢 **Bot online** ({'PC' if heartbeat_role(cfg) != 'listen' else 'cloud'}). "
                     f"Checking every {every}.{nxt}", GREEN)
    good_cfg, was_dropping, problem = cfg, None, None
    while True:
        try:
            try:
                cfg = load_config()  # pick up edits without restarting
            except json.JSONDecodeError as e:
                if problem != "config":
                    post_status(good_cfg, f"⚠️ **config.json has a typo**, so the bot is paused until it's fixed "
                                          f"and saved.\n`{e}`", RED)
                problem = "config"
                print(f"   ! config.json has a typo, fix and save it: {e}")
                time.sleep(60)
                continue
            if problem == "config":
                post_status(cfg, "✅ config.json is fixed. Checking again.", GREEN)
            good_cfg = cfg
            drop = active_window(cfg)
            if drop and was_dropping != drop["name"]:
                print(f"\n>>> DROP MODE ON: {drop['name']} until {drop['end']:%I:%M %p}, "
                      f"checking every {drop['every']}s")
                post_status(cfg, f"🚨 **Drop mode ON: {drop['name']}.** Checking booster boxes every "
                                 f"{drop['every']}s until {drop['end']:%I:%M %p}.", RED)
            elif not drop and was_dropping:
                print(f"\n>>> DROP MODE OFF, back to every {args.loop:g} minutes")
                post_status(cfg, f"Drop mode off ({was_dropping} finished). Back to every {every}.", GREY)
            was_dropping = drop["name"] if drop else None
            run_once(cfg, args, drop)
            if problem == "crash":
                post_status(cfg, "✅ Checks are working again.", GREEN)
            problem = None
            wait = seconds_until_next_check(cfg, args.loop)
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001
            print(f"   ! check failed: {e}")
            if problem != "crash":
                post_status(good_cfg, f"⚠️ **A check failed:** `{str(e)[:300]}`\nIt'll keep retrying every {every}.", RED)
            problem = "crash"
            wait = args.loop * 60
        sys.stdout.flush()
        time.sleep(wait)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
