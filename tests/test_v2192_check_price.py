"""v2.19.2: "Check price" on a collection item asks the singles shops now, keeps that price for the day
(the hourly update doesn't put the older record back), and falls back to the records when nothing is in
stock. No network: the shop lookups are faked.

Run:  python -m unittest discover -s tests
"""
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402
import collection as col  # noqa: E402

CFG = {"singles": {"shops": {"Elemental Arcade": "https://ea.test", "Good Games": "https://gg.test"}}}


def find(shop, price, title, cond="NM"):
    return {"shop": shop, "price": price, "url": f"https://{shop[:2].lower()}.test/products/x", "note": title,
            "cond": cond}


class CheckPrice(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._path, self._here = col.PATH, col.HERE
        col.PATH, col.HERE = os.path.join(self.dir, "collection.json"), self.dir
        self._ea, self._hs, self._quote = tb.elemental_card, tb.handle_shop_card, col.quote
        self.ea, self.gg, self.calls = [], [], []

        def ea(card, base):
            self.calls.append(("ea", card["num"]))
            return list(self.ea)

        def gg(card, name, base):
            self.calls.append(("gg", card["num"]))
            return list(self.gg)
        tb.elemental_card, tb.handle_shop_card = ea, gg
        self.record_price = 2.74
        col.quote = lambda _tb, it, cfg=None: (None if it.get("value") is None and self.record_price is None else
                                              {"price": it["value"], "source": "your estimate", "series": {}}
                                              if it.get("value") is not None else
                                              {"price": self.record_price, "source": "cheapest copy in stock",
                                               "where": "Elemental Arcade", "url": "", "series": {}})
        col._cache.update(t=0, prices={})

    def tearDown(self):
        tb.elemental_card, tb.handle_shop_card, col.quote = self._ea, self._hs, self._quote
        col.PATH, col.HERE = self._path, self._here
        col._cache.update(t=0, prices={})
        shutil.rmtree(self.dir, ignore_errors=True)

    def add(self, **d):
        return col.upsert(tb, dict({"name": "Sabo (SEC)", "kind": "Card", "state": "Raw", "card": "OP13-120"}, **d), CFG)

    def test_takes_the_cheapest_regular_copy_in_stock_now(self):
        it = self.add()
        self.ea = [find("Elemental Arcade", 3.10, "Sabo - OP13-120 [Carrying On His Will]"),
                   find("Elemental Arcade", 1.50, "Sabo - OP13-120 (Alternate Art) [Carrying On His Will]"),
                   find("Elemental Arcade", 0.90, "Sabo - OP13-120 [Carrying On His Will] Damaged")]
        self.gg = [find("Good Games", 2.95, "Sabo (SP) - Carrying On His Will")]
        _, q, note = col.check_price(tb, it["id"], CFG)
        self.assertEqual(q["price"], 3.10)            # not the alt art, the SP, or the damaged copy
        self.assertEqual(q["where"], "Elemental Arcade")
        self.assertIn("A$3.10 at Elemental Arcade (was A$2.74)", note)
        self.assertIn(("ea", "OP13-120"), self.calls)
        self.assertIn(("gg", "OP13-120"), self.calls)

    def test_the_live_price_stays_for_the_day(self):
        it = self.add()
        self.ea = [find("Elemental Arcade", 3.10, "Sabo - OP13-120 [Carrying On His Will]")]
        col.check_price(tb, it["id"], CFG)
        snap = col.snapshot(tb, CFG)                  # the hourly update: records still say 2.74
        row = next(r for r in snap["items"] if r["id"] == it["id"])
        self.assertEqual(row["now"], 3.10)
        self.assertIn("checked just now", row["source"])
        self.assertEqual(col.load(tb)[0]["hist"][col.today()], 3.10)

    def test_version_words_pick_the_alt_art(self):
        it = self.add(name="Marco (Alt Art)", card="OP16-014", match="alternate art")
        self.ea = [find("Elemental Arcade", 1.00, "Marco - OP16-014 [The Time of Battle]"),
                   find("Elemental Arcade", 12.50, "Marco - OP16-014 (Alternate Art) [The Time of Battle]")]
        _, q, _ = col.check_price(tb, it["id"], CFG)
        self.assertEqual(q["price"], 12.50)

    def test_none_in_stock_falls_back_to_the_records(self):
        it = self.add()
        _, q, note = col.check_price(tb, it["id"], CFG)
        self.assertEqual(q["price"], 2.74)
        self.assertTrue(note.startswith("None in stock at Elemental or Good Games right now"))

    def test_nothing_anywhere_says_so_and_keeps_the_item(self):
        it = self.add()
        self.record_price = None
        _, q, note = col.check_price(tb, it["id"], CFG)
        self.assertIsNone(q)
        self.assertIn("No price found", note)
        self.assertEqual(len(col.load(tb)), 1)

    def test_sealed_rereads_the_latest_shop_check(self):
        tb.atomic_write_json(os.path.join(self.dir, "status.json"), {"sealed_ts": time.time() - 240})
        it = self.add(name="Shanks tin (TS-03)", kind="Tin", state="Sealed", card="", match="ts-03")
        _, q, _ = col.check_price(tb, it["id"], CFG)
        self.assertEqual(self.calls, [])               # no singles-shop search for sealed
        self.assertIn("shops checked 4 min ago", q["source"])

    def test_estimate_is_left_alone(self):
        it = self.add(name="Nike DON!!", kind="Promo", card="", value=300)
        _, _, note = col.check_price(tb, it["id"], CFG)
        self.assertIn("your own estimate", note)
        self.assertEqual(self.calls, [])

    def test_editing_what_is_priced_drops_the_old_check(self):
        it = self.add()
        self.ea = [find("Elemental Arcade", 3.10, "Sabo - OP13-120 [Carrying On His Will]")]
        col.check_price(tb, it["id"], CFG)
        col.upsert(tb, {"id": it["id"], "card": "PRB02-014"}, CFG)
        self.assertNotIn("checked", col.load(tb)[0])

    def test_unknown_item(self):
        with self.assertRaises(ValueError):
            col.check_price(tb, "deadbeef", CFG)


if __name__ == "__main__":
    unittest.main()
