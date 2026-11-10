"""v2.15: security - event log scrubbing, CAPTCHA pause, network guard (allowed sites, endpoint, verification,
rotation, fail-closed, emergency stop), file checks, the Security page, the container -> PC auto-buy hand-over.
No network."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402
import auto_buy  # noqa: E402
import captcha_watch as cw  # noqa: E402
import fileguard  # noqa: E402
import netguard as ng  # noqa: E402
import security_log as sl  # noqa: E402
import security_panel as sp  # noqa: E402

HOME_IP, VPN_A, VPN_B = "203.0.113.7", "198.51.100.20", "198.51.100.99"
CHALLENGE = (b"<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>"
             b"<script src='/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1'></script></body></html>")


def cfg(**net):
    c = {"sealed": {"max_price": 260, "shopify_collections": [
        {"name": "Gumnut", "url": "https://www.gumnut.com.au/collections/one-piece-card-game/products.json?limit=250"}]},
        "extra_shops": False, "chain_shops": False, "pokemon": False, "alerts": {},
        "security": {"enabled": True, "files": {"enforce": False},
                     "network": dict({"ip_check_url": "https://am.i.mullvad.net/json"}, **net)}}
    return c


PROXY = dict(mode="proxy", endpoints={"melbourne": "http://user:hunter2@vpn:8888", "sydney": "http://vpn2:8888"})


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.ip = {"ip": VPN_A, "mullvad_exit_ip": True}
        self.ip_error = None
        self.posts = []
        self.saved_env = {k: os.environ.get(k) for k in ng.PROXY_VARS + ("NO_PROXY", "no_proxy")}
        for p in (mock.patch.object(tb, "HERE", self.dir.name),
                  mock.patch.object(tb, "CONTROLS_PATH", os.path.join(self.dir.name, "controls.json")),
                  mock.patch.object(tb.HTTP, "_exchange", side_effect=self.exchange),
                  mock.patch.object(tb, "post_status", side_effect=lambda c, text, color=None: self.posts.append(text))):
            p.start()
            self.addCleanup(p.stop)
        ng.RT.update(state=None, applied=None, violations=[], on=False)
        self.addCleanup(self.off)

    def off(self):
        ng.apply(tb, {})                         # guards removed, proxy settings put back
        ng.RT.update(state=None, applied=None, violations=[])
        fileguard.disable()
        for k, v in self.saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def exchange(self, method, url, body=None, headers=None):
        if self.ip_error:
            raise self.ip_error
        return 200, {}, json.dumps(self.ip).encode()

    def events(self):
        return [e["event"] for e in sl.recent(tb, 100)]


class Log(Base):
    def test_secrets_and_addresses_never_reach_the_log(self):
        sl.log(tb, "endpoint_selected", endpoint="http://user:hunter2@vpn:8888",
               hook="https://discord.com/api/webhooks/123456/AbC-dEf_secret", ip=HOME_IP,
               note="token=abc123 password: hunter2", key="wOEI9rqqbDwnN8/Bpp22sVz48T71vJ4fYmFWujulwUU=", local="10.64.222.21")
        raw = open(sl.path(tb)).read()
        for secret in ("hunter2", "AbC-dEf_secret", "abc123", "wOEI9rqqbDwnN8", HOME_IP):
            self.assertNotIn(secret, raw)
        e = sl.recent(tb, 1)[0]
        self.assertEqual(e["ip"], "203.0.x.x")
        self.assertEqual(e["local"], "10.64.222.21")            # private addresses aren't secret
        self.assertIn("***:***@vpn:8888", e["endpoint"])

    def test_log_is_cut_over_when_big(self):
        with mock.patch.object(sl, "MAX_BYTES", 200):
            for i in range(12):
                sl.log(tb, "blocked_host", host=f"x{i}.example")
        self.assertTrue(os.path.exists(sl.path(tb) + ".1"))


class Captcha(unittest.TestCase):
    def test_challenges_are_recognised(self):
        self.assertEqual(cw.detect(403, {"cf-mitigated": "challenge"}, b""), "Cloudflare challenge")
        self.assertEqual(cw.detect(403, {"Content-Type": "text/html"}, CHALLENGE), "Cloudflare challenge")
        self.assertEqual(cw.detect(429, {}, b"<html><body><div class=\"h-captcha\" data-sitekey=x></div></body></html>"), "hCaptcha")
        self.assertEqual(cw.detect(200, {}, b"<html><form action=\"/challenge\" method=post></form></html>"), "Shopify challenge")
        self.assertEqual(cw.detect(403, {}, b"<html><body>Please verify you are human</body></html>"), "human verification")
        self.assertEqual(cw.detect(403, {}, b"<html><script src='https://geo.captcha-delivery.com/captcha/'></script></html>"), "DataDome")

    def test_normal_replies_are_not(self):
        self.assertIsNone(cw.detect(200, {}, b'{"products": [{"title": "recaptcha challenge-platform"}]}'))
        self.assertIsNone(cw.detect(200, {}, b"<html><script src='https://www.google.com/recaptcha/api.js'></script>"
                                             b"<h1>One Piece OP-13</h1></html>"))       # a real page with a newsletter box
        self.assertIsNone(cw.detect(403, {}, b"<html><body>Forbidden</body></html>"))       # a plain refusal isn't a CAPTCHA
        self.assertIsNone(cw.detect(404, {}, b"<html>verify you are human</html>"))
        self.assertIsNone(cw.detect(200, {"Content-Type": "application/xml"}, b"<urlset><loc>x</loc></urlset>"))

    def test_slow_down_challenge_is_a_temporary_pause(self):
        # the real page Shopify shops behind Cloudflare sent on 10 Nov 2026: HTTP 429 + cf-mitigated: challenge
        real = (b"<!DOCTYPE html><html><head><title>Verifying your connection...</title></head><body><noscript>Enable "
                b"JavaScript and cookies to continue</noscript><script>(function(){window._cf_chl_opt = {cFPWv: 'b'};"
                b"var a = document.createElement('script');a.src = '/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1';"
                b"})();</script></body></html>")
        self.assertEqual(cw.detect(429, {"cf-mitigated": "challenge", "content-type": "text/html"}, real), "Cloudflare challenge")
        st, h, t = {}, "shop.test", 100000
        self.assertFalse(cw.pause(st, h, "Cloudflare challenge", "u", now=t, status=429))          # not told
        self.assertFalse(cw.pause(st, h, "Cloudflare challenge", "u", now=t + 2, status=429))      # same burst: counted once
        e = st["captcha"][h]
        self.assertEqual((e["count"], e["until"] - t, e.get("needs_you")), (1, 600, None))
        self.assertTrue(cw.is_paused(st, h, {}, now=t + 599))
        self.assertFalse(cw.is_paused(st, h, {}, now=t + 601))                                     # one try after 10 min
        waits = []
        for i in range(8):                                                                         # still challenged each time
            t = st["captcha"][h]["until"] + 1
            told = cw.pause(st, h, "Cloudflare challenge", "u", now=t, status=429)
            if st["captcha"][h].get("needs_you"):
                break
            waits.append(st["captcha"][h]["until"] - t)
        self.assertEqual(waits, [1200, 2400, 4800, 9600, 14400])  # doubling, capped at 4 h, then past 6 hours in all:
        self.assertTrue(told and st["captcha"][h]["needs_you"])   # ...it waits for you, and you're told
        self.assertTrue(cw.is_paused(st, h, {}, now=t + 10 ** 7))
        self.assertIn("6 hours", cw.message("Shop", h, st["captcha"][h]))
        self.assertFalse(cw.pause(st, h, "Cloudflare challenge", "u", now=t + 3600, status=429))   # stays waiting, no repeat notice
        self.assertTrue(st["captcha"][h]["needs_you"])

    def test_pause_tells_you_once_a_day_and_resume_clears_it(self):
        st = {}
        self.assertTrue(cw.pause(st, "shop.test", "hCaptcha", "https://shop.test/x", now=1000, status=403))
        self.assertTrue(st["captcha"]["shop.test"]["needs_you"])                           # a real CAPTCHA waits for you at once
        self.assertFalse(cw.pause(st, "shop.test", "hCaptcha", "https://shop.test/x", now=2000, status=403))
        self.assertTrue(cw.is_paused(st, "shop.test", {}, now=10 ** 9))                    # forever, by default
        every6 = {"security": {"captcha": {"recheck_hours": 1}}}                           # 1 is raised to 6
        self.assertTrue(cw.is_paused(st, "shop.test", every6, now=2000 + 5 * 3600))
        self.assertFalse(cw.is_paused(st, "shop.test", every6, now=2000 + 6 * 3600 + 1))
        self.assertTrue(cw.resume(st, "shop.test"))
        self.assertFalse(cw.is_paused(st, "shop.test"))


class Settings(unittest.TestCase):
    def test_defaults_are_off_and_rotation_has_a_floor(self):
        self.assertFalse(ng.settings({})["enabled"])
        self.assertFalse(ng.settings({"security": "yes"})["enabled"])
        problems = []
        s = ng.settings(cfg(rotate_minutes=5, **PROXY), problems)
        self.assertEqual(s["rotate_minutes"], 60)
        self.assertTrue(any("too short" in p for p in problems))

    def test_endpoints_from_the_environment_and_bad_ones_skipped(self):
        problems = []
        with mock.patch.dict(os.environ, {"BOT_ENDPOINTS": "melbourne=http://vpn:8888, sydney=env:SYD", "SYD": "http://vpn2:8888",
                                          "BOT_NET_MODE": "proxy", "BOT_SECURITY": "1"}):
            s = ng.settings({"security": {"network": {"endpoints": {"bad": "socks5://x:1", "empty": "env:NOPE"}}}}, problems)
        self.assertTrue(s["enabled"])
        self.assertEqual((s["mode"], sorted(s["endpoints"])), ("proxy", ["melbourne", "sydney"]))
        self.assertEqual(len(problems), 2)


class Guard(Base):
    def test_off_means_untouched(self):
        orig = socket.getaddrinfo
        ng.apply(tb, {"sealed": {}})
        ng.gate("https://anything.example/x")                    # no error
        self.assertIs(socket.getaddrinfo, orig)
        self.assertFalse(os.path.exists(sl.path(tb)))

    def test_only_allowed_sites_and_too_many_strangers_stop_the_bot(self):
        c = cfg()
        c["security"]["allowlist"] = {"max_violations": 3, "extra_hosts": ["extra.example"]}
        ng.apply(tb, c)
        for ok in ("https://www.gumnut.com.au/x", "https://discord.com/api/webhooks/1/x", "https://cdn.discordapp.com/a.png",
                   "https://extra.example/", "http://127.0.0.1:8766/", "https://am.i.mullvad.net/json"):
            ng.gate(ok)
        for i, bad in enumerate(("https://evil.example/a", "https://evil.example/b", "https://other.example/")):
            with self.assertRaises(ng.Blocked):
                ng.gate(bad)
        self.assertIsNone(ng.stopped(tb))                        # two different sites so far
        with self.assertRaises(ng.Blocked):
            ng.gate("https://third.example/")
        self.assertIn("unexpected network activity", ng.stopped(tb)["reason"])
        self.assertTrue(any("Emergency stop" in p for p in self.posts))
        with self.assertRaises(ng.Blocked):                      # now even allowed sites are refused
            ng.gate("https://www.gumnut.com.au/x")
        self.assertEqual(self.events().count("blocked_host"), 3)
        ng.RT["state"] = None                                    # a restart: still stopped
        ng.apply(tb, c)
        self.assertIsNotNone(ng.stopped(tb))
        ng.emergency_resume(tb)
        ng.gate("https://www.gumnut.com.au/x")

    def test_bot_requests_are_skipped_not_counted_as_shop_failures(self):
        ng.apply(tb, cfg())
        tb.HTTP.skip_hosts = set()
        with self.assertRaises(tb.SkipHost):
            tb.HTTP.fetch("https://evil.example/products.json")
        with mock.patch.object(tb, "_fail") as fail:
            self.assertIsNone(tb.fetch_json("https://evil.example/products.json"))
            fail.assert_not_called()

    def test_a_shops_own_redirect_is_allowed_but_shared_platforms_are_not(self):
        c = cfg()
        c["sealed"]["shopify_collections"] += [
            {"name": "Good Games", "url": "https://shop.goodgames.com.au/collections/x/products.json"},
            {"name": "Tiny", "url": "https://tiny-shop.myshopify.com/collections/x/products.json"}]
        ng.apply(tb, c)
        ng.gate("https://www.goodgames.com.au/collections/x")           # shop.goodgames.com.au redirects here
        socket.getaddrinfo                                               # (the socket guard uses the same list)
        self.assertTrue(ng.host_allowed("www.goodgames.com.au", ng.RT["allow"]))
        ng.gate("https://tiny-shop.myshopify.com/x")
        with self.assertRaises(ng.Blocked):
            ng.gate("https://someone-else.myshopify.com/x")
        with self.assertRaises(ng.Blocked):
            ng.gate("https://goodgames.com.au.evil.example/x")
        self.assertEqual(ng.site_of("www.jbhifi.com.au"), "jbhifi.com.au")

    def test_sockets_and_urllib_are_guarded_too(self):
        ng.apply(tb, cfg())
        with self.assertRaises(OSError):
            socket.getaddrinfo("evil.example", 443)
        with self.assertRaises(OSError):
            socket.getaddrinfo("8.8.8.8", 53)                    # a bare public address
        socket.getaddrinfo("localhost", 80)
        with self.assertRaises(urllib.error.URLError):
            urllib.request.urlopen("https://evil.example/", timeout=2)
        self.assertIn("blocked_socket", self.events())
        ng.apply(tb, {})
        self.assertIsNone(ng.RT["orig_getaddrinfo"])

    def test_proxy_endpoint_is_used_verified_and_never_logged(self):
        ng.apply(tb, cfg(**PROXY), now=1000)
        self.assertEqual(os.environ["HTTPS_PROXY"], "http://user:hunter2@vpn:8888")
        snap = ng.snapshot(tb)
        self.assertEqual((snap["network"]["connected"], snap["network"]["endpoint"], snap["network"]["ip"]),
                         (True, "melbourne", VPN_A))
        self.assertNotIn("hunter2", json.dumps(snap))
        self.assertNotIn("vpn:8888", json.dumps(snap))
        self.assertNotIn("hunter2", open(sl.path(tb)).read())
        ng.gate("https://www.gumnut.com.au/x")
        ng.apply(tb, {})
        self.assertEqual(os.environ.get("HTTPS_PROXY"), self.saved_env["HTTPS_PROXY"])

    def test_failed_check_means_disconnected_and_nothing_is_sent(self):
        c = cfg(**PROXY)
        ng.apply(tb, c, now=1000)
        self.ip_error = OSError("proxy down")
        ng.apply(tb, c, now=1000 + 601)                          # the 10-minute verification
        self.assertFalse(ng.snapshot(tb)["network"]["connected"])
        with self.assertRaises(ng.Blocked):
            ng.gate("https://www.gumnut.com.au/x")
        self.assertEqual(os.environ["HTTPS_PROXY"], "http://user:hunter2@vpn:8888")       # never falls back to direct
        self.assertTrue(any("disconnected" in p for p in self.posts))
        ng.apply(tb, c, now=1000 + 620)                          # not asked again within a minute
        self.ip_error = None
        ng.apply(tb, c, now=1000 + 700)
        self.assertTrue(ng.snapshot(tb)["network"]["connected"])
        ng.gate("https://www.gumnut.com.au/x")
        self.assertEqual([e for e in self.events() if e.startswith("vpn_")], ["vpn_reconnected", "vpn_disconnected"])

    def test_home_address_or_a_non_vpn_address_counts_as_disconnected(self):
        self.ip = {"ip": HOME_IP, "mullvad_exit_ip": False}
        ng.apply(tb, cfg(never_ips=[HOME_IP], **PROXY), now=1000)
        self.assertFalse(ng.snapshot(tb)["network"]["connected"])
        self.off()
        ng.apply(tb, cfg(require_vpn_flag=True, **PROXY), now=1000)
        self.assertFalse(ng.snapshot(tb)["network"]["connected"])
        self.assertIn("isn't a VPN address", ng.snapshot(tb)["network"]["reason"])

    def test_rotation_is_a_timer_only(self):
        c = cfg(rotate_minutes=60, **PROXY)
        ng.apply(tb, c, now=1000)
        ng.on_response("https://www.gumnut.com.au/x", 403, {}, CHALLENGE)              # a shop challenges the bot
        ng.apply(tb, c, now=1000 + 59 * 60)
        self.assertEqual(ng.snapshot(tb)["network"]["endpoint"], "melbourne")          # a block doesn't bring it forward
        self.ip = {"ip": VPN_B, "mullvad_exit_ip": True}
        ng.apply(tb, c, now=1000 + 60 * 60 + 1)
        snap = ng.snapshot(tb)
        self.assertEqual((snap["network"]["endpoint"], snap["network"]["ip"]), ("sydney", VPN_B))
        self.assertEqual(os.environ["HTTPS_PROXY"], "http://vpn2:8888")
        self.assertIn("ip_rotated", self.events())
        with self.assertRaises(ng.Blocked):                      # the CAPTCHA pause holds on the new address
            ng.gate("https://www.gumnut.com.au/x")
        ng.apply(tb, c, now=1000 + 120 * 60 + 2)                 # same address after a rotation is reported
        self.assertIn("rotation_no_change", self.events())

    def test_rotation_interval_from_the_page_has_the_same_floor(self):
        ng.apply(tb, cfg(**PROXY), now=1000)
        with self.assertRaises(ValueError):
            ng.set_rotation(tb, 5)
        ng.set_rotation(tb, 120)
        self.assertEqual(ng.snapshot(tb)["network"]["rotate_minutes"], 120)
        with self.assertRaises(ValueError):
            ng.select_endpoint(tb, "nowhere")
        ng.select_endpoint(tb, "sydney")
        ng.apply(tb, cfg(**PROXY), now=2000)
        self.assertEqual(ng.snapshot(tb)["network"]["endpoint"], "sydney")

    def test_captcha_pauses_the_shop_until_you_resume(self):
        c = cfg()
        ng.apply(tb, c)
        self.assertTrue(ng.on_response("https://www.gumnut.com.au/collections/x", 403, {}, CHALLENGE))
        self.assertEqual(len([p for p in self.posts if "human verification" in p]), 1)
        self.assertIn("Gumnut", self.posts[-1])
        with self.assertRaises(ng.Blocked):
            ng.gate("https://www.gumnut.com.au/y")
        ng.gate("https://discord.com/api/x")                     # other sites carry on
        self.assertEqual(ng.snapshot(tb)["captcha"]["paused"][0]["host"], "www.gumnut.com.au")
        ng.resume_captcha(tb, "www.gumnut.com.au")
        ng.gate("https://www.gumnut.com.au/y")
        self.assertFalse(ng.on_response("https://www.gumnut.com.au/y", 200, {}, b'{"products": []}'))
        self.assertEqual(self.events()[:2], ["captcha_resumed", "captcha_detected"])

    def test_fetch_stops_at_a_challenge(self):
        ng.apply(tb, cfg())
        tb.HTTP.skip_hosts = set()
        with mock.patch.object(tb.HTTP, "_get_following", return_value=(403, {"cf-mitigated": "challenge"}, b"")), \
                mock.patch.object(tb.HTTP, "allowed", return_value=True):
            with self.assertRaises(tb.SkipHost):
                tb.HTTP.fetch("https://www.gumnut.com.au/collections/z/products.json", memo=False)
        self.assertIn("www.gumnut.com.au", cw.paused(ng.load_state(tb)))


class Files(Base):
    def test_paths(self):
        root = fileguard._norm(self.dir.name)
        self.assertTrue(fileguard.inside(os.path.join(self.dir.name, "a", "b.json"), [root]))
        self.assertFalse(fileguard.inside(self.dir.name + "x", [root]))
        self.assertFalse(fileguard.inside(os.path.join(self.dir.name, "..", "etc"), [root]))
        self.assertTrue(fileguard.is_write("w", 0) and fileguard.is_write("a+", 0) and fileguard.is_write(None, os.O_CREAT))
        self.assertFalse(fileguard.is_write("rb", os.O_RDONLY))

    def test_writes_outside_the_data_folder_are_refused_and_logged(self):
        other = tempfile.mkdtemp(dir=os.path.dirname(os.path.abspath(__file__)))     # not under the temp folder
        self.addCleanup(lambda: (fileguard.disable(), os.path.isdir(other) and os.rmdir(other)))
        c = cfg()
        c["security"]["files"] = {"enforce": True}
        ng.apply(tb, c)
        with open(os.path.join(self.dir.name, "ok.json"), "w") as f:                 # the data folder: fine
            f.write("{}")
        open(__file__).close()                                                       # reading anywhere: fine
        with self.assertRaises(PermissionError):
            open(os.path.join(other, "nope.txt"), "w")
        with self.assertRaises(PermissionError):
            os.mkdir(os.path.join(other, "sub"))
        self.assertFalse(os.listdir(other))
        self.assertIn("blocked_file", self.events())
        self.assertGreaterEqual(ng.snapshot(tb)["monitoring"]["blocked_files"], 2)
        ng.apply(tb, {})                                                             # security off: allowed again
        os.mkdir(os.path.join(other, "sub"))
        os.rmdir(os.path.join(other, "sub"))

    def test_programs_can_be_refused_in_the_container(self):
        fileguard.enable(self.dir.name, block_processes=True)
        with self.assertRaises(PermissionError):
            subprocess.Popen([sys.executable, "-c", "pass"])
        fileguard.disable()


class Page(Base):
    def test_controls(self):
        c = cfg(**PROXY)
        with mock.patch.object(tb, "load_config", return_value=c):
            ng.apply(tb, c, now=1000)
            self.assertIn("Stopped", sp.handle_post(tb, "/api/security/stop", {}))
            self.assertEqual(sp.state(tb)["stopped"]["by"], "you")
            self.assertIn("Resumed", sp.handle_post(tb, "/api/security/resume", {}))
            sp.handle_post(tb, "/api/security/endpoint", {"name": "sydney"})
            sp.handle_post(tb, "/api/security/rotation", {"minutes": 90})
            with self.assertRaises(ValueError):
                sp.handle_post(tb, "/api/security/rotation", {"minutes": 1})
            with self.assertRaises(ValueError):
                sp.handle_post(tb, "/api/security/environment", {"image": "windows"})
            sp.handle_post(tb, "/api/security/environment", {"image": "alpine"})
            st = sp.state(tb)
            self.assertEqual((st["environment"]["next_image"], st["network"]["rotate_minutes"]), ("alpine", 90))
            with self.assertRaises(LookupError):
                sp.handle_post(tb, "/api/security/nope", {})

    def test_page_needs_the_key_and_localhost(self):
        c = cfg()
        c["security"]["panel_port"] = 0
        with mock.patch.object(tb, "load_config", return_value=c), mock.patch.object(sp, "port", return_value=18766):
            self.assertIsNone(sp.start(tb, c) if sp.port.return_value == 0 else None)
            srv = sp.start(tb, c)
            self.addCleanup(sp.stop)
            base = f"http://127.0.0.1:{srv.server_address[1]}"
            key = sp.token(tb)

            def get(path, headers):
                req = urllib.request.Request(base + path, headers=headers)
                try:
                    with urllib.request.urlopen(req, timeout=5) as r:
                        return r.status, r.read()
                except urllib.error.HTTPError as e:
                    return e.code, e.read()
            self.assertEqual(get("/api/security", {})[0], 401)
            self.assertEqual(get("/api/security", {"X-Token": "wrong"})[0], 401)
            self.assertEqual(get("/api/security", {"X-Token": key, "Host": "evil.example"})[0], 403)
            code, body = get("/api/security", {"X-Token": key})
            self.assertEqual(code, 200)
            self.assertIn("network", json.loads(body))
            self.assertEqual(get("/", {})[0], 200)
            req = urllib.request.Request(base + "/api/security/stop", data=b"{}", method="POST")
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(req, timeout=5)
            self.assertIsNone(ng.stopped(tb))


class HandOver(Base):
    def test_container_hands_over_and_the_pc_checks_what_it_gets(self):
        path = os.path.join(self.dir.name, "offers.jsonl")
        good = {"id": "box|Gumnut|op-13", "kind": "Booster box", "name": "OP-13 Booster Box", "shop": "Gumnut", "price": 199.0,
                "url": "https://www.gumnut.com.au/products/op-13", "cart": "https://www.gumnut.com.au/cart/1:1", "extra": "dropped"}
        bad = [dict(good, id="x1", cart="https://evil.example/cart/1:1"), dict(good, id="x2", cart="http://www.gumnut.com.au/cart/1:1"),
               dict(good, id="x3", price="lots"), dict(good, id="x4", cart=""), {"id": 5}]
        with mock.patch.object(auto_buy, "OFFERS_PATH", path):
            auto_buy.write_offers(tb, [good] + bad)
            with open(path, "a") as f:
                f.write("not json\n" + json.dumps({"t": 1, "finds": [dict(good, id="old")]}) + "\n")
            finds, pos = auto_buy.read_offers(0, {"www.gumnut.com.au"})
            self.assertEqual([f["id"] for f in finds], ["box|Gumnut|op-13"])
            self.assertNotIn("extra", finds[0])
            self.assertEqual(auto_buy.read_offers(pos, {"www.gumnut.com.au"}), ([], pos))     # nothing twice
            self.assertEqual(auto_buy.read_offers(0, set())[0], [])                           # a shop the PC doesn't know

    def test_in_the_container_offer_writes_instead_of_buying(self):
        f = {"id": "box|Gumnut|op-13", "kind": "Booster box", "name": "OP-13 Booster Box", "shop": "Gumnut", "price": 199.0,
             "url": "https://www.gumnut.com.au/products/op-13", "cart": "https://www.gumnut.com.au/cart/1:1"}
        path = os.path.join(self.dir.name, "offers.jsonl")
        with mock.patch.object(auto_buy, "OFFERS_PATH", path), mock.patch.object(tb, "IN_CONTAINER", True, create=True), \
                mock.patch.object(auto_buy, "settings", return_value={"mode": "live", "what": ["boxes"]}), \
                mock.patch.object(auto_buy, "eligible", return_value=(True, "")), \
                mock.patch.object(auto_buy, "start") as start:
            taken = auto_buy.offer(tb, {}, [f])
        self.assertEqual([t["id"] for t in taken], [f["id"]])
        start.assert_not_called()                                 # no browser in the container
        self.assertEqual(auto_buy._q.qsize(), 0)
        self.assertEqual(json.loads(open(path).read())["finds"][0]["cart"], f["cart"])


class DataFolder(unittest.TestCase):
    def test_bot_data_dir_moves_everything_the_bot_writes(self):
        with tempfile.TemporaryDirectory() as d:
            code = ("import tcg_bot as tb, auto_buy, link_watch, chain_shops, netguard, security_log;"
                    "print(tb.HERE == r'%s', tb.CODE_DIR != tb.HERE, tb.IN_CONTAINER, auto_buy.PROFILE_DIR.startswith(tb.CODE_DIR),"
                    " link_watch.WATCH_PATH.startswith(tb.HERE), netguard.state_path(tb).startswith(tb.HERE))" % d)
            out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                                 cwd=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."),
                                 env=dict(os.environ, BOT_DATA_DIR=d, BOT_CONTAINER="1"))
            self.assertEqual(out.stdout.strip(), "True True True True True True", out.stderr[-400:])


if __name__ == "__main__":
    unittest.main()
