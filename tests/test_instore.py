"""v2.10: the One Piece in-store section (onepiece_instore.py + tcg_bot.onepiece_posts)."""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tcg_bot as tb            # noqa: E402
import onepiece_instore as oi   # noqa: E402

RELEASES = [{"date": "2026-11-20", "name": "OP-18 The Dominance of God"},
            {"date": "2026-11-20", "name": "DP-13 Double Pack Set Vol. 13"},
            {"date": "2026-12-04", "name": "IB-09 / IB-10 Illustration Boxes"},
            {"date": "2027-03-01", "name": "29th Anniversary Premium Card Collection (date approx.)"}]
DAY = datetime(2026, 11, 20)
INSTORE, SEALED, STATUS = ("https://discord.com/api/webhooks/1/instore", "https://discord.com/api/webhooks/2/sealed",
                           "https://discord.com/api/webhooks/3/status")


def quiet(fn, *a, **kw):
    out, old = io.StringIO(), sys.stdout
    sys.stdout = out
    try:
        return fn(*a, **kw)
    finally:
        sys.stdout = old


class Settings(unittest.TestCase):
    def test_defaults_and_off(self):
        s = oi.settings({})
        self.assertTrue(s["enabled"])
        self.assertEqual((s["evening"], s["morning"]), ("18:00", "07:00"))
        self.assertFalse(oi.settings({"instore": False})["enabled"])
        self.assertFalse(oi.settings({"instore": {"enabled": False}})["enabled"])

    def test_bad_values_fall_back_with_a_warning(self):
        cfg = {"instore": {"evening": "6pm", "stores": "Kmart"}}
        s = oi.settings(cfg)
        self.assertEqual(s["evening"], "18:00")
        self.assertEqual(s["stores"], oi.DEFAULT_STORES)
        self.assertEqual(len(oi.warnings(cfg)), 2)
        self.assertEqual(oi.warnings({"instore": {"morning": "6:30", "stores": ["EB Games"]}}), [])
        self.assertEqual(oi.settings({"instore": {"morning": "6:30"}})["morning"], "06:30")


class Calendar(unittest.TestCase):
    def test_release_days_group_by_day_and_skip_approx(self):
        days = oi.release_days({"releases": RELEASES}, now=datetime(2026, 11, 1), days=120)
        self.assertEqual([d for d, _ in days], [DAY, datetime(2026, 12, 4)])
        self.assertEqual(len(days[0][1]), 2)
        op18 = next(r for r in days[0][1] if r["code"] == "OP-18")
        self.assertTrue(op18["booster"])
        self.assertFalse(next(r for r in days[0][1] if r["code"] == "DP-13")["booster"])

    def test_calendar_lines_say_today_tomorrow(self):
        lines = oi.calendar_lines({"releases": RELEASES}, now=DAY - timedelta(days=1))
        self.assertIn("(tomorrow)", lines[0][1])
        self.assertTrue(any("🔜" in t for _, t in lines))   # the approximate one at the end


