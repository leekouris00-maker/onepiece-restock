"""Tests for auto_buy.py (v2.11): what may be auto-bought, the spend limits, reading a checkout's total,
and the checkout itself against fake Shopify checkout pages on a local server (headless Chromium).
No real shops, no real payments, no Discord.

Run:  python -m unittest discover -s tests
"""
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import auto_buy as ab  # noqa: E402
import fast_lane as fl  # noqa: E402
import tcg_bot as tb  # noqa: E402

S = dict(ab.DEFAULTS, mode="live", until=0)
S["what"], S["games"] = ["boxes", "watch"], ["onepiece"]


def box(**kw):
    f = {"id": "box|Gumnut|op-13", "kind": "Booster box", "name": "OP-13 Booster Box", "shop": "Gumnut",
         "price": 240.0, "url": "https://gumnut.test/products/op-13", "cart": "https://gumnut.test/cart/111:1", "note": ""}
    f.update(kw)
    return f


def quiet(fn, *a, **kw):
    out, old = io.StringIO(), sys.stdout
    sys.stdout = out
    try:
        return fn(*a, **kw)
    finally:
        sys.stdout = old


class Eligible(unittest.TestCase):
    def test_box_restock_ok(self):
        self.assertEqual(ab.eligible(box(), S), (True, ""))

    def test_never_new_listings_preorders_pokemon_or_woo(self):
        self.assertFalse(ab.eligible(box(kind="New listing"), S)[0])
        self.assertFalse(ab.eligible(box(note="pre-order"), S)[0])
        self.assertFalse(ab.eligible(box(name="OP-14 Booster Box (Pre-Order)"), S)[0])
        self.assertFalse(ab.eligible(box(game="pokemon"), S)[0])
        self.assertFalse(ab.eligible(box(cart="https://jtoys.test/checkout/?add-to-cart=5&quantity=1"), S)[0])
        self.assertFalse(ab.eligible(box(kind="Single"), S)[0])
        self.assertFalse(ab.eligible(box(kind="Sealed"), S)[0])          # watched sealed: off by default

    def test_preorders_and_sealed_when_switched_on(self):
        s = dict(S, preorders=True, what=["boxes", "sealed"])
        self.assertTrue(ab.eligible(box(note="pre-order"), s)[0])
        self.assertTrue(ab.eligible(box(kind="Sealed"), s)[0])

    def test_watch_link_quantity_capped(self):
        f = box(kind="Sealed", link_watch=True, cart_qty=5)
        self.assertTrue(ab.eligible(f, S)[0])
        self.assertEqual(ab.cart_for(f, S), ("https://gumnut.test/cart/111:2", 2))


