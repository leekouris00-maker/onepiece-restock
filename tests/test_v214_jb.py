"""v2.14: JB Hi-Fi (chain_shops.py). Formats are the real ones read from JB on 10 Nov 2026. No network."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402
import chain_shops as cs  # noqa: E402

WATCH = tb.DEFAULT_SEALED_WATCH
EB03 = cs.JB_SEEDS[0]
INDEX = """<?xml version="1.0"?><sitemapindex>
<sitemap><loc>https://www.jbhifi.com.au/sitemap_agentic_discovery.xml</loc></sitemap>
<sitemap><loc>https://www.jbhifi.com.au/sitemap_products_1.xml?from=1&amp;to=2</loc></sitemap>
<sitemap><loc>https://www.jbhifi.com.au/sitemap_products_2.xml?from=3&amp;to=4</loc></sitemap>
<sitemap><loc>https://www.jbhifi.com.au/sitemap_products_3.xml?from=5&amp;to=6</loc></sitemap>
<sitemap><loc>https://www.jbhifi.com.au/sitemap_collections_1.xml?from=1&amp;to=2</loc></sitemap></sitemapindex>"""


def sitemap(*handles):
    return "<urlset>" + "".join(f"<url><loc>https://www.jbhifi.com.au/products/{h}</loc>"
                                f"<lastmod>2026-11-10T09:04:30+11:00</lastmod></url>" for h in handles) + "</urlset>"


def js(handle, title, sellers, tags=("Brand:One Piece",)):
    """sellers: [(name, cents, available)]; a product JB sells itself has one "Default Title" variant."""
    opts = [{"name": "Seller", "position": 1, "values": [s[0] for s in sellers]}] if sellers[0][0] != "Default Title" \
        else [{"name": "Title", "position": 1, "values": ["Default Title"]}]
    return {"title": title, "handle": handle, "type": "MOVIES", "tags": list(tags), "options": opts,
            "variants": [{"id": 1000 + i, "title": n, "public_title": n, "price": c, "available": a}
                         for i, (n, c, a) in enumerate(sellers)]}


class Parsing(unittest.TestCase):
    def test_product_sitemaps_newest_first(self):
        self.assertEqual(cs.product_sitemaps(INDEX),
                         ["https://www.jbhifi.com.au/sitemap_products_3.xml?from=5&to=6",
                          "https://www.jbhifi.com.au/sitemap_products_2.xml?from=3&to=4",
                          "https://www.jbhifi.com.au/sitemap_products_1.xml?from=1&to=2"])

    def test_only_one_piece_products(self):
        self.assertEqual(cs.handles_in_sitemap(sitemap("megahouse-lookup-kaito", "one-piece-card-game-op-18-booster-box",
                                                       "one-piece-grandista-portgas-d-ace-figure-figure")),
                         ["one-piece-card-game-op-18-booster-box", "one-piece-grandista-portgas-d-ace-figure-figure"])


