#!/usr/bin/env python3
"""
Pokémon watch for the restock bot
=================================

Adds Pokémon TCG to the One Piece restock bot, organised in "sections": one per upcoming English
release (Delta Reign, the 30th Celebration products...). For each section the bot:

  1. searches the same Australian shops as the One Piece checks (plus a couple of Pokémon shops) for
     that set's sealed products: booster boxes, Elite Trainer Boxes, booster bundles, Build & Battle,
     collections, tins, blisters, battle decks. English only; accessories and cases are skipped.
  2. alerts in that release's own Discord channel when a shop first lists a product (pre-orders,
     "coming soon") and whenever one is buyable at or under the max price for its type.
  3. posts in-store drop notices in #pokemon-in-store: the evening before a release ("tomorrow in
     stores") and at 7am on the day ("out today", pinging the Pokémon role). Anyone in the server can
     add a sighting with /pokemon report (that's in commands_bot.py).
  4. turns on drop mode (checks every minute) on the PC copy the evening before and the morning of a
     release, for just the sets releasing that day.

Nothing Pokémon is posted until the Pokémon channels exist (add_pokemon_channels.py, or /pokemon setup
in Discord). Until then the bot quietly remembers what's listed, so setting the channels up later
doesn't flood them with old listings. It only reads shop websites: it never buys or logs in.

Everything has a default, so config.json needs nothing. To change things, add a "pokemon" section to
config.json, e.g.:

    "pokemon": {
      "max": {"Elite Trainer Box": 99, "Booster box": 280},
      "sections": [
        {"name": "ME07 Example Name", "code": "ME07", "match": ["Example Name"], "emoji": "🌟",
         "dates": [{"date": "2027-01-29", "what": "Release day", "drop": true, "ping": true}]}
      ]
    }

A section with the same name as a built-in one changes that one (e.g. {"name": "30th Celebration",
"enabled": false} switches it off); any other name is added. "pokemon": false switches Pokémon off.

Webhooks (set by add_pokemon_channels.py): "pokemon_webhooks" in "alerts" (config.json or secrets.json)
maps a section's slug, "restocks" (the catch-all channel) and "in-store" to webhook links. The cloud
copy reads the same map, as one line of JSON, from the POKEMON_WEBHOOKS GitHub secret, and the role to
ping from POKEMON_PING.
"""
import html
import json
import re
import time
import urllib.parse
from datetime import datetime, timedelta

GAME = "pokemon"
YELLOW = 0xFFCB05
EVERY_MINUTES = 10          # PC copy (--loop): a full Pokémon check every 10 min; release mornings every minute
MIN_EVERY = 2
MORNING = "07:00"           # "out today in stores" post
EVENING = "18:00"           # "tomorrow in stores" post, the day before
MORNING_UNTIL = "13:00"     # a morning post that couldn't go out by then is skipped (old news)
EVENING_UNTIL = "23:30"
REMINDER_KEEP_DAYS = 60

# Most you'd pay (AUD) per product type before it alerts as "buyable". New listings and pre-orders
# alert whatever the price (marked "over your max"). 0 = never alert as buyable. Change any of these
# with "pokemon": {"max": {...}} in config.json or /pokemon max in Discord.
# Starting points: normal Australian retail, so a restock at a fair price alerts and a marked-up one
# doesn't. What the shops charged for Delta Reign in Oct 2026: booster boxes $319-350, ETBs $130-160,
# booster bundles $59-70, Build & Battle $44-59, 3-pack blisters $28-35. EB Games (Pitch Black): ETB $120,
# bundle $59, premium collection $99. 30th Celebration Ultra-Premium Collection: $439-449.
DEFAULT_MAX = {
    "Booster box": 360,
    "Elite Trainer Box": 160,
    "Pokémon Center ETB": 220,
    "Booster bundle": 70,
    "Build & Battle": 60,
    "Ultra-Premium Collection": 460,
    "Collection": 100,
    "Small collection": 50,
    "Tin": 45,
    "Mini tin": 25,
    "Blister": 35,
    "Battle deck": 50,
    "Booster pack": 0,
}
TYPES = list(DEFAULT_MAX)
DEFAULT_WATCH_TYPES = [t for t in TYPES if t != "Booster pack"]     # single packs: too many listings to alert on

# The upcoming English releases. "match" is text in a shop's product title (case, spaces and dashes
# don't matter); "queries" is what the bot types into each shop's search (defaults to "match").
# "dates": in-store days. "drop": drop mode the evening before and that morning (PC copy).
# "ping": the 7am "out today" post pings the Pokémon role.
DEFAULT_SECTIONS = [
    {
        "name": "Delta Reign", "code": "ME06", "emoji": "🐉", "match": ["Delta Reign"],
        "dates": [
            {"date": "2026-10-24", "kind": "prerelease", "time": "09:00",
             "what": "prerelease events and the Build & Battle Box at participating Play! Pokémon stores"},
            {"date": "2026-11-06", "kind": "release", "drop": True, "ping": True,
             "what": "booster packs and boxes, Elite Trainer Boxes, booster bundles, Build & Battle boxes and blisters"},
        ],
    },
    {
        "name": "30th Celebration", "emoji": "🎂", "match": ["30th Celebration"],
        "dates": [
            {"date": "2026-10-30", "what": "Espeon ex and Umbreon ex Battle Decks"},
            {"date": "2026-11-06", "drop": True, "ping": True,
             "what": "Day & Night Ultra-Premium Collections, Ditto Premium Collection, Mew & Mewtwo Figure Collections"},
            {"date": "2026-12-04", "what": "Binder Collection and Pokémon ex Tins"},
        ],
    },
    {
        # Announced for early 2027 without an English name yet. Calendar only until it has one: add the
        # name to "match" (and a date) in config.json, or ask Claude, and it gets watched like the others.
        "name": "ME07", "code": "ME07", "emoji": "🌟", "match": [], "channel": False,
        "note": "next Mega Evolution set, early 2027 (English name and date not announced yet)",
    },
]

