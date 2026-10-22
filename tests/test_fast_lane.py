"""Tests for fast_lane.py (v2.6): drop-window fast lane, desk mode, quantity links; and the eBay
seller/junk filters. No network: shops and Discord are fakes.

Run:  python -m unittest discover -s tests
"""
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ebay_watch as ew  # noqa: E402
import fast_lane as fl  # noqa: E402
import link_watch as lw  # noqa: E402
import tcg_bot as tb  # noqa: E402

BOXES, SEALED = "https://discord.test/boxes", "https://discord.test/sealed"
DROP = {"name": "EB-05 eve", "games": ["onepiece"], "sections": [], "every": 60, "sealed_only": True,
        "start": datetime.now() - timedelta(minutes=5), "end": datetime.now() + timedelta(hours=2)}


def js(price, available, vid=7, title="Default Title"):
    return json.dumps({"title": "x", "variants": [{"id": vid, "title": title, "price": int(price * 100),
                                                   "available": available}]}).encode()


def listing(shop, handle, name, group="box", base="https://a.test", mx=260.0):
    return {"id": f"list|{shop}|{handle}", "box_id": f"{'box' if group == 'box' else 'sealed' if group == 'watch' else 'item'}|{shop}|{handle}",
            "group": group, "kind": "New listing", "name": name, "shop": shop, "price": 0.0, "available": False,
            "url": f"{base}/products/{handle}", "cart": "", "note": "", "max": mx, "page": 1}


def quiet(fn, *a, **kw):
    out, old = io.StringIO(), sys.stdout
    sys.stdout = out
    try:
        return fn(*a, **kw)
    finally:
        sys.stdout = old


class Codes(unittest.TestCase):
    def test_codes_from_the_window(self):
        self.assertEqual(fl.window_codes({"name": "EB-05 release day (auto)"}), ["EB-05"])
        self.assertEqual(fl.window_codes({"name": "OP-18 eve", "codes": ["PRB-02", "op19"]}), ["OP-18", "PRB-02", "OP-19"])
        self.assertEqual(fl.window_codes({"name": "Delta Reign"}), [])

    def test_pattern(self):
        rx = fl.code_pattern(["EB-05", "OP-18"])
        for t in ("One Piece EB-05 Booster Box", "EB05 Display", "[eb 05] box", "EB5 box", "OP18 Booster Box"):
            self.assertTrue(rx.search(t), t)
        for t in ("EB-06 Booster Box", "OP-180 thing", "OP-1 box", "EB-50 box"):
            self.assertFalse(rx.search(t), t)


