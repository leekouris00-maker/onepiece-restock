"""v2.19.4: one shared pace for every Shopify shop, with a background lane for singles and price-drop lists."""
import os
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402


class Fake:
    """Stands in for urlopen: records each GET and answers with a chosen status."""

    def __init__(self, status=200, headers=None):
        self.status, self.headers, self.times, self.lock = status, headers or {}, [], threading.Lock()

    def __call__(self, req, timeout=None, context=None):
        import urllib.error
        import urllib.parse
        with self.lock:
            self.times.append((time.time(), urllib.parse.urlsplit(req.full_url).hostname, tb.in_background()))
        if self.status >= 400:
            raise urllib.error.HTTPError(req.full_url, self.status, "x", dict(self.headers), None)
        r = mock.MagicMock()
        r.__enter__.return_value = r
        r.status, r.getheaders.return_value, r.read.return_value = self.status, list(self.headers.items()), b"{}"
        return r


class Base(unittest.TestCase):
    def setUp(self):
        self.http = tb._Http()
        self.http.robots_on = False
        self.http._ctx = object()
        self.fake = Fake()
        for p in (mock.patch.object(tb.urllib.request, "urlopen", side_effect=self.fake),
                  mock.patch.object(tb, "netguard", None), mock.patch.object(tb, "HOST_GAP", 0)):
            p.start()
            self.addCleanup(p.stop)


class Detection(Base):
    def test_paths(self):
        for p in ("/products.json", "/collections/one-piece/products.json", "/search/suggest.json",
                  "/products/op-09-box.js", "/products/op-09-box.json"):
            self.assertTrue(self.http.is_shopify("x.com", p), p)
        for p in ("/wp-json/wc/store/products", "/", "/shop/op09"):
            self.assertFalse(self.http.is_shopify("x.com", p), p)

    def test_learns_from_headers(self):
        for h in ({"x-shopid": "1"}, {"x-shopify-stage": "p"}, {"x-sorting-hat-shopid": "2"}, {"powered-by": "Shopify"}):
            http = tb._Http()
            http._learn_platform("a.com", h)
            self.assertTrue(http.is_shopify("a.com", "/anything"), h)
        http = tb._Http()
        http._learn_platform("a.com", {"server": "nginx"})
        self.assertFalse(http.is_shopify("a.com", "/anything"))


class Config(unittest.TestCase):
    def tearDown(self):
        tb.HTTP.sp_on, tb.HTTP.sp_rate, tb.HTTP.sp_bg_rate = True, tb.SHOPIFY_PER_SEC, tb.SHOPIFY_BG_PER_SEC

    def apply(self, cfg):
        with mock.patch.object(tb, "netguard", None), mock.patch.object(tb, "load_status", return_value={}):
            tb.begin_check(cfg, {})

    def test_settings(self):
        self.assertIn("shopify_pace", tb.KNOWN_SETTINGS)
        self.apply({"shopify_pace": {"per_second": 5, "background_per_second": 2}})
        self.assertEqual((tb.HTTP.sp_on, tb.HTTP.sp_rate, tb.HTTP.sp_bg_rate), (True, 5, 2))
        self.apply({"shopify_pace": False})
        self.assertFalse(tb.HTTP.sp_on)
        self.apply({})
        self.assertEqual((tb.HTTP.sp_on, tb.HTTP.sp_rate), (True, tb.SHOPIFY_PER_SEC))


