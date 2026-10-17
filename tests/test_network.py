"""The HTTP layer against local mock shops (real TLS, real keep-alive). Needs: pip install cryptography"""
import gzip
import json
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
import tcg_bot as tb  # noqa: E402

NET = None
GUMNUT = "https://www.gumnut.com.au/collections/one-piece-card-game/products.json?limit=250"
POKEBOX = "https://www.pokebox.com.au/collections/one-piece-card-game-booster-boxes-english/products.json?limit=250"


def setUpModule():
    global NET
    if not helpers.have_crypto():
        raise unittest.SkipTest("needs the cryptography package for the mock shops' TLS certificate")
    NET = helpers.Net()
    NET.patch_process(tb)


def tearDownModule():
    if NET:
        NET.unpatch_process()
        NET.stop()


class Base(unittest.TestCase):
    def setUp(self):
        tb.HTTP.close_idle()
        tb.HTTP.memo.clear()
        tb.HTTP.cond.clear()
        tb.HTTP.cond_bytes = 0
        tb.HTTP.robots.clear()
        tb.HTTP.skip_hosts = set()
        tb.HTTP.cool.clear()
        tb.HTTP.next_at.clear()
        tb.HTTP.reset_metrics()
        NET.inet.stats.reset()
        NET.inet.script.clear()
        NET.inet.robots.clear()
        NET.inet.profile.etag = False
        NET.inet.idle_timeout = 20


class KeepAliveAndGzip(Base):
    # These cover v2's pooled connections, which are off by default ("classic_requests": true sends
    # requests the v1/urllib way, after shops' bot protection refused the pooled style in Oct 2026).
    def setUp(self):
        super().setUp()
        self._classic, tb.HTTP.classic = tb.HTTP.classic, False

    def tearDown(self):
        tb.HTTP.classic = self._classic

    def test_one_connection_for_many_requests(self):
        for h in ("sabo-sp-carrying-on-his-will", "sabo-parallel-carrying-on-his-will"):
            self.assertIsNotNone(tb.fetch_json(f"https://tcg.goodgames.com.au/products/{h}.js"))
        tb.HTTP.memo.clear()
        for _ in range(3):
            tb.HTTP.memo.clear()
            self.assertIsNotNone(tb.fetch_json("https://tcg.goodgames.com.au/products/sabo-sp-carrying-on-his-will.js"))
        s = NET.inet.stats.snapshot()
        self.assertEqual(s["connections"], 1)          # robots.txt + 5 product pages, one TLS handshake
        self.assertEqual(s["requests"], 6)

    def test_gzip_is_requested_and_decoded(self):
        data = tb.fetch_json(GUMNUT)
        self.assertEqual(len(data["products"]), 100)
        self.assertLess(tb.HTTP.m["bytes_wire"], tb.HTTP.m["bytes"] / 3)

    def test_server_closing_idle_connection_is_handled(self):
        NET.inet.idle_timeout = 0.2
        self.assertIsNotNone(tb.fetch_json("https://tcg.goodgames.com.au/products/sabo-sp-carrying-on-his-will.js"))
        time.sleep(0.6)                                # the shop drops the idle connection
        tb.HTTP.memo.clear()
        self.assertIsNotNone(tb.fetch_json("https://tcg.goodgames.com.au/products/sabo-sp-carrying-on-his-will.js"))


