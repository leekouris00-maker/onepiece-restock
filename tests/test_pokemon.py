"""Tests for the Pokémon watch (pokemon_watch.py), how the restock bot runs it, and the channel setup
(add_pokemon_channels.py). No network: shop searches, Discord and the Discord API are all fakes.

Run:  python -m unittest discover -s tests
"""
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
from datetime import datetime
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402
import pokemon_watch as pw  # noqa: E402
import add_pokemon_channels as apc  # noqa: E402

H = "https://discord.com/api/webhooks"
DELTA, THIRTY, RESTOCKS, INSTORE = f"{H}/1/delta", f"{H}/2/thirty", f"{H}/3/restocks", f"{H}/4/instore"
BOXES, SINGLES, STATUS = f"{H}/5/boxes", f"{H}/6/singles", f"{H}/7/status"
POKE_ROLE, OP_ROLE = "<@&999>", "<@&111>"


# ---------------------------------------------------------------- fakes
def sp(handle, title, price, available=True, tags=""):
    """A product as Shopify's search (suggest.json) returns it."""
    return {"handle": handle, "title": title, "price": f"{price:.2f}", "available": available, "tags": tags,
            "vid": 10_000 + sum(map(ord, handle))}


def woo(pid, name, price, in_stock=True):
    return {"id": pid, "name": name, "prices": {"price": str(int(round(price * 100))), "currency_minor_unit": 2},
            "is_in_stock": in_stock, "is_purchasable": True, "permalink": f"https://w.test/product/{pid}/",
            "categories": [{"name": "Pokemon"}]}


class FakeShops:
    """Stands in for tb.fetch_json: Shopify search + product .js, and WooCommerce search, by URL."""

    def __init__(self, shopify=None, woocommerce=None, down=(), feeds=None):
        self.shopify, self.woo, self.down, self.calls = shopify or {}, woocommerce or {}, set(down), []
        self.feeds = feeds or {}           # (host, collection path) -> [products.json products]

    def __call__(self, url, tries=2):
        self.calls.append(url)
        u = urllib.parse.urlsplit(url)
        q = urllib.parse.parse_qs(u.query)
        if u.hostname in self.down:
            tb._note_host(url, False)
            return None
        tb._note_host(url, True)
        if u.path.endswith("/search/suggest.json"):
            words = q["q"][0].lower().split()
            return {"resources": {"results": {"products": [p for p in self.shopify.get(u.hostname, [])
                                                          if all(w in p["title"].lower() for w in words)][:10]}}}
        if u.path.endswith("/products.json"):
            page = int(q.get("page", ["1"])[0])
            items = self.feeds.get((u.hostname, u.path[: -len("/products.json")]))
            return None if items is None else {"products": items[(page - 1) * 250: page * 250]}
        if u.path.startswith("/wp-json/wc/store/v1/products"):
            term = q["search"][0].lower()
            return [p for p in self.woo.get(u.hostname, []) if term in p["name"].lower().replace("&#8211;", "-")]
        if u.path.endswith(".js"):
            handle = u.path.rsplit("/", 1)[-1][:-3]
            for p in self.shopify.get(u.hostname, []):
                if p["handle"] == handle:
                    return {"handle": handle, "variants": [{"id": p["vid"], "available": p["available"],
                                                            "price": int(round(float(p["price"]) * 100))}]}
        return None


def base_cfg(**alerts):
    return {"sealed": {"max_price": 260}, "singles": {"shops": {}, "cards": []}, "alerts": dict(alerts),
            "pokemon": {"shops": [{"name": "ShopA", "base": "https://a.test"},
                                  {"name": "ShopB", "base": "https://b.test"},
                                  {"name": "WooShop", "woo": "https://w.test"}],
                        "extra_shops": False, "reminders": False}}


def stock():
    return FakeShops(
        shopify={
            "a.test": [sp("dr-etb", "Pokemon TCG: Mega Evolution Delta Reign Elite Trainer Box", 120),
                       sp("dr-box", "Delta Reign Booster Box (36 Packs)", 390),
                       sp("dr-bundle", "Delta Reign Booster Bundle [Pre-Order]", 59, available=False, tags="pre-order"),
                       sp("dr-jp", "Delta Reign Booster Box (Japanese)", 150),
                       sp("dr-sleeves", "Delta Reign Card Sleeves", 15),
                       sp("upc-day", "Pokemon TCG: 30th Celebration Ultra-Premium Collection - Day", 449)],
            "b.test": [sp("dr-etb-b", "Delta Reign ETB", 169)],
        },
        woocommerce={"w.test": [woo(77, "Pokemon &#8211; Delta Reign &#8211; Elite Trainer Box", 139, in_stock=False)]})


class Patched(unittest.TestCase):
    """Fake shops in place of the network, and a recorder in place of Discord."""

    def setUp(self):
        self._fetch, self._send, self._out = tb.fetch_json, tb.discord_send, sys.stdout
        sys.stdout = io.StringIO()                   # the bot prints a lot; keep test output readable
        self.sent = []
        tb.discord_send = lambda alerts, hook, payload, tries=3: self.sent.append((hook, payload)) or True
        self.shops = stock()
        tb.fetch_json = self.shops
        pw._followups.clear()
        tb.begin_check({}, {})

    def tearDown(self):
        tb.fetch_json, tb.discord_send, sys.stdout = self._fetch, self._send, self._out

    def hooks_hit(self):
        return [h for h, _ in self.sent]


