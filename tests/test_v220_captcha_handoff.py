"""v2.20: the CAPTCHA hand-off. PC copy: a newly paused shop is opened in your own browser (desk mode), and the bot
makes two tries of its own and then waits. Cloud copy: a shop that keeps refusing is left to the PC copy.
Nothing is solved or got round. No network."""
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402
import captcha_watch as cw  # noqa: E402
import netguard as ng  # noqa: E402

CHALLENGE = (b"<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>"
             b"<script src='/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1'></script></body></html>")
H = "www.gumnut.com.au"
URL = f"https://{H}/collections/x/products.json"
T0 = 1_800_000_000


class Tries(unittest.TestCase):
    """captcha_watch by itself."""

    def test_two_tries_then_waits(self):
        st = {}
        self.assertTrue(cw.pause(st, H, "hCaptcha", URL, now=T0, status=403, auto_tries=cw.AUTO_TRIES))
        e = st["captcha"][H]
        self.assertEqual((e["tried"], e["try_at"]), (0, T0 + 900))
        self.assertTrue(cw.is_paused(st, H, now=T0 + 899))
        self.assertFalse(cw.is_paused(st, H, now=T0 + 900))              # first try is due
        cw.pause(st, H, "hCaptcha", URL, now=T0 + 905, status=403, auto_tries=cw.AUTO_TRIES)
        e = st["captcha"][H]
        self.assertEqual((e["tried"], e["try_at"]), (1, T0 + 905 + 7200))
        self.assertTrue(cw.is_paused(st, H, now=T0 + 905 + 7199))
        self.assertFalse(cw.is_paused(st, H, now=T0 + 905 + 7200))       # second try
        cw.pause(st, H, "hCaptcha", URL, now=T0 + 9000, status=403, auto_tries=cw.AUTO_TRIES)
        e = st["captcha"][H]
        self.assertEqual(e["tried"], 2)
        self.assertNotIn("try_at", e)
        self.assertTrue(cw.is_paused(st, H, now=T0 + 30 * 86400))        # no third try: waits for Resume

    def test_resume_starts_the_tries_again(self):
        st = {}
        for t in (0, 1000, 9000):
            cw.pause(st, H, "hCaptcha", URL, now=T0 + t, status=403, auto_tries=cw.AUTO_TRIES)
        cw.resume(st, H)
        cw.pause(st, H, "hCaptcha", URL, now=T0 + 20000, status=403, auto_tries=cw.AUTO_TRIES)
        self.assertEqual(st["captcha"][H]["tried"], 0)

    def test_no_tries_unless_asked(self):
        st = {}
        cw.pause(st, H, "hCaptcha", URL, now=T0, status=403)
        self.assertNotIn("try_at", st["captcha"][H])
        self.assertTrue(cw.is_paused(st, H, now=T0 + 30 * 86400))

    def test_slow_down_pause_is_unchanged_then_gets_tries(self):
        st = {}
        self.assertFalse(cw.pause(st, H, "Cloudflare challenge", URL, now=T0, status=429, auto_tries=cw.AUTO_TRIES))
        self.assertNotIn("try_at", st["captcha"][H])
        self.assertEqual(st["captcha"][H]["until"], T0 + 600)
        cw.pause(st, H, "Cloudflare challenge", URL, now=T0 + cw.STUCK_AFTER + 1, status=429, auto_tries=cw.AUTO_TRIES)
        e = st["captcha"][H]
        self.assertTrue(e["needs_you"])
        self.assertEqual(e["tried"], 0)

    def test_left_to_the_pc_after_three_days(self):
        st = {}
        cw.pause(st, H, "Cloudflare challenge", URL, now=T0, status=403, leave_after=cw.LEAVE_AFTER)
        self.assertNotIn("left", st["captcha"][H])
        self.assertFalse(cw.is_paused(st, H, now=T0 + 86400, hours=24))           # the daily try
        self.assertFalse(cw.pause(st, H, "Cloudflare challenge", URL, now=T0 + 86400, status=403,
                                  leave_after=cw.LEAVE_AFTER, notify_gap=7 * 86400))
        t = T0 + cw.LEAVE_AFTER + 60
        self.assertTrue(cw.pause(st, H, "Cloudflare challenge", URL, now=t, status=403,
                                 leave_after=cw.LEAVE_AFTER, notify_gap=7 * 86400))      # one last notice
        self.assertTrue(st["captcha"][H]["left"])
        self.assertTrue(cw.is_paused(st, H, now=t + 6 * 86400, hours=24))        # no longer daily
        self.assertFalse(cw.is_paused(st, H, now=t + 7 * 86400, hours=24))       # weekly
        for weeks in (1, 2, 30):
            self.assertFalse(cw.pause(st, H, "Cloudflare challenge", URL, now=t + weeks * 7 * 86400, status=403,
                                      leave_after=cw.LEAVE_AFTER, notify_gap=7 * 86400))  # never mentioned again
        self.assertTrue(st["captcha"][H]["left"])

    def test_messages(self):
        e = {"kind": "hCaptcha", "status": 403, "try_at": time.time() + 890}
        m = cw.message("Gumnut", H, e, how=cw.HOW_DISCORD)
        self.assertIn("tries once more by itself in about 15 min", m)
        self.assertIn("doesn't let the bot in", m)
        self.assertNotIn("tries once more", cw.message("Gumnut", H, {"kind": "hCaptcha", "status": 403}))
        left = {"kind": "Cloudflare challenge", "status": 429, "left": True}
        m = cw.message("Gumnut", H, left, cloud=True)
        self.assertIn("leaving it to the PC copy", m)
        self.assertIn("3 days", m)
        d = cw.digest([("A", "a.com", left), ("B", "b.com", {"kind": "x", "status": 429})], cloud=True)
        self.assertIn("(https://a.com/)** (Cloudflare challenge) - now left to the PC copy", d)
        self.assertNotIn("(x) - now left", d)

    def test_settings(self):
        self.assertEqual(cw.settings({})["open_tab"], "desk")
        self.assertEqual(cw.settings({"security": {"captcha": {"open_tab": True}}})["open_tab"], "always")
        self.assertEqual(cw.settings({"security": {"captcha": {"open_tab": False}}})["open_tab"], "never")