class Posts(unittest.TestCase):
    def cfg(self):
        return {"releases": RELEASES}

    def test_eve_post_in_its_window_then_never_again(self):
        due = oi.reminders_due(self.cfg(), {}, now=DAY - timedelta(hours=6))      # 19 Nov 6pm
        self.assertEqual([r["key"] for r in due], ["op:2026-11-20|eve"])
        self.assertFalse(due[0]["ping"])
        self.assertIn("Tomorrow in stores", due[0]["embed"]["title"])
        self.assertIn("OP-18", due[0]["embed"]["description"])
        status = {}
        oi.mark_sent(status, due[0]["key"], DAY - timedelta(hours=6))
        self.assertEqual(oi.reminders_due(self.cfg(), status, now=DAY - timedelta(hours=5)), [])
        self.assertEqual(oi.reminders_due(self.cfg(), {}, now=DAY - timedelta(hours=7)), [])    # 5pm: too early

    def test_day_post_pings_and_lists_whats_online(self):
        snap = {"sealed": {"ts": (DAY + timedelta(hours=7)).timestamp() - 600, "listings": [
            {"name": "One Piece OP-18 Booster Box", "shop": "Gumnut", "price": 259.0, "available": True,
             "url": "https://g/p/op18", "cart": "https://g/cart/1:1"},
            {"name": "One Piece Card Game OP18 Booster Display (Preorder)", "shop": "Good Games", "price": 399.0,
             "available": False, "url": "https://gg/p/op18"},
            {"name": "One Piece OP-18 Booster Box JAPANESE", "shop": "Card Bot", "price": 150.0, "available": True,
             "url": "https://cb/p/op18jp"},
            {"name": "One Piece OP-17 Booster Box", "shop": "Gumnut", "price": 200.0, "available": True,
             "url": "https://g/p/op17"}]}}
        due = oi.reminders_due(self.cfg(), {}, now=DAY + timedelta(hours=7), snapshot=snap, money=tb.money, short=tb._short)
        self.assertEqual([r["key"] for r in due], ["op:2026-11-20|day"])
        self.assertTrue(due[0]["ping"])
        field = due[0]["embed"]["fields"][0]["value"]
        self.assertIn("✅ [One Piece OP-18 Booster Box](https://g/cart/1:1) **$259.00** · Gumnut", field)
        self.assertIn("⏳", field)                              # the pre-order, after the buyable one
        self.assertNotIn("JAPANESE", field)
        self.assertNotIn("OP-17", field)
        self.assertEqual(oi.reminders_due(self.cfg(), {}, now=DAY + timedelta(hours=14)), [])   # 2pm: window over

    def test_stale_snapshot_is_not_quoted(self):
        snap = {"sealed": {"ts": (DAY - timedelta(days=1)).timestamp(), "listings": [
            {"name": "OP-18 Booster Box", "shop": "G", "price": 1, "available": True, "url": "u"}]}}
        due = oi.reminders_due(self.cfg(), {}, now=DAY + timedelta(hours=7), snapshot=snap)
        self.assertNotIn("fields", due[0]["embed"])

    def test_drop_note_comes_from_the_real_windows(self):
        wins = [{"name": "OP-18 eve", "start": DAY - timedelta(hours=6), "end": DAY - timedelta(minutes=1), "every": 60,
                 "games": ["onepiece"]},
                {"name": "OP-18 day", "start": DAY + timedelta(hours=8), "end": DAY + timedelta(hours=14), "every": 60,
                 "games": ["onepiece"]},
                {"name": "poke", "start": DAY, "end": DAY + timedelta(hours=14), "every": 60, "games": ["pokemon"]}]
        self.assertEqual(oi.drop_note(wins, DAY, "eve"),
                         " The bot checks the online shops tonight 6:00 PM–11:59 PM (every 60s) and tomorrow 8:00 AM–2:00 PM (every 60s).")
        self.assertIn("today 8:00 AM", oi.drop_note(wins, DAY, "day"))
        self.assertEqual(oi.drop_note([], DAY, "eve"), "")
        self.assertEqual(oi.drop_note(wins[2:], DAY, "day"), "")   # a Pokémon window doesn't count

    def test_recently_sent_and_pruning(self):
        status = {}
        oi.mark_sent(status, "op:2026-11-20|eve", DAY)
        oi.mark_sent(status, "op:2026-10-01|day", DAY)        # pruned: older than 30 days? no, marked now - keep
        self.assertEqual(oi.recently_sent(status, now=DAY + timedelta(minutes=10)), ["op:2026-10-01|day", "op:2026-11-20|eve"])
        self.assertEqual(oi.recently_sent(status, now=DAY + timedelta(hours=1)), [])
        status[oi.STATUS_KEY]["op:2026-09-01|eve"] = (DAY - timedelta(days=40)).timestamp()
        oi.mark_sent(status, "op:2026-11-20|day", DAY)
        self.assertNotIn("op:2026-09-01|eve", status[oi.STATUS_KEY])

    def test_hook_only_when_the_channel_exists(self):
        self.assertEqual(oi.instore_hook({"discord_webhook_sealed": SEALED}), "")
        self.assertEqual(oi.instore_hook({"discord_webhook_instore": INSTORE}), INSTORE)


