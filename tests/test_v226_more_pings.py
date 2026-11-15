"""v2.26: catch more of what other groups ping, without more noise: over-retail shops and Japanese boxes post
quietly, and a feed product the bot never saw goes on the watch list by itself. No network."""
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import link_watch as lw  # noqa: E402
import misses as ms  # noqa: E402
import scorecard as sc  # noqa: E402
import tcg_bot as tb  # noqa: E402

NOW = 1_800_000_000
HOOK = "https://discord.com/api/webhooks/1/boxes"
SOFT = "https://discord.com/api/webhooks/2/restocks"
CFG = {"sealed": {"max_price": 300, "shopify_collections": [], "shopify_search": [], "shopify_products": [],
                  "woocommerce": []}}


def listing(shop="Games Empire", pid="op18", name="One Piece OP-18 Booster Box", price=425.0, available=True,
            group="box", prefix=None, mx=300.0, **kw):
    return dict({"id": f"list|{shop}|{pid}", "box_id": f"{prefix or group}|{shop}|{pid}", "group": group,
                 "kind": "New listing", "name": name, "shop": shop, "price": price, "available": available,
                 "url": f"https://x.test/{pid}", "cart": "", "note": "", "max": mx, "page": 1}, **kw)


class Japanese(unittest.TestCase):
    def setUp(self):
        tb.SEALED_OPTS.update(new=True, packs=False, jp=True)
        self.addCleanup(tb.SEALED_OPTS.update, new=True, packs=False, jp=True)

    def test_japanese_box_is_its_own_group_with_no_buy_price(self):
        for t in ("One Piece OP-17 The World's Strongest Warriors Booster Box (Japanese)",
                  "One Piece The Time of Battle OP-16 Japanese Booster Box",
                  "One Piece｜OP-16 The Time of Battle Booster Box - JP",
                  "One Piece Card Game EB-05 Booster Display [JP]"):
            self.assertEqual(tb.classify(t, [], 300), ("New listing", "jp", "jp", 0.0, None), t)

    def test_english_box_is_unchanged(self):
        self.assertEqual(tb.classify("One Piece OP-18 Booster Box (English)", [], 300)[2], "box")

    def test_not_japanese_boxes(self):
        for t in ("One Piece OP-16 Japanese Booster Box Case (12 boxes)",       # a case
                  "One Piece OP-16 Japanese Booster Pack",                      # a pack
                  "One Piece OP-16 Booster Box Simplified Chinese JP",          # Chinese print
                  "Gundam Card Game Japanese Booster Box",                      # another game
                  "Nami OP16-001 [Japanese Booster Box promo] (Rare)",          # a single
                  "One Piece Japanese Starter Deck ST-30"):                     # not a booster box
            self.assertIsNone(tb.classify(t, [], 300), t)

    def test_switched_off(self):
        tb.begin_check({"japanese_alerts": False}, status={})
        self.assertIsNone(tb.classify("One Piece OP-17 Booster Box (Japanese)", [], 300))
        tb.begin_check({}, status={})
        self.assertIsNotNone(tb.classify("One Piece OP-17 Booster Box (Japanese)", [], 300))

    def test_shop_reader_lists_it_but_never_as_a_find(self):
        products = [{"title": "One Piece OP-17 Booster Box (Japanese)", "handle": "jp17",
                     "variants": [{"id": 1, "price": "160.00", "available": True}]}]
        with mock.patch.object(tb, "shopify_collection", return_value=(products, {"jp17": 1})):
            finds, listings = tb.shopify_boxes("GB Toys", "https://gbtoys.com.au/collections/x/products.json", 300)
        self.assertEqual(finds, [])                                   # $160 is under the box max: still no buy alert
        self.assertEqual([(l["group"], l["box_id"]) for l in listings], [("jp", "jp|GB Toys|jp17")])

    def test_first_read_only_remembers_then_new_ones_alert(self):
        known = {"S": [], "S (all sealed)": []}                        # a shop the bot already knew before v2.26
        a = listing("S", "jp17", "OP-17 Booster Box (Japanese)", 160, group="jp", mx=0.0)
        self.assertEqual(tb.new_listings({"S": [a]}, known, []), [])
        self.assertEqual(known["S (japanese)"], [a["id"]])
        b = listing("S", "jp18", "OP-18 Booster Box (Japanese)", 170, group="jp", mx=0.0)
        out = tb.new_listings({"S": [a, b]}, known, [])
        self.assertEqual([l["id"] for l in out], [b["id"]])
        # a shop with no Japanese boxes yet is remembered as empty, so its first one alerts
        known2 = {"T": [], "T (all sealed)": []}
        tb.new_listings({"T": []}, known2, [])
        self.assertEqual(known2["T (japanese)"], [])
        self.assertEqual(len(tb.new_listings({"T": [dict(b, shop="T")]}, known2, [])), 1)

    def test_now_buyable(self):
        l = listing("S", "jp17", "OP-17 Booster Box (Japanese)", 160, group="jp", mx=0.0)
        out = tb.opened_listings({"S": [l]}, hist={l["box_id"]: {"avail": False, "since": NOW - 3600}}, now=NOW)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0]["opened"])

    def test_scorecard_no_longer_calls_it_filtered(self):
        self.assertIsNone(ms.skip_reason(tb, {}, "One Piece Card Game Japanese Booster Box OP-18"))
        self.assertIn("japanese", ms.skip_reason(tb, {"japanese_alerts": False},
                                                 "One Piece Card Game Japanese Booster Box OP-18"))
        self.assertIn("Japanese box", ms.seen_reason(tb, {}, [("jp|S|x", {"points": [["2026-11-16", 160]], "avail": True})]))