class Limits(unittest.TestCase):
    def led(self, *orders):
        return {"orders": [dict(o) for o in orders]}

    def test_per_order_and_per_day(self):
        now = time.time()
        self.assertTrue(ab.budget_ok(self.led(), "x", 240, S, now)[0])
        self.assertFalse(ab.budget_ok(self.led(), "x", 320, S, now)[0])
        led = self.led({"t": now - 60, "id": "y", "mode": "live", "status": "paid", "total": 100})
        self.assertFalse(ab.budget_ok(led, "x", 240, S, now)[0])         # 100 + 240 > 300 a day
        self.assertTrue(ab.budget_ok(led, "x", 190, S, now)[0])

    def test_unclear_and_paying_count_tests_and_stops_dont(self):
        now = time.time()
        for st in ("paying", "unclear", "bank"):
            led = self.led({"t": now, "id": "y", "mode": "live", "status": st, "total": 200})
            self.assertFalse(ab.budget_ok(led, "x", 150, S, now)[0], st)
        for o in ({"t": now, "id": "y", "mode": "test", "status": "test", "total": 200},
                  {"t": now, "id": "y", "mode": "live", "status": "stopped", "total": 200},
                  {"t": now, "id": "y", "mode": "live", "status": "declined", "total": 200}):
            self.assertTrue(ab.budget_ok(self.led(o), "x", 150, S, now)[0], o)

    def test_orders_per_day_and_same_product(self):
        now = time.time()
        two = self.led(*({"t": now, "id": f"y{i}", "mode": "live", "status": "paid", "total": 1} for i in range(2)))
        self.assertFalse(ab.budget_ok(two, "x", 10, S, now)[0])
        led = self.led({"t": now - 3 * 86400, "id": "x", "mode": "live", "status": "paid", "total": 240})
        self.assertFalse(ab.budget_ok(led, "x", 10, S, now)[0])           # same box 3 days ago
        led["orders"][0]["t"] = now - 8 * 86400
        self.assertTrue(ab.budget_ok(led, "x", 10, S, now)[0])
        yesterday = self.led({"t": now - 86400 - 3600, "id": "y", "mode": "live", "status": "paid", "total": 290})
        roomy = dict(S, per_week=5000, per_month=5000)
        self.assertTrue(ab.budget_ok(yesterday, "x", 240, roomy, now)[0])  # yesterday's spend doesn't count today

    def test_total_with_postage(self):
        self.assertFalse(ab.total_ok({"orders": []}, 312.50, S)[0])
        self.assertTrue(ab.total_ok({"orders": []}, 252.50, S)[0])


class Totals(unittest.TestCase):
    def test_shopify_summary(self):
        text = ("Order summary\nOP-13 Booster Box\n1\n$240.00\nSubtotal\n$240.00\nShipping\n$12.50\n"
                "Total\nAUD $252.50\nIncluding $22.95 in taxes\nTOTAL SAVINGS\n$5.00")
        self.assertEqual(ab.read_total(text), 252.50)
        self.assertEqual(ab.read_subtotal(text), 240.00)

    def test_variants(self):
        self.assertEqual(ab.read_total("Subtotal $1,240.00 Shipping FREE Total AUD $1,240.00"), 1240.0)
        self.assertEqual(ab.read_total("Total (AUD) A$99.95"), 99.95)
        self.assertEqual(ab.read_total("Total savings $5.00\nTotal\n$80.00"), 80.0)
        self.assertIsNone(ab.read_total("Subtotal $10.00"))


class List(unittest.TestCase):
    def items(self):
        return [ab.make_item(code="OP-15", max=240, qty=2), ab.make_item(code="EB-05", max=230),
                ab.make_item(match="premium booster|prb, 02", max=300, name="PRB-02")]

    def test_codes(self):
        self.assertEqual(ab.norm_code("op15"), "OP-15")
        self.assertEqual(ab.norm_code(" eb-5 "), "EB-05")
        self.assertEqual(ab.norm_code("PRB-02"), "PRB-02")
        self.assertEqual(ab.norm_code("OP-15 box"), "")
        rx = ab.code_rx("EB-05")
        self.assertTrue(rx.search("Extra Booster EB05 Booster Box") and rx.search("eb-5 box"))
        self.assertFalse(ab.code_rx("OP-15").search("OP-150 promo"))

    def test_matching_max_and_kind(self):
        its = self.items()
        self.assertEqual(ab.item_for(box(name="OP-15 Adventure on Kami's Island Booster Box", price=230), its)["id"], "op-15")
        self.assertIsNone(ab.item_for(box(name="OP-15 Booster Box", price=245), its))          # over its max
        self.assertIsNone(ab.item_for(box(name="OP-15 Card Sleeves", kind="Sealed", price=20), its))
        self.assertIsNone(ab.item_for(box(name="OP-16 Booster Box", price=200), its))          # not on the list
        prb = box(name="Premium Booster Box PRB-02 (English)", kind="Sealed", link_watch=True, price=290)
        self.assertEqual(ab.item_for(prb, its)["name"], "PRB-02")
        self.assertFalse(ab.eligible(box(name="OP-16 Booster Box"), dict(S, what=["list"]), its)[0])
        self.assertTrue(ab.eligible(box(name="OP-15 Booster Box", price=230), dict(S, what=["list"]), its)[0])

    def test_quantity_left(self):
        its = self.items()
        f = box(name="OP-15 Booster Box", price=230)
        self.assertEqual(ab.cart_for(f, S, its[0]), ("https://gumnut.test/cart/111:2", 2))
        its[0]["bought"] = 1
        self.assertEqual(ab.cart_for(f, S, its[0])[1], 1)
        its[0]["bought"] = 2
        self.assertIsNone(ab.item_for(f, its))                                                 # got them all

    def test_week_and_month_budgets(self):
        now = time.time()
        s = dict(S, per_day=1000, per_week=500, per_month=700)
        led = {"orders": [{"t": now - 60, "id": "y", "mode": "live", "status": "paid", "total": 300}]}
        self.assertIn("this week", ab.budget_ok(led, "x", 240, s, now)[1])
        self.assertTrue(ab.budget_ok(led, "x", 190, s, now)[0])
        from datetime import date, timedelta as td
        d = date.fromtimestamp(now)
        earlier = [t for t in (now - k * 86400 for k in range(7, 28))
                   if date.fromtimestamp(t).month == d.month and date.fromtimestamp(t).isocalendar()[1] != d.isocalendar()[1]]
        if earlier:                                       # an order earlier this month, in another week
            led = {"orders": [{"t": earlier[0], "id": "y", "mode": "live", "status": "paid", "total": 500}]}
            self.assertIn("this month", ab.budget_ok(led, "x", 240, s, now)[1])
            self.assertIn("this month", ab.total_ok(led, 250, s, now)[1])


