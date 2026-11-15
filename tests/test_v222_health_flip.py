"""v2.22: the PC copy's health reaches the cloud copy (version + hours), a market line and flip estimate on
booster-box alerts and /flip, and eBay alerts at a % under market. No network."""
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import ebay_watch as ew  # noqa: E402
import flip  # noqa: E402
import tcg_bot as tb  # noqa: E402

NOW = time.time()
STORE = {"v": 1, "synced": NOW - 3600, "fx": {"rate": 1.5},
         "groups": {"1": {"a": "OP18", "n": "The Dominance of God"}, "2": {"a": "PRB-02", "n": "Premium Booster 2"},
                    "3": {"a": "OP14-EB04", "n": "Azure"}, "4": {"a": "OP01", "n": "Romance Dawn"},
                    "5": {"a": "OP13", "n": "Carrying On His Will"}},
         "items": {"1001": {"n": "The Dominance of God Booster Box", "g": "1", "t": "sealed", "m": 200.0},
                   "1002": {"n": "The Dominance of God Booster Box Case", "g": "1", "t": "sealed", "m": 2400.0},
                   "1003": {"n": "Premium Booster Vol. 2 - Booster Box", "g": "2", "t": "sealed", "m": 350.0},
                   "1004": {"n": "The Azure Sea's Seven Booster Box", "g": "3", "t": "sealed", "m": 250.0},
                   "1005": {"n": "Romance Dawn - Booster Box (Wave 2 - White)", "g": "4", "t": "sealed", "m": 1300.0},
                   "1006": {"n": "Romance Dawn - Booster Box (Wave 1 - Blue)", "g": "4", "t": "sealed", "m": 9000.0},
                   "1007": {"n": "Sleeved Booster Box thing", "g": "5", "t": "sealed", "m": 5.0},
                   "1008": {"n": "Carrying On His Will Booster Box", "g": "5", "t": "sealed", "m": None},
                   "2001:Normal": {"n": "Sabo (120)", "g": "5", "t": "card", "m": 40.0}}}


class Matching(unittest.TestCase):
    def test_codes(self):
        self.assertEqual(flip.codes_in("One Piece OP-18 Booster Box"), ["OP18"])
        self.assertEqual(flip.codes_in("[eb 05] box / PRB02 / op9"), ["EB05", "PRB02", "OP09"])
        self.assertEqual(flip.codes_in("TOP18 thing, OP-180, shop123"), [])

    def test_box_market(self):
        m = flip.box_market(STORE, "op-18")
        self.assertEqual((m["key"], m["usd"], m["aud"], m["code"]), ("1001", 200.0, 300.0, "OP18"))   # the box, not the case
        self.assertEqual(flip.box_market(STORE, "PRB-02")["key"], "1003")
        self.assertEqual(flip.box_market(STORE, "OP14")["key"], "1004")
        self.assertIsNone(flip.box_market(STORE, "EB-04"))         # shares a TCGplayer set with OP-14: not guessed
        self.assertEqual(flip.box_market(STORE, "OP-01")["key"], "1005")   # two print waves: the cheaper one
        self.assertIsNone(flip.box_market(STORE, "OP-13"))         # no market price yet
        self.assertIsNone(flip.box_market(STORE, "OP-99"))
        self.assertIsNone(flip.box_market({}, "OP-18"))

    def test_only_one_plain_english_box_gets_a_market(self):
        for name in ("Bandai One Piece Card Game: The Dominance of God [OP-18] - Booster Box",
                     "One Piece OP18 Booster Display (English)", "ONE PIECE CG OP-18 Booster Box (24 Packs) PRE-ORDER"):
            self.assertEqual(flip.listing_market(STORE, name)["key"], "1001", name)
        for name in ("OP-18 Booster Box – Japanese One Piece TCG", "One Piece OP-18 Booster Box [JP]",
                     "OP-18 Booster Box Case (12 Boxes)", "OP-18 Booster Pack", "OP-18 Booster Box x2",
                     "OP-18 + EB-05 Booster Box", "One Piece Booster Box", "OP-18 Booster Box pre-order deposit",
                     "OP-18 Double Pack Set", "OP-99 Booster Box"):
            self.assertIsNone(flip.listing_market(STORE, name), name)

    def test_lookup(self):
        self.assertEqual(flip.lookup(STORE, "OP-18")["key"], "1001")
        self.assertEqual(flip.lookup(STORE, "1003")["usd"], 350.0)
        self.assertEqual(flip.lookup(STORE, "2001")["key"], "2001:Normal")
        self.assertIsNone(flip.lookup(STORE, "999999"))
        self.assertIsNone(flip.lookup(STORE, ""))


