"""v2.19.2: singles listed "Card Name [Set Name]" were posted as new sealed listings, because the set name
in square brackets has "Booster" in it. Titles are the real ones from GUF, 13 Nov 2026. No network.

Run:  python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402

WATCH = tb.DEFAULT_SEALED_WATCH


class BracketSingles(unittest.TestCase):
    def setUp(self):
        tb.SEALED_OPTS.update(new=True, packs=False)

    def kind(self, title):
        c = tb.classify(title, WATCH, 260)
        return c[0] if c else None

    def test_set_name_in_square_brackets_is_a_single(self):
        for t in ("My name is Shirahoshi!! [Extra Booster: One Piece Heroines Edition Vol. 2]",
                  "Alvida [Extra Booster: One Piece Heroines Edition Vol. 2]",
                  "Nico Robin (SP) [Extra Booster: One Piece Heroines Edition Vol. 2]",
                  "Fight and Die with Me!!! [Extra Booster: One Piece Heroines Edition Vol. 2]",
                  "Yamato [Extra Booster: One Piece Heroines Edition Vol. 2]",
                  "Buggy [Premium Booster -The Best-]"):
            self.assertIsNone(self.kind(t), t)

    def test_sealed_with_code_in_brackets_still_alerts(self):
        for t in ("One Piece Card Game - Double Pack Display TBA [DP-12]",
                  "One Piece Card Game: Starter Deck - Ace & Newgate [ST-22]",
                  "One Piece Card Game [ English Version 2nd Anniversary Set ]",
                  "One Piece Card Game: Extra Booster - Heroines Edition vol.2 Display – TBA [EB-05]",
                  "ONE PIECE TCG: TS-02 Tin Pack Set Vol. 2 - Master Case [48 Tins]",
                  "One Piece TCG [Starter Deck ST-30]"):
            self.assertIsNotNone(self.kind(t), t)

    def test_boxes_unchanged(self):
        self.assertEqual(self.kind("ONE PIECE CARD GAME - [EB-05] HEROINES VOL.2 BOOSTER BOX"), "Booster box")


if __name__ == "__main__":
    unittest.main()
