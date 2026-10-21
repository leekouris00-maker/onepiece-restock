"""v2.4: every new English One Piece sealed listing alerts (not just booster boxes and the watch list),
the release-code sweep finds pre-orders outside a shop's One Piece section, and "now buyable" alerts
when a listed product opens. Titles are real ones from Gameology and Good Games on 22 Oct 2026.
No network.

Run:  python -m unittest discover -s tests
"""
import os
import sys
import time
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402

WATCH = tb.DEFAULT_SEALED_WATCH
SEALED_HOOK, BOXES = "https://discord.test/sealed", "https://discord.test/boxes"


def product(handle, title, price, available, variant_titles=("Default Title",), tags=()):
    return {"handle": handle, "title": title, "tags": list(tags),
            "variants": [{"id": abs(hash((handle, v))) % 10 ** 14, "title": v, "price": f"{price:.2f}",
                          "available": available} for v in variant_titles]}


class Classify(unittest.TestCase):
    def setUp(self):
        tb.SEALED_OPTS.update(new=True, packs=False)

    def group(self, title, variants=None):
        c = tb.classify(title, WATCH, 260, variants)
        return c[2] if c else None

    def test_products_v23_never_saw_are_now_new_sealed(self):
        for t in ("One Piece Card Game ST-39 Starter Deck", "One Piece Card Game ST-44 Starter Deck",
                  "One Piece Card Game - Tin Pack Set Vol. 3 [TS-03] (Preorder)",
                  "One Piece Card Game Special Goods Set - Former Four Emperors",
                  "ONE PIECE Card Game Premium Card Collection Leader Collection ENG",
                  "One Piece Card Game - Devil Fruits Collection Vol 1 (DF-01)"):
            self.assertEqual(self.group(t), "new", t)

    def test_boxes_and_watch_items_keep_their_groups(self):
        self.assertEqual(self.group("One Piece Card Game OP-18 Booster Box"), "box")
        self.assertEqual(self.group("One Piece Card Game PEB-01 Premium Extra Booster Box"), "box")
        self.assertEqual(self.group("One Piece Card Game Booster Box – TBA [OP-18] (Preorder)"), "box")
        self.assertEqual(self.group("One Piece Card Game DP-13 Double Pack"), "watch")
        self.assertEqual(self.group("One Piece Card Game Starter Deck – TBA - ST-37 (Preorder)"), "watch")

    def test_not_sealed_singles_accessories_foreign_prints_and_packs(self):
        for t in ("One Piece Card Game OP-18 Single Booster Pack",               # packs: off by default
                  "One Piece Card Game - Two Legends OP-08 Booster Pack",
                  "One Piece Card Game Official Sleeves Set 17 (Set of 4)",
                  "One Piece Card Game: Official Playmat – Limited Edition: Vol. 3",
                  "One Piece Card Game Card Case Monkey D. Luffy (Limited Edition)",
                  "One Piece Card Game Storage Box Standard Black",
                  "One Piece Card Game Japanese 3rd Anniversary Set Simplified Chinese Version",
                  "One Piece Card Game Premium Card Collection - Kumamoto Japanese",
                  "One Piece｜OP-16 The Time of Battle Booster Box - JP",
                  "Sabo - OP13-120 [Carrying On His Will] (Starter Deck set)",       # card number: a single
                  "Koala (P-069) Promo Set"):
            self.assertIsNone(self.group(t), t)

    def test_merch_and_stray_singles_from_the_first_cloud_run_are_left_out(self):
        for t in ("Grand Ship Collection Thousand Sunny", "One Piece Grand Ship Collection Baratie",
                  "One Piece - Character Stamp Blind Box", "One Piece Paldolce Collection Vol.1(Ver.B)",
                  "One Piece Battle Record Collection Trafalgar Law",
                  "Mighty Jaxx: Freenys Hidden Dissectibles – One Piece (Wano Arc Edition) Display",
                  "*Pre-order* One Piece - Luffy w/Momonosuke Pop! Premium (ETA October)",
                  "2026 Guarded Cherry Pie One Piece 1-Card Box",
                  "One Piece Card Game - Kaku 003 (Common Alternate Art) - Starter Deck 29: Egghead (ST-29)",
                  "2025 One Piece Premium Card Collection -Best Selection Vol.4 - #070 Nami"):
            self.assertIsNone(self.group(t), t)
        for t in ("One Piece - Premium Card Collection - Uta  (Limit 1 Per Customer)",
                  "One Piece Starter Deck ST-35 : Sabo (Limit 2 Per Customer)",
                  "One Piece Card Game - Tin Pack Set Vol. 3 Display [TS-03] (Preorder)",
                  "One Piece Card Game Double Pack – TBA DP-14",
                  "One Piece Card Game - Gift Box 2023 (GB-01)",
                  "One Piece Card Game Learn Together Deck Set LD-01"):
            self.assertEqual(self.group(t), "new", t)

    def test_a_single_sold_by_condition_is_not_sealed(self):
        self.assertIsNone(self.group("Mr.3(Galdino) - Starter Deck EX: Gear 5",
                                     [{"title": "Near Mint"}, {"title": "Lightly Played"}]))

    def test_packs_on_request_and_switch_off(self):
        tb.SEALED_OPTS.update(packs=True)
        self.assertEqual(self.group("One Piece Card Game OP-18 Single Booster Pack"), "new")
        tb.SEALED_OPTS.update(new=False, packs=False)
        self.assertIsNone(self.group("One Piece Card Game ST-39 Starter Deck"))
        self.assertEqual(self.group("One Piece Card Game OP-18 Booster Box"), "box")   # boxes unchanged


