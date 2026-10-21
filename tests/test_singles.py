"""Singles prices (v2.3): the copy a price is quoted for, and the 6-hourly price drops.
No network: shop pages, product lists and Discord are fakes.

Run:  python -m unittest discover -s tests
"""
import gzip
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402

EA = "https://elementalarcade.com.au"
GG = "https://tcg.goodgames.com.au"
H = "https://discord.com/api/webhooks"
SINGLES, DROPS = f"{H}/6/singles", f"{H}/8/drops"
CONDS = ["Near Mint Foil", "Lightly Played Foil", "Moderately Played Foil", "Heavily Played Foil", "Damaged Foil"]
RATIO = [1, 0.85, 0.7, 0.6, 0.5]


def js_variants(nm_cents, in_stock=("Near Mint Foil",), base_id=500):
    """Variants as a product page (.js) gives them: prices in cents, one per condition."""
    return [{"id": base_id + i, "title": c, "available": c in in_stock, "price": int(round(nm_cents * r))}
            for i, (c, r) in enumerate(zip(CONDS, RATIO))]


def feed_product(handle, title, nm, nm_in_stock=True, body="", base_id=900):
    """A product as a collection's products.json gives it: prices as dollar strings."""
    return {"handle": handle, "title": title, "body_html": body,
            "variants": [{"id": base_id + i, "title": c, "available": nm_in_stock and i == 0,
                          "price": f"{nm * r:.2f}"} for i, (c, r) in enumerate(zip(CONDS, RATIO))]}


class Quiet(unittest.TestCase):
    def setUp(self):
        self._out = sys.stdout
        sys.stdout = io.StringIO()

    def tearDown(self):
        sys.stdout = self._out


# ---------------------------------------------------------------- which copy a price is for
class Copies(unittest.TestCase):
    def test_near_mint_when_its_in_stock(self):
        self.assertEqual(tb.nm_copy(js_variants(200, in_stock=CONDS), cents=True), (2.0, 500, "NM"))

    def test_cheapest_condition_left_when_near_mint_is_gone(self):
        price, vid, cond = tb.nm_copy(js_variants(200, in_stock=("Lightly Played Foil", "Damaged Foil")), cents=True)
        self.assertEqual((price, vid, cond), (1.0, 504, "Damaged"))

    def test_nothing_in_stock(self):
        self.assertEqual(tb.nm_copy(js_variants(200, in_stock=()), cents=True), (None, None, ""))
        self.assertEqual(tb.nm_copy(None, cents=True), (None, None, ""))

    def test_dollar_prices(self):
        v = [{"id": 1, "title": "Default Title", "available": True, "price": "4.50"}]
        self.assertEqual(tb.nm_copy(v, cents=False), (4.5, 1, ""))

    def test_nm_price_still_works_for_old_callers(self):
        self.assertEqual(tb.nm_price({"variants": js_variants(150, in_stock=CONDS)}), (1.5, 500))

    def test_link_text_never_leaves_a_stray_bracket(self):
        t = tb.link_text("Koala (Alternate Art) - EB03-042 [Extra Booster: One Piece Heroines Edition]", 50)
        self.assertNotIn("[", t)
        self.assertTrue(t.endswith("…") and len(t) == 50)

    def test_conditions(self):
        self.assertEqual(tb.condition("Lightly Played Foil"), "LP")
        self.assertEqual(tb.condition("Moderately Played"), "MP")
        self.assertEqual(tb.condition("Default Title"), "")
        self.assertEqual(tb.price_label({"price": 2, "cond": "NM"}), "$2.00 (NM)")
        self.assertEqual(tb.price_label({"price": 2}), "$2.00")


