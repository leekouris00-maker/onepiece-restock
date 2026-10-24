"""Tests for tcgplayer.py (v2.8). No network: TCGCSV's answers are made up here, shaped like the real
ones (names, extendedData, Normal/Foil price rows) as seen on tcgcsv.com in October 2026.

Run:  python -m unittest discover -s tests
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402,F401  (loads first, as tcgplayer.py expects)
import tcgplayer as tp  # noqa: E402
import value as cv  # noqa: E402

B = "https://tcgcsv.com"


def card(pid, name, num, rarity="SEC"):
    return {"productId": pid, "name": name, "cleanName": name, "imageUrl": "", "categoryId": 68, "groupId": 0,
            "url": f"https://www.tcgplayer.com/product/{pid}/x", "modifiedOn": "",
            "extendedData": [{"name": "Rarity", "displayName": "Rarity", "value": rarity},
                             {"name": "Number", "displayName": "Number", "value": num},
                             {"name": "Description", "displayName": "Description", "value": "..."}]}


def sealed(pid, name):
    return {"productId": pid, "name": name, "cleanName": name, "extendedData": []}


def price(pid, market, low=None, sub="Foil"):
    return {"productId": pid, "lowPrice": low if low is not None else market, "midPrice": market,
            "highPrice": market * 3, "marketPrice": market, "directLowPrice": None, "subTypeName": sub}


GROUPS = [
    {"groupId": 24303, "name": "Carrying On His Will", "abbreviation": "OP13", "isSupplemental": False,
     "publishedOn": "2025-11-07T00:00:00", "modifiedOn": "", "categoryId": 68},
    {"groupId": 24498, "name": "Carrying On His Will: 3rd Anniversary Tournament Cards", "abbreviation": "OP13 ANN",
     "isSupplemental": False, "publishedOn": "2025-10-31T00:00:00", "modifiedOn": "", "categoryId": 68},
    {"groupId": 3188, "name": "Romance Dawn", "abbreviation": "OP01", "isSupplemental": False,
     "publishedOn": "2022-12-02T00:00:00", "modifiedOn": "", "categoryId": 68},
    {"groupId": 24305, "name": "Premium Booster -The Best- Vol. 2", "abbreviation": "PRB-02", "isSupplemental": False,
     "publishedOn": "2025-10-03T00:00:00", "modifiedOn": "", "categoryId": 68},
]


def products(day_prices):
    """{groupId: (products, prices)} for one day; day_prices tweaks market prices by product id."""
    op13 = [card(657256, "Sabo (004)", "OP13-004", "L"), card(657257, "Sabo (004) (Alternate Art)", "OP13-004", "L"),
            card(657410, "Sabo (120)", "OP13-120"), card(657413, "Sabo (120) (Parallel)", "OP13-120"),
            card(657414, "Sabo (120) (Wanted Poster)", "OP13-120"),
            sealed(628352, "Carrying On His Will Booster Box"), sealed(628353, "Carrying On His Will Booster Box Case"),
            {"productId": 660710, "name": "DON!! Card (Gol.D.Roger) (Gold)",
             "extendedData": [{"name": "CardType", "value": "DON!!"}, {"name": "Rarity", "value": "DON!!"}]}]
    ann = [card(700001, "Sabo (120)", "OP13-120")]          # same number and version, another set
    op01 = [card(1001, "Shanks", "OP01-120"), card(1002, "Shanks (Parallel)", "OP01-120"),
            card(1003, "Roronoa Zoro", "OP01-001", "L")]
    prb = [card(2001, "Carrot (OP08-023) (Alternate Art)", "OP08-023", "R"),
           card(2002, "Shanks (Reprint)", "OP01-120"), card(2003, "Shanks (Pirate Foil)", "OP01-120")]
    base = {657256: 0.15, 657257: 26.86, 657410: 2.77, 657413: 12.33, 657414: 115.62, 628352: 443.33,
            628353: 5970.87, 660710: 4.53, 700001: 9.0, 1001: 8.5, 1002: 85.0, 1003: 0.3, 2001: 60.0,
            2002: 3.0, 2003: 20.0}
    base.update(day_prices)
    pr = lambda ids: [price(i, base[i], sub="Normal" if i in (628352, 628353) else "Foil") for i in ids]
    out = {24303: (op13, pr([p["productId"] for p in op13])), 24498: (ann, pr([700001])),
           3188: (op01, pr([1001, 1002, 1003])), 24305: (prb, pr([2001, 2002, 2003]))}
    # Zoro has a Normal and a Foil row: two prices for one product
    out[3188][1].append(price(1003, 0.1, sub="Normal"))
    return out


def fake_tcgcsv(stamp, day_prices=None, fail=()):
    data = products(day_prices or {})
    pages = {f"{B}/last-updated.txt": stamp.encode(),
             f"{B}/tcgplayer/categories": json.dumps({"success": True, "results": [
                 {"categoryId": 3, "name": "Pokemon", "displayName": "Pokemon"},
                 {"categoryId": 68, "name": "One Piece Card Game", "displayName": "One Piece Card Game"}]}).encode(),
             f"{B}/tcgplayer/68/groups": json.dumps({"success": True, "results": GROUPS}).encode(),
             "https://api.frankfurter.dev/v1/latest?base=USD&symbols=AUD":
                 json.dumps({"base": "USD", "rates": {"AUD": 1.5}}).encode()}
    for gid, (prods, prices) in data.items():
        pages[f"{B}/tcgplayer/68/{gid}/products"] = json.dumps({"success": True, "results": prods}).encode()
        pages[f"{B}/tcgplayer/68/{gid}/prices"] = json.dumps({"success": True, "results": prices}).encode()

    def get(url, tries=3):
        if url in pages and not any(f in url for f in fail):
            return pages[url]
        raise OSError(f"{url}: HTTP 404")
    return get


def synced(stamps_prices):
    """Run several days of syncs; -> the store."""
    store = tp.empty_store()
    orig = tp._get
    try:
        for stamp, dp in stamps_prices:
            tp._get = fake_tcgcsv(stamp, dp)
            tp.sync(store, {}, log=lambda *_: None, sleep=lambda *_: None)
    finally:
        tp._get = orig
    return store


DAY1 = "2026-10-22T20:05:00+0000"
DAY2 = "2026-10-23T20:06:07+0000"


class SyncTests(unittest.TestCase):
    def test_sync_keys_kinds_and_prices(self):
        st = synced([(DAY1, {})])
        it = st["items"]
        self.assertEqual(st["category"], 68)
        self.assertEqual(st["updated"], DAY1)
        self.assertEqual(it["657413"]["num"], "OP13-120")
        self.assertEqual(it["657413"]["m"], 12.33)
        self.assertEqual(it["628352"]["t"], "sealed")
        self.assertEqual(it["660710"]["t"], "don")
        self.assertIn("1003:Foil", it)                    # two price rows -> two keys
        self.assertIn("1003:Normal", it)
        self.assertNotIn("1003", it)
        self.assertEqual(st["fx"]["rate"], 1.5)
        self.assertEqual(st["groups"]["24303"]["a"], "OP13")

    def test_same_stamp_is_skipped_and_history_only_on_change(self):
        st = synced([(DAY1, {}), (DAY2, {657414: 130.0})])
        orig = tp._get
        tp._get = fake_tcgcsv(DAY2)
        try:
            self.assertEqual(tp.sync(st, {}, log=lambda *_: None, sleep=lambda *_: None), "same")
        finally:
            tp._get = orig
        self.assertEqual(len(st["items"]["657414"]["h"]), 2)
        self.assertEqual(len(st["items"]["657413"]["h"]), 1)          # unchanged: one point
        self.assertEqual(st["items"]["1003:Normal"].get("h"), [])     # bulk: no history

    def test_failed_sets_keep_old_data_and_mark_partial(self):
        st = synced([(DAY1, {})])
        orig = tp._get
        tp._get = fake_tcgcsv(DAY2, fail=("/24303/", "/3188/"))      # 2 of 4 sets fail
        try:
            self.assertEqual(tp.sync(st, {}, log=lambda *_: None, sleep=lambda *_: None), "partial")
        finally:
            tp._get = orig
        self.assertIn("657413", st["items"])                            # kept
        self.assertEqual(st["updated"], DAY1)                           # tried again next run

    def test_save_and_load_round_trip(self):
        st = synced([(DAY1, {})])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.json")
            tp.save_store(st, p)
            back = tp.load_store(p)
        self.assertEqual(back["items"], st["items"])
        self.assertEqual(back["groups"], st["groups"])
        self.assertEqual(back["updated"], DAY1)


class MatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = synced([(DAY1, {})])

    def m(self, name):
        return tp.match(self.st, name)

    def test_elemental_and_good_games_titles(self):
        self.assertEqual(self.m("Shanks (Parallel) - OP01-120 [Romance Dawn]"), "1002")
        self.assertEqual(self.m("Shanks - OP01-120 [Romance Dawn]"), "1001")
        self.assertEqual(self.m("Sabo (Wanted Poster) [Carrying On His Will] (OP13-120)"), "657414")
        self.assertEqual(self.m("Sabo - OP13-120 (Parallel) [Carrying On His Will]"), "657413")
        self.assertEqual(self.m("Sabo - OP13-004 [Carrying On His Will]"), "657256")
        self.assertEqual(self.m("Shanks (Reprint) [Premium Booster -The Best- Vol. 2] (OP01-120)"), "2002")
        self.assertEqual(self.m("Shanks (Pirate Foil) - OP01-120 [Premium Booster -The Best- Vol. 2]"), "2003")

    def test_same_version_in_two_sets_goes_by_set_name(self):
        self.assertEqual(self.m("Sabo - OP13-120 [Carrying On His Will]"), "657410")
        self.assertEqual(self.m("Sabo - OP13-120 [Carrying On His Will: 3rd Anniversary Tournament Cards]"), "700001")
        self.assertIsNone(self.m("Sabo - OP13-120"))                    # no set: can't tell which

    def test_alternate_art_and_parallel_are_the_same_version(self):
        self.assertEqual(self.m("Carrot (Alternate Art) [Premium Booster -The Best- Vol. 2] (OP08-023)"), "2001")
        self.assertEqual(self.m("Carrot - OP08-023 (Parallel) [Premium Booster -The Best- Vol. 2]"), "2001")

    def test_no_match_for_unknown_versions(self):
        self.assertIsNone(self.m("Shanks (Jolly Roger Foil) - OP01-120 [Romance Dawn]"))
        self.assertIsNone(self.m("Sabo (Manga) - OP13-120 [Carrying On His Will]"))
        self.assertIsNone(self.m("A booster box with no number"))

    def test_versions(self):
        self.assertEqual(tp.tcg_version("Sabo (120) (Parallel)"), ("alternate art",))
        self.assertEqual(tp.tcg_version("Nami (OP01-016) (SP)"), ("sp",))
        self.assertEqual(tp.tcg_version("Monkey.D.Luffy (Super Pre-Release) [Winner]"), ("super pre-release", "winner"))
        self.assertEqual(tp.tcg_version("Jewelry Bonney - PRB02-004 (Alternate Art)"), ("alternate art",))
        self.assertEqual(tp.shop_version("Sabo (Wanted Poster) [Carrying On His Will] (OP13-120)"), ("wanted poster",))


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.st = synced([(DAY1, {}), (DAY2, {657414: 140.0, 1002: 70.0, 628352: 480.0})])
        self.cfg = {"sealed": {"max_price": 750},
                    "singles": {"cards": [
                        {"name": "Sabo", "num": "OP13-120", "max": 12, "enabled": True,
                         "exclude": ["wanted", "super alternate"]},
                        {"name": "Zoro", "num": "OP01-001", "max": 1, "enabled": False}]}}

    def test_movers(self):
        up, down = tp.movers(self.st, tp.settings({}), 1)
        self.assertEqual([x[1] for x in up], ["657414"])               # +21%; the box's +8% is under 10%
        self.assertEqual([x[1] for x in down], ["1002"])

    def test_deals_from_the_shops_record(self):
        drops = {"v": 1, "shops": {"Elemental Arcade": {"base": "https://elementalarcade.com.au"}},
                 "items": {
                     # TCGplayer A$105 (US$70 x 1.5); A$60 in stock: 43% under -> a deal
                     "Elemental Arcade|shanks-parallel-op01120-romance-dawn":
                         {"n": "Shanks (Parallel) - OP01-120 [Romance Dawn]", "p": [[1, 120.6, 1], [2, 60.0, 1]]},
                     # sold out: left out
                     "Elemental Arcade|sabo-op13120-wanted":
                         {"n": "Sabo - OP13-120 (Wanted Poster) [Carrying On His Will]", "p": [[1, 50.0, 0]]},
                     # under A$10 on TCGplayer: left out
                     "Elemental Arcade|sabo-op13004":
                         {"n": "Sabo - OP13-004 [Carrying On His Will]", "p": [[1, 0.05, 1]]},
                     # A$12 vs TCGplayer A$12.75: not cheap enough
                     "Elemental Arcade|shanks-op01120-romance-dawn":
                         {"n": "Shanks - OP01-120 [Romance Dawn]", "p": [[1, 12.0, 1]]}}}
        deals = tp.shop_deals(self.st, drops, tp.settings({}))
        self.assertEqual([d["tkey"] for d in deals], ["1002"])
        self.assertAlmostEqual(deals[0]["market_aud"], 105.0)
        self.assertTrue(deals[0]["url"].endswith("/products/shanks-parallel-op01120-romance-dawn"))
        self.assertFalse(deals[0]["check"])

    def test_report_embeds_fit_discord(self):
        drops = {"shops": {}, "items": {}}
        embeds = tp.report(self.st, self.cfg, drops)
        titles = [e["title"] for e in embeds]
        self.assertEqual(titles[0], "📈 TCGplayer movers")
        self.assertIn("📦 Booster boxes on TCGplayer", titles)
        self.assertIn("🎯 Your want list on TCGplayer", titles)
        for e in embeds:
            size = len(e["title"]) + len(e.get("description", "")) + len(e["footer"]["text"]) + sum(
                len(f["name"]) + len(f["value"]) for f in e.get("fields") or [])
            self.assertLess(size, 6000)
            self.assertLessEqual(len(e.get("description", "")), 4096)
        box = next(e for e in embeds if e["title"].startswith("📦"))["description"]
        self.assertIn("Carrying On His Will Booster Box · OP13", box)
        self.assertNotIn("Case", box)
        self.assertIn("✅ under your max", box)                         # US$480 x 1.5 = A$720 <= A$750
        want = next(e for e in embeds if e["title"].startswith("🎯"))["description"]
        self.assertIn("Sabo · OP13-120", want)                         # cheapest non-excluded: the regular
        self.assertNotIn("Zoro", want)                                 # switched off

    def test_first_day_says_movers_start_tomorrow(self):
        st = synced([(DAY1, {})])
        self.assertIn("movers start tomorrow", tp.report(st, {}, None)[0]["description"])

    def test_lookup(self):
        e = tp.lookup_embed(self.st, "OP13-120")
        self.assertIn("Sabo (Wanted Poster) · OP13-120", e["description"])
        self.assertIn("▲21% since Thu 22 Oct", e["description"])     # under a week of record so far
        e = tp.lookup_embed(self.st, "op13 booster box")
        self.assertTrue(e["description"].startswith("[Carrying On His Will Booster Box Case"))
        self.assertIn("Nothing", tp.lookup_embed(self.st, "zzzz")["title"])

    def test_value_line_and_value_build(self):
        line = tp.value_line(self.st, "Sabo (Wanted Poster) [Carrying On His Will] (OP13-120)")
        self.assertIn("A$210.00", line)                                 # US$140 x 1.5
        now = 1_800_000_000
        store = {"v": 1, "shops": {"Good Games": {"base": "https://tcg.goodgames.com.au", "scans": [now - 3600]}},
                 "items": {"Good Games|sabo-wanted-poster-carrying-on-his-will":
                           {"n": "Sabo (Wanted Poster) [Carrying On His Will] (OP13-120)", "p": [[now - 86400, 201.3, 1]]}}}
        e, _ = cv.build({}, "OP13-120", now=now, store=store, tcg=self.st)
        self.assertIn("TCGplayer (US) market **A$210.00**", e["description"])
        e, _ = cv.build({}, "OP13-120", now=now, store=store)
        self.assertNotIn("TCGplayer", e["description"])


if __name__ == "__main__":
    unittest.main()
