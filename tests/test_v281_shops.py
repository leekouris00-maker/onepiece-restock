"""v2.8.1: shops added from the Fellowship of the Ping list (24 Oct 2026), and booster boxes listed at a
pre-order deposit price don't alert as cheap boxes. Titles and prices are real ones seen that day.
No network.

Run:  python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402

CFG = {"sealed": {"max_price": 260, "shopify_collections": [], "woocommerce": []}}


def woo(pid, name, price_cents, in_stock):
    return {"id": pid, "name": name, "permalink": f"https://cardplustcg.com.au/product/{pid}",
            "is_in_stock": in_stock, "is_purchasable": True,
            "prices": {"price": str(price_cents), "currency_minor_unit": 2}}


class NewShops(unittest.TestCase):
    def test_new_shops_are_checked(self):
        cols, prods, woos, _ = tb.sealed_shops(CFG)
        names = {s["name"] for s in cols + prods + woos}
        for n in ("Goldfields Games", "Rogue Online", "The Wandering Collector", "Overhauled Games", "CardPlus TCG"):
            self.assertIn(n, names)
        self.assertTrue(any("op-18" in p["url"] for p in prods))

    def test_config_entries_win_and_extra_shops_can_be_switched_off(self):
        cfg = {"sealed": {"max_price": 260, "woocommerce": [{"name": "CardPlus TCG", "url": "https://x/y"}]}}
        _, _, woos, _ = tb.sealed_shops(cfg)
        self.assertEqual([w["url"] for w in woos if w["name"] == "CardPlus TCG"], ["https://x/y"])
        _, prods, woos, _ = tb.sealed_shops(dict(CFG, extra_shops=False))
        self.assertEqual((prods, woos), ([], []))

    def test_shop_names_know_the_new_hosts(self):
        names = tb.shop_names(dict(CFG, singles={"shops": {}}))
        self.assertEqual(names.get("goldfieldsgames.com.au"), "Goldfields Games")
        self.assertEqual(names.get("overhauledgames.com.au"), "Overhauled Games")


class Deposits(unittest.TestCase):
    def setUp(self):
        self._fetch, self._sweep = tb.fetch_json, tb.SWEPT.copy()
        tb.SEALED_OPTS.update(new=True, packs=False)

    def tearDown(self):
        tb.fetch_json = self._fetch

    def run_woo(self, items):
        tb.fetch_json = lambda url, tries=tb.HTTP_TRIES: items
        cfg = {"sealed": {"max_price": 260, "woocommerce": [{"name": "CardPlus TCG", "url": "https://cardplustcg.com.au/x"}]},
               "extra_shops": False}
        return tb.check_sealed(cfg)

    def test_deposit_priced_boxes_dont_alert_but_real_ones_do(self):
        finds, by_shop = self.run_woo([
            woo(1, "One Piece Card Game: Extra Booster Display – TBA [EB-06] (PRE-ORDER) 29 Jan 2027", 3500, True),
            woo(2, "One Piece Card Game: Booster Box OP-20 Pre-Order Deposit Only", 9900, True),
            woo(3, "One Piece CG OP-19 Booster Display Box (English) &#8211; Release Date 5 Mar 2027", 25000, True),
            woo(4, "One Piece CG OP-13 Booster Display Box (English)", 85000, True),
        ])
        self.assertEqual([f["id"] for f in finds], ["box|CardPlus TCG|3"])
        self.assertEqual(len(by_shop["CardPlus TCG"]), 4)        # all still tracked as listings

    def test_asia_and_japanese_boxes_never_alert(self):
        finds, _ = self.run_woo([
            woo(5, "OP-13 Carrying On His Will Booster Box (For Asia Edition) – English One Piece TCG", 19995, True),
            woo(6, "OP-16 The Time of Battle Booster Box – Japanese One Piece TCG", 16995, True),
        ])
        self.assertEqual(finds, [])


if __name__ == "__main__":
    unittest.main()