class ElementalWantList(unittest.TestCase):
    """The bug from 21 Oct: Koala OP05-006 alerted at $1 (a sold-out Damaged copy) when the only copy
    left was Near Mint at $2."""

    def setUp(self):
        self._suggest, self._js = tb.suggest, tb.product_js
        self.pages = {}
        self.opened = []
        tb.suggest = lambda base, q: [{"handle": "koala-op05006-awakening-of-the-new-era",
                                        "title": "Koala - OP05-006 [Awakening of the New Era]",
                                        "available": True, "price": "1.00", "price_min": "1.00", "price_max": "2.00",
                                        "variants": []}]

        def js(base, handle):
            self.opened.append(handle)
            return self.pages.get(handle)
        tb.product_js = js

    def tearDown(self):
        tb.suggest, tb.product_js = self._suggest, self._js

    def card(self, mx):
        return {"name": "Koala", "num": "OP05-006", "qty": 1, "max": mx, "deck": "Sabo"}

    def test_price_is_the_copy_in_stock(self):
        self.pages["koala-op05006-awakening-of-the-new-era"] = {"variants": js_variants(200)}
        self.assertEqual(tb.elemental_card(self.card(1.5), EA), [])        # $2 NM is over the $1.50 max
        (f,) = tb.elemental_card(self.card(2.5), EA)
        self.assertEqual((f["price"], f["cond"]), (2.0, "NM"))
        self.assertTrue(f["cart"].endswith("/cart/500:1"))                 # the NM copy goes in the cart

    def test_a_played_copy_under_max_still_alerts_and_says_so(self):
        self.pages["koala-op05006-awakening-of-the-new-era"] = {"variants": js_variants(200, ("Lightly Played Foil",))}
        (f,) = tb.elemental_card(self.card(1.8), EA)
        self.assertEqual((f["price"], f["cond"]), (1.7, "LP"))
        self.assertIn("(LP)", tb.report([f], "New"))
        self.assertIn("$1.70 (LP)", json.dumps(tb._discord_embeds([f])))

    def test_no_page_no_alert(self):
        self.assertEqual(tb.elemental_card(self.card(5), EA), [])

    def test_cheapest_condition_over_max_skips_the_page(self):
        self.pages["koala-op05006-awakening-of-the-new-era"] = {"variants": js_variants(200)}
        self.assertEqual(tb.elemental_card(self.card(0.5), EA), [])
        self.assertEqual(self.opened, [])


class ClassicGzip(unittest.TestCase):
    """Classic (v1-style) requests unpack a gzip reply - they only ask for one for the big singles lists."""

    def test_unpacks_gzip(self):
        body = json.dumps({"products": [{"handle": "a"}]}).encode()

        class Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def getheaders(self):
                return [("Content-Encoding", "gzip")]

            def read(self):
                return gzip.compress(body)

        seen = {}

        def urlopen(req, timeout=None, context=None):
            seen.update(req.header_items())
            return Resp()
        real = tb.urllib.request.urlopen
        tb.urllib.request.urlopen = urlopen
        http = tb._Http()
        try:
            http.gzip_urls.add(f"{EA}/collections/x/products.json")
            data = http.fetch(f"{EA}/collections/x/products.json?limit=250", robots=False, memo=False)
        finally:
            tb.urllib.request.urlopen = real
        self.assertEqual(json.loads(data), {"products": [{"handle": "a"}]})
        self.assertEqual(seen.get("Accept-encoding"), "gzip")