# ---------------------------------------------------------------- reading product titles
class Filters(unittest.TestCase):
    def test_product_types(self):
        cases = {"Delta Reign Elite Trainer Box": "Elite Trainer Box",
                 "Pokemon Center Elite Trainer Box Delta Reign": "Pokémon Center ETB",
                 "Delta Reign Booster Display Box": "Booster box",
                 "Delta Reign Booster Bundle": "Booster bundle",
                 "Delta Reign Build & Battle Box": "Build & Battle",
                 "30th Celebration Ultra-Premium Collection - Night": "Ultra-Premium Collection",
                 "30th Celebration Mini Tin": "Mini tin",
                 "30th Celebration ex Tin": "Tin",
                 "Delta Reign 3-Pack Blister": "Blister",
                 "30th Celebration Umbreon ex Battle Deck": "Battle deck",
                 "30th Celebration Binder Collection": "Collection",
                 "30th Celebration Sylveon ex Box": "Collection",
                 "Delta Reign Booster Pack": "Booster pack"}
        for title, want in cases.items():
            self.assertEqual(pw.product_type(title), want, title)

    def test_english_sealed_only(self):
        pc = pw.settings({})
        delta = pc["sections"][0]
        keep = lambda t: pw._keep(pc, delta, t)  # noqa: E731
        self.assertEqual(keep("Delta Reign Elite Trainer Box"), "Elite Trainer Box")
        self.assertEqual(keep("Delta Reign Elite Trainer Box (9 packs, 65 card sleeves)"), "Elite Trainer Box")
        for t in ("Delta Reign Booster Box Japanese", "Delta Reign Booster Box (JP)", "Delta Reign Booster Box Korean",
                  "Delta Reign Booster Box Case (6)", "Delta Reign ETB Acrylic Case", "Delta Reign Deck Box",
                  "Delta Reign Card Sleeves", "Delta Reign Booster Pack", "PSA 10 Delta Reign Mega Rayquaza",
                  "Phantasmal Flames Elite Trainer Box"):
            self.assertIsNone(keep(t), t)

    def test_real_titles_from_australian_shops(self):
        """Titles the cloud copy saw on 20 Oct 2026."""
        pc = pw.settings({})
        sec = {s["slug"]: s for s in pc["sections"]}
        singles = ["Gengar Prime 94/102 (ME: 30th Celebration Classic Collection)  - Holofoil",
                   "Arceus VSTAR - 123/172 [ME: 30th Celebration Classic Collection]",
                   "Eevee - 116/128 (30th Celebration) [Blister Exclusives]"]
        for t in singles:
            self.assertIsNone(pw._keep(pc, sec["30th-celebration"], t), t)
        sealed = {"Pokemon – Delta Reign – Booster (Box)": "Booster box",
                  "Pokémon Trading Card Game - Mega Evolution ME06 - Delta Reign - Booster Box - English": "Booster box",
                  "Pokemon TCG: Mega Evolution Delta Reign - Checklane Blister": "Blister",
                  "Pokemon TCG - Delta Reign Build and Battle Box": "Build & Battle",
                  "Pokemon: 30th Celebration Pokemon Center Exclusive Elite Trainer Box (ETB)": "Pokémon Center ETB",
                  "Pokémon TCG: 30th Celebration Poster Collection (Poster Box)": "Small collection",
                  "Pokémon Trading Card Game - 30th Celebration - Tech Sticker Collection [Assorted]": "Small collection",
                  "Pokemon TCG: 30th Celebration Ditto Premium Collection": "Collection",
                  "Pokemon – 30th Celebration – Mini Tin (Single) – Limit 1": "Mini tin",
                  "Pokémon TCG: 30th Celebration 4 Booster Tin (Assorted) (Releases Dec 2026)": "Tin"}
        for t, want in sealed.items():
            slug = "delta-reign" if "Delta" in t else "30th-celebration"
            self.assertEqual(pw._keep(pc, sec[slug], t), want, t)

    def test_singles_shops_are_left_out(self):
        names = [s["name"] for s in pw.shops({"sealed": {"max_price": 1}, "singles": {"shops": {
            "Elemental Arcade": "https://elementalarcade.com.au", "Mayhem": "https://www.mayhemcollectables.com.au",
            "Good Games": "https://tcg.goodgames.com.au"}}}, tb)]
        self.assertFalse({"Elemental Arcade", "Mayhem", "Good Games"} & set(names))

    def test_matching_ignores_case_spaces_and_dashes(self):
        s = {"match": ["Delta Reign"]}
        self.assertTrue(pw.matches("MEGA EVOLUTION - DELTA-REIGN ETB", s))
        self.assertFalse(pw.matches("Chaos Rising ETB", s))


# ---------------------------------------------------------------- settings
class Settings(unittest.TestCase):
    def test_defaults(self):
        pc = pw.settings({})
        self.assertTrue(pc["enabled"])
        self.assertEqual([s["slug"] for s in pc["sections"]], ["delta-reign", "30th-celebration", "me07"])
        me07 = pc["sections"][2]
        self.assertFalse(me07["queries"])          # no English name yet: calendar only, nothing searched
        self.assertFalse(me07["channel"])
        self.assertNotIn("Booster pack", pc["watch_types"])
        self.assertEqual(pc["max"]["Elite Trainer Box"], 160)

    def test_config_changes(self):
        problems = []
        pc = pw.settings({"pokemon": {"max": {"etb": 99, "Booster box": "280", "Nonsense": 5},
                                      "sections": [{"name": "30th Celebration", "enabled": False},
                                                   {"name": "Aura Test", "match": ["Aura Test"], "emoji": "🌟",
                                                    "dates": [{"date": "2027-01-29", "drop": True},
                                                              {"date": "29/01/2027"}]}]}}, problems)
        self.assertEqual(pc["max"]["Elite Trainer Box"], 99)
        self.assertEqual(pc["max"]["Booster box"], 280)
        by = {s["slug"]: s for s in pc["sections"]}
        self.assertFalse(by["30th-celebration"]["enabled"])
        self.assertTrue(by["aura-test"]["enabled"] and by["aura-test"]["channel"])
        self.assertEqual(len(by["aura-test"]["dates"]), 1)
        self.assertTrue(by["aura-test"]["dates"][0]["ping"])          # drop days ping by default
        self.assertTrue(any("Nonsense" in p for p in problems))
        self.assertTrue(any("29/01/2027" in p for p in problems))

    def test_switched_off(self):
        self.assertFalse(pw.enabled({"pokemon": False}))
        self.assertEqual(pw.auto_windows({"pokemon": False}), [])
        cfg = {"sealed": {"max_price": 1}, "singles": {}, "pokemon": False}
        self.assertEqual(tb.check_config(cfg), [])

    def test_bot_config_check_knows_pokemon(self):
        cfg = {"sealed": {"max_price": 260}, "singles": {}, "alerts": {"pokemon_webhooks": json.dumps({"delta-reign": DELTA,
                                                                                                         "x": "nope"})},
               "pokemon": {"max": {"etb": 99}}}
        w = tb.check_config(cfg)
        self.assertFalse(any("unknown setting" in x for x in w))
        self.assertEqual(cfg["alerts"]["pokemon_webhooks"], {"delta-reign": DELTA})   # JSON from GitHub, bad link dropped
        self.assertTrue(any('"x"' in x for x in w))


