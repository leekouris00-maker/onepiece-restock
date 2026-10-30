"""Tests for link_watch.py (/watch) and the /watch wiring in tcg_bot.py. No network: pages are canned.

Run:  python -m unittest discover -s tests
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import link_watch as lw  # noqa: E402
import tcg_bot as tb  # noqa: E402


def shopify_js(title, variants):
    return json.dumps({"title": title, "variants": [
        {"id": vid, "title": vt, "price": int(round(p * 100)), "available": av} for vid, vt, p, av in variants]}).encode()


def ld_page(obj, extra=""):
    return (f"<html><head><title>Shop</title>{extra}<script type=\"application/ld+json\">{json.dumps(obj)}</script>"
            "</head><body>hi</body></html>").encode()


class FakeWeb:
    """fetch(url) -> bytes from a dict; anything else raises like a 404."""

    def __init__(self, pages):
        self.pages, self.asked = dict(pages), []

    def __call__(self, url):
        self.asked.append(url)
        if url in self.pages:
            v = self.pages[url]
            if isinstance(v, Exception):
                raise v
            return v
        err = OSError("HTTP 404")
        err.code = 404
        raise err


class Robots(Exception):
    pass


Robots.__name__ = "RobotsDisallowed"


# ---------------------------------------------------------------- reading pages
class ShopifyPages(unittest.TestCase):
    URL = "https://www.gumnut.com.au/products/op15-booster-box?utm_source=discord#reviews"

    def test_in_stock_cheapest_buyable_variant_and_cart_link(self):
        web = FakeWeb({"https://www.gumnut.com.au/products/op15-booster-box.js": shopify_js(
            "OP-15 Booster Box", [(11, "Pre-order", 189.95, False), (12, "In stock", 199.0, True)])})
        r = lw.read(lw.clean_url(self.URL), web)
        self.assertTrue(r["ok"] and r["buyable"])
        self.assertEqual(r["price"], 199.0)
        self.assertEqual(r["cart"], "https://www.gumnut.com.au/cart/12:1")
        self.assertEqual(r["status"], "in stock")
        self.assertIn("OP-15 Booster Box", r["title"])

    def test_sold_out(self):
        web = FakeWeb({"https://www.gumnut.com.au/products/op15-booster-box.js": shopify_js(
            "OP-15 Booster Box", [(11, "Default Title", 189.95, False)])})
        r = lw.read(self.URL, web)
        self.assertTrue(r["ok"])
        self.assertFalse(r["buyable"])
        self.assertEqual((r["status"], r["price"], r["cart"]), ("sold out", 189.95, ""))
        self.assertEqual(r["title"], "OP-15 Booster Box")          # "Default Title" isn't added

    def test_a_chosen_variant_is_the_one_watched(self):
        url = "https://shop.test/products/sleeves?variant=22"
        web = FakeWeb({"https://shop.test/products/sleeves.js": shopify_js(
            "Sleeves", [(21, "Black", 10.0, True), (22, "Red", 12.0, False)])})
        r = lw.read(lw.clean_url(url), web)
        self.assertFalse(r["buyable"])
        self.assertEqual(r["price"], 12.0)

    def test_not_shopify_after_all_falls_back_to_the_page(self):
        url = "https://shop.test/products/thing"
        web = FakeWeb({url: ld_page({"@type": "Product", "name": "Thing",
                                     "offers": {"@type": "Offer", "price": "49.00", "priceCurrency": "AUD",
                                                "availability": "https://schema.org/InStock"}})})
        r = lw.read(url, web)
        self.assertEqual((r["ok"], r["buyable"], r["price"], r["how"]), (True, True, 49.0, "page data"))


class OtherPages(unittest.TestCase):
    def test_woocommerce_graph_preorder(self):
        page = ld_page({"@context": "https://schema.org", "@graph": [
            {"@type": "WebPage", "name": "x"},
            {"@type": "Product", "name": "One Piece EB-05 Booster Box",
             "offers": [{"@type": "Offer", "price": "165.00", "priceCurrency": "AUD",
                         "availability": "http://schema.org/PreOrder"}]}]})
        r = lw.parse_html(page.decode())
        self.assertEqual((r["buyable"], r["status"], r["price"], r["currency"]), (True, "pre-order open", 165.0, "AUD"))

    def test_aggregate_offer_and_out_of_stock(self):
        page = ld_page({"@type": "Product", "name": "Tin", "offers": {"@type": "AggregateOffer", "lowPrice": 30,
                                                                      "availability": "OutOfStock"}})
        r = lw.parse_html(page.decode())
        self.assertEqual((r["buyable"], r["status"], r["price"]), (False, "sold out", 30.0))

    def test_product_group_variants(self):
        page = ld_page({"@type": "ProductGroup", "name": "Playmat", "hasVariant": [
            {"@type": "Product", "name": "Playmat Red", "offers": {"price": 40, "availability": "SoldOut"}},
            {"@type": "Product", "name": "Playmat Blue", "offers": {"price": 45, "availability": "InStock"}}]})
        r = lw.parse_html(page.decode())
        self.assertEqual((r["buyable"], r["price"], r["title"]), (True, 45.0, "Playmat Blue"))

    def test_meta_tags_last(self):
        page = ('<meta property="og:title" content="Big Retailer Box &amp; Co">'
                '<meta property="product:price:amount" content="1,299.00">'
                '<meta property="product:availability" content="instock">')
        r = lw.parse_html(page)
        self.assertEqual((r["ok"], r["buyable"], r["price"], r["title"]), (True, True, 1299.0, "Big Retailer Box & Co"))

    def test_price_without_stock_is_never_called_buyable(self):
        r = lw.parse_html('<meta property="og:price:amount" content="99">')
        self.assertTrue(r["ok"])
        self.assertFalse(r["buyable"])
        self.assertIn("not whether", r["problem"])

    def test_nothing_readable(self):
        url = "https://x.test/p"
        r = lw.read(url, FakeWeb({url: b"<html>no data</html>"}))
        self.assertFalse(r["ok"])
        self.assertIn("doesn't say a price", r["problem"])

    def test_blocked_and_missing_pages_say_why(self):
        url = "https://x.test/p"
        self.assertIn("robots.txt", lw.read(url, FakeWeb({url: Robots(url)}))["problem"])
        self.assertIn("404", lw.read(url, FakeWeb({}))["problem"])

    def test_broken_json_ld_is_skipped(self):
        page = ('<script type="application/ld+json">{oops</script>'
                + ld_page({"@type": "Product", "name": "B", "offers": {"price": 5, "availability": "InStock"}}).decode())
        self.assertEqual(lw.parse_html(page)["price"], 5.0)


# ---------------------------------------------------------------- the list
class ListFile(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "watches.json")

    def test_add_update_remove(self):
        it, what = lw.add("https://Shop.test/products/a?utm_source=x&variant=5#top", 150, "Box A", "lee", self.path)
        self.assertEqual(what, "added")
        self.assertEqual(it["url"], "https://shop.test/products/a?variant=5")
        it2, what = lw.add("https://shop.test/products/a?variant=5", 140, "", "lee", self.path)
        self.assertEqual((what, it2["max"], it2["name"]), ("updated", 140.0, "Box A"))
        self.assertEqual(len(lw.load(self.path)), 1)
        lw.add("https://shop.test/products/b", None, "Tin B", "lee", self.path)
        self.assertIsNone(lw.load(self.path)[1]["max"])                    # any price
        self.assertEqual(lw.remove("tin", self.path)["name"], "Tin B")
        self.assertEqual(lw.remove(it["id"], self.path)["name"], "Box A")
        self.assertEqual(lw.load(self.path), [])
        self.assertIsNone(lw.remove("nothing", self.path))

    def test_bad_links_and_limit(self):
        with self.assertRaises(ValueError):
            lw.add("not a link", 10, path=self.path)
        with self.assertRaises(ValueError):
            lw.add("https://shop.test/p", -5, path=self.path)
        for i in range(lw.MAX_WATCHES):
            lw.add(f"https://shop.test/products/p{i}", 10, path=self.path)
        with self.assertRaises(ValueError):
            lw.add("https://shop.test/products/one-more", 10, path=self.path)

    def test_missing_or_broken_file(self):
        self.assertEqual(lw.load(self.path), [])
        with open(self.path, "w") as f:
            f.write("{nope")
        out, old = io.StringIO(), sys.stdout
        sys.stdout = out
        try:
            self.assertEqual(lw.load(self.path), [])
            with self.assertRaises(ValueError):
                lw.add("https://shop.test/products/a", 10, path=self.path)
        finally:
            sys.stdout = old


# ---------------------------------------------------------------- checking
def quiet(fn, *a, **kw):
    out, old = io.StringIO(), sys.stdout
    sys.stdout = out
    try:
        return fn(*a, **kw)
    finally:
        sys.stdout = old


class Checking(unittest.TestCase):
    def items(self):
        return [{"id": "aaaa", "url": "https://s.test/products/box", "name": "OP-15 box", "max": 200.0},
                {"id": "bbbb", "url": "https://s.test/products/tin", "name": "", "max": 20.0},
                {"id": "cccc", "url": "https://s.test/products/mat", "name": "Mat", "max": None},
                {"id": "dddd", "url": "https://gone.test/x", "name": "Gone", "max": 10.0}]

    def web(self):
        return FakeWeb({
            "https://s.test/products/box.js": shopify_js("OP-15 Booster Box", [(1, "Default Title", 189.0, True)]),
            "https://s.test/products/tin.js": shopify_js("Pokemon Tin", [(2, "Default Title", 35.0, True)]),
            "https://s.test/products/mat.js": shopify_js("Playmat", [(3, "Default Title", 999.0, True)])})

    def test_only_buyable_within_max_alert(self):
        res = quiet(lw.check, None, self.web(), items=self.items())
        self.assertEqual(sorted(f["id"] for f in res.finds), ["watch|aaaa", "watch|cccc"])
        box = next(f for f in res.finds if f["id"] == "watch|aaaa")
        self.assertEqual((box["kind"], box["price"], box["shop"]), ("Sealed", 189.0, "s.test"))
        self.assertTrue(box["link_watch"] and box["priority"])
        self.assertEqual(box["cart"], "https://s.test/cart/1:1")
        self.assertIn("your max $200.00", box["note"])
        self.assertEqual(res.ok_ids(), {"watch|aaaa", "watch|bbbb", "watch|cccc"})   # dddd failed to load

    def test_status_keeps_last_good_reading_through_a_failure(self):
        st = {}
        items = self.items()[:1]
        lw.remember(st, quiet(lw.check, None, self.web(), items=items), now=100)
        self.assertEqual(st["watch_last"]["aaaa"]["price"], 189.0)
        lw.remember(st, quiet(lw.check, None, FakeWeb({}), items=items), now=200)
        e = st["watch_last"]["aaaa"]
        self.assertEqual((e["ok"], e["price"], e["fails"], e["buyable"]), (False, 189.0, 1, True))
        self.assertIn("✅", lw.describe(items[0], e))
        self.assertIn("last read failed", lw.describe(items[0], e))

    def test_describe(self):
        it = {"id": "x", "url": "https://s.test/p", "name": "Box", "max": 100.0}
        self.assertIn("💸", lw.describe(it, {"ok": True, "buyable": True, "status": "in stock", "price": 150}))
        self.assertIn("⏳", lw.describe(it, {"ok": True, "buyable": False, "status": "sold out", "price": 90}))
        self.assertIn("not checked yet", lw.describe(it, None))


# ---------------------------------------------------------------- inside the bot
SEALED, WATCH, BOXES = "https://discord.test/sealed", "https://discord.test/watch", "https://discord.test/boxes"


class BotRuns(unittest.TestCase):
    """The real run_once: a watched link alerts once, stays quiet while it stays in stock, and alerts
    again after it sells out and comes back. A page that fails to load doesn't cause a repeat."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        names = ("STATE_PATH", "KNOWN_PATH", "STATUS_PATH", "SNAPSHOT_PATH", "HISTORY_PATH", "EVENTS_PATH",
                 "LOG_PATH", "CONTROLS_PATH", "RECAP_PATH", "PICKS_PATH", "DROPS_PATH")
        self.paths = {k: getattr(tb, k) for k in names}
        for k in names:
            setattr(tb, k, os.path.join(self.tmp, k.lower() + ".json"))
        self.saved = {n: getattr(tb, n) for n in ("check_sealed", "check_singles", "ebay_watch", "onepiece_instore", "pokemon_watch",
                                                   "run_price_drops", "store_locked", "desktop_beep", "discord_send",
                                                   "pc_last_seen")}
        self.saved_http = tb.HTTP.fetch
        self.watch_path = lw.WATCH_PATH
        lw.WATCH_PATH = os.path.join(self.tmp, "watches.json")
        tb.check_sealed = lambda cfg, sweep=False: ([], {})
        tb.check_singles = lambda cfg: []
        tb.ebay_watch = tb.pokemon_watch = tb.onepiece_instore = None
        tb.run_price_drops = lambda cfg, status, **kw: []
        tb.store_locked = lambda host: False
        tb.desktop_beep = lambda: None
        tb.pc_last_seen = lambda cfg: None
        self.sent = []
        tb.discord_send = lambda alerts, hook, payload, tries=3: self.sent.append((hook, payload)) or True
        self.pages = {}
        tb.HTTP.fetch = lambda url, tries=2, **kw: FakeWeb(self.pages)(url)

    def tearDown(self):
        for k, v in {**self.paths, **self.saved}.items():
            setattr(tb, k, v)
        tb.HTTP.fetch = self.saved_http
        lw.WATCH_PATH = self.watch_path
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_bot(self, **alerts):
        self.sent.clear()
        a = SimpleNamespace(all=False, loop=None, sealed=False, singles=False, pokemon=False)
        quiet(tb.run_once, {"sealed": {"max_price": 260}, "singles": {"shops": {}, "cards": []},
                            "alerts": {"discord_webhook_boxes": BOXES, "discord_webhook_sealed": SEALED,
                                       **alerts}}, a)
        return [p for h, p in self.sent if h in (SEALED, WATCH)]

    def stock(self, available, price=150.0):
        self.pages["https://s.test/products/box.js"] = shopify_js("OP-15 Booster Box",
                                                                  [(9, "Default Title", price, available)])

    def test_alert_once_then_again_after_a_restock(self):
        lw.add("https://s.test/products/box", 160, "OP-15 box", "lee")
        self.stock(True)
        posts = self.run_bot()
        self.assertEqual(len(posts), 1)
        title = posts[0]["embeds"][0]["title"]
        self.assertIn("🔗 Watched: OP-15 box", title)
        self.assertEqual(self.run_bot(), [])                     # still in stock: quiet
        self.pages.clear()
        self.assertEqual(self.run_bot(), [])                     # page down: quiet, and remembered
        self.stock(True)
        self.assertEqual(self.run_bot(), [])                     # back up, same stock: no repeat
        self.stock(False)
        self.assertEqual(self.run_bot(), [])                     # sold out
        self.stock(True)
        self.assertEqual(len(self.run_bot()), 1)                 # restocked: alert again
        last = tb.load_status()["watch_last"]
        self.assertEqual(list(last.values())[0]["price"], 150.0)

    def test_over_max_waits_for_a_price_drop(self):
        lw.add("https://s.test/products/box", 140, "OP-15 box", "lee")
        self.stock(True, 150)
        self.assertEqual(self.run_bot(), [])
        self.stock(True, 135)
        self.assertEqual(len(self.run_bot()), 1)

    def test_own_channel_if_set_up(self):
        lw.add("https://s.test/products/box", None, "OP-15 box", "lee")
        self.stock(True)
        self.run_bot(discord_webhook_watch=WATCH)
        self.assertEqual({h for h, _ in self.sent if h in (SEALED, WATCH)}, {WATCH})

    def test_nothing_watched_changes_nothing(self):
        self.assertEqual(self.run_bot(), [])
        self.assertNotIn("watch_last", tb.load_status())