class Targets(unittest.TestCase):
    def test_release_boxes_and_watch_links(self):
        by_shop = {
            "Gumnut": [listing("Gumnut", "eb05-box", "One Piece EB-05 Booster Box"),
                       listing("Gumnut", "eb05-deck", "EB-05 Starter Deck", group="new"),
                       listing("Gumnut", "op15-box", "OP-15 Booster Box")],
            "Woo": [dict(listing("Woo", "x", "EB-05 Booster Box"), url="https://w.test/product/eb-05-box")],
            "Gone": None,
            "Mayhem": [listing("Mayhem", "eb05-tin", "EB-05 Tin Collection", group="watch", base="https://m.test", mx=60)],
        }
        items = [{"id": "w1", "url": "https://s.test/products/sleeves", "name": "Sleeves", "max": 20.0},
                 {"id": "w2", "url": "https://big.test/p/12345", "name": "Not Shopify", "max": None}]
        t = fl.build_targets(DROP, by_shop, items)
        self.assertEqual([x["id"] for x in t], ["watch|w1", "box|Gumnut|eb05-box", "sealed|Mayhem|eb05-tin"])
        self.assertEqual(t[1]["js"], "https://a.test/products/eb05-box.js")
        self.assertEqual((t[2]["kind"], t[2]["max"]), ("Sealed", 60))
        self.assertEqual(len(fl.build_targets(DROP, by_shop, items, max_targets=2)), 2)

    def test_settings(self):
        self.assertIsNone(fl.settings({"fast_lane": False}))
        self.assertEqual(fl.settings({})["seconds"], 15)
        self.assertEqual(fl.settings({"fast_lane": {"seconds": 3}})["seconds"], fl.MIN_SECONDS)   # never faster than 10 s


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        names = ("STATE_PATH", "KNOWN_PATH", "STATUS_PATH", "SNAPSHOT_PATH", "HISTORY_PATH", "EVENTS_PATH",
                 "LOG_PATH", "CONTROLS_PATH", "RECAP_PATH", "PICKS_PATH", "DROPS_PATH")
        self.paths = {k: getattr(tb, k) for k in names}
        for k in names:
            setattr(tb, k, os.path.join(self.tmp, k.lower() + ".json"))
        self.saved = {n: getattr(tb, n) for n in ("check_sealed", "check_singles", "ebay_watch", "pokemon_watch",
                                                   "run_price_drops", "store_locked", "desktop_beep", "discord_send",
                                                   "pc_last_seen", "push_phone")}
        self.fetch, self.cool = tb.HTTP.fetch, dict(tb.HTTP.cool)
        self.watch_path = lw.WATCH_PATH
        lw.WATCH_PATH = os.path.join(self.tmp, "watches.json")
        tb.check_singles = lambda cfg: []
        tb.ebay_watch = tb.pokemon_watch = None
        tb.run_price_drops = lambda cfg, status, **kw: []
        tb.store_locked = lambda host: False
        tb.desktop_beep = lambda: None
        tb.pc_last_seen = lambda cfg: None
        tb.push_phone = lambda cfg, title, body: None
        self.sent, self.pages, self.asked = [], {}, []
        tb.discord_send = lambda alerts, hook, payload, tries=3: self.sent.append((hook, payload)) or True

        def fetch(url, tries=2, memo=True, **kw):
            self.asked.append(url)
            if url in self.pages:
                return self.pages[url]
            raise tb.HttpError(404, "Not Found")
        tb.HTTP.fetch = fetch
        fl.TARGETS[:] = []
        fl.LATENCY.clear()
        fl._opened.clear()
        fl._opened_links.clear()
        self.cfg = {"sealed": {"max_price": 260}, "singles": {"shops": {}, "cards": []},
                    "alerts": {"discord_webhook_boxes": BOXES, "discord_webhook_sealed": SEALED}}

    def tearDown(self):
        for k, v in {**self.paths, **self.saved}.items():
            setattr(tb, k, v)
        tb.HTTP.fetch = self.fetch
        tb.HTTP.cool.clear()
        tb.HTTP.cool.update(self.cool)
        lw.WATCH_PATH = self.watch_path
        fl.TARGETS[:] = []
        fl.LATENCY.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def posts(self):
        return [p for h, p in self.sent if h in (BOXES, SEALED)]