class Quieten(unittest.TestCase):
    def test_soft_shops_are_in_the_list(self):
        names = tb.soft_shop_names(CFG)
        for n in ("Games Empire", "X-Playground", "Dropstore", "Lootable", "Games Portal", "GB Toys"):
            self.assertIn(n, names)
        self.assertNotIn("GUF", names)
        self.assertEqual(tb.soft_shop_names(dict(CFG, extra_shops=False)), set())
        self.assertIn("gamesempire.com.au", tb.shop_names(CFG))        # so the scorecard and allowed-sites know it

    def test_marks_japanese_and_soft_shop_listings(self):
        loud = listing("GUF", "a", group="new", prefix="item", mx=0.0)
        jp = listing("GUF", "b", group="jp", mx=0.0)
        shop = listing("Games Empire", "c", group="box")
        out = tb.quieten(CFG, [loud, jp, shop], {}, NOW)
        self.assertEqual([bool(l.get("soft")) for l in out], [False, True, True])
        self.assertNotIn("soft", jp)                                    # the originals aren't changed

    def test_quiet_now_buyable_once_a_day_per_product(self):
        status = {}
        l = listing("Games Empire", "c", group="new", prefix="item", mx=0.0, opened=True)
        self.assertEqual(len(tb.quieten(CFG, [l], status, NOW)), 1)
        self.assertEqual(tb.quieten(CFG, [l], status, NOW + 3600), [])
        self.assertEqual(len(tb.quieten(CFG, [l], status, NOW + 25 * 3600)), 1)
        loud = listing("GUF", "d", group="new", prefix="item", mx=0.0, opened=True)
        self.assertEqual(len(tb.quieten(CFG, [loud], status, NOW)), 1)  # loud ones aren't throttled here
        self.assertEqual(len(tb.quieten(CFG, [loud], status, NOW + 60)), 1)

    def test_over_max_restocks_pass_through(self):
        l = listing("Games Empire", "c", soft=True, opened=True, note="back in stock, over your $300.00 max")
        status = {"soft_alerts": {l["box_id"]: NOW}}                    # restocked_over_max already counted it
        self.assertEqual(tb.quieten(CFG, [l], status, NOW), [l])

    def test_a_real_deal_at_a_soft_shop_is_still_a_loud_find(self):
        products = [{"title": "One Piece OP-18 Booster Box", "handle": "op18",
                     "variants": [{"id": 1, "price": "250.00", "available": True}]}]
        with mock.patch.object(tb, "shopify_collection", return_value=(products, {"op18": 1})):
            finds, _ = tb.shopify_boxes("Games Empire", "https://gamesempire.com.au/collections/x/products.json", 300)
        self.assertEqual([(f["kind"], f["price"], f.get("soft")) for f in finds], [("Booster box", 250.0, None)])


