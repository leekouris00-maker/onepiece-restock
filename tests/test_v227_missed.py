"""v2.27: the misses of 12-16 Nov 2026 (Fellowship paste): shops refusing the bot are reported, the sweep
asks fewer searches per burst, the PC says how long it was off, the cloud says when the PC is behind,
quiet restocks repeat after 3 hours. No network."""
import os
import sys
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402

NOW = 1_800_000_000
CFG = {"sealed": {"max_price": 300, "shopify_collections": [
    {"name": "Rogue Online", "url": "https://rogueonline.com.au/collections/x/products.json?limit=250"},
    {"name": "Gumnut", "url": "https://www.gumnut.com.au/collections/x/products.json?limit=250"}],
    "shopify_search": [], "shopify_products": [], "woocommerce": []}, "extra_shops": False}
ROGUE, GUMNUT = "rogueonline.com.au", "www.gumnut.com.au"


def run_check(refused=(), ok=(), bad=()):
    """Fill the per-check records the way _fail/_note_host do."""
    with tb._host_lock:
        tb._host_results.clear()
        tb._host_refused.clear()
        tb._host_refused.update(refused)
        for h in ok:
            tb._host_results.setdefault(h, [0, 0])[0] += 1
        for h in bad:
            tb._host_results.setdefault(h, [0, 0])[1] += 1


class Refused(unittest.TestCase):
    def tearDown(self):
        run_check()

    def test_429_is_recorded_as_refused_not_down(self):
        run_check()
        tb._fail("https://rogueonline.com.au/collections/x/products.json", tb.HttpError(429, "Too Many Requests"))
        self.assertIn(ROGUE, tb._host_refused)
        self.assertNotIn(ROGUE, tb._host_results)        # still not "down"

    def test_posts_once_after_two_hours_then_when_back(self):
        st = {}
        run_check(refused=[ROGUE, GUMNUT])
        self.assertEqual(tb.refused_shops(CFG, st, now=NOW), [])
        run_check(refused=[ROGUE, GUMNUT])
        self.assertEqual(tb.refused_shops(CFG, st, now=NOW + 3600), [])
        run_check(refused=[ROGUE, GUMNUT])
        posts = tb.refused_shops(CFG, st, now=NOW + 2 * 3600 + 1)
        self.assertEqual(len(posts), 1)
        text, color = posts[0]
        self.assertIn("2 shops keep refusing", text)
        self.assertIn("Gumnut, Rogue Online", text)
        self.assertEqual(color, tb.AMBER)
        run_check(refused=[ROGUE, GUMNUT])
        self.assertEqual(tb.refused_shops(CFG, st, now=NOW + 3 * 3600), [])     # said already
        run_check(ok=[ROGUE], refused=[GUMNUT])
        posts = tb.refused_shops(CFG, st, now=NOW + 4 * 3600)
        self.assertEqual(len(posts), 1)
        self.assertIn("Reading again", posts[0][0])
        self.assertIn("Rogue Online", posts[0][0])
        self.assertNotIn(ROGUE, st["shop_refused"])
        self.assertEqual(st["shop_refused_said"], [GUMNUT])

    def test_a_shop_that_answers_in_between_starts_over(self):
        st = {}
        run_check(refused=[ROGUE])
        tb.refused_shops(CFG, st, now=NOW)
        run_check(ok=[ROGUE])
        tb.refused_shops(CFG, st, now=NOW + 3600)
        run_check(refused=[ROGUE])
        self.assertEqual(tb.refused_shops(CFG, st, now=NOW + 2 * 3600 + 5), [])
        self.assertEqual(st["shop_refused"][ROGUE], NOW + 2 * 3600 + 5)

    def test_refused_and_answered_in_the_same_check_is_not_refused(self):
        st = {}
        run_check(refused=[ROGUE], ok=[ROGUE])
        tb.refused_shops(CFG, st, now=NOW)
        self.assertNotIn(ROGUE, st["shop_refused"])

    def test_a_new_refusal_posts_the_whole_list_again(self):
        st = {}
        run_check(refused=[ROGUE])
        tb.refused_shops(CFG, st, now=NOW)
        run_check(refused=[ROGUE])
        self.assertEqual(len(tb.refused_shops(CFG, st, now=NOW + 2 * 3600)), 1)
        run_check(refused=[ROGUE, GUMNUT])
        tb.refused_shops(CFG, st, now=NOW + 2 * 3600 + 60)
        run_check(refused=[ROGUE, GUMNUT])
        posts = tb.refused_shops(CFG, st, now=NOW + 4 * 3600 + 120)
        self.assertEqual(len(posts), 1)
        self.assertIn("Gumnut, Rogue Online", posts[0][0])

    def test_shop_off_the_list_is_forgotten(self):
        st = {"shop_refused": {"old.example.com": NOW - 99999}, "shop_refused_said": ["old.example.com"]}
        run_check()
        self.assertEqual(tb.refused_shops(CFG, st, now=NOW), [])
        self.assertEqual(st["shop_refused"], {})
        self.assertEqual(st["shop_refused_said"], [])

    def test_begin_check_clears_refused(self):
        run_check(refused=[ROGUE])
        with mock.patch.object(tb.HTTP, "reset_metrics"):
            try:
                tb.begin_check({"sealed": {"max_price": 300}}, {})
            except Exception:  # noqa: BLE001 - only the clearing at the top matters here
                pass
        self.assertEqual(tb._host_refused, set())