class Retries(Base):
    def test_503_then_ok_is_retried(self):
        NET.inet.script[("www.gumnut.com.au", "/collections/one-piece-card-game/products.json")] = [(503, {}, b"busy")]
        self.assertIsNotNone(tb.fetch_json(GUMNUT))
        self.assertEqual(tb.HTTP.m["retries"], 1)

    def test_401_is_not_retried_and_not_asked_again(self):
        url = "https://www.mayhemcollectables.com.au/search/suggest.json?q=sabo&resources[type]=product&resources[limit]=10"
        t0 = time.perf_counter()
        self.assertIsNone(tb.fetch_json(url))
        self.assertIsNone(tb.fetch_json(url.replace("sabo", "garp")))     # same shop, same path: fast fail
        self.assertLess(time.perf_counter() - t0, 1.0)                   # v1 slept 4.5 s per URL here
        by = NET.inet.stats.snapshot()["by_host"]["www.mayhemcollectables.com.au"]
        self.assertEqual(by.get("s401", 0), 1)

    def test_429_puts_the_shop_on_a_cooldown(self):
        # A 429 isn't retried straight away (that's what got the PC blocked on 17 Oct 2026): the shop is
        # left alone for at least COOL_MIN seconds, and every page there fails fast without a request.
        NET.inet.script[("www.gumnut.com.au", "/collections/one-piece-card-game/products.json")] = [
            (429, {"Retry-After": "0.2"}, b"")]
        self.assertIsNone(tb.fetch_json(GUMNUT))
        left = tb.HTTP.cooling().get("www.gumnut.com.au", 0)
        self.assertGreater(left, tb.COOL_MIN - 5)
        before = NET.inet.stats.requests
        self.assertIsNone(tb.fetch_json(GUMNUT))
        self.assertEqual(NET.inet.stats.requests, before)       # no request sent while cooling

    def test_cooldown_doubles_and_resets_after_a_good_answer(self):
        h = "www.gumnut.com.au"
        self.assertAlmostEqual(tb.HTTP._cool_down(h, None), tb.COOL_MIN)
        tb.HTTP.cool[h][0] = 0                                  # cooldown over
        self.assertAlmostEqual(tb.HTTP._cool_down(h, None), tb.COOL_MIN * 2)
        tb.HTTP.cool[h][0] = 0
        self.assertAlmostEqual(tb.HTTP._cool_down(h, 5000), tb.COOL_MAX)   # capped
        tb.HTTP.cool[h][0] = 0
        self.assertIsNotNone(tb.fetch_json(GUMNUT))             # answers fine -> back to the start
        self.assertNotIn(h, tb.HTTP.cool)

    def test_429_is_not_counted_as_the_shop_being_down(self):
        NET.inet.script[("www.gumnut.com.au", "/collections/one-piece-card-game/products.json")] = [
            (429, {}, b"")]
        with tb._host_lock:
            tb._host_results.clear()
        self.assertIsNone(tb.fetch_json(GUMNUT))
        self.assertNotIn("www.gumnut.com.au", tb._host_results)

    def test_requests_to_one_shop_are_spaced_out(self):
        tb.HTTP.memo.clear()
        t0 = time.perf_counter()
        for q in ("a", "b", "c"):
            tb.fetch_json(GUMNUT + "&x=" + q)
        self.assertGreaterEqual(time.perf_counter() - t0, 2 * tb.HOST_GAP - 0.05)

    def test_429_long_retry_after_is_left_for_next_check(self):
        NET.inet.script[("www.gumnut.com.au", "/collections/one-piece-card-game/products.json")] = [
            (429, {"Retry-After": "120"}, b"")]
        t0 = time.perf_counter()
        self.assertIsNone(tb.fetch_json(GUMNUT))
        self.assertLess(time.perf_counter() - t0, 1.0)

    def test_redirect_is_followed(self):
        NET.inet.script[("www.gumnut.com.au", "/collections/old-name/products.json")] = [
            (301, {"Location": GUMNUT}, b"")]
        data = tb.fetch_json("https://www.gumnut.com.au/collections/old-name/products.json?limit=250")
        self.assertEqual(len(data["products"]), 100)


