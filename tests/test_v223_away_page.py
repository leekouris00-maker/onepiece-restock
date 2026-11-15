"""v2.23: the My collection / auto-buy page away from home (a second listener on the PC's Tailscale address) and
a new pairing code without being at the PC (/autobuy phone -> remote_code). A stand-in address (127.0.0.2)
plays the Tailscale address; no Tailscale, no network."""
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import auto_buy as ab  # noqa: E402
import auto_buy_web as web  # noqa: E402
import tcg_bot as tb  # noqa: E402

TS_IP, TS_NAME = "127.0.0.2", "nebula.tail1234.ts.net"
UP = {"installed": True, "running": True, "ip": TS_IP, "name": TS_NAME}
DOWN = {"installed": True, "running": False, "ip": None, "name": None}


class Base(unittest.TestCase):
    settings = {"web_port": 0, "web_away": True}
    ts = UP

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.info = dict(self.ts)
        for p in (mock.patch.object(tb, "CONTROLS_PATH", os.path.join(self.dir, "controls.json")),
                  mock.patch.object(ab, "LEDGER_PATH", os.path.join(self.dir, "autobuy.json")),
                  mock.patch.object(ab, "LIST_PATH", os.path.join(self.dir, "autobuy_list.json")),
                  mock.patch.object(web, "TOKEN_PATH", os.path.join(self.dir, "token.txt")),
                  mock.patch.object(tb, "DRY_RUN", [False]),
                  mock.patch.object(web, "tailscale_info", side_effect=lambda fresh=False: dict(self.info)),
                  mock.patch.dict(web._ts_cache, {"t": 0.0, "info": dict(self.ts)})):
            p.start()
            self.addCleanup(p.stop)
        self.srv = web.start(tb, ab, {"auto_buy": dict(self.settings)})
        self.addCleanup(web.stop)
        self.port = self.srv.server_address[1]
        self.key = web.token()

    def call(self, path, body=None, key=True, host=None, ip="127.0.0.1"):
        req = urllib.request.Request(f"http://{ip}:{self.port}{path}", method="POST" if body is not None else "GET",
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


class Away(Base):
    def test_answers_on_the_tailscale_address_with_the_key(self):
        code, p = self.call("/api/phone", ip=TS_IP, host=f"{TS_NAME}:{self.port}")
        self.assertEqual(code, 200)
        self.assertEqual((p["away"], p["lan"]), (True, False))
        self.assertEqual(p["away_urls"], [f"http://{TS_NAME}:{self.port}", f"http://{TS_IP}:{self.port}"])
        self.assertEqual(self.call("/api/state", ip=TS_IP, host=TS_IP)[0], 200)
        self.assertEqual(self.call("/api/state", ip=TS_IP, host=TS_IP, key=False)[0], 401)       # the key is still needed

    def test_only_its_own_name_is_answered(self):
        for host in ("evil.example", "localhost", "127.0.0.1"):
            self.assertEqual(self.call("/api/phone/code", {}, ip=TS_IP, host=host)[0], 403, host)
        self.assertEqual(self.call("/api/phone/code", {}, host=TS_NAME)[0], 403)      # and the PC's own listener is unchanged
        self.assertEqual(self.call("/api/phone/code", {}, host="localhost")[0], 200)

    def test_a_phone_pairs_over_it(self):
        c = self.call("/api/phone/code", {})[1]["code"]
        code, d = self.call("/api/pair", {"code": c}, key=False, ip=TS_IP, host=TS_NAME)
        self.assertEqual((code, d["key"]), (200, self.key))
        self.assertEqual(self.call("/api/pair", {"code": c}, key=False, ip=TS_IP, host=TS_NAME)[0], 403)   # one use

    def test_follows_tailscale_going_and_coming(self):
        handler = web._away["srv"].RequestHandlerClass
        self.info = dict(DOWN)
        self.assertFalse(web._away_sync(handler, self.port))
        with self.assertRaises(OSError):
            self.call("/api/phone", ip=TS_IP, host=TS_NAME)
        self.assertEqual(self.call("/api/phone")[1]["away_urls"], [])
        self.info = dict(UP)
        self.assertTrue(web._away_sync(handler, self.port))
        self.assertEqual(self.call("/api/phone", ip=TS_IP, host=TS_NAME)[0], 200)

    def test_stop_closes_it(self):
        web.stop()
        self.assertIsNone(web._away["srv"])
        with self.assertRaises(OSError):
            self.call("/api/phone", ip=TS_IP, host=TS_NAME)

    def test_remote_code_for_the_discord_command(self):
        d = web.remote_code({"auto_buy": {"web_port": self.port}})
        self.assertRegex(d["code"], r"^\d{6}$")
        self.assertEqual((d["away"], d["lan"], d["seconds"]), (True, False, web.PAIR_SECONDS))
        self.assertEqual(d["away_urls"][0], f"http://{TS_NAME}:{self.port}")
        self.assertEqual(self.call("/api/pair", {"code": d["code"]}, key=False, ip=TS_IP, host=TS_NAME)[0], 200)

    def test_remote_code_when_the_page_is_not_running(self):
        web.stop()
        with self.assertRaises(OSError):
            web.remote_code({"auto_buy": {"web_port": self.port}}, timeout=2)


class OffByDefault(Base):
    settings = {"web_port": 0}

    def test_no_away_listener(self):
        self.assertIsNone(web._away["srv"])
        with self.assertRaises(OSError):
            self.call("/api/phone", ip=TS_IP, host=TS_NAME)
        p = self.call("/api/phone")[1]
        self.assertEqual((p["away"], p["away_urls"]), (False, []))
        self.assertFalse(web.web_settings({})["away"])
        self.assertTrue(web.web_settings({"auto_buy": {"web_away": True}})["away"])

    def test_switch_is_pc_only_and_keeps_config(self):
        cfg = os.path.join(self.dir, "config.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"auto_buy": {"web_port": 0}, "keep": "me"}, f)
        with mock.patch.object(tb, "CONFIG_PATH", cfg), mock.patch.object(web, "restart_soon", return_value=False):
            self.assertEqual(self.call("/api/phone/away", {"on": True}, key=False)[0], 401)
            code, d = self.call("/api/phone/away", {"on": True})
            self.assertEqual(code, 200)
            self.assertIn("Away access on", d["note"])
            with open(cfg, encoding="utf-8") as f:
                raw = json.load(f)
            self.assertEqual((raw["auto_buy"], raw["keep"]), ({"web_port": 0, "web_away": True}, "me"))
            self.assertTrue(os.path.isfile(cfg + ".bak"))

    def test_switch_refused_from_a_phone(self):
        handler = self.srv.RequestHandlerClass
        with mock.patch.object(handler, "_local", return_value=False):
            code, d = self.call("/api/phone/away", {"on": True})
        self.assertEqual(code, 403)
        self.assertIn("PC itself", d["error"])


class NotConnected(Base):
    ts = DOWN

    def test_on_but_tailscale_down(self):
        self.assertIsNone(web._away["srv"])
        p = self.call("/api/phone")[1]
        self.assertEqual((p["away"], p["away_urls"], p["ts"]), (True, [], {"installed": True, "running": False}))


class TailscaleInfo(unittest.TestCase):
    def info(self, status):
        with mock.patch.object(web, "_ts_status", return_value=status), \
                mock.patch.dict(web._ts_cache, {"t": 0.0, "info": None}), \
                mock.patch("socket.gethostbyname_ex", return_value=("pc", [], ["192.168.1.5"])):
            return web.tailscale_info(fresh=True)

    def test_reads_status(self):
        i = self.info({"BackendState": "Running", "Self": {"TailscaleIPs": ["fd7a::1", "100.101.102.103"],
                                                           "DNSName": "Nebula.tail1234.ts.net."}})
        self.assertEqual(i, {"installed": True, "running": True, "ip": "100.101.102.103", "name": "nebula.tail1234.ts.net"})

    def test_signed_out_or_missing(self):
        self.assertEqual(self.info({"BackendState": "NeedsLogin", "Self": {"TailscaleIPs": ["100.101.102.103"]}}),
                         {"installed": True, "running": False, "ip": None, "name": None})
        self.assertEqual(self.info(None), {"installed": False, "running": False, "ip": None, "name": None})

    def test_odd_names_and_addresses_are_dropped(self):
        i = self.info({"BackendState": "Running", "Self": {"TailscaleIPs": ["8.8.8.8"], "DNSName": "bad name<script>."}})
        self.assertEqual((i["ip"], i["name"]), (None, None))
        self.assertTrue(web._is_ts_ip("100.64.0.1") and web._is_ts_ip("100.127.255.254"))
        self.assertFalse(web._is_ts_ip("100.128.0.1") or web._is_ts_ip("192.168.1.5") or web._is_ts_ip(""))


if __name__ == "__main__":
    unittest.main()