class CollectionAndListings(unittest.TestCase):
    URL = "https://www.gameology.com.au/collections/one-piece-card-game/products.json?limit=250"

    def setUp(self):
        tb.SEALED_OPTS.update(new=True, packs=False)
        self._fetch = tb.fetch_json
        self.page = {"products": [
            product("op18", "One Piece Card Game OP-18 Booster Box", 229.95, False, tags=["ComingSoon", "preorder"]),
            product("st39", "One Piece Card Game ST-39 Starter Deck", 24.95, True, tags=["preorder"]),
            product("sleeves", "One Piece Card Game Official Sleeves Set 17 (Set of 4)", 19.95, True),
        ]}
        tb.fetch_json = lambda url, tries=tb.HTTP_TRIES: self.page if "page=" not in url else {"products": []}
        tb.PAGE_HINTS.clear()

    def tearDown(self):
        tb.fetch_json = self._fetch

    def test_new_sealed_lists_but_never_price_alerts(self):
        finds, listings = tb.shopify_boxes("Gameology", self.URL, 260, WATCH)
        self.assertEqual(finds, [])                                  # ST-39 is in stock, but "new" never buy-alerts
        by = {l["name"]: l for l in listings}
        self.assertEqual(set(by), {"One Piece Card Game OP-18 Booster Box", "One Piece Card Game ST-39 Starter Deck"})
        st = by["One Piece Card Game ST-39 Starter Deck"]
        self.assertEqual((st["group"], st["box_id"], st["max"]), ("new", "item|Gameology|st39", 0.0))
        self.assertIn("pre-order", st["note"])

    def test_first_read_remembers_then_the_next_new_one_alerts_once(self):
        known = {"Gameology": ["list|Gameology|op18"], "Gameology (other sealed)": []}   # a v2.3 memory
        _, listings = tb.shopify_boxes("Gameology", self.URL, 260, WATCH)
        self.assertEqual(tb.new_listings({"Gameology": listings}, known, []), [])          # upgrade: no flood
        self.assertIn("list|Gameology|st39", known["Gameology (all sealed)"])
        self.page["products"].append(product("st44", "One Piece Card Game ST-44 Starter Deck", 24.95, False))
        _, listings = tb.shopify_boxes("Gameology", self.URL, 260, WATCH)
        new = tb.new_listings({"Gameology": listings}, known, [])
        self.assertEqual([l["id"] for l in new], ["list|Gameology|st44"])
        self.assertIn("listed, not buyable yet", new[0]["note"])
        self.assertNotIn("over your", new[0]["note"])                # no max to be over
        self.assertEqual(tb.new_listings({"Gameology": listings}, known, []), [])

    def test_a_shop_with_no_other_sealed_still_alerts_on_its_first_one(self):
        known = {"Gumnut": []}
        tb.new_listings({"Gumnut": []}, known, [])
        self.assertEqual(known.get("Gumnut (all sealed)"), [])
        l = {"id": "list|Gumnut|st39", "box_id": "item|Gumnut|st39", "group": "new", "kind": "New listing",
             "name": "ST-39", "shop": "Gumnut", "price": 25.0, "available": True, "url": "u", "cart": "",
             "note": "", "max": 0.0, "page": 1}
        self.assertEqual(len(tb.new_listings({"Gumnut": [l]}, known, [])), 1)