# ---------------------------------------------------------------- reading a shop's whole singles list
class Catalogs(unittest.TestCase):
    URL = f"{EA}/collections/one-piece-singles/products.json?limit=250"

    def setUp(self):
        self._fetch = tb.fetch_json
        self.calls, self.fail_pages = [], set()
        self.items = [feed_product(f"card-{i}", f"Card {i}", 1 + i / 100) for i in range(600)]

        def fetch(url, tries=2):
            self.calls.append(url)
            page = int(dict(tb.urllib.parse.parse_qsl(tb.urllib.parse.urlsplit(url).query)).get("page", 1))
            if page in self.fail_pages:
                return None
            return {"products": self.items[(page - 1) * 250: page * 250]}
        tb.fetch_json = fetch
        tb.PAGE_HINTS.pop(self.URL, None)

    def tearDown(self):
        tb.fetch_json = self._fetch
        tb.PAGE_HINTS.pop(self.URL, None)

    def test_reads_every_page(self):
        products, complete = tb.read_catalog(self.URL)
        self.assertEqual((len(products), complete), (600, True))
        self.assertEqual(tb.PAGE_HINTS[self.URL], 3)
        self.assertIn(self.URL.split("?")[0], tb.HTTP.gzip_urls)
        self.calls.clear()
        products, complete = tb.read_catalog(self.URL)                     # pages 1-3 asked for at once now
        self.assertEqual((len(products), complete, len(self.calls)), (600, True, 3))

    def test_a_failed_page_means_not_complete(self):
        self.fail_pages.add(2)
        products, complete = tb.read_catalog(self.URL)
        self.assertEqual((len(products), complete), (250, False))

    def test_first_page_failing_means_nothing(self):
        self.fail_pages.add(1)
        self.assertEqual(tb.read_catalog(self.URL), (None, False))

    def test_stops_at_max_pages(self):
        products, complete = tb.read_catalog(self.URL, max_pages=2)
        self.assertEqual((len(products), complete), (500, False))

    def test_entries_follow_the_near_mint_copy(self):
        e = tb.catalog_entry(feed_product("garp", "Monkey.D.Garp - OP13-016 [Carrying On His Will]", 1.0))
        self.assertEqual(e, {"name": "Monkey.D.Garp - OP13-016 [Carrying On His Will]", "price": 1.0,
                             "avail": True, "vid": 900})
        e = tb.catalog_entry(feed_product("garp", "Monkey.D.Garp - OP13-016", 1.0, nm_in_stock=False))
        self.assertFalse(e["avail"])                                       # NM sold out: not "in stock"

    def test_good_games_names_get_the_card_number(self):
        p = feed_product("hody", "Hody Jones [Wings of the Captain]", 2.1,
                         body="<table><tr><td>Number:</td><td>OP06-035</td></tr></table>")
        self.assertEqual(tb.catalog_entry(p)["name"], "Hody Jones [Wings of the Captain] (OP06-035)")


# ---------------------------------------------------------------- remembering prices, finding drops
def make_store():
    return {"v": 1, "shops": {}, "items": {}}