class Ticks(Base):
    def targets(self):
        by_shop = {"Gumnut": [listing("Gumnut", "eb05", "One Piece EB-05 Booster Box")],
                   "Mayhem": [listing("Mayhem", "eb05b", "EB-05 Booster Box", base="https://m.test")]}
        fl.TARGETS[:] = fl.build_targets(DROP, by_shop)

    def test_alerts_once_then_again_after_a_restock(self):
        self.targets()
        self.pages = {"https://a.test/products/eb05.js": js(199, False),
                      "https://m.test/products/eb05b.js": js(205, False)}
        self.assertEqual(quiet(fl.tick, tb, self.cfg, DROP), [])
        self.pages["https://a.test/products/eb05.js"] = js(199, True, vid=42)
        new = quiet(fl.tick, tb, self.cfg, DROP)
        self.assertEqual([f["id"] for f in new], ["box|Gumnut|eb05"])
        self.assertEqual(new[0]["cart"], "https://a.test/cart/42:1")
        self.assertIn("fast lane", new[0]["note"])
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual(tb.load_state()["box|Gumnut|eb05"], 199.0)
        self.assertEqual(quiet(fl.tick, tb, self.cfg, DROP), [])                # still in stock: quiet
        self.pages["https://a.test/products/eb05.js"] = js(199, False)
        quiet(fl.tick, tb, self.cfg, DROP)
        self.assertNotIn("box|Gumnut|eb05", tb.load_state())                  # sold out: forgotten
        self.pages["https://a.test/products/eb05.js"] = js(199, True)
        self.assertEqual(len(quiet(fl.tick, tb, self.cfg, DROP)), 1)          # back: alerts again

    def test_over_max_and_failed_reads_stay_quiet(self):
        self.targets()
        self.pages = {"https://a.test/products/eb05.js": js(300, True)}       # over the $260 box max
        self.assertEqual(quiet(fl.tick, tb, self.cfg, DROP), [])
        tb.save_state({"box|Mayhem|eb05b": 205.0})
        quiet(fl.tick, tb, self.cfg, DROP)                                    # Mayhem 404s this time
        self.assertIn("box|Mayhem|eb05b", tb.load_state())                    # a failed read forgets nothing

    def test_429_pauses_that_shop_only(self):
        self.targets()
        self.pages = {"https://a.test/products/eb05.js": js(199, False), "https://m.test/products/eb05b.js": js(205, False)}
        tb.HTTP.cool["m.test"] = [time.time() + 300, 1]
        quiet(fl.tick, tb, self.cfg, DROP)
        self.assertEqual(self.asked, ["https://a.test/products/eb05.js"])
        self.assertEqual(fl.STATUS["paused"], ["m.test"])

    def test_slow_shop_gets_top_targets_only(self):
        by_shop = {"Gumnut": [listing("Gumnut", f"eb05-{i}", f"EB-05 Booster Box v{i}") for i in range(5)]}
        fl.TARGETS[:] = fl.build_targets(DROP, by_shop)
        fl.LATENCY["a.test"] = 4000
        quiet(fl.tick, tb, self.cfg, DROP)
        self.assertEqual(len(self.asked), 2)
        self.assertEqual(fl.STATUS["slow"], ["a.test"])

    def test_full_check_does_not_repeat_a_fast_lane_alert(self):
        self.targets()
        self.pages = {"https://a.test/products/eb05.js": js(199, True)}
        quiet(fl.tick, tb, self.cfg, DROP)
        self.assertEqual(len(self.posts()), 1)
        self.sent.clear()
        tb.check_sealed = lambda cfg, sweep=False: ([{"id": "box|Gumnut|eb05", "kind": "Booster box",
                                                      "name": "One Piece EB-05 Booster Box", "shop": "Gumnut",
                                                      "price": 199.0, "url": "https://a.test/products/eb05",
                                                      "cart": "", "note": ""}], {})
        a = SimpleNamespace(all=False, loop=None, sealed=False, singles=False, pokemon=False)
        quiet(tb.run_once, self.cfg, a, DROP)
        self.assertEqual(self.posts(), [])

    def test_watch_links_ride_the_fast_lane(self):
        lw.add("https://s.test/products/sleeves", 20, "Sleeves", "lee", qty=3)
        fl.TARGETS[:] = fl.build_targets(DROP, {}, lw.load())
        self.pages = {"https://s.test/products/sleeves.js": js(15, True, vid=5)}
        new = quiet(fl.tick, tb, self.cfg, DROP)
        self.assertEqual(new[0]["id"], f"watch|{lw.load()[0]['id']}")
        self.assertEqual(new[0]["cart_n"], "https://s.test/cart/5:3")              # buy-3 link
        self.assertIn("Buy 3", json.dumps(self.posts()[0], ensure_ascii=False))