class TheSum(unittest.TestCase):
    def test_settings(self):
        self.assertEqual(flip.settings({}), {"ebay_fee_pct": 0.0, "fixed_fee": 0.0, "postage": 12.0})
        self.assertIsNone(flip.settings({"flip": False}))
        self.assertEqual(flip.settings({"flip": {"ebay_fee_pct": 13.4, "fixed_fee": 0.3, "postage": "9"}}),
                         {"ebay_fee_pct": 13.4, "fixed_fee": 0.3, "postage": 9.0})
        self.assertEqual(flip.settings({"flip": {"postage": -1, "ebay_fee_pct": "x"}}), flip.settings({}))
        self.assertEqual(flip.warnings({}), [])
        self.assertEqual(flip.warnings({"flip": False}), [])
        self.assertEqual(len(flip.warnings({"flip": {"postage": -1}})), 1)
        self.assertEqual(len(flip.warnings({"flip": "yes"})), 1)
        self.assertFalse([w for w in tb.check_config({"singles": {}, "sealed": {}, "flip": {"postage": 10}}) if "flip" in w])

    def test_free_selling(self):
        e = flip.estimate(300.0, 215.0, flip.settings({}))
        self.assertEqual((e["fee"], e["keep"], e["profit"], e["break_even"]), (0.0, 288.0, 73.0, 288.0))
        self.assertAlmostEqual(e["pct"], 34.0, places=1)

    def test_pro_plan_fees(self):
        e = flip.estimate(300.0, 260.0, flip.settings({"flip": {"ebay_fee_pct": 13.4, "fixed_fee": 0.3}}))
        self.assertEqual(e["fee"], 40.5)
        self.assertEqual(e["profit"], -12.5)

    def test_alert_field(self):
        f = flip.alert_field({}, "One Piece OP-18 Booster Box", 215.0, store=STORE, now=NOW)
        self.assertEqual(f["name"], "Market")
        for part in ("US market ≈ A$300.00", "tcgplayer.com/product/1001", "US$200.00", "+A$73.00 (+34%)",
                     "no eBay fee, $12.00 postage", "Estimate"):
            self.assertIn(part, f["value"])
        loss = flip.alert_field({}, "One Piece OP-18 Booster Box", 320.0, store=STORE, now=NOW)["value"]
        self.assertIn("−A$32.00 (-10%)", loss)
        self.assertNotIn("Resold", flip.alert_field({}, "OP-18 Booster Box", None, store=STORE, now=NOW)["value"])

    def test_no_field_when_unsure(self):
        self.assertIsNone(flip.alert_field({"flip": False}, "OP-18 Booster Box", 215, store=STORE, now=NOW))
        self.assertIsNone(flip.alert_field({}, "OP-18 Booster Box Japanese", 215, store=STORE, now=NOW))
        self.assertIsNone(flip.alert_field({}, "OP-18 Booster Box", 215, store={}, now=NOW))
        old = dict(STORE, synced=NOW - 8 * 86400)
        self.assertIsNone(flip.alert_field({}, "OP-18 Booster Box", 215, store=old, now=NOW))    # week-old prices

    def test_report_for_the_command(self):
        title, lines = flip.report({}, "op18", 215, store=STORE, now=NOW)
        text = "\n".join(lines)
        self.assertEqual(title, "The Dominance of God Booster Box (OP18)")
        for part in ("A$300.00", "Buying at A$215.00:** +A$73.00", "Break-even buy price:** A$288.00", "not an Australian sold price"):
            self.assertIn(part, text)
        _, lines = flip.report({}, "OP-18", None, store=STORE, now=NOW)
        self.assertNotIn("Buying at", "\n".join(lines))
        title, lines = flip.report({}, "sabo", 5, store=STORE, now=NOW)
        self.assertIn("No market price", title)
        self.assertIn("No price data", flip.report({}, "OP-18", 5, store={}, now=NOW)[0])
        _, lines = flip.report({}, "OP-18", None, store=dict(STORE, synced=NOW - 4 * 86400), now=NOW)
        self.assertIn("4 days old", lines[-1])


