"""
My collection (v2.11.4): pricing from the bot's own records, the price when added, the 7-day change,
totals, photos, and the page's routes. Temp files only: no shops, no Discord, no GitHub.

Run:  python -m unittest tests.test_collection
"""
import base64
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import auto_buy as ab  # noqa: E402
import auto_buy_web as web  # noqa: E402
import collection as col  # noqa: E402
import tcg_bot as tb  # noqa: E402
import tcgplayer as tp  # noqa: E402


def day(n):
    return (date.today() - timedelta(days=n)).isoformat()


def ts(n):
    return datetime.fromisoformat(day(n)).timestamp() + 3600


TINY_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.saved = (col.PATH, col.PHOTOS_DIR, tb.HISTORY_PATH, tb.DROPS_PATH, tp.load_for)
        col.PATH = os.path.join(self.dir, "collection.json")
        col.PHOTOS_DIR = os.path.join(self.dir, "photos")
        tb.HISTORY_PATH = os.path.join(self.dir, "price_history.json")
        tb.DROPS_PATH = os.path.join(self.dir, "singles_prices.json")
        col._cache.update(t=0, prices={})
        # Two shops with the TS-02 tin over the last 9 days (one sold out), plus a 12-tin display that
        # must not count, and a booster box that doesn't match.
        tb.atomic_write_json(tb.HISTORY_PATH, {
            "item|A|ts02": {"name": "One Piece Card Game Tin Pack Set Vol. 2 (TS-02)", "shop": "Alpha",
                            "url": "https://a.example/products/ts02",
                            "points": [[day(9), 80.0, True], [day(7), 80.0, True], [day(3), 90.0, True], [day(0), 100.0, True]]},
            "item|B|ts02": {"name": "One Piece Tin Pack Vol 2 TS-02 (Random Select)", "shop": "Beta",
                            "url": "https://b.example/products/ts02",
                            "points": [[day(9), 70.0, False], [day(0), 70.0, False]]},
            "item|C|disp": {"name": "One Piece Tin Pack Set Vol. 2 (TS-02) - Sealed Display (12 Tins)", "shop": "Gamma",
                            "url": "https://c.example/x", "points": [[day(0), 20.0, True]]},
            "box|A|op15": {"name": "OP-15 Booster Box", "shop": "Alpha", "url": "", "points": [[day(0), 230.0, True]]},
        })
        tb.atomic_write_json(tb.DROPS_PATH, {"v": 1, "shops": {"Elemental Arcade": {"base": "https://ea.example"}}, "items": {
            "Elemental Arcade|sabo-sp": {"n": "Sabo - OP13-120 (Wanted Poster) [Carrying On His Will]", "p": [[ts(8), 300.0, 1], [ts(1), 330.0, 1]]},
            "Elemental Arcade|sabo": {"n": "Sabo - OP13-120 [Carrying On His Will]", "p": [[ts(8), 10.0, 1], [ts(2), 12.0, 1]]},
            "Elemental Arcade|sabo-jp": {"n": "Sabo - OP13-120 (Japanese) [Carrying On His Will]", "p": [[ts(1), 5.0, 1]]},
        }})
        tp.load_for = lambda cfg=None: {"fx": {"rate": 1.5}, "items": {
            "111": {"n": "Monkey.D.Luffy - OP05-119", "t": "card", "num": "OP05-119", "m": 20.0,
                    "h": [[date.fromisoformat(day(8)).toordinal(), 10.0], [date.fromisoformat(day(1)).toordinal(), 20.0]]},
            "112": {"n": "Monkey.D.Luffy - OP05-119 (Parallel)", "t": "card", "num": "OP05-119", "m": 200.0, "h": []}}}
        tp._index_cache.clear()

    def tearDown(self):
        (col.PATH, col.PHOTOS_DIR, tb.HISTORY_PATH, tb.DROPS_PATH, tp.load_for) = self.saved
        tp._index_cache.clear()
        shutil.rmtree(self.dir)


