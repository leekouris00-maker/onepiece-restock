"""Fast tests of the bot's logic - no network, no extra packages. Run: python -m unittest discover tests"""
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tcg_bot as tb  # noqa: E402

SHOPIFY_ROBOTS = """
User-agent: *
Disallow: /admin
Disallow: /cart
Disallow: /collections/*sort_by*
Disallow: /collections/*+*
Disallow: /recommendations/products
Disallow: /cart.js
Disallow: /cdn/wpm/*.js
Allow: /

User-agent: Nutch
Disallow: /
"""


class Robots(unittest.TestCase):
    def test_shopify_default_allows_what_the_bot_reads(self):
        rules = tb.parse_robots(SHOPIFY_ROBOTS)
        for path in ("/search/suggest.json?q=OP13-120&resources[type]=product&resources[limit]=10",
                     "/collections/one-piece-card-game/products.json?limit=250", "/products/sabo.js"):
            self.assertTrue(tb.robots_allows(rules, path), path)

    def test_disallowed_paths(self):
        rules = tb.parse_robots(SHOPIFY_ROBOTS)
        self.assertFalse(tb.robots_allows(rules, "/collections/all?sort_by=price-ascending"))
        self.assertFalse(tb.robots_allows(rules, "/cart.js"))
        self.assertFalse(tb.robots_allows(rules, "/cdn/wpm/abc.js"))

    def test_search_disallowed_like_pokebox(self):
        rules = tb.parse_robots("User-agent: *\nDisallow: /search\n")
        self.assertFalse(tb.robots_allows(rules, "/search/suggest.json?q=x"))
        self.assertTrue(tb.robots_allows(rules, "/products/x.js"))

    def test_longest_match_and_allow_wins_ties(self):
        rules = tb.parse_robots("User-agent: *\nDisallow: /a\nAllow: /a/b\nDisallow: /x$\nAllow: /tie\nDisallow: /tie\n")
        self.assertTrue(tb.robots_allows(rules, "/a/b/c"))
        self.assertFalse(tb.robots_allows(rules, "/a/c"))
        self.assertFalse(tb.robots_allows(rules, "/x"))
        self.assertTrue(tb.robots_allows(rules, "/x/y"))
        self.assertTrue(tb.robots_allows(rules, "/tie"))

    def test_other_agents_groups_ignored(self):
        rules = tb.parse_robots("User-agent: BadBot\nDisallow: /\n\nUser-agent: *\nDisallow: /private\n")
        self.assertTrue(tb.robots_allows(rules, "/products/x.js"))
        self.assertFalse(tb.robots_allows(rules, "/private/x"))

    def test_empty_disallow_allows_everything(self):
        self.assertTrue(tb.robots_allows(tb.parse_robots("User-agent: *\nDisallow:\n"), "/anything"))


class Titles(unittest.TestCase):
    def test_preorder_needs_the_word_order_or_sale(self):
        self.assertFalse(tb.is_preorder("One Piece Card Game PRB-02 The Best Premium Booster Box"))
        self.assertFalse(tb.is_preorder("Prerelease Event Pack"))
        self.assertTrue(tb.is_preorder("OP-19 Booster Box (Pre-Order)"))
        self.assertTrue(tb.is_preorder("OP-19 Booster Box", ["One Piece", "preorder"]))
        self.assertTrue(tb.is_preorder("OP-19 Booster Box - PRESALE"))
        self.assertTrue(tb.is_preorder("x", "Pre Order, One Piece"))

    def test_box_titles(self):
        self.assertTrue(tb.is_box_title("One Piece Card Game OP-13 Carrying On His Will Booster Box"))
        self.assertFalse(tb.is_box_title("One Piece OP-13 Booster Box (Japanese)"))
        self.assertFalse(tb.is_box_title("One Piece OP-13 Booster Box Case (12 boxes)"))


