"""Whole-bot runs (python tcg_bot.py, as the PC and cloud run it) against the mock shops, including
side-by-side checks against the original v1 bot. Needs: pip install cryptography"""
import os
import re
import sys
import time
import unittest
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402

import fixtures  # noqa: E402  (bench/, put on the path by helpers)

NET = None
V2 = os.path.join(helpers.REPO, "tcg_bot.py")
HAVE_V1 = os.path.exists(helpers.V1_BOT)


def setUpModule():
    global NET
    if not helpers.have_crypto():
        raise unittest.SkipTest("needs the cryptography package for the mock shops' TLS certificate")
    NET = helpers.Net()


def tearDownModule():
    if NET:
        NET.stop()


def posted_titles():
    return sorted(e["title"] for p in NET.inet.stats.discord for e in p.get("embeds", []) if e.get("title"))


class Base(unittest.TestCase):
    def setUp(self):
        NET.inet.data = fixtures.build("baseline")
        NET.inet.stats.reset()
        NET.inet.discord_fail = 0
        NET.inet.ntfy_pc_on = False
        NET.inet.profile.discord_429 = 0


class Basics(Base):
    def test_full_run_writes_snapshot_and_state(self):
        d = helpers.bot_dir(V2, base=NET.dir)
        p = helpers.run_bot(NET, d, extra_env=helpers.WEBHOOKS)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        snap = helpers.load(d, "latest.json")
        self.assertIn("sealed", snap)
        self.assertIn("singles", snap)
        self.assertTrue(snap["sealed"]["listings"])
        self.assertTrue(helpers.load(d, "seen.json"))
        self.assertTrue(NET.inet.stats.discord, "fresh install should post what's in stock under max")
        posts = NET.inet.stats.discord
        self.assertIn("<@&", posts[0]["content"])
        for p in posts:                       # a channel's 2nd, 3rd... message of the same batch doesn't ping again
            if any(f"({i}/" in p["content"] for i in range(2, 10)):
                self.assertNotIn("<@&", p["content"])
                self.assertEqual(p["allowed_mentions"], {"parse": []})

    def test_dry_run_saves_and_posts_nothing(self):
        d = helpers.bot_dir(V2, base=NET.dir)
        p = helpers.run_bot(NET, d, ["--dry-run"], extra_env=helpers.WEBHOOKS)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(sorted(os.listdir(d)), ["config.json", "tcg_bot.py"])
        self.assertEqual(NET.inet.stats.discord, [])

    def test_self_test_passes(self):
        d = helpers.bot_dir(V2, base=NET.dir)
        p = helpers.run_bot(NET, d, ["--self-test"])
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn("PASS", p.stdout)

    def test_notepad_bom_in_config_is_fine(self):
        d = helpers.bot_dir(V2, base=NET.dir)
        path = os.path.join(d, "config.json")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write(text)
        p = helpers.run_bot(NET, d, ["--dry-run"])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_cloud_status_file_has_no_per_run_noise(self):
        d = helpers.bot_dir(V2, base=NET.dir)
        helpers.run_bot(NET, d, extra_env={"GITHUB_ACTIONS": "true"})
        st = helpers.load(d, "status.json")
        for k in ("last_check", "last_found", "last_run"):
            self.assertNotIn(k, st)


class DeliveryNeverLost(Base):
    def test_alerts_are_retried_when_discord_is_down(self):
        d = helpers.bot_dir(V2, base=NET.dir)
        NET.inet.discord_fail = 10 ** 6
        p = helpers.run_bot(NET, d, extra_env=helpers.WEBHOOKS)
        self.assertIn("didn't reach Discord", p.stdout)
        seen = helpers.load(d, "seen.json", {})
        self.assertFalse(any(k.startswith("card|") for k in seen), "undelivered finds must not be marked seen")
        NET.inet.discord_fail = 0
        NET.inet.stats.reset()
        helpers.run_bot(NET, d, extra_env=helpers.WEBHOOKS)
        self.assertTrue(any("Belo Betty" in t for t in posted_titles()))
        self.assertTrue(any(k.startswith("card|") for k in helpers.load(d, "seen.json", {})))

    @unittest.skipUnless(HAVE_V1, "original bot not found")
    def test_v1_loses_them(self):
        """The bug v2 fixes: v1 saves finds as seen even when the Discord post failed."""
        d = helpers.bot_dir(helpers.V1_BOT, base=NET.dir)
        NET.inet.discord_fail = 10 ** 6
        helpers.run_bot(NET, d, extra_env=helpers.WEBHOOKS)
        NET.inet.discord_fail = 0
        NET.inet.stats.reset()
        helpers.run_bot(NET, d, extra_env=helpers.WEBHOOKS)
        self.assertFalse(any("Belo Betty" in t for t in posted_titles()))


