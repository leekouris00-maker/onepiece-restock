"""
Deterministic mock shop data for the benchmarks and tests.

Built from the bot's own real data in this repo - recap.json (every box / watched listing the cloud
copy saw on 14 Oct 2026, with real titles, handles, prices and stock) and known_products.json - and
padded with filler products so each shop's catalogue and payload size look like the real thing
(a real Shopify products.json product is roughly 3-6 KB once body_html, variants and images are in).

Nothing here touches the network.
"""
import hashlib
import json
import os
import random
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# shop name -> (host, collection handle, filler products to add)
COLLECTIONS = {
    "Gumnut": ("www.gumnut.com.au", "one-piece-card-game", 90),
    "Good Games (sealed)": ("shop.goodgames.com.au", "one-piece-card-game", 110),
    "Gameology": ("www.gameology.com.au", "one-piece-card-game", 150),
    "TCGroup": ("www.tcgroupau.com.au", "one-piece-booster-box", 30),
    "Pokebox": ("www.pokebox.com.au", "one-piece-card-game-booster-boxes-english", 290),
    "Pocket Games": ("pocketgames.com.au", "one-piece-tcg-cards", 200),
    "Alpha Gaming": ("alphagaming.com.au", "one-piece-sealed-products", 60),
}
SEARCH_SHOPS = {
    "Grailborne": "grailborne.com.au",
    "Collectible Madness": "collectiblemadness.com.au",
    "Friendly Collectibles": "friendlycollectibles.com.au",
}
WOO = {"JToys": "www.jtoys.com.au", "M-G": "www.m-g.com.au"}
SINGLES = {
    "Elemental Arcade": "elementalarcade.com.au",
    "Mayhem": "www.mayhemcollectables.com.au",
    "Good Games": "tcg.goodgames.com.au",
}
OTHER_HOSTS = ["raw.githubusercontent.com", "discord.com", "ntfy.sh"]

POKEBOX_EB05 = "one-piece-card-game-extra-booster-heroines-edition-vol-2-eb-05-booster-box-english"

# Hosts that refuse the bot the way the real ones did on 13-14 Oct 2026 (status.json: shop_down)
REFUSE = {"www.mayhemcollectables.com.au": 401, "www.jtoys.com.au": 403}

SETS = [("OP-01", "Romance Dawn"), ("OP-02", "Paramount War"), ("OP-03", "Pillars of Strength"),
        ("OP-04", "Kingdoms of Intrigue"), ("OP-05", "Awakening of the New Era"),
        ("OP-06", "Wings of the Captain"), ("OP-07", "500 Years in the Future"), ("OP-08", "Two Legends"),
        ("OP-09", "Emperors in the New World"), ("OP-10", "Royal Blood"), ("OP-11", "A Fist of Divine Speed"),
        ("OP-12", "Legacy of the Master"), ("OP-13", "Carrying On His Will"), ("OP-14", "The Azure Sea's Seven"),
        ("OP-15", "Adventure on Kami's Island"), ("OP-16", "The Time of Battle")]
CHARACTERS = ["Monkey.D.Luffy", "Roronoa Zoro", "Nami", "Usopp", "Sanji", "Tony Tony.Chopper", "Nico Robin",
              "Franky", "Brook", "Jinbe", "Trafalgar Law", "Eustass\"Captain\"Kid", "Shanks", "Kaido",
              "Charlotte Linlin", "Boa Hancock", "Yamato", "Portgas.D.Ace", "Sabo", "Koby", "Buggy", "Crocodile"]
ACCESSORY = ["Dragon Shield Matte Sleeves - {c}", "Ultra Pro One Piece Playmat - {c}", "Deck Box - {c}",
             "One Piece Card Game Official Sleeves - {c}", "Card Binder 9-Pocket - {c}"]


def _rng(*key):
    return random.Random(int(hashlib.sha256("|".join(map(str, key)).encode()).hexdigest()[:12], 16))


def _id(*key):
    return int(hashlib.sha256("|".join(map(str, key)).encode()).hexdigest()[:13], 16) % 9_000_000_000_000 + 1_000_000_000_000