# ---------------------------------------------------------------- checking the shops
class Checking(Patched):
    def test_finds_and_listings(self):
        res = pw.check(base_cfg(), tb)
        self.assertIsNone(res.problem)
        self.assertEqual(sorted(res.sections), ["30th-celebration", "delta-reign"])
        finds = {f["id"]: f for f in res.finds}
        etb = finds["poke|delta-reign|ShopA|dr-etb"]
        self.assertEqual((etb["kind"], etb["ptype"], etb["price"], etb["game"]), ("Sealed", "Elite Trainer Box", 120.0, "pokemon"))
        self.assertTrue(etb["cart"].startswith("https://a.test/cart/"))
        self.assertIn("poke|30th-celebration|ShopA|upc-day", finds)            # $449 UPC is under the $460 max
        self.assertNotIn("poke|delta-reign|ShopA|dr-box", finds)               # $390 box: over the $360 max
        self.assertNotIn("poke|delta-reign|ShopB|dr-etb-b", finds)             # $169 ETB: over the $160 max
        listed = {l["id"]: l for l in res.all_listings()}
        self.assertIn("plist|delta-reign|ShopA|dr-box", listed)
        self.assertFalse(listed["plist|delta-reign|ShopA|dr-bundle"]["available"])
        self.assertTrue(listed["plist|delta-reign|ShopA|dr-bundle"]["preorder"])
        w = listed["plist|delta-reign|WooShop|77"]
        self.assertEqual(w["name"], "Pokemon – Delta Reign – Elite Trainer Box")   # HTML entities decoded
        self.assertFalse(any("jp" in k or "sleeves" in k for k in listed))

    def test_a_shop_that_doesnt_answer(self):
        self.shops.down.add("b.test")
        res = pw.check(base_cfg(), tb)
        self.assertIsNone(res.listings[("ShopB", "delta-reign")])
        self.assertNotIn(("ShopB", "delta-reign"), res.ok_pairs)
        self.assertIn(("ShopA", "delta-reign"), res.ok_pairs)

    def test_just_the_releases_out_today(self):
        res = pw.check(base_cfg(), tb, only={"delta-reign"})
        self.assertEqual(res.sections, ["delta-reign"])
        self.assertFalse(any("30th" in urllib.parse.unquote(u).lower() for u in self.shops.calls))

    def test_singles_filling_the_search_dont_hide_sealed(self):
        singles = [sp(f"dr-single-{i}", f"Mega Card ex {i}/190 Delta Reign", 4) for i in range(12)]
        self.shops.shopify["b.test"] = singles + [sp("dr-etb-b", "Delta Reign Elite Trainer Box", 119)]
        res = pw.check(base_cfg(), tb, only={"delta-reign"})
        self.assertIn("poke|delta-reign|ShopB|dr-etb-b", {f["id"] for f in res.finds})
        b_calls = [urllib.parse.unquote(u) for u in self.shops.calls if "b.test/search" in u]
        self.assertEqual(len(b_calls), 1 + len(pw.CROWDED_WORDS))
        a_calls = [u for u in self.shops.calls if "a.test/search" in u]
        self.assertEqual(len(a_calls), 1)                  # a shop with a short list: one search

        self.shops.calls.clear()                           # next check (drop mode, a minute later)
        res = pw.check(base_cfg(), tb, only={"delta-reign"})
        self.assertIn("plist|delta-reign|ShopB|dr-etb-b", {l["id"] for l in res.all_listings()})
        self.assertEqual(len([u for u in self.shops.calls if "b.test/search" in u]), 1)   # follow-ups reused

    def test_shop_read_through_its_collection_feeds(self):
        def feed(handle, title, price, available=True):
            return {"handle": handle, "title": title, "tags": ["Pre-Order"] if not available else [],
                    "variants": [{"id": 5000 + len(handle), "price": f"{price:.2f}", "available": available}]}
        self.shops.feeds[("c.test", "/collections/boxes")] = [
            feed("old", "Pokémon TCG Sun & Moon: Unified Minds Booster Box", 300),
            feed("dr-box", "Pokemon TCG: Mega Evolution ME06 - Delta Reign Booster Box", 289, available=False)]
        self.shops.feeds[("c.test", "/collections/etbs")] = [
            feed("dr-etb", "Pokemon TCG: Mega Evolution ME06 - Delta Reign Elite Trainer Box", 115)]
        cfg = base_cfg()
        cfg["pokemon"]["collections"] = [
            {"name": "ShopC", "url": "https://c.test/collections/boxes/products.json?limit=250"},
            {"name": "ShopC", "url": "https://c.test/collections/etbs/products.json?limit=250"}]
        shop = next(s for s in pw.shops(cfg, tb) if s["name"] == "ShopC")
        self.assertEqual((shop["kind"], len(shop["collections"])), ("collection", 2))
        res = pw.check(cfg, tb)
        listed = {l["id"]: l for l in res.all_listings()}
        self.assertTrue(listed["plist|delta-reign|ShopC|dr-box"]["preorder"])
        self.assertFalse(listed["plist|delta-reign|ShopC|dr-box"]["available"])
        etb = next(f for f in res.finds if f["id"] == "poke|delta-reign|ShopC|dr-etb")
        self.assertEqual(etb["cart"], "https://c.test/cart/5006:1")
        self.assertNotIn("plist|delta-reign|ShopC|old", listed)
        feed_calls = [u for u in self.shops.calls if "c.test" in u and "products.json" in u]
        self.assertEqual(len(feed_calls), 2)               # each feed once, shared by both releases
        self.assertFalse([u for u in self.shops.calls if "c.test/search" in u])

    def test_pokebox_is_read_through_its_feeds(self):
        shop = next(s for s in pw.shops({"sealed": {"max_price": 1, "shopify_collections": [
            {"name": "Pokebox", "url": "https://www.pokebox.com.au/collections/x/products.json?limit=250"}]},
            "singles": {}}, tb) if s["name"] == "Pokebox")
        self.assertEqual(shop["kind"], "collection")
        self.assertEqual(len(shop["collections"]), 4)

    def test_never_raises(self):
        def boom(url, tries=2):
            raise RuntimeError("surprise")
        tb.fetch_json = boom
        res = pw.check(base_cfg(), tb)
        self.assertIn("surprise", res.problem)
        self.assertEqual((res.finds, res.listings), ([], {}))

    def test_new_listings_first_read_only_remembers(self):
        known = {}
        res = pw.check(base_cfg(), tb)
        self.assertEqual(pw.new_listings(res, known, {f["id"] for f in res.finds}), [])
        self.assertIn("ShopA (pokemon:delta-reign)", known)
        self.shops.shopify["a.test"].append(sp("dr-bb", "Delta Reign Build & Battle Box", 65))       # over $60: listing
        self.shops.shopify["a.test"].append(sp("dr-blister", "Delta Reign 3 Pack Blister", 30))     # under $35: a find
        res = pw.check(base_cfg(), tb)
        new = pw.new_listings(res, known, {f["id"] for f in res.finds})
        self.assertEqual([l["id"] for l in new], ["plist|delta-reign|ShopA|dr-bb"])
        self.assertIn("over your $60 max", new[0]["note"])


