"""Tests for auto_buy_web.py (v2.11.2): the auto-buy page on the PC and the shared controls behind it
(also used by /autobuy panel). Local server on a random port, temp files, no shops, no Discord.

Run:  python -m unittest discover -s tests
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import auto_buy as ab  # noqa: E402
import auto_buy_web as web  # noqa: E402
import tcg_bot as tb  # noqa: E402


class Page(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.saved = (tb.CONTROLS_PATH, ab.LEDGER_PATH, ab.LIST_PATH, ab.SHOTS_DIR, web.TOKEN_PATH, tb.DRY_RUN[0])
        tb.CONTROLS_PATH = os.path.join(self.dir, "controls.json")
        ab.LEDGER_PATH = os.path.join(self.dir, "autobuy.json")
        ab.LIST_PATH = os.path.join(self.dir, "autobuy_list.json")
        ab.SHOTS_DIR = os.path.join(self.dir, "shots")
        web.TOKEN_PATH = os.path.join(self.dir, "token.txt")
        tb.DRY_RUN[0] = False
        os.makedirs(ab.SHOTS_DIR)
        with open(os.path.join(ab.SHOTS_DIR, "20261105-190000-test.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\nfake")
        self.srv = web.start(tb, ab, {"auto_buy": {"web_port": 0}})
        self.port = self.srv.server_address[1]
        self.key = web.token()

    def tearDown(self):
        web.stop()
        (tb.CONTROLS_PATH, ab.LEDGER_PATH, ab.LIST_PATH, ab.SHOTS_DIR, web.TOKEN_PATH, tb.DRY_RUN[0]) = self.saved
        shutil.rmtree(self.dir)

    def call(self, path, body=None, key=True, host=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None)
        req.add_header("Content-Type", "application/json")
        if key:
            req.add_header("X-Token", self.key)
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_page_loads_without_key_but_data_needs_it(self):
        code, html = self.call("/", key=False)
        self.assertEqual(code, 200)
        self.assertIn(b"Auto-buy", html)
        self.assertNotIn(self.key.encode(), html)
        self.assertEqual(self.call("/api/state", key=False)[0], 401)
        self.assertEqual(self.call("/api/mode", {"mode": "live"}, key=False)[0], 401)
        self.assertEqual(ab.settings(tb, {})["mode"], "off")

    def test_phone_pairing(self):
        # v2.11.5: the PC page makes a 6-digit code; a phone swaps it (once) for the key
        self.assertEqual(self.call("/api/phone/code", {}, key=False)[0], 401)
        self.assertEqual(self.call("/api/pair", {"code": "123456"}, key=False)[0], 403)   # nothing waiting
        code, p = self.call("/api/phone")
        self.assertEqual((code, p["lan"], p["local"]), (200, False, True))
        c = self.call("/api/phone/code", {})[1]["code"]
        self.assertRegex(c, r"^\d{6}$")
        wrong = "000000" if c != "000000" else "111111"
        self.assertEqual(self.call("/api/pair", {"code": wrong}, key=False)[0], 403)
        code, d = self.call("/api/pair", {"code": c[:3] + " " + c[3:]}, key=False)
        self.assertEqual((code, d["key"]), (200, self.key))
        self.assertEqual(self.call("/api/pair", {"code": c}, key=False)[0], 403)          # one use only
        # too many wrong guesses kill the code
        c = self.call("/api/phone/code", {})[1]["code"]
        for _ in range(web.PAIR_TRIES):
            self.call("/api/pair", {"code": wrong if wrong != c else "222222"}, key=False)
        self.assertEqual(self.call("/api/pair", {"code": c}, key=False)[0], 403)

    def test_home_screen_bits(self):
        code, m = self.call("/manifest.webmanifest", key=False)
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(m)["start_url"], "/#collection")
        for path in ("/icon-192.png", "/icon-512.png", "/apple-touch-icon.png"):
            code, png = self.call(path, key=False)
            self.assertEqual(code, 200)
            self.assertTrue(png.startswith(b"\x89PNG"))
        html = self.call("/", key=False)[1]
        self.assertIn(b'rel="manifest"', html)
        self.assertIn(b"apple-mobile-web-app-capable", html)

    def test_phone_access_switch(self):
        cfg = os.path.join(self.dir, "config.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"auto_buy": {"web_port": 0}, "keep": "me"}, f)
        saved, saved_restart = tb.CONFIG_PATH, web.restart_soon
        tb.CONFIG_PATH, web.restart_soon = cfg, lambda *a, **k: False
        try:
            code, d = self.call("/api/phone/lan", {"on": True})
            self.assertEqual(code, 200)
            self.assertIn("restart_bot.bat", d["note"])
            with open(cfg, encoding="utf-8") as f:
                raw = json.load(f)
            self.assertEqual((raw["auto_buy"], raw["keep"]), ({"web_port": 0, "web_lan": True}, "me"))
            self.assertTrue(os.path.isfile(cfg + ".bak"))
            self.assertEqual(self.call("/api/phone/lan", {"on": True}, key=False)[0], 401)
        finally:
            tb.CONFIG_PATH, web.restart_soon = saved, saved_restart

    def test_lan_addresses_are_private(self):
        for ip in web.lan_addresses():
            self.assertRegex(ip, r"^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.)")

    def test_only_localhost_names(self):
        self.assertEqual(self.call("/api/state", host="evil.example:8765")[0], 403)
        self.assertEqual(self.call("/api/mode", {"mode": "live"}, host="evil.example")[0], 403)
        self.assertEqual(self.call("/api/state", host=f"localhost:{self.port}")[0], 200)

    def test_state_and_controls(self):
        code, st = self.call("/api/state")
        self.assertEqual((code, st["mode"]), (200, "off"))
        self.assertEqual([it["code"] for it in st["items"]][:2], ["OP-14", "OP-15"])
        self.assertEqual(st["shots"], ["20261105-190000-test.png"])
        code, r = self.call("/api/mode", {"mode": "test", "hours": 2})
        self.assertEqual((code, r["state"]["mode"]), (200, "test"))
        self.assertAlmostEqual(r["state"]["until"], time.time() + 7200, delta=60)
        self.assertEqual(self.call("/api/mode", {"mode": "panic"})[0], 400)
        code, r = self.call("/api/limits", {"per_order": "280", "per_day": "", "per_week": 450, "per_month": 900})
        self.assertEqual(r["state"]["limits"], {"per_order": 280, "per_day": 300, "per_week": 450, "per_month": 900})
        self.assertEqual(self.call("/api/limits", {"per_week": "lots"})[0], 400)

    def test_items(self):
        code, r = self.call("/api/item", {"code": "prb2", "max": "300", "qty": 2})
        self.assertEqual(code, 200)
        prb = next(it for it in r["state"]["items"] if it["id"] == "prb-02")
        self.assertEqual((prb["max"], prb["qty"], prb["name"]), (300.0, 2, "PRB-02 booster box"))
        self.assertEqual(self.call("/api/item", {"code": "OP15 box", "max": 1})[0], 400)
        self.assertEqual(self.call("/api/item", {"code": "OP-15", "max": 0})[0], 400)
        r = self.call("/api/item/edit", {"id": "op-15", "on": False, "max": 230})[1]
        it = next(x for x in r["state"]["items"] if x["id"] == "op-15")
        self.assertEqual((it["on"], it["max"]), (False, 230.0))
        ab.count_bought(tb, "op-15", 1)
        r = self.call("/api/item/edit", {"id": "op-15", "reset": True})[1]
        self.assertEqual(next(x for x in r["state"]["items"] if x["id"] == "op-15")["bought"], 0)
        r = self.call("/api/item/edit", {"id": "op-15", "remove": True})[1]
        self.assertNotIn("op-15", [x["id"] for x in r["state"]["items"]])
        self.assertEqual(self.call("/api/item/edit", {"id": "op-15", "on": True})[0], 400)

    def test_try_and_screenshots(self):
        self.assertEqual(self.call("/api/try", {"url": "javascript:alert(1)"})[0], 400)
        self.assertEqual(self.call("/api/try", {"url": "https://shop.test/products/op-15-box"})[0], 200)
        self.assertEqual(tb.read_controls()["autobuy"]["try"], "https://shop.test/products/op-15-box")
        code, raw = self.call(f"/shot/20261105-190000-test.png?t={self.key}", key=False)
        self.assertEqual((code, raw[:4]), (200, b"\x89PNG"))
        self.assertEqual(self.call("/shot/20261105-190000-test.png", key=False)[0], 404)
        self.assertEqual(self.call(f"/shot/..%2Fcontrols.json?t={self.key}", key=False)[0], 404)


if __name__ == "__main__":
    unittest.main()