class Sweep(unittest.TestCase):
    Q = ["EB-05", "TS-03", "OP-18", "DP-13", "IB-09", "IB-10", "ST-37", "ST-38", "EB-06", "OP-19",
         "one piece pre-order", "one piece preorder"]

    def test_takes_turns_and_covers_every_search(self):
        seen = []
        for r in range(3):
            b = tb.sweep_batch({}, self.Q, round_no=r)
            self.assertEqual(len(b), tb.SWEEP_PER_RUN)
            seen += b
        self.assertEqual(sorted(seen), sorted(self.Q))

    def test_drop_window_code_is_always_asked(self):
        w = {"name": "OP-18 eve"}
        for r in range(5):
            b = tb.sweep_batch({}, self.Q, w, round_no=r)
            self.assertEqual(b[0], "OP-18")
            self.assertEqual(len(b), tb.SWEEP_PER_RUN)
            self.assertEqual(b.count("OP-18"), 1)

    def test_window_extra_codes(self):
        self.assertEqual(tb.window_codes({"name": "EB-06 eve", "codes": ["PRB-02", "op19"]}),
                         ["EB-06", "PRB-02", "OP-19"])
        self.assertEqual(tb.window_codes(None), [])

    def test_zero_means_all_and_short_lists_are_kept(self):
        self.assertEqual(tb.sweep_batch({"sweep_per_run": 0}, self.Q, round_no=1), self.Q)
        self.assertEqual(tb.sweep_batch({}, self.Q[:3], round_no=7), self.Q[:3])

    def test_counter_moves_on_its_own(self):
        tb._SWEEP_ROUND[0] = 0
        a = tb.sweep_batch({}, self.Q)
        b = tb.sweep_batch({}, self.Q)
        self.assertNotEqual(a, b)

    def test_sweep_jobs_use_the_batch_and_skip_no_sweep_shops(self):
        cfg = {"sealed": {"max_price": 300, "shopify_collections": [], "shopify_products": [],
                          "woocommerce": [], "shopify_search": [
                              {"name": "A", "base": "https://a.example.com"},
                              {"name": "B", "base": "https://b.example.com", "sweep": False}]},
               "extra_shops": False, "sweep_queries": ["PEB-01"]}
        tb._SWEEP_ROUND[0] = 0
        jobs = tb.sweep_jobs(cfg, 300, [], {"name": "OP-18 eve"})
        self.assertEqual([j[1] for j in jobs], ["A"])
        self.assertEqual(jobs[0][5][0], "OP-18")
        self.assertLessEqual(len(jobs[0][5]), tb.SWEEP_PER_RUN)

    def test_setting_is_known(self):
        self.assertIn("sweep_per_run", tb.KNOWN_SETTINGS)


class Groovy(unittest.TestCase):
    def test_quiet_one_search_no_sweep(self):
        g = [x for x in tb.EXTRA_SHOPIFY_SEARCH if x["name"] == "Groovy Collectables"]
        self.assertEqual(len(g), 1)
        self.assertTrue(g[0]["soft"])
        self.assertIs(g[0]["sweep"], False)
        self.assertEqual(g[0]["queries"], ["one piece booster box"])
        cfg = {"sealed": {"max_price": 300, "shopify_collections": [], "shopify_search": [],
                          "shopify_products": [], "woocommerce": []}}
        self.assertIn("Groovy Collectables", tb.soft_shop_names(cfg))
        self.assertNotIn("Groovy Collectables", [j[1] for j in tb.sweep_jobs(cfg, 300, [])])

    def test_check_sealed_passes_the_shop_queries(self):
        cfg = {"sealed": {"max_price": 300, "shopify_collections": [], "shopify_products": [], "woocommerce": [],
                          "shopify_search": [{"name": "G", "base": "https://g.example.com", "queries": ["q1"]},
                                             {"name": "H", "base": "https://h.example.com"}]},
               "extra_shops": False}
        calls = []

        def fake(shop, base, mx, watch, queries=None, page_no=1):
            calls.append((shop, queries))
            return [], []
        with mock.patch.object(tb, "shopify_search_boxes", fake), mock.patch.object(tb, "chain_shops", None), \
                mock.patch.object(tb, "neto_shops", None):
            tb.check_sealed(cfg)
        self.assertEqual(sorted(calls), [("G", ["q1"]), ("H", None)])


