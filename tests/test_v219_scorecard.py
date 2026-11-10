"""v2.19: the scorecard (scorecard.py, /scorecard, the feed channel) and the uptime log. No network.

Run:  python -m unittest discover -s tests
"""
import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime
from types import SimpleNamespace as NS
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402
import misses as ms  # noqa: E402
import scorecard as sc  # noqa: E402

NOW = 1_800_000_000
GUMNUT = "https://www.gumnut.com.au/products/op-18-booster-box"
CFG = {"sealed": {"max_price": 260, "shopify_collections": [
           {"name": "Gumnut", "url": "https://www.gumnut.com.au/collections/one-piece/products.json"}]},
       "singles": {"shops": {"Good Games": "https://tcg.goodgames.com.au"}, "cards": []},
       "extra_shops": False}


def mem(hist=None, events=None):
    return {"hist": [hist or {}], "known": [{}], "drops": [{}], "events": list(events or [])}


def box_hist():
    return {"box|Gumnut|op-18-booster-box": {"name": "One Piece OP-18 Booster Box", "shop": "Gumnut", "url": GUMNUT,
                                             "points": [["2026-10-22", 249.0, True]], "avail": True,
                                             "first": NOW - 86400}}


class Isolated(unittest.TestCase):
    """Every test gets its own bot folder, so nothing touches the real misses.json or uptime.json."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        for name, val in (("HERE", self.dir.name), ("UPTIME_PATH", os.path.join(self.dir.name, "uptime.json")),
                          ("EVENTS_PATH", os.path.join(self.dir.name, "events.jsonl"))):
            p = mock.patch.object(tb, name, val)
            p.start()
            self.addCleanup(p.stop)
        tb.DRY_RUN[0] = False


class Links(unittest.TestCase):
    def test_product_links_only(self):
        text = ("OP-18 restock! <https://www.Gumnut.com.au/products/op-18-booster-box?variant=12> also "
                "https://gumnut.com.au/products/op-18-booster-box (same) https://discord.gg/abc "
                "https://cdn.shop.com/files/box.png https://www.pokebox.com.au/ https://x.com/fellowship/status/1")
        self.assertEqual(sc.product_links([text]), [GUMNUT.replace("www.", "")])

    def test_message_reads_embeds_and_forwards(self):
        embed = NS(url="https://jtoys.com.au/products/op-18", title="OP-18 Booster Box", description="In stock",
                   author=None, fields=[NS(name="Also", value="[EB](https://www.ebgames.com.au/product/x/123)")])
        posted = datetime.fromtimestamp(NOW)
        original = datetime.fromtimestamp(NOW - 300)
        snap = NS(content="https://pokebox.com.au/products/op-18-box", embeds=[], created_at=original)
        msg = NS(content="", embeds=[embed], created_at=posted, message_snapshots=[snap])
        links, when = sc.message_links(msg)
        self.assertEqual(links, ["https://jtoys.com.au/products/op-18", "https://ebgames.com.au/product/x/123",
                                 "https://pokebox.com.au/products/op-18-box"])
        self.assertEqual(when, NOW - 300)           # a forward counts from when it was first posted


class Queue(Isolated):
    def test_waits_then_grades_once_per_drop(self):
        cfg = {**CFG, "scorecard": {"ignore_hosts": ["www.amazon.com"]}}
        added = sc.queue(tb, cfg, [GUMNUT, "https://amazon.com/dp/B0X"], NOW, {"channel_id": 1, "message_id": 2},
                         now=NOW)
        self.assertEqual(added, [GUMNUT.replace("www.", "")])          # ignored hosts never go in
        self.assertEqual(sc.queue(tb, cfg, [GUMNUT], NOW + 600, now=NOW + 600), [])   # same drop again
        self.assertEqual(sc.take_due(tb, NOW + 29 * 60), [])           # not yet: a late bot alert still counts
        due = sc.take_due(tb, NOW + 30 * 60)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["ref"], {"channel_id": 1, "message_id": 2})
        self.assertEqual(sc.take_due(tb, NOW + 31 * 60), [])
        self.assertEqual(sc.load_state(tb)["feed_since"], NOW)
        self.assertEqual(len(sc.queue(tb, cfg, [GUMNUT], NOW + 7 * 3600, now=NOW + 7 * 3600)), 1)   # a new drop

    def test_grade_logs_a_feed_result(self):
        ev = [{"t": NOW - 240, "event": "alert", "url": GUMNUT}]
        with mock.patch.object(ms, "memory", return_value=mem(box_hist(), ev)):
            sc.queue(tb, CFG, [GUMNUT], NOW, {"channel_id": 1, "message_id": 2}, now=NOW)
            [(item, res)] = sc.grade_due(tb, CFG, NOW + 1800)
        self.assertEqual((res["kind"], res["lead_min"]), ("first", 4))
        self.assertEqual(sc.one_line(res), "✅ Bot was first by 4 min · Gumnut")
        [logged] = json.load(open(ms.misses_path(tb)))
        self.assertEqual((logged["source"], logged["kind"], logged["lead_min"]), ("feed", "first", 4))

    def test_last_weeks_alert_is_not_a_win(self):
        ev = [{"t": NOW - 3 * 86400, "event": "alert", "url": GUMNUT}]
        r = ms.explain(tb, CFG, GUMNUT, reported=NOW, remote=False, live=False, mem=mem(box_hist(), ev), match_hours=6)
        self.assertEqual(r["kind"], "seen")
        r = ms.explain(tb, CFG, GUMNUT, reported=NOW, remote=False, live=False, mem=mem(box_hist(), ev))
        self.assertEqual(r["kind"], "first")       # /missed keeps its old answer

    def test_never_looks_up_an_unlisted_shop_when_security_is_on(self):
        calls = []
        look = lambda tb_, host, handle: calls.append(host)  # noqa: E731
        ng = NS(RT={"on": True, "s": {"enforce": True}})
        with mock.patch.object(ms, "live_look", look), mock.patch.object(tb, "netguard", ng, create=True):
            r = ms.explain(tb, CFG, "https://randomshop.com/products/x", reported=NOW, remote=False, mem=mem())
            self.assertEqual(r["kind"], "not_watched")
            self.assertEqual(calls, [])
            ms.explain(tb, CFG, "https://www.gumnut.com.au/products/pcc", reported=NOW, remote=False, mem=mem())
            self.assertEqual(calls, ["gumnut.com.au"])              # its own shops are still fine


class Uptime(Isolated):
    def test_marks_each_hour_once(self):
        self.assertTrue(tb.mark_uptime(NOW, "pc"))
        self.assertFalse(tb.mark_uptime(NOW + 60, "pc"))           # same hour: file not rewritten
        self.assertTrue(tb.mark_uptime(NOW + 3600, "pc"))
        data = json.load(open(tb.UPTIME_PATH))
        line = data["pc"][time.strftime("%Y-%m-%d", time.gmtime(NOW))]
        h = int(NOW // 3600) % 24
        self.assertEqual(line[h:h + 2], "11")
        tb.DRY_RUN[0] = True
        try:
            self.assertFalse(tb.mark_uptime(NOW + 7200, "pc"))
        finally:
            tb.DRY_RUN[0] = False

    def test_percentages_and_longest_gap(self):
        start = (NOW // 86400) * 86400                              # midnight UTC
        for h in list(range(0, 10)) + list(range(14, 24)):          # PC down 10:00-14:00
            tb.mark_uptime(start + h * 3600 + 5, "pc")
        for h in range(11, 13):                                     # the cloud covers part of it
            tb.mark_uptime(start + h * 3600 + 5, "cloud")
        up = sc.uptime(tb, {}, days=28, now=start + 86400 + 10, remote=False)
        self.assertEqual(up["hours"], 24)                           # starts when the log starts
        self.assertAlmostEqual(up["pc"], 20 / 24)
        self.assertAlmostEqual(up["either"], 22 / 24)
        self.assertEqual(up["longest_gap_h"], 1)

    def test_no_log_yet(self):
        self.assertIsNone(sc.uptime(tb, {}, now=NOW, remote=False))


class Summary(Isolated):
    def log(self, kind, n, **extra):
        for i in range(n):
            ms.record(tb, {"kind": kind, "link": f"https://gumnut.com.au/products/{kind}-{i}", "host": "gumnut.com.au",
                           "shop": "Gumnut", "reported": NOW - 3600, "source": "feed", **extra})

    def test_verdict(self):
        st = sc.load_state(tb)
        st["feed_since"] = NOW - 30 * 86400
        sc.save_state(tb, st)
        self.log("first", 26, lead_min=3)
        self.log("late", 2, late_min=1)            # within a minute: counts as keeping up
        self.log("late", 2, late_min=9)
        self.log("not_watched", 4)                 # not counted against the bot
        ms.record(tb, {"kind": "late", "late_min": 40, "link": "x", "host": "a.com", "reported": NOW - 60})  # /missed
        for h in range(28 * 24):
            tb.mark_uptime(NOW - h * 3600, "pc")
        bot = [{"t": NOW - 7200, "event": "alert", "kind": "Booster box", "shop": "Pokebox",
                "url": "https://pokebox.com.au/products/op-18"},
               {"t": NOW - 7200, "event": "alert", "kind": "Booster box", "shop": "Gumnut",
                "url": "https://gumnut.com.au/products/first-0"},                      # the feed had this one
               {"t": NOW - 7200, "event": "alert", "kind": "Single", "shop": "eBay (from Japan)", "url": "https://ebay.com.au/itm/1"}]
        s = sc.summary(tb, CFG, 28, NOW, remote=False, mem=mem(events=bot))
        self.assertEqual((s["scope"], s["wins"], s["manual"]), (30, 28, 1))
        self.assertAlmostEqual(s["win_rate"], 28 / 30)
        self.assertEqual([e["shop"] for e in s["bot_only"]], ["Pokebox"])
        self.assertTrue(s["ready"], s["checks"])
        title, lines = sc.render(s)
        self.assertIn("Ready to charge", title)
        self.assertTrue(any("gumnut.com.au (4)" in line for line in lines))
        self.assertTrue(any("not in the verdict" in line for line in lines))

    def test_not_ready_says_why(self):
        self.log("first", 3, lead_min=2)
        self.log("not_found", 2)
        s = sc.summary(tb, CFG, 28, NOW, remote=False, mem=mem())
        self.assertFalse(s["ready"])
        title, lines = sc.render(s)
        self.assertIn("Not ready", title)
        self.assertIn("❌ 5 of 30 drops compared", lines)
        self.assertTrue(any("uptime: no log yet" in line for line in lines))

    def test_empty(self):
        title, lines = sc.render(sc.summary(tb, CFG, 28, NOW, remote=False, mem=mem()))
        self.assertTrue(any("No feed yet" in line for line in lines))

    def test_weekly_once(self):
        monday = datetime(2026, 11, 16, 9, 5).timestamp()
        self.assertFalse(sc.weekly_due(tb, {}, monday - 3600))     # 8am: not yet
        self.assertTrue(sc.weekly_due(tb, {}, monday))
        self.assertFalse(sc.weekly_due(tb, {}, monday + 600))
        self.assertFalse(sc.weekly_due(tb, {"scorecard": {"weekly_post": False}}, monday + 7 * 86400))


class DiscordCommand(Isolated):
    def setUp(self):
        super().setUp()
        try:
            import commands_bot
        except (Exception, SystemExit) as e:  # noqa: BLE001
            self.skipTest(f"discord.py isn't installed here ({e})")
        self.cb = commands_bot

    def test_commands_registered(self):
        names = {c.name for c in self.cb.bot.tree.get_commands()}
        self.assertIn("scorecard", names)
        self.assertIn("Grade against bot", {c.name for c in self.cb.bot.tree.get_commands(
            type=self.cb.discord.AppCommandType.message)})

    def test_scorecard_embed(self):
        e = self.cb.build_scorecard(CFG, 28)
        self.assertIn("Not ready", e.title)

    def test_feed_message_is_queued(self):
        cfg = {**CFG, "scorecard": {"feed_channel_id": "55"}}
        reacted = []

        async def react(emoji):
            reacted.append(emoji)

        msg = NS(author=NS(), guild=NS(), channel=NS(id=55), id=9, content=f"Restock {GUMNUT}", embeds=[],
                 created_at=datetime.fromtimestamp(time.time()), message_snapshots=[], add_reaction=react)
        with mock.patch.object(self.cb, "cfg_now", return_value=cfg), \
                mock.patch.object(tb, "load_config", return_value=cfg):
            asyncio.run(self.cb.on_message(msg))
        self.assertEqual(reacted, ["⏳"])
        [p] = sc.load_state(tb)["pending"]
        self.assertEqual(p["ref"], {"channel_id": 55, "message_id": 9})
        msg.channel = NS(id=56)                                    # other channels are left alone
        with mock.patch.object(self.cb, "cfg_now", return_value=cfg), \
                mock.patch.object(tb, "load_config", return_value=cfg):
            asyncio.run(self.cb.on_message(msg))
        self.assertEqual(len(reacted), 1)


class ChromeSandbox(unittest.TestCase):
    """v2.19: the auto-buy Chrome keeps its sandbox (Playwright turns it off unless asked)."""

    def setUp(self):
        try:
            import auto_buy
        except Exception as e:  # noqa: BLE001
            self.skipTest(f"auto_buy won't import here ({e})")
        self.ab = auto_buy

    def pw(self, fail_when):
        calls = []

        def launch(**kw):
            calls.append((kw.get("channel"), kw["chromium_sandbox"]))
            err = fail_when(kw)
            if err:
                raise RuntimeError(err)
            return "ctx"
        return NS(chromium=NS(launch_persistent_context=launch)), calls

    def test_sandbox_on(self):
        pw, calls = self.pw(lambda kw: None)
        self.assertEqual(self.ab.launch_chrome(pw, {"user_data_dir": "x", "browser": "chrome"}), "ctx")
        self.assertEqual(calls, [("chrome", True)])

    def test_no_chrome_uses_bundled_chromium_still_sandboxed(self):
        pw, calls = self.pw(lambda kw: "chrome not found" if kw.get("channel") else None)
        self.ab.launch_chrome(pw, {"user_data_dir": "x"})
        self.assertEqual(calls, [("chrome", True), (None, True)])

    def test_falls_back_only_when_the_sandbox_itself_fails(self):
        pw, calls = self.pw(lambda kw: "sandbox failed" if kw["chromium_sandbox"] else None)
        self.ab.launch_chrome(pw, {"user_data_dir": "x"})
        self.assertEqual(calls[-1], ("chrome", False))

    def test_profile_in_use_is_not_retried_without_sandbox(self):
        pw, calls = self.pw(lambda kw: "user data directory is already in use")
        with self.assertRaises(RuntimeError):
            self.ab.launch_chrome(pw, {"user_data_dir": "x"})
        self.assertTrue(all(sb for _, sb in calls))


if __name__ == "__main__":
    unittest.main()