class Pace(Base):
    def test_off_means_no_wait(self):
        self.http.sp_on = False
        t0 = time.time()
        for i in range(10):
            self.http.fetch(f"https://s{i}.com/products.json", memo=False)
        self.assertLess(time.time() - t0, 0.3)

    def test_shared_across_shops(self):
        self.http.sp_rate = 20
        t0 = time.time()
        tb.pmap(lambda i: self.http.fetch(f"https://s{i}.com/products.json", memo=False), range(11))
        self.assertGreaterEqual(time.time() - t0, 0.45)      # 11 requests at 20/s across 11 different shops
        self.assertEqual(self.http.shopify_metrics()["front"], 11)

    def test_non_shopify_not_paced(self):
        self.http.sp_rate = 2
        t0 = time.time()
        tb.pmap(lambda i: self.http.fetch(f"https://w{i}.com/wp-json/x", memo=False), range(8))
        self.assertLess(time.time() - t0, 0.4)

    def test_background_waits_behind_front(self):
        self.http.sp_rate, self.http.sp_bg_rate = 10, 10
        out = []

        def front():
            for i in range(6):
                self.http.fetch(f"https://f{i}.com/products.json", memo=False)
                out.append("f")

        def back():
            time.sleep(0.02)
            with tb.background():
                self.http.fetch("https://b.com/products.json", memo=False)
            out.append("b")

        ts = [threading.Thread(target=front), threading.Thread(target=back)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertGreaterEqual(out.index("b"), 4)            # went once the front had (nearly) finished

    def test_background_rate(self):
        self.http.sp_rate, self.http.sp_bg_rate = 100, 10
        t0 = time.time()
        with tb.background():
            for i in range(6):
                self.http.fetch(f"https://b{i}.com/products.json", memo=False)
        self.assertGreaterEqual(time.time() - t0, 0.45)
        self.assertEqual(self.http.shopify_metrics()["background"], 6)

    def test_background_never_waits_too_long(self):
        self.http.sp_front_waiting = 1                        # someone is always waiting in front
        with mock.patch.object(tb, "BG_MAX_WAIT", 0.2), tb.background():
            t0 = time.time()
            self.http.fetch("https://b.com/products.json", memo=False)
        self.assertLess(time.time() - t0, 1.0)


class Strikes(Base):
    def test_429_slows_all_and_holds_background(self):
        self.fake.status = 429
        with self.assertRaises(tb.HttpError):
            self.http.fetch("https://a.com/products.json", memo=False, tries=1)
        self.assertEqual(self.http.sp_slow, 2)
        with tb.background(), self.assertRaises(tb.HttpError) as e:
            self.http.fetch("https://other.com/products.json", memo=False)
        self.assertEqual(e.exception.status, 429)
        self.assertIn("singles wait", str(e.exception))
        self.assertEqual(self.http.shopify_metrics()["held"], 1)

    def test_one_strike_per_burst_and_quarter_floor(self):
        self.assertTrue(self.http._shopify_strike())
        self.assertFalse(self.http._shopify_strike())         # same burst
        for _ in range(4):
            self.http.sp_strike -= tb.SHOPIFY_STRIKE_GAP + 1
            self.http._shopify_strike()
        self.assertEqual(self.http.sp_slow, tb.SHOPIFY_SLOW_MAX)

    def test_recovers(self):
        self.http._shopify_strike()
        self.http.sp_strike -= tb.SHOPIFY_RECOVER + 1
        self.http.sp_step -= tb.SHOPIFY_RECOVER + 1
        self.http.sp_hold = 0
        self.http._group_gate("a.com", "/products.json")
        self.assertEqual(self.http.sp_slow, 1)

    def test_only_shopify_429_strikes(self):
        self.fake.status = 429
        with self.assertRaises(tb.HttpError):
            self.http.fetch("https://woo.com/wp-json/wc/store/products", memo=False, tries=1)
        self.assertEqual(self.http.sp_slow, 1)

    def test_held_singles_are_slow_down_not_shop_down(self):
        err = tb.HttpError(429, "Too Many Requests - singles wait", 60)
        with mock.patch.object(tb, "_note_host") as note, mock.patch("builtins.print"):
            tb._fail("https://a.com/products.json", err)
        note.assert_not_called()


class Lanes(unittest.TestCase):
    def test_pmap_carries_lane_and_uses_own_pools(self):
        seen = []

        def f(x):
            seen.append((tb.in_background(), threading.current_thread().name))
            return x

        with tb.background():
            tb.pmap(f, range(4))
        self.assertTrue(all(bg and "bg-" in name for bg, name in seen))
        seen.clear()
        tb.pmap(f, range(4))
        self.assertTrue(all(not bg and "bg-" not in name for bg, name in seen))

    def test_singles_in_background_boxes_and_pokemon_not(self):
        lanes = {}
        with mock.patch.object(tb, "check_sealed", side_effect=lambda *a: lanes.setdefault("sealed", tb.in_background())), \
                mock.patch.object(tb, "check_singles", side_effect=lambda *a: lanes.setdefault("singles", tb.in_background())), \
                mock.patch.object(tb, "pokemon_watch", mock.Mock(check=lambda *a: lanes.setdefault("poke", tb.in_background()))):
            tb.run_checks_all({})
        self.assertEqual(lanes, {"sealed": False, "singles": True, "poke": False})


if __name__ == "__main__":
    unittest.main()