class InTheAlert(unittest.TestCase):
    def find(self, **kw):
        f = {"id": "box|Gameology|op18", "kind": "Booster box", "name": "One Piece OP-18 Booster Box", "shop": "Gameology",
             "price": 215.0, "url": "https://g.test/p", "cart": "", "note": ""}
        f.update(kw)
        return f

    def fields(self, f, cfg=None):
        with mock.patch.object(flip, "load_store", return_value=STORE), mock.patch.object(tb, "read_json", return_value={}):
            return {x["name"]: x["value"] for x in tb._discord_embeds([f], cfg or {})[0]["fields"]}

    def test_box_alert_gets_the_market_line(self):
        self.assertIn("+A$73.00", self.fields(self.find())["Market"])

    def test_new_listing_with_a_price_too(self):
        self.assertIn("Market", self.fields(self.find(kind="New listing")))
        self.assertNotIn("Market", self.fields(self.find(kind="New listing", price=0.0)))

    def test_not_on_singles_watched_links_or_when_off(self):
        self.assertNotIn("Market", self.fields(self.find(kind="Single", qty=1)))
        self.assertNotIn("Market", self.fields(self.find(link_watch=True)))
        self.assertNotIn("Market", self.fields(self.find(), {"flip": False}))
        self.assertNotIn("Market", self.fields(self.find(name="One Piece OP-18 Booster Box (Japanese)")))


class Refresh(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "tcgplayer_prices.json")
        self.remote = dict(STORE, synced=NOW - 60)
        self.asked = []
        for p in (mock.patch.object(flip, "PATH", self.path), mock.patch.object(tb, "IN_ACTIONS", False),
                  mock.patch.object(tb, "repo_json", side_effect=lambda c, n, max_age=0: self.asked.append(n) or self.remote),
                  mock.patch.dict(flip._cache, {"path": None, "mtime": None, "store": None})):
            p.start()
            self.addCleanup(p.stop)

    def write(self, store):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(store, f)

    def test_fresh_local_file_is_used_without_asking(self):
        self.write(STORE)
        self.assertEqual(flip.refresh(tb, {})["synced"], STORE["synced"])
        self.assertEqual(self.asked, [])

    def test_stale_or_missing_file_takes_the_repo_copy(self):
        self.assertEqual(flip.refresh(tb, {})["synced"], self.remote["synced"])
        self.assertTrue(os.path.exists(self.path))
        self.assertEqual(flip.load_store()["synced"], self.remote["synced"])
        self.write(dict(STORE, synced=NOW - 3 * 86400))
        flip._cache.update(path=None)
        self.assertEqual(flip.refresh(tb, {})["synced"], self.remote["synced"])

    def test_cloud_copy_never_asks_and_a_bad_repo_copy_is_ignored(self):
        with mock.patch.object(tb, "IN_ACTIONS", True):
            self.assertEqual(flip.refresh(tb, {}), {})
        self.assertEqual(self.asked, [])
        self.remote = None
        self.assertEqual(flip.refresh(tb, {}), {})
        self.assertFalse(os.path.exists(self.path))


