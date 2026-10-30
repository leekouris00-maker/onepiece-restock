"""v2.10.1: "pause_shops" - a shop left alone until a date."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tcg_bot as tb  # noqa: E402


class PauseShops(unittest.TestCase):
    def cfg(self, **extra):
        return {"sealed": {"max_price": 260, "shopify_collections": [
            {"name": "Gumnut", "url": "https://g.test/collections/x/products.json"}]}, "singles": {"shops": {}, "cards": []}, **extra}

    def names(self, cfg):
        return sorted(x["name"] for g in tb.sealed_shops(cfg) for x in g)

    def test_default_pause_ends_on_its_date(self):
        self.assertIn("Light of Cards", tb.paused_shops({}, date(2026, 10, 31)))
        self.assertNotIn("Light of Cards", tb.paused_shops({}, date(2026, 11, 1)))

    def test_config_pauses_win_and_false_clears(self):
        self.assertEqual(tb.paused_shops({"pause_shops": {"Gumnut": "2099-01-01", "Light of Cards": "2000-01-01"}},
                                         date(2026, 10, 31)), {"Gumnut"})
        self.assertEqual(tb.paused_shops({"pause_shops": False}, date(2026, 10, 31)), set())

    def test_paused_shop_is_left_out_of_every_list(self):
        cfg = self.cfg(pause_shops={"Gumnut": "2099-01-01", "Grailborne": "2099-01-01"})
        tb.CONFIG_WARNINGS[:] = tb.check_config(cfg)
        self.assertEqual(tb.CONFIG_WARNINGS, [])
        names = self.names(cfg)
        self.assertNotIn("Gumnut", names)
        self.assertNotIn("Grailborne", names)
        self.assertIn("Cherry Collectables", names)
        self.assertEqual([j[1] for j in tb.sweep_jobs(cfg, 260, []) if j[1] in ("Gumnut", "Grailborne")], [])

    def test_bad_date_warns_and_does_not_pause(self):
        cfg = self.cfg(pause_shops={"Gumnut": "tomorrow"})
        w = tb.check_config(cfg)
        self.assertEqual(len(w), 1)
        self.assertIn("Gumnut", self.names(cfg))
        cfg = self.cfg(pause_shops=["Gumnut"])
        self.assertEqual(len(tb.check_config(cfg)), 1)
        self.assertIn("Gumnut", self.names(cfg))


if __name__ == "__main__":
    unittest.main()
