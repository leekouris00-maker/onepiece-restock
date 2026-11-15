"""v2.25: a booster box back in stock above your max posts once, quietly (no @ping, no phone push, no auto-buy).
No network."""
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402

NOW = 1_800_000_000
HOOK = "https://discord.com/api/webhooks/1/boxes"
SOFT = "https://discord.com/api/webhooks/2/restocks"


def listing(shop="Overhauled", pid="op08", name="One Piece OP-08 Booster Box", price=499.95, available=True, group="box",
            mx=300.0, note=""):
    return {"id": f"list|{shop}|{pid}", "box_id": f"box|{shop}|{pid}", "group": group, "kind": "New listing", "name": name,
            "shop": shop, "price": price, "available": available, "url": f"https://x.test/{pid}", "cart": "", "note": note,
            "max": mx, "page": 1}


def hist_for(l, avail=False, since=NOW - 3600):
    return {l["box_id"]: {"avail": avail, "since": since}}


class OverMax(unittest.TestCase):
    def go(self, listings, hist, status=None, cfg=None, skip=(), now=NOW):
        return tb.restocked_over_max(cfg or {}, {"s": listings}, {} if status is None else status, skip, hist, now)

    def test_back_in_stock_over_max(self):
        l = listing()
        out = self.go([l], hist_for(l))
        self.assertEqual(len(out), 1)
        f = out[0]
        self.assertTrue(f["soft"] and f["opened"])
        self.assertEqual((f["kind"], f["price"], f["shop"]), ("New listing", 499.95, "Overhauled"))
        self.assertEqual(f["note"], "back in stock, over your $300.00 max")
        self.assertTrue(f["id"].startswith("open|box|Overhauled|op08|"))

    def test_not_for_these(self):
        l = listing()
        self.assertEqual(self.go([listing(price=280.0)], hist_for(l)), [])                  # under max: the loud alert has it
        self.assertEqual(self.go([listing(available=False)], hist_for(l)), [])
        self.assertEqual(self.go([l], {}), [])                                               # never seen: a new-listing alert
        self.assertEqual(self.go([l], hist_for(l, avail=True)), [])                          # was already buyable
        self.assertEqual(self.go([l], hist_for(l, since=NOW - 300)), [])                     # flickered for 5 minutes
        self.assertEqual(self.go([l], hist_for(l), skip={l["box_id"]}), [])
        g = listing(group="new", mx=0.0)
        self.assertEqual(self.go([g], hist_for(g)), [])                                      # other sealed: opened_listings
        case = listing(pid="case", name="One Piece OP-17 Booster Box Case (12 Boxes)", price=7190.0)
        self.assertEqual(self.go([case], hist_for(case)), [])                                # over 4x your max
        dep = listing(pid="dep", name="One Piece OP-19 Booster Box deposit", price=350.0)
        self.assertEqual(self.go([dep], hist_for(dep)), [])
        self.assertEqual(self.go([l], hist_for(l), cfg={"restock_alerts": False}), [])
        self.assertEqual(self.go(None, hist_for(l)), [])                                     # the shop didn't load

    def test_watched_sealed_item_too(self):
        w = listing(pid="tin", name="One Piece Tin Set", price=80.0, group="watch", mx=50.0, note="Tin")
        out = self.go([w], hist_for(w))
        self.assertEqual(out[0]["note"], "Tin, back in stock, over your $50.00 max")

    def test_preorder_wording(self):
        p = listing(pid="op19", name="PRE-ORDER One Piece OP-19 Booster Box", price=320.0)
        self.assertIn("pre-order open, over your", self.go([p], hist_for(p))[0]["note"])

    def test_once_a_day_per_product(self):
        l, st = listing(), {}
        self.assertEqual(len(self.go([l], hist_for(l), st)), 1)
        self.assertEqual(self.go([l], hist_for(l, since=NOW + 3600), st, now=NOW + 2 * 3600), [])     # in and out 2 h later
        self.assertEqual(len(self.go([l], hist_for(l, since=NOW + 23 * 3600), st, now=NOW + 25 * 3600)), 1)
        other = listing(shop="Cherry")
        self.assertEqual(len(self.go([other], hist_for(other), st, now=NOW + 2 * 3600)), 1)           # another shop still posts
        st["soft_alerts"]["old"] = NOW - 30 * 86400
        self.go([], {}, st)
        self.assertNotIn("old", st["soft_alerts"])

    def test_settings(self):
        l = listing()
        cfg = {"restock_alerts": {"repeat_hours": 1, "max_times": 1.5}}
        self.assertEqual(self.go([l], hist_for(l), cfg=cfg), [])                              # 499.95 > 1.5 x 300
        self.assertEqual(len(self.go([listing(price=400.0)], hist_for(l), cfg=cfg)), 1)
        self.assertEqual(tb.soft_settings({}), {"repeat_hours": 24.0, "max_times": 4.0})
        self.assertEqual(tb.soft_settings({"restock_alerts": {"repeat_hours": -1}}), tb.soft_settings({}))
        self.assertFalse([w for w in tb.check_config({"singles": {}, "sealed": {}, "restock_alerts": False}) if "restock" in w])


