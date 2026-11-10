"""v2.16: CAPTCHA detection runs by itself, with the rest of security switched off (PC copy and cloud copy):
pause, one notice per check, Resume from Discord, the cloud copy's once-a-day try, and nothing is ever solved.
No network."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402
import captcha_watch as cw  # noqa: E402
import netguard as ng  # noqa: E402

CHALLENGE = (b"<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>"
             b"<script src='/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1'></script></body></html>")
GUMNUT, GG = "www.gumnut.com.au", "www.goodgames.com.au"


def cfg(**security):
    c = {"sealed": {"max_price": 260, "shopify_collections": [
        {"name": "Gumnut", "url": f"https://{GUMNUT}/collections/one-piece-card-game/products.json?limit=250"},
        {"name": "Good Games", "url": f"https://{GG}/collections/one-piece/products.json?limit=250"}]},
        "extra_shops": False, "chain_shops": False, "pokemon": False, "alerts": {}}
    if security:
        c["security"] = security
    return c


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.posts = []
        for p in (mock.patch.object(tb, "HERE", self.dir.name),
                  mock.patch.object(tb, "IN_ACTIONS", False),
                  mock.patch.object(tb, "post_status", side_effect=lambda c, text, color=None: self.posts.append(text))):
            p.start()
            self.addCleanup(p.stop)
        self.reset()
        self.addCleanup(self.reset)

    def reset(self):
        ng.RT.update(state=None, wstate=None, wsig=None, notices=[], watch=False, on=False, violations=[], applied=None)

    def saved(self):
        return json.load(open(os.path.join(self.dir.name, ng.WATCH_STATE_NAME)))


class Alone(Base):
    def test_on_by_default_with_security_off(self):
        s = ng.apply(tb, cfg())
        self.assertFalse(s["enabled"])
        self.assertFalse(ng.RT["on"])
        self.assertTrue(ng.RT["watch"])
        self.assertTrue(ng.snapshot(tb)["captcha"]["alone"])
        self.assertIsNone(ng.RT["orig_getaddrinfo"])             # none of the security guards were installed
        ng.gate("https://anything.example/x")                    # no allowed-sites list either

    def test_can_be_switched_off(self):
        ng.apply(tb, cfg(captcha={"enabled": False}))
        self.assertFalse(ng.RT["watch"])
        self.assertFalse(ng.on_response(f"https://{GUMNUT}/x", 403, {}, CHALLENGE))
        ng.gate(f"https://{GUMNUT}/x")
        self.assertFalse(os.path.exists(os.path.join(self.dir.name, ng.WATCH_STATE_NAME)))

    def test_challenge_pauses_the_shop_and_only_that_shop(self):
        c = cfg()
        ng.apply(tb, c)
        self.assertTrue(ng.on_response(f"https://{GUMNUT}/collections/x", 403, {}, CHALLENGE))
        with self.assertRaises(ng.Blocked):
            ng.gate(f"https://{GUMNUT}/y")
        ng.gate(f"https://{GG}/y")
        ng.gate("https://discord.com/api/webhooks/1/x")
        self.assertTrue(self.saved()["captcha"][GUMNUT]["needs_you"])
        self.assertFalse(os.path.exists(os.path.join(self.dir.name, ng.STATE_NAME)))   # the security file isn't touched
        self.assertEqual(self.posts, [])                         # nothing yet: one notice at the end of the check
        self.assertEqual(ng.flush_notices(tb, c), 1)
        self.assertEqual(len(self.posts), 1)
        self.assertIn("Gumnut", self.posts[0])
        self.assertIn("/captcha resume:Gumnut", self.posts[0])
        self.assertIn("won't try to get round it", self.posts[0])
        self.assertEqual(ng.flush_notices(tb, c), 0)             # said once
        self.assertEqual(len(self.posts), 1)

    def test_several_shops_get_one_notice_between_them(self):
        c = cfg()
        ng.apply(tb, c)
        for host in (GUMNUT, GG, "unlisted.example"):
            ng.on_response(f"https://{host}/x", 403, {"cf-mitigated": "challenge"}, b"")
            ng.on_response(f"https://{host}/y", 403, {"cf-mitigated": "challenge"}, b"")       # parallel replies: once
        self.assertEqual(ng.flush_notices(tb, c), 3)
        self.assertEqual(len(self.posts), 1)
        for word in ("3 shops", "Gumnut", "Good Games", "unlisted.example", "resume:all"):
            self.assertIn(word, self.posts[0])

    def test_fetch_stops_at_a_challenge_and_leaves_the_shop_alone(self):
        ng.apply(tb, cfg())
        tb.HTTP.skip_hosts = set()
        url = f"https://{GUMNUT}/collections/z/products.json"
        with mock.patch.object(tb.HTTP, "_get_following", return_value=(403, {"cf-mitigated": "challenge"}, b"")) as get, \
                mock.patch.object(tb.HTTP, "allowed", return_value=True):
            with self.assertRaises(tb.SkipHost):
                tb.HTTP.fetch(url, memo=False)
            with self.assertRaises(tb.SkipHost):
                tb.HTTP.fetch(url + "?page=2", memo=False)
            self.assertEqual(get.call_count, 1)                  # the second one never left the PC

    def test_slow_down_challenge_is_temporary_and_quiet(self):
        c = cfg()
        ng.apply(tb, c)
        self.assertTrue(ng.on_response(f"https://{GUMNUT}/x", 429, {"cf-mitigated": "challenge"}, CHALLENGE))
        e = self.saved()["captcha"][GUMNUT]
        self.assertFalse(e.get("needs_you"))
        self.assertEqual(ng.flush_notices(tb, c), 0)
        with self.assertRaises(ng.Blocked):
            ng.gate(f"https://{GUMNUT}/y")
        with mock.patch.object(cw.time, "time", return_value=e["until"] + 1):
            ng.gate(f"https://{GUMNUT}/y")                       # one try after the pause
        self.assertFalse(ng.on_response(f"https://{GUMNUT}/y", 200, {}, b'{"products": []}'))
        self.assertEqual(ng.watch_list(tb, c), [])               # it answered normally: pause cleared by itself

    def test_resume_by_name_and_all(self):
        c = cfg()
        ng.apply(tb, c)
        for host in (GUMNUT, GG):
            ng.on_response(f"https://{host}/x", 403, {}, CHALLENGE)
        self.assertEqual([r["name"] for r in ng.watch_list(tb, c)], ["Gumnut", "Good Games"])
        self.assertEqual(ng.resume_matching(tb, "nothing like it", c), [])
        self.assertEqual(ng.resume_matching(tb, "gumnut", c), ["Gumnut"])
        ng.gate(f"https://{GUMNUT}/y")
        with self.assertRaises(ng.Blocked):
            ng.gate(f"https://{GG}/y")
        self.assertEqual(ng.resume_matching(tb, "ALL", c), ["Good Games"])
        self.assertEqual(self.saved().get("captcha"), {})
        self.assertTrue(ng.on_response(f"https://{GUMNUT}/y", 403, {}, CHALLENGE))     # challenged again: paused again
        with self.assertRaises(ng.Blocked):
            ng.gate(f"https://{GUMNUT}/z")

    def test_resume_from_the_other_program_is_picked_up(self):
        # the commands bot (/captcha resume) is a separate program: it changes the file, the restock bot re-reads it
        c = cfg()
        ng.apply(tb, c)
        ng.on_response(f"https://{GUMNUT}/x", 403, {}, CHALLENGE)
        path = os.path.join(self.dir.name, ng.WATCH_STATE_NAME)
        st = self.saved()
        st["captcha"].pop(GUMNUT)
        with open(path, "w") as f:
            json.dump(st, f)
        os.utime(path, ns=(1, 1))                                # a different time stamp, whatever the clock's resolution
        ng.gate(f"https://{GUMNUT}/y")

    def test_still_challenged_is_repeated_weekly_not_daily(self):
        st = {}
        self.assertTrue(cw.pause(st, "s.test", "hCaptcha", "u", now=1000, status=403, notify_gap=ng.WATCH_REMIND))
        self.assertFalse(cw.pause(st, "s.test", "hCaptcha", "u", now=1000 + 2 * 86400, status=403, notify_gap=ng.WATCH_REMIND))
        self.assertTrue(cw.pause(st, "s.test", "hCaptcha", "u", now=1000 + 7 * 86400 + 1, status=403, notify_gap=ng.WATCH_REMIND))

    def test_pauses_survive_switching_security_on_and_off(self):
        ng.apply(tb, cfg())
        ng.on_response(f"https://{GUMNUT}/x", 403, {}, CHALLENGE)
        on = cfg(enabled=True, files={"enforce": False}, network={"mode": "direct", "verify_minutes": 10 ** 6})
        with mock.patch.object(ng, "verify"):
            ng.apply(tb, on)
        try:
            self.assertIn(GUMNUT, cw.paused(ng.load_state(tb)))
            with self.assertRaises(ng.Blocked):
                ng.gate(f"https://{GUMNUT}/y")
            ng.on_response(f"https://{GG}/x", 403, {}, CHALLENGE)
        finally:
            ng.apply(tb, cfg())
        self.assertEqual({r["host"] for r in ng.watch_list(tb, cfg())}, {GUMNUT, GG})

    def test_nothing_in_the_bot_solves_or_skips_a_challenge(self):
        here = os.path.dirname(os.path.abspath(ng.__file__))
        for name in ("captcha_watch.py", "netguard.py"):
            src = open(os.path.join(here, name), encoding="utf-8").read().lower()
            for word in ("capsolver", "2captcha", "anticaptcha", "anti-captcha", "cf_clearance", "g-recaptcha-response\": ",
                         "playwright", "selenium"):
                self.assertNotIn(word, src, f"{name} mentions {word}")


class Cloud(Base):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(tb, "IN_ACTIONS", True)
        p.start()
        self.addCleanup(p.stop)

    def test_cloud_copy_tries_once_a_day_and_says_why(self):
        c = cfg()
        s = ng.apply(tb, c)
        self.assertEqual(s["captcha"]["recheck_hours"], 24)
        for host in (GUMNUT, GG):
            ng.on_response(f"https://{host}/x", 403, {}, CHALLENGE)
        ng.flush_notices(tb, c)
        self.assertEqual(len(self.posts), 1)
        self.assertIn("cloud copy", self.posts[0])
        self.assertNotIn("/captcha", self.posts[0])              # nobody can press Resume for the cloud copy
        since = self.saved()["captcha"][GUMNUT]["since"]
        with mock.patch.object(cw.time, "time", return_value=since + 23 * 3600):
            with self.assertRaises(ng.Blocked):
                ng.gate(f"https://{GUMNUT}/y")
        with mock.patch.object(cw.time, "time", return_value=since + 24 * 3600 + 1):
            ng.gate(f"https://{GUMNUT}/y")

    def test_a_fresh_process_keeps_the_pause(self):
        # each cloud check is a new run of the program: the pause comes back from captcha_state.json
        c = cfg()
        ng.apply(tb, c)
        ng.on_response(f"https://{GUMNUT}/x", 403, {}, CHALLENGE)
        self.reset()
        ng.apply(tb, c)
        with self.assertRaises(ng.Blocked):
            ng.gate(f"https://{GUMNUT}/y")
        self.assertEqual(ng.flush_notices(tb, c), 0)             # and it isn't announced a second time

    def test_workflow_saves_the_pause_file(self):
        here = os.path.dirname(os.path.abspath(ng.__file__))
        yml = open(os.path.join(here, ".github", "workflows", "main.yml"), encoding="utf-8").read()
        self.assertEqual(yml.count("captcha_state.json"), 2)
        ignored = open(os.path.join(here, ".gitignore"), encoding="utf-8").read().split()
        self.assertNotIn("captcha_state.json", ignored)


class DiscordCommand(Base):
    def setUp(self):
        super().setUp()
        try:
            import commands_bot
        except (Exception, SystemExit) as e:  # noqa: BLE001
            self.skipTest(f"discord.py isn't installed here ({e})")
        self.cb = commands_bot

    def test_list_and_resume(self):
        c = cfg()
        ng.apply(tb, c)
        self.assertIn("No shop is asking", self.cb.build_captcha(c))
        ng.on_response(f"https://{GUMNUT}/x", 403, {}, CHALLENGE)
        ng.on_response(f"https://{GG}/x", 429, {"cf-mitigated": "challenge"}, CHALLENGE)
        text = self.cb.build_captcha(c)
        self.assertIn("2 shop(s) paused", text)
        self.assertIn("/captcha resume:Gumnut", text)
        self.assertIn("tries again by itself", text)
        text = self.cb.build_captcha(c, "gumnut")
        self.assertIn("Trying again on the next check: **Gumnut**", text)
        self.assertIn("1 shop(s) paused", text)
        self.assertIn("No paused shop matches", self.cb.build_captcha(c, "mint"))

    def test_points_at_the_security_page_when_security_is_on(self):
        self.assertIn("Security page", self.cb.build_captcha(cfg(enabled=True)))
        self.assertIn("switched off", self.cb.build_captcha(cfg(captcha={"enabled": False})))


if __name__ == "__main__":
    unittest.main()