class Loop(Base):
    def test_run_once_sets_targets_in_a_window_and_clears_after(self):
        tb.check_sealed = lambda cfg, sweep=False: ([], {"Gumnut": [listing("Gumnut", "eb05", "EB-05 Booster Box")]})
        a = SimpleNamespace(all=False, loop=None, sealed=False, singles=False, pokemon=False)
        quiet(tb.run_once, self.cfg, a, DROP)
        self.assertEqual([t["id"] for t in fl.TARGETS], ["box|Gumnut|eb05"])
        self.assertEqual(tb.load_status()["fast_lane"]["targets"], 1)
        quiet(tb.run_once, self.cfg, a, None)
        self.assertEqual(fl.TARGETS, [])

    def test_wait_runs_ticks_between_full_checks(self):
        fl.TARGETS[:] = [{"id": "box|G|x", "kind": "Booster box", "name": "EB-05 Box", "shop": "G",
                          "url": "https://a.test/products/x", "js": "https://a.test/products/x.js", "max": 260, "prio": 1}]
        clock = [1000.0]
        fake = SimpleNamespace(time=lambda: clock[0], sleep=lambda s: clock.__setitem__(0, clock[0] + s),
                               perf_counter=time.perf_counter, strftime=time.strftime)
        old_time, old_aw = fl.time, tb.active_window
        fl.time, tb.active_window = fake, (lambda cfg, now=None: DROP)
        try:
            quiet(fl.wait, tb, self.cfg, 60)
        finally:
            fl.time, tb.active_window = old_time, old_aw
        self.assertEqual(len(self.asked), 3)            # at 15, 30 and 45 s; the full check comes at 60
        self.assertAlmostEqual(clock[0], 1060.0)

    def test_no_window_just_sleeps(self):
        slept = []
        old = fl.time
        fl.time = SimpleNamespace(time=time.time, sleep=slept.append, perf_counter=time.perf_counter)
        try:
            fl.TARGETS[:] = [{"id": "x", "js": "https://a.test/products/x.js"}]
            fl.wait(tb, self.cfg, 300)
        finally:
            fl.time = old
        self.assertEqual(slept, [300])
        self.assertEqual(self.asked, [])


class Desk(Base):
    def finds(self):
        return [{"id": "box|A|1", "kind": "Booster box", "name": "EB-05 Box", "price": 199.0, "cart": "https://a.test/cart/1:1"},
                {"id": "list|A|2", "kind": "New listing", "name": "EB-05 Deck", "price": 20.0, "cart": "https://a.test/cart/2:1"},
                {"id": "sealed|B|3", "kind": "Sealed", "name": "Tin", "price": 40.0, "cart": "https://b.test/cart/3:1"},
                {"id": "box|C|4", "kind": "Booster box", "name": "EB-05 Box C", "price": 205.0, "cart": "https://c.test/cart/4:1"},
                {"id": "card|D|5", "kind": "Single", "name": "Sabo", "price": 1.0, "cart": "https://d.test/cart/5:1"}]

    def desk(self, on=True):
        tb.atomic_write_json(tb.CONTROLS_PATH, {"desk_until": time.time() + (3600 if on else -10)})

    def test_off_opens_nothing(self):
        opened = []
        self.desk(False)
        self.assertEqual(fl.desk_open(tb, self.finds(), opener=opened.append), [])
        self.assertEqual(opened, [])

    def test_on_opens_targets_two_a_minute_never_new_listings(self):
        opened = []
        self.desk()
        quiet(fl.desk_open, tb, self.finds(), opener=opened.append, now=1000)
        self.assertEqual(opened, ["https://a.test/cart/1:1", "https://c.test/cart/4:1"])    # boxes first, cap 2
        quiet(fl.desk_open, tb, self.finds(), opener=opened.append, now=1030)
        self.assertEqual(len(opened), 2)                                                 # still inside the minute
        quiet(fl.desk_open, tb, self.finds(), opener=opened.append, now=1070)
        self.assertEqual(opened[2:], ["https://b.test/cart/3:1"])                        # same links not reopened
        self.assertNotIn("https://a.test/cart/2:1", opened)
        self.assertNotIn("https://d.test/cart/5:1", opened)

    def test_full_check_alert_opens_the_tab(self):
        opened = []
        old = fl.webbrowser.open
        fl.webbrowser.open = lambda url, new=0: opened.append(url)
        try:
            self.desk()
            tb.check_sealed = lambda cfg, sweep=False: ([{"id": "box|Gumnut|eb05", "kind": "Booster box",
                                                          "name": "EB-05 Booster Box", "shop": "Gumnut", "price": 199.0,
                                                          "url": "https://a.test/products/eb05",
                                                          "cart": "https://a.test/cart/9:1", "note": ""}], {})
            quiet(tb.run_once, self.cfg, SimpleNamespace(all=False, loop=None, sealed=False, singles=False, pokemon=False))
        finally:
            fl.webbrowser.open = old
        self.assertEqual(opened, ["https://a.test/cart/9:1"])