def _body(title, extra, rng, n=None):
    """Product description HTML of a realistic length (Shopify returns it in products.json)."""
    n = n or rng.randint(900, 2600)
    words = ("Bandai official English product. Each booster pack contains 12 cards. "
             "Strategy, collection and gameplay for the One Piece Card Game. "
             "Ships in protective packaging. Pre-orders ship on release day. Limit per customer applies. "
             ).split()
    out, size = [f"<p><strong>{title}</strong></p>", f"<p>{extra}</p>"], 0
    while size < n:
        para = " ".join(rng.choice(words) for _ in range(rng.randint(25, 60)))
        out.append(f"<p>{para}</p>")
        size += len(para) + 7
    return "".join(out)


def slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")


def shopify_product(host, title, handle, price, available, rng, tags=(), product_type="Sealed",
                    variants=None, body_extra=""):
    pid = _id(host, handle)
    stamp = "2026-09-%02dT10:%02d:00+10:00" % (rng.randint(1, 28), rng.randint(0, 59))
    if variants is None:
        variants = [("Default Title", price, available)]
    vs = []
    for i, (vt, vp, va) in enumerate(variants, 1):
        vs.append({"id": _id(host, handle, vt), "title": vt, "option1": vt, "option2": None, "option3": None,
                   "sku": f"{slug(handle)[:18].upper()}-{i}", "requires_shipping": True, "taxable": True,
                   "featured_image": None, "available": bool(va), "price": f"{vp:.2f}", "grams": 1100,
                   "compare_at_price": None, "position": i, "product_id": pid, "created_at": stamp,
                   "updated_at": stamp})
    images = [{"id": _id(host, handle, "img", k), "created_at": stamp, "position": k, "updated_at": stamp,
               "product_id": pid, "variant_ids": [],
               "src": f"https://cdn.shopify.com/s/files/1/0{pid % 997:03d}/{pid % 8191:04d}/files/{handle}-{k}.jpg?v=17{pid % 99999999:08d}",
               "width": 1200, "height": 1200} for k in range(1, rng.randint(2, 4))]
    return {"id": pid, "title": title, "handle": handle, "body_html": _body(title, body_extra, rng),
            "published_at": stamp, "created_at": stamp, "updated_at": stamp, "vendor": "Bandai",
            "product_type": product_type, "tags": list(tags), "variants": vs, "images": images,
            "options": [{"name": "Title", "position": 1, "values": [v[0] for v in variants]}]}


def product_js(p):
    """Shopify Ajax API shape (/products/<handle>.js): prices in cents, tags as a list."""
    cents = [int(round(float(v["price"]) * 100)) for v in p["variants"]]
    return {"id": p["id"], "title": p["title"], "handle": p["handle"], "description": p["body_html"],
            "published_at": p["published_at"], "created_at": p["created_at"], "vendor": p["vendor"],
            "type": p["product_type"], "tags": p["tags"], "price": min(cents), "price_min": min(cents),
            "price_max": max(cents), "available": any(v["available"] for v in p["variants"]),
            "price_varies": len(set(cents)) > 1, "compare_at_price": None,
            "variants": [{"id": v["id"], "title": v["title"], "option1": v["option1"], "option2": None,
                          "option3": None, "sku": v["sku"], "requires_shipping": True, "taxable": True,
                          "featured_image": None, "available": v["available"],
                          "name": f"{p['title']} - {v['title']}", "public_title": v["title"],
                          "options": [v["title"]], "price": c, "weight": 1100, "compare_at_price": None,
                          "inventory_management": "shopify", "barcode": ""} for v, c in zip(p["variants"], cents)],
            "images": [i["src"] for i in p["images"]], "featured_image": p["images"][0]["src"] if p["images"] else None,
            "options": p["options"], "url": f"/products/{p['handle']}"}