class Drops(unittest.TestCase):
    T = 1_800_000_000          # a fixed "now" for the tests

    def scan(self, store, t, prices, shop="Elemental Arcade", base=EA, complete=True):
        """prices: {handle: nm price, or (nm price, in stock)}"""
        products = []
        for h, v in prices.items():
            nm, avail = v if isinstance(v, tuple) else (v, True)
            products.append(feed_product(h, f"{h.title()} - OP01-001", nm, avail))
        return tb.record_catalog(store, shop, base, products, complete, t)

    def drops(self, store, now, **kw):
        return tb.best_drops(store, now, kw.pop("hours", 6), kw.pop("min_pct", 10), kw.pop("min_drop", 1.0),
                             kw.pop("top", 10), kw.pop("rank_by", "percent"))

    def test_a_drop_inside_the_window(self):
        s, h = make_store(), 3600
        self.scan(s, self.T, {"zoro": 20, "nami": 5, "ace": 50})
        for i in range(1, 7):
            self.scan(s, self.T + i * h, {"zoro": 20 if i < 3 else 15, "nami": 5, "ace": 50 if i < 5 else 44})
        got = self.drops(s, self.T + 6 * h + 60)
        self.assertEqual([(d["name"].split(" ")[0], d["was"], d["price"]) for d in got], [("Zoro", 20, 15), ("Ace", 50, 44)])
        self.assertAlmostEqual(got[0]["pct"], 25)
        self.assertEqual(got[0]["url"], f"{EA}/products/zoro")
        self.assertTrue(got[0]["cart"].startswith(f"{EA}/cart/"))

    def test_ranked_by_dollars(self):
        s, h = make_store(), 3600
        self.scan(s, self.T, {"zoro": 20, "ace": 50})
        self.scan(s, self.T + 2 * h, {"zoro": 15, "ace": 44})
        self.assertEqual([d["name"][:3] for d in self.drops(s, self.T + 3 * h, rank_by="dollars")], ["Ace", "Zor"])

    def test_small_drops_rises_and_sold_out_are_left_out(self):
        s, h = make_store(), 3600
        self.scan(s, self.T, {"tiny": 2.0, "tenpct": 100, "rise": 10, "gone": 10, "common": 0.5})
        self.scan(s, self.T + 2 * h, {"tiny": 1.5, "tenpct": 95, "rise": 12, "gone": (5, False), "common": 0.25})
        self.assertEqual(self.drops(s, self.T + 3 * h), [])   # $0.50 off, 5% off, a rise, not buyable, $0.25 off

    def test_net_change_over_the_window(self):
        s, h = make_store(), 3600
        self.scan(s, self.T, {"brook": 10})
        self.scan(s, self.T + h, {"brook": 14})
        self.scan(s, self.T + 2 * h, {"brook": 10})
        self.assertEqual(self.drops(s, self.T + 3 * h), [])    # back where it was: no drop

    def test_old_drops_dont_count(self):
        s, h = make_store(), 3600
        for i in range(10):
            self.scan(s, self.T + i * h, {"law": 30 if i < 2 else 20})
        self.assertEqual(self.drops(s, self.T + 9 * h + 60), [])   # it dropped 7 hours ago

    def test_restocked_cheaper_at_good_games(self):
        s, h = make_store(), 3600
        self.scan(s, self.T, {"hody": 10, "other": 3}, shop="Good Games", base=GG)
        self.scan(s, self.T + h, {"other": 3}, shop="Good Games", base=GG)          # hody sold out: off the list
        self.assertEqual(s["items"]["Good Games|hody"]["p"][-1][2], 0)
        self.scan(s, self.T + 3 * h, {"hody": 7.5, "other": 3}, shop="Good Games", base=GG)
        (d,) = self.drops(s, self.T + 4 * h)
        self.assertEqual((d["was"], d["price"], d["shop"]), (10, 7.5, "Good Games"))

    def test_a_partial_read_doesnt_mark_singles_sold_out(self):
        s = make_store()
        self.scan(s, self.T, {"a": 5, "b": 5})
        self.scan(s, self.T + 60, {"a": 5}, complete=False)
        self.assertEqual(s["items"]["Elemental Arcade|b"]["p"][-1][2], 1)

    def test_bot_off_for_a_while_compares_with_its_first_read_back(self):
        s, h = make_store(), 3600
        self.scan(s, self.T, {"luffy": 40})                    # then off for two days, price fell meanwhile
        self.scan(s, self.T + 48 * h, {"luffy": 30})
        self.scan(s, self.T + 50 * h, {"luffy": 30})
        self.assertEqual(self.drops(s, self.T + 51 * h), [])  # the $10 drop happened while it was off
        self.scan(s, self.T + 52 * h, {"luffy": 24})
        (d,) = self.drops(s, self.T + 53 * h)
        self.assertEqual((d["was"], d["price"]), (30, 24))

    def test_new_listing_that_dropped(self):
        s, h = make_store(), 3600
        self.scan(s, self.T, {"old": 5})
        self.scan(s, self.T + h, {"old": 5, "new": 20})
        self.scan(s, self.T + 2 * h, {"old": 5, "new": 16})
        (d,) = self.drops(s, self.T + 3 * h)
        self.assertEqual((d["name"][:3], d["was"], d["price"]), ("New", 20, 16))

    def test_unchanged_singles_add_nothing(self):
        s = make_store()
        self.scan(s, self.T, {"a": 5})
        self.assertEqual(self.scan(s, self.T + 60, {"a": 5}), 0)
        self.assertEqual(len(s["items"]["Elemental Arcade|a"]["p"]), 1)

    def test_old_changes_and_long_gone_singles_are_let_go(self):
        s, h = make_store(), 3600
        self.scan(s, self.T, {"a": 5, "b": 9})
        self.scan(s, self.T + h, {"a": 6})                     # b leaves the list
        self.scan(s, self.T + 2 * h, {"a": 7})
        self.scan(s, self.T + 60 * h, {"a": 8})
        pts = s["items"]["Elemental Arcade|a"]["p"]
        self.assertEqual([p[1] for p in pts], [7, 8])           # the last price before 48h ago stays
        self.assertIn("Elemental Arcade|b", s["items"])
        self.scan(s, self.T + 15 * 24 * h, {"a": 8})
        self.assertNotIn("Elemental Arcade|b", s["items"])      # gone 15 days: forgotten
        self.assertEqual(len(s["shops"]["Elemental Arcade"]["scans"]), 1)

    def test_saved_and_read_back(self):
        tmp = tempfile.mkdtemp()
        old = tb.DROPS_PATH
        tb.DROPS_PATH = os.path.join(tmp, "singles_prices.json")
        try:
            s = make_store()
            self.scan(s, self.T, {"a": 5, "b": 9})
            tb.save_drops_store(s)
            with open(tb.DROPS_PATH, encoding="utf-8") as f:
                text = f.read()
            self.assertEqual(text.count("\n"), 4)              # one single per line
            self.assertEqual(tb.load_drops_store(), json.loads(text))
            self.assertEqual(tb.load_drops_store()["items"], s["items"])
        finally:
            tb.DROPS_PATH = old
            shutil.rmtree(tmp, ignore_errors=True)

    def test_embed_fits_discord(self):
        s, h = make_store(), 3600
        names = {f"card-with-a-really-long-name-number-{i}": 100 for i in range(40)}
        self.scan(s, self.T, names)
        self.scan(s, self.T + h, {k: 50 for k in names})
        drops = self.drops(s, self.T + 2 * h, top=40)
        e = tb.drops_embed(drops, 6, s, tb.DROPS_DEFAULTS, self.T + 2 * h)
        self.assertLessEqual(len(e["description"]), 4096)
        self.assertLessEqual(len(json.dumps(e)), 6000)
        self.assertIn("50% off ($50.00)", e["description"])
        self.assertIn("tracking 40 singles at Elemental Arcade", e["footer"]["text"])
        empty = tb.drops_embed([], 6, s, tb.DROPS_DEFAULTS, self.T)
        self.assertIn("No single in stock got 10% or more", empty["description"])