class Sweep(unittest.TestCase):
    GG = "https://shop.goodgames.com.au"

    def setUp(self):
        tb.SEALED_OPTS.update(new=True, packs=False)
        self._fetch, self._allowed, self._robots = tb.fetch_json, tb.HTTP.allowed, tb.HTTP.robots_on
        self.asked = []
        suggest = {"resources": {"results": {"products": [
            {"handle": "one-piece-card-game-booster-box-tba-op-18", "price": "399.00", "available": False,
             "title": "One Piece Card Game Booster Box – TBA [OP-18] (Preorder)", "tags": ["PREORDER"]},
            {"handle": "one-piece-card-game-starter-deck-tba-st-38", "price": "38.00", "available": False,
             "title": "One Piece Card Game Starter Deck – TBA - ST-38 (Preorder)"},
            {"handle": "kill-team", "price": "70.00", "available": False, "title": "Kill Team - Shadowvaults (Book)"},
        ]}}}

        def fetch(url, tries=tb.HTTP_TRIES):
            self.asked.append(url)
            if "/search/suggest.json" in url:
                return suggest
            return {"products": [product("op08", "One Piece Card Game - Two Legends OP-08 Booster Box", 399, False)]} \
                if "page=" not in url else {"products": []}
        tb.fetch_json = fetch
        tb.HTTP.robots_on = False
        tb.PAGE_HINTS.clear()
        self.cfg = {"sealed": {"max_price": 260, "shopify_collections": [
            {"name": "Good Games (sealed)", "url": self.GG + "/collections/one-piece-card-game/products.json?limit=250"}]},
            "extra_shops": False, "releases": [{"date": "2026-11-20", "name": "OP-18 The Dominance of God"}]}

    def tearDown(self):
        tb.fetch_json, tb.HTTP.allowed, tb.HTTP.robots_on = self._fetch, self._allowed, self._robots

    def test_queries_come_from_the_release_calendar(self):
        q = tb.sweep_queries({"releases": tb.DEFAULT_RELEASES, "sweep_queries": ["PEB-01"]}, datetime(2026, 10, 22))
        self.assertEqual(q[0], "PEB-01")
        for code in ("EB-05", "TS-03", "OP-18", "DP-13", "IB-09", "IB-10", "ST-37", "ST-38", "EB-06", "OP-19"):
            self.assertIn(code, q)
        self.assertIn("one piece pre-order", q)
        old = tb.sweep_queries({"releases": [{"date": "2026-01-01", "name": "OP-14"}]}, datetime(2026, 10, 22))
        self.assertNotIn("OP-14", old)                               # long released: not searched any more

    def test_good_games_op18_is_found_only_by_the_sweep(self):
        _, by = tb.check_sealed(self.cfg, sweep=False)
        self.assertNotIn("OP-18", " ".join(l["name"] for l in by["Good Games (sealed)"]))
        _, by = tb.check_sealed(self.cfg, sweep=True)
        names = {l["name"]: l for l in by["Good Games (sealed)"]}
        op18 = names["One Piece Card Game Booster Box – TBA [OP-18] (Preorder)"]
        self.assertEqual((op18["group"], op18["page"]), ("box", tb.SWEEP_PAGE))
        self.assertNotIn("Kill Team - Shadowvaults (Book)", names)   # not One Piece
        self.assertIn("Good Games (sealed)", tb.SWEPT)
        self.assertTrue(any("q=OP-18" in u for u in self.asked))

    def test_first_sweep_remembers_and_later_sweeps_alert(self):
        known, pages = {}, {}
        _, by = tb.check_sealed(self.cfg, sweep=False)
        tb.new_listings(by, known, [], pages)                       # v2.3-style first read of the shop
        _, by = tb.check_sealed(self.cfg, sweep=True)
        self.assertEqual(tb.new_listings(by, known, [], pages, swept=set(tb.SWEPT)), [])   # first sweep: quiet
        self.assertEqual(pages["Good Games (sealed)"], tb.SWEEP_PAGE)
        _, by = tb.check_sealed(self.cfg, sweep=False)              # a normal check: nothing forgotten
        self.assertEqual(tb.new_listings(by, known, [], pages), [])
        by["Good Games (sealed)"].append({
            "id": "list|Good Games (sealed)|eb06", "box_id": "box|Good Games (sealed)|eb06", "group": "box",
            "kind": "New listing", "name": "One Piece Card Game Extra Booster Box [EB-06] (Preorder)",
            "shop": "Good Games (sealed)", "price": 199.0, "available": False, "url": "u", "cart": "",
            "note": "pre-order", "max": 260, "page": tb.SWEEP_PAGE})
        new = tb.new_listings(by, known, [], pages)
        self.assertEqual([l["id"] for l in new], ["list|Good Games (sealed)|eb06"])

    def test_a_shop_whose_robots_blocks_search_is_skipped_quietly(self):
        tb.HTTP.robots_on = True
        tb.HTTP.allowed = lambda url: "/search" not in url
        tb.SWEPT.clear()
        self.assertEqual(tb.sweep_shopify("Pokebox", "https://www.pokebox.com.au", 260, WATCH, ["OP-18"]), ([], []))
        self.assertNotIn("Pokebox", tb.SWEPT)
        self.assertFalse(any("pokebox" in u for u in self.asked))

    def test_a_failed_sweep_never_marks_the_shop_down(self):
        tb.fetch_json = lambda url, tries=tb.HTTP_TRIES: None if "suggest" in url else \
            {"products": [product("op08", "One Piece Card Game - Two Legends OP-08 Booster Box", 399, False)]}
        _, by = tb.check_sealed(self.cfg, sweep=True)
        self.assertIsNotNone(by["Good Games (sealed)"])
        self.assertNotIn("Good Games (sealed)", tb.SWEPT)

    def test_woo_sweep_searches_each_code(self):
        urls = []

        def fetch(url, tries=tb.HTTP_TRIES):
            urls.append(url)
            return [{"id": 7, "name": "One Piece Card Game &#8211; Starter Deck [ST-38]", "permalink": "https://m/st38",
                     "prices": {"price": "3800", "currency_minor_unit": 2}, "is_in_stock": False}]
        tb.fetch_json = fetch
        finds, ls = tb.sweep_woo("M-G", "https://www.m-g.com.au/wp-json/wc/store/v1/products?search=x&per_page=50",
                                 260, WATCH, ["ST-38", "one piece preorder"])
        self.assertEqual(finds, [])
        self.assertTrue(any("search=one+piece+ST-38" in u for u in urls))
        self.assertTrue(any("search=one+piece+preorder" in u for u in urls))
        self.assertEqual({l["page"] for l in ls}, {tb.SWEEP_PAGE})