class Jb(unittest.TestCase):
    def setUp(self):
        tb.SEALED_OPTS.update(new=True, packs=False)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.pages = {
            cs.JB_FEED: {"products": [{"handle": "rugby-league-26", "title": "Rugby League 26"}]},
            cs.JB_SITEMAP: INDEX,
            "https://www.jbhifi.com.au/sitemap_products_3.xml?from=5&to=6": sitemap("megahouse-lookup-kaito"),
            "https://www.jbhifi.com.au/sitemap_products_2.xml?from=3&to=4": sitemap(
                "one-piece-card-game-st-21-starter-deck", "one-piece-collection-12-blu-ray-box"),
            "https://www.jbhifi.com.au/sitemap_products_1.xml?from=1&to=2": sitemap("one-piece-card-game-op-13-booster-box"),
            self.url(EB03): js(EB03, "One Piece Card Game Extra Booster Display Heroines Edition Box 24 Pack EB-03",
                               [("Gameology", 79915, True), ("SuperGamers", 21400, True)]),
            self.url("one-piece-card-game-st-21-starter-deck"): js(
                "one-piece-card-game-st-21-starter-deck", "One Piece Card Game ST-21 Starter Deck EX Gear 5",
                [("Default Title", 2900, False)]),
            self.url("one-piece-collection-12-blu-ray-box"): js(
                "one-piece-collection-12-blu-ray-box", "One Piece Collection 12 Blu-ray Box", [("Default Title", 4998, True)]),
            self.url("one-piece-card-game-op-13-booster-box"): js(
                "one-piece-card-game-op-13-booster-box", "One Piece Card Game OP-13 Carrying On His Will Booster Box",
                [("Default Title", 29900, True)]),
        }
        self.asked = []
        for p in (mock.patch.object(tb, "HERE", self.dir.name), mock.patch.object(tb.HTTP, "fetch", side_effect=self.fetch),
                  mock.patch.dict(os.environ, {"BOT_CHAIN_SHOPS": "on"})):
            p.start()
            self.addCleanup(p.stop)

    @staticmethod
    def url(handle):
        return f"{cs.JB_BASE}/products/{handle}.js"

    def fetch(self, url, *a, **k):
        self.asked.append(url)
        page = self.pages.get(url)
        if page is None:
            raise tb.HttpError(404, "Not Found")
        if isinstance(page, Exception):
            raise page
        return (page if isinstance(page, str) else json.dumps(page)).encode()

    def read(self, now, fast=False):
        return cs.jb_boxes(tb, 260, WATCH, fast=fast, now=now)

    def state(self):
        return json.load(open(os.path.join(self.dir.name, cs.STATE_NAME)))[cs.JB_NAME]

    def test_first_reading(self):
        finds, listings = self.read(1000)
        self.assertEqual([f["id"] for f in finds], [f"box|JB Hi-Fi|{EB03}"])      # A$214 from SuperGamers, under the max
        f = finds[0]
        self.assertEqual((f["price"], f["kind"], f["shop"]), (214.0, "Booster box", "JB Hi-Fi"))
        self.assertIn("sold by SuperGamers on JB Marketplace", f["note"])
        self.assertEqual(f["cart"], "https://www.jbhifi.com.au/cart/1001:1")
        self.assertEqual(f["url"], f"https://www.jbhifi.com.au/products/{EB03}")
        # the two newest sitemap files were read: the starter deck is listed (not buyable), the Blu-ray isn't a card product
        self.assertEqual(sorted(l["id"] for l in listings),
                         [f"list|JB Hi-Fi|{EB03}", "list|JB Hi-Fi|one-piece-card-game-st-21-starter-deck"])
        self.assertTrue(all(l.get("quiet") for l in listings))
        st = self.state()
        self.assertEqual(st["handles"]["one-piece-collection-12-blu-ray-box"], {"ok": False})
        self.assertEqual((st["cursor"], st["files"]), (2, 3))

    def test_between_readings_nothing_is_asked_and_nothing_changes(self):
        first = self.read(1000)
        self.asked.clear()
        again = self.read(1000 + cs.REFRESH - 5)
        self.assertEqual(self.asked, [])
        self.assertEqual([f["id"] for f in again[0]], [f["id"] for f in first[0]])
        self.assertEqual(sorted(l["id"] for l in again[1]), sorted(l["id"] for l in first[1]))
        self.read(1000 + 130, fast=True)             # a drop window's 2-minute sweep reads again
        self.assertIn(cs.JB_FEED, self.asked)

    def test_backfill_carries_on_and_stays_quiet_but_buyable_boxes_alert(self):
        known = {}
        tb.new_listings({"JB Hi-Fi": self.read(1000)[1]}, known, [])                   # first read: remember
        self.pages[self.url("one-piece-card-game-op-13-booster-box")]["variants"][0]["price"] = 25900
        finds, listings = self.read(2000)            # third sitemap file: the OP-13 box at A$259
        op13 = [l for l in listings if "op-13" in l["id"]][0]
        self.assertTrue(op13.get("quiet"))
        self.assertIn("box|JB Hi-Fi|one-piece-card-game-op-13-booster-box", [f["id"] for f in finds])
        self.assertEqual(tb.new_listings({"JB Hi-Fi": listings}, known, []), [])      # remembered, not announced
        self.assertIn(op13["id"], known["JB Hi-Fi"])

    def test_a_new_product_in_the_feed_alerts_as_a_new_listing(self):
        _, listings = self.read(1000)
        known = {}
        tb.new_listings({"JB Hi-Fi": listings}, known, [])                             # first read: remember
        h = "one-piece-card-game-op-19-booster-box"
        self.pages[cs.JB_FEED]["products"].insert(0, {"handle": h, "title": "One Piece Card Game OP-19 Booster Box"})
        self.pages[self.url(h)] = js(h, "One Piece Card Game OP-19 Booster Box", [("Default Title", 34900, False)],
                                     tags=("Brand:One Piece", "Preorder"))
        finds, listings = self.read(2000)
        new = tb.new_listings({"JB Hi-Fi": listings}, known, finds)
        self.assertEqual([l["id"] for l in new], [f"list|JB Hi-Fi|{h}"])
        self.assertIn("listed, not buyable yet", new[0]["note"])
        self.assertEqual(new[0]["price"], 349.0)
        self.assertEqual(tb.new_listings({"JB Hi-Fi": self.read(2100)[1]}, known, []), [])   # not again from the replay

    def test_jb_not_answering_keeps_the_last_reading_then_gives_up(self):
        first = self.read(1000)
        self.pages[self.url(EB03)] = tb.HttpError(503, "Service Unavailable")
        with mock.patch.object(tb, "_fail"):
            kept = self.read(2000)
            self.assertEqual([f["id"] for f in kept[0]], [f["id"] for f in first[0]])
            self.assertEqual(self.read(1000 + cs.STALE + 10), ([], None))

    def test_a_removed_product_is_dropped_after_three_misses(self):
        self.read(1000)
        del self.pages[self.url(EB03)]
        for i in range(1, 4):
            finds, listings = self.read(1000 + i * 700)
            self.assertEqual(finds, [])
        self.assertEqual(self.state()["handles"][EB03], {"ok": False})

    def test_everything_down_on_the_first_reading(self):
        self.pages = {k: tb.HttpError(503, "x") for k in self.pages}
        with mock.patch.object(tb, "_fail"):
            self.assertEqual(self.read(1000), ([], None))

    def test_check_sealed_includes_jb_and_can_switch_it_off(self):
        cfg = {"sealed": {"max_price": 260}, "extra_shops": False}
        finds, by_shop = tb.check_sealed(cfg)
        self.assertEqual([f["shop"] for f in finds], ["JB Hi-Fi"])
        self.assertEqual(len(by_shop["JB Hi-Fi"]), 2)
        self.assertEqual(tb.shop_names(cfg).get("www.jbhifi.com.au"), "JB Hi-Fi")
        for off in ({"chain_shops": False}, {"pause_shops": {"JB Hi-Fi": "2099-01-01"}}):
            finds, by_shop = tb.check_sealed(dict(cfg, **off))
            self.assertEqual((finds, by_shop), ([], {}))


if __name__ == "__main__":
    unittest.main()
