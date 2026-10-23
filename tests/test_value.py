"""Tests for value.py (/value). No network: the price record is made up here.

Run:  python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402
import value as cv  # noqa: E402

D = 86400
NOW = 1_800_000_000
T = NOW - 8 * D
EA, GG = "https://elementalarcade.com.au", "https://tcg.goodgames.com.au"
CFG = {"singles": {"shops": {"Elemental Arcade": EA, "Good Games": GG}}}


def store(items, scans_from=T):
    scans = list(range(int(scans_from), NOW + 1, 3600))
    return {"v": 1, "shops": {"Elemental Arcade": {"base": EA, "scans": scans},
                              "Good Games": {"base": GG, "scans": scans}}, "items": items}


WANTED = {
    "Elemental Arcade|sabo-op13120-wanted": {
        "n": "Sabo - OP13-120 (Wanted Poster) [Carrying On His Will]",
        "p": [[T, 219.9, 1], [T + 2.5 * D, 214.5, 1], [T + 4.2 * D, 214.5, 0], [T + 5 * D, 209, 1]]},
    "Good Games|sabo-wanted-poster-carrying-on-his-will": {
        "n": "Sabo (Wanted Poster) [Carrying On His Will] (OP13-120)",
        "p": [[T, 225, 1], [T + 3 * D, 201.3, 1], [T + 7.2 * D, 198.0, 1]]},
    "Elemental Arcade|sabo-op13004-carrying-on-his-will": {
        "n": "Sabo - OP13-004 [Carrying On His Will]", "p": [[T, 1.0, 1]]},
    "Good Games|carrot-alternate-art-best-vol-2": {
        "n": "Carrot (Alternate Art) [Premium Booster -The Best- Vol. 2] (OP08-023)", "p": [[T, 147.9, 1]]},
    "Elemental Arcade|carrot-op08023-parallel-two-legends": {
        "n": "Carrot - OP08-023 (Parallel) [Two Legends]", "p": [[T, 19.3, 1]]},
}


class Names(unittest.TestCase):
    def test_both_shops_title_styles_give_the_same_card(self):
        a = cv.parse_name("Sabo - OP13-120 (Wanted Poster) [Carrying On His Will]")
        b = cv.parse_name("Sabo (Wanted Poster) [Carrying On His Will] (OP13-120)")
        self.assertEqual(a, ("OP13-120", "Sabo", "wanted poster"))
        self.assertEqual(a, b)
        self.assertEqual(cv.group_key("Sabo - OP13-120 (Wanted Poster) [Carrying On His Will]"),
                         cv.group_key("Sabo (Wanted Poster) [Carrying On His Will] (OP13-120)"))

    def test_parallel_is_alternate_art_and_starter_deck_numbers_dont_split(self):
        self.assertEqual(cv.parse_name("Carrot - OP08-023 (Parallel) [Two Legends]")[2], "alternate art")
        self.assertEqual(cv.set_name("Buggy - ST25-002 [Starter Deck 25: Blue Buggy]"),
                         cv.set_name("Buggy [Starter Deck: Blue Buggy] (ST25-002)"))

    def test_reprints_in_another_set_are_kept_apart_and_labelled(self):
        gs = cv.groups(store(WANTED))
        carrots = sorted(g["label"] for k, g in gs.items() if k.startswith("OP08-023"))
        self.assertEqual(len(carrots), 2)
        self.assertTrue(any("Two Legends" in c for c in carrots))
        self.assertTrue(all("Alternate Art" in c for c in carrots))

    def test_short_version_names_are_capitals(self):
        self.assertEqual(cv.nice_version("sp"), "SP")
        self.assertEqual(cv.nice_version("alternate art"), "Alternate Art")
        self.assertEqual(cv.nice_version(""), "Regular")


class Finding(unittest.TestCase):
    def setUp(self):
        self.s = store(WANTED)

    def test_number_with_or_without_the_dash(self):
        self.assertEqual(cv.find(self.s, "OP13-120"), ["OP13-120|wanted poster|carrying on his will"])
        self.assertEqual(cv.find(self.s, "op13120"), ["OP13-120|wanted poster|carrying on his will"])

    def test_words_narrow_it_down(self):
        self.assertEqual(len(cv.find(self.s, "sabo")), 2)
        self.assertEqual(len(cv.find(self.s, "sabo wanted")), 1)
        self.assertEqual(cv.find(self.s, "zoro"), [])

    def test_autocomplete_puts_valuable_in_stock_first(self):
        sug = cv.suggestions(self.s, "")
        self.assertIn("Sabo OP13-120 · Wanted Poster · $198.00", sug[0][0])
        self.assertIn(sug[0][1], cv.groups(self.s))
        self.assertLessEqual(len(sug), 25)


class Lines(unittest.TestCase):
    def test_window_starts_with_the_price_going_in_and_ends_now(self):
        pts = WANTED["Good Games|sabo-wanted-poster-carrying-on-his-will"]["p"]
        t0 = NOW - 7 * D
        w = cv.window(pts, t0, NOW)
        self.assertEqual(w[0], (t0, 225, True))
        self.assertEqual(w[-1], (NOW, 198.0, True))
        self.assertEqual([p[1] for p in w], [225, 201.3, 198.0, 198.0])

    def test_listed_after_the_window_started(self):
        w = cv.window([[NOW - D, 10, 1]], NOW - 7 * D, NOW)
        self.assertEqual(w, [(NOW - D, 10, True), (NOW, 10, True)])

    def test_stats(self):
        st = cv.stats([(0, 225, True), (1, 201.3, True), (2, 198.0, True)])
        self.assertEqual((st["now"], st["low"], st["high"], st["change"]), (198.0, 198.0, 225, -27.0))
        self.assertTrue(cv.trend(st).startswith("▼ $27.00"))
        self.assertEqual(cv.trend(cv.stats([(0, 5, True), (1, 5, True)])), "▬ no change")

    def test_cheapest_in_stock_wins_and_sold_out_only_counts_when_nothing_is_in(self):
        a = [(0, 10, True), (5, 10, False), (10, 10, False)]
        b = [(0, 12, True), (10, 12, True)]
        self.assertEqual([p[1] for p in cv.cheapest([a, b], 0, 10)], [10, 12, 12])
        c = [(0, 15, False), (10, 15, False)]
        self.assertEqual(cv.cheapest([c], 0, 10)[-1], (10, 15, False))

    def test_labels_spread_around_their_bunch(self):
        ends = [[10.0, 10.0], [10.5, 10.5], [100.0, 100.0]]
        cv.place_labels(ends, 2.0)
        self.assertAlmostEqual(ends[1][1] - ends[0][1], 2.0)
        self.assertAlmostEqual((ends[0][1] + ends[1][1]) / 2, 10.25)    # centred, not all pushed up
        self.assertEqual(ends[2][1], 100.0)


class Answer(unittest.TestCase):
    def test_one_version_has_a_line_per_shop_and_the_value(self):
        e, png = cv.build(CFG, "OP13-120", 7, now=NOW, store=store(WANTED))
        self.assertIn("Worth about **$198.00**", e["description"])
        self.assertIn("Good Games", e["description"])
        self.assertIn("Elemental Arcade", e["description"])
        self.assertIn("$198.00 to $225.00", e["description"])
        self.assertTrue(e["url"].startswith(GG))
        self.assertIn("▼ $27.00", e["description"])
        if png is not None:
            self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(e["image"]["url"], "attachment://value.png")

    def test_several_versions_listed_most_valuable_first(self):
        e, _ = cv.build(CFG, "sabo", 7, now=NOW, store=store(WANTED))
        self.assertIn("2 versions", e["title"])
        self.assertLess(e["description"].index("OP13-120"), e["description"].index("OP13-004"))

    def test_a_short_record_says_when_the_week_fills_out(self):
        e, _ = cv.build(CFG, "OP13-004", 7, now=NOW, store=store(WANTED, scans_from=NOW - 2 * D))
        self.assertIn("fills out to 7 days", e["footer"]["text"])

    def test_nothing_matches_and_no_record(self):
        e, png = cv.build(CFG, "zoro", 7, now=NOW, store=store(WANTED))
        self.assertIn("Nothing matches", e["title"])
        self.assertIsNone(png)
        e, _ = cv.build(CFG, "zoro", 7, now=NOW, store={"v": 1, "shops": {}, "items": {}})
        self.assertIn("No prices recorded yet", e["description"])

    def test_without_matplotlib_it_still_answers_with_a_sparkline(self):
        old = cv.chart_png
        cv.chart_png = lambda *a, **k: None
        try:
            e, png = cv.build(CFG, "OP13-120", 7, now=NOW, store=store(WANTED))
        finally:
            cv.chart_png = old
        self.assertIsNone(png)
        self.assertNotIn("image", e)
        self.assertIn("one bar a day", e["description"])
        self.assertIn("pip install matplotlib", e["description"])


class Record(unittest.TestCase):
    def test_the_record_keeps_a_week(self):
        self.assertGreaterEqual(tb.DROPS_KEEP_HOURS, 7 * 24)


if __name__ == "__main__":
    unittest.main()
