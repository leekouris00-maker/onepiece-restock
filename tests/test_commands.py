"""Discord commands (commands_bot.py) without connecting to Discord. Needs: pip install discord.py
(the live-check test also needs cryptography, for the mock shops)."""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402

try:
    import discord  # noqa: F401
    HAVE_DISCORD = True
except ImportError:
    HAVE_DISCORD = False

if HAVE_DISCORD:
    import commands_bot as cb  # noqa: E402
    import tcg_bot as tb  # noqa: E402


def finds_snapshot(ts):
    box = {"id": "box|Gumnut|op18", "kind": "Booster box", "name": "OP-18 Booster Box", "shop": "Gumnut", "price": 249.0,
           "url": "https://www.gumnut.com.au/products/op18", "cart": "https://www.gumnut.com.au/cart/1:1", "note": ""}
    singles = [
        {"id": f"card|Elemental Arcade|X|{i}", "kind": "Single", "name": n, "shop": "Elemental Arcade", "price": p, "qty": q,
         "url": f"https://elementalarcade.com.au/products/{i}", "cart": f"https://elementalarcade.com.au/cart/{100 + i}:{q}",
         "note": "", "deck": "Sabo", "priority": i == 0}
        for i, (n, p, q) in enumerate([("Belo Betty OP05-015", 0.5, 4), ("Monkey.D.Garp OP13-016", 0.55, 4)])]
    listing = {"id": "list|Gumnut|op18", "box_id": "box|Gumnut|op18", "group": "box", "kind": "New listing",
               "name": "OP-18 Booster Box", "shop": "Gumnut", "price": 249.0, "available": True,
               "url": box["url"], "cart": box["cart"], "note": "", "max": 260, "page": 1}
    return {"version": 2, "ts": ts, "sealed": {"ts": ts, "finds": [box], "listings": [listing], "down": []},
            "singles": {"ts": ts, "finds": singles}}


@unittest.skipUnless(HAVE_DISCORD, "needs discord.py")
class Commands(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cmds-")
        self.saved = {k: getattr(tb, k) for k in ("CONFIG_PATH", "SECRETS_PATH", "SNAPSHOT_PATH", "STATUS_PATH",
                                                   "CONTROLS_PATH", "HISTORY_PATH", "EVENTS_PATH", "PICKS_PATH")}
        for k in self.saved:
            setattr(tb, k, os.path.join(self.dir, os.path.basename(self.saved[k])))
        self.audit = cb.AUDIT_PATH
        cb.AUDIT_PATH = os.path.join(self.dir, "audit.log")
        shutil.copy(os.path.join(helpers.REPO, "config.json"), tb.CONFIG_PATH)
        cb.LIVE.result, cb.LIVE.t = None, 0.0

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(tb, k, v)
        cb.AUDIT_PATH = self.audit
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_deals_answers_from_a_recent_snapshot(self):
        tb.atomic_write_json(tb.SNAPSHOT_PATH, finds_snapshot(time.time() - 120))
        cfg = cb.cfg_now()
        data, ts, kind, note = asyncio.run(cb.get_data(cfg, False, 1))
        self.assertEqual(kind, "snapshot")
        e = cb.build_deals(cfg, data, kind, ts, note=note)
        self.assertIn("(3)", e.title)
        text = json.dumps(e.to_dict())
        self.assertIn("One cart at Elemental Arcade", text)
        self.assertIn("/cart/100:4,101:4", text)
        self.assertIn("2 min ago", e.footer.text)

    def test_boxes_lists_in_stock_boxes(self):
        tb.atomic_write_json(tb.SNAPSHOT_PATH, finds_snapshot(time.time()))
        cfg = cb.cfg_now()
        data, ts, kind, note = asyncio.run(cb.get_data(cfg, False, 1))
        e = cb.build_listings(cfg, data, kind, ts, "box", note=note)
        self.assertIn("(1)", e.title)
        self.assertIn("✅", e.fields[0].value)

    def test_want_add_and_remove_edit_config_safely(self):
        with open(tb.SECRETS_PATH, "w") as f:
            json.dump({"discord_webhook_boxes": "https://discord.com/api/webhooks/1/SECRET"}, f)
        (what, card), problems = cb.edit_config(
            lambda raw: ("added", raw["singles"]["cards"].append({"name": "Koala", "num": "OP12-086", "qty": 2, "max": 3.0,
                                                                  "enabled": True}) or raw["singles"]["cards"][-1]),
            "tester", "want OP12-086")
        self.assertEqual(problems, [])
        with open(tb.CONFIG_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        self.assertEqual(raw["singles"]["cards"][-1]["num"], "OP12-086")
        self.assertNotIn("SECRET", json.dumps(raw), "secrets.json must never be copied into config.json")
        self.assertTrue(os.path.exists(tb.CONFIG_PATH + ".bak"))
        with open(cb.AUDIT_PATH, encoding="utf-8") as f:
            self.assertIn("tester  want OP12-086", f.read())

    def test_card_numbers(self):
        self.assertEqual(cb.norm_num("op13120"), "OP13-120")
        self.assertEqual(cb.norm_num(" prb02-014 "), "PRB02-014")
        self.assertEqual(cb.norm_num("p105"), "P-105")
        self.assertIsNone(cb.norm_num("sabo"))

    def test_admin_check(self):
        cfg = {"alerts": {"admin_user_ids": ["42"]}}
        perms = types.SimpleNamespace(manage_guild=False, administrator=False)
        inter = types.SimpleNamespace(user=types.SimpleNamespace(id=42, guild_permissions=perms))
        self.assertTrue(cb.is_admin(inter, cfg))
        inter.user.id = 7
        self.assertFalse(cb.is_admin(inter, cfg))
        inter.user.guild_permissions = types.SimpleNamespace(manage_guild=True, administrator=False)
        self.assertTrue(cb.is_admin(inter, cfg))

    def test_history_and_stats_render(self):
        tb.record_history({"Gumnut": [finds_snapshot(time.time())["sealed"]["listings"][0]]})
        cfg = cb.cfg_now()
        self.assertIn("OP-18", cb.build_history(cfg, "op-18").fields[0].value)
        self.assertTrue(cb.build_stats(cfg).fields)

    @unittest.skipUnless(helpers.have_crypto(), "needs cryptography for the mock shops")
    def test_fresh_checks_are_shared(self):
        net = helpers.Net()
        try:
            net.patch_process(tb)
            tb.HTTP.close_idle()
            tb.HTTP.memo.clear()
            tb.HTTP.robots.clear()
            cfg = cb.cfg_now()

            async def burst():
                return await asyncio.gather(*(cb.get_data(cfg, True, f"user{i}") for i in range(5)))
            out = asyncio.run(burst())
            self.assertTrue(all(kind == "live" for _, _, kind, _ in out))
            self.assertEqual(net.inet.stats.paths[("www.gumnut.com.au", "collection")], 1, "five people, one check")
        finally:
            net.unpatch_process()
            net.stop()


if __name__ == "__main__":
    unittest.main()