class Wiring(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.paths = (tb.CONTROLS_PATH, ab.LEDGER_PATH, ab.LIST_PATH)
        tb.CONTROLS_PATH = os.path.join(self.dir, "controls.json")
        ab.LEDGER_PATH = os.path.join(self.dir, "autobuy.json")
        ab.LIST_PATH = os.path.join(self.dir, "autobuy_list.json")
        self.start = ab.start
        ab.start = lambda _tb: None
        while not ab._q.empty():
            ab._q.get_nowait()
        ab._busy.clear()

    def tearDown(self):
        tb.CONTROLS_PATH, ab.LEDGER_PATH, ab.LIST_PATH = self.paths
        ab.start = self.start
        while not ab._q.empty():
            ab._q.get_nowait()
        ab._busy.clear()
        shutil.rmtree(self.dir)

    def ctl(self, **kw):
        tb.atomic_write_json(tb.CONTROLS_PATH, {"autobuy": kw})

    def test_off_by_default_and_expiry(self):
        self.assertEqual(ab.settings(tb, {})["mode"], "off")
        self.ctl(mode="live", until=time.time() - 5)
        self.assertEqual(ab.settings(tb, {})["mode"], "off")
        self.ctl(mode="test", until=0, per_order=150)
        s = ab.settings(tb, {"auto_buy": {"per_order": 400, "per_day": 500}})
        self.assertEqual((s["mode"], s["per_order"], s["per_day"]), ("test", 150, 500))

    def test_offer_marks_the_alert_and_desk_mode_skips_it(self):
        self.ctl(mode="live", until=0)
        ab.save_items(tb, [ab.make_item(code="OP-13", max=250)])
        finds = [box(), box(id="list|x", kind="New listing"), box(id="box|y|z", game="pokemon")]
        taken = quiet(ab.offer, tb, {}, finds)
        self.assertEqual([f["id"] for f in taken], ["box|Gumnut|op-13"])
        self.assertTrue(finds[0]["autobuy"])
        self.assertEqual(finds[0]["note"], "")                 # friends see the alert: it doesn't say it's auto-buying
        self.assertEqual(ab._q.qsize(), 1)
        quiet(ab.offer, tb, {}, [box()])                       # already queued: not twice
        self.assertEqual(ab._q.qsize(), 1)
        tb.atomic_write_json(tb.CONTROLS_PATH, {"desk_until": time.time() + 3600})
        opened = []
        quiet(fl.desk_open, tb, [finds[0], box(id="box|b|c", cart="https://b.test/cart/9:1")], opener=opened.append)
        self.assertEqual(opened, ["https://b.test/cart/9:1"])

    def test_list_starts_with_this_seasons_boxes_and_counts_buys(self):
        items = ab.load_items(tb)
        self.assertEqual([it["code"] for it in items], ["OP-14", "OP-15", "OP-16", "OP-17", "OP-18", "EB-05"])
        self.assertTrue(all(it["max"] == 260 and it["qty"] == 1 for it in items))
        it = ab.count_bought(tb, "op-15", 1)
        self.assertEqual(it["bought"], 1)
        self.assertIsNone(ab.item_for(box(name="OP-15 Booster Box", price=220), ab.load_items(tb)))

    def test_offer_takes_one_per_item_cheapest_shop(self):
        self.ctl(mode="test", until=0)
        ab.save_items(tb, [ab.make_item(code="OP-15", max=250)])
        a = box(id="box|A|op15", name="OP-15 Booster Box", price=240, cart="https://a.test/cart/1:1")
        b = box(id="box|B|op15", name="OP-15 Booster Box", price=225, cart="https://b.test/cart/2:1")
        c = box(id="box|C|op16", name="OP-16 Booster Box", price=200, cart="https://c.test/cart/3:1")
        taken = quiet(ab.offer, tb, {}, [a, b, c])
        self.assertEqual([f["id"] for f in taken], ["box|B|op15"])
        self.assertEqual(ab._q.get_nowait()["item"], "op-15")

    def test_offer_does_nothing_when_off(self):
        self.assertEqual(quiet(ab.offer, tb, {}, [box()]), [])
        self.assertEqual(ab._q.qsize(), 0)


# ---------------------------------------------------------------- fake Shopify checkout
PAID = []

PAGE = """<html><body><main>
<h2>Delivery</h2><p>Lee K, 1 Test St, Vermont VIC 3133</p>
{card}{captcha}
<h2>Order summary</h2><p>OP-13 Booster Box</p><p>1</p><p>$240.00</p>
<p>Subtotal</p><p>{sub}</p><p>Shipping</p><p>$12.50</p><p>Total</p><p>AUD {total}</p>
<form method="post" action="{pay}"><button type="submit">Pay now</button></form>
</main></body></html>"""


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, body, code=200, loc=None):
        self.send_response(code)
        if loc:
            self.send_header("Location", loc)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):
        p = self.path
        if p.startswith("/cart/"):
            vid = p.split("/cart/")[1].split(":")[0]
            if vid == "6":
                return self.send("", 302, "/account/login?checkout_url=x")
            if vid == "7":
                return self.send("<p>Sorry, this product is sold out.</p>")
            return self.send("", 302, f"/checkouts/cn/c{vid}")
        if p.startswith("/checkouts/cn/") and p.endswith("/thank-you"):
            return self.send("<h1>Thank you, Lee!</h1><p>Your order is confirmed</p>")
        if p.startswith("/checkouts/cn/"):
            vid = p.split("/c")[-1]
            card = '<iframe src="/card-fields.html" width="300" height="60"></iframe>' if vid == "2" else ""
            cap = '<iframe src="/hcaptcha.html" width="300" height="80"></iframe>' if vid == "4" else ""
            total, sub = ("$352.50", "$240.00") if vid == "5" else ("$252.50", "$240.00")
            if vid == "8":
                sub, total = "$480.00", "$492.50"
            return self.send(PAGE.format(card=card, captcha=cap, total=total, sub=sub, pay=f"/pay/{vid}"))
        if p == "/card-fields.html":
            return self.send('<input name="number" autocomplete="cc-number" placeholder="Card number">')
        if p == "/hcaptcha.html":
            return self.send("<p>I am human</p>")
        if p.startswith("/decline"):
            return self.send("<p>Your card was declined. Try a different payment method.</p>"
                             "<button>Pay now</button>")
        if p.startswith("/bank"):
            return self.send('<p>Waiting for your bank</p><iframe src="/acs/3ds-challenge.html"></iframe>')
        if p.startswith("/acs/"):
            return self.send("<p>Approve in your banking app</p>")
        return self.send("not found", 404)

    def do_POST(self):
        vid = self.path.split("/pay/")[-1]
        PAID.append(vid)
        if vid == "3":
            return self.send("", 303, "/decline")
        if vid == "9":
            return self.send("", 303, "/bank")
        return self.send("", 303, f"/checkouts/cn/c{vid}/thank-you")