class Opened(unittest.TestCase):
    def listing(self, available=True, group="new"):
        return {"id": "list|Gameology|st39", "box_id": "item|Gameology|st39", "group": group, "kind": "New listing",
                "name": "One Piece Card Game ST-39 Starter Deck", "shop": "Gameology", "price": 24.95,
                "available": available, "url": "u", "cart": "c", "note": "pre-order", "max": 0.0, "page": 1}

    def test_alerts_when_a_listed_product_opens(self):
        now = time.time()
        hist = {"item|Gameology|st39": {"avail": False, "since": now - 3600}}
        out = tb.opened_listings({"Gameology": [self.listing()]}, hist=hist, now=now)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0]["opened"])
        self.assertIn("pre-order open", out[0]["note"])
        self.assertTrue(out[0]["id"].startswith("open|item|Gameology|st39|"))

    def test_quiet_for_flickers_new_products_still_listed_boxes_and_buyable(self):
        now = time.time()
        by = {"Gameology": [self.listing()]}
        self.assertEqual(tb.opened_listings(by, hist={"item|Gameology|st39": {"avail": False, "since": now - 60}},
                                            now=now), [])                        # unavailable for just a minute
        self.assertEqual(tb.opened_listings(by, hist={}, now=now), [])             # new: that's a new-listing alert
        self.assertEqual(tb.opened_listings(by, hist={"item|Gameology|st39": {"avail": True, "since": 0}}, now=now), [])
        self.assertEqual(tb.opened_listings({"Gameology": [self.listing(available=False)]},
                                            hist={"item|Gameology|st39": {"avail": False, "since": 0}}, now=now), [])
        box = dict(self.listing(group="box"), box_id="box|Gameology|op18")
        self.assertEqual(tb.opened_listings({"Gameology": [box]}, hist={"box|Gameology|op18": {"avail": False,
                                                                                                "since": 0}}, now=now), [])