def suggest_result(p):
    """Predictive Search product shape (prices as dollar strings; variants omitted when the query
    doesn't match a variant title, as Shopify documents)."""
    prices = [float(v["price"]) for v in p["variants"]]
    avail = [float(v["price"]) for v in p["variants"] if v["available"]]
    return {"available": bool(avail), "body": p["body_html"][:600], "compare_at_price_max": "0.00",
            "compare_at_price_min": "0.00", "handle": p["handle"], "id": p["id"],
            "image": p["images"][0]["src"] if p["images"] else None,
            "price": f"{(min(avail) if avail else min(prices)):.2f}", "price_max": f"{max(prices):.2f}",
            "price_min": f"{(min(avail) if avail else min(prices)):.2f}", "tags": p["tags"], "title": p["title"],
            "type": p["product_type"], "url": f"/products/{p['handle']}?_pos=1&_sid=x&_ss=r", "vendor": p["vendor"]}


# ----------------------------------------------------------------------------- singles
def _card_catalogue():
    """(num, list of (title_elemental, handle_elemental, title_gg, handle_gg, variants, number_in_body))."""
    cards = {
        "OP13-120": ("Sabo", "Carrying On His Will", [
            ("", "sp", 2.75, False), ("Parallel", "parallel", 10.30, False), ("Wanted Poster", "wanted-poster", 95.0, True),
            ("Red Super Alternate Art", "red-super-alternate-art", 480.0, True)]),
        "PRB02-014": ("Sabo", "Premium Booster -The Best- Vol. 2", [
            ("", "", 3.15, True), ("Parallel", "parallel", 9.0, True)]),
        "OP05-015": ("Belo Betty", "Awakening of the New Era", [
            ("", "", 0.50, True), ("Reprint", "reprint", 0.50, True), ("Jolly Roger Foil", "jolly-roger-foil", 0.65, True),
            ("Alternate Art", "alternate-art", 6.0, True)]),
        "OP13-016": ("Monkey.D.Garp", "Carrying On His Will", [("", "", 0.55, True), ("Parallel", "parallel", 4.0, False)]),
        "OP05-021": ("Revolutionary Army HQ", "Awakening of the New Era", [
            ("", "", 0.35, True), ("Reprint", "reprint", 0.35, True), ("Pirate Foil", "pirate-foil", 0.35, True)]),
    }
    # Other cards that share a name, so name searches return lookalikes the bot must reject by number
    lookalikes = {
        "Monkey.D.Garp": [("OP02-121", "Paramount War"), ("ST17-004", "Starter Deck Blue Donquixote"),
                          ("OP09-014", "Emperors in the New World"), ("OP06-026", "Wings of the Captain"),
                          ("EB02-031", "Anime 25th Collection"), ("OP11-007", "A Fist of Divine Speed"),
                          ("P-061", "Promotion"), ("OP03-038", "Pillars of Strength")],
        "Belo Betty": [("OP05-002", "Awakening of the New Era (Leader)"), ("OP10-097", "Royal Blood")],
        "Sabo": [("OP04-083", "Kingdoms of Intrigue"), ("P-105", "Promotion"), ("OP13-004", "Carrying On His Will (Leader)"),
                 ("EB01-040", "Memorial Collection"), ("OP07-016", "500 Years in the Future")],
        "Revolutionary Army HQ": [("OP12-099", "Legacy of the Master")],
    }
    return cards, lookalikes