# Pokémon shops on top of the One Piece ones (which are searched too). Skip any with "skip_shops".
EXTRA_SHOPS = [
    {"name": "Kollecter", "base": "https://www.kollecter.com.au"},
    {"name": "Monster Mart", "base": "https://www.monstermart.com.au"},
]
# One Piece singles shops left out: their Pokémon search results were all singles in Oct 2026, and the
# One Piece want list depends on them not getting busier (they rate-limited the bot before). Good Games'
# sealed shop is searched instead of its singles shop. Add any back with "pokemon": {"shops": [...]}.
SKIP_HOSTS = {"tcg.goodgames.com.au", "elementalarcade.com.au", "www.mayhemcollectables.com.au"}
# Shops whose robots.txt asks bots not to use their search: their English sealed Pokémon collections are
# read instead (one feed per product kind, shared by every release). Add more with "pokemon":
# {"collections": [{"name": "...", "url": "https://.../collections/<handle>/products.json?limit=250"}]}.
DEFAULT_COLLECTIONS = [
    {"name": "Pokebox", "url": f"https://www.pokebox.com.au/collections/{h}/products.json?limit=250"}
    for h in ("english-pokemon-tcg-booster-boxes", "english-pokemon-tcg-elite-trainer-boxes",
              "english-pokemon-tcg-collection-boxes", "english-pokemon-tcg-single-packs")
]

# ---------------------------------------------------------------- reading product titles
NON_ENGLISH_RE = re.compile(r"\b(japanese|japan|jp|jpn|korean|kor|chinese|simplified|traditional|s-?chinese|"
                            r"t-?chinese|thai|indonesian|indo|asia|asian)\b|\(jp\)|日本|中文|한국")
# Opened or graded stuff, cases of several boxes, protectors: never what the bot is for.
HARD_EXCLUDE_RE = re.compile(r"\b(toploaders?|top\s*loaders?|protectors?|acrylic|magnetic|storage|display\s*cases?|"
                             r"empty|opened|graded|psa|cgc|bgs|slab(bed)?|code\s*cards?|single\s*card|cases?|lots?|"
                             r"bulk|proxy|custom|replica|art\s*print|holofoil|holo|reverse\s*holo|non[\s-]*holo)\b"
                             # a card number like 94/102 means a single card (e.g. the Classic Collection reprints)
                             r"|\b\d{1,3}\s*/\s*\d{2,3}\b")
# Accessories. Only checked when the title doesn't already say it's a sealed product, because an ETB's
# title can mention its "65 card sleeves".
SOFT_EXCLUDE_RE = re.compile(r"\b(sleeves?|deck\s*box(es)?|play\s*mats?|playmats?|portfolios?|binders?(?!\s*collection)|"
                             r"card\s*folder|pocket\s*pages?)\b")
STRONG_TYPES = {"Booster box", "Elite Trainer Box", "Pokémon Center ETB", "Booster bundle", "Build & Battle",
                "Ultra-Premium Collection", "Tin", "Mini tin", "Blister"}
TYPE_RULES = [
    ("Pokémon Center ETB", r"pok[eé]?mon\s*cent(er|re).{0,40}(elite\s*trainer|etb)|\bpc\s*etb\b"),
    ("Elite Trainer Box", r"elite\s*trainer\s*box|\betb\b"),
    ("Booster box", r"booster\W*(box|display)|display\s*box|\b36\s*(booster\s*)?packs?\b"),
    ("Booster bundle", r"booster\s*bundle"),
    ("Build & Battle", r"build\s*(&|and|n)\s*battle"),
    ("Ultra-Premium Collection", r"ultra[\s-]*premium|\bupc\b"),
    ("Small collection", r"(poster|sticker|knock\s*out|pin)\s*(collection|box)"),
    ("Mini tin", r"mini\s*tins?\b"),
    ("Tin", r"\btins?\b"),
    ("Blister", r"blister|check\s*lane|\b[23][\s-]*packs?\b"),
    ("Battle deck", r"battle\s*decks?|league\s*battle|starter\s*decks?|theme\s*decks?|\bdecks?\b"),
    ("Collection", r"collection|\bbox\b|premium|figure|poster|stacking|gift"),
    ("Booster pack", r"booster\s*packs?|sleeved\s*boosters?|\bpacks?\b|\bbooster\b"),
]
TYPE_RULES = [(t, re.compile(rx, re.I)) for t, rx in TYPE_RULES]
TYPE_ICON = {"Booster box": "📦", "Elite Trainer Box": "🎒", "Pokémon Center ETB": "🎒", "Booster bundle": "🧺",
             "Build & Battle": "⚔️", "Ultra-Premium Collection": "👑", "Collection": "🎁", "Small collection": "🎁",
             "Tin": "🥫",
             "Mini tin": "🥫", "Blister": "🃏", "Battle deck": "🛡️", "Booster pack": "🃏"}