# ---------------------------------------------------------------- settings
class Settings(unittest.TestCase):
    def test_lists_come_from_your_singles_shops(self):
        cfg = {"singles": {"shops": {"Elemental Arcade": EA, "Mayhem": "https://www.mayhemcollectables.com.au",
                                     "Good Games": GG}}}
        names = [x["name"] for x in tb.drops_settings(cfg)["shops"]]
        self.assertEqual(names, ["Elemental Arcade", "Good Games"])
        self.assertEqual(tb.drops_settings({"singles": {"shops": {}}})["shops"], [])
        self.assertFalse(tb.drops_settings({"price_drops": False})["enabled"])

    def test_bad_values_are_warned_about_and_ignored(self):
        cfg = {"price_drops": {"every_hours": 5, "rank_by": "vibes", "top": "x", "min_pct": "15", "colour": 1,
                               "shops": [{"name": "X"}]}}
        w = tb.check_drops_config(cfg)
        self.assertEqual(len(w), 5)
        self.assertEqual(cfg["price_drops"], {"min_pct": 15.0, "shops": []})
        s = tb.drops_settings(cfg)
        self.assertEqual((s["every_hours"], s["rank_by"], s["top"], s["min_pct"]), (6, "percent", 10, 15.0))

    def test_known_setting(self):
        self.assertNotIn("price_drops", " ".join(tb.check_config({"price_drops": {"top": 5}, "sealed": {"max_price": 1}})))