class Base(unittest.TestCase):
    cloud = False

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.posts, self.opened, self.controls = [], [], {}
        for p in (mock.patch.object(tb, "HERE", self.dir.name),
                  mock.patch.object(tb, "IN_ACTIONS", self.cloud),
                  mock.patch.object(tb, "IN_CONTAINER", False),
                  mock.patch.object(tb, "read_controls", side_effect=lambda: dict(self.controls)),
                  mock.patch.object(tb, "post_status", side_effect=lambda c, text, color=None: self.posts.append(text))):
            p.start()
            self.addCleanup(p.stop)
        self.reset()
        self.addCleanup(self.reset)

    def reset(self):
        ng.RT.update(state=None, wstate=None, wsig=None, notices=[], tabs=[], watch=False, on=False, violations=[],
                     applied=None)

    def saved(self):
        with open(os.path.join(self.dir.name, ng.WATCH_STATE_NAME), encoding="utf-8") as f:
            return json.load(f)["captcha"]

    def tabs(self, cfg=None):
        return ng.open_tabs(tb, cfg or {}, opener=self.opened.append)


class OnThePC(Base):
    def test_tab_only_in_desk_mode(self):
        ng.apply(tb, {})
        ng.on_response(URL, 403, {}, CHALLENGE)
        self.assertEqual(self.tabs(), [])                        # desk mode off: just the notice
        self.assertEqual(self.opened, [])

    def test_tab_opens_once_front_page(self):
        self.controls["desk_until"] = time.time() + 3600
        ng.apply(tb, {})
        ng.on_response(URL, 403, {}, CHALLENGE)
        self.assertEqual(self.tabs(), [H])
        self.assertEqual(self.opened, [f"https://{H}/"])         # the shop's front page, not the feed address
        self.assertTrue(self.saved()[H]["tab"])
        self.assertEqual(self.tabs(), [])
        with mock.patch.object(cw, "SAME_BURST", -5):           # the bot's own try is challenged again: no second tab
            ng.on_response(URL, 403, {}, CHALLENGE)
        self.assertEqual(self.tabs(), [])
        self.assertEqual(len(self.opened), 1)
        self.assertEqual(self.saved()[H]["tried"], 1)

    def test_open_tab_setting(self):
        c = {"security": {"captcha": {"open_tab": True}}}
        ng.apply(tb, c)
        ng.on_response(URL, 403, {}, CHALLENGE)
        self.assertEqual(self.tabs(c), [H])                      # always, desk mode or not
        self.reset()
        self.controls["desk_until"] = time.time() + 3600
        c = {"security": {"captcha": {"open_tab": False}}}
        ng.apply(tb, c)
        ng.on_response(f"https://b.example/x", 403, {}, CHALLENGE)
        self.assertEqual(self.tabs(c), [])

    def test_few_tabs_per_check_and_not_for_slow_down(self):
        self.controls["desk_until"] = time.time() + 3600
        ng.apply(tb, {})
        for i in range(6):
            ng.on_response(f"https://shop{i}.example/x", 403, {}, CHALLENGE)
        ng.on_response("https://slow.example/x", 429, {"cf-mitigated": "challenge"}, CHALLENGE)
        got = self.tabs()
        self.assertEqual(len(got), ng.TABS_PER_CHECK)
        self.assertNotIn("slow.example", got)

    def test_not_in_dry_run_or_container(self):
        self.controls["desk_until"] = time.time() + 3600
        ng.apply(tb, {})
        ng.on_response(URL, 403, {}, CHALLENGE)
        with mock.patch.object(tb, "IN_CONTAINER", True):
            self.assertEqual(self.tabs(), [])
        ng.RT["tabs"].append(H)
        with mock.patch.object(tb, "DRY_RUN", [True]):
            self.assertEqual(self.tabs(), [])

    def test_flush_opens_the_tab(self):
        self.controls["desk_until"] = time.time() + 3600
        ng.apply(tb, {})
        ng.on_response(URL, 403, {}, CHALLENGE)
        with mock.patch("webbrowser.open", side_effect=lambda url, new=0: self.opened.append(url)):
            ng.flush_notices(tb, {})
        self.assertEqual(self.opened, [f"https://{H}/"])
        self.assertIn("tries once more by itself", self.posts[0])

    def test_own_try_goes_out_and_a_normal_answer_resumes(self):
        ng.apply(tb, {})
        ng.on_response(URL, 403, {}, CHALLENGE)
        with self.assertRaises(ng.Blocked):
            ng.gate(URL)
        real = time.time
        with mock.patch("time.time", side_effect=lambda: real() + 901):
            ng.gate(URL)                                         # the try is let through...
            ng.on_response(URL, 200, {"content-type": "application/json"}, b'{"products": []}')
        self.assertNotIn(H, self.saved())                        # ...and the shop is back, nobody pressed Resume
        ng.gate(URL)

    def test_listed_with_the_next_try(self):
        ng.apply(tb, {})
        ng.on_response(URL, 403, {}, CHALLENGE)
        row = ng.watch_list(tb, {})[0]
        self.assertAlmostEqual(row["try_at"], time.time() + 900, delta=5)
        self.assertFalse(row["left"])