class Sharing(Base):
    def test_identical_requests_at_once_share_one(self):
        out = []
        ts = [threading.Thread(target=lambda: out.append(tb.fetch_json(GUMNUT))) for _ in range(12)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(len(out), 12)
        self.assertTrue(all(o for o in out))
        paths = NET.inet.stats.paths
        self.assertEqual(paths[("www.gumnut.com.au", "collection")], 1)

    def test_conditional_get_uses_304(self):
        NET.inet.profile.etag = True
        a = tb.fetch_json(GUMNUT)
        tb.HTTP.memo.clear()
        b = tb.fetch_json(GUMNUT)
        self.assertEqual(a, b)
        self.assertEqual(tb.HTTP.m["not_modified"], 1)


class RobotsTxt(Base):
    def test_disallowed_search_is_not_requested(self):
        NET.inet.robots["grailborne.com.au"] = "User-agent: *\nDisallow: /search\n"
        self.assertEqual(tb.suggest("https://grailborne.com.au", "one piece booster box"), [])
        self.assertEqual(NET.inet.stats.paths.get(("grailborne.com.au", "suggest"), 0), 0)

    def test_missing_robots_means_allowed(self):
        NET.inet.robots["grailborne.com.au"] = 404
        self.assertTrue(tb.suggest("https://grailborne.com.au", "one piece booster box"))

    def test_unreachable_robots_holds_off(self):
        NET.inet.robots["grailborne.com.au"] = 503
        self.assertEqual(tb.suggest("https://grailborne.com.au", "one piece booster box"), [])
        self.assertTrue(tb.HTTP.robots["grailborne.com.au"].get("unreachable"))


class Pagination(Base):
    def test_reads_past_the_first_250(self):
        products, pages = tb.shopify_collection(POKEBOX)
        self.assertEqual(len(products), 315)
        self.assertEqual(pages["one-piece-card-game-extra-booster-heroines-edition-vol-2-eb-05-booster-box-english"], 2)

    def test_known_second_page_is_asked_for_at_once(self):
        tb.PAGE_HINTS.clear()
        a, pa = tb.shopify_collection(POKEBOX)
        self.assertEqual(tb.PAGE_HINTS[POKEBOX], 2)
        tb.HTTP.memo.clear()
        NET.inet.stats.reset()
        b, pb = tb.shopify_collection(POKEBOX)
        self.assertEqual([p["handle"] for p in a], [p["handle"] for p in b])
        self.assertEqual(pa, pb)
        self.assertEqual(NET.inet.stats.paths[("www.pokebox.com.au", "collection")], 2)

    def test_a_shrunk_collection_resets_its_hint(self):
        tb.PAGE_HINTS[GUMNUT] = 3                      # Gumnut has one page now
        products, pages = tb.shopify_collection(GUMNUT)
        self.assertEqual(len(products), 100)
        self.assertEqual(set(pages.values()), {1})
        self.assertEqual(tb.PAGE_HINTS[GUMNUT], 1)

    def test_shopify_boxes_sees_eb05_in_the_collection(self):
        finds, listings = tb.shopify_boxes("Pokebox", POKEBOX, 260, tb.DEFAULT_SEALED_WATCH)
        self.assertTrue(any("EB-05" in l["name"] for l in listings))


class QuietPeriod(Base):
    def test_down_shop_is_skipped_without_a_request(self):
        tb.HTTP.skip_hosts = {"www.gumnut.com.au"}
        self.assertIsNone(tb.fetch_json(GUMNUT))
        self.assertEqual(NET.inet.stats.snapshot()["requests"], 0)


class Discord(Base):
    def test_429_is_waited_out_and_message_confirmed(self):
        NET.inet.profile.discord_429 = 1
        try:
            ok = tb.discord_send({}, helpers.WEBHOOKS["DISCORD_WEBHOOK_BOXES"], {"content": "hi"})
        finally:
            NET.inet.profile.discord_429 = 0
        self.assertTrue(ok)
        self.assertEqual(len(NET.inet.stats.discord), 1)

    def test_server_errors_give_up_after_three_tries(self):
        NET.inet.discord_fail = 5
        try:
            ok = tb.discord_send({}, helpers.WEBHOOKS["DISCORD_WEBHOOK_BOXES"], {"content": "hi"}, tries=2)
        finally:
            NET.inet.discord_fail = 0
        self.assertFalse(ok)

    def test_many_finds_go_out_in_several_messages(self):
        finds = [{"id": f"card|Elemental Arcade|X|{i}", "kind": "Single", "name": f"Card {i}", "shop": "Elemental Arcade",
                  "price": 1.0, "qty": 1, "url": f"https://elementalarcade.com.au/products/{i}",
                  "cart": f"https://elementalarcade.com.au/cart/{1000 + i}:1", "note": "", "deck": ""} for i in range(23)]
        cfg = {"alerts": {"discord_webhook_singles": helpers.WEBHOOKS["DISCORD_WEBHOOK_SINGLES"]}}
        ok, delivered = tb.push_discord_detailed(cfg, "t", "b", finds)
        self.assertTrue(ok)
        self.assertEqual(delivered, {f["id"] for f in finds})
        posts = NET.inet.stats.discord
        self.assertEqual(sum(len(p["embeds"]) for p in posts), 24)        # 23 cards + the one-cart embed
        self.assertTrue(all(len(p["embeds"]) <= 10 for p in posts))
        self.assertIn("🧺", posts[0]["embeds"][0]["title"])


if __name__ == "__main__":
    unittest.main()
