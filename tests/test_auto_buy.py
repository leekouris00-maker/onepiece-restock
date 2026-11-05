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
        self.assertTrue(ab.budget_ok(yesterday, "x", 240, S, now)[0])     # yesterday's spend doesn't count today

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


class Wiring(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.paths = (tb.CONTROLS_PATH, ab.LEDGER_PATH)
        tb.CONTROLS_PATH = os.path.join(self.dir, "controls.json")
        ab.LEDGER_PATH = os.path.join(self.dir, "autobuy.json")
        self.start = ab.start
        ab.start = lambda _tb: None
        while not ab._q.empty():
            ab._q.get_nowait()
        ab._busy.clear()

    def tearDown(self):
        tb.CONTROLS_PATH, ab.LEDGER_PATH = self.paths
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
        finds = [box(), box(id="list|x", kind="New listing"), box(id="box|y|z", game="pokemon")]
        taken = quiet(ab.offer, tb, {}, finds)
        self.assertEqual([f["id"] for f in taken], ["box|Gumnut|op-13"])
        self.assertIn("🤖 auto-buying", finds[0]["note"])
        self.assertEqual(ab._q.qsize(), 1)
        quiet(ab.offer, tb, {}, [box()])                       # already queued: not twice
        self.assertEqual(ab._q.qsize(), 1)
        tb.atomic_write_json(tb.CONTROLS_PATH, {"desk_until": time.time() + 3600})
        opened = []
        quiet(fl.desk_open, tb, [finds[0], box(id="box|b|c", cart="https://b.test/cart/9:1")], opener=opened.append)
        self.assertEqual(opened, ["https://b.test/cart/9:1"])

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
        self.saved = (tb.CONTROLS_PATH, ab.LEDGER_PATH, ab.SHOTS_DIR, tb.DRY_RUN[0])
        tb.CONTROLS_PATH = os.path.join(self.dir, "controls.json")
        ab.LEDGER_PATH = os.path.join(self.dir, "autobuy.json")
        ab.SHOTS_DIR = os.path.join(self.dir, "shots")

    def tearDown(self):
        tb.CONTROLS_PATH, ab.LEDGER_PATH, ab.SHOTS_DIR, tb.DRY_RUN[0] = self.saved
        shutil.rmtree(self.dir)

    def test_budget_blocks_before_opening_a_browser(self):
        tb.atomic_write_json(tb.CONTROLS_PATH, {"autobuy": {"mode": "live", "per_order": 100}})
        tb.DRY_RUN[0] = True                   # nothing posted to Discord
        opened = []
        b = ab.Buyer(tb, launcher=lambda s: opened.append(1))
        r = quiet(b.handle, {"f": box(), "t": time.time(), "mode": "live"})
        self.assertEqual(r["status"], "skipped")
        self.assertEqual(opened, [])

    def test_stale_and_off_jobs_dropped(self):
        tb.atomic_write_json(tb.CONTROLS_PATH, {"autobuy": {"mode": "live"}})
        tb.DRY_RUN[0] = True
        b = ab.Buyer(tb, launcher=lambda s: self.fail("opened"))
        self.assertIsNone(quiet(b.handle, {"f": box(), "t": time.time() - 600, "mode": "live"}))
        tb.DRY_RUN[0] = False
        tb.atomic_write_json(tb.CONTROLS_PATH, {"autobuy": {"mode": "off"}})
        tb.DRY_RUN[0] = True
        self.assertIsNone(quiet(b.handle, {"f": box(), "t": time.time(), "mode": "live"}))


if __name__ == "__main__":
    unittest.main()
