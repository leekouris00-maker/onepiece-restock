"""Tests for deck_price.py (/pricecheck). No network: the price records are made up here.

Run:  python -m unittest discover -s tests
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import deck_price as dk  # noqa: E402

NOW = 1_800_000_000
EA, GG = "https://elementalarcade.com.au", "https://tcg.goodgames.com.au"

SHOPS = {"v": 1, "shops": {"Elemental Arcade": {"base": EA, "scans": [NOW]}, "Good Games": {"base": GG, "scans": [NOW]}},
         "items": {
             # Sabo OP13-120: regular sold out, only the Wanted Poster in stock
             "Elemental Arcade|sabo-op13120": {"n": "Sabo - OP13-120 [Carrying On His Will]", "p": [[NOW, 5.5, 0]]},
             "Good Games|sabo-wanted": {"n": "Sabo (Wanted Poster) [Carrying On His Will] (OP13-120)", "p": [[NOW, 196.1, 1]]},
             # Belo Betty: two shops, cheapest wins
             "Elemental Arcade|belo-betty": {"n": "Belo Betty - OP05-015 [Awakening of the New Era]", "p": [[NOW, 1.0, 1]]},
             "Good Games|belo-betty": {"n": "Belo Betty [Awakening of the New Era] (OP05-015)", "p": [[NOW, 1.5, 1]]},
             # Koala: a reprint counts as a play copy
             "Good Games|koala-reprint": {"n": "Koala (Reprint) [Premium Booster] (OP05-006)", "p": [[NOW, 1.2, 1]]},
             # gone from the list: not buyable
             "Good Games|dragon": {"n": "Monkey.D.Dragon [Carrying On His Will] (OP13-017)", "p": [[NOW, 1.0, 1]], "gone": NOW},
             # Japanese copies never count
             "Elemental Arcade|stussy-jp": {"n": "Stussy - OP07-085 (Japanese) [500 Years]", "p": [[NOW, 0.5, 1]]},
         }}

TCG = {"v": 1, "fx": {"rate": 1.5}, "groups": {}, "items": {
    "1": {"t": "card", "num": "OP13-120", "n": "Sabo (120)", "m": 4.0},
    "2": {"t": "card", "num": "OP13-120", "n": "Sabo (120) (Wanted Poster)", "m": 120.0},
    "3": {"t": "card", "num": "OP05-015", "n": "Belo Betty", "m": 0.5},
    "4": {"t": "card", "num": "OP05-006", "n": "Koala", "m": 0.6},
    "5": {"t": "card", "num": "OP07-085", "n": "Stussy", "m": 3.0},
}}

CFG = {"singles": {"cards": [
    {"name": "Sabo", "num": "OP13-120", "qty": 4, "owned": 4, "deck": "Sabo"},
    {"name": "Belo Betty", "num": "OP05-015", "qty": 4, "owned": 1, "deck": "Sabo"},
    {"name": "Koala", "num": "OP05-006", "qty": 2, "deck": "both Sabo decks"},
    {"name": "Luffy", "num": "ST30-001", "qty": 1, "deck": "Luffy & Ace"},
]}}


class Parse(unittest.TestCase):
    def test_formats(self):
        cards, _ = dk.parse("1xOP12-001\n4x OP12-016 4 OP05-015 OP13-120 x3 OP01-016 2x P-001 st30-002")
        self.assertEqual(cards, [("OP12-001", 1), ("OP12-016", 4), ("OP05-015", 4), ("P-001", 2),
                                 ("OP13-120", 3), ("OP01-016", 1), ("ST30-002", 1)])

    def test_adds_up_and_warns(self):
        cards, warn = dk.parse("3xOP05-015 2xOP05-015")
        self.assertEqual(cards, [("OP05-015", 5)])
        self.assertTrue(any("More than 4" in w for w in warn))

    def test_full_deck_no_count_warning(self):
        text = "1xOP12-001 " + " ".join(f"4xOP12-{i:03d}" for i in range(10, 22)) + " 2xOP05-015"
        cards, warn = dk.parse(text)
        self.assertEqual(sum(q for _, q in cards), 51)
        self.assertEqual(warn, [])

    def test_nothing(self):
        self.assertEqual(dk.parse("hello there")[0], [])


class Price(unittest.TestCase):
    def setUp(self):
        dk._shop_cache.clear()

    def test_collector_copy_does_not_count(self):
        rows, tot = dk.price([("OP13-120", 4)], SHOPS, TCG)
        r = rows[0]
        self.assertIsNone(r["shop"])
        self.assertEqual(r["other"][3], "wanted poster")
        self.assertEqual(tot["shop_aud"], 0)
        self.assertAlmostEqual(tot["gap_aud"], 4 * 4.0 * 1.5)

    def test_cheapest_shop_reprint_gone_japanese(self):
        rows, tot = dk.price([("OP05-015", 4), ("OP05-006", 1), ("OP13-017", 1), ("OP07-085", 2)], SHOPS, TCG)
        by = {r["num"]: r for r in rows}
        self.assertEqual(by["OP05-015"]["shop"][1], "Elemental Arcade")
        self.assertEqual(by["OP05-006"]["shop"][0], 1.2)
        self.assertIsNone(by["OP13-017"]["shop"])
        self.assertIsNone(by["OP07-085"]["shop"])
        self.assertAlmostEqual(tot["shop_aud"], 4 * 1.0 + 1.2)
        self.assertEqual(tot["shop_cards"], 5)

    def test_no_tcgplayer_only_regular_counts(self):
        rows, _ = dk.price([("OP13-120", 1), ("OP05-015", 1)], SHOPS, None)
        self.assertIsNone(rows[0]["shop"])
        self.assertEqual(rows[1]["shop"][0], 1.0)

    def test_fair(self):
        self.assertTrue(dk.fair(7.6, 1.6, ""))         # a promo print of a bulk card: still a play copy
        self.assertFalse(dk.fair(196.1, 6.0, "wanted poster"))
        self.assertFalse(dk.fair(2.0, None, "alternate art"))


class Decks(unittest.TestCase):
    def setUp(self):
        dk._shop_cache.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.old = dk.DECKS_PATH
        dk.DECKS_PATH = os.path.join(self.tmp.name, "decks.json")

    def tearDown(self):
        dk.DECKS_PATH = self.old
        self.tmp.cleanup()

    def test_want_list_deck_counts_what_is_left(self):
        title, cards, have, _, _ = dk.resolve(CFG, "sabo")
        self.assertEqual(title, "Sabo")
        self.assertEqual(dict(cards), {"OP13-120": 0, "OP05-015": 3, "OP05-006": 2})   # 'both Sabo decks' joins
        self.assertEqual(have["OP05-015"], (4, 1))
        e = dk.build(CFG, "Sabo", SHOPS, TCG)
        self.assertIn("Got them all", e["description"])
        self.assertIn("A$3.00", e["description"])          # 3 Belo Betty at A$1

    def test_save_resolve_remove(self):
        self.assertEqual(dk.save_deck("Red/Black Sabo", [("OP05-015", 4)], "lee"), "added")
        self.assertEqual(dk.save_deck("red/black  sabo", [("OP05-015", 2)], "lee"), "updated")
        title, cards, _, src, _ = dk.resolve(CFG, "RED/BLACK SABO")
        self.assertEqual((title, cards), ("red/black sabo", [("OP05-015", 2)]))
        self.assertIn("saved by lee", src)
        self.assertTrue(any("Red" in a or "red" in a for a, _ in dk.suggestions(CFG, "black")))
        self.assertIsNotNone(dk.remove_deck("Red/Black Sabo"))
        self.assertIsNone(dk.resolve(CFG, "Red/Black Sabo"))

    def test_pasted_list(self):
        e = dk.build(CFG, "4xOP05-015 4xOP13-120", SHOPS, TCG)
        self.assertTrue(e["title"].startswith("🃏 Pasted list"))
        self.assertIn("no play copy in stock", e["description"])
        self.assertIn("Wanted Poster", e["description"])

    def test_unknown(self):
        self.assertTrue(dk.build(CFG, "zzz", SHOPS, TCG)["title"].startswith("🃏 No deck"))


if __name__ == "__main__":
    unittest.main()
