"""Tests for deal_finder.py. No network: eBay and Discord are replaced with fakes.

Run:  python -m unittest discover -s tests
"""
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import deal_finder as df  # noqa: E402
import ebay_watch as ew  # noqa: E402

RATE = 1.5
STORE = {"fx": {"rate": RATE}, "day": 1, "groups": {"1": {"n": "Carrying On His Will", "a": "OP13"}},
         "items": {
             "10": {"n": "Sabo (120)", "g": "1", "t": "card", "m": 2.0, "num": "OP13-120"},
             "11": {"n": "Sabo (120) (Parallel)", "g": "1", "t": "card", "m": 40.0, "num": "OP13-120"},
             "12": {"n": "Sabo (120) (Super Alternate Art)", "g": "1", "t": "card", "m": 700.0, "num": "OP13-120"},
             "13": {"n": "Sabo (120) (Red Super Alternate Art)", "g": "1", "t": "card", "m": 4800.0, "num": "OP13-120"},
             "14": {"n": "Sabo (120) (Wanted Poster)", "g": "1", "t": "card", "m": 110.0, "num": "OP13-120"},
             "20": {"n": "Roronoa Zoro (118) (Parallel)", "g": "1", "t": "card", "m": 60.0, "num": "OP13-118"},
             "21": {"n": "Roronoa Zoro (118) (Parallel) (Reprint)", "g": "1", "t": "card", "m": 50.0, "num": "OP13-118"},
             "30": {"n": "Nami (001)", "g": "1", "t": "card", "m": 30.0, "num": "OP13-001"},
             "31": {"n": "Nami (001)", "g": "1", "t": "card", "m": 30.0, "num": "OP13-002"},
             "32": {"n": "Nami (001)", "g": "1", "t": "card", "m": 30.0, "num": "OP13-003"},
         }}


def item(iid, title, price, post=0.0, country="AU", pct="99.9", score=500, **extra):
    it = {"itemId": f"v1|{iid}|0", "legacyItemId": str(iid), "title": title,
          "price": {"value": f"{price:.2f}", "currency": "AUD"},
          "itemWebUrl": f"https://www.ebay.com.au/itm/{iid}?hash=x", "itemLocation": {"country": country},
          "buyingOptions": ["FIXED_PRICE"], "seller": {"feedbackPercentage": pct, "feedbackScore": score}}
    if post is not None:
        it["shippingOptions"] = [{"shippingCost": {"value": f"{post:.2f}", "currency": "AUD"}}]
    it.update(extra)
    return it


class FakeTb:
    """The bits of tcg_bot the deal finder uses."""
    IN_ACTIONS = False
    AMBER = 0

    def __init__(self):
        self.DRY_RUN = [False]
        self.sent, self.pushed, self.status = [], [], []
        self.files = {}

    def read_json(self, path, default=None):
        return json.loads(self.files[path]) if path in self.files else default

    def atomic_write_json(self, path, obj, **kw):
        self.files[path] = json.dumps(obj)

    def discord_send(self, alerts, hook, payload):
        self.sent.append((hook, payload))
        return True

    def push_phone(self, cfg, title, body):
        self.pushed.append(title)

    def post_status(self, cfg, text, color=0):
        self.status.append(text)

    def redact(self, s):
        return s

    def link_text(self, s, n=60):
        return str(s)[:n]


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeEbay:
    def __init__(self, items=(), status=200):
        self.items, self.status, self.queries = list(items), status, []

    def __call__(self, req, timeout=None):
        url = req.full_url
        if "oauth2" in url:
            return FakeResp(json.dumps({"access_token": "tok", "expires_in": 7200}).encode())
        if self.status != 200:
            raise urllib.error.HTTPError(url, self.status, "x", {}, None)
        self.queries.append(urllib.parse.parse_qs(urllib.parse.urlparse(url).query))
        return FakeResp(json.dumps({"itemSummaries": self.items}).encode())


CFG = {"alerts": {"ebay_client_id": "id", "ebay_client_secret": "secret",
                  "discord_webhook_autobuy": "https://discord.com/api/webhooks/1/private"}}


class Base(unittest.TestCase):
    def setUp(self):
        self.s = df.settings({})
        import tcgplayer as tp
        self.tp = tp
        self.idx = df.price_index(tp, STORE, self.s)
        ew._token.update(value=None, exp=0)
        self._old = ew._urlopen
        self._old_load = tp.load_for
        tp.load_for = lambda cfg=None: STORE
        for k in ("EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"):
            os.environ.pop(k, None)

    def tearDown(self):
        ew._urlopen = self._old
        self.tp.load_for = self._old_load