def soft_find(**kw):
    l = listing(**kw)
    return dict(l, id=f"open|{l['box_id']}|1", opened=True, soft=True, note="back in stock, over your $300.00 max")


def loud_find():
    return {"id": "box|Gameology|op18", "kind": "Booster box", "name": "One Piece OP-18 Booster Box", "shop": "Gameology",
            "price": 259.95, "url": "https://g.test/p", "cart": "", "note": ""}


class Posting(unittest.TestCase):
    def setUp(self):
        self.sent = []
        for p in (mock.patch.object(tb, "discord_send", side_effect=lambda a, hook, payload: self.sent.append((hook, payload)) or True),
                  mock.patch.object(tb, "read_json", return_value={})):
            p.start()
            self.addCleanup(p.stop)
        self.cfg = {"alerts": {"discord_webhook_boxes": HOOK, "discord_ping": "<@&1>"}, "flip": False}

    def post(self, finds, cfg=None, ping=True):
        return tb.push_discord_detailed(cfg or self.cfg, "t", "b", finds, ping=ping)

    def test_quiet_restock_alone_pings_nobody(self):
        f = soft_find()
        ok, delivered = self.post([f])
        self.assertEqual(delivered, {f["id"]})
        hook, payload = self.sent[0]
        self.assertEqual(hook, HOOK)
        self.assertNotIn("<@&1>", payload["content"])
        self.assertIn("restock(s) over your max", payload["content"])
        self.assertTrue(payload["embeds"][0]["title"].startswith("🔔 Restock (over max): "))

    def test_loud_box_still_pings(self):
        self.post([loud_find()])
        self.assertTrue(self.sent[0][1]["content"].startswith("<@&1> "))

    def test_mixed_message_pings_for_the_loud_one(self):
        self.post([loud_find(), soft_find()])
        self.assertEqual(len(self.sent), 1)
        self.assertTrue(self.sent[0][1]["content"].startswith("<@&1> "))

    def test_own_channel_when_set(self):
        cfg = {"alerts": dict(self.cfg["alerts"], discord_webhook_restocks=SOFT), "flip": False}
        self.post([loud_find(), soft_find()], cfg)
        by_hook = dict(self.sent)
        self.assertEqual(set(by_hook), {HOOK, SOFT})
        self.assertTrue(by_hook[HOOK]["content"].startswith("<@&1> "))
        self.assertNotIn("<@&1>", by_hook[SOFT]["content"])


class InTheRun(unittest.TestCase):
    def test_no_ping_push_or_auto_buy_for_a_quiet_restock(self):
        with open(tb.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('auto_buy.offer(sys.modules[__name__], cfg, [f for f in deliver if not f.get("soft")])', src)
        self.assertIn('ping = bool(loud) and ping_allowed(cfg, loud)', src)
        self.assertIn("restocked_over_max(cfg, by_shop, status,", src)

    def test_desk_mode_never_opens_one(self):
        opened = []
        with mock.patch.object(tb.fast_lane, "desk_until", return_value=time.time() + 600), \
                mock.patch.object(tb, "IN_ACTIONS", False), mock.patch.object(tb, "DRY_RUN", [False]):
            tb.fast_lane.desk_open(tb, [dict(soft_find(), cart="https://x.test/cart/1:1")], opener=opened.append)
        self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()