class Delivery(unittest.TestCase):
    def setUp(self):
        self.sent = []
        for p in (mock.patch.object(tb, "discord_send", side_effect=lambda a, hook, payload: self.sent.append((hook, payload)) or True),
                  mock.patch.object(tb, "read_json", return_value={})):
            p.start()
            self.addCleanup(p.stop)
        self.cfg = {"alerts": {"discord_webhook": HOOK, "discord_webhook_restocks": SOFT, "discord_ping": "<@&1>"},
                    "sealed": {"max_price": 300}}

    def push(self, finds, cfg=None):
        return tb.push_discord_detailed(cfg or self.cfg, "t", "b", finds, ping=True)

    def titles(self):
        return [e["title"] for _, p in self.sent for e in p.get("embeds", [])]

    def test_quiet_listings_go_to_the_restocks_channel_unpinged(self):
        jp = listing("GB Toys", "jp17", "OP-17 Booster Box (Japanese)", 160, group="jp", mx=0.0, soft=True, note="in stock")
        new = listing("Games Empire", "op19", "One Piece OP-19 Booster Box", 425, soft=True,
                      note="in stock (over your $300.00 max)")
        opened = listing("Dropstore", "st40", "One Piece Starter Deck ST-40", 40, group="new", prefix="item", mx=0.0,
                         soft=True, opened=True, note="now buyable")
        self.push([jp, new, opened])
        self.assertEqual({h for h, _ in self.sent}, {SOFT})
        text = json.dumps([p for _, p in self.sent], ensure_ascii=False)
        self.assertNotIn("<@&1>", text)
        self.assertIn("3 quiet alert(s) (no ping)", text)
        t = self.titles()
        self.assertTrue(t[0].startswith("🇯🇵 Japanese, new listing: "), t)
        self.assertTrue(t[1].startswith("🔔 New listing: "), t)
        self.assertTrue(t[2].startswith("🔔 Now buyable: "), t)

    def test_over_max_restock_keeps_its_v225_wording(self):
        l = listing("Games Empire", "op18", soft=True, opened=True, note="back in stock, over your $300.00 max")
        self.push([l])
        self.assertIn("1 restock(s) over your max (no ping)", json.dumps([p for _, p in self.sent]))
        self.assertTrue(self.titles()[0].startswith("🔔 Restock (over max): "))

    def test_scorecard_link_is_quiet_and_yours_is_not(self):
        auto = {"id": "watch|a", "kind": "Sealed", "name": "One Piece Starter Deck ST-40", "shop": "x.com.au", "price": 40.0,
                "url": "https://x.com.au/p/a", "cart": "", "note": "in stock", "link_watch": True, "auto": True, "soft": True}
        mine = dict(auto, id="watch|b", auto=False, soft=False, priority=True)
        self.push([auto])
        self.assertEqual({h for h, _ in self.sent}, {SOFT})
        self.assertNotIn("<@&1>", json.dumps([p for _, p in self.sent]))
        self.sent.clear()
        self.push([mine])
        self.assertEqual({h for h, _ in self.sent}, {HOOK})