# ---------------------------------------------------------------- when it reads and posts
class Posting(Quiet):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self._path = tb.DROPS_PATH
        tb.DROPS_PATH = os.path.join(self.tmp, "singles_prices.json")
        self.saved = {n: getattr(tb, n) for n in ("read_catalog", "discord_send", "pc_heard_since")}
        self.sent, self.reads, self.ok = [], [], True
        self.prices = {"zoro": 20.0, "nami": 5.0}
        self.heard = False

        def read(url, max_pages=tb.CATALOG_MAX_PAGES):
            self.reads.append(url)
            return [feed_product(h, f"{h.title()} - OP01-001", p) for h, p in self.prices.items()], True
        tb.read_catalog = read
        tb.discord_send = lambda alerts, hook, payload, tries=3: self.sent.append((hook, payload)) or self.ok
        tb.pc_heard_since = lambda cfg, ts: self.heard
        self.cfg = {"singles": {"shops": {"Elemental Arcade": EA}},
                    "alerts": {"discord_webhook_singles": SINGLES}}

    def tearDown(self):
        tb.DROPS_PATH = self._path
        for n, v in self.saved.items():
            setattr(tb, n, v)
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def at(self, day_hour, minute=5):
        return datetime(2026, 10, 21, 0, 0).timestamp() + day_hour * 3600 + minute * 60

    def test_reads_hourly_and_posts_once_a_slot(self):
        st = {}
        self.assertIsNone(tb.run_price_drops(self.cfg, st, now=self.at(1)))   # 1am: first read, no post yet
        self.assertEqual((len(self.reads), self.sent), (1, []))
        tb.run_price_drops(self.cfg, st, now=self.at(1, 30))                   # half an hour on: not due
        self.assertEqual(len(self.reads), 1)
        self.prices["zoro"] = 14.0
        tb.run_price_drops(self.cfg, st, now=self.at(2, 10))                   # an hour on: read again
        self.assertEqual(len(self.reads), 2)
        self.assertEqual(self.sent, [])
        drops = tb.run_price_drops(self.cfg, st, now=self.at(6, 2))            # 6am: post the 12am-6am drops
        self.assertEqual(len(self.reads), 3)                                   # read fresh first
        self.assertEqual([d["name"][:4] for d in drops], ["Zoro"])
        ((hook, payload),) = self.sent
        self.assertEqual(hook, SINGLES)
        self.assertEqual(payload["allowed_mentions"], {"parse": []})          # no ping
        self.assertIn("Zoro", payload["embeds"][0]["description"])
        self.assertEqual(st["drops_slot"], "2026-10-21 06")
        tb.run_price_drops(self.cfg, st, now=self.at(6, 20))
        self.assertEqual(len(self.sent), 1)                                    # once per slot

    def test_own_channel_if_set(self):
        self.cfg["alerts"]["discord_webhook_drops"] = DROPS
        st = {}
        tb.run_price_drops(self.cfg, st, now=self.at(1))
        self.prices["zoro"] = 10.0
        tb.run_price_drops(self.cfg, st, now=self.at(6))
        self.assertEqual([h for h, _ in self.sent], [DROPS])

    def test_nothing_to_post(self):
        st = {}
        tb.run_price_drops(self.cfg, st, now=self.at(1))
        tb.run_price_drops(self.cfg, st, now=self.at(6))
        self.assertEqual(self.sent, [])
        self.assertEqual(st["drops_slot"], "2026-10-21 06")

    def test_failed_post_is_tried_again(self):
        st = {}
        tb.run_price_drops(self.cfg, st, now=self.at(1))
        self.prices["zoro"] = 10.0
        self.ok = False
        tb.run_price_drops(self.cfg, st, now=self.at(6))
        self.assertEqual(st["drops_slot"], "2026-10-21 00")
        self.ok = True
        tb.run_price_drops(self.cfg, st, now=self.at(6, 10))
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(st["drops_slot"], "2026-10-21 06")

    def test_cloud_copy_leaves_it_to_the_pc(self):
        st = {}
        tb.run_price_drops(self.cfg, st, role="listen", now=self.at(1))
        self.prices["zoro"] = 10.0
        tb.run_price_drops(self.cfg, st, role="listen", pc_on=True, now=self.at(6))
        self.assertEqual(self.sent, [])                                        # the PC is on: it posts
        st["drops_slot"] = "2026-10-21 00"
        self.heard = True
        tb.run_price_drops(self.cfg, st, role="listen", now=self.at(6, 30))
        self.assertEqual(self.sent, [])                                        # the PC was on this slot
        st["drops_slot"] = "2026-10-21 00"
        self.heard = False
        tb.run_price_drops(self.cfg, st, role="listen", now=self.at(6, 40))
        self.assertEqual(len(self.sent), 1)                                    # the PC's been off: cloud posts

    def test_show_all_returns_drops_without_posting(self):
        st = {}
        tb.run_price_drops(self.cfg, st, now=self.at(1))
        self.prices["zoro"] = 10.0
        tb.run_price_drops(self.cfg, st, now=self.at(2, 10))
        drops = tb.run_price_drops(self.cfg, st, show_all=True, now=self.at(2, 20))
        self.assertEqual(len(drops), 1)
        self.assertEqual(self.sent, [])
        self.assertIn("Zoro", tb.drops_report(drops, 6))

    def test_off_and_no_shops(self):
        st = {}
        self.assertIsNone(tb.run_price_drops({"price_drops": False, **self.cfg}, st, now=self.at(1)))
        self.assertIsNone(tb.run_price_drops({"singles": {"shops": {}}}, st, now=self.at(1)))
        self.assertEqual(self.reads, [])
        self.assertFalse(os.path.exists(tb.DROPS_PATH))

    def test_dry_run_reads_but_saves_and_posts_nothing(self):
        st = {}
        tb.DRY_RUN[0] = True
        try:
            tb.run_price_drops(self.cfg, st, now=self.at(1))
            st["drops_slot"] = "2026-10-21 00"
            tb.run_price_drops(self.cfg, st, now=self.at(6))
        finally:
            tb.DRY_RUN[0] = False
        self.assertEqual(len(self.reads), 2)
        self.assertEqual(self.sent, [])
        self.assertFalse(os.path.exists(tb.DROPS_PATH))