class InTheCloud(Base):
    cloud = True

    def test_no_tabs_no_own_tries(self):
        self.controls["desk_until"] = time.time() + 3600
        ng.apply(tb, {})
        ng.on_response(URL, 403, {}, CHALLENGE)
        self.assertNotIn("try_at", self.saved()[H])
        self.assertEqual(self.tabs(), [])

    def test_left_after_three_days_one_notice(self):
        ng.apply(tb, {})
        ng.on_response(URL, 403, {}, CHALLENGE)
        self.assertEqual(ng.flush_notices(tb, {}), 1)
        real = time.time
        with mock.patch("time.time", side_effect=lambda: real() + cw.LEAVE_AFTER + 5):
            ng.gate(URL)                                         # the daily try
            ng.on_response(URL, 403, {}, CHALLENGE)
            self.assertEqual(ng.flush_notices(tb, {}), 1)
            self.assertTrue(self.saved()[H]["left"])
            with self.assertRaises(ng.Blocked):
                ng.gate(URL)
        self.assertIn("leaving it to the PC copy", self.posts[-1])
        with mock.patch("time.time", side_effect=lambda: real() + cw.LEAVE_AFTER + 2 * 86400):
            with self.assertRaises(ng.Blocked):
                ng.gate(URL)                                     # no longer tried daily
        with mock.patch("time.time", side_effect=lambda: real() + cw.LEAVE_AFTER + 8 * 86400):
            ng.gate(URL)                                         # weekly
            ng.on_response(URL, 403, {}, CHALLENGE)
            self.assertEqual(ng.flush_notices(tb, {}), 0)        # and not mentioned again
        self.assertEqual(len(self.posts), 2)


if __name__ == "__main__":
    unittest.main()
