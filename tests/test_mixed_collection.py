"""A shop whose only list mixes games (Gametraders Modbury Heights' "trading-cards"): with "must_include"
only One Piece titles count, so its Yu-Gi-Oh and Pokémon boxes never alert as One Piece. No network.

Run:  python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402

URL = "https://www.gametradersinglefarm.com.au/collections/trading-cards/products.json?limit=250"


def product(handle, title, price, available):
    return {"handle": handle, "title": title, "tags": ["One Piece"] if "One Piece" in title else [],
            "variants": [{"id": abs(hash(handle)) % 10 ** 14, "price": f"{price:.2f}", "available": available}]}


PAGE = {"products": [
    product("eb05", "*Pre-order* One Piece Card Game: Extra Booster Box – TBA (EB-05) (30th October)", 214.99, True),
    product("op18", "*Pre-order* One Piece Card Game: Booster Display – TBA (OP-18) (20th November)", 214.99, False),
    product("ygo", "Yugioh - Phantom Revenge Booster Box", 129.99, True),
    product("pkm", "Pokemon TCG: Mega Evolution Pitch Black Booster Box", 319.99, True),
    product("gift", "*Pre-order* One Piece Card Game: Gift Collection – Heroines (GC 2026) (20th November)", 129.99, False),
]}


class MixedCollection(unittest.TestCase):
    def setUp(self):
        self._fetch = tb.fetch_json
        self.asked = []

        def fetch(url, tries=tb.HTTP_TRIES):
            self.asked.append(url)
            return PAGE if "page=" not in url else {"products": []}
        tb.fetch_json = fetch
        tb.PAGE_HINTS.clear()

    def tearDown(self):
        tb.fetch_json = self._fetch
        tb.PAGE_HINTS.clear()
        tb.HTTP.gzip_urls.discard(URL.split("?")[0])

    def test_only_one_piece_titles_count(self):
        finds, listings = tb.shopify_boxes("Gametraders Modbury Heights", URL, 260, tb.DEFAULT_SEALED_WATCH,
                                           ["one piece"], 2)
        self.assertEqual([f["name"][:40] for f in finds], ["*Pre-order* One Piece Card Game: Extra B"])
        self.assertEqual(finds[0]["cart"].split("/cart/")[0], "https://www.gametradersinglefarm.com.au")
        self.assertEqual(sorted(l["box_id"].split("|")[-1] for l in listings), ["eb05", "gift", "op18"])
        self.assertTrue(all("one piece" in l["name"].lower() for l in listings))

    def test_without_it_other_games_would_alert(self):
        finds, _ = tb.shopify_boxes("Gametraders Modbury Heights", URL, 260, tb.DEFAULT_SEALED_WATCH)
        self.assertIn("Yugioh - Phantom Revenge Booster Box", [f["name"] for f in finds])

    def test_check_sealed_passes_the_settings_on(self):
        cfg = {"sealed": {"max_price": 260, "shopify_collections": [
            {"name": "Gametraders Modbury Heights", "url": URL, "must_include": "one piece", "max_pages": 2,
             "gzip": True}]}, "extra_shops": False}
        self.assertEqual(tb.check_config(cfg), [])
        finds, by_shop = tb.check_sealed(cfg)
        self.assertEqual([f["id"] for f in finds], ["box|Gametraders Modbury Heights|eb05"])
        self.assertEqual(len(by_shop["Gametraders Modbury Heights"]), 3)
        self.assertIn(URL.split("?")[0], tb.HTTP.gzip_urls)


class ConfigCheck(unittest.TestCase):
    def check(self, **extra):
        cfg = {"sealed": {"max_price": 260, "shopify_collections": [
            dict({"name": "GT", "url": URL}, **extra)]}}
        return tb.check_config(cfg), cfg["sealed"]["shopify_collections"]

    def test_a_word_becomes_a_list(self):
        warnings, shops = self.check(must_include="one piece", max_pages="2")
        self.assertEqual(warnings, [])
        self.assertEqual(shops[0]["must_include"], ["one piece"])
        self.assertEqual(shops[0]["max_pages"], 2)

    def test_a_broken_filter_skips_the_shop_instead_of_alerting_on_everything(self):
        warnings, shops = self.check(must_include=["one piece", 3])
        self.assertEqual(shops, [])
        self.assertIn("must_include", warnings[0])

    def test_max_pages_is_kept_sensible(self):
        self.assertEqual(self.check(max_pages=50)[1][0]["max_pages"], 8)
        warnings, shops = self.check(max_pages="lots")
        self.assertNotIn("max_pages", shops[0])
        self.assertIn("max_pages", warnings[0])

    def test_the_real_config_loads_cleanly(self):
        cfg = tb.load_config()
        self.assertEqual(tb.CONFIG_WARNINGS, [])
        gt = [s for s in cfg["sealed"]["shopify_collections"] if s["name"] == "Gametraders Modbury Heights"]
        self.assertEqual(gt[0]["must_include"], ["one piece"])


if __name__ == "__main__":
    unittest.main()