# ---------------------------------------------------------------- Discord
class Routing(Patched):
    def finds(self):
        res = pw.check(base_cfg(), tb)
        return {f["section"]: f for f in res.finds}

    def test_each_release_gets_its_own_channel_and_role(self):
        f = self.finds()
        op_box = {"id": "box|Gumnut|op18", "kind": "Booster box", "name": "OP-18 Booster Box", "shop": "Gumnut",
                  "price": 199.0, "url": "https://g.test/op18", "cart": "", "note": ""}
        alerts = {"discord_webhook_boxes": BOXES, "discord_ping": OP_ROLE, "pokemon_ping": POKE_ROLE,
                  "bot_name": "One Piece Restock (cloud)",
                  "pokemon_webhooks": {"delta-reign": DELTA, "30th-celebration": THIRTY, "restocks": RESTOCKS}}
        ok, delivered = tb.push_discord_detailed({"alerts": alerts}, "t", "b", [f["delta-reign"], f["30th-celebration"], op_box])
        self.assertTrue(ok)
        by = {h: p for h, p in self.sent}
        self.assertEqual(set(by), {DELTA, THIRTY, BOXES})
        self.assertTrue(by[DELTA]["content"].startswith(POKE_ROLE))
        self.assertNotIn(OP_ROLE, by[DELTA]["content"])
        self.assertTrue(by[BOXES]["content"].startswith(OP_ROLE))
        self.assertEqual(by[DELTA]["username"], "Pokémon Restock (cloud)")
        self.assertEqual(by[BOXES]["username"], "One Piece Restock (cloud)")
        self.assertEqual(delivered, {f["delta-reign"]["id"], f["30th-celebration"]["id"], op_box["id"]})

    def test_a_release_without_a_channel_uses_the_catch_all(self):
        f = self.finds()
        alerts = {"pokemon_webhooks": {"delta-reign": DELTA, "restocks": RESTOCKS}}
        tb.push_discord_detailed({"alerts": alerts}, "t", "b", [f["30th-celebration"]])
        self.assertEqual(self.hooks_hit(), [RESTOCKS])

    def test_no_pokemon_channels_yet_means_quiet_not_retried(self):
        f = self.finds()
        ok, delivered = tb.push_discord_detailed({"alerts": {"discord_webhook_boxes": BOXES}}, "t", "b",
                                                 [f["delta-reign"]])
        self.assertEqual(self.sent, [])
        self.assertIn(f["delta-reign"]["id"], delivered)

    def test_discord_test_message_reaches_pokemon_channels(self):
        tb.push_discord_detailed({"alerts": {"discord_webhook_boxes": BOXES,
                                             "pokemon_webhooks": {"delta-reign": DELTA, "in-store": INSTORE}}}, "t", "b")
        self.assertEqual(set(self.hooks_hit()), {BOXES, DELTA, INSTORE})

    def test_embed_says_type_and_set(self):
        e = tb._discord_embeds([self.finds()["delta-reign"]])[0]
        names = {x["name"]: x["value"] for x in e["fields"]}
        self.assertEqual((names["Type"], names["Set"]), ("Elite Trainer Box", "Delta Reign"))
        self.assertEqual(e["color"], pw.YELLOW)
        self.assertIn("ETB", tb.report([self.finds()["delta-reign"]], "x").upper() + "ETB")
        self.assertIn("POKÉMON", tb.report([self.finds()["delta-reign"]], "x"))


