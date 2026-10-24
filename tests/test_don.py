"""v2.7.1: DON!! cards (no card number) on the want list, and /bought for eBay watch items.
No network: shop searches, product pages and Discord are fakes.

Run:  python -m unittest discover -s tests
"""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402

try:
    import commands_bot as cb  # noqa: E402
except SystemExit:            # discord.py not installed: the command tests are skipped
    cb = None

EA = "https://elementalarcade.com.au"
GG = "https://tcg.goodgames.com.au"
GOMU = {"name": "Gomu Gomu DON!!", "num": "DON-GOMU-GOMU", "match": ["gomu"], "qty": 1, "max": 80.0}


def variants(cents):
    return [{"id": 700, "title": "Near Mint", "available": True, "price": cents}]


class Matching(unittest.TestCase):
    def test_words_and_key(self):
        self.assertEqual(tb.don_words("GOMU GOMU (RUBBER-RUBBER) DON!! CARD"), ["gomu", "gomu"])
        self.assertEqual(tb.don_key(tb.don_words("Gomu Gomu DON")), "DON-GOMU-GOMU")

    def test_a_don_card_title_matches(self):
        for t in ("DON!! Card (Gomu Gomu)", "Nike x One Piece DON !! card gomu gomu", "don-card-gomu-gomu-nike"):
            self.assertTrue(tb.card_matches(GOMU, t), t)

    def test_other_cards_dont(self):
        for t in ("Monkey D. Luffy - OP05-119 Gomu Gomu", "Don Quixote Doflamingo - gomu", "DON!! Card (Mera Mera)"):
            self.assertFalse(tb.card_matches(GOMU, t), t)

    def test_either_spelling(self):
        c = dict(GOMU, match=["gomu|gum"])
        self.assertTrue(tb.card_matches(c, "DON!! card Gum Gum"))

    def test_numbered_cards_unchanged(self):
        self.assertTrue(tb.card_matches({"num": "OP13-120"}, "sabo-op13120"))
        self.assertEqual(tb.card_label({"name": "Sabo", "num": "OP13-120"}), "Sabo OP13-120")
        self.assertEqual(tb.card_label(GOMU), "Gomu Gomu DON!!")

    def test_config_keeps_it_switched_on(self):
        cfg = {"singles": {"shops": {}, "cards": [dict(GOMU)]}}
        tb.check_config(cfg)
        self.assertTrue(cfg["singles"]["cards"][0].get("enabled", True))


class Shops(unittest.TestCase):
    def setUp(self):
        self._suggest, self._js = tb.suggest, tb.product_js
        self.queries = []
        results = [{"handle": "don-card-gomu-gomu", "title": "DON!! Card (Gomu Gomu)", "available": True,
                    "price": "60.00", "price_min": "60.00"},
                   {"handle": "luffy-op05-119", "title": "Monkey D. Luffy - OP05-119 Gomu Gomu", "available": True,
                    "price": "5.00", "price_min": "5.00"}]
        pages = {"don-card-gomu-gomu": {"title": "DON!! Card (Gomu Gomu)", "variants": variants(6000),
                                        "description": "DON!!"},
                 "luffy-op05-119": {"title": "Monkey D. Luffy - OP05-119 Gomu Gomu", "variants": variants(500),
                                    "description": "DON!! -2: gomu gomu"}}

        def suggest(base, q):
            self.queries.append(q)
            return results
        tb.suggest = suggest
        tb.product_js = lambda base, h: pages.get(h)

    def tearDown(self):
        tb.suggest, tb.product_js = self._suggest, self._js

    def test_elemental(self):
        (f,) = tb.elemental_card(dict(GOMU), EA)
        self.assertEqual((f["name"], f["price"]), ("Gomu Gomu DON!!", 60.0))
        self.assertEqual(self.queries, ["don gomu"])

    def test_good_games_matches_on_title_not_card_text(self):
        (f,) = tb.handle_shop_card(dict(GOMU), "Good Games", GG)
        self.assertIn("don-card-gomu-gomu", f["url"])

    def test_over_max(self):
        self.assertEqual(tb.elemental_card(dict(GOMU, max=50), EA), [])