def singles_catalogue(host):
    rng = _rng("singles", host)
    cards, lookalikes = _card_catalogue()
    out = []
    gg = host == "tcg.goodgames.com.au"
    for num, (name, setname, versions) in cards.items():
        n_squash = num.lower().replace("-", "")
        for label, hslug, price, avail in versions:
            if gg:
                title = f"{name}{' (' + label + ')' if label else ''} [{setname}]"
                handle = slug(f"{name} {label} {setname}") + ("-1" if not label else "")
                if num == "OP13-120" and label == "":
                    handle = "sabo-sp-carrying-on-his-will"
                if num == "OP13-120" and label == "Parallel":
                    handle = "sabo-parallel-carrying-on-his-will"
                gg_price = round(price * 1.9 + 0.3, 2)
            else:
                title = f"{name}{' (' + label + ')' if label else ''} - {num} [{setname}]"
                handle = slug(f"{name} {hslug} {n_squash} {setname}")
                gg_price = price
            variants = [("Near Mint", gg_price, avail), ("Lightly Played", round(gg_price * 0.85, 2), avail),
                        ("Moderately Played", round(gg_price * 0.7, 2), False)]
            out.append(shopify_product(host, title, handle, gg_price, avail, rng, tags=["One Piece", "Single", num],
                                       product_type="One Piece Single", variants=variants,
                                       body_extra=f"Card Number: {num} | Rarity: {'SEC' if num.endswith('120') else 'C'}"))
        for lnum, lset in lookalikes.get(name, []):
            title = f"{name} [{lset}]" if gg else f"{name} - {lnum} [{lset}]"
            handle = slug(f"{name} {lnum} {lset}")
            p = rng.choice([0.4, 1.2, 3.5, 8.0, 25.0])
            out.append(shopify_product(host, title, handle, p, rng.random() < 0.6, rng, tags=["One Piece", "Single", lnum],
                                       product_type="One Piece Single",
                                       variants=[("Near Mint", p, True), ("Lightly Played", round(p * 0.85, 2), True)],
                                       body_extra=f"Card Number: {lnum}"))
    # bulk of the singles catalogue (other cards) so search has something to sift through
    for i in range(160):
        ch = rng.choice(CHARACTERS)
        code, sname = rng.choice(SETS)
        num = f"{code.replace('-', '')}-{rng.randint(1, 121):03d}"
        title = f"{ch} [{sname}]" if gg else f"{ch} - {num} [{sname}]"
        p = rng.choice([0.3, 0.5, 1.0, 2.5, 6.0, 15.0])
        out.append(shopify_product(host, title, slug(f"{ch} {num} {sname} {i}"), p, rng.random() < 0.7, rng,
                                   tags=["One Piece", "Single", num], product_type="One Piece Single",
                                   variants=[("Near Mint", p, True)], body_extra=f"Card Number: {num}"))
    return out


# ----------------------------------------------------------------------------- sealed
def _recap_listings():
    with open(os.path.join(REPO, "recap.json"), encoding="utf-8") as f:
        snap = json.load(f)["snapshot"]
    by_shop = {}
    for key, v in snap.items():
        if not key.startswith("list|"):
            continue
        handle = v["url"].rsplit("/products/", 1)[-1]
        by_shop.setdefault(v["shop"], []).append((v["name"], handle, float(v["price"]), bool(v["available"])))
    return by_shop


def _filler(host, n, rng):
    out = []
    for i in range(n):
        kind = rng.random()
        code, sname = rng.choice(SETS)
        if kind < 0.35:
            title = f"One Piece Card Game - {sname} Booster Pack ({code})"
            p = rng.choice([7.95, 8.95, 9.95, 12.0])
        elif kind < 0.55:
            st = rng.choice([f"ST-{n:02d}" for n in range(1, 30)])
            title = f"One Piece Card Game - Starter Deck {st}"
            p = rng.choice([24.95, 29.95, 34.95])
        elif kind < 0.8:
            title = rng.choice(ACCESSORY).format(c=rng.choice(CHARACTERS))
            p = rng.choice([14.95, 19.95, 39.95, 59.95])
        else:
            ch = rng.choice(CHARACTERS)
            title = f"{ch} - {code.replace('-', '')}-{rng.randint(1, 121):03d} [{sname}]"
            p = rng.choice([0.5, 2.0, 9.0, 30.0])
        out.append(shopify_product(host, title, slug(title) + f"-{i}", p, rng.random() < 0.55, rng,
                                   tags=["One Piece"], product_type="Accessory" if "Sleeve" in title else "Sealed"))
    return out