class EbayUnderMarket(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "ebay_watch.json")
        for p in (mock.patch.object(flip, "load_store", return_value=STORE), mock.patch.object(ew, "_said", set(), create=True),
                  mock.patch.object(ew, "_say_once", side_effect=lambda t: self.said.append(t))):
            p.start()
            self.addCleanup(p.stop)
        self.said = []

    def cards(self, *entries):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"cards": [dict({"name": "x", "search": ["x"]}, **e) for e in entries]}, f)
        return ew.load_watch(self.path)[0]

    def test_max_follows_the_market(self):
        c = self.cards({"under_market_pct": 20, "market_tcgplayer": "OP-18"})[0]
        self.assertEqual((c["max"], c["market"], c["under_pct"]), (240.0, 300.0, 20.0))

    def test_typed_market_and_the_lower_of_max_and_target(self):
        c = self.cards({"under_market_pct": 10, "market_aud": 650})[0]
        self.assertEqual(c["max"], 585.0)
        self.assertEqual(self.cards({"under_market_pct": 10, "market_aud": 650, "max": 500})[0]["max"], 500.0)
        self.assertEqual(self.cards({"under_market_pct": 10, "market_aud": 650, "max": 900})[0]["max"], 585.0)

    def test_no_market_falls_back_to_max_or_is_skipped(self):
        c = self.cards({"under_market_pct": 20, "market_tcgplayer": "OP-99", "max": 100})[0]
        self.assertEqual((c["max"], c["market"], c["under_pct"]), (100.0, None, None))
        self.assertEqual(self.cards({"under_market_pct": 20, "market_tcgplayer": "OP-99"}), [])
        self.assertIn("no market price could be found", self.said[-1])
        with mock.patch.object(flip, "load_store", return_value=dict(STORE, synced=NOW - 9 * 86400)):
            self.assertEqual(self.cards({"under_market_pct": 20, "market_tcgplayer": "OP-18"}), [])   # stale prices

    def test_plain_max_is_unchanged_and_bad_pct_is_ignored(self):
        c = self.cards({"max": 550})[0]
        self.assertEqual((c["max"], c["market"], c["under_pct"]), (550.0, None, None))
        c = self.cards({"max": 550, "market_aud": 650})[0]              # a market with no % does nothing
        self.assertEqual((c["max"], c["market"]), (550.0, None))
        c = self.cards({"max": 550, "under_market_pct": 150, "market_aud": 650})[0]
        self.assertEqual(c["max"], 550.0)
        self.assertIn("between", self.said[-1])

    def test_alert_says_how_far_under(self):
        card = self.cards({"under_market_pct": 20, "market_tcgplayer": "OP-18"})[0]
        f = ew.make_find(card, {"itemId": "v1|1|0", "title": "OP-18 box", "itemWebUrl": "https://www.ebay.com.au/itm/1"},
                         (210.0, 15.0, 0.0, 225.0))
        self.assertIn("25% under the market price of A$300.00", f["note"])
        plain = ew.make_find(self.cards({"max": 550})[0], {"itemId": "v1|2|0", "title": "x"}, (1.0, 0.0, 0.0, 1.0))
        self.assertNotIn("under the market", plain["note"])


def ntfy(msgs):
    return "\n".join(json.dumps({"event": "message", "time": t, "message": m}) for t, m in msgs).encode()