if __name__ == "__main__":
    unittest.main()


class BoxAndPackListings(unittest.TestCase):
    """23 Oct 2026: Pocket Games' '... Booster Box & Pack [JP]' listings alerted as $9-$20 boxes."""

    def test_jp_in_brackets_is_japanese(self):
        for t in ("One Piece TCG (OP-13) – Carrying On His Will Booster Box & Pack [JP]",
                  "OP-13 Booster Box [JPN]", "OP-13 Booster Box JPN"):
            self.assertFalse(tb.is_box_title(t), t)
        self.assertTrue(tb.is_box_title("One Piece OP-13 Carrying On His Will Booster Box"))

    def test_box_and_pack_priced_by_the_box(self):
        vs = [{"id": 1, "title": "Pack", "price": "9.00", "available": True},
              {"id": 2, "title": "Booster Box", "price": "189.00", "available": True}]
        self.assertEqual(tb.cheapest_available(vs, cents=False), (189.0, 2))
        vs[1]["available"] = False
        self.assertEqual(tb.cheapest_available(vs, cents=False), (None, None))   # only packs left: no box
        plain = [{"id": 3, "title": "Default Title", "price": "199.00", "available": True}]
        self.assertEqual(tb.cheapest_available(plain, cents=False), (199.0, 3))
