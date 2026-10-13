#!/usr/bin/env python3
"""
One Piece TCG restock bot (Lee's version)
=========================================

Checks Australian shops for:
  1. English One Piece booster boxes in stock (or buyable on pre-order) at or under your max price
  2. Singles on your want list at Elemental Arcade, Mayhem Collectables and Good Games

Only needs Python 3.8+ (no extra installs).

    python tcg_bot.py                 check once, show only NEW finds since last run
    python tcg_bot.py --all           check once, show everything that currently matches
    python tcg_bot.py --loop 30       keep running, check every 30 minutes
    python tcg_bot.py --sealed        only check booster boxes
    python tcg_bot.py --singles       only check singles
    python tcg_bot.py --test-discord  post a test message to your Discord channel and stop

Edit config.json to change the want list, max prices and alerts (phone via ntfy,
and/or a Discord channel via "discord_webhook" under "alerts").

Alert settings can also come from environment variables, which win over config.json.
The cloud copy (GitHub Actions) uses these so the webhooks stay secret:
    DISCORD_WEBHOOK, DISCORD_WEBHOOK_BOXES, DISCORD_WEBHOOK_SINGLES, DISCORD_PING,
    NTFY_TOPIC, BOT_NAME (the name the Discord posts show, e.g. "One Piece Restock (cloud)")

It never buys anything, adds to cart or logs in.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
STATE_PATH = os.path.join(HERE, "seen.json")
LOG_PATH = os.path.join(HERE, "finds.log")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# environment variable -> key in config.json "alerts"
ENV_ALERTS = {
    "DISCORD_WEBHOOK": "discord_webhook",
    "DISCORD_WEBHOOK_BOXES": "discord_webhook_boxes",
    "DISCORD_WEBHOOK_SINGLES": "discord_webhook_singles",
    "DISCORD_PING": "discord_ping",
    "NTFY_TOPIC": "ntfy_topic",
    "BOT_NAME": "bot_name",
}

# Variant words that mean "not the regular print" (used unless a card overrides it)
DEFAULT_EXCLUDE = [
    "alternate art", "alt art", "parallel", "(sp)", " sp ", "manga", "wanted", "full art",
    "treasure", "pre-release", "prerelease", "release event", "japanese", "promotion",
    "championship", "store treasure", "beginners deck", "anniversary", "sp gold", "sp silver",
    "playmat", "jumbo", "signed",
]
BOX_EXCLUDE = ["japanese", "(jp)", " jp ", "asia", "asian", "chinese", "korean",
               "case", "sleeved", "single pack", "booster pack", "display case"]


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
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    print(f"   ! couldn't read {short(url)} ({last})")
    return None


def short(url):
    p = urllib.parse.urlparse(url)
    return p.netloc + p.path


def money(x):
    return f"${x:,.2f}"


def norm(s):
    return " " + re.sub(r"\s+", " ", (s or "").lower()) + " "


def is_excluded(title, words):
    t = norm(title)
    return any(w.lower() in t for w in words)


def card_num_variants(num):
    """OP13-120 -> ['op13-120', 'op13120'] (Elemental sometimes drops the dash in handles)."""
    n = num.lower()
    return [n, n.replace("-", "")]


# ---------------------------------------------------------------- sealed
def shopify_boxes(shop_name, url, max_price):
    data = fetch_json(url)
    out = []
    if not data:
        return out
    for p in data.get("products", []):
        title = p.get("title", "")
        if "booster box" not in title.lower() and "booster display" not in title.lower():
            continue
        if is_excluded(title, BOX_EXCLUDE):
            continue
        variants = p.get("variants", [])
        avail = [v for v in variants if v.get("available")]
        if not avail:
            continue
        price = min(float(v["price"]) for v in avail)
        if price > max_price:
            continue
        base = "https://" + urllib.parse.urlparse(url).netloc
        out.append({
            "id": f"box|{shop_name}|{p.get('handle')}",
            "kind": "Booster box", "name": title, "shop": shop_name, "price": price,
            "url": f"{base}/products/{p.get('handle')}",
            "note": "pre-order" if "pre" in json.dumps(p.get("tags", "")).lower() + title.lower() else "",
        })
    return out


def shopify_product_box(shop_name, url, max_price):
    """A single product .js URL (Shopify prices are in cents here)."""
    p = fetch_json(url)
    if not p:
        return []
    avail = [v for v in p.get("variants", []) if v.get("available")]
    if not avail:
        return []
    price = min(v["price"] for v in avail) / 100
    if price > max_price:
        return []
    return [{"id": f"box|{shop_name}|{p.get('handle')}", "kind": "Booster box", "name": p.get("title"),
             "shop": shop_name, "price": price, "url": url.replace(".js", ""), "note": ""}]


def woo_boxes(shop_name, url, max_price):
    data = fetch_json(url)
    out = []
    if not isinstance(data, list):
        return out
    for p in data:
        name = re.sub("<[^>]+>", "", p.get("name", ""))
        if "one piece" not in name.lower() or "booster box" not in name.lower():
            continue
        if is_excluded(name, BOX_EXCLUDE):
            continue
        if not (p.get("is_in_stock") and p.get("is_purchasable", True)):
            continue
        prices = p.get("prices", {})
        minor = int(prices.get("currency_minor_unit", 2))
        price = int(prices.get("price", 0)) / (10 ** minor)
        if price <= 0 or price > max_price:
            continue
        out.append({"id": f"box|{shop_name}|{p.get('id')}", "kind": "Booster box", "name": name,
                    "shop": shop_name, "price": price, "url": p.get("permalink"), "note": ""})
    return out


def check_sealed(cfg):
    s = cfg["sealed"]
    mx = s["max_price"]
    jobs = []
    for shop in s["shopify_collections"]:
        jobs.append((shopify_boxes, shop["name"], shop["url"], mx))
    for shop in s.get("shopify_products", []):
        jobs.append((shopify_product_box, shop["name"], shop["url"], mx))
    for shop in s.get("woocommerce", []):
        jobs.append((woo_boxes, shop["name"], shop["url"], mx))
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda j: j[0](*j[1:]), jobs))
    finds = [f for r in results for f in r]
    # de-dupe (same product listed twice)
    seen, out = set(), []
    for f in finds:
        if f["id"] not in seen:
            seen.add(f["id"])
            out.append(f)
    return out


# ---------------------------------------------------------------- singles
def suggest(base, q):
    url = (f"{base}/search/suggest.json?q={urllib.parse.quote(q)}"
           f"&resources[type]=product&resources[limit]=10")
    data = fetch_json(url)
    if not data:
        return []
    return data.get("resources", {}).get("results", {}).get("products", [])


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
        out.append(single_find(card, "Elemental Arcade", price, base + "/products/" + p["handle"], title))
    return out


def product_js(base, handle):
    return fetch_json(f"{base}/products/{handle}.js")


def js_matches_number(p, num):
    blob = json.dumps(p).lower()
    return any(n in blob for n in card_num_variants(num))


def nm_price(p):
    """Near-mint available price in dollars (Mayhem/GG .js prices are cents)."""
    avail = [v for v in p.get("variants", []) if v.get("available")]
    if not avail:
        return None
    nm = [v for v in avail if "near mint" in (v.get("title") or "").lower()]
    pick = nm or avail
    return min(v["price"] for v in pick) / 100


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
        price = nm_price(p)
        if price is None or price > card["max"]:
            continue
        out.append(single_find(card, shop_name, price, f"{base}/products/{h}", p.get("title", "")))
    return out


def single_find(card, shop, price, url, title):
    return {"id": f"card|{shop}|{card['num']}|{url.rsplit('/', 1)[-1]}", "kind": "Single",
            "name": f"{card['name']} {card['num']}", "deck": card.get("deck", ""), "qty": card.get("qty", 1),
            "shop": shop, "price": price, "url": url, "note": title, "priority": card.get("priority", False)}


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
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda j: j[0](*j[1:]), jobs))
    return [f for r in results for f in r]


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
    """Post to a Discord channel through a webhook URL (alerts.discord_webhook in config.json).

    One embed per find (up to 10, Discord's limit), so each has a clickable title.
    Falls back to a single text embed when there are no find objects (e.g. the test message).
    """
    alerts = cfg.get("alerts") or {}
    default = alerts.get("discord_webhook")
    boxes_hook = alerts.get("discord_webhook_boxes") or default
    singles_hook = alerts.get("discord_webhook_singles") or default
    if not (default or boxes_hook or singles_hook):
        return False
    if finds is None:  # test message: post to every channel that's set up
        ok = True
        for hook in dict.fromkeys(h for h in (boxes_hook, singles_hook, default) if h):
            ok = _discord_post(alerts, hook, title, [{"title": title[:256], "description": body[:4000],
                                                       "color": 0x2A9D8F}], 0) and ok
        return ok
    # route each find to its channel (boxes vs singles), one message per channel
    groups = {}
    for f in finds:
        hook = boxes_hook if f["kind"] == "Booster box" else singles_hook
        if hook:
            groups.setdefault(hook, []).append(f)
    ok = True
    for hook, group in groups.items():
        n_box = sum(1 for f in group if f["kind"] == "Booster box")
        t = f"{len(group)} new find(s)" + (f", {n_box} box(es)" if n_box else "")
        ok = _discord_post(alerts, hook, t, _discord_embeds(group), max(0, len(group) - 10)) and ok
    return ok


def _discord_embeds(finds):
    embeds = []
    for f in finds[:10]:
        is_box = f["kind"] == "Booster box"
        fields = [{"name": "Price", "value": money(f["price"]), "inline": True},
                  {"name": "Shop", "value": f["shop"], "inline": True}]
        if not is_box:
            fields.append({"name": "Want", "value": f"x{f['qty']}" + (f" ({f['deck']})" if f.get("deck") else ""),
                           "inline": True})
        if f.get("note"):
            fields.append({"name": "Listing", "value": str(f["note"])[:1000], "inline": False})
        embeds.append({
            "title": (("📦 " if is_box else ("⭐ " if f.get("priority") else "🃏 ")) + f["name"])[:256],
            "url": f["url"],
            "color": 0xF4A261 if is_box else (0xE63946 if f.get("priority") else 0x457B9D),
            "fields": fields,
        })
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
    singles = sorted([f for f in finds if f["kind"] == "Single"],
                     key=lambda f: (not f.get("priority"), f["name"], f["price"]))
    lines = []
    if boxes:
        lines.append("BOOSTER BOXES")
        for f in sorted(boxes, key=lambda f: f["price"]):
            lines.append(f"  {f['name']}  {money(f['price'])}  @ {f['shop']} {f['note']}".rstrip())
            lines.append(f"    {f['url']}")
    if singles:
        lines.append("SINGLES")
        for f in singles:
            star = "*" if f.get("priority") else " "
            deck = f" [{f['deck']}]" if f.get("deck") else ""
            lines.append(f" {star}{f['name']} x{f['qty']}{deck}  {money(f['price'])}  @ {f['shop']}")
            lines.append(f"    {f['url']}")
        b = best_single_shop(singles)
        if b and b[1] > 1:
            lines.append(f"  Tip: {b[0]} has {b[1]} of these cards - one order saves shipping.")
    if not lines:
        return f"{label}: nothing new in stock."
    return f"{label}:\n" + "\n".join(lines)


# ---------------------------------------------------------------- main
def run_once(cfg, args):
    stamp = datetime.now().strftime("%a %d %b %Y %I:%M %p")
    print(f"\n=== One Piece restock check - {stamp} ===")
    finds = []
    if not args.singles:
        print(" checking booster boxes...")
        finds += check_sealed(cfg)
    if not args.sealed:
        print(" checking singles...")
        finds += check_singles(cfg)

    state = load_state()
    show = finds if args.all else new_only(finds, state)
    text = report(show, "Everything currently matching" if args.all else "New since last check")
    print("\n" + text)

    # remember what's in stock now (items that sold out drop off, so a restock counts as new)
    save_state({f["id"]: f["price"] for f in finds})

    if show and not args.all:
        desktop_beep()
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"\n--- {stamp} ---\n{text}\n")
        n_box = sum(1 for f in show if f["kind"] == "Booster box")
        title = f"One Piece: {len(show)} new find(s)" + (f", {n_box} box(es)" if n_box else "")
        push_phone(cfg, title, text[:3500])
        # boxes first, then priority singles, so the most important finds fill Discord's 10 slots
        ordered = sorted(show, key=lambda f: (f["kind"] != "Booster box", not f.get("priority"), f["price"]))
        push_discord(cfg, title, text, ordered)


def main():
    ap = argparse.ArgumentParser(description="One Piece TCG restock bot")
    ap.add_argument("--all", action="store_true", help="show everything matching, not just new finds")
    ap.add_argument("--loop", type=float, metavar="MINUTES", help="keep checking every N minutes")
    ap.add_argument("--sealed", action="store_true", help="only booster boxes")
    ap.add_argument("--singles", action="store_true", help="only singles")
    ap.add_argument("--test-discord", action="store_true", help="post a test message to Discord and stop")
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

    if not args.loop:
        run_once(cfg, args)
        return
    print(f"Running every {args.loop:g} minutes. Press Ctrl+C to stop.")
    while True:
        try:
            cfg = load_config()  # pick up edits without restarting
            run_once(cfg, args)
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001
            print(f"   ! check failed: {e}")
        sys.stdout.flush()
        time.sleep(args.loop * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