class InTheCheck(Quiet):
    """run_once reads the lists on singles checks only (not in drop mode's every-minute box checks), and a
    problem in the price drops never stops the restock check."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        names = ("STATE_PATH", "KNOWN_PATH", "STATUS_PATH", "SNAPSHOT_PATH", "HISTORY_PATH", "EVENTS_PATH",
                 "LOG_PATH", "CONTROLS_PATH", "RECAP_PATH", "PICKS_PATH", "DROPS_PATH")
        self.paths = {k: getattr(tb, k) for k in names}
        for k in names:
            setattr(tb, k, os.path.join(self.tmp, k.lower() + ".json"))
        self.saved = {n: getattr(tb, n) for n in ("check_sealed", "check_singles", "ebay_watch", "pokemon_watch",
                                                   "run_price_drops", "store_locked", "desktop_beep")}
        tb.check_sealed = lambda cfg, sweep=False: ([], {})
        tb.check_singles = lambda cfg: []
        tb.ebay_watch = tb.pokemon_watch = None
        tb.store_locked = lambda host: False
        tb.desktop_beep = lambda: None
        self.calls = []
        tb.run_price_drops = lambda cfg, status, **kw: self.calls.append(kw) or []

    def tearDown(self):
        for k, v in {**self.paths, **self.saved}.items():
            setattr(tb, k, v)
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def run_bot(self, drop=None, **args):
        a = SimpleNamespace(all=False, loop=None, sealed=False, singles=False, pokemon=False)
        a.__dict__.update(args)
        tb.run_once({"sealed": {"max_price": 260}, "singles": {"shops": {}, "cards": []}, "alerts": {}}, a, drop)
        return sys.stdout.getvalue()

    def test_on_singles_checks_only(self):
        self.run_bot()
        self.assertEqual(len(self.calls), 1)
        self.run_bot(sealed=True)
        self.assertEqual(len(self.calls), 1)
        now = datetime.now()
        self.run_bot(drop={"name": "OP-18", "games": ["onepiece"], "sections": [], "every": 60, "sealed_only": True,
                           "start": now - timedelta(minutes=1), "end": now + timedelta(hours=1)})
        self.assertEqual(len(self.calls), 1)

    def test_a_crash_in_price_drops_doesnt_stop_the_check(self):
        def boom(cfg, status, **kw):
            raise RuntimeError("bad list")
        tb.run_price_drops = boom
        out = self.run_bot()
        self.assertIn("price drops skipped this check (bad list)", out)
        self.assertTrue(os.path.exists(tb.STATUS_PATH))                       # the check still finished and saved


if __name__ == "__main__":
    unittest.main()