class Checkout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise unittest.SkipTest("playwright not installed")
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch()
        except Exception as e:  # noqa: BLE001
            cls.pw.stop()
            raise unittest.SkipTest(f"no Chromium: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()

    def run_one(self, vid, mode="live", led=None, s=None):
        PAID.clear()
        page = self.browser.new_page()
        try:
            return ab.checkout(page, f"{self.base}/cart/{vid}:1", 240.0, s or S, mode,
                               led if led is not None else {"orders": []}, box(), tb=None, timeout=6)
        finally:
            page.close()

    def test_live_pays_and_confirms(self):
        led = {"orders": []}
        r = self.run_one("1", led=led)
        self.assertEqual((r["status"], r["total"], PAID), ("paid", 252.50, ["1"]))
        self.assertEqual(led["orders"][0]["status"], "paying")         # counted before Pay was pressed

    def test_test_mode_never_presses_pay(self):
        r = self.run_one("1", mode="test")
        self.assertEqual((r["status"], r["total"], PAID), ("test", 252.50, []))

    def test_stops_for_card_captcha_login_sold_out(self):
        for vid, word in (("2", "card"), ("4", "captcha"), ("6", "signed in"), ("7", "sold out")):
            r = self.run_one(vid)
            self.assertEqual(r["status"], "stopped", vid)
            self.assertIn(word, r["why"], vid)
            self.assertEqual(PAID, [], vid)

    def test_stops_over_limits_and_wrong_cart(self):
        r = self.run_one("5")
        self.assertEqual(r["status"], "stopped")
        self.assertIn("per-order", r["why"])
        led = {"orders": [{"t": time.time(), "id": "y", "mode": "live", "status": "paid", "total": 100}]}
        r = self.run_one("1", led=led)
        self.assertIn("today's spend", r["why"])
        r = self.run_one("8", s=dict(S, per_order=600, per_day=600))
        self.assertIn("something else is in this checkout", r["why"])
        self.assertEqual(PAID, [])

    def test_declined(self):
        r = self.run_one("3")
        self.assertEqual(r["status"], "declined")
        self.assertIn("declined", r["why"])

    def test_bank_check_that_never_finishes_is_unclear(self):
        r = self.run_one("9", s=dict(S, pay_wait_seconds=30))
        self.assertEqual(r["status"], "unclear")


class Handle(unittest.TestCase):
    """Buyer.handle end to end: the ledger and the report, posting switched off (dry run)."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.saved = (tb.CONTROLS_PATH, ab.LEDGER_PATH, ab.SHOTS_DIR, tb.DRY_RUN[0], ab.LIST_PATH)
        ab.LIST_PATH = os.path.join(self.dir, "autobuy_list.json")
        tb.CONTROLS_PATH = os.path.join(self.dir, "controls.json")
        ab.LEDGER_PATH = os.path.join(self.dir, "autobuy.json")
        ab.SHOTS_DIR = os.path.join(self.dir, "shots")

    def tearDown(self):
        tb.CONTROLS_PATH, ab.LEDGER_PATH, ab.SHOTS_DIR, tb.DRY_RUN[0], ab.LIST_PATH = self.saved
        shutil.rmtree(self.dir)

    def test_budget_blocks_before_opening_a_browser(self):
        tb.atomic_write_json(tb.CONTROLS_PATH, {"autobuy": {"mode": "live", "per_order": 100}})
        tb.DRY_RUN[0] = True                   # nothing posted to Discord
        opened = []
        b = ab.Buyer(tb, launcher=lambda s: opened.append(1))
        r = quiet(b.handle, {"f": box(), "t": time.time(), "mode": "live"})
        self.assertEqual(r["status"], "skipped")
        self.assertEqual(opened, [])

    def test_item_already_bought_dropped(self):
        tb.atomic_write_json(tb.CONTROLS_PATH, {"autobuy": {"mode": "live"}})
        ab.save_items(tb, [ab.make_item(code="OP-15", max=250, bought=1)])
        tb.DRY_RUN[0] = True
        b = ab.Buyer(tb, launcher=lambda s: self.fail("opened"))
        job = {"f": box(name="OP-15 Booster Box", price=230), "t": time.time(), "mode": "live", "item": "op-15"}
        self.assertIsNone(quiet(b.handle, job))

    def test_stale_and_off_jobs_dropped(self):
        tb.atomic_write_json(tb.CONTROLS_PATH, {"autobuy": {"mode": "live"}})
        tb.DRY_RUN[0] = True
        b = ab.Buyer(tb, launcher=lambda s: self.fail("opened"))
        self.assertIsNone(quiet(b.handle, {"f": box(), "t": time.time() - 600, "mode": "live"}))
        tb.DRY_RUN[0] = False
        tb.atomic_write_json(tb.CONTROLS_PATH, {"autobuy": {"mode": "off"}})
        tb.DRY_RUN[0] = True
        self.assertIsNone(quiet(b.handle, {"f": box(), "t": time.time(), "mode": "live"}))


class Private(unittest.TestCase):
    """v2.11.3: friends are in the server. Auto-buy posts only to its own private channel."""

    def setUp(self):
        self.sent, self.status = [], []
        self.saved = (tb.discord_send, tb.post_status, tb.load_config, tb.DRY_RUN[0], ab._no_channel_said[0])
        tb.discord_send = lambda alerts, hook, payload, tries=3: self.sent.append(hook) or True
        tb.post_status = lambda cfg, text, color=0: self.status.append(text)
        tb.DRY_RUN[0] = False
        ab._no_channel_said[0] = 0.0

    def tearDown(self):
        tb.discord_send, tb.post_status, tb.load_config, tb.DRY_RUN[0], ab._no_channel_said[0] = self.saved

    def test_never_to_shared_channels(self):
        cfg = {"alerts": {"discord_webhook_status": "https://discord.test/status", "discord_webhook": "https://discord.test/main",
                          "discord_webhook_boxes": "https://discord.test/boxes"}}
        quiet(ab.post, tb, "✅ Bought it: OP-15 box, delivered to 1 Test St", tb.GREEN, cfg=cfg)
        quiet(ab.post, tb, "✅ Bought another", tb.GREEN, cfg=cfg)
        self.assertEqual(self.sent, [])
        self.assertEqual(len(self.status), 1)                  # one heads-up, with no details in it
        self.assertNotIn("OP-15", self.status[0])
        self.assertNotIn("Test St", self.status[0])
        cfg["alerts"]["discord_webhook_autobuy"] = "https://discord.test/private"
        quiet(ab.post, tb, "✅ Bought it", tb.GREEN, cfg=cfg)
        self.assertEqual(self.sent, ["https://discord.test/private"])

    def test_private_channel_overwrites(self):
        import add_channels as ac
        calls = []

        def api(token, method, path, body=None, auth=True, url=None):
            calls.append((method, path, body))
            if path == "/users/@me":
                return {"id": "999"}
            if path.endswith("/channels") and method == "GET":
                return [{"id": "50", "type": 4, "name": ac.CATEGORY}]
            if method == "POST" and path.endswith("/channels"):
                return {"id": "77", **body}
            if path.endswith("/webhooks") and method == "GET":
                return []
            if path.endswith("/webhooks"):
                return {"id": "1", "token": "abc"}
            return {}
        old = ac.api
        ac.api = api
        try:
            res = ac.make_private("tok", 123, ["555"])
        finally:
            ac.api = old
        self.assertEqual(res["hooks"]["discord_webhook_autobuy"][0], "https://discord.com/api/webhooks/1/abc")
        body = next(b for m, p, b in calls if m == "POST" and p == "/guilds/123/channels")
        over = {o["id"]: o for o in body["permission_overwrites"]}
        self.assertEqual(over["123"]["deny"], str(ac.VIEW))           # @everyone can't see it
        self.assertTrue(int(over["555"]["allow"]) & ac.VIEW)           # you can
        self.assertTrue(int(over["999"]["allow"]) & ac.HOOKS)          # the bot can post
        self.assertEqual(body["parent_id"], "50")


import add_channels as ac  # noqa: E402


class TestV2193Singles(unittest.TestCase):
    """Singles whose set name says "Booster Box" were kind "Booster box", so they matched the OP-18 item."""

    def test_single_with_box_set_name_is_not_a_box(self):
        import tcg_bot as tb
        for t in ("Franky (Leader) OP18-021 [The Dominance of God Booster Box]",
                  "Nico Robin - OP18-031 - Manga Rare [OP-18 Booster Box]"):
            self.assertFalse(tb.is_box_title(t), t)
            self.assertNotEqual((tb.classify(t, [], 260) or ("",))[0], "Booster box", t)
        for t in ("One Piece Card Game OP-18 Booster Box",
                  "One Piece Card Game - The Dominance of God [OP-18] Booster Box (24 Packs) Pre-Order",
                  "ONE PIECE CARD GAME EB-05 Booster Box"):
            self.assertTrue(tb.is_box_title(t), t)

    def test_list_item_never_matches_a_single(self):
        it = ab.make_item(code="OP-18", max=260)
        single = {"name": "Nico Robin OP18-031 [OP-18 Booster Box]", "kind": "Booster box", "price": 120}
        box = {"name": "One Piece Card Game OP-18 Booster Box", "kind": "Booster box", "price": 230}
        self.assertFalse(ab.item_matches(it, single))
        self.assertTrue(ab.item_matches(it, box))
        words = ab.make_item(match="op-18|op18", max=260)
        self.assertFalse(ab.item_matches(words, {"name": "Loki OP18-119 SEC", "kind": "Single"}))

    def test_deals_channel_is_its_own_private_channel(self):
        calls = []

        def api(token, method, path, body=None, auth=True, url=None):
            calls.append((method, path, body))
            if path == "/users/@me":
                return {"id": "999"}
            if path.endswith("/channels") and method == "GET":
                return [{"id": "60", "type": 0, "name": ac.PRIVATE_NAME}]
            if method == "POST" and path.endswith("/channels"):
                return {"id": "78", **body}
            if path.endswith("/webhooks") and method == "GET":
                return []
            if path.endswith("/webhooks"):
                return {"id": "2", "token": "def"}
            return {}
        old = ac.api
        ac.api = api
        try:
            res = ac.make_private("tok", 123, ["555"], ac.DEALS_NAME, ac.DEALS_KEY)
        finally:
            ac.api = old
        self.assertIn("discord_webhook_deals", res["hooks"])
        self.assertNotIn("discord_webhook_autobuy", res["hooks"])
        body = next(b for m, p, b in calls if m == "POST" and p == "/guilds/123/channels")
        self.assertEqual(body["name"], "🔒・deals")
        self.assertEqual({o["id"]: o for o in body["permission_overwrites"]}["123"]["deny"], str(ac.VIEW))


if __name__ == "__main__":
    unittest.main()