class Routing(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self._send = tb.discord_send
        tb.discord_send = lambda alerts, hook, payload, tries=3: self.sent.append((hook, payload)) or True

    def tearDown(self):
        tb.discord_send = self._send

    def test_new_sealed_and_now_buyable_go_to_the_sealed_channel(self):
        f = {"id": "list|Gameology|st39", "kind": "New listing", "group": "new", "name": "ST-39 Starter Deck",
             "shop": "Gameology", "price": 24.95, "url": "u", "cart": "", "note": "pre-order"}
        g = dict(f, id="open|item|Gameology|st39|1", opened=True)
        tb.push_discord_detailed({"alerts": {"discord_webhook_boxes": BOXES, "discord_webhook_sealed": SEALED_HOOK}},
                                 "t", "b", [f, g])
        self.assertEqual({h for h, _ in self.sent}, {SEALED_HOOK})
        titles = [e["title"] for _, p in self.sent for e in p["embeds"]]
        self.assertIn("🆕 ST-39 Starter Deck", titles)
        self.assertIn("🔓 Now buyable: ST-39 Starter Deck", titles)


class Settings(unittest.TestCase):
    def test_new_settings_are_known_and_checked(self):
        cfg = {"sealed": {"max_price": 260}, "new_sealed": True, "new_sealed_packs": False, "sweep": True,
               "sweep_every_minutes": "x", "sweep_queries": "PEB-01"}
        w = tb.check_config(cfg)
        self.assertFalse(any("unknown setting" in x for x in w))
        self.assertTrue(any("sweep_queries" in x for x in w))
        self.assertTrue(any("sweep_every_minutes" in x for x in w))
        self.assertEqual(cfg["sweep_queries"], [])

    def test_begin_check_applies_new_sealed_settings(self):
        tb.begin_check({"new_sealed": False, "new_sealed_packs": True}, status={})
        self.assertEqual(tb.SEALED_OPTS, {"new": False, "packs": True})
        tb.begin_check({}, status={})
        self.assertEqual(tb.SEALED_OPTS, {"new": True, "packs": False})


if __name__ == "__main__":
    unittest.main()