@unittest.skipIf(cb is None, "discord.py not installed")
class Commands(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.saved = (tb.CONFIG_PATH, cb.AUDIT_PATH, cb.ew.WATCH_PATH if cb.ew else None)
        tb.CONFIG_PATH = os.path.join(self.dir, "config.json")
        cb.AUDIT_PATH = os.path.join(self.dir, "audit.log")
        with open(tb.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"singles": {"shops": {}, "cards": [{"name": "Sabo", "num": "OP13-120", "qty": 1, "max": 5}]},
                       "alerts": {"admin_user_ids": ["1"]}}, f)
        if cb.ew:
            cb.ew.WATCH_PATH = os.path.join(self.dir, "ebay_watch.json")
            with open(cb.ew.WATCH_PATH, "w", encoding="utf-8") as f:
                json.dump({"cards": [{"name": "Nike x One Piece Gomu Gomu DON!! card (English)", "max": 400},
                                     {"name": "Nike x One Piece Gomu Gomu DON!! card (Japanese)", "max": 300},
                                     {"name": "Nike x One Piece Mera Mera DON!! card (English)", "max": 400}]}, f)

    def tearDown(self):
        tb.CONFIG_PATH, cb.AUDIT_PATH, wp = self.saved
        if cb.ew:
            cb.ew.WATCH_PATH = wp
        shutil.rmtree(self.dir, ignore_errors=True)

    def inter(self):
        sent = []

        async def send_message(msg=None, **kw):
            sent.append(msg)
        user = SimpleNamespace(id=1, guild_permissions=None, __str__=lambda self: "lee")
        return SimpleNamespace(user=user, response=SimpleNamespace(send_message=send_message,
                                                                   is_done=lambda: False)), sent

    def run_cmd(self, cmd, **kw):
        i, sent = self.inter()
        asyncio.run(cmd.callback(i, **kw))
        return sent[-1]

    def raw(self):
        with open(tb.CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)

    def test_want_add_a_don_card(self):
        msg = self.run_cmd(cb.want_add, num="Gomu Gomu DON", max=80.0)
        self.assertIn("Gomu Gomu DON!!", msg)
        c = self.raw()["singles"]["cards"][-1]
        self.assertEqual((c["num"], c["match"], c["name"]), ("DON-GOMU-GOMU", ["gomu"], "Gomu Gomu DON!!"))

    def test_a_plain_name_still_needs_a_number(self):
        self.assertIn("OP13-120", self.run_cmd(cb.want_add, num="sabo", max=5.0))
        self.assertEqual(len(self.raw()["singles"]["cards"]), 1)

    def test_bought_a_don_card_on_the_want_list(self):
        self.run_cmd(cb.want_add, num="Gomu Gomu DON", max=80.0)
        msg = self.run_cmd(cb.bought_cmd, card="gomu gomu don")
        self.assertIn("stopped alerting", msg)
        self.assertFalse(self.raw()["singles"]["cards"][-1]["enabled"])

    @unittest.skipIf(not cb or not cb.ew, "no ebay_watch.py")
    def test_bought_the_screenshot_text_asks_which_one(self):
        msg = self.run_cmd(cb.bought_cmd, card='"GOMU GOMU" (RUBBER-RUBBER) DON!! CARD')
        self.assertIn("more than one", msg)
        self.assertIn("(English)", msg)
        self.assertIn("(Japanese)", msg)
        self.assertNotIn("Mera", msg)

    @unittest.skipIf(not cb or not cb.ew, "no ebay_watch.py")
    def test_bought_an_ebay_item_from_the_list(self):
        msg = self.run_cmd(cb.bought_cmd, card="ebay:Nike x One Piece Gomu Gomu DON!! card (English)")
        self.assertIn("stopped looking", msg)
        with open(cb.ew.WATCH_PATH, encoding="utf-8") as f:
            cards = json.load(f)["cards"]
        self.assertFalse(cards[0]["enabled"])
        self.assertTrue(cards[1].get("enabled", True))

    def test_nothing_matches(self):
        self.assertIn("isn't on the want list or the eBay watch", self.run_cmd(cb.bought_cmd, card="zoro"))


if __name__ == "__main__":
    unittest.main()