def _num(x):
    if isinstance(x, bool) or x is None:
        return None
    try:
        return float(str(x).strip().replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _squash(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower().replace("é", "e")).strip("-")
    return s[:60] or "section"


def is_english(title):
    return not NON_ENGLISH_RE.search(str(title or "").lower())


def is_excluded(title, ptype=None):
    t = str(title or "").lower()
    if HARD_EXCLUDE_RE.search(t):
        return True
    return ptype not in STRONG_TYPES and bool(SOFT_EXCLUDE_RE.search(t))


def day_text(d):
    """'Fri 6 Nov' (no leading zero)."""
    return f"{d:%a} {d.day} {d:%b}"


def product_type(title):
    """Booster box, Elite Trainer Box, ... from the product title, or None if it isn't one we know."""
    t = str(title or "")
    for name, rx in TYPE_RULES:
        if rx.search(t):
            return name
    return None


def matches(title, section):
    t, sq = str(title or "").lower(), _squash(title)
    for m in section.get("match") or []:
        if m.lower() in t or (_squash(m) and _squash(m) in sq):
            return True
    return False


# ---------------------------------------------------------------- settings
def _date(s):
    try:
        return datetime.strptime(str(s), "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def _hhmm(s, default):
    s = str(s or default)
    return s if re.fullmatch(r"\d{1,2}:\d{2}", s) else default


def _norm_section(s, problems):
    name = str(s.get("name") or "").strip()
    if not name:
        problems.append(f"pokemon section {s!r} needs a \"name\"; skipped")
        return None
    match = s.get("match")
    match = [match] if isinstance(match, str) else [str(m) for m in (match or []) if str(m).strip()]
    queries = s.get("queries")
    queries = [queries] if isinstance(queries, str) else [str(q) for q in (queries or []) if str(q).strip()]
    dates = []
    for d in s.get("dates") or []:
        if not isinstance(d, dict) or not _date(d.get("date")):
            problems.append(f"pokemon section \"{name}\": date {d!r} should look like "
                            f"{{\"date\": \"2026-11-06\", \"what\": \"...\"}}; skipped")
            continue
        kind = str(d.get("kind") or "release")
        drop = bool(d.get("drop", False))
        dates.append({"date": str(d["date"]), "what": str(d.get("what") or "release day"), "kind": kind,
                      "drop": drop, "ping": bool(d.get("ping", drop)), "eve": bool(d.get("eve", drop)),
                      "time": _hhmm(d.get("time"), MORNING)})
    mx = {}
    for k, v in (s.get("max") or {}).items() if isinstance(s.get("max"), dict) else []:
        t, n = _type_name(k), _num(v)
        if t and n is not None:
            mx[t] = n
    return {"name": name, "slug": slugify(s.get("slug") or name), "code": str(s.get("code") or ""),
            "emoji": str(s.get("emoji") or "⚡"), "match": match, "queries": queries or list(match),
            "channel": bool(s.get("channel", bool(match))), "dates": sorted(dates, key=lambda d: d["date"]),
            "max": mx, "note": str(s.get("note") or ""), "enabled": s.get("enabled", True) is not False}


def _type_name(k):
    """'etb' / 'Elite Trainer Box' / 'elite-trainer-box' -> 'Elite Trainer Box' (None if unknown)."""
    sq = _squash(k)
    aliases = {"etb": "Elite Trainer Box", "pcetb": "Pokémon Center ETB", "pokemoncenteretb": "Pokémon Center ETB",
               "box": "Booster box", "boosterbox": "Booster box", "bundle": "Booster bundle", "bb": "Build & Battle",
               "buildandbattle": "Build & Battle", "upc": "Ultra-Premium Collection", "pack": "Booster pack",
               "small": "Small collection",
               "minitin": "Mini tin", "deck": "Battle deck"}
    if sq in aliases:
        return aliases[sq]
    for t in TYPES:
        if _squash(t) == sq:
            return t
    return None


def settings(cfg, problems=None):
    """Built-in defaults merged with config.json "pokemon". problems (a list) collects warnings."""
    problems = [] if problems is None else problems
    raw = (cfg or {}).get("pokemon")
    if raw is False:
        return {"enabled": False, "sections": [], "max": dict(DEFAULT_MAX), "watch_types": [], "collections": [],
                "every_minutes": EVERY_MINUTES, "reminders": False, "drop_windows": False, "extra_shops": False,
                "shops": None, "skip_shops": set()}
    if raw is not None and not isinstance(raw, dict):
        problems.append("\"pokemon\" in config.json should be a {...} section (or false); using the defaults")
        raw = {}
    raw = raw or {}
    mx = dict(DEFAULT_MAX)
    for k, v in (raw.get("max") or {}).items() if isinstance(raw.get("max"), dict) else []:
        t, n = _type_name(k), _num(v)
        if t is None:
            problems.append(f"pokemon \"max\": unknown product type \"{k}\" (types: {', '.join(TYPES)})")
        elif n is None or n < 0:
            problems.append(f"pokemon \"max\" for {t} should be a number (it's {v!r})")
        else:
            mx[t] = n
    wt = raw.get("watch_types")
    if isinstance(wt, list):
        types = [t for t in (_type_name(x) for x in wt) if t]
    else:
        types = list(DEFAULT_WATCH_TYPES)
    by_name = {}
    order = []
    for s in DEFAULT_SECTIONS:
        by_name[s["name"].lower()] = dict(s)
        order.append(s["name"].lower())
    for s in raw.get("sections") or [] if isinstance(raw.get("sections"), list) else []:
        if not isinstance(s, dict) or not s.get("name"):
            problems.append(f"pokemon section {s!r} needs a \"name\"; skipped")
            continue
        key = str(s["name"]).lower()
        if key in by_name:
            by_name[key] = {**by_name[key], **s}
        else:
            by_name[key] = dict(s)
            order.append(key)
    sections = [x for x in (_norm_section(by_name[k], problems) for k in order) if x]
    seen, unique = set(), []
    for s in sections:
        if s["slug"] in seen:
            problems.append(f"two pokemon sections are both called \"{s['name']}\"; the second is skipped")
            continue
        seen.add(s["slug"])
        unique.append(s)
    cols = list(DEFAULT_COLLECTIONS) if raw.get("extra_shops", True) is not False else []
    for c in raw.get("collections") or [] if isinstance(raw.get("collections"), list) else []:
        if isinstance(c, dict) and c.get("name") and str(c.get("url", "")).startswith("https://") \
                and "/collections/" in str(c["url"]):
            cols.append({"name": str(c["name"]), "url": str(c["url"])})
        else:
            problems.append(f"pokemon collection {c!r} needs a \"name\" and an https://.../collections/... \"url\"; skipped")
    return {"enabled": raw.get("enabled", True) is not False,
            "every_minutes": max(MIN_EVERY, _num(raw.get("every_minutes")) or EVERY_MINUTES),
            "max": mx, "watch_types": types, "sections": unique, "collections": cols,
            "extra_shops": raw.get("extra_shops", True) is not False,
            "shops": raw.get("shops") if isinstance(raw.get("shops"), list) else None,
            "skip_shops": {str(x).lower() for x in raw.get("skip_shops") or []},
            "reminders": raw.get("reminders", True) is not False,
            "drop_windows": raw.get("drop_windows", True) is not False}


def warnings(cfg):
    problems = []
    settings(cfg, problems)
    return problems


def enabled(cfg):
    pc = settings(cfg)
    return pc["enabled"] and any(s["enabled"] and s["match"] for s in pc["sections"])


def every_minutes(cfg):
    return settings(cfg)["every_minutes"]


def max_for(pc, section, ptype):
    v = section.get("max", {}).get(ptype)
    return float(pc["max"].get(ptype, 0) if v is None else v)


def section_by_slug(cfg, slug):
    return next((s for s in settings(cfg)["sections"] if s["slug"] == slug), None)


# ---------------------------------------------------------------- shops
def shops(cfg, tb, pc=None):
    """[{"name", "kind": "shopify"|"woo", "base"}]: the One Piece shops (one per website) plus the
    Pokémon extras, or "pokemon": {"shops": [...]} if you list your own."""
    pc = pc or settings(cfg)
    out, hosts = [], set()

    def add(name, base, kind):
        host = urllib.parse.urlsplit(base).hostname or ""
        if not host or host in hosts or host in SKIP_HOSTS or str(name).lower() in pc["skip_shops"]:
            return
        hosts.add(host)
        out.append({"name": str(name), "kind": kind, "base": f"https://{host}"})

    if pc["shops"] is not None:
        for s in pc["shops"]:
            if isinstance(s, dict) and s.get("name") and str(s.get("woo") or s.get("base") or "").startswith("https://"):
                add(s["name"], s.get("woo") or s["base"], "woo" if s.get("woo") else "shopify")
    else:
        cols, prods, woo, search = tb.sealed_shops(cfg)
        for s in cols + prods:
            add(s["name"].replace(" (sealed)", ""), s["url"], "shopify")
        for s in search:
            add(s["name"], s["base"], "shopify")
        for s in woo:
            add(s["name"], s["url"], "woo")
        for name, base in ((cfg.get("singles") or {}).get("shops") or {}).items():
            add(name, base, "shopify")
        if pc["extra_shops"]:
            for s in EXTRA_SHOPS:
                add(s["name"], s["base"], "shopify")
    # shops read through their collection feeds instead of their search
    for c in pc["collections"]:
        host = urllib.parse.urlsplit(c["url"]).hostname or ""
        if host in SKIP_HOSTS or c["name"].lower() in pc["skip_shops"]:
            continue
        shop = next((s for s in out if urllib.parse.urlsplit(s["base"]).hostname == host), None)
        if shop is None:
            shop = {"name": c["name"], "kind": "collection", "base": f"https://{host}"}
            hosts.add(host)
            out.append(shop)
        shop["kind"] = "collection"
        shop.setdefault("collections", [])
        if c["url"] not in shop["collections"]:
            shop["collections"].append(c["url"])
    return out


# ---------------------------------------------------------------- checking
class Result:
    """finds: buyable at or under max. listings[(shop, slug)]: everything seen for that release at that
    shop, or None if the shop couldn't be read. sections: the slugs checked. problem: why it failed."""

    def __init__(self):
        self.finds, self.listings, self.sections, self.problem = [], {}, [], None

    @property
    def ok_pairs(self):
        return {k for k, v in self.listings.items() if v is not None}

    def all_listings(self):
        return [l for ls in self.listings.values() for l in (ls or [])]


def _release_note(section, now=None):
    """'out Fri 6 Nov' for a release with one in-store day still to come. Left off when products come out
    on different days (30th Celebration), because the bot can't tell which day a product belongs to."""
    now = now or datetime.now()
    days = [_date(d["date"]) for d in section.get("dates") or [] if d["kind"] == "release"]
    days = [d for d in days if d and d.date() > now.date()]
    return f"out {day_text(days[0])}" if len(days) == 1 else ""


def next_day(section, now=None):
    """(date, entry) of the next in-store day for this release, or None."""
    now = now or datetime.now()
    for d in section.get("dates") or []:
        when = _date(d["date"])
        if when and when.date() >= now.date():
            return when, d
    return None


def _listing(shop, section, handle, title, ptype, price, available, url, cart, preorder, limit):
    note = ", ".join(x for x in (ptype, "pre-order" if preorder else "", _release_note(section)) if x)
    pid = f"poke|{section['slug']}|{shop}|{handle}"
    return {"id": f"plist|{section['slug']}|{shop}|{handle}", "box_id": pid, "poke_id": pid, "group": GAME,
            "game": GAME, "kind": "New listing", "section": section["slug"], "section_name": section["name"],
            "ptype": ptype, "name": title, "shop": shop, "price": round(float(price or 0), 2),
            "available": bool(available), "url": url, "cart": cart, "note": note, "max": limit, "page": 1,
            "preorder": bool(preorder)}


def _find_from(l):
    f = {k: l[k] for k in ("game", "section", "section_name", "ptype", "name", "shop", "price", "url", "cart",
                           "note", "preorder")}
    f.update(id=l["poke_id"], kind="Booster box" if l["ptype"] == "Booster box" else "Sealed")
    return f


def _keep(pc, section, title):
    """(product type) if this title is an English sealed product of this release we watch, else None."""
    if not title or not matches(title, section) or not is_english(title):
        return None
    ptype = product_type(title)
    if ptype not in pc["watch_types"] or is_excluded(title, ptype):
        return None
    return ptype


SEARCH_LIMIT = 10              # a Shopify shop's search returns at most 10 products per query
# When a search comes back full (lots of products for one set, or its singles), the bot searches again
# for each kind of sealed product, so a box or ETB can't get pushed out of the top 10.
CROWDED_WORDS = ["box", "bundle", "collection", "tin", "blister", "deck"]
# Those follow-up searches are reused for 10 minutes, so drop mode (a check every minute) asks each shop
# once or twice a minute, not seven times. The top 10 are always fresh.
FOLLOWUP_EVERY = 10 * 60
_followups = {}                # (shop address, release) -> (time, {handle: product}) in a running bot


def _shopify(tb, pc, shop, section):
    base = shop["base"]
    products, state = {}, {"ok": False, "full": False}

    def take(queries):
        for data in tb.pmap(lambda q: tb.fetch_json(tb._suggest_url(base, q)), queries):
            if not isinstance(data, dict):
                continue
            state["ok"] = True
            items = ((data.get("resources") or {}).get("results") or {}).get("products") or []
            if len(items) >= SEARCH_LIMIT:
                state["full"] = True
            for p in items:
                if p.get("handle"):
                    products.setdefault(p["handle"], p)

    take(section["queries"])
    if not state["ok"]:
        return None
    if state["full"]:
        key = (base, section["slug"])
        hit = _followups.get(key)
        if hit and time.time() - hit[0] < FOLLOWUP_EVERY:
            for h, p in hit[1].items():
                products.setdefault(h, p)            # what this check saw itself wins
        else:
            top = set(products)
            take([f"{section['queries'][0]} {w}" for w in CROWDED_WORDS])
            _followups[key] = (time.time(), {h: p for h, p in products.items() if h not in top})
    rows = []
    for handle, p in products.items():
        title = html.unescape(str(p.get("title") or "")).strip()
        ptype = _keep(pc, section, title)
        if not ptype:
            continue
        price = _num(p.get("price")) or _num(p.get("price_min")) or 0.0
        limit = max_for(pc, section, ptype)
        rows.append((handle, title, ptype, price, bool(p.get("available")), limit,
                     tb.is_preorder(title, p.get("tags", ""))))
    want = [r[0] for r in rows if r[4] and 0 < r[3] <= r[5]]       # cart links only for what will alert
    carts = dict(zip(want, tb.pmap(lambda h: tb.product_js(base, h) or {}, want)))
    out = []
    for handle, title, ptype, price, avail, limit, pre in rows:
        cart = ""
        if handle in carts:
            _, vid = tb.cheapest_available(carts[handle].get("variants"), cents=True)
            cart = tb.shopify_cart_link(base, vid)
        out.append(_listing(shop["name"], section, handle, title, ptype, price, avail,
                            f"{base}/products/{handle}", cart, pre, limit))
    return out


def _read_feeds(tb, shop):
    """{handle: product} from all of a shop's collection feeds, or None if none of them could be read."""
    products, ok = {}, False
    for got, _ in [tb.shopify_collection(u) for u in shop.get("collections") or []]:
        if got is None:
            continue
        ok = True
        for p in got:
            if p.get("handle"):
                products.setdefault(p["handle"], p)
    return products if ok else None


def _collection(tb, pc, shop, section, products):
    """This release's products in a shop's collection feeds (read once per check by _read_feeds)."""
    if products is None:
        return None
    base, out = shop["base"], []
    for handle, p in products.items():
        title = html.unescape(str(p.get("title") or "")).strip()
        ptype = _keep(pc, section, title)
        if not ptype:
            continue
        variants = p.get("variants") or []
        price, vid = tb.cheapest_available(variants, cents=False)
        prices = [x for x in (_num(v.get("price")) for v in variants) if x]
        avail = price is not None
        limit = max_for(pc, section, ptype)
        out.append(_listing(shop["name"], section, handle, title, ptype,
                            price if avail else (min(prices) if prices else 0.0), avail,
                            f"{base}/products/{handle}", tb.shopify_cart_link(base, vid) if avail and vid else "",
                            tb.is_preorder(title, p.get("tags", "")), limit))
    return out


def _woo(tb, pc, shop, section):
    base = shop["base"]
    urls = [f"{base}/wp-json/wc/store/v1/products?search={urllib.parse.quote(q)}&per_page=50"
            for q in section["queries"]]
    results = tb.pmap(tb.fetch_json, urls)
    out, ok, seen = [], False, set()
    for data in results:
        if not isinstance(data, list):
            continue
        ok = True
        for p in data:
            pid = p.get("id")
            if pid in seen:
                continue
            seen.add(pid)
            title = html.unescape(re.sub("<[^>]+>", "", str(p.get("name") or ""))).strip()
            ptype = _keep(pc, section, title)
            if not ptype:
                continue
            prices = p.get("prices") or {}
            try:
                price = int(prices.get("price") or 0) / (10 ** int(prices.get("currency_minor_unit", 2)))
            except (TypeError, ValueError):
                price = 0.0
            buyable = bool(p.get("is_in_stock") and p.get("is_purchasable", True))
            limit = max_for(pc, section, ptype)
            cats = " ".join(str(c.get("name", "")) for c in p.get("categories") or [] if isinstance(c, dict))
            out.append(_listing(shop["name"], section, str(pid), title, ptype, price, buyable,
                                p.get("permalink") or base, tb.woo_cart_link(base, pid) if buyable else "",
                                tb.is_preorder(title, cats), limit))
    return out if ok else None


def check(cfg, tb, only=None):
    """Search every shop for every watched release (or just the slugs in `only`). Never raises."""
    res = Result()
    try:
        pc = settings(cfg)
        if not pc["enabled"]:
            return res
        sections = [s for s in pc["sections"] if s["enabled"] and s["queries"] and (not only or s["slug"] in only)]
        res.sections = [s["slug"] for s in sections]
        shop_list = shops(cfg, tb, pc)
        jobs = [(shop, s) for shop in shop_list for s in sections]
        feeds = {}                       # collection-feed shops: read each feed once, for every release
        feed_shops = [shop for shop in shop_list if shop["kind"] == "collection"] if sections else []
        for shop, got in tb.pmap(lambda sh: (sh, _read_feeds(tb, sh)), feed_shops, leaf=False):
            feeds[shop["name"]] = got

        def run(job):
            shop, s = job
            if shop["kind"] == "collection":
                return job, _collection(tb, pc, shop, s, feeds.get(shop["name"]))
            return job, (_woo if shop["kind"] == "woo" else _shopify)(tb, pc, shop, s)

        for (shop, s), listings in tb.pmap(run, jobs, leaf=False):
            res.listings[(shop["name"], s["slug"])] = listings
            for l in listings or []:
                if l["available"] and 0 < l["price"] <= l["max"]:
                    res.finds.append(_find_from(l))
        seen, uniq = set(), []
        for f in res.finds:
            if f["id"] not in seen:
                seen.add(f["id"])
                uniq.append(f)
        res.finds = uniq
    except Exception as e:  # noqa: BLE001  (a surprise here must never stop the One Piece checks)
        print(f"   ! Pokémon check: unexpected {type(e).__name__}: {e}")
        res.problem = f"{type(e).__name__}: {e}"
        res.finds, res.listings = [], {}
    n_ok = len(res.ok_pairs)
    if res.sections:
        print(f"   (Pokémon: {len(res.finds)} buyable within your max, {len(res.all_listings())} listing(s) seen, "
              f"{n_ok}/{len(res.listings)} shop searches answered)")
    return res


def known_key(shop, slug):
    return f"{shop} (pokemon:{slug})"


def new_listings(res, known, finds_ids=()):
    """Listings never seen before for that release at that shop. The first good read of a shop for a
    release only remembers what's there (no alerts), so new sections and new shops don't flood."""
    out = []
    finds_ids = set(finds_ids)
    for (shop, slug), listings in res.listings.items():
        if listings is None:
            continue
        key = known_key(shop, slug)
        ids = {l["id"] for l in listings}
        if key not in known:
            known[key] = sorted(ids)
            continue
        before = set(known[key])
        for l in listings:
            if l["id"] in before or l["poke_id"] in finds_ids:
                continue
            status = "in stock" if l["available"] else ("not buyable yet" if l["preorder"]
                                                        else "listed, not buyable yet")
            if l["available"] and l["max"] and l["price"] > l["max"]:
                status += f" (over your ${l['max']:,.0f} max)"
            out.append(dict(l, note=(l["note"] + " · " if l["note"] else "") + status))
        known[key] = sorted(before | ids)
    return out


# ---------------------------------------------------------------- Discord
def hooks(alerts):
    """{"<slug>" | "restocks" | "in-store": webhook link} from "pokemon_webhooks" (a dict, or the
    JSON text the cloud copy gets from the POKEMON_WEBHOOKS secret)."""
    raw = (alerts or {}).get("pokemon_webhooks")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if isinstance(v, str) and v.startswith("https://")}


def hook_for(alerts, slug):
    h = hooks(alerts)
    return h.get(slug) or h.get("restocks") or h.get("default")


def instore_hook(alerts):
    h = hooks(alerts)
    return h.get("in-store") or h.get("instore") or h.get("restocks") or h.get("default")


def ping(alerts):
    return str((alerts or {}).get("pokemon_ping") or "").strip()


def bot_name(alerts):
    name = str((alerts or {}).get("bot_name") or "")
    if "one piece" in name.lower():
        return re.sub(r"(?i)one piece", "Pokémon", name)
    return "Pokémon Restock" + (" (cloud)" if "cloud" in name.lower() else "")


def embed_extras(f):
    """(icon, colour, extra fields) for a Pokémon find or listing in an alert."""
    fields = []
    if f.get("ptype"):
        fields.append({"name": "Type", "value": f["ptype"], "inline": True})
    if f.get("section_name"):
        fields.append({"name": "Set", "value": f["section_name"], "inline": True})
    icon = TYPE_ICON.get(f.get("ptype"), "⚡")
    return icon, YELLOW, fields


# ---------------------------------------------------------------- release calendar and in-store posts
def release_days(cfg, now=None, days=120, past=0):
    """[(date, [(section, date entry)])] for in-store days from `past` days ago to `days` ahead."""
    now = now or datetime.now()
    by_day = {}
    for s in settings(cfg)["sections"]:
        if not s["enabled"]:
            continue
        for d in s["dates"]:
            when = _date(d["date"])
            delta = (when.date() - now.date()).days
            if -past <= delta <= days:
                by_day.setdefault(d["date"], []).append((s, d))
    return [(_date(k), v) for k, v in sorted(by_day.items())]


def calendar_lines(cfg, now=None, days=120):
    """Lines for /pokemon releases, /drops and the recap: one per release day, then sets with no date yet."""
    now = now or datetime.now()
    out = []
    for when, items in release_days(cfg, now, days):
        n = (when.date() - now.date()).days
        tail = " (today!)" if n == 0 else (" (tomorrow)" if n == 1 else f" · in {n} days")
        what = "; ".join(f"{s['emoji']} **{s['name']}**" + (" prerelease" if d["kind"] == "prerelease" else "")
                         + f": {d['what']}" for s, d in items)
        out.append((when, f"📅 **{day_text(when)}**{tail}\n{what}"))
    for s in settings(cfg)["sections"]:
        if s["enabled"] and not s["dates"] and s["note"]:
            out.append((now + timedelta(days=days + 1), f"🔜 {s['emoji']} **{s['name']}**: {s['note']}"))
    return out


def short_calendar(cfg, now=None, days=14):
    """[(date, one line)] for the daily recap's "next 14 days"."""
    now = now or datetime.now()
    out = []
    for when, items in release_days(cfg, now, days):
        n = (when.date() - now.date()).days
        names = ", ".join(dict.fromkeys(s["name"] + (" prerelease" if d["kind"] == "prerelease" else "")
                                        for s, d in items))
        out.append((when, f"⚡ **{day_text(when)}** Pokémon: {names}" + (" (today!)" if n == 0 else f" (in {n} days)")))
    return out


def _at(day, hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    return day.replace(hour=h, minute=m, second=0, microsecond=0)


def reminders_due(cfg, status, now=None):
    """In-store posts that are due now and haven't gone out: [{"key", "embed", "ping"}]."""
    pc = settings(cfg)
    if not pc["enabled"] or not pc["reminders"]:
        return []
    now = now or datetime.now()
    sent = status.get("pokemon_reminders") or {}
    out = []
    for when, items in release_days(cfg, now, days=1, past=0):
        day = when
        # evening before: for days with a release that gets drop mode
        if any(d["eve"] for _, d in items):
            start, until = _at(day - timedelta(days=1), EVENING), _at(day - timedelta(days=1), EVENING_UNTIL)
            key = f"{day:%Y-%m-%d}|eve"
            if start <= now < until and key not in sent:
                out.append({"key": key, "ping": False, "due": start, "embed": _embed(day, items, "eve")})
        start = _at(day, min(d["time"] for _, d in items))
        key = f"{day:%Y-%m-%d}|day"
        if start <= now < _at(day, MORNING_UNTIL) and key not in sent:
            out.append({"key": key, "ping": any(d["ping"] for _, d in items), "due": start,
                        "embed": _embed(day, items, "day")})
    return out


def recently_sent(status, seconds=1800, now=None):
    """Release-day posts this copy made (or knows were made) in the last half hour."""
    now = (now or datetime.now()).timestamp()
    return sorted(k for k, t in (status.get("pokemon_reminders") or {}).items() if now - (_num(t) or 0) < seconds)


def mark_sent(status, key, now=None):
    now = now or datetime.now()
    sent = status.setdefault("pokemon_reminders", {})
    sent[key] = round(now.timestamp())
    cutoff = now.timestamp() - REMINDER_KEEP_DAYS * 86400
    for k in [k for k, t in sent.items() if (_num(t) or 0) < cutoff]:
        sent.pop(k)


def _embed(day, items, which):
    lines = [f"{s['emoji']} **{s['name']}**" + (f" ({s['code']})" if s["code"] else "") + f": {d['what']}"
             for s, d in items]
    prerelease_only = all(d["kind"] == "prerelease" for _, d in items)
    if which == "eve":
        title = f"🛒 Tomorrow in stores · {day_text(day)}"
        foot = ("Most stores put new stock out from opening, but each store does its own thing and quantities "
                "are limited. The PC copy checks the online shops every minute tonight (6pm–midnight) and "
                "tomorrow 7am–1pm.")
    elif prerelease_only:
        title = f"🎟️ Prerelease today · {day_text(day)}"
        foot = "Prerelease stock is at local game stores running events, not the big chains."
    else:
        title = f"📍 Out today in stores · {day_text(day)}"
        foot = ("Each store puts stock out on its own schedule and quantities are usually limited, so not every "
                "store will have it on day one. Seen some on a shelf? `/pokemon report` pings everyone here.")
    return {"title": title, "description": "\n".join(lines) + "\n\n" + foot, "color": YELLOW}


# ---------------------------------------------------------------- drop mode
def auto_windows(cfg):
    """Drop-mode windows for release days with "drop": the evening before (6pm-midnight) and that
    morning (7am-1pm), every 60 seconds, checking only the releases out that day."""
    if cfg.get("auto_drop_windows", True) is False:
        return []
    pc = settings(cfg)
    if not pc["enabled"] or not pc["drop_windows"]:
        return []
    out = []
    for when, items in release_days(cfg, datetime.now(), days=400, past=1):
        drops = [s for s, d in items if d["drop"] and s["queries"]]
        if not drops:
            continue
        slugs = sorted({s["slug"] for s in drops})
        names = " + ".join(dict.fromkeys(s["name"] for s in drops))
        out.append({"name": f"{names} eve (auto)", "start": _at(when - timedelta(days=1), EVENING),
                    "end": _at(when - timedelta(days=1), "23:59"), "every": 60, "sealed_only": True,
                    "games": [GAME], "sections": slugs})
        out.append({"name": f"{names} release day (auto)", "start": _at(when, MORNING), "end": _at(when, MORNING_UNTIL),
                    "every": 60, "sealed_only": True, "games": [GAME], "sections": slugs})
    return out


# ---------------------------------------------------------------- first post in a new channel
def intro_posts(cfg, res, status, alerts):
    """For each release channel that's just been set up: one post (no ping) listing what the shops have
    for it right now, so the channel doesn't start empty. [(slug, hook, embed)]"""
    done = status.get("pokemon_intro") or {}
    h = hooks(alerts)
    out = []
    for s in settings(cfg)["sections"]:
        slug = s["slug"]
        if not s["enabled"] or slug not in res.sections or slug not in h or done.get(slug):
            continue
        rows = [l for (shop, sl), ls in res.listings.items() if sl == slug for l in (ls or [])]
        if not any(sl == slug and ls is not None for (_, sl), ls in res.listings.items()):
            continue
        buy = sorted([l for l in rows if l["available"] and 0 < l["price"] <= l["max"]], key=lambda l: l["price"])
        pre = sorted([l for l in rows if not l["available"]], key=lambda l: (l["ptype"], l["price"]))
        over = sorted([l for l in rows if l["available"] and not (0 < l["price"] <= l["max"])], key=lambda l: l["price"])

        def line(l, mark):
            return (f"{mark} [{l['name'][:60]}]({l.get('cart') or l['url']}) **${l['price']:,.2f}** · {l['shop']}"
                    if l["price"] else f"{mark} [{l['name'][:60]}]({l['url']}) · {l['shop']}")

        fields = []
        for name, items, mark, empty in (
                (f"✅ Buyable now within your max ({len(buy)})", buy, "✅", "Nothing yet."),
                (f"⏳ Listed, not buyable yet ({len(pre)})", pre, "⏳", "None."),
                (f"▫️ In stock over your max ({len(over)})", over, "▫️", None)):
            if items or empty:
                val = "\n".join(line(l, mark) for l in items[:10]) or empty
                if len(items) > 10:
                    val += f"\n…and {len(items) - 10} more"
                fields.append({"name": name, "value": val[:1020]})
        out.append((slug, h[slug], {
            "title": f"{s['emoji']} {s['name']}: what the shops have right now"[:256], "color": YELLOW,
            "description": (f"{s['note']}\n" if s["note"] else "")
            + "This channel gets every new listing and pre-order for this release, and an alert whenever "
              "something is buyable at or under your max. Release-day posts go in #pokemon-in-store.",
            "fields": fields}))
    return out


def mark_intro(status, slug):
    status.setdefault("pokemon_intro", {})[slug] = round(time.time())


# ---------------------------------------------------------------- try it by hand
if __name__ == "__main__":
    import sys
    sys.exit("Run the bot instead:  py -3 tcg_bot.py --pokemon --all --dry-run   (prints what it finds, posts nothing)")