class Config(unittest.TestCase):
    def base(self):
        return {"alerts": {}, "sealed": {"max_price": 260, "shopify_collections": []},
                "singles": {"shops": {"Elemental Arcade": "https://elementalarcade.com.au"},
                            "cards": [{"name": "Sabo", "num": "OP13-120", "qty": 4, "max": 12}]}}

    def test_numbers_typed_as_text_are_fixed(self):
        cfg = self.base()
        cfg["sealed"]["max_price"] = "$260"
        cfg["singles"]["cards"][0]["max"] = "12.50"
        cfg["singles"]["cards"][0]["qty"] = "4"
        self.assertEqual(tb.check_config(cfg), [])
        self.assertEqual(cfg["sealed"]["max_price"], 260.0)
        self.assertEqual(cfg["singles"]["cards"][0]["max"], 12.5)
        self.assertEqual(cfg["singles"]["cards"][0]["qty"], 4)

    def test_broken_card_is_switched_off_not_fatal(self):
        cfg = self.base()
        cfg["singles"]["cards"].append({"name": "Mystery", "max": "lots"})
        w = tb.check_config(cfg)
        self.assertEqual(len(w), 1)
        self.assertFalse(cfg["singles"]["cards"][1]["enabled"])
        self.assertTrue(cfg["singles"]["cards"][0].get("enabled", True))

    def test_typo_in_setting_name_is_spotted(self):
        cfg = self.base()
        cfg["drop_window"] = []
        w = tb.check_config(cfg)
        self.assertTrue(any('did you mean "drop_windows"' in x for x in w), w)

    def test_bad_values(self):
        cfg = self.base()
        cfg["sealed"]["max_price"] = "cheap"
        cfg["alerts"] = {"discord_webhook_boxes": "https://example.com/hook", "quiet_hours": "late"}
        cfg["singles"]["shops"]["Mayhem"] = "www.mayhemcollectables.com.au"
        w = tb.check_config(cfg)
        self.assertEqual(cfg["sealed"]["max_price"], 0.0)
        self.assertNotIn("Mayhem", cfg["singles"]["shops"])
        self.assertNotIn("quiet_hours", cfg["alerts"])
        self.assertEqual(len(w), 4, w)

    def test_real_configs_have_no_warnings(self):
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(repo, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertEqual(tb.check_config(cfg), [])


class DropWindows(unittest.TestCase):
    def test_auto_windows_for_booster_releases(self):
        cfg = {"releases": [{"date": "2026-11-20", "name": "OP-18 The Dominance of God"},
                            {"date": "2026-11-20", "name": "DP-13 Double Pack Set Vol. 13"},
                            {"date": "2027-03-01", "name": "PRB-03 Premium (date approx.)"}]}
        ws = tb.auto_windows(cfg, now=datetime(2026, 10, 14))
        self.assertEqual([w["name"] for w in ws], ["OP-18 eve (auto)", "OP-18 release day (auto)"])
        self.assertEqual(ws[0]["start"], datetime(2026, 11, 19, 18, 0))
        self.assertEqual(ws[1]["end"], datetime(2026, 11, 20, 14, 0))

    def test_your_windows_win_where_they_overlap(self):
        cfg = {"releases": [{"date": "2026-11-20", "name": "OP-18"}],
               "drop_windows": [{"name": "mine", "start": "2026-11-20 07:00", "end": "2026-11-20 12:00"}]}
        names = [w["name"] for w in tb.parse_windows(cfg)]
        self.assertIn("mine", names)
        self.assertNotIn("OP-18 release day (auto)", names)
        self.assertIn("OP-18 eve (auto)", names)

    def test_switch_off(self):
        self.assertEqual(tb.auto_windows({"auto_drop_windows": False, "releases": [{"date": "2030-01-01", "name": "OP-30"}]}), [])


def single(shop, name, price, vid, qty=4, base="https://elementalarcade.com.au", **kw):
    f = {"id": f"card|{shop}|{name}|{vid}", "kind": "Single", "name": name, "shop": shop, "price": price,
         "qty": qty, "url": f"{base}/products/{vid}", "cart": f"{base}/cart/{vid}:{qty}", "note": ""}
    f.update(kw)
    return f


class Carts(unittest.TestCase):
    def test_one_cart_per_shop_cheapest_copy_of_each_card(self):
        finds = [single("Elemental Arcade", "Belo Betty OP05-015", 0.65, 11),
                 single("Elemental Arcade", "Belo Betty OP05-015", 0.50, 12),      # cheaper copy of the same card
                 single("Elemental Arcade", "Monkey.D.Garp OP13-016", 0.55, 13),
                 single("Elemental Arcade", "Revolutionary Army HQ OP05-021", 0.35, 14, qty=3),
                 single("Good Games", "Belo Betty OP05-015", 1.50, 21, base="https://tcg.goodgames.com.au"),
                 single("Elemental Arcade", "Value thing", 3.0, 99, value_pick=True)]
        carts = tb.combined_carts(finds)
        self.assertEqual(len(carts), 1)
        c = carts[0]
        self.assertEqual(c["shop"], "Elemental Arcade")
        self.assertEqual(c["n"], 3)
        self.assertEqual(sorted(c["link"].rsplit("/", 1)[1].split(",")), ["12:4", "13:4", "14:3"])
        self.assertAlmostEqual(c["total"], 0.50 * 4 + 0.55 * 4 + 0.35 * 3)

    def test_no_cart_for_a_single_card(self):
        self.assertEqual(tb.combined_carts([single("Elemental Arcade", "A", 1, 1)]), [])


class Chunking(unittest.TestCase):
    def test_ten_embeds_per_message(self):
        items = [({"title": f"x{i}"}, {i}) for i in range(25)]
        self.assertEqual([len(m) for m in tb._chunks(items)], [10, 10, 5])

    def test_character_budget(self):
        big = "y" * 1500
        items = [({"title": "t", "description": big}, {i}) for i in range(8)]
        msgs = tb._chunks(items)
        self.assertTrue(all(sum(tb._embed_size(e) for e, _ in m) <= tb.EMBED_BUDGET for m in msgs))
        self.assertEqual(sum(len(m) for m in msgs), 8)


class Pings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = tb.CONTROLS_PATH
        tb.CONTROLS_PATH = os.path.join(self.tmp, "controls.json")

    def tearDown(self):
        tb.CONTROLS_PATH = self.old

    def test_quiet_hours_except_boxes(self):
        cfg = {"alerts": {"quiet_hours": "23:00-07:00"}}
        night, day = datetime(2026, 10, 14, 2, 30), datetime(2026, 10, 14, 12, 0)
        single_find = [{"kind": "Single"}]
        box = [{"kind": "Booster box"}]
        self.assertFalse(tb.ping_allowed(cfg, single_find, night))
        self.assertTrue(tb.ping_allowed(cfg, box, night))
        self.assertTrue(tb.ping_allowed(cfg, single_find, day))

    def test_mute(self):
        tb.atomic_write_json(tb.CONTROLS_PATH, {"mute_until": time.time() + 600})
        self.assertFalse(tb.ping_allowed({"alerts": {}}, [{"kind": "Booster box"}]))
        tb.atomic_write_json(tb.CONTROLS_PATH, {"mute_until": time.time() - 1})
        self.assertTrue(tb.ping_allowed({"alerts": {}}, [{"kind": "Booster box"}]))


def listing(shop, handle, page=1, available=False, price=200.0):
    return {"id": f"list|{shop}|{handle}", "box_id": f"box|{shop}|{handle}", "group": "box", "kind": "New listing",
            "name": handle, "shop": shop, "price": price, "available": available, "url": "u", "cart": "",
            "note": "", "max": 260, "page": page}


class NewListings(unittest.TestCase):
    def test_first_read_remembers_quietly_then_alerts(self):
        known = {}
        self.assertEqual(tb.new_listings({"Pokebox": [listing("Pokebox", "a")]}, known, []), [])
        out = tb.new_listings({"Pokebox": [listing("Pokebox", "a"), listing("Pokebox", "b")]}, known, [])
        self.assertEqual([l["id"] for l in out], ["list|Pokebox|b"])

    def test_reading_page_two_for_the_first_time_does_not_flood(self):
        known, pages = {}, {}
        tb.new_listings({"Pokebox": [listing("Pokebox", "a")]}, known, [], pages)
        out = tb.new_listings({"Pokebox": [listing("Pokebox", "a"), listing("Pokebox", "old-on-p2", page=2)]}, known, [], pages)
        self.assertEqual(out, [])
        self.assertEqual(pages["Pokebox"], 2)
        out = tb.new_listings({"Pokebox": [listing("Pokebox", "a"), listing("Pokebox", "old-on-p2", page=2),
                                           listing("Pokebox", "brand-new", page=2)]}, known, [], pages)
        self.assertEqual([l["id"] for l in out], ["list|Pokebox|brand-new"])

    def test_fresh_install_records_depth_so_page_two_additions_alert(self):
        known, pages = {}, {}
        tb.new_listings({"Pokebox": [listing("Pokebox", "a"), listing("Pokebox", "b", page=2)]}, known, [], pages)
        self.assertEqual(pages["Pokebox"], 2)
        out = tb.new_listings({"Pokebox": [listing("Pokebox", "a"), listing("Pokebox", "b", page=2),
                                           listing("Pokebox", "c", page=2)]}, known, [], pages)
        self.assertEqual([l["id"] for l in out], ["list|Pokebox|c"])

    def test_buyable_box_not_doubled_as_new_listing(self):
        known = {"Gumnut": []}
        l = listing("Gumnut", "op18", available=True, price=250)
        out = tb.new_listings({"Gumnut": [l]}, known, [{"id": "box|Gumnut|op18"}])
        self.assertEqual(out, [])


class History(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.paths = (tb.HISTORY_PATH, tb.EVENTS_PATH)
        tb.HISTORY_PATH = os.path.join(self.tmp, "h.json")
        tb.EVENTS_PATH = os.path.join(self.tmp, "e.jsonl")

    def tearDown(self):
        tb.HISTORY_PATH, tb.EVENTS_PATH = self.paths

    def test_lowest_seen_and_events(self):
        day1, day2 = datetime.now() - timedelta(days=2), datetime.now() - timedelta(days=1)
        tb.record_history({"Gumnut": [listing("Gumnut", "op13", available=False, price=220)]}, day1)
        tb.record_history({"Gumnut": [listing("Gumnut", "op13", available=True, price=210)]}, day2)
        tb.record_history({"Gumnut": [listing("Gumnut", "op13", available=True, price=230)]})
        hist = tb.read_json(tb.HISTORY_PATH)
        low = tb.lowest_seen(hist, "box|Gumnut|op13")
        self.assertEqual(low[0], 210)
        ev = tb.read_events(30)
        self.assertEqual([e["event"] for e in ev], ["in_stock"])

    def test_one_point_per_day(self):
        for p in (220, 215, 230):
            tb.record_history({"Gumnut": [listing("Gumnut", "x", available=True, price=p)]})
        pts = tb.read_json(tb.HISTORY_PATH)["box|Gumnut|x"]["points"]
        self.assertEqual(len(pts), 1)
        self.assertEqual(pts[0][1], 215)          # lowest in-stock price that day


class Files(unittest.TestCase):
    def test_atomic_write_and_tolerant_read(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "x.json")
        tb.atomic_write_json(p, {"a": 1})
        self.assertEqual(tb.read_json(p), {"a": 1})
        self.assertEqual([f for f in os.listdir(d) if f.endswith(".tmp")], [])
        with open(p, "w", encoding="utf-8-sig") as f:        # what Notepad saves
            f.write('{"b": 2}')
        self.assertEqual(tb.read_json(p), {"b": 2})
        with open(p, "w") as f:
            f.write('{"half": ')
        self.assertEqual(tb.read_json(p, {}), {})

    def test_log_rolls_over(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "finds.log")
        tb.append_text(p, "x" * 200, max_bytes=100)
        tb.append_text(p, "y", max_bytes=100)
        self.assertTrue(os.path.exists(p + ".1"))
        with open(p) as f:
            self.assertEqual(f.read(), "y")

    def test_redact(self):
        s = tb.redact("failed https://discord.com/api/webhooks/123456/AbC-dEf_ghi?wait=true")
        self.assertNotIn("AbC-dEf_ghi", s)
        self.assertIn("123456", s)


class SeenLogic(unittest.TestCase):
    def test_new_only(self):
        finds = [{"id": "a", "price": 10.0}, {"id": "b", "price": 5.0}, {"id": "c", "price": 7.0}]
        out = tb.new_only(finds, {"a": 10.0, "b": 6.0})
        self.assertEqual([f["id"] for f in out], ["b", "c"])


if __name__ == "__main__":
    unittest.main()