def build(scenario="baseline"):
    """The whole mock internet for one scenario.

    baseline - stock and prices exactly as the cloud copy saw them on 14 Oct 2026 (so nothing new to alert)
    restock  - a few things come back in stock under your max (a box at Gameology and Pokebox, singles at
               Elemental), to exercise the alert path
    """
    recap = _recap_listings()
    shopify = {}          # host -> {"collections": {handle: [products]}, "products": {handle: p}, "index": [p]}
    for shop, (host, coll, n_fill) in COLLECTIONS.items():
        rng = _rng("sealed", host)
        real = []
        for title, handle, price, avail in recap.get(shop, []):
            if scenario == "restock" and shop == "Gameology" and "OP-18" in title:
                avail = True
            if scenario == "restock" and shop == "Pokebox" and "OP-16" in title:
                avail = True
            real.append(shopify_product(host, title, handle, price, avail, rng,
                                        tags=["One Piece", "Booster Box", "pre-order"] if "OP-19" in title else ["One Piece"],
                                        product_type="Booster Box"))
        items = _filler(host, n_fill, rng)
        # spread the real listings through the catalogue (collections aren't sorted by "new")
        for p in real:
            items.insert(rng.randint(0, len(items)), p)
        if host == "www.pokebox.com.au":     # EB-05 sits past the first 250 products (state notes, 13 Oct)
            eb05 = next((p for p in items if p["handle"] == POKEBOX_EB05), None) or shopify_product(
                host, "One Piece Card Game Extra Booster Heroines Edition Vol. 2 (EB-05) Booster Box (English)",
                POKEBOX_EB05, 220.0, False, rng, product_type="Booster Box")
            items = [p for p in items if p["handle"] != POKEBOX_EB05]
            items.insert(min(len(items), 265), eb05)
        h = shopify.setdefault(host, {"collections": {}, "products": {}, "index": []})
        h["collections"][coll] = items
        for p in items:
            h["products"][p["handle"]] = p
        h["index"].extend(items)
    for shop, host in SEARCH_SHOPS.items():
        rng = _rng("search", host)
        items = [shopify_product(host, t, hd, pr, av, rng, product_type="Booster Box")
                 for t, hd, pr, av in recap.get(shop, [])]
        items += _filler(host, 40, rng)
        h = shopify.setdefault(host, {"collections": {}, "products": {}, "index": []})
        for p in items:
            h["products"][p["handle"]] = p
        h["index"].extend(items)
    for shop, host in SINGLES.items():
        items = singles_catalogue(host)
        if scenario == "restock" and host == "elementalarcade.com.au":
            for p in items:
                if p["handle"].startswith("sabo-sp-op13120"):
                    for v in p["variants"]:
                        v["available"] = True
        h = shopify.setdefault(host, {"collections": {}, "products": {}, "index": []})
        for p in items:
            h["products"][p["handle"]] = p
        h["index"].extend(items)
    woo = {"www.m-g.com.au": [
        {"id": 5101, "name": "Pokemon TCG Booster Box - Scarlet &amp; Violet", "permalink": "https://www.m-g.com.au/product/pkm-bb/",
         "is_in_stock": True, "is_purchasable": True,
         "prices": {"price": "21995", "regular_price": "21995", "currency_code": "AUD", "currency_minor_unit": 2}},
        {"id": 5102, "name": "One Piece Card Game Booster Box OP-13 <em>Carrying On His Will</em>",
         "permalink": "https://www.m-g.com.au/product/op13-bb/", "is_in_stock": False, "is_purchasable": True,
         "prices": {"price": "32995", "regular_price": "32995", "currency_code": "AUD", "currency_minor_unit": 2}},
    ]}
    with open(os.path.join(REPO, "recap.json"), "rb") as f:
        raw = {"/leekouris00-maker/onepiece-restock/master/recap.json": f.read()}
    return {"shopify": shopify, "woo": woo, "raw": raw, "refuse": dict(REFUSE)}


def all_hosts():
    hosts = [h for h, _, _ in COLLECTIONS.values()] + list(SEARCH_SHOPS.values()) + list(WOO.values()) \
        + list(SINGLES.values()) + OTHER_HOSTS
    return sorted(set(hosts))


if __name__ == "__main__":
    data = build()
    for host, h in sorted(data["shopify"].items()):
        size = len(json.dumps({"products": h["index"][:250]}).encode())
        print(f"{host:34} {len(h['index']):4} products, first page {size / 1024:7.0f} KB")