class InTheBot(unittest.TestCase):
    """tcg_bot.onepiece_posts and the status post, with the clock pinned to release day 7am."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        names = ("STATE_PATH", "KNOWN_PATH", "STATUS_PATH", "SNAPSHOT_PATH", "HISTORY_PATH", "EVENTS_PATH",
                 "LOG_PATH", "CONTROLS_PATH", "RECAP_PATH", "PICKS_PATH", "DROPS_PATH")
        self.paths = {k: getattr(tb, k) for k in names}
        for k in names:
            setattr(tb, k, os.path.join(self.tmp, k.lower() + ".json"))
        self.saved = {n: getattr(tb, n) for n in ("check_sealed", "check_singles", "ebay_watch", "pokemon_watch",
                                                   "link_watch", "fast_lane", "run_price_drops", "store_locked",
                                                   "desktop_beep", "discord_send", "pc_last_seen", "repo_json")}
        tb.check_sealed = lambda cfg, sweep=False: ([], {})
        tb.check_singles = lambda cfg: []
        tb.ebay_watch = tb.pokemon_watch = tb.link_watch = tb.fast_lane = None
        tb.run_price_drops = lambda cfg, status, **kw: []
        tb.store_locked = lambda host: False
        tb.desktop_beep = lambda: None
        tb.pc_last_seen = lambda cfg: None
        tb.repo_json = lambda cfg, name, max_age=1800: None
        self.sent = []
        tb.discord_send = lambda alerts, hook, payload, tries=3: self.sent.append((hook, payload)) or True
        tb.PC_INFO.update(pokemon=False, posted=set())

    def tearDown(self):
        for k, v in {**self.paths, **self.saved}.items():
            setattr(tb, k, v)
        tb.PC_INFO.update(pokemon=False, posted=set())
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cfg(self, **alerts):
        return {"sealed": {"max_price": 260}, "singles": {"shops": {}, "cards": []}, "releases": RELEASES,
                "auto_drop_windows": False, "alerts": {"discord_webhook_sealed": SEALED, "discord_webhook_status": STATUS,
                                                       "discord_ping": "<@&9>", **alerts}}

    def posts(self, cfg, role=None, pc_on=False, status=None, now=DAY + timedelta(hours=7)):
        status = {} if status is None else status
        keys = quiet(tb.onepiece_posts, cfg, status, role, pc_on, now)
        return keys, status

    def test_quiet_without_the_channel(self):
        keys, status = self.posts(self.cfg())
        self.assertEqual((keys, self.sent), ([], []))
        self.assertNotIn(oi.STATUS_KEY, status)              # not marked: it posts once the channel exists

    def test_posts_once_with_ping_then_remembers(self):
        cfg = self.cfg(discord_webhook_instore=INSTORE)
        keys, status = self.posts(cfg)
        self.assertEqual(keys, ["op:2026-11-20|day"])
        hook, payload = self.sent[0]
        self.assertEqual(hook, INSTORE)
        self.assertEqual(payload["content"], "<@&9>")
        self.assertEqual(payload["allowed_mentions"], {"parse": ["roles", "users", "everyone"]})
        self.assertIn("Out today in stores", payload["embeds"][0]["title"])
        self.assertIn("op:2026-11-20|day", status[oi.STATUS_KEY])
        self.posts(cfg, status=status)
        self.assertEqual(len(self.sent), 1)

    def test_cloud_copy_waits_for_the_pc(self):
        cfg = self.cfg(discord_webhook_instore=INSTORE)
        keys, status = self.posts(cfg, role="listen", pc_on=True)
        self.assertEqual((keys, self.sent), ([], []))
        self.assertNotIn(oi.STATUS_KEY, status)               # the PC posts it; only marked once the PC says so
        tb.PC_INFO["posted"] = {"op:2026-11-20|day"}
        keys, status = self.posts(cfg, role="listen", pc_on=True)
        self.assertEqual(self.sent, [])
        self.assertIn("op:2026-11-20|day", status[oi.STATUS_KEY])
        tb.PC_INFO["posted"] = set()
        keys, _ = self.posts(cfg, role="listen", pc_on=False)   # PC off: the cloud copy posts it
        self.assertEqual(keys, ["op:2026-11-20|day"])

    def test_pc_copy_skips_what_the_cloud_posted(self):
        tb.repo_json = lambda cfg, name, max_age=1800: {oi.STATUS_KEY: {"op:2026-11-20|day": 1}}
        keys, status = self.posts(self.cfg(discord_webhook_instore=INSTORE), role="send")
        self.assertEqual((keys, self.sent), ([], []))
        self.assertIn("op:2026-11-20|day", status[oi.STATUS_KEY])

    def test_heartbeat_carries_the_posts(self):
        status = {}
        oi.mark_sent(status, "op:2026-11-20|day")
        self.assertIn("r=op:2026-11-20|day", tb.heartbeat_body(self.cfg(heartbeat_topic="t"), status))

    def test_status_post_quiet_then_live_once_each(self):
        status = {}
        posts = tb.onepiece_status_posts(self.cfg(), status, DAY - timedelta(days=5))
        self.assertEqual(len(posts), 1)
        self.assertIn("quietly", posts[0][0])
        self.assertIn("Fri 20 Nov", posts[0][0])
        self.assertEqual(tb.onepiece_status_posts(self.cfg(), status), [])
        posts = tb.onepiece_status_posts(self.cfg(discord_webhook_instore=INSTORE), status)
        self.assertIn("live", posts[0][0])
        self.assertEqual(tb.onepiece_status_posts(self.cfg(discord_webhook_instore=INSTORE), status), [])

    def test_full_run_is_quiet_on_release_day_without_the_channel(self):
        """run_once with the real clock: whatever today is, no in-store post lands in another channel."""
        a = SimpleNamespace(all=False, loop=None, sealed=False, singles=False, pokemon=False)
        quiet(tb.run_once, self.cfg(), a)
        hooks = [h for h, _ in self.sent]
        self.assertNotIn(SEALED, hooks)
        self.assertEqual([h for h in hooks if h != STATUS], [])
        with open(tb.STATUS_PATH) as f:
            self.assertEqual(json.load(f)["instore_state"], "quiet")


if __name__ == "__main__":
    unittest.main()
