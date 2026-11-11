"""v2.19.1: promo singles were posted as sealed "Heroines Gift Collection" finds. Titles are the real ones
from Cherry Collectables, GUF and Grailborne on 11 Nov 2026. No network.

Run:  python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402

WATCH = tb.DEFAULT_SEALED_WATCH


class PromoSingles(unittest.TestCase):
    def setUp(self):
        tb.SEALED_OPTS.update(new=True, packs=False)

    def group(self, title, variants=None):
        c = tb.classify(title, WATCH, 260, variants)
        return c[2] if c else None

    def test_gift_collection_promo_singles_are_not_sealed(self):
        for t in ("Trafalgar Law - ST03-008 - One Piece Gift Collection 2023 Promo",
                  "Yamato - ST09-012 - One Piece Gift Collection 2023 Promo",
                  "Boa Hancock (Gift Collection 2023) [One Piece Promotion Cards]",
                  "Nami (Gift Collection 2026) [One Piece Promotion Cards]",
                  "Uta (Gift Collection - Heroines)"):
            self.assertIsNone(self.group(t), t)
            self.assertIsNone(tb.watch_item(t, WATCH), t)

    def test_the_real_sealed_products_still_match(self):
        for t in ("*Pre-order* One Piece Card Game: Gift Collection – Heroines (GC 2026) (20th November)",
                  "One Piece Card Game Heroines Gift Collection",
                  "One Piece Card Game: Premium Card Collection - 29th Anniversary Edition "
                  "(P-159 Monkey D. Luffy, 8 Cards) (Ships March 2027)",
                  "One Piece Card Game Double Pack Set Vol.13 (DP-13)",
                  "One Piece Card Game Starter Deck – TBA - ST-37 (Preorder)"):
            self.assertEqual(self.group(t), "watch", t)

    def test_older_gift_collection_is_not_the_heroines_one(self):
        self.assertIsNone(tb.watch_item("One Piece Card Game Gift Collection 2023 (GC-01)", WATCH))

    def test_promo_packs_stay_sealed_and_condition_variants_are_singles(self):
        self.assertFalse(tb.looks_like_single("One Piece Card Game Promotion Pack Vol. 3"))
        self.assertIsNone(self.group("One Piece Card Game Heroines Gift Collection",
                                     [{"title": "Near Mint"}, {"title": "Lightly Played"}]))