class AutoLinks(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.path = os.path.join(d.name, "watches.json")

    def test_public_https_only(self):
        for ok in ("https://gamesempire.com.au/products/op-18", "https://www.shop.co.nz/p/1?variant=2"):
            self.assertTrue(lw.public_https(ok), ok)
        for bad in ("http://gamesempire.com.au/products/op-18", "https://192.168.1.1/x", "https://localhost/x",
                    "https://shop.com.au:8443/x", "https://user:pw@shop.com.au/x", "https://router.local/x",
                    "https://nas.internal/x", "ftp://shop.com.au/x", "https://[::1]/x", "javascript:alert(1)", ""):
            self.assertFalse(lw.public_https(bad), bad)

    def test_auto_add_has_its_own_limit_and_never_touches_yours(self):
        mine, what = lw.add("https://shop.com.au/products/mine", 200, "Mine", "lee", self.path)
        self.assertEqual(what, "added")
        self.assertEqual(lw.add("https://shop.com.au/products/mine", None, "x", "scorecard", self.path, None, True)[1], "already")
        self.assertEqual(lw.load(self.path)[0]["max"], 200)             # your max and name are untouched
        for i in range(lw.AUTO_MAX):
            it, what = lw.add(f"https://shop.com.au/products/a{i}", None, f"A{i}", "scorecard", self.path, None, True)
            self.assertEqual((what, it["auto"]), ("added", True))
        with self.assertRaises(ValueError):
            lw.add("https://shop.com.au/products/more", None, "x", "scorecard", self.path, None, True)
        with self.assertRaises(ValueError):
            lw.add("http://shop.com.au/products/plain", None, "x", "scorecard", self.path, None, True)
        self.assertEqual(lw.add("https://shop.com.au/products/second", 50, "Mine 2", "lee", self.path)[1], "added")
        self.assertEqual(sum(1 for it in lw.load(self.path) if it["auto"]), lw.AUTO_MAX)

    def test_adding_one_yourself_makes_it_yours(self):
        lw.add("https://shop.com.au/products/a", None, "A", "scorecard", self.path, None, True)
        it, what = lw.add("https://shop.com.au/products/a", 250, "A", "lee", self.path)
        self.assertEqual(what, "updated")
        self.assertFalse(lw.load(self.path)[0]["auto"])

    def test_dropped_after_thirty_days(self):
        lw.add("https://shop.com.au/products/a", None, "A", "scorecard", self.path, None, True)
        lw.add("https://shop.com.au/products/mine", 200, "Mine", "lee", self.path)
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        for it in data["items"]:
            it["added"] = "2026-10-01"
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.assertEqual(lw.prune_auto(self.path, date(2026, 10, 20)), 0)
        self.assertEqual(lw.prune_auto(self.path, date(2026, 11, 16)), 1)
        self.assertEqual([it["name"] for it in lw.load(self.path)], ["Mine"])

    def test_find_is_marked(self):
        item = {"id": "a", "url": "https://shop.com.au/products/a", "name": "A", "max": None, "auto": True}
        f = lw.make_find(item, {"title": "A", "price": 40.0, "status": "in stock", "currency": "AUD", "cart": ""})
        self.assertTrue(f["auto"])
        self.assertFalse(f["priority"])
        self.assertIn("added by the scorecard", f["note"])
        self.assertNotIn("auto", lw.make_find(dict(item, auto=False), {"title": "A", "price": 40.0, "status": "in stock"}))


class LearnFromMisses(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.path = os.path.join(d.name, "watches.json")
        self.state = {}
        for p in (mock.patch.object(lw, "WATCH_PATH", self.path),
                  mock.patch.object(sc, "load_state", side_effect=lambda tb_: self.state.setdefault("s", {"pending": [], "recent": {}})),
                  mock.patch.object(sc, "save_state", side_effect=lambda tb_, st: self.state.__setitem__("s", st)),
                  mock.patch.object(ms, "_guarded", return_value=False)):
            p.start()
            self.addCleanup(p.stop)

    def reading(self, title="One Piece Card Game OP-18 Booster Box", **kw):
        r = dict({"ok": True, "title": title, "price": 425.0, "currency": "AUD", "buyable": True, "status": "in stock"}, **kw)
        return mock.patch.object(lw, "read", return_value=r)

    def go(self, kind="not_found", link="https://gamesempire.com.au/products/op-18", source="feed", cfg=None):
        return sc.auto_watch(tb, cfg or {}, {"link": link, "source": source}, {"kind": kind, "link": link}, fetch=lambda u: b"")

    def test_never_seen_product_is_added(self):
        with self.reading():
            note = self.go()
        self.assertIn("now on the watch list", note)
        it = lw.load(self.path)[0]
        self.assertEqual((it["auto"], it["by"], it["max"]), (True, "scorecard", None))

    def test_unwatched_shop_too_unless_security_is_enforcing(self):
        with self.reading():
            self.assertIn("now on the watch list", self.go("not_watched", "https://newshop.com.au/products/op-18"))
            ms._guarded.return_value = True
            note = self.go("not_watched", "https://othershop.com.au/products/op-18")
            self.assertIn("security", note)
            self.assertIn("now on the watch list", self.go("not_found", "https://guf.com.au/products/op-18"))
        self.assertEqual(len(lw.load(self.path)), 2)

    def test_only_misses_from_the_feed(self):
        with self.reading() as rd:
            for kind in ("first", "late", "seen", "filtered", "error"):
                self.assertEqual(self.go(kind), "")
            self.assertEqual(self.go(source="report"), "")
            self.assertEqual(self.go(cfg={"scorecard": {"auto_watch": False}}), "")
            self.assertEqual(self.go(link="http://gamesempire.com.au/products/op-18"), "")
            self.assertEqual(self.go(link="https://10.0.0.5/products/op-18"), "")
            rd.assert_not_called()                                      # none of those even loads the page
        self.assertEqual(lw.load(self.path), [])

    def test_only_one_piece_sealed_in_dollars(self):
        for kw in ({"title": "Pokémon Scarlet & Violet Booster Box"}, {"title": "Sabo - OP13-120 [Carrying On His Will]"},
                   {"title": "One Piece Card Game Official Sleeves Set 17"}, {"title": "One Piece Luffy Figure"},
                   {"title": ""}, {"ok": False}, {"currency": "USD"}):
            with self.reading(**kw):
                self.assertEqual(self.go(), "", kw)
        self.assertEqual(lw.load(self.path), [])

    def test_already_watched_says_nothing_and_full_says_so(self):
        with self.reading():
            self.go()
            self.assertEqual(self.go(), "")
            for i in range(lw.AUTO_MAX - 1):
                self.go(link=f"https://gamesempire.com.au/products/b{i}")
            self.assertIn("already watching", self.go(link="https://gamesempire.com.au/products/last"))

    def test_a_page_that_cannot_be_read_never_raises(self):
        with mock.patch.object(lw, "read", side_effect=RuntimeError("boom")):
            self.assertEqual(self.go(), "")

    def test_shop_suggested_on_its_third_drop_only(self):
        res = {"kind": "not_watched", "host": "newshop.com.au"}
        notes = [sc.shop_suggestion(tb, {}, res) for _ in range(4)]
        self.assertEqual([bool(n) for n in notes], [False, False, True, False])
        self.assertIn("newshop.com.au has come up 3 times", notes[2])
        self.assertEqual(sc.shop_suggestion(tb, {}, {"kind": "not_found", "host": "guf.com.au"}), "")

    def test_reply_carries_the_note(self):
        res = {"kind": "not_found", "shop": "GUF", "extra": ["➕ now on the watch list"]}
        self.assertEqual(sc.one_line(res).split("\n"), ["🙈 Watched shop, never seen · GUF", "➕ now on the watch list"])
        self.assertEqual(sc.one_line({"kind": "not_found", "shop": "GUF"}), "🙈 Watched shop, never seen · GUF")


if __name__ == "__main__":
    unittest.main()