# ---------------------------------------------------------------- in-store posts and drop mode
class Reminders(unittest.TestCase):
    CFG = {"pokemon": {}}

    def due(self, when, status=None):
        return pw.reminders_due(self.CFG, status or {}, datetime.strptime(when, "%Y-%m-%d %H:%M"))

    def test_release_day_posts(self):
        eve = self.due("2026-11-05 18:30")
        self.assertEqual([(r["key"], r["ping"]) for r in eve], [("2026-11-06|eve", False)])
        self.assertIn("Tomorrow in stores · Fri 6 Nov", eve[0]["embed"]["title"])
        day = self.due("2026-11-06 07:05")
        self.assertEqual([(r["key"], r["ping"]) for r in day], [("2026-11-06|day", True)])
        text = day[0]["embed"]["title"] + day[0]["embed"]["description"]
        self.assertIn("Out today in stores", text)
        self.assertIn("Delta Reign", text)
        self.assertIn("Ultra-Premium", text)
        self.assertEqual(self.due("2026-11-06 06:55"), [])
        self.assertEqual(self.due("2026-11-06 13:30"), [])            # too late in the day: old news

    def test_each_post_goes_once(self):
        status = {}
        r = self.due("2026-11-06 07:05", status)[0]
        pw.mark_sent(status, r["key"], datetime(2026, 11, 6, 7, 5))
        self.assertEqual(self.due("2026-11-06 07:10", status), [])

    def test_prerelease_and_quiet_days(self):
        pre = self.due("2026-10-24 09:10")
        self.assertEqual(len(pre), 1)
        self.assertFalse(pre[0]["ping"])
        self.assertIn("Prerelease today", pre[0]["embed"]["title"])
        self.assertEqual(self.due("2026-10-24 08:00"), [])             # prerelease post is at 9am
        self.assertEqual(self.due("2026-10-29 18:30"), [])             # battle decks: no "tomorrow" post
        decks = self.due("2026-10-30 07:10")
        self.assertEqual(len(decks), 1)
        self.assertFalse(decks[0]["ping"])

    def test_calendar(self):
        lines = [x[1] for x in pw.calendar_lines({}, datetime(2026, 10, 20), 60)]
        self.assertTrue(lines[0].startswith("📅 **Sat 24 Oct**"))
        self.assertTrue(any("ME07" in l for l in lines))


class DropWindows(unittest.TestCase):
    def test_pokemon_release_day_window(self):
        d = tb.active_window({"pokemon": {}}, datetime(2026, 11, 6, 9, 0))
        self.assertEqual(d["games"], ["pokemon"])
        self.assertEqual(sorted(d["sections"]), ["30th-celebration", "delta-reign"])
        self.assertEqual(tb.drop_label(d), "Pokémon")

    def test_overlapping_one_piece_and_pokemon_windows_merge(self):
        cfg = {"pokemon": {}, "drop_windows": [{"name": "OP test", "start": "2026-11-06 08:00",
                                                "end": "2026-11-06 14:00", "every_seconds": 45}]}
        d = tb.active_window(cfg, datetime(2026, 11, 6, 9, 0))
        self.assertEqual(d["games"], ["onepiece", "pokemon"])
        self.assertEqual(d["every"], 45)
        self.assertEqual(tb.drop_label(d), "booster boxes and Pokémon")

    def test_user_window_for_pokemon(self):
        cfg = {"pokemon": False, "drop_windows": [{"name": "Poke", "game": "Pokémon", "start": "2026-12-04 07:00",
                                                   "end": "2026-12-04 09:00"}]}
        d = tb.active_window(cfg, datetime(2026, 12, 4, 8, 0))
        self.assertEqual((d["games"], d["sections"]), (["pokemon"], []))


