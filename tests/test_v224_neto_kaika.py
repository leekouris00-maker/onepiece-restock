"""v2.24: shops on Neto (Anime Kaika), read from the microdata in their pages. Fixtures follow Kaika's real
markup as seen on 16 Nov 2026. No network."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import link_watch as lw  # noqa: E402
import neto_shops as ns  # noqa: E402
import tcg_bot as tb  # noqa: E402

CAT = "https://www.kaika.com.au/trading-card-games-tcg/one-piece-card-game/"
OP18 = "https://www.kaika.com.au/pre-order-one-piece-card-game-booster-box-tba-op-1~356329"
OP19 = "https://www.kaika.com.au/one-piece-card-game-booster-box-tba-op-19"


def card(name, url, price, button):
    buy = {"cart": '<button type="button" title="Add to Cart" class="addtocart btn-info btn col-xs-10 btn-loads btn-lg" '
                   'rel="x" data-loading-text="<i class=\'fa fa-spinner fa-spin\'></i>">Add to Cart</button>',
           "store": '<input type="hidden" value="In-store only"> <a class="btn-info btn col-xs-10 btn-loads btn-lg" '
                    'href="/contact_us" title="In-store only">In-store only</a>',
           "none": ""}[button]
    return (f'<div class="thumbnail c_productThumbnail c_galleryThumbnail" itemscope itemtype="http://schema.org/Product"> '
            f'<a href="{url}" class="thumbnail-image"><img src="/a.jpg" alt="{name}"></a> <div class="caption"> '
            f'<h3 itemprop="name"><a href="{url}" title="{name}">{name[:50]}</a></h3> '
            f'<p class="price" itemprop="offers" itemscope itemtype="http://schema.org/Offer"> '
            f'<span itemprop="price">${price}</span> <meta itemprop="priceCurrency" content="AUD"> </p> </div> '
            f'<!-- Purchase Logic --> <form class="form-inline buying-options"> <input type="hidden" value="SKU"> {buy} </form> '
            f'<!-- /Purchase Logic --> <span nloader-content="xyz"></span></div>')


def category(*cards):
    return "<html><head><title>One Piece</title></head><body><div class='row'>" + "".join(cards) + "</div></body></html>"


def product(name, price, avail, label, desc="Bandai Card Games", related=""):
    return (f'<html><head><title>{name}</title><meta name="description" content="{name} - {desc}"/></head><body>'
            f'<div class="row" itemscope itemtype="http://schema.org/Product"><div itemscope itemtype="http://schema.org/Product">'
            f'<h1 itemprop="name">{name}</h1>'
            f'<div itemprop="offers" itemscope itemtype="http://schema.org/Offer" class="wrapper-pricing row"> '
            f'<meta itemprop="priceCurrency" content="AUD"> <div class="col-sm-6 c_pricingWrapper"> '
            f'<div class="productprice productpricetext" itemprop="price"> ${price} </div> </div> '
            f'<div class="c_stockBadge"> <span itemprop="availability" content="{avail}" class="labelicon">{label}</span> </div></div>'
            f'<span itemprop="productID">TCGOPEN00084B</span></div></div>{related}</body></html>')


BOX18 = "-PRE ORDER- One Piece Card Game: Booster Box - TBA [OP-18] [TCG]"
BOX19 = "One Piece Card Game: Booster Box - TBA [OP-19]"
SOLD18 = product(BOX18, "214.99", "out_of_stock", "Sold Out",
                 related=card("One Piece Card Game: Official Sleeves", "https://www.kaika.com.au/sleeves", "19.99", "cart"))
LIVE18 = product(BOX18, "214.99", "in_stock", "In Stock")
STORE19 = product(BOX19, "214.99", "in_stock", "In Stock",
                  desc="Bandai Card Games - Available from March 5, 2027 at Anime Kaika Burwood Store Only.")
SECTION = category(card("One Piece Card Game: Set Sail Deck Set [SD-01] [TCG]", "https://www.kaika.com.au/sd-01", "49.99", "store"),
                   card("One Piece Card Game: Official Sleeves Set 14 [TCG]", "https://www.kaika.com.au/sleeves-14", "19.99", "cart"),
                   card("One Piece Card Game: Booster Box - The Time Of Battle [OP-16] [TCG]", "https://www.kaika.com.au/op-16", "214.99", "cart"),
                   card("One Piece Card Game: Extra Booster Box - Anime 25th Collection [EB-02]", "/eb-02", "1,199.99", "none"))


class Parsing(unittest.TestCase):
    def test_category(self):
        rows = ns.parse_category(SECTION, CAT)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0], {"name": "One Piece Card Game: Set Sail Deck Set [SD-01] [TCG]", "url": "https://www.kaika.com.au/sd-01",
                                   "price": 49.99, "buyable": False, "store_only": True})
        self.assertEqual((rows[2]["name"], rows[2]["price"], rows[2]["buyable"]),
                         ("One Piece Card Game: Booster Box - The Time Of Battle [OP-16] [TCG]", 214.99, True))   # full name from title=""
        self.assertEqual((rows[3]["url"], rows[3]["price"], rows[3]["buyable"]), ("https://www.kaika.com.au/eb-02", 1199.99, False))
        self.assertEqual(ns.parse_category("<html>nothing</html>", CAT), [])

    def test_product_sold_out(self):
        r = ns.parse_product(SOLD18, OP18)
        self.assertEqual((r["name"], r["price"], r["currency"], r["buyable"], r["store_only"], r["status"]),
                         (BOX18, 214.99, "AUD", False, False, "sold out"))      # the related sleeves card isn't read as this product

    def test_product_in_stock(self):
        r = ns.parse_product(LIVE18, OP18)
        self.assertEqual((r["buyable"], r["status"]), (True, "in stock"))
        self.assertTrue(ns.parse_product(product(BOX18, "214.99", "http://schema.org/InStock", "In Stock"), OP18)["buyable"])

    def test_store_only_is_never_buyable(self):
        r = ns.parse_product(STORE19, OP19)
        self.assertEqual((r["buyable"], r["store_only"], r["status"]), (False, True, "in store only"))

    def test_a_changed_page_is_not_read_as_sold_out(self):
        self.assertIsNone(ns.parse_product("<html><h1>Page not found</h1></html>", OP18))
        self.assertIsNone(ns.parse_product(SOLD18.replace('itemprop="availability"', 'data-x="1"'), OP18))
        self.assertIsNone(ns.parse_product(SOLD18.replace("$214.99", "Call us"), OP18))

    def test_watch_links_can_read_kaika(self):
        r = lw.read(OP18, fetch=lambda u: LIVE18.encode())
        self.assertEqual((r["ok"], r["price"], r["buyable"], r["status"]), (True, 214.99, True, "in stock"))
        r = lw.read(OP19, fetch=lambda u: STORE19.encode())
        self.assertEqual((r["ok"], r["buyable"], r["status"]), (True, False, "in store only"))


class Settings(unittest.TestCase):
    def test_built_in_and_off_switches(self):
        self.assertEqual([s["name"] for s in ns.shops({})], ["Anime Kaika"])
        self.assertEqual(ns.shops({"neto_shops": False}), [])
        self.assertEqual(ns.shops({"extra_shops": False}), [])
        self.assertEqual(ns.hosts({}), {"www.kaika.com.au": "Anime Kaika"})
        for u in ns.SHOPS[0]["categories"] + ns.SHOPS[0]["products"]:
            self.assertTrue(u.startswith("https://www.kaika.com.au/"))
            self.assertNotIn("?", u)                       # robots.txt closes /*?*rf= (search): never used

    def test_own_shops(self):
        cfg = {"neto_shops": [{"name": "Mine", "categories": ["https://x.test/op/", "http://insecure/"]}, {"name": "bad"}]}
        got = {s["name"]: s for s in ns.shops(cfg)}
        self.assertEqual(sorted(got), ["Anime Kaika", "Mine"])
        self.assertEqual(got["Mine"]["categories"], ["https://x.test/op/"])
        self.assertEqual(len(ns.warnings(cfg)), 1)
        self.assertEqual(ns.warnings({}), [])
        self.assertEqual(len(ns.warnings({"neto_shops": "yes"})), 1)
        self.assertEqual([s["name"] for s in ns.shops(dict(cfg, extra_shops=False))], ["Mine"])
        self.assertFalse([w for w in tb.check_config({"singles": {}, "sealed": {}, "neto_shops": False}) if "neto" in w])


class Reading(unittest.TestCase):
    def setUp(self):
        self.pages = {CAT: SECTION, OP18: SOLD18, OP19: STORE19}
        self.asked, self.sleeps = [], []
        http = mock.Mock()
        http.fetch.side_effect = self.fetch
        for p in (mock.patch.object(tb, "HTTP", http), mock.patch.object(ns, "_sleep", self.sleeps.append),
                  mock.patch.object(tb, "_fail"), mock.patch.object(tb, "_say_once")):
            p.start()
            self.addCleanup(p.stop)
        self.shop = ns.SHOPS[0]

    def fetch(self, url, **kw):
        self.asked.append(url)
        page = self.pages.get(url)
        if isinstance(page, Exception):
            raise page
        return page.encode()

    def run_boxes(self):
        finds, listings = ns.boxes(tb, self.shop, 260.0, tb.DEFAULT_SEALED_WATCH)
        return finds, {l["name"]: l for l in listings or []} if listings is not None else None

    def test_sold_out_everywhere(self):
        finds, ls = self.run_boxes()
        self.assertEqual(self.asked, [CAT, OP18, OP19])
        self.assertEqual(self.sleeps, [1.0, 1.0])                         # the shop's Crawl-delay
        self.assertEqual([f["name"] for f in finds], ["One Piece Card Game: Booster Box - The Time Of Battle [OP-16] [TCG]"])
        self.assertEqual((ls[BOX18]["available"], ls[BOX18]["price"], ls[BOX18]["group"], ls[BOX18]["note"]), (False, 214.99, "box", "pre-order"))
        self.assertEqual((ls[BOX19]["available"], ls[BOX19]["note"]), (False, "in-store only, not sold online"))
        self.assertNotIn("One Piece Card Game: Official Sleeves Set 14 [TCG]", ls)        # sleeves aren't watched
        self.assertNotIn("One Piece Card Game: Extra Booster Box - Anime 25th Collection [EB-02]",
                         [f["name"] for f in finds])                                      # no button, over max
        for l in ls.values():
            self.assertEqual((l["shop"], l["cart"], l["page"], l["kind"]), ("Anime Kaika", "", 1, "New listing"))
            self.assertTrue(l["id"].startswith("list|Anime Kaika|"))

    def test_op18_comes_into_stock(self):
        self.pages[OP18] = LIVE18
        finds, ls = self.run_boxes()
        f = next(x for x in finds if x["name"] == BOX18)
        self.assertEqual((f["kind"], f["price"], f["url"], f["shop"]), ("Booster box", 214.99, OP18, "Anime Kaika"))
        self.assertEqual(f["id"], ls[BOX18]["box_id"])
        self.assertTrue(ls[BOX18]["available"])

    def test_store_only_box_never_alerts(self):
        finds, _ = self.run_boxes()
        self.assertNotIn(BOX19, [f["name"] for f in finds])

    def test_product_page_wins_over_the_section_card(self):
        self.pages[CAT] = category(card(BOX19, OP19, "214.99", "cart"))    # the card alone would look buyable online
        finds, ls = self.run_boxes()
        self.assertFalse(ls[BOX19]["available"])
        self.assertEqual(finds, [])

    def test_nothing_readable_means_unknown_not_empty(self):
        for url in self.pages:
            self.pages[url] = OSError("down")
        self.assertEqual(ns.boxes(tb, self.shop, 260.0), ([], None))

    def test_told_to_stop_asks_no_more(self):
        self.pages[CAT] = tb.HttpError(429, "Too Many Requests")
        self.assertEqual(ns.boxes(tb, self.shop, 260.0), ([], None))
        self.assertEqual(self.asked, [CAT])

    def test_quiet_period_and_robots(self):
        self.pages[CAT] = tb.SkipHost("www.kaika.com.au")
        self.assertEqual(ns.boxes(tb, self.shop, 260.0), ([], None))
        self.assertEqual(self.asked, [CAT])
        self.asked.clear()
        self.pages[CAT] = tb.RobotsDisallowed(CAT)
        finds, ls = ns.boxes(tb, self.shop, 260.0)
        self.assertEqual(len(self.asked), 3)                              # the product pages are still read
        self.assertEqual(len(ls), 2)

    def test_one_page_failing_keeps_the_rest(self):
        self.pages[OP18] = OSError("timeout")
        _, ls = self.run_boxes()
        self.assertIn(BOX19, ls)
        self.assertNotIn(BOX18, ls)


class InTheCheck(unittest.TestCase):
    CFG = {"sealed": {"max_price": 260}, "extra_shops": True, "sweep": False, "chain_shops": False}

    def jobs(self, cfg):
        seen = []
        with mock.patch.object(tb, "pmap", side_effect=lambda fn, jobs, **k: seen.extend(jobs) or []), \
                mock.patch.object(tb, "sealed_shops", return_value=([], [], [], [])):
            tb.check_sealed(cfg)
        return [j for j in seen if j[0] is tb.neto_boxes]

    def test_kaika_is_a_sealed_job(self):
        js = self.jobs(self.CFG)
        self.assertEqual([(j[1], j[3]) for j in js], [("Anime Kaika", 260)])
        self.assertIn("www.kaika.com.au", tb.shop_names({"sealed": {}, "pokemon": False}))

    def test_off_and_paused(self):
        self.assertEqual(self.jobs(dict(self.CFG, neto_shops=False)), [])
        self.assertEqual(self.jobs(dict(self.CFG, pause_shops={"Anime Kaika": "2999-01-01"})), [])

    def test_updater_knows_the_file(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "update_files.txt"), encoding="utf-8") as f:
            self.assertIn("neto_shops.py", f.read().split())


if __name__ == "__main__":
    unittest.main()