class TestTitles(Base):
    def test_card_numbers(self):
        self.assertEqual(df.card_numbers("Sabo OP13-120 SEC"), {"OP13-120"})
        self.assertEqual(df.card_numbers("sabo op13 120"), {"OP13-120"})
        self.assertEqual(df.card_numbers("Luffy ST10006"), {"ST10-006"})
        self.assertEqual(df.card_numbers("Luffy P-001 promo"), {"P-001"})
        self.assertEqual(df.card_numbers("PRB01-001 Luffy"), {"PRB01-001"})
        self.assertEqual(df.card_numbers("Sabo (no number)"), set())

    def test_version_words(self):
        self.assertEqual(df.tags_of("Sabo Super Alt Art"), {"saa"})
        self.assertEqual(df.tags_of("Sabo Red Super Alternate Art"), {"red_saa"})
        self.assertEqual(df.tags_of("Sabo Parallel Alt Art"), {"aa"})
        self.assertEqual(df.tags_of("Luffy Manga Alt Art"), {"manga"})
        self.assertEqual(df.tags_of("Sabo Wanted Poster SEC"), {"wanted"})
        self.assertEqual(df.tags_of("Sabo SEC Near Mint"), frozenset())

    def test_skipped_titles(self):
        for t in ("Japanese Sabo OP13-120", "Sabo OP13-120 PSA 10", "Sabo OP13-120 x4 playset",
                  "Choose your card OP13", "Sabo OP13-120 creased", "Sabo OP13-120 proxy", "サボ OP13-120",
                  "OP13 booster box sealed"):
            self.assertTrue(df.skip_reason(t), t)
        self.assertEqual(df.skip_reason("Sabo OP13-120 Parallel pack fresh NM"), "")
        self.assertEqual(df.skip_reason("Nami OP01-016 Box Topper"), "")


class TestValue(Base):
    def test_takes_the_exact_version(self):
        self.assertEqual(df.value(self.idx, "Sabo OP13-120 Super Alt Art")[1], "12")
        self.assertEqual(df.value(self.idx, "Sabo OP13-120 Red Super Alt Art")[1], "13")
        self.assertEqual(df.value(self.idx, "Sabo OP13-120 Parallel")[1], "11")
        self.assertEqual(df.value(self.idx, "Sabo OP13-120 Wanted Poster")[1], "14")

    def test_title_without_version_is_the_plain_card(self):
        self.assertEqual(df.value(self.idx, "Sabo OP13-120 SEC")[1], "10")

    def test_cheapest_printing_when_several_fit(self):
        m, k, _ = df.value(self.idx, "Zoro OP13-118 Alt Art")
        self.assertEqual(k, "21")
        self.assertAlmostEqual(m, 50.0 * RATE)

    def test_two_numbers_or_unknown_number(self):
        self.assertIsNone(df.value(self.idx, "Sabo OP13-120 and Zoro OP13-118"))
        self.assertIsNone(df.value(self.idx, "Luffy OP99-999"))


class TestEvaluate(Base):
    def test_a_deal(self):
        # parallel Sabo: market 40 x 1.5 = A$60; A$35 + A$2 postage = A$37 -> 38% under, 60*0.87-37 = 15.2 profit
        d = df.evaluate(item(1, "Sabo OP13-120 Parallel NM", 35, post=2), self.idx, self.s)
        self.assertIsNotNone(d)
        self.assertEqual(d["total"], 37.0)
        self.assertAlmostEqual(d["pct"], 38.33, places=1)
        self.assertAlmostEqual(d["profit"], 15.2, places=1)
        self.assertEqual(d["tkey"], "11")

    def test_not_cheap_enough(self):
        self.assertIsNone(df.evaluate(item(2, "Sabo OP13-120 Parallel", 50, post=2), self.idx, self.s))

    def test_overseas_gst_and_hidden_postage_count(self):
        # A$40 from Japan with postage not shown: +A$3 guessed, +A$4 GST = A$47 -> only 21.7% under: no deal
        self.assertIsNone(df.evaluate(item(3, "Sabo OP13-120 Parallel", 40, post=None, country="JP"),
                                      self.idx, self.s))
        d = df.evaluate(item(4, "Sabo OP13-120 Parallel", 30, post=None), self.idx, self.s)
        self.assertTrue(d["guessed_post"])
        self.assertEqual(d["total"], 33.0)

    def test_too_good_to_be_true_is_skipped(self):
        # super alt: A$1,050 market; A$150 is under 20% of it
        self.assertIsNone(df.evaluate(item(5, "Sabo OP13-120 Super Alt Art", 150), self.idx, self.s))
        d = df.evaluate(item(6, "Sabo OP13-120 Super Alt Art", 400), self.idx, self.s)
        self.assertTrue(d["check"])

    def test_low_feedback_and_variation_listings(self):
        self.assertIsNone(df.evaluate(item(7, "Sabo OP13-120 Parallel", 30, pct="95.0"), self.idx, self.s))
        self.assertIsNone(df.evaluate(item(8, "Sabo OP13-120 Parallel", 30, score=3), self.idx, self.s))
        self.assertIsNone(df.evaluate(item(9, "Sabo OP13-120 Parallel", 30, itemGroupType="SELLER_DEFINED_VARIATIONS"),
                                      self.idx, self.s))

    def test_cheap_cards_ignored(self):
        self.assertIsNone(df.evaluate(item(10, "Sabo OP13-120", 0.5), self.idx, self.s))


