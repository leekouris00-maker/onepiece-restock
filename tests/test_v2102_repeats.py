"""v2.10.2: no Gundam (or other games') boxes, and no repeat alerts for cents-level price wobble."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tcg_bot as tb  # noqa: E402

WATCH = tb.DEFAULT_SEALED_WATCH


def f(id_, price):
    return {"id": id_, "price": price}


class OtherGames(unittest.TestCase):
    def test_gundam_box_ignored(self):
        t = "PRE-ORDER GUNDAM CARD GAME [GD06] BOOSTER BOX"
        self.assertFalse(tb.is_box_title(t))
        self.assertIsNone(tb.classify(t, WATCH, 260))

    def test_other_games_ignored(self):
        for t in ("Yu-Gi-Oh! Phantom Revenge Booster Box", "Dragon Ball Super Fusion World FB05 Booster Box",
                  "Digimon Card Game BT20 Booster Box", "Union Arena Booster Box Jujutsu Kaisen"):
            self.assertIsNone(tb.classify(t, WATCH, 260), t)

    def test_one_piece_boxes_still_count(self):
        for t in ("One Piece Card Game - The World's Strongest Warriors Booster Box [OP-17]",
                  "OP-14 Booster Box English", "ONE PIECE CARD GAME - [EB-05] HEROINES VOL.2 BOOSTER BOX"):
            self.assertTrue(tb.is_box_title(t), t)

    def test_illustration_box_only_new_ones(self):
        old = "One Piece Card Game: Illustration Box Vol.7 (IB-07) - English Sealed"
        self.assertIsNone(tb.watch_item(old, WATCH))
        self.assertIsNotNone(tb.watch_item("One Piece Card Game Illustration Box Vol.9 [IB-09]", WATCH))
        self.assertIsNotNone(tb.watch_item("One Piece Card Game Illustration Box Vol 10", WATCH))


class Repeats(unittest.TestCase):
    def test_new_item_alerts(self):
        self.assertEqual(len(tb.new_only([f("card|x", 80)], {})), 1)

    def test_cents_wobble_doesnt_alert(self):
        self.assertEqual(tb.new_only([f("card|x", 82.2)], {"card|x": 83.1}), [])
        self.assertEqual(tb.new_only([f("ebay|1", 265.88)], {"ebay|1": 275.43}), [])   # 3.5%, FX

    def test_real_drop_alerts(self):
        self.assertEqual(len(tb.new_only([f("box|a", 230)], {"box|a": 260})), 1)
        self.assertEqual(len(tb.new_only([f("card|x", 30)], {"card|x": 40})), 1)

    def test_cooldown_after_dropping_out(self):
        now = 1_000_000
        recent = tb.remember_alerts({}, [f("card|x", 80.7)], now=now)
        # forgotten from seen.json (page didn't load), back the next day at the same price: quiet
        self.assertEqual(tb.new_only([f("card|x", 80.7)], {}, recent, now=now + 20 * 3600), [])
        # after the cool-down it's a fresh alert again
        self.assertEqual(len(tb.new_only([f("card|x", 80.7)], {}, recent, now=now + 30 * 3600)), 1)

    def test_box_restock_still_alerts_soon(self):
        now = 1_000_000
        recent = tb.remember_alerts({}, [f("box|s|h", 199)], now=now)
        self.assertEqual(tb.new_only([f("box|s|h", 199)], {}, recent, now=now + 600), [])          # a blip
        self.assertEqual(len(tb.new_only([f("box|s|h", 199)], {}, recent, now=now + 3 * 3600)), 1)  # a restock

    def test_settings_from_config(self):
        rs = tb.repeat_settings({"alerts": {"repeat_drop_pct": 1, "repeat_drop_min": 0}})
        self.assertEqual(len(tb.new_only([f("card|x", 82.0)], {"card|x": 83.1}, rs=rs)), 1)


class GroupMove(unittest.TestCase):
    def test_product_moving_group_isnt_new(self):
        l = {"id": "list|Grailborne|ib-07", "box_id": "sealed|Grailborne|ib-07", "group": "new", "kind": "New listing",
             "name": "Illustration Box Vol.7 (IB-07)", "shop": "Grailborne", "price": 69.0, "available": True,
             "url": "u", "cart": "", "note": "", "max": 0, "page": 1}
        known = {"Grailborne": [], "Grailborne (other sealed)": ["list|Grailborne|ib-07"],
                 "Grailborne (all sealed)": []}
        self.assertEqual(tb.new_listings({"Grailborne": [l]}, known, []), [])
        known = {"Grailborne": [], "Grailborne (other sealed)": [], "Grailborne (all sealed)": []}
        self.assertEqual(len(tb.new_listings({"Grailborne": [l]}, known, [])), 1)


if __name__ == "__main__":
    unittest.main()