class PcHealth(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.up = os.path.join(self.dir.name, "uptime.json")
        self.feed = b""
        self.urls = []
        fake = mock.Mock()
        fake.fetch.side_effect = lambda url, **k: self.urls.append(url) or self.feed
        fake.post.side_effect = lambda url, body, headers=None: self.urls.append(body) or (200, {}, b"")
        for p in (mock.patch.object(tb, "HTTP", fake), mock.patch.object(tb, "UPTIME_PATH", self.up),
                  mock.patch.object(tb, "DRY_RUN", [False]), mock.patch.object(tb, "_last_heartbeat", 0),
                  mock.patch.dict(tb.PC_HEALTH, {"version": "", "hours": set(), "last": None}),
                  mock.patch.dict(tb.PC_INFO, {"pokemon": False, "posted": set()})):
            p.start()
            self.addCleanup(p.stop)
        self.cfg = {"alerts": {"heartbeat_topic": "t"}}

    def test_pc_says_its_version(self):
        tb.send_heartbeat(self.cfg, force=True, status={})
        self.assertEqual(self.urls[-1], f"pc-on v={tb.VERSION}".encode())
        self.assertEqual(tb.heartbeat_body(self.cfg, {}), "pc-on")           # the part older cloud copies read is unchanged

    def test_cloud_reads_version_and_hours(self):
        t = time.time()
        self.feed = ntfy([(t - 5 * 3600, "pc-on v=2.21.0"), (t - 2 * 3600, "pc-on pokemon v=2.22.0"), (t - 60, "pc-on pokemon r=a|day v=2.22.0")])
        self.assertAlmostEqual(tb.pc_last_seen(self.cfg), t - 60, delta=1)
        self.assertIn("since=6h", self.urls[0])
        self.assertEqual(tb.PC_HEALTH["version"], "2.22.0")
        self.assertEqual(len(tb.PC_HEALTH["hours"]), 3)
        self.assertEqual(tb.PC_INFO, {"pokemon": True, "posted": {"a|day"}})     # only the last 20 minutes, as before

    def test_pc_heard_hours_ago_is_off_but_its_hours_still_count(self):
        t = time.time()
        self.feed = ntfy([(t - 3 * 3600, "pc-on pokemon r=old|day v=2.22.0")])
        self.assertIsNone(tb.pc_last_seen(self.cfg))
        self.assertEqual(len(tb.PC_HEALTH["hours"]), 1)
        self.assertEqual(tb.PC_INFO, {"pokemon": False, "posted": set()})
        self.feed = b""
        self.assertIsNone(tb.pc_last_seen(self.cfg))
        self.assertEqual(tb.PC_HEALTH["hours"], set())
        self.assertEqual(tb.PC_HEALTH["version"], "2.22.0")                  # the last version heard is kept

    def test_an_old_pc_copy_and_junk_versions(self):
        t = time.time()
        self.feed = ntfy([(t - 30, "pc-on pokemon")])
        self.assertIsNotNone(tb.pc_last_seen(self.cfg))
        self.assertEqual(tb.PC_HEALTH["version"], "")
        self.feed = ntfy([(t - 30, "pc-on v=<script>alert(1)</script>")])
        tb.pc_last_seen(self.cfg)
        self.assertEqual(tb.PC_HEALTH["version"], "")

    def test_copies_health_lines(self):
        now = 1_800_000_000 - 1_800_000_000 % 3600 + 600         # ten minutes into an hour
        for h in range(1, 20):
            tb.mark_uptime(now=now - h * 3600, copy="pc")
        for h in (0, 1, 2, 3, 30):
            tb.mark_uptime(now=now - h * 3600, copy="cloud")
        with mock.patch.object(tb, "IN_ACTIONS", False):
            pc, cloud = tb.copies_health({}, now=now, remote=False)
        self.assertEqual(pc, f"PC v{tb.VERSION}: checked in 19 of the last 24 hours · last heard last hour (this one)")
        self.assertEqual(cloud, "Cloud: checked in 3 of the last 24 hours · last heard this hour")
        with mock.patch.object(tb, "IN_ACTIONS", True), \
                mock.patch.object(tb, "repo_json", side_effect=lambda c, n, max_age=0: {"pc_version": "2.21.0"} if n == "status.json" else {}):
            pc, cloud = tb.copies_health({}, now=now + 5 * 3600)
        self.assertEqual(pc, "PC v2.21.0: checked in 19 of the last 24 hours · last heard 6 h ago ⚠️")
        self.assertIn("(this one)", cloud)
        os.remove(self.up)
        self.assertEqual(tb.copies_health({}, now=now, remote=False), ["PC: no record yet", "Cloud: no record yet"])


if __name__ == "__main__":
    unittest.main()