class TestRun(Base):
    def run_bot(self, tb, items, cfg=CFG, now=1_000_000.0, **kw):
        ew._urlopen = FakeEbay(items)
        return df.run(tb, cfg, now=now, **kw), ew._urlopen

    def test_posts_new_deals_privately_once(self):
        tb = FakeTb()
        deals, fake = self.run_bot(tb, [item(1, "Sabo OP13-120 Parallel", 30), item(2, "Sabo OP13-120 Parallel", 59)])
        self.assertEqual(len(deals), 1)
        self.assertEqual(len(tb.sent), 1)
        hook, payload = tb.sent[0]
        self.assertEqual(hook, CFG["alerts"]["discord_webhook_autobuy"])
        self.assertIn("% under", payload["embeds"][0]["title"])
        self.assertEqual(payload["allowed_mentions"], {"parse": []})
        q = fake.queries[0]
        self.assertEqual(q["sort"], ["newlyListed"])
        self.assertIn("deliveryCountry:AU", q["filter"][0])
        # next round: same listing, same price -> not posted again
        deals, _ = self.run_bot(tb, [item(1, "Sabo OP13-120 Parallel", 30)], now=1_000_000.0 + 3600)
        self.assertEqual(len(deals), 1)
        self.assertEqual(len(tb.sent), 1)
        # it drops another 10%+ -> posted again
        self.run_bot(tb, [item(1, "Sabo OP13-120 Parallel", 25)], now=1_000_000.0 + 7200)
        self.assertEqual(len(tb.sent), 2)

    def test_waits_between_rounds(self):
        tb = FakeTb()
        self.run_bot(tb, [])
        _, fake = self.run_bot(tb, [item(1, "Sabo OP13-120 Parallel", 30)], now=1_000_000.0 + 60)
        self.assertEqual(fake.queries, [])

    def test_searches_are_taken_in_turns(self):
        tb = FakeTb()
        cfg = dict(CFG, deal_finder={"searches_per_hour": 4, "every_minutes": 15, "extra_searches": ["a", "b"],
                                     "min_market": 30, "min_cards_per_set": 3})
        _, f1 = self.run_bot(tb, [], cfg=cfg)
        _, f2 = self.run_bot(tb, [], cfg=cfg, now=1_000_000.0 + 1000)
        _, f3 = self.run_bot(tb, [], cfg=cfg, now=1_000_000.0 + 2000)
        _, f4 = self.run_bot(tb, [], cfg=cfg, now=1_000_000.0 + 3000)     # 1 search a round, back to the start
        self.assertEqual([q["q"][0] for f in (f1, f2, f3, f4) for q in f.queries], ["a", "b", "one piece OP13", "a"])

    def test_big_profit_pushes_phone(self):
        tb = FakeTb()
        self.run_bot(tb, [item(1, "Sabo OP13-120 Super Alt Art", 600)])
        self.assertEqual(len(tb.pushed), 1)
        self.assertIn("OP13-120", tb.pushed[0])

    def test_no_private_channel_never_uses_shared_channels(self):
        tb = FakeTb()
        cfg = {"alerts": {"ebay_client_id": "id", "ebay_client_secret": "secret",
                          "discord_webhook_singles": "https://discord.com/api/webhooks/2/shared"}}
        df._no_channel_said[0] = 0.0
        self.run_bot(tb, [item(1, "Sabo OP13-120 Parallel", 30)], cfg=cfg)
        self.assertEqual(tb.sent, [])
        self.assertEqual(len(tb.status), 1)
        self.assertNotIn("Sabo", tb.status[0])

    def test_cloud_copy_and_no_key_do_nothing(self):
        tb = FakeTb()
        tb.IN_ACTIONS = True
        _, fake = self.run_bot(tb, [item(1, "Sabo OP13-120 Parallel", 30)])
        self.assertEqual(fake.queries, [])
        tb = FakeTb()
        _, fake = self.run_bot(tb, [item(1, "Sabo OP13-120 Parallel", 30)], cfg={"alerts": {}})
        self.assertEqual(fake.queries, [])

    def test_ebay_limit_pauses(self):
        tb = FakeTb()
        ew._urlopen = FakeEbay(status=429)
        df.run(tb, CFG, now=1_000_000.0)
        st = json.loads(tb.files[df.STATE_PATH])
        self.assertGreater(st["pause_until"], 1_000_000.0)

    def test_dry_run_posts_and_saves_nothing(self):
        tb = FakeTb()
        tb.DRY_RUN[0] = True
        deals, _ = self.run_bot(tb, [item(1, "Sabo OP13-120 Parallel", 30)], force=True)
        self.assertEqual(len(deals), 1)
        self.assertEqual(tb.sent, [])
        self.assertEqual(tb.files, {})


if __name__ == "__main__":
    unittest.main()