class Pricing(Base):
    def test_sealed_tin_price_start_and_week(self):
        it = col.upsert(tb, {"name": "Luffy tin", "kind": "Tin", "paid": "40", "match": "ts-02 tin"})
        snap = col.snapshot(tb)
        row = snap["items"][0]
        self.assertEqual(row["now"], 100.0)                       # cheapest IN stock (Beta is sold out, display skipped)
        self.assertIn("in stock", row["source"])
        self.assertEqual(row["where"], "Alpha")
        self.assertEqual(row["start"], {"date": day(0), "price": 100.0})   # price on the day it was added
        self.assertEqual(row["week"]["from"], 80.0)               # a week ago, from the bot's history
        self.assertEqual(row["week"]["pct"], 25.0)
        self.assertEqual(row["week"]["label"], "7 days")
        self.assertGreaterEqual(len(row["spark"]), 7)
        self.assertEqual(snap["totals"]["paid"], 40.0)
        self.assertEqual(snap["totals"]["worth"], 100.0)
        self.assertEqual(snap["totals"]["gain"], 60.0)
        self.assertEqual(it["got"], day(0))

    def test_got_in_the_past_uses_that_days_price(self):
        col.upsert(tb, {"name": "Shanks tin", "kind": "Tin", "paid": 40, "match": "ts-02 tin", "got": day(5)})
        row = col.snapshot(tb)["items"][0]
        self.assertEqual(row["start"], {"date": day(5), "price": 80.0})

    def test_card_by_number_and_version(self):
        col.upsert(tb, {"name": "Sabo", "kind": "Card", "card": "op13120", "state": "Raw"})
        col.upsert(tb, {"name": "Sabo wanted", "kind": "Card", "card": "OP13-120", "match": "wanted poster", "state": "Raw"})
        col.upsert(tb, {"name": "Sabo JP", "kind": "Card", "card": "OP13-120", "lang": "JP", "state": "Raw"})
        rows = {r["name"]: r for r in col.snapshot(tb)["items"]}
        self.assertEqual(rows["Sabo"]["card"], "OP13-120")
        self.assertEqual(rows["Sabo"]["now"], 12.0)               # regular print, not the Wanted Poster
        self.assertEqual(rows["Sabo wanted"]["now"], 330.0)
        self.assertEqual(rows["Sabo JP"]["now"], 5.0)
        self.assertEqual(rows["Sabo wanted"]["week"]["pct"], 10.0)

    def test_tcgplayer_when_no_shop_has_it(self):
        col.upsert(tb, {"name": "Luffy", "kind": "Card", "card": "OP05-119", "state": "Raw"})
        col.upsert(tb, {"name": "Luffy AA", "kind": "Card", "card": "OP05-119", "match": "alternate art", "state": "Raw"})
        rows = {r["name"]: r for r in col.snapshot(tb)["items"]}
        self.assertEqual(rows["Luffy"]["now"], 30.0)              # US$20 x 1.5
        self.assertIn("TCGplayer", rows["Luffy"]["source"])
        self.assertEqual(rows["Luffy"]["week"]["pct"], 100.0)     # A$15 eight days ago -> A$30
        self.assertEqual(rows["Luffy AA"]["now"], 300.0)

    def test_estimate_and_nothing_found(self):
        col.upsert(tb, {"name": "Nike Gomu Gomu DON!!", "kind": "Promo", "value": "150", "paid": "90"})
        col.upsert(tb, {"name": "Mystery", "kind": "Other", "paid": "10"})
        snap = col.snapshot(tb)
        rows = {r["name"]: r for r in snap["items"]}
        self.assertEqual(rows["Nike Gomu Gomu DON!!"]["now"], 150.0)
        self.assertEqual(rows["Nike Gomu Gomu DON!!"]["source"], "your estimate")
        self.assertIsNone(rows["Nike Gomu Gomu DON!!"]["week"])   # only one day so far
        self.assertIsNone(rows["Mystery"]["now"])
        self.assertEqual(snap["totals"]["paid"], 100.0)            # total cost counts everything paid
        self.assertEqual(snap["totals"]["worth"], 160.0)           # unpriced counts at what you paid
        self.assertEqual(snap["totals"]["gain"], 60.0)
        self.assertEqual(snap["totals"]["priced"], 1)

    def test_total_cost_uses_quantity_and_flags_missing(self):
        col.upsert(tb, {"name": "Luffy tin", "kind": "Tin", "paid": "40", "qty": "2", "match": "ts-02 tin"})
        col.upsert(tb, {"name": "Gift", "kind": "Other"})
        T = col.snapshot(tb)["totals"]
        self.assertEqual(T["paid"], 80.0)
        self.assertEqual(T["items"], 3)
        self.assertEqual(T["no_cost"], 1)

    def test_week_change_rules(self):
        self.assertIsNone(col.week_change({}))
        self.assertIsNone(col.week_change({day(0): 5}))
        w = col.week_change({day(3): 50, day(0): 60})
        self.assertEqual(w["pct"], 20.0)
        self.assertTrue(w["label"].startswith("since "))
        w = col.week_change({day(20): 10, day(8): 40, day(6): 45, day(0): 50})
        self.assertEqual((w["from"], w["pct"], w["label"]), (40, 25.0, "7 days"))

    def test_daily_point_and_history_kept(self):
        col.upsert(tb, {"name": "Luffy tin", "kind": "Tin", "match": "ts-02 tin"})
        with open(tb.HISTORY_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        raw["item|A|ts02"]["points"][-1][1] = 110.0               # shop raises the price later today
        tb.atomic_write_json(tb.HISTORY_PATH, raw)
        col.refresh(tb, force=True)
        it = col.load(tb)[0]
        self.assertEqual(it["hist"][day(0)], 110.0)
        self.assertEqual(it["start"]["price"], 100.0)              # the price when added doesn't move
        self.assertEqual(it["hist"][day(7)], 80.0)

    def test_changing_what_is_priced_restarts_record(self):
        it = col.upsert(tb, {"name": "Thing", "kind": "Tin", "match": "ts-02 tin"})
        it = col.upsert(tb, {"id": it["id"], "match": "op-15 booster box", "kind": "Sealed"})
        self.assertEqual(it["start"]["price"], 230.0)
        it = col.upsert(tb, {"id": it["id"], "notes": "holding"})  # other edits keep the record
        self.assertEqual(it["start"]["price"], 230.0)

    def test_checks(self):
        for bad in ({"name": ""}, {"name": "x", "kind": "Car"}, {"name": "x", "paid": "abc"},
                    {"name": "x", "card": "hello"}, {"name": "x", "got": "tomorrow"}, {"name": "x", "qty": "0"}):
            with self.assertRaises(ValueError, msg=bad):
                col.upsert(tb, bad)
        with self.assertRaises(ValueError):
            col.upsert(tb, {"id": "deadbeef", "name": "x"})

    def test_remove_and_photo(self):
        it = col.upsert(tb, {"name": "Shanks tin", "kind": "Tin"})
        with self.assertRaises(ValueError):
            col.set_photo(tb, it["id"], "data:image/png;base64,AAAA")
        col.set_photo(tb, it["id"], "data:image/jpeg;base64," + base64.b64encode(TINY_JPEG).decode())
        self.assertTrue(os.path.isfile(col.photo_path(it["id"])))
        self.assertTrue(col.load(tb)[0]["photo"])
        col.remove(tb, it["id"])
        self.assertEqual(col.load(tb), [])
        self.assertFalse(os.path.exists(col.photo_path(it["id"])))
        with self.assertRaises(ValueError):
            col.photo_path("../x")


class Page(Base):
    def setUp(self):
        super().setUp()
        self.saved2 = (tb.CONTROLS_PATH, ab.LEDGER_PATH, ab.LIST_PATH, ab.SHOTS_DIR, web.TOKEN_PATH)
        tb.CONTROLS_PATH = os.path.join(self.dir, "controls.json")
        ab.LEDGER_PATH = os.path.join(self.dir, "autobuy.json")
        ab.LIST_PATH = os.path.join(self.dir, "autobuy_list.json")
        ab.SHOTS_DIR = os.path.join(self.dir, "shots")
        web.TOKEN_PATH = os.path.join(self.dir, "token.txt")
        self.srv = web.start(tb, ab, {"auto_buy": {"web_port": 0}})
        self.port = self.srv.server_address[1]
        self.key = web.token()

    def tearDown(self):
        web.stop()
        (tb.CONTROLS_PATH, ab.LEDGER_PATH, ab.LIST_PATH, ab.SHOTS_DIR, web.TOKEN_PATH) = self.saved2
        super().tearDown()

    def call(self, path, body=None, key=True):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None)
        req.add_header("Content-Type", "application/json")
        if key:
            req.add_header("X-Token", self.key)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_routes(self):
        code, html = self.call("/", key=False)
        self.assertEqual(code, 200)
        self.assertIn(b"My collection", html)
        self.assertEqual(self.call("/api/collection", key=False)[0], 401)
        self.assertEqual(self.call("/api/collection/item", {"name": "x"}, key=False)[0], 401)
        code, d = self.call("/api/collection/item", {"name": "Luffy tin", "kind": "Tin", "paid": "40", "match": "ts-02 tin"})
        self.assertEqual(code, 200, d)
        self.assertEqual(d["collection"]["items"][0]["now"], 100.0)
        iid = d["collection"]["items"][0]["id"]
        code, d = self.call("/api/collection/item", {"name": "x", "paid": "lots"})
        self.assertEqual(code, 400)
        photo = "data:image/jpeg;base64," + base64.b64encode(TINY_JPEG).decode()
        code, d = self.call("/api/collection/photo", {"id": iid, "data": photo})
        self.assertEqual(code, 200, d)
        code, raw = self.call(f"/cphoto/{iid}.jpg?t={self.key}", key=False)
        self.assertEqual((code, raw[:2]), (200, b"\xff\xd8"))
        self.assertEqual(self.call(f"/cphoto/{iid}.jpg", key=False)[0], 404)
        code, d = self.call("/api/collection")
        self.assertEqual(d["totals"]["paid"], 40.0)
        code, d = self.call("/api/collection/remove", {"id": iid})
        self.assertEqual((code, d["collection"]["items"]), (200, []))


if __name__ == "__main__":
    unittest.main()