class Handoff(Base):
    """Cloud copy (listen) + PC copy: nothing posted twice, nothing lost when the PC goes quiet."""

    def run_cloud(self, d):
        return helpers.run_bot(NET, d, extra_env=dict(helpers.WEBHOOKS, HEARTBEAT_TOPIC="t", HEARTBEAT_ROLE="listen"))

    def test_cloud_posts_what_the_pc_missed(self):
        d = helpers.bot_dir(V2, base=NET.dir)
        NET.inet.ntfy_pc_on, NET.inet.ntfy_last = True, time.time() - 60
        self.run_cloud(d)                              # PC on: cloud quiet
        self.assertEqual(NET.inet.stats.discord, [])
        time.sleep(1.1)
        NET.inet.ntfy_last = time.time()               # PC checked in after that: it posted those itself
        self.run_cloud(d)
        self.assertEqual(helpers.load(d, "status.json")["held"], {})
        NET.inet.ntfy_last = time.time()
        time.sleep(1.1)
        NET.inet.data = fixtures.build("restock")      # boxes restock... and the PC dies before its next check
        self.run_cloud(d)
        self.assertEqual(NET.inet.stats.discord, [])
        self.assertTrue(helpers.load(d, "status.json")["held"])
        NET.inet.ntfy_pc_on = False                    # 20 minutes of silence later
        self.run_cloud(d)
        titles = posted_titles()
        self.assertTrue(any("OP-18" in t for t in titles), titles)
        self.assertEqual(helpers.load(d, "status.json")["held"], {})


@unittest.skipUnless(HAVE_V1, "original bot not found")
class SameFindsAsV1(Base):
    """v1 and v2 read the same shops and must find the same things (v2 only adds what v1 couldn't see)."""

    def pair(self):
        return helpers.bot_dir(helpers.V1_BOT, base=NET.dir), helpers.bot_dir(V2, base=NET.dir)

    def test_same_state_and_alerts(self):
        d1, d2 = self.pair()
        for scenario in ("baseline", "restock"):
            NET.inet.data = fixtures.build(scenario)
            out = {}
            for name, d in (("v1", d1), ("v2", d2)):
                NET.inet.stats.reset()
                p = helpers.run_bot(NET, d, extra_env=helpers.WEBHOOKS)
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                titles = [t for t in posted_titles() if not t.startswith("🧺")]
                cut = sum(int(m) for p in NET.inet.stats.discord for m in re.findall(r"\+(\d+) more", p["content"]))
                out[name] = (helpers.load(d, "seen.json"), helpers.load(d, "known_products.json"), titles, cut)
            (s1, k1, t1, cut1), (s2, k2, t2, cut2) = out["v1"], out["v2"]
            self.assertEqual(s1, s2, f"{scenario}: seen.json differs")
            for shop, ids in k1.items():
                self.assertTrue(set(ids) <= set(k2.get(shop, [])), f"{scenario}: v2 forgot listings at {shop}")
            extra = {shop: sorted(set(k2[shop]) - set(k1.get(shop, []))) for shop in k2 if set(k2[shop]) - set(k1.get(shop, []))}
            self.assertTrue(set(extra) <= {"Pokebox"}, f"only Pokebox page 2 should add listings: {extra}")
            # v1 cut each channel off at 10 finds ("+N more, see finds.log"); v2 sends them all
            self.assertFalse(Counter(t1) - Counter(t2), f"{scenario}: v2 missed an alert v1 sent")
            self.assertEqual(cut2, 0)
            self.assertEqual(len(t2), len(t1) + cut1, f"{scenario}: v2 should send exactly what v1 cut off")


if __name__ == "__main__":
    unittest.main()
