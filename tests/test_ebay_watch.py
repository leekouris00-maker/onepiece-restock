"""Tests for ebay_watch.py. No network: eBay's API is replaced with canned replies.

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
import ebay_watch as ew  # noqa: E402

REAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ebay_watch.json")
# The check tests count eBay calls, so they run against the Luffy card alone (the first card in the
# real list), not however many cards the list holds today.
with open(REAL_FILE, encoding="utf-8") as _f:
    _real = json.load(_f)
_real["cards"] = _real["cards"][:1]
CARD_FILE = os.path.join(tempfile.mkdtemp(), "ebay_watch.json")
with open(CARD_FILE, "w", encoding="utf-8") as _f:
    json.dump(_real, _f)
SECRET = "SBX-cert-secret-value-123"


def luffy():
    cards, _ = ew.load_watch(CARD_FILE)
    return cards[0]


def item(iid, title, price, post=None, country="AU", currency="AUD", offers=False):
    it = {"itemId": f"v1|{iid}|0", "legacyItemId": str(iid), "title": title,
          "price": {"value": f"{price:.2f}", "currency": currency},
          "itemWebUrl": f"https://www.ebay.com.au/itm/{iid}?hash=item123&amdata=x",
          "itemLocation": {"country": country}, "buyingOptions": ["FIXED_PRICE"] + (["BEST_OFFER"] if offers else []),
          "seller": {"username": "someone", "feedbackPercentage": "99.8", "feedbackScore": 1234}}
    if post is not None:
        it["shippingOptions"] = [{"shippingCostType": "FIXED", "shippingCost": {"value": f"{post:.2f}", "currency": "AUD"}}]
    return it


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeEbay:
    """Stands in for urllib.request.urlopen: answers the token and search calls, records requests."""

    def __init__(self, items=(), token_status=200, search_status=200, net_error=False, stale_token_once=False):
        self.items, self.token_status, self.search_status = list(items), token_status, search_status
        self.net_error, self.stale_token_once = net_error, stale_token_once
        self.calls = []

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.calls.append(req)
        if self.net_error:
            raise urllib.error.URLError(OSError("no route to host"))
        if url.startswith(ew.TOKEN_URL):
            if self.token_status != 200:
                raise urllib.error.HTTPError(url, self.token_status, "nope", {}, io.BytesIO(b'{"error":"invalid_client"}'))
            return FakeResp(json.dumps({"access_token": f"tok{len(self.calls)}", "expires_in": 7200}).encode())
        if self.stale_token_once:
            self.stale_token_once = False
            raise urllib.error.HTTPError(url, 401, "expired", {}, io.BytesIO(b"{}"))
        if self.search_status != 200:
            raise urllib.error.HTTPError(url, self.search_status, "err", {}, io.BytesIO(b"{}"))
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        cap = float(q["filter"][0].split("[..")[1].split("]")[0])
        hits = [i for i in self.items if float(i["price"]["value"]) <= cap]
        return FakeResp(json.dumps({"total": len(hits), "itemSummaries": hits}).encode())

    def searches(self):
        return [r for r in self.calls if r.full_url.startswith(ew.SEARCH_URL)]

    def tokens(self):
        return [r for r in self.calls if r.full_url.startswith(ew.TOKEN_URL)]


class Base(unittest.TestCase):
    def setUp(self):
        self._open, self._env = ew._urlopen, dict(os.environ)
        self._secrets = ew.SECRETS_PATH
        ew.SECRETS_PATH = os.path.join(tempfile.mkdtemp(), "secrets.json")   # never read a real one
        ew._token.update(value=None, exp=0.0)
        ew._cache["finds"] = []
        ew._said.clear()
        os.environ.pop("EBAY_CLIENT_ID", None)
        os.environ.pop("EBAY_CLIENT_SECRET", None)
        self.cfg = {"alerts": {"ebay_client_id": "my-app-id", "ebay_client_secret": SECRET}}

    def tearDown(self):
        ew._urlopen = self._open
        ew.SECRETS_PATH = self._secrets
        os.environ.clear()
        os.environ.update(self._env)

    def run_check(self, fake, status, **kw):
        ew._urlopen = fake
        out = io.StringIO()
        old, sys.stdout = sys.stdout, out
        try:
            res = ew.check(self.cfg, status, watch_path=CARD_FILE, **kw)
        finally:
            sys.stdout = old
        self.assertNotIn(SECRET, out.getvalue())
        return res


class MatchTests(unittest.TestCase):
    GOOD = [
        "PSA 10 Luffy Promo ST10-006 ONE PIECE DAY 2024 ONE PIECE Card Game Japanese",
        "2024 ONE PIECE JAPANESE PROMOS ONE PIECE DAY #006 MONKEY D. LUFFY PSA 10",
        "PSA 10 Monkey D. Luffy ST10-006 Promo One Piece Day 2024 Visitor Card Japan",
        'PSA 10 ONE PIECE Card Game "One Piece Day 2024" Monkey D Luffy Promo ST10-006 JP',
        "2024 ONE PIECE JPN PROMOS ONE PIECE DAY #006 MONKEY D. LUFFY PSA 10",
        "Monkey D Luffy ST10006 One Piece Day'24 PSA10 Japanese",
    ]
    BAD = [
        "2025 ONE PIECE PROMOS ONE PIECE DAY DALLAS #006 MONKEY D. LUFFY PSA 10",          # English Dallas
        "One Piece Day Dallas Card Monkey D. Luffy ST10-006 PSA 10 English Edition 2025",
        "PSA 10 Monkey D. Luffy ONE PIECE Card ST10-006 1st Anniversary Set Promo Chinese",
        "2024 ONE PIECE JAPANESE PROMOS ONE PIECE DAY #006 MONKEY D. LUFFY PSA 9",
        "Luffy ST10-006 One Piece Day 2024 Japanese promo - PSA 10 candidate!",            # raw card
        "Luffy One Piece Day 2024 ST10-006 BGS 10 Pristine",
        "CGC 10 Luffy ST10-006 One Piece Day 2024 Japanese",
        "Monkey D Luffy P-110 Promo One Piece Day 2025 PSA 10",                           # different card
        "One Piece Day 2024 Luffy ST10-006 PSA 10 + Zoro PSA 10 lot",
        "Luffy ST10-006 One Piece Day 2024 PSA 100 custom display",
    ]

    def test_the_card_matches(self):
        for t in self.GOOD:
            self.assertTrue(ew.title_matches(t, luffy()), t)

    def test_other_versions_and_raw_cards_do_not(self):
        for t in self.BAD:
            self.assertFalse(ew.title_matches(t, luffy()), t)


class CostTests(unittest.TestCase):
    def test_australian_seller_no_gst(self):
        self.assertEqual(ew.cost(item(1, "x", 520, post=10, country="AU")), (520.0, 10.0, 0.0, 530.0))

    def test_overseas_seller_adds_gst_on_item_and_postage(self):
        self.assertEqual(ew.cost(item(1, "x", 450, post=25, country="JP")), (450.0, 25.0, 47.5, 522.5))

    def test_free_and_missing_postage(self):
        self.assertEqual(ew.cost(item(1, "x", 500, post=0, country="AU"))[3], 500.0)
        self.assertEqual(ew.cost(item(1, "x", 500, country="AU")), (500.0, None, 0.0, 500.0))

    def test_gst_can_be_switched_off(self):
        self.assertEqual(ew.cost(item(1, "x", 450, post=25, country="US"), add_gst=False)[3], 475.0)

    def test_non_aud_price_skipped(self):
        self.assertIsNone(ew.cost(item(1, "x", 300, currency="USD")))


class CheckTests(Base):
    GOOD = "2024 ONE PIECE JAPANESE PROMOS ONE PIECE DAY #006 MONKEY D. LUFFY PSA 10"

    def listing_set(self):
        return [
            item(111, self.GOOD, 455, post=20, country="JP", offers=True),   # 455+20+47.50 = 522.50 -> alert
            item(222, self.GOOD, 540, post=15, country="AU"),               # 555 delivered -> over max
            item(333, "2025 ONE PIECE PROMOS ONE PIECE DAY DALLAS #006 MONKEY D. LUFFY PSA 10", 300, post=0),
            item(444, "PSA 10 Luffy Promo ST10-006 ONE PIECE DAY 2024 Japanese", 480, country="AU"),  # no post shown
        ]

    def test_no_key_does_nothing(self):
        self.cfg = {}
        fake = FakeEbay(self.listing_set())
        res = self.run_check(fake, {})
        self.assertFalse(res.active or res.ran)
        self.assertEqual(res.finds, [])
        self.assertEqual(fake.calls, [])
        self.assertIsNone(ew.status_message({}, res))

    def test_finds_only_the_card_at_or_under_max_delivered(self):
        fake, status = FakeEbay(self.listing_set()), {}
        res = self.run_check(fake, status, now=1_000_000)
        self.assertTrue(res.ran)
        self.assertEqual([f["id"] for f in res.finds], ["ebay|v1|444|0", "ebay|v1|111|0"])
        f = res.finds[1]
        self.assertEqual(f["price"], 522.5)
        self.assertEqual(f["kind"], "Single")
        self.assertEqual(f["shop"], "eBay (from Japan)")
        self.assertEqual(f["url"], "https://www.ebay.com.au/itm/111")
        self.assertIn("A$47.50 GST (est.)", f["note"])
        self.assertIn("accepts offers", f["note"])
        self.assertIn("psacard.com/cert", f["note"])
        self.assertNotIn("someone", f["note"])                     # no seller usernames kept
        self.assertIn("postage not shown", res.finds[0]["note"])
        self.assertEqual(status["ebay_ts"], 1_000_000)
        self.assertEqual(len(fake.tokens()), 1)
        self.assertEqual(len(fake.searches()), 2)

    def test_request_shape(self):
        fake = FakeEbay(self.listing_set())
        self.run_check(fake, {}, now=1_000_000)
        r = fake.searches()[0]
        self.assertEqual(r.get_header("X-ebay-c-marketplace-id"), "EBAY_AU")
        self.assertEqual(r.get_header("X-ebay-c-enduserctx"), "contextualLocation=country%3DAU")
        self.assertEqual(r.get_header("Authorization"), "Bearer tok1")
        flt = urllib.parse.parse_qs(urllib.parse.urlsplit(r.full_url).query)["filter"][0]
        self.assertEqual(flt, "price:[..550.00],priceCurrency:AUD,buyingOptions:{FIXED_PRICE},deliveryCountry:AU")
        tok = fake.tokens()[0]
        self.assertEqual(tok.get_method(), "POST")
        self.assertIn(b"grant_type=client_credentials", tok.data)

    def test_waits_between_checks_and_reuses_token(self):
        fake, status = FakeEbay(self.listing_set()), {}
        first = self.run_check(fake, status, now=1_000_000)
        n = len(fake.calls)
        soon = self.run_check(fake, status, now=1_000_000 + 5 * 60)
        self.assertFalse(soon.ran)
        self.assertEqual(len(fake.calls), n)                               # eBay not asked
        self.assertEqual([f["id"] for f in soon.finds], [f["id"] for f in first.finds])  # last finds kept
        later = self.run_check(fake, status, now=1_000_000 + 16 * 60)
        self.assertTrue(later.ran)
        self.assertEqual(len(fake.tokens()), 1)                            # token reused
        forced = self.run_check(fake, status, now=1_000_000 + 17 * 60, force=True)
        self.assertTrue(forced.ran)

    def test_key_from_environment_or_secrets_file(self):
        self.cfg = {}
        os.environ["EBAY_CLIENT_ID"], os.environ["EBAY_CLIENT_SECRET"] = "env-id", SECRET
        self.assertEqual(ew.credentials({}), ("env-id", SECRET))
        os.environ.pop("EBAY_CLIENT_ID")
        os.environ.pop("EBAY_CLIENT_SECRET")
        with open(ew.SECRETS_PATH, "w", encoding="utf-8") as f:
            json.dump({"ebay_client_id": "file-id", "ebay_client_secret": SECRET, "discord_webhook_boxes": ""}, f)
        self.assertEqual(ew.credentials({}), ("file-id", SECRET))
        with open(ew.SECRETS_PATH, "w", encoding="utf-8") as f:
            json.dump({"ebay_client_id": "", "ebay_client_secret": ""}, f)
        self.assertEqual(ew.credentials({}), (None, None))

    def test_refused_key_posts_once(self):
        fake, status = FakeEbay(self.listing_set(), token_status=401), {}
        res = self.run_check(fake, status, now=1_000_000)
        self.assertFalse(res.ran)
        self.assertEqual(res.kind, "key")
        self.assertNotIn(SECRET, res.problem)
        text, _ = ew.status_message(status, res)
        self.assertIn("refused the key", text)
        res = self.run_check(fake, status, now=1_000_000 + 16 * 60)
        self.assertIsNone(ew.status_message(status, res))                   # same problem: no repeat

    def test_network_trouble_posts_after_three_and_recovery_is_announced(self):
        status = {"ebay_state": "ok"}
        t = 1_000_000
        for i in range(3):
            res = self.run_check(FakeEbay(net_error=True), status, now=t + i * 16 * 60)
            msg = ew.status_message(status, res)
            self.assertEqual(msg is not None, i == 2, i)
        self.assertIn("couldn't reach eBay", msg[0])
        res = self.run_check(FakeEbay(self.listing_set()), status, now=t + 4 * 16 * 60)
        self.assertEqual(ew.status_message(status, res)[0], "✅ **eBay watch is working again.**")

    def test_first_success_announces_watch_once(self):
        status = {}
        res = self.run_check(FakeEbay(self.listing_set()), status, now=1_000_000)
        text, _ = ew.status_message(status, res)
        self.assertIn("eBay watch is on", text)
        self.assertIn("up to $550 delivered", text)
        res = self.run_check(FakeEbay(self.listing_set()), status, now=1_000_000 + 16 * 60)
        self.assertIsNone(ew.status_message(status, res))

    def test_stale_token_is_renewed_once(self):
        fake = FakeEbay(self.listing_set(), stale_token_once=True)
        res = self.run_check(fake, {}, now=1_000_000)
        self.assertTrue(res.ran)
        self.assertEqual(len(fake.tokens()), 2)

    def test_daily_limit(self):
        res = self.run_check(FakeEbay(self.listing_set(), search_status=429), {}, now=1_000_000)
        self.assertEqual(res.kind, "limit")

    def test_broken_watch_file_is_ignored(self):
        bad = os.path.join(tempfile.mkdtemp(), "ebay_watch.json")
        with open(bad, "w", encoding="utf-8") as f:
            f.write('{"cards": [{"name": "x", "max": "lots"}, ')
        ew._urlopen = FakeEbay()
        res = ew.check(self.cfg, {}, watch_path=bad)
        self.assertFalse(res.active)
        with open(bad, "w", encoding="utf-8") as f:
            json.dump({"cards": [{"name": "no max", "search": "x"}, {"name": "off", "max": 5, "enabled": False}]}, f)
        self.assertEqual(ew.load_watch(bad)[0], [])


if __name__ == "__main__":
    unittest.main()


class RealListTests(unittest.TestCase):
    def test_every_card_in_the_real_list_loads(self):
        with open(REAL_FILE, encoding="utf-8") as f:
            wanted = [c for c in json.load(f)["cards"] if c.get("enabled", True)]
        cards, _ = ew.load_watch(REAL_FILE)
        self.assertEqual(len(cards), len(wanted))

    def test_nike_shoe_size_filter(self):
        cards, _ = ew.load_watch(REAL_FILE)
        g = next(c for c in cards if "Gomu Gomu - US 10" in c["name"])
        self.assertTrue(ew.title_matches("Nike Air Max Plus TN One Piece Gomu Gomu IR0968-500 US 10", g))
        self.assertTrue(ew.title_matches("Nike TN Air Max Plus One Piece Gomu Gomu UK9 / US10", g))
        self.assertFalse(ew.title_matches("Nike Air Max Plus One Piece Gomu Gomu US 10.5", g))
        self.assertFalse(ew.title_matches("Nike Air Max Plus One Piece Gomu Gomu Womens US 10", g))
        self.assertFalse(ew.title_matches("One Piece x Nike Air Max Plus Gomu Gomu DON!! Promo Card", g))

    def test_half_sizes_never_pass_as_whole_sizes(self):
        cards, _ = ew.load_watch(REAL_FILE)
        g = next(c for c in cards if "Gomu Gomu - US 10" in c["name"])
        # the real listing that slipped through on 22 Oct 2026
        self.assertFalse(ew.title_matches(
            'IR0968-500 One Piece × Nike Air Max Plus "Devil Fruits/Gomu Gomu" US10.5 ✅✅', g))
        for size in ("US10.5", "US 10.5", "Size 10½", "US 10 1/2", "US M10.5", "sz 10,5", "10.5 US"):
            self.assertFalse(ew.title_matches(f"Nike Air Max Plus One Piece Gomu Gomu {size}", g), size)
        for size in ("US10", "US 10", "Size 10", "US M10", "Men's US 10", "10 US"):
            self.assertTrue(ew.title_matches(f"Nike Air Max Plus One Piece Gomu Gomu {size}", g), size)
        self.assertTrue(ew.title_matches(
            'IR0968-500 One Piece × Nike Air Max Plus "Devil Fruits/Gomu Gomu" (Men\'s US 10)', g))

    def test_half_size_rule_leaves_other_titles_alone(self):
        self.assertEqual(ew._norm("Luffy PSA 10 ST10-006 $10.50"), " luffy psa 10 st10 006 10 50 ")
        self.assertTrue(ew.title_matches("PSA 10 Luffy Promo ST10-006 ONE PIECE DAY 2024 Japanese", luffy()))


class MultiCardTests(Base):
    """A listing that matches several watched cards (a set) is one alert, named after all of them."""

    def test_set_is_one_alert(self):
        with open(REAL_FILE, encoding="utf-8") as f:
            data = json.load(f)
        data["cards"] = [c for c in data["cards"] if c["name"].endswith("DON!! card (Japanese)")]
        path = os.path.join(tempfile.mkdtemp(), "ebay_watch.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        fake = FakeEbay([
            item(900, "NIKE x ONE PIECE 3 DON!! Cards Set Gomu Mera Ope Japanese Promo NO LUFFY", 85, post=5, country="JP"),
            item(901, "PRESALE Nike x ONE PIECE TCG Mera Mera DON!! Air Max Plus Jump Promo Japanese", 110, post=10, country="JP"),
        ])
        ew._urlopen = fake
        out, old = io.StringIO(), sys.stdout
        sys.stdout = out
        try:
            res = ew.check(self.cfg, {}, watch_path=path, now=1_000_000)
        finally:
            sys.stdout = old
        by_id = {f["id"]: f for f in res.finds}
        self.assertEqual(len(res.finds), 2)
        s = by_id["ebay|v1|900|0"]
        self.assertEqual(s["name"], "Gomu Gomu DON!! card (Japanese) + Mera Mera DON!! card (Japanese) + "
                                    "Ope Ope DON!! card (Japanese)")
        self.assertIn("3 of your cards", s["note"])
        self.assertEqual(s["price"], 99.0)
        one = by_id["ebay|v1|901|0"]
        self.assertEqual(one["name"], "Nike x One Piece Mera Mera DON!! card (Japanese)")
        self.assertNotIn("of your cards", one["note"])

    def test_nike_don_cards(self):
        cards, _ = ew.load_watch(REAL_FILE)
        en = next(c for c in cards if c["name"] == "Nike x One Piece Gomu Gomu DON!! card (English)")
        jp = next(c for c in cards if c["name"] == "Nike x One Piece Gomu Gomu DON!! card (Japanese)")
        t = "One Piece x Nike Air Max Plus Gomu Gomu DON!! Promo Card (English)"
        self.assertTrue(ew.title_matches(t, en))
        self.assertFalse(ew.title_matches(t, jp))
        self.assertTrue(ew.title_matches("Nike Air Max Plus Gomu Gomu DON!! Promo Card Japanese", jp))
        self.assertFalse(ew.title_matches("Nike Gomu Gomu DON card English PSA 10", en))
        self.assertFalse(ew.title_matches("Nike Premium Card Collection 34 card set Japanese Gomu DON", jp))