class OffGap(unittest.TestCase):
    def test_says_how_long(self):
        st = {"last_check": "2026-11-16 03:32:04"}
        note = tb.off_gap_note(st, now=datetime(2026, 11, 16, 14, 58))
        self.assertIn("11.4 hours", note)
        self.assertIn("Mon 16 Nov 03:32 AM", note)

    def test_days_and_minutes(self):
        self.assertIn("2.0 days", tb.off_gap_note({"last_check": "2026-11-12 00:03:36"},
                                                   now=datetime(2026, 11, 14, 0, 5)))
        self.assertIn("40 minutes", tb.off_gap_note({"last_check": "2026-11-16 03:00:00"},
                                                     now=datetime(2026, 11, 16, 3, 40)))

    def test_quiet_for_a_normal_restart_or_no_record(self):
        self.assertEqual(tb.off_gap_note({"last_check": "2026-11-16 03:32:04"},
                                         now=datetime(2026, 11, 16, 3, 40)), "")
        self.assertEqual(tb.off_gap_note({}), "")
        self.assertEqual(tb.off_gap_note({"last_check": "junk"}), "")


class PcBehind(unittest.TestCase):
    def test_posts_once_a_day_while_behind(self):
        st = {"pc_version": "2.25.0"}
        with mock.patch.object(tb, "VERSION", "2.27.0"):
            p = tb.pc_behind_post(st, True, now=NOW)
            self.assertIn("v2.25.0", p[0])
            self.assertIn("update_bot.bat", p[0])
            self.assertIsNone(tb.pc_behind_post(st, True, now=NOW + 3600))
            self.assertIsNotNone(tb.pc_behind_post(st, True, now=NOW + 25 * 3600))

    def test_quiet_when_current_off_or_unknown(self):
        with mock.patch.object(tb, "VERSION", "2.27.0"):
            self.assertIsNone(tb.pc_behind_post({"pc_version": "2.27.0"}, True, now=NOW))
            self.assertIsNone(tb.pc_behind_post({"pc_version": "2.28.0"}, True, now=NOW))
            self.assertIsNone(tb.pc_behind_post({"pc_version": "2.25.0"}, False, now=NOW))
            self.assertIsNone(tb.pc_behind_post({}, True, now=NOW))
            self.assertIsNone(tb.pc_behind_post({"pc_version": "?"}, True, now=NOW))

    def test_version_compare_is_numeric(self):
        self.assertLess(tb._version_tuple("2.9.0"), tb._version_tuple("2.10.0"))
        self.assertLess(tb._version_tuple("2.19.5"), tb._version_tuple("2.27.0"))


class QuietRepeat(unittest.TestCase):
    def test_default_is_three_hours(self):
        self.assertEqual(tb.soft_settings({})["repeat_hours"], 3.0)
        self.assertEqual(tb.soft_settings({"restock_alerts": {"repeat_hours": 24}})["repeat_hours"], 24.0)

    def test_second_restock_the_same_evening_posts(self):
        # X-Playground OP-18 came back at 17:40 and again at 19:43 on 15 Nov; the second one was dropped
        st = {}
        l = {"id": "open|list|X-Playground|op18|1", "box_id": "box|X-Playground|op18", "group": "box",
             "shop": "X-Playground", "opened": True, "name": "OP-18 Booster Box", "price": 399.95}
        cfg = {"sealed": {"max_price": 300, "shopify_collections": [{"name": "X-Playground", "url": "https://x/p",
                                                                     "soft": True}],
                          "shopify_search": [], "shopify_products": [], "woocommerce": []}, "extra_shops": False}
        self.assertEqual(len(tb.quieten(cfg, [l], st, now=NOW)), 1)
        self.assertEqual(len(tb.quieten(cfg, [l], st, now=NOW + 2 * 3600 + 3 * 60)), 0)
        self.assertEqual(len(tb.quieten(cfg, [l], st, now=NOW + 3 * 3600 + 60)), 1)


if __name__ == "__main__":
    unittest.main()
