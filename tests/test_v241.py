"""v2.4.1: memory files keep a last good copy, a phone push when Discord stops taking posts, and /missed.
No network.

Run:  python -m unittest discover -s tests
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402
import misses as ms  # noqa: E402

BOXES = "https://discord.com/api/webhooks/1/aaa"
SINGLES = "https://discord.com/api/webhooks/2/bbb"


class Backups(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "price_history.json")
        tb.RESTORED.clear()
        tb.DRY_RUN[0] = False

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        tb.RESTORED.clear()

    def test_previous_version_is_kept(self):
        tb.atomic_write_json(self.path, {"v": 1})
        self.assertFalse(os.path.exists(self.path + ".bak"))      # nothing to back up the first time
        tb.atomic_write_json(self.path, {"v": 2})
        self.assertEqual(json.load(open(self.path + ".bak")), {"v": 1})
        self.assertEqual(tb.read_json(self.path), {"v": 2})

    def test_damaged_file_loads_last_good_copy(self):
        tb.atomic_write_json(self.path, {"v": 1})
        tb.atomic_write_json(self.path, {"v": 2})
        with open(self.path, "w") as f:
            f.write('{"v": 2, "points": [[')                     # cut off half way
        self.assertEqual(tb.read_json(self.path, {}), {"v": 1})
        self.assertEqual([n for n, _ in tb.RESTORED], ["price_history.json"])
        self.assertTrue(os.path.exists(self.path + ".damaged"))
        self.assertEqual(json.load(open(self.path)), {"v": 1})   # the good copy is put back in place

    def test_damaged_file_never_overwrites_the_backup(self):
        tb.atomic_write_json(self.path, {"v": 1})
        tb.atomic_write_json(self.path, {"v": 2})                # .bak = v1
        with open(self.path, "w") as f:
            f.write("garbage")
        tb.atomic_write_json(self.path, {"v": 3})                # garbage isn't copied over the good .bak
        self.assertEqual(json.load(open(self.path + ".bak")), {"v": 1})

    def test_deleted_file_is_not_brought_back(self):
        tb.atomic_write_json(self.path, {"v": 1})
        tb.atomic_write_json(self.path, {"v": 2})
        os.remove(self.path)                                     # deleting it on purpose resets it
        self.assertEqual(tb.read_json(self.path, {}), {})

    def test_other_files_get_no_backup(self):
        p = os.path.join(self.dir, "latest.json")
        tb.atomic_write_json(p, {"v": 1})
        tb.atomic_write_json(p, {"v": 2})
        self.assertFalse(os.path.exists(p + ".bak"))
        with open(p, "w") as f:
            f.write("garbage")
        self.assertEqual(tb.read_json(p, {"empty": True}), {"empty": True})

    def test_dry_run_writes_nothing(self):
        tb.DRY_RUN[0] = True
        try:
            tb.atomic_write_json(self.path, {"v": 1})
        finally:
            tb.DRY_RUN[0] = False
        self.assertFalse(os.path.exists(self.path))


class DiscordHealth(unittest.TestCase):
    def setUp(self):
        self.pushes, self.posts = [], []
        self._push, self._post = tb.push_phone, tb.post_status
        tb.push_phone = lambda cfg, title, body: self.pushes.append((title, body))
        tb.post_status = lambda cfg, text, color=None: self.posts.append(text)
        self.cfg = {"alerts": {"discord_webhook_boxes": BOXES, "discord_webhook_singles": SINGLES,
                               "ntfy_topic": "lee-phone"}}
        self.status = {}

    def tearDown(self):
        tb.push_phone, tb.post_status = self._push, self._post
        tb._hook_results.clear()

    def check(self, *results):
        tb._hook_results.clear()
        for hook, ok, err, code in results:
            tb._note_hook(hook, ok, err, code)
        return tb.discord_health(self.cfg, self.status)

    def test_deleted_webhook_warns_straight_away(self):
        failing = self.check((BOXES, False, "HTTP 404: Unknown Webhook", 404), (SINGLES, True, "", None))
        self.assertEqual([k for k, _ in failing], ["discord_webhook_boxes"])
        self.assertEqual(len(self.pushes), 1)
        self.assertIn("#booster-boxes", self.pushes[0][1])
        self.assertIn("doesn't exist any more", self.pushes[0][1])

    def test_server_errors_warn_after_three_checks(self):
        for _ in range(2):
            self.check((BOXES, False, "HTTP 503", None))
        self.assertEqual(self.pushes, [])
        self.check((BOXES, False, "HTTP 503", None))
        self.assertEqual(len(self.pushes), 1)
        self.check((BOXES, False, "HTTP 503", None))
        self.assertEqual(len(self.pushes), 1)                    # one push, not one per check

    def test_recovery_says_so_and_clears(self):
        self.check((BOXES, False, "HTTP 404", 404))
        self.check((BOXES, True, "", None))
        self.assertEqual(len(self.pushes), 2)
        self.assertIn("working again", self.pushes[1][0])
        self.assertTrue(any("again" in p for p in self.posts))
        self.assertEqual(self.status["discord_health"], {})

    def test_a_good_post_in_the_same_check_counts_as_working(self):
        self.check((BOXES, False, "HTTP 503", None), (BOXES, True, "", None))
        self.assertEqual(self.status["discord_health"], {})

    def test_webhook_addresses_never_saved(self):
        self.check((BOXES, False, "HTTP 404", 404))
        self.assertNotIn("discord.com", json.dumps(self.status))

    def test_pokemon_channel_named(self):
        self.cfg["alerts"]["pokemon_webhooks"] = {"mega-evolution": "https://discord.com/api/webhooks/3/ccc"}
        self.check(("https://discord.com/api/webhooks/3/ccc", False, "HTTP 404", 404))
        self.assertIn("pokemon:mega-evolution", self.status["discord_health"])
        self.assertIn("Pokémon mega-evolution", self.pushes[0][1])


GUMNUT = "https://www.gumnut.com.au/products/op-18-booster-box"
NOW = 1_800_000_000


def mem(hist=None, events=(), known=None, drops=None):
    return {"hist": [hist or {}], "known": [known or {}], "drops": [drops or {}], "events": list(events)}


class Missed(unittest.TestCase):
    def setUp(self):
        self.cfg = {"sealed": {"max_price": 260, "shopify_collections": [
                        {"name": "Gumnut", "url": "https://www.gumnut.com.au/collections/one-piece/products.json"}]},
                    "singles": {"shops": {"Good Games": "https://tcg.goodgames.com.au"}, "cards": []},
                    "extra_shops": False}
        self._look = ms.live_look

    def tearDown(self):
        ms.live_look = self._look

    def explain(self, link, m, reported=NOW, live=False):
        return ms.explain(tb, self.cfg, link, reported=reported, remote=False, live=live, mem=m)

    def hist(self, avail=True, price=249.0, key="box|Gumnut|op-18-booster-box", first=NOW - 3600):
        return {key: {"name": "One Piece OP-18 Booster Box", "shop": "Gumnut", "url": GUMNUT,
                      "points": [["2026-10-22", price, avail]], "avail": avail, "since": first, "first": first}}

    def test_link_cleanup(self):
        self.assertEqual(ms.clean_link("<https://www.Gumnut.com.au/products/x/?variant=5>"),
                         ("gumnut.com.au", "/products/x"))
        self.assertEqual(ms.clean_link("check this gumnut.com.au/collections/op/products/x"),
                         ("gumnut.com.au", "/collections/op/products/x"))
        self.assertEqual(ms.handle_of("/collections/op/products/X-Y"), "x-y")
        self.assertEqual(ms.clean_link("nope"), (None, None))

    def test_bot_was_first(self):
        ev = [{"t": NOW - 600, "event": "alert", "url": GUMNUT + "?variant=1"}]
        r = self.explain(GUMNUT, mem(self.hist(), ev))
        self.assertEqual(r["kind"], "first")
        self.assertIn("10 min before", r["headline"])

    def test_bot_was_late(self):
        ev = [{"t": NOW + 900, "event": "alert", "url": GUMNUT}]
        r = self.explain(GUMNUT, mem(self.hist(), ev))
        self.assertEqual((r["kind"], r["late_min"]), ("late", 15))
        self.assertIn("seen the listing earlier", r["lines"][0])

    def test_seen_but_over_max(self):
        r = self.explain(GUMNUT, mem(self.hist(price=399.0)))
        self.assertEqual(r["kind"], "seen")
        self.assertIn("over your $260.00 max", r["headline"])

    def test_seen_but_not_buyable(self):
        r = self.explain(GUMNUT, mem(self.hist(avail=False)))
        self.assertIn("not buyable", r["headline"])

    def test_seen_in_the_all_sealed_group(self):
        r = self.explain(GUMNUT, mem(self.hist(key="item|Gumnut|op-18-booster-box")))
        self.assertIn("all sealed", r["headline"])

    def test_known_listing_without_history(self):
        r = self.explain(GUMNUT, mem(known={"Gumnut (all sealed)": ["list|Gumnut|op-18-booster-box"]}))
        self.assertEqual(r["kind"], "seen")

    def test_single_at_a_singles_shop(self):
        link = "https://tcg.goodgames.com.au/products/sabo-sp"
        r = self.explain(link, mem(drops={"items": {"Good Games|sabo-sp": {"n": "Sabo", "p": [[NOW, 5.0, 1]]}}}))
        self.assertEqual(r["kind"], "seen")
        self.assertIn("want list", r["headline"])

    def test_shop_not_watched(self):
        ms.live_look = lambda tb_, host, handle: {"title": "x", "available": True, "price": 1, "variants": []}
        r = self.explain("https://newshop.com.au/products/op-18", mem(), live=True)
        self.assertEqual(r["kind"], "not_watched")
        self.assertIn("Shopify", r["lines"][0])

    def test_filtered_out_says_why(self):
        ms.live_look = lambda tb_, host, handle: {"title": "One Piece Card Game Japanese Booster Box OP-18",
                                                  "available": True, "price": 150, "variants": []}
        r = self.explain("https://www.gumnut.com.au/products/jp-op18", mem(), live=True)
        self.assertEqual(r["kind"], "filtered")
        self.assertIn("japanese", r["headline"])

    def test_watched_but_never_seen(self):
        ms.live_look = lambda tb_, host, handle: {"title": "One Piece Card Game Premium Card Collection Vol. 4",
                                                  "available": False, "price": 90, "variants": []}
        r = self.explain("https://www.gumnut.com.au/products/pcc-4", mem(), live=True)
        self.assertEqual(r["kind"], "not_found")

    def test_skip_reasons(self):
        cfg = {}
        self.assertIsNone(ms.skip_reason(tb, cfg, "One Piece Card Game OP-18 Booster Box"))
        self.assertIn("sleeve", ms.skip_reason(tb, cfg, "One Piece Card Game Official Sleeves Luffy"))
        self.assertIn("pack", ms.skip_reason(tb, cfg, "One Piece Booster Pack OP-14"))
        self.assertIn("single", ms.skip_reason(tb, cfg, "Sabo OP13-120 SEC One Piece Card Game"))

    def test_log_and_summary(self):
        d = tempfile.mkdtemp()
        here = tb.HERE
        tb.HERE = d
        try:
            for k, late in (("late", 12), ("late", 30), ("not_watched", None)):
                ms.record(tb, {"kind": k, "host": "kmart.com.au", "late_min": late, "link": "x"}, "lee", "Fellowship")
            head, lines = ms.summary(tb)
            self.assertIn("3 miss", head)
            self.assertTrue(any("timing" in line for line in lines))
            self.assertTrue(os.path.exists(os.path.join(d, "misses.json")))
        finally:
            tb.HERE = here
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
