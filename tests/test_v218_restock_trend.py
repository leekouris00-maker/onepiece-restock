"""v2.18: restock trends per shop (restock_trend.py) and /restocks. No network."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402
import restock_trend as rt  # noqa: E402

DAY = 86400
NOW = 1_800_000_000          # a fixed "now" so nothing depends on the real clock


def ins(t, shop, pid, name="OP-18 booster box", price=214.99):
    return {"t": t, "event": "in_stock", "id": pid, "name": name, "shop": shop, "price": price, "was": 3 * DAY}


def out(t, shop, pid, was):
    return {"t": t, "event": "sold_out", "id": pid, "name": "x", "shop": shop, "price": 214.99, "was": was}


class Grouping(unittest.TestCase):
    def test_products_within_an_hour_are_one_restock(self):
        ev = [ins(NOW - 5000, "Pokebox", "a"), ins(NOW - 4000, "Pokebox", "b"), ins(NOW - 2000, "Pokebox", "c"),
              ins(NOW - 2000, "Gameology", "d")]
        rs = rt.restocks(ev)
        self.assertEqual(len(rs), 2)
        pb = next(r for r in rs if r["shop"] == "Pokebox")
        self.assertEqual([i["id"] for i in pb["items"]], ["a", "b", "c"])

    def test_more_than_an_hour_apart_is_two(self):
        rs = rt.restocks([ins(NOW - 9000, "Pokebox", "a"), ins(NOW - 1000, "Pokebox", "b")])
        self.assertEqual(len(rs), 2)

    def test_same_product_twice_in_one_restock_counts_once(self):
        rs = rt.restocks([ins(NOW - 900, "JToys", "a"), ins(NOW - 300, "JToys", "a")])
        self.assertEqual(len(rs[0]["items"]), 1)

    def test_how_long_it_lasted_comes_from_the_next_sell_out(self):
        ev = [ins(NOW - 10 * DAY, "JToys", "a"), out(NOW - 9 * DAY, "JToys", "a", DAY),
              ins(NOW - 2 * DAY, "JToys", "a")]
        rs = rt.restocks(ev)
        self.assertEqual(rs[0]["items"][0]["lasted"], DAY)
        self.assertIsNone(rs[1]["items"][0]["lasted"])          # still in stock

    def test_game_filter(self):
        ev = [ins(NOW - 100, "M-G", "poke|30th|M-G|1", "Pokemon ETB"), ins(NOW - 100, "Gumnut", "box|gum|op18")]
        self.assertEqual([r["shop"] for r in rt.restocks(ev, "Pokémon")], ["M-G"])
        self.assertEqual([r["shop"] for r in rt.restocks(ev, "One Piece")], ["Gumnut"])

    def test_ignores_alerts_and_junk(self):
        ev = [{"t": NOW, "event": "alert", "shop": "eBay", "id": "e"}, {"event": "in_stock"}, {}]
        self.assertEqual(rt.restocks(ev), [])


class Trend(unittest.TestCase):
    def stats(self, ev, since=None, days=30):
        return rt.shop_stats(rt.restocks(ev), days, NOW, since if since is not None else rt.data_since(ev))

    def test_counts_this_period_against_the_one_before(self):
        ev = [ins(NOW - d * DAY, "Pokebox", f"a{d}") for d in (1, 5, 9, 13, 40)]
        s = self.stats(ev, since=NOW - 70 * DAY)[0]
        self.assertEqual((s["count"], s["prev"]), (4, 1))
        self.assertEqual(s["trend"], "↑ +300%")

    def test_down_steady_new(self):
        self.assertEqual(rt.trend_label(1, 4, True), "↓ -75%")
        self.assertEqual(rt.trend_label(10, 9, True), "→ steady")
        self.assertEqual(rt.trend_label(2, 0, True), "new")
        self.assertEqual(rt.trend_label(3, 0, False), "building history")

    def test_no_comparison_until_the_log_covers_both_periods(self):
        ev = [ins(NOW - d * DAY, "Pokebox", f"a{d}") for d in (1, 5)]
        self.assertEqual(self.stats(ev, since=NOW - 20 * DAY)[0]["trend"], "building history")

    def test_busiest_first_and_old_shops_left_out(self):
        ev = [ins(NOW - DAY, "A", "1"), ins(NOW - 3 * DAY, "B", "2"), ins(NOW - 5 * DAY, "B", "3"),
              ins(NOW - 200 * DAY, "Old", "4")]
        self.assertEqual([s["shop"] for s in self.stats(ev)], ["B", "A"])

    def test_gap_lasted_and_next_guess(self):
        ev = []
        for d in (2, 6, 10, 14):
            ev += [ins(NOW - d * DAY, "Gameology", f"g{d}"), out(NOW - d * DAY + 7200, "Gameology", f"g{d}", 7200)]
        s = self.stats(ev)[0]
        self.assertAlmostEqual(s["gap_days"], 4)
        self.assertAlmostEqual(s["lasted_min"], 120)
        self.assertAlmostEqual(s["next"], NOW + 2 * DAY)
        self.assertIn("around", rt.next_guess(s["next"], NOW))
        self.assertIn("due now", rt.next_guess(NOW - 1, NOW))

    def test_no_guess_with_too_few_restocks(self):
        s = self.stats([ins(NOW - DAY, "A", "1"), ins(NOW - 3 * DAY, "A", "2")])[0]
        self.assertIsNone(s["next"])

    def test_weekly_chart_only_covers_logged_weeks(self):
        ev = [ins(NOW - DAY, "A", "1"), ins(NOW - 8 * DAY, "A", "2"), ins(NOW - 9 * DAY, "A", "3")]
        s = self.stats(ev, since=NOW - 15 * DAY)[0]
        self.assertEqual(s["weekly"], [0, 2, 1])
        self.assertEqual(len(self.stats(ev, since=NOW - 400 * DAY)[0]["weekly"]), rt.WEEKS)

    def test_busiest_day_needs_a_repeat(self):
        # three restocks on three different days: no "busiest day"
        s = self.stats([ins(NOW - d * DAY, "A", str(d)) for d in (1, 2, 3)])[0]
        self.assertIsNone(s["day"])
        # same weekday three weeks running
        s = self.stats([ins(NOW - w * 7 * DAY, "A", str(w)) for w in (1, 2, 3)])[0]
        self.assertEqual(s["day"], (rt.DAYS[datetime.fromtimestamp(NOW - 7 * DAY).weekday()], 3))

    def test_find_shop(self):
        st = self.stats([ins(NOW - DAY, "Good Games (sealed)", "1"), ins(NOW - DAY, "Gameology", "2")])
        self.assertEqual(rt.find_shop(st, "gameology")["shop"], "Gameology")
        self.assertEqual(rt.find_shop(st, "good games")["shop"], "Good Games (sealed)")
        self.assertIsNone(rt.find_shop(st, "kmart"))
        self.assertIsNone(rt.find_shop(st, " "))

    def test_words(self):
        s = self.stats([ins(NOW - d * DAY, "Pokebox", str(d), price=219.99) for d in (1, 3, 5)])[0]
        line = rt.overview_line(s, NOW)
        self.assertIn("**Pokebox** · 3 restocks", line)
        self.assertIn("every ~2 days", line)
        fields = dict(rt.detail_fields(s, 30, NOW))
        self.assertIn("$219.99", fields["🧾 Recent restocks"])
        self.assertIn("may still be in stock", fields["🧾 Recent restocks"])
        self.assertEqual(rt.spark([0, 1, 2]), "▁▅█")
        self.assertEqual(rt.duration(45), "45 min")
        self.assertEqual(rt.duration(150), "2.5 h")


class DiscordCommand(unittest.TestCase):
    def setUp(self):
        try:
            import commands_bot
        except (Exception, SystemExit) as e:  # noqa: BLE001
            self.skipTest(f"discord.py isn't installed here ({e})")
        self.cb = commands_bot
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        path = os.path.join(self.dir.name, "events.jsonl")
        now = int(datetime.now().timestamp())
        ev = [ins(now - d * DAY, "Pokebox", f"p{d}") for d in (1, 4, 7)] + [ins(now - 2 * DAY, "M-G", "poke|x|M-G|1")]
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(e) + "\n" for e in ev))
        p = mock.patch.object(tb, "EVENTS_PATH", path)
        p.start()
        self.addCleanup(p.stop)

    def test_overview(self):
        e = self.cb.build_restocks({})
        self.assertIn("last 30 days", e.title)
        self.assertIn("Pokebox", e.fields[0].value)
        self.assertIn("M-G", e.fields[0].value)
        self.assertIn("building history", e.description)

    def test_one_shop_and_game_filter(self):
        e = self.cb.build_restocks({}, "pokebox", 14)
        self.assertIn("Pokebox", e.title)
        self.assertIn("📈 Trend", [f.name for f in e.fields])
        self.assertNotIn("M-G", self.cb.build_restocks({}, "", 30, "onepiece").fields[0].value)
        self.assertIn("No One Piece restocks", self.cb.build_restocks({}, "m-g", 30, "onepiece").description)

    def test_empty_log(self):
        with open(tb.EVENTS_PATH, "w", encoding="utf-8"):
            pass
        self.assertIn("No restocks logged yet", self.cb.build_restocks({}).fields[0].value)


if __name__ == "__main__":
    unittest.main()
