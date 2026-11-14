"""v2.21: a settings file with a typo is said out loud (never showing a secret), the updater keeps itself
current, and the drop rehearsal's readiness card. No network."""
import ast
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from unittest import mock

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import add_channels as ac  # noqa: E402
import add_pokemon_channels as apc  # noqa: E402
import rehearsal as rh  # noqa: E402
import settings_check as sc  # noqa: E402
import tcg_bot as tb  # noqa: E402
import updater as up  # noqa: E402

HOOK = "https://discord.com/api/webhooks/123456789012345678/SeCrEtToKeN_abcdefghijklmnop"
TOPIC = "lees-very-private-topic"
MISSING_COMMA = ('{\n "discord_webhook_boxes": "' + HOOK + '",\n "ntfy_topic": "' + TOPIC + '"\n'
                 ' "discord_bot_token": "abc"\n}\n')


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class Typos(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def p(self, name, text):
        path = os.path.join(self.dir.name, name)
        write(path, text)
        return path

    def test_missing_comma_names_the_line_before(self):
        r = sc.problem(self.p("secrets.json", MISSING_COMMA))
        self.assertEqual(r["line"], 4)
        self.assertIn("secrets.json has a typo on line 4", r["text"])
        self.assertIn("Line 3 is probably missing a comma", r["text"])
        self.assertIn('"ntfy_topic": "***"', r["text"])

    def test_never_shows_a_secret(self):
        for text in (MISSING_COMMA, '{\n "ntfy_topic": "' + TOPIC + ',\n "x": 1\n}', '{\n ntfy_topic: "' + TOPIC + '"\n}',
                     '{\n "a": "' + HOOK + '"\n "b": 2\n}', '{"discord_webhook": "' + HOOK + '" "ntfy_topic": "' + TOPIC + '"}'):
            r = sc.problem(self.p("secrets.json", text))
            self.assertIsNotNone(r)
            for secret in (TOPIC, "SeCrEtToKeN", "123456789012345678"):
                self.assertNotIn(secret, json.dumps(r), text)

    def test_config_hides_sensitive_values_but_shows_ordinary_ones(self):
        r = sc.problem(self.p("config.json", '{\n "alerts": {\n  "ntfy_topic": "' + TOPIC + '"\n  "bot_name": "x"\n }\n}'))
        self.assertNotIn(TOPIC, r["text"])
        r = sc.problem(self.p("config.json", '{\n "sealed": {\n  "max_price": 260\n  "x": 1\n }\n}'))
        self.assertIn('"max_price": 260', r["text"])
        r = sc.problem(self.p("config.json", '{\n "note": "see ' + HOOK + '"\n "x": 1\n}'))
        self.assertNotIn("SeCrEtToKeN", r["text"])

    def test_other_typos(self):
        r = sc.problem(self.p("config.json", '{\n "a": 1,\n "b": 2,\n}'))
        self.assertIn("Line 3 ends with a comma but it's the last entry", r["text"])
        self.assertIn("quote mark", sc.problem(self.p("config.json", '{\n "a": "b\n}'))["text"])
        self.assertIn("empty", sc.problem(self.p("config.json", ""))["text"])
        self.assertIn("start with {", sc.problem(self.p("config.json", "[1, 2]"))["text"])

    def test_fine_or_missing(self):
        self.assertIsNone(sc.problem(self.p("config.json", '{"a": 1}')))
        self.assertIsNone(sc.problem(self.p("config.json", '\ufeff{"a": 1}')))          # Notepad's BOM
        self.assertIsNone(sc.problem(os.path.join(self.dir.name, "nope.json")))

    def test_channel_scripts_say_it_plainly(self):
        path = self.p("secrets.json", MISSING_COMMA)
        for mod in (ac, apc):
            with self.assertRaises(mod.SettingsTypo) as cm:
                mod.read_json(path)
            msg = str(cm.exception)
            self.assertIn("Line 3 is probably missing a comma", msg)
            self.assertIn("Notepad", msg)
            self.assertNotIn(TOPIC, msg)
            self.assertIsInstance(cm.exception, ValueError)
            self.assertIsNone(mod.read_json(os.path.join(self.dir.name, "nope.json")))


class SecretsInTheBot(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.cfg, self.sec = (os.path.join(self.dir.name, n) for n in ("config.json", "secrets.json"))
        write(self.cfg, json.dumps({"alerts": {}, "sealed": {"max_price": 260}, "singles": {}}))
        for p in (mock.patch.object(tb, "CONFIG_PATH", self.cfg), mock.patch.object(tb, "SECRETS_PATH", self.sec),
                  mock.patch.object(tb, "IN_ACTIONS", False), mock.patch.object(tb, "IN_CONTAINER", False),
                  mock.patch.object(tb, "SECRETS_PROBLEM", [None]), mock.patch.object(tb, "_secrets_good", [None]),
                  mock.patch.dict(os.environ, {k: "" for k in tb.ENV_ALERTS})):
            p.start()
            self.addCleanup(p.stop)

    def load(self):
        with redirect_stdout(io.StringIO()) as out:
            cfg = tb.load_config()
        return cfg, out.getvalue()

    def test_good_file_loads_and_is_remembered(self):
        write(self.sec, json.dumps({"discord_webhook_boxes": HOOK, "ntfy_topic": TOPIC}))
        cfg, _ = self.load()
        self.assertEqual(cfg["alerts"]["discord_webhook_boxes"], HOOK)
        self.assertIsNone(tb.SECRETS_PROBLEM[0])
        self.assertTrue(os.path.exists(self.sec + ".lastgood"))

    def test_typo_keeps_the_last_good_copy_and_says_so(self):
        write(self.sec, json.dumps({"discord_webhook_boxes": HOOK, "ntfy_topic": TOPIC}))
        self.load()
        write(self.sec, MISSING_COMMA)
        cfg, out = self.load()
        self.assertEqual(cfg["alerts"]["discord_webhook_boxes"], HOOK)      # alerts keep working
        self.assertIn("Line 3 is probably missing a comma", tb.SECRETS_PROBLEM[0])
        self.assertIn("using the last copy that worked", tb.SECRETS_PROBLEM[0])
        self.assertNotIn(TOPIC, tb.SECRETS_PROBLEM[0])
        self.assertIn("!!!", out)
        _, again = self.load()
        self.assertNotIn("!!!", again)                                      # printed once, not every check
        write(self.sec, json.dumps({"discord_webhook_boxes": HOOK}))
        self.load()
        self.assertIsNone(tb.SECRETS_PROBLEM[0])

    def test_typo_after_a_restart_uses_the_saved_copy(self):
        write(self.sec, json.dumps({"discord_webhook_boxes": HOOK}))
        self.load()
        tb._secrets_good[0] = None                                          # the bot restarted
        write(self.sec, MISSING_COMMA)
        cfg, _ = self.load()
        self.assertEqual(cfg["alerts"]["discord_webhook_boxes"], HOOK)

    def test_typo_with_nothing_to_fall_back_on(self):
        write(self.sec, MISSING_COMMA)
        cfg, _ = self.load()
        self.assertNotIn("discord_webhook_boxes", cfg["alerts"])
        self.assertIn("is off", tb.SECRETS_PROBLEM[0])

    def test_no_secrets_file_is_fine(self):
        self.load()
        self.assertIsNone(tb.SECRETS_PROBLEM[0])

    def test_cloud_copy_keeps_no_saved_copy(self):
        write(self.sec, json.dumps({"discord_webhook_boxes": HOOK}))
        with mock.patch.object(tb, "IN_ACTIONS", True):
            self.load()
        self.assertFalse(os.path.exists(self.sec + ".lastgood"))

    def test_config_typo_text(self):
        write(self.cfg, '{\n "alerts": {}\n "sealed": {}\n}')
        with self.assertRaises(json.JSONDecodeError) as cm:
            tb.load_config()
        self.assertIn("config.json has a typo on line 3. Line 2 is probably missing a comma", tb.typo_text(self.cfg, cm.exception))


def local_imports(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return {n for n in names if os.path.exists(os.path.join(ROOT, n + ".py"))}


class Updater(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.here = self.dir.name
        self.repo = {"update_files.txt": b"# notes\ntcg_bot.py\nnew_module.py\nrestart_bot.bat\nupdate_bot.bat\n",
                     "tcg_bot.py": b'VERSION = "9.9.9"\n', "new_module.py": b"x = 1\n",
                     "restart_bot.bat": b"@echo off\necho hi\n", "update_bot.bat": b"@echo off\r\nrem updater.py\r\n"}
        self.said = []

    def fetch(self, name):
        if name not in self.repo:
            raise OSError("404")
        return self.repo[name]

    def run_update(self, **kw):
        return up.update(self.here, self.fetch, self.said.append, **kw)

    def read(self, name):
        with open(os.path.join(self.here, name), "rb") as f:
            return f.read()

    def test_list_in_the_repo_matches_the_built_in_one(self):
        with open(os.path.join(ROOT, "update_files.txt"), encoding="utf-8") as f:
            listed = up.parse_list(f.read())
        self.assertEqual(sorted(listed), sorted(up.BUILTIN))
        for name in listed:
            self.assertTrue(os.path.exists(os.path.join(ROOT, name)), name)
            self.assertFalse(name.endswith(".json"), name)

    def test_every_module_the_bot_imports_is_listed(self):
        with open(os.path.join(ROOT, "update_files.txt"), encoding="utf-8") as f:
            listed = set(up.parse_list(f.read()))
        todo, seen = ["tcg_bot.py", "commands_bot.py", "auto_buy_host.py", "add_channels.py", "updater.py"], set()
        while todo:
            name = todo.pop()
            if name in seen:
                continue
            seen.add(name)
            self.assertIn(name, listed, f"{name} is imported by the bot but update_files.txt doesn't list it")
            todo += [m + ".py" for m in local_imports(os.path.join(ROOT, name))]
        self.assertGreater(len(seen), 20)

    def test_settings_and_running_files_can_never_be_updated(self):
        for name in ("config.json", "secrets.json", "seen.json", "run_forever.bat", "run_commands.bat",
                     "start_bot_hidden.vbs", "../x.py", "sub/x.py", "C:\\x.py", ".env", "x.exe", ""):
            self.assertFalse(up.allowed(name), name)
        self.assertEqual(up.parse_list("config.json\n../evil.py\ntcg_bot.py\ntcg_bot.py # twice\nHOW TO RUN.txt\n"),
                         ["tcg_bot.py", "HOW TO RUN.txt"])

    def test_updates_backs_up_and_reports_the_version(self):
        write(os.path.join(self.here, "tcg_bot.py"), 'VERSION = "1.0"\n')
        ok, changed, version = self.run_update()
        self.assertTrue(ok)
        self.assertEqual(version, "9.9.9")
        self.assertEqual(changed, ["tcg_bot.py", "new_module.py", "restart_bot.bat", "update_bot.bat"])
        self.assertEqual(self.read("new_module.py"), b"x = 1\n")                # a file the old list never knew
        self.assertEqual(self.read("restart_bot.bat"), b"@echo off\r\necho hi\r\n")   # Windows line endings
        self.assertEqual(self.read(os.path.join("backup-before-update", "tcg_bot.py")), b'VERSION = "1.0"\n')
        ok, changed, _ = self.run_update()
        self.assertEqual((ok, changed), (True, []))
        self.assertIn("Already up to date", self.said[-1])

    def test_all_or_nothing(self):
        write(os.path.join(self.here, "tcg_bot.py"), 'VERSION = "1.0"\n')
        self.repo["new_module.py"] = b"def broken(:\n"
        ok, changed, _ = self.run_update()
        self.assertEqual((ok, changed), (False, []))
        self.assertEqual(self.read("tcg_bot.py"), b'VERSION = "1.0"\n')
        self.assertFalse(os.path.exists(os.path.join(self.here, "new_module.py")))
        del self.repo["new_module.py"]
        self.assertFalse(self.run_update()[0])
        self.repo["new_module.py"] = b"<!DOCTYPE html><html>error</html>"
        self.assertFalse(self.run_update()[0])
        self.assertEqual(self.read("tcg_bot.py"), b'VERSION = "1.0"\n')

    def test_running_bat_gets_a_new_copy_beside_it(self):
        write(os.path.join(self.here, "update_bot.bat"), "old")
        ok, changed, _ = self.run_update(defer_bat=True)
        self.assertTrue(ok)
        self.assertEqual(self.read("update_bot.bat"), b"old")
        self.assertEqual(self.read("update_bot.bat.new"), b"@echo off\r\nrem updater.py\r\n")

    def test_falls_back_to_the_built_in_list(self):
        del self.repo["update_files.txt"]
        ok, _, _ = self.run_update()
        self.assertFalse(ok)                               # the fake repo lacks most files: nothing changed
        self.assertIn("built into the updater", self.said[0])

    def test_never_touches_settings(self):
        write(os.path.join(self.here, "config.json"), "{}")
        self.repo["update_files.txt"] += b"config.json\nsecrets.json\n"
        self.repo["config.json"] = b'{"hacked": true}'
        self.assertTrue(self.run_update()[0])
        self.assertEqual(self.read("config.json"), b"{}")

    def test_warns_about_a_settings_typo(self):
        write(os.path.join(self.here, "secrets.json"), MISSING_COMMA)
        bad = up.check_settings(self.here, self.said.append)
        self.assertEqual(len(bad), 1)
        self.assertNotIn(TOPIC, "".join(self.said))

    def test_batch_files(self):
        for name in sorted(n for n in os.listdir(ROOT) if n.endswith(".bat")):
            with open(os.path.join(ROOT, name), "rb") as f:
                raw = f.read()
            self.assertNotIn(b"\n", raw.replace(b"\r\n", b""), f"{name} needs Windows line endings")
        with open(os.path.join(ROOT, "update_bot.bat"), "rb") as f:
            bat = f.read()
        self.assertLess(len(bat), 1500)        # shorter than every older update_bot.bat, so swapping it in is safe
        self.assertIn(b"updater.py", bat)
        self.assertNotIn(b":end", bat)
        self.assertTrue(bat.rstrip().endswith(b"exit /b 1"))
        with open(os.path.join(ROOT, "restart_bot.bat"), "rb") as f:
            self.assertNotIn(b"v2.3.0", f.read())
        with open(os.path.join(ROOT, ".gitattributes"), encoding="utf-8") as f:
            self.assertIn("*.bat -text", f.read())


NOW = datetime(2026, 11, 19, 15, 2)
EVE = {"name": "OP-18 eve", "start": "2026-11-19 18:00", "end": "2026-11-19 23:59", "every_seconds": 60}
DAY = {"name": "OP-18 release day", "start": "2026-11-20 08:00", "end": "2026-11-20 14:00", "every_seconds": 60}


def listing(shop, handle, name, available=False, price=0.0, group="box", mx=260.0):
    return {"id": f"list|{shop}|{handle}", "box_id": f"box|{shop}|{handle}", "group": group, "kind": "New listing",
            "name": name, "shop": shop, "price": price, "available": available,
            "url": f"https://{shop.lower().replace(' ', '')}.test/products/{handle}", "cart": "", "note": "", "max": mx,
            "page": 1}


class Rehearsal(unittest.TestCase):
    def setUp(self):
        self.posts, self.controls = [], {}
        self.cfg = {"drop_windows": [EVE, DAY], "auto_drop_windows": False, "pokemon": False,
                    "alerts": {"ntfy_topic": "t"}, "sealed": {"max_price": 260}}
        self.by_shop = {
            "Gameology": [listing("Gameology", "op18", "One Piece OP-18 Booster Box", True, 259.95)],
            "TCGroup": [listing("TCGroup", "op18", "One Piece OP18 Booster Box", True, 499.99)],
            "Pokebox": [listing("Pokebox", "op-18", "ONE PIECE OP-18 Booster Box"),
                        listing("Pokebox", "op-16", "ONE PIECE OP-16 Booster Box", True, 219.99)],
            "Gumnut": [listing("Gumnut", "op-10", "One Piece OP-10 Booster Box")],
            "Good Games": [],
            "Pocket Games": None, "Rogue Online": None, "Mayhem": None}
        hosts = {"pocketgames.com.au": "Pocket Games", "rogueonline.com.au": "Rogue Online", "mayhem.test": "Mayhem"}
        fake_ng = mock.Mock()
        fake_ng.watch_list.return_value = [{"name": "Pocket Games", "host": "pocketgames.com.au", "needs_you": True}]
        fake_http = mock.Mock()
        fake_http.cooling.return_value = {"rogueonline.com.au": 300.0}
        for p in (mock.patch.object(tb, "IN_ACTIONS", False), mock.patch.object(tb, "netguard", fake_ng),
                  mock.patch.object(tb, "HTTP", fake_http), mock.patch.object(tb, "shop_names", return_value=hosts),
                  mock.patch.object(tb, "read_controls", side_effect=lambda: dict(self.controls)),
                  mock.patch.object(tb, "SECRETS_PROBLEM", [None]), mock.patch.object(tb, "CONFIG_WARNINGS", []),
                  mock.patch.object(tb, "auto_buy", None),
                  mock.patch.object(tb.fast_lane.lw, "load", return_value=[]),
                  mock.patch.object(tb, "post_status", side_effect=lambda c, text, color=None: self.posts.append((text, color)))):
            p.start()
            self.addCleanup(p.stop)

    def test_due_once_three_hours_before_the_eve_window(self):
        st = {}
        self.assertIsNone(rh.due(tb, self.cfg, st, datetime(2026, 11, 19, 14, 59)))
        w = rh.due(tb, self.cfg, st, NOW)
        self.assertEqual(w["name"], "OP-18 eve")
        rh.mark(st, w, NOW)
        self.assertIsNone(rh.due(tb, self.cfg, st, NOW + timedelta(minutes=5)))
        self.assertIsNone(rh.due(tb, self.cfg, st, datetime(2026, 11, 19, 18, 5)))      # window is on

    def test_release_morning_gets_no_card_of_its_own(self):
        for t in (datetime(2026, 11, 20, 5, 30), datetime(2026, 11, 20, 7, 55)):
            self.assertIsNone(rh.due(tb, self.cfg, {}, t))

    def test_not_on_the_cloud_copy_and_can_be_switched_off(self):
        with mock.patch.object(tb, "IN_ACTIONS", True):
            self.assertIsNone(rh.due(tb, self.cfg, {}, NOW))
        self.assertIsNone(rh.due(tb, dict(self.cfg, alerts={"heartbeat_topic": "x", "heartbeat_role": "listen"}), {}, NOW))
        self.assertIsNone(rh.due(tb, dict(self.cfg, drop_rehearsal=False), {}, NOW))
        self.assertEqual(tb.check_config(dict(self.cfg, drop_rehearsal=False, singles={})), [])

    def test_a_pokemon_window_is_left_alone(self):
        cfg = dict(self.cfg, drop_windows=[dict(EVE, game="pokemon")])
        self.assertIsNone(rh.due(tb, cfg, {}, NOW))

    def test_survey(self):
        w = rh.due(tb, self.cfg, {}, NOW)
        s = rh.survey(tb, self.cfg, w, self.by_shop)
        self.assertEqual(s["codes"], ["OP-18"])
        self.assertEqual(s["listing"], [("Gameology", "buyable", 259.95), ("Pokebox", "not buyable yet", 0.0),
                                        ("TCGroup", "over max", 499.99)])
        self.assertEqual(s["ready"], ["Good Games", "Gumnut"])
        self.assertEqual(dict(s["blocked"]), {"Pocket Games": "asked for human verification",
                                              "Rogue Online": "asked the bot to slow down", "Mayhem": "didn't load"})

    def test_card(self):
        w = rh.due(tb, self.cfg, {}, NOW)
        text, colour = rh.build(tb, self.cfg, w, self.by_shop, NOW)
        self.assertEqual(colour, tb.AMBER)
        for part in ("Drop rehearsal: OP-18 eve", "Thu 19 Nov 06:00 PM", "in about 3 h", "read 5 of 8 shops",
                     "Already listing OP-18 (3)", "Gameology (buyable now, $259.95)", "TCGroup (in stock, over your max",
                     "Pokebox (listed, not buyable yet)", "Ready (2, no OP-18 listing yet",
                     "asked for human verification (1):** Pocket Games", "asked the bot to slow down (1):** Rogue Online",
                     "didn't load (1):** Mayhem", "won't get round", "Fast lane: 3 target(s)", "Desk mode: **off for the window**",
                     "Phone alerts: on"):
            self.assertIn(part, text)
        self.assertNotIn("Nothing needs doing", text)

    def test_all_clear_card(self):
        self.controls["desk_until"] = datetime(2026, 11, 20, 2, 0).timestamp()
        ok = {k: v for k, v in self.by_shop.items() if v is not None}
        w = rh.due(tb, self.cfg, {}, NOW)
        text, colour = rh.build(tb, self.cfg, w, ok, NOW)
        self.assertEqual(colour, tb.GREEN)
        self.assertIn("Nothing needs doing", text)
        self.assertIn("Desk mode: on until Fri 02:00 AM", text)
        self.assertIn("read 5 of 5 shops", text)

    def test_card_mentions_a_broken_secrets_file(self):
        w = rh.due(tb, self.cfg, {}, NOW)
        with mock.patch.object(tb, "SECRETS_PROBLEM", ["secrets.json has a typo on line 4."]):
            text, colour = rh.build(tb, self.cfg, w, {"Gumnut": []}, NOW)
        self.assertIn("secrets.json won't load", text)
        self.assertEqual(colour, tb.AMBER)

    def test_maybe_post_posts_once(self):
        st = {}
        self.assertIsNone(rh.maybe_post(tb, self.cfg, st, {}, NOW))               # nothing read: wait for a real check
        self.assertEqual(rh.maybe_post(tb, self.cfg, st, self.by_shop, NOW)["name"], "OP-18 eve")
        self.assertIsNone(rh.maybe_post(tb, self.cfg, st, self.by_shop, NOW + timedelta(minutes=5)))
        self.assertEqual(len(self.posts), 1)
        self.assertIn("OP-18 eve|2026-11-19 18:00", st["rehearsed"])

    def test_next_window_for_the_command(self):
        self.assertEqual(rh.next_window(tb, self.cfg, NOW)["name"], "OP-18 eve")
        self.assertEqual(rh.next_window(tb, self.cfg, NOW, "release")["name"], "OP-18 release day")
        self.assertIsNone(rh.next_window(tb, self.cfg, NOW, "EB-06"))


if __name__ == "__main__":
    unittest.main()