class Pacing(unittest.TestCase):
    """What run_once checks inside a Pokémon-only drop window."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.paths = {k: getattr(tb, k) for k in ("STATE_PATH", "KNOWN_PATH", "STATUS_PATH", "SNAPSHOT_PATH",
                                                  "HISTORY_PATH", "EVENTS_PATH", "LOG_PATH", "CONTROLS_PATH")}
        for k in self.paths:
            setattr(tb, k, os.path.join(self.tmp, k.lower() + ".json"))
        self._run, self._ebay, self._oi = tb.run_checks_all, tb.ebay_watch, tb.onepiece_instore
        self.calls = []

        def fake(cfg, sealed=True, singles=True, pokemon=True, poke_only=None, sweep=False):
            self.calls.append((sealed, singles, pokemon, poke_only))
            return (([], {}) if sealed else None), ([] if singles else None), (pw.Result() if pokemon else None)
        tb.run_checks_all = fake
        tb.ebay_watch = tb.onepiece_instore = None

    def tearDown(self):
        for k, v in self.paths.items():
            setattr(tb, k, v)
        tb.run_checks_all, tb.ebay_watch, tb.onepiece_instore = self._run, self._ebay, self._oi
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_with(self, status, drop):
        tb.save_status(status)
        old, sys.stdout = sys.stdout, io.StringIO()
        try:
            tb.run_once(base_cfg(), SimpleNamespace(all=False, loop=5, sealed=False, singles=False, pokemon=False), drop)
        finally:
            sys.stdout = old
        return self.calls[-1]

    def test_pokemon_window_leaves_one_piece_at_its_normal_pace(self):
        now = time.time()
        drop = {"name": "DR day", "games": ["pokemon"], "sections": ["delta-reign"], "every": 60, "sealed_only": True,
                "start": datetime.now(), "end": datetime.now()}
        sealed, singles, poke, only = self.run_with({"sealed_ts": now - 60, "singles_ts": 0, "pokemon_ts": now - 60}, drop)
        self.assertFalse(sealed)            # One Piece boxes were checked a minute ago: not due
        self.assertTrue(singles)            # singles aren't paused by a Pokémon window
        self.assertTrue(poke)
        self.assertEqual(only, {"delta-reign"})
        sealed, singles, poke, only = self.run_with({"sealed_ts": now - 400, "singles_ts": now, "pokemon_ts": now - 700}, drop)
        self.assertTrue(sealed)
        self.assertFalse(singles)
        self.assertIsNone(only)             # the full Pokémon check was due

    def test_one_piece_window_unchanged(self):
        drop = {"name": "OP-18", "games": ["onepiece"], "sections": [], "every": 60, "sealed_only": True,
                "start": datetime.now(), "end": datetime.now()}
        sealed, singles, poke, only = self.run_with({"sealed_ts": time.time(), "pokemon_ts": time.time()}, drop)
        self.assertTrue(sealed)
        self.assertFalse(singles)
        self.assertFalse(poke)


# ---------------------------------------------------------------- whole checks, start to finish
class FullRuns(Patched):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.paths = {k: getattr(tb, k) for k in ("STATE_PATH", "KNOWN_PATH", "STATUS_PATH", "SNAPSHOT_PATH",
                                                  "HISTORY_PATH", "EVENTS_PATH", "LOG_PATH", "CONTROLS_PATH",
                                                  "RECAP_PATH", "PICKS_PATH")}
        for k in self.paths:
            setattr(tb, k, os.path.join(self.tmp, k.lower() + ".json"))
        self.saved = {n: getattr(tb, n) for n in ("check_sealed", "check_singles", "ebay_watch", "onepiece_instore", "pc_last_seen",
                                                   "store_locked", "desktop_beep")}
        tb.check_sealed = lambda cfg, sweep=False: ([], {})
        tb.check_singles = lambda cfg: []
        tb.ebay_watch = tb.onepiece_instore = None
        tb.pc_last_seen = lambda cfg: None
        tb.store_locked = lambda host: False
        tb.desktop_beep = lambda: None
        self.args = SimpleNamespace(all=False, loop=None, sealed=False, singles=False, pokemon=False)

    def tearDown(self):
        for k, v in self.paths.items():
            setattr(tb, k, v)
        for n, v in self.saved.items():
            setattr(tb, n, v)
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def run_bot(self, cfg):
        self.sent.clear()
        out, old = io.StringIO(), sys.stdout
        sys.stdout = out
        try:
            tb.run_once(cfg, self.args)
        finally:
            sys.stdout = old
        return out.getvalue()

    def live_cfg(self):
        return base_cfg(discord_webhook_status=STATUS, discord_webhook_boxes=BOXES, pokemon_ping=POKE_ROLE,
                        pokemon_webhooks={"delta-reign": DELTA, "30th-celebration": THIRTY, "restocks": RESTOCKS,
                                          "in-store": INSTORE})

    def test_quiet_until_the_channels_exist_then_no_flood(self):
        quiet = base_cfg(discord_webhook_status=STATUS, discord_webhook_boxes=BOXES)
        self.run_bot(quiet)
        self.assertEqual(self.hooks_hit(), [STATUS])                       # one "Pokémon watch is on, quietly" post
        self.assertIn("quietly", self.sent[0][1]["embeds"][0]["description"])
        seen = tb.load_state()
        self.assertIn("poke|delta-reign|ShopA|dr-etb", seen)               # remembered, so it won't alert later
        self.run_bot(quiet)
        self.assertEqual(self.sent, [])                                    # nothing new, nothing posted

        out = self.run_bot(self.live_cfg())                                # channels are set up
        hit = self.hooks_hit()
        self.assertIn(DELTA, hit)
        self.assertIn(THIRTY, hit)
        intro = next(p for h, p in self.sent if h == DELTA)
        self.assertIn("what the shops have right now", intro["embeds"][0]["title"])
        self.assertNotIn("content", intro)                                 # the intro doesn't ping
        self.assertTrue(any("alerts are live" in p["embeds"][0]["description"] for h, p in self.sent if h == STATUS))
        self.assertEqual(hit.count(DELTA), 1)                              # one summary, not one alert per item
        self.assertIn("nothing new", out)

    def test_restock_and_new_product_alerts(self):
        cfg = self.live_cfg()
        self.run_bot(cfg)                                                  # first run: remember + intro posts
        self.shops.shopify["a.test"].append(sp("dr-bb", "Delta Reign Build & Battle Box", 40))
        self.run_bot(cfg)
        self.assertEqual(self.hooks_hit(), [DELTA])
        p = self.sent[0][1]
        self.assertTrue(p["content"].startswith(POKE_ROLE))
        self.assertIn("Build & Battle", json.dumps(p["embeds"], ensure_ascii=False))

        etb = self.shops.shopify["a.test"][0]
        etb["available"] = False                                           # sells out...
        self.run_bot(cfg)
        self.assertEqual(self.sent, [])
        etb["available"] = True                                            # ...and comes back: alert again
        self.run_bot(cfg)
        self.assertEqual(self.hooks_hit(), [DELTA])
        self.assertIn("Elite Trainer Box", json.dumps(self.sent[0][1]["embeds"], ensure_ascii=False))

    def test_a_shop_that_drops_out_doesnt_realert_when_back(self):
        cfg = self.live_cfg()
        self.run_bot(cfg)
        self.shops.down.add("a.test")
        self.run_bot(cfg)
        self.assertIn("poke|delta-reign|ShopA|dr-etb", tb.load_state())    # kept while the shop was unreadable
        self.shops.down.clear()
        self.run_bot(cfg)
        self.assertEqual([h for h in self.hooks_hit() if h != STATUS], [])

    def fake_reminders(self):
        fake = [{"key": "2026-11-06|day", "ping": True, "due": datetime(2026, 11, 6, 7, 0),
                 "embed": {"title": "📍 Out today in stores · Fri 6 Nov", "description": "x", "color": pw.YELLOW}}]
        real = pw.reminders_due
        pw.reminders_due = lambda cfg, status, now=None: [r for r in fake if r["key"] not in status.get("pokemon_reminders", {})]
        self.addCleanup(setattr, pw, "reminders_due", real)

    def cloud(self, cfg, pc_on, pc_pokemon=False, posted=()):
        cfg["alerts"].update(heartbeat_topic="t", heartbeat_role="listen")
        tb.pc_last_seen = lambda c: (tb.PC_INFO.update(pokemon=pc_pokemon, posted=set(posted))
                                     or (time.time() - 60 if pc_on else None))     # checked in a minute ago
        self.addCleanup(tb.PC_INFO.update, pokemon=False, posted=set())

    def instore_posts(self):
        return [p for h, p in self.sent if h == INSTORE]

    def test_release_day_post_goes_once(self):
        self.fake_reminders()
        cfg = self.live_cfg()
        self.run_bot(cfg)
        posts = self.instore_posts()
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["content"], POKE_ROLE)
        self.run_bot(cfg)
        self.assertEqual(self.instore_posts(), [])

    def test_cloud_waits_while_the_pc_posts_pokemon(self):
        self.fake_reminders()
        cfg = self.live_cfg()
        self.cloud(cfg, pc_on=True, pc_pokemon=True)
        self.run_bot(cfg)
        self.assertEqual(self.instore_posts(), [])
        self.assertNotIn("2026-11-06|day", tb.load_status().get("pokemon_reminders", {}))   # still waiting
        self.cloud(cfg, pc_on=True, pc_pokemon=True, posted=["2026-11-06|day"])          # the PC says it posted
        self.run_bot(cfg)
        self.assertEqual(self.instore_posts(), [])
        self.assertIn("2026-11-06|day", tb.load_status()["pokemon_reminders"])

    def test_cloud_posts_when_the_pc_goes_quiet_before_posting(self):
        self.fake_reminders()
        cfg = self.live_cfg()
        self.cloud(cfg, pc_on=True, pc_pokemon=True)
        self.run_bot(cfg)
        self.cloud(cfg, pc_on=False)
        self.run_bot(cfg)
        self.assertEqual(len(self.instore_posts()), 1)

    def test_cloud_posts_pokemon_if_the_pc_copy_doesnt(self):
        cfg = self.live_cfg()
        self.cloud(cfg, pc_on=True, pc_pokemon=False)      # e.g. the PC still runs the old bot
        self.fake_reminders()
        self.run_bot(cfg)                                  # first run: remembers what's listed
        self.assertEqual(len(self.instore_posts()), 1)
        self.shops.shopify["a.test"].append(sp("dr-bb", "Delta Reign Build & Battle Box", 40))
        self.run_bot(cfg)
        self.assertEqual(self.hooks_hit(), [DELTA])        # posted by the cloud while the PC is on

    def test_cloud_holds_pokemon_finds_while_the_pc_posts_them(self):
        cfg = self.live_cfg()
        self.cloud(cfg, pc_on=True, pc_pokemon=True)
        self.run_bot(cfg)
        self.shops.shopify["a.test"].append(sp("dr-bb", "Delta Reign Build & Battle Box", 40))
        self.run_bot(cfg)
        self.assertEqual(self.sent, [])
        self.assertIn("poke|delta-reign|ShopA|dr-bb", tb.load_status()["held"])

    def test_pc_skips_a_post_the_cloud_already_made(self):
        self.fake_reminders()
        cfg = self.live_cfg()
        cfg["alerts"].update(heartbeat_topic="t")         # PC copy ("send")
        real_repo, real_hb = tb.repo_json, tb.send_heartbeat
        tb.repo_json = lambda c, name, max_age=1800: {"pokemon_reminders": {"2026-11-06|day": 1}} \
            if name == "status.json" else None
        tb.send_heartbeat = lambda *a, **k: None
        self.addCleanup(setattr, tb, "repo_json", real_repo)
        self.addCleanup(setattr, tb, "send_heartbeat", real_hb)
        self.run_bot(cfg)
        self.assertEqual(self.instore_posts(), [])
        self.assertIn("2026-11-06|day", tb.load_status()["pokemon_reminders"])

    def test_heartbeat_says_what_the_pc_does(self):
        cfg = self.live_cfg()
        self.assertEqual(tb.heartbeat_body(cfg, {"pokemon_reminders": {"2026-11-06|day": time.time()}}),
                         "pc-on pokemon r=2026-11-06|day")
        self.assertEqual(tb.heartbeat_body(cfg, {"pokemon_reminders": {"old|day": time.time() - 7200}}), "pc-on pokemon")
        self.assertEqual(tb.heartbeat_body(base_cfg(), {}), "pc-on")              # no Pokémon channels on the PC

    def test_cloud_reads_the_heartbeat(self):
        lines = [{"event": "open"}, {"event": "message", "time": 100, "message": "pc-on pokemon r=a|eve"},
                 {"event": "message", "time": 200, "message": "pc-on pokemon r=a|day,b|day"}]
        real = tb.HTTP.fetch
        tb.HTTP.fetch = lambda *a, **k: "\n".join(json.dumps(x) for x in lines).encode()
        self.addCleanup(setattr, tb.HTTP, "fetch", real)
        read = self.saved["pc_last_seen"]                      # the real one (setUp swaps in a stand-in)
        self.assertEqual(read({"alerts": {"heartbeat_topic": "t"}}), 200)
        self.assertEqual(tb.PC_INFO, {"pokemon": True, "posted": {"a|eve", "a|day", "b|day"}})
        lines[2]["message"] = "pc-on"
        read({"alerts": {"heartbeat_topic": "t"}})
        self.assertFalse(tb.PC_INFO["pokemon"])                                   # the latest message decides
        tb.PC_INFO.update(pokemon=False, posted=set())

    def test_a_shop_taken_off_the_list_is_forgotten(self):
        cfg = self.live_cfg()
        self.run_bot(cfg)
        self.assertIn("poke|delta-reign|ShopA|dr-etb", tb.load_state())
        cfg["pokemon"]["shops"] = [x for x in cfg["pokemon"]["shops"] if x["name"] != "ShopA"]
        self.run_bot(cfg)
        self.assertFalse([k for k in tb.load_state() if k.startswith("poke|") and "|ShopA|" in k])

    def test_snapshot_and_history_include_pokemon(self):
        self.run_bot(self.live_cfg())
        snap = tb.read_json(tb.SNAPSHOT_PATH, {})
        self.assertTrue(any(l["section"] == "delta-reign" for l in snap["pokemon"]["listings"]))
        hist = tb.read_json(tb.HISTORY_PATH, {})
        self.assertIn("poke|delta-reign|ShopA|dr-etb", hist)

    def test_recap_has_a_pokemon_line_and_fits_discord(self):
        self.run_bot(self.live_cfg())
        e = tb.run_recap(self.live_cfg(), now=datetime(2026, 10, 30, 8, 30), post=False, save=False)
        names = [f["name"] for f in e["fields"]]
        self.assertTrue(any(n.startswith("⚡ Pokémon within your max") for n in names))
        soon = next(f["value"] for f in e["fields"] if f["name"].startswith("🗓️"))
        self.assertIn("Pokémon: Delta Reign, 30th Celebration", soon)
        size = len(e["title"]) + len(e.get("description", "")) + sum(len(f["name"]) + len(f["value"]) for f in e["fields"])
        self.assertLess(size, 6000)

    def test_fit_embed_trims_whole_lines(self):
        e = {"title": "t", "fields": [{"name": "a", "value": "\n".join(["x" * 100] * 10)} for _ in range(8)]}
        tb.fit_embed(e)
        size = sum(len(f["name"]) + len(f["value"]) for f in e["fields"])
        self.assertLessEqual(size, tb.EMBED_TOTAL_MAX)
        self.assertTrue(all(v["value"].endswith("…") or len(v["value"]) <= 1009 for v in e["fields"]))


# ---------------------------------------------------------------- the Discord channel setup
class FakeDiscordApi:
    def __init__(self):
        self.roles, self.channels, self.hooks, self.posts, self.n = [], [], {}, [], 100

    def _id(self):
        self.n += 1
        return str(self.n)

    def __call__(self, req, timeout=None):
        url, method = req.full_url, req.get_method()
        body = json.loads(req.data) if req.data else None
        path = urllib.parse.urlsplit(url).path.replace("/api/v10", "")
        out = None
        if path == "/users/@me/guilds":
            out = [{"id": "1", "name": "Lee's One Piece TCG"}]
        elif path == "/guilds/1/roles":
            if method == "POST":
                self.roles.append(dict(body, id=self._id()))
                out = self.roles[-1]
            else:
                out = self.roles
        elif path == "/guilds/1/channels":
            if method == "POST":
                self.channels.append(dict(body, id=self._id()))
                out = self.channels[-1]
            else:
                out = self.channels
        elif path.startswith("/channels/") and path.endswith("/webhooks"):
            cid = path.split("/")[2]
            if method == "POST":
                self.hooks[cid] = [{"id": self._id(), "token": f"tok{cid}", "name": body["name"]}]
            out = self.hooks.get(cid, [])[-1] if method == "POST" else self.hooks.get(cid, [])
        elif path.startswith("/api/webhooks/"):
            self.posts.append((url, body))
            out = {}
        else:
            raise urllib.error.HTTPError(url, 404, "nope", {}, io.BytesIO(b"{}"))
        return FakeResp(json.dumps(out).encode())


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class ChannelSetup(unittest.TestCase):
    def setUp(self):
        self.api, self._open = FakeDiscordApi(), apc._urlopen
        apc._urlopen = self.api
        self.tmp = tempfile.mkdtemp()
        self._paths = (apc.CONFIG_PATH, apc.SECRETS_PATH)
        apc.CONFIG_PATH, apc.SECRETS_PATH = os.path.join(self.tmp, "config.json"), os.path.join(self.tmp, "secrets.json")

    def tearDown(self):
        apc._urlopen = self._open
        apc.CONFIG_PATH, apc.SECRETS_PATH = self._paths
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_makes_role_category_and_a_channel_per_release(self):
        res = apc.setup("token", cfg={}, log=lambda *a: None)
        self.assertEqual(set(res["hooks"]), {"in-store", "restocks", "delta-reign", "30th-celebration"})
        names = [c["name"] for c in self.api.channels]
        self.assertEqual(names[0], apc.CATEGORY)
        for n in ("📍・pokemon-in-store", "⚡・pokemon-restocks", "🐉・delta-reign", "🎂・30th-celebration"):
            self.assertIn(n, names)
        self.assertFalse(any("me07" in n for n in names))
        self.assertTrue(all(c.get("permission_overwrites") for c in self.api.channels if c["type"] == 0))   # read-only
        self.assertEqual(res["ping"], f"<@&{self.api.roles[0]['id']}>")
        self.assertTrue(self.api.roles[0]["mentionable"])
        self.assertEqual(len(self.api.posts), 4)                       # a hello in each new channel

    def test_running_it_again_makes_nothing_new(self):
        first = apc.setup("token", cfg={}, log=lambda *a: None)
        n_channels, n_posts = len(self.api.channels), len(self.api.posts)
        again = apc.setup("token", cfg={}, log=lambda *a: None)
        self.assertEqual(again["created"], [])
        self.assertEqual((len(self.api.channels), len(self.api.posts)), (n_channels, n_posts))
        self.assertEqual(again["hooks"], first["hooks"])

    def test_saves_in_secrets_json(self):
        with open(apc.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"alerts": {"discord_webhook_boxes": BOXES}, "sealed": {}}, f)
        self.assertEqual(apc.save({"delta-reign": DELTA}, POKE_ROLE), "secrets.json")      # made if missing
        sec = json.load(open(apc.SECRETS_PATH, encoding="utf-8"))
        self.assertEqual((sec["pokemon_webhooks"], sec["pokemon_ping"]), ({"delta-reign": DELTA}, POKE_ROLE))
        self.assertNotIn("pokemon_webhooks", json.load(open(apc.CONFIG_PATH, encoding="utf-8"))["alerts"])
        with open(apc.SECRETS_PATH, "w", encoding="utf-8") as f:
            json.dump({"alerts": {"discord_bot_token": "x"}}, f)
        apc.save({"in-store": INSTORE}, POKE_ROLE)
        sec = json.load(open(apc.SECRETS_PATH, encoding="utf-8"))
        self.assertEqual(sec["alerts"]["pokemon_webhooks"], {"in-store": INSTORE})          # same layout as the file
        self.assertEqual(sec["alerts"]["discord_bot_token"], "x")
        vals = apc.github_values({"delta-reign": DELTA}, POKE_ROLE)
        self.assertEqual(json.loads(vals["POKEMON_WEBHOOKS"]), {"delta-reign": DELTA})
        self.assertNotIn(" ", vals["POKEMON_WEBHOOKS"])

    def test_channel_topics_say_whats_next(self):
        topics = {k: t for k, _, t, _ in apc.plan({})}
        self.assertIn("Next in stores:", topics["delta-reign"])


if __name__ == "__main__":
    unittest.main()