class Qty(unittest.TestCase):
    def test_box_quantities(self):
        f = lambda shop: {"kind": "Booster box", "shop": shop, "cart": "https://a.test/cart/9:1"}
        cfg = {"sealed": {"cart_qty": {"default": 1, "Mayhem": 2}}}
        a, b = fl.add_qty_links(cfg, [f("Gumnut"), f("Mayhem")])
        self.assertNotIn("cart_n", a)
        self.assertEqual((b["cart_qty"], b["cart_n"]), (2, "https://a.test/cart/9:2"))
        self.assertEqual(fl.add_qty_links({"sealed": {"cart_qty": 3}}, [f("X")])[0]["cart_n"], "https://a.test/cart/9:3")
        woo = {"kind": "Booster box", "shop": "W", "cart": "https://w.test/checkout/?add-to-cart=5&quantity=1"}
        self.assertNotIn("cart_n", fl.add_qty_links({"sealed": {"cart_qty": 3}}, [woo])[0])   # Shopify links only

    def test_embed_and_report_show_the_buy_n_link(self):
        f = {"id": "box|A|1", "kind": "Booster box", "name": "EB-05", "shop": "A", "price": 199.0, "url": "u",
             "cart": "https://a.test/cart/9:1", "note": "", "cart_qty": 2, "cart_n": "https://a.test/cart/9:2"}
        self.assertIn("BUY 2: https://a.test/cart/9:2", tb.report([f], "x"))
        fields = tb._discord_embeds([f])[0]["fields"]
        self.assertTrue(any(x["name"] == "⚡ Buy 2" for x in fields))


class EbayFilters(unittest.TestCase):
    CARD = {"skip_all": ew.SKIP_ALL, "min_pct": 98.0, "min_n": 20}

    def test_junk_words(self):
        for t in ("Nike Gomu Gomu DON card DIGITAL CODE only", "PSA 10 Luffy - EMPTY BOX", "Luffy promo artwork only",
                  "Nike TN One Piece - read description"):
            self.assertTrue(ew.junk(t, self.CARD), t)
        self.assertFalse(ew.junk("Nike x One Piece Mera Mera DON!! Promo Card English", self.CARD))

    def test_seller_feedback(self):
        it = lambda pct, n: {"seller": {"feedbackPercentage": pct, "feedbackScore": n}}
        self.assertTrue(ew.seller_ok(it("99.5", 340), self.CARD))
        self.assertFalse(ew.seller_ok(it("96.0", 340), self.CARD))
        self.assertFalse(ew.seller_ok(it("100.0", 3), self.CARD))
        self.assertTrue(ew.seller_ok({}, self.CARD))                         # no feedback shown: let through

    def test_settings_from_the_file(self):
        path = os.path.join(tempfile.mkdtemp(), "ebay_watch.json")
        with open(path, "w") as f:
            json.dump({"min_feedback_pct": 95, "skip_all": ["box only"],
                       "cards": [{"name": "x", "max": 10, "search": "x"}]}, f)
        c = ew.load_watch(path)[0][0]
        self.assertEqual((c["min_pct"], c["min_n"], c["skip_all"]), (95.0, ew.MIN_FEEDBACK_COUNT, ["box only"]))


if __name__ == "__main__":
    unittest.main()
