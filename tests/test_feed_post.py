"""feed_post.py: only buyable One Piece shop stock from shops that let the bot in goes to the app's feed."""
import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import feed_post as fp

FINDS = [
    {"id": "box|Shop A|op14", "kind": "Booster box", "name": "OP-14 Booster Box", "shop": "Shop A", "price": 179.95, "url": "https://a.example/op14"},
    {"id": "new|Shop B|op13", "kind": "New listing", "name": "OP-13 Booster Pack", "shop": "Shop B", "price": 9.0, "url": "https://b.example/op13", "opened": True},
    {"id": "new|Shop B|jp", "kind": "New listing", "group": "jp", "name": "OP-15 Booster Box", "shop": "Shop B", "price": 120, "url": "https://b.example/jp"},
    {"id": "new|Shop C|soon", "kind": "New listing", "name": "OP-16 Booster Box", "shop": "Shop C", "price": None, "url": "https://c.example/soon"},
    {"id": "single|x", "kind": "Single", "name": "Luffy", "shop": "Shop A", "price": 50, "url": "https://a.example/luffy"},
    {"id": "v|x", "kind": "Sealed", "value_pick": True, "name": "Tin", "shop": "Shop A", "price": 5, "url": "https://a.example/tin"},
    {"id": "poke|x", "kind": "Booster box", "game": "pokemon", "name": "Pokémon box", "shop": "Shop A", "price": 200, "url": "https://a.example/pk"},
    {"id": "link|x", "kind": "Sealed", "link_watch": True, "name": "Watched", "shop": "Shop A", "price": 5, "url": "https://a.example/w"},
    {"id": "box|Refusing|op14", "kind": "Booster box", "name": "OP-14 Booster Box", "shop": "Refusing Shop", "price": 170, "url": "https://r.example/op14"},
    {"id": "box|Http|op14", "kind": "Booster box", "name": "OP-14 Booster Box", "shop": "Http Shop", "price": 170, "url": "http://h.example/op14"},
    {"id": "box|Shop A|op14", "kind": "Booster box", "name": "OP-14 Booster Box", "shop": "Shop A", "price": 179.95, "url": "https://a.example/op14"},
]


def test_rows_only_public_restocks():
    rows = fp.rows_for(FINDS, refused=["refusing shop"], today="2026-11-27")
    assert [r["title"] for r in rows] == ["OP-14 Booster Box", "OP-13 Booster Pack", "Japanese OP-15 Booster Box"]
    assert rows[0] == {"ext_id": "bot:box|Shop A|op14:2026-11-27", "title": "OP-14 Booster Box", "kind": "box", "price": "179.95",
                       "store": "Shop A", "state": "ONLINE", "url": "https://a.example/op14"}
    assert rows[1]["kind"] == "pack" and rows[2]["kind"] == "box"


def test_kind_of():
    assert fp.kind_of("OP-14 Booster Box Case", "Booster box") == "case"
    assert fp.kind_of("ST-29 Starter Deck") == "deck"
    assert fp.kind_of("Promo Pack Vol 7") == "pack"
    assert fp.kind_of("Playmat") == "other"


def test_post_off_without_token():
    assert fp.post({}, FINDS) is None


def test_post_sends_rows(monkeypatch):
    sent = {}

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def opener(req, timeout=0):
        sent["url"], sent["body"], sent["key"] = req.full_url, json.loads(req.data), req.headers.get("Apikey")
        return R(b"3")
    n = fp.post({"app_feed_token": "tok", "app_anon_key": "anon"}, FINDS, refused=["Refusing Shop"], opener=opener)
    assert n == 3
    assert sent["url"].endswith("/rest/v1/rpc/bot_post_restock") and sent["key"] == "anon"
    assert sent["body"]["token"] == "tok" and len(sent["body"]["rows"]) == 3


def test_post_never_raises():
    def boom(req, timeout=0): raise OSError("offline")
    assert fp.post({"app_feed_token": "tok", "app_anon_key": "anon"}, FINDS, opener=boom) is None
    assert fp.post({"app_feed_token": "tok", "app_anon_key": "anon", "app_feed": False}, FINDS) is None
