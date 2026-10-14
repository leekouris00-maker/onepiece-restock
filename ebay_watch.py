#!/usr/bin/env python3
"""
eBay watch for the One Piece restock bot
========================================

Checks eBay for the cards in ebay_watch.json and turns any listing at or under your max into a
normal bot find: Discord alert, phone push, finds.log, /deals and the daily recap. It only reads
eBay - it never buys, bids or logs in.

It uses eBay's official Browse API (eBay Australia, Buy It Now listings that post to Australia),
so it needs a free eBay developer key. Without one it does nothing and the rest of the bot carries
on exactly as before.

"max" in ebay_watch.json is the most you'd pay in AUD, delivered: the item price, plus postage to
Australia, plus the 10% GST eBay adds at checkout on items posted from overseas (an estimate).

Get the eBay key (once, free, about 10 minutes):
  1. developer.ebay.com > sign in with your eBay account > join the eBay Developers Program.
  2. Application Keysets > create a keyset under "Production". If it asks about "marketplace account
     deletion" notices, choose the exemption (this bot doesn't keep any eBay user's data).
  3. Copy the App ID (Client ID) and the Cert ID (Client Secret) into:
       PC copy:    secrets.json next to the bot ("ebay_client_id" and "ebay_client_secret"),
                   then double-click restart_bot.bat
       Cloud copy: GitHub > onepiece-restock > Settings > Secrets and variables > Actions >
                   New repository secret: EBAY_CLIENT_ID, then EBAY_CLIENT_SECRET
The bot posts "eBay watch is on" in Discord once the key works.

Try it any time (prints what's listed now; posts nothing, saves nothing):
    py -3 ebay_watch.py
"""
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WATCH_PATH = os.path.join(HERE, "ebay_watch.json")
SECRETS_PATH = os.path.join(HERE, "secrets.json")
CONFIG_PATH = os.path.join(HERE, "config.json")

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"
MARKETPLACE = "EBAY_AU"
EVERY_MINUTES = 15          # how often each copy of the bot asks eBay (the free key allows 5,000 searches a day)
MIN_EVERY = 5
GST_RATE = 0.10             # eBay adds GST at checkout on items posted to Australia from overseas
NET_FAILS_BEFORE_POST = 3   # eBay unreachable this many checks in a row -> one status post
TIMEOUT = 20
GREEN, AMBER = 0x2A9D8F, 0xF4A261

KEY_MSG = ("eBay refused the key, so eBay isn't being checked. Make sure you copied the Production App ID "
           "(Client ID) and Cert ID (Client Secret): secrets.json on the PC, EBAY_CLIENT_ID and "
           "EBAY_CLIENT_SECRET in GitHub for the cloud copy.")

COUNTRY = {"AU": "Australia", "JP": "Japan", "US": "USA", "GB": "UK", "CA": "Canada", "HK": "Hong Kong",
           "CN": "China", "TW": "Taiwan", "KR": "Korea", "SG": "Singapore", "NZ": "New Zealand",
           "MY": "Malaysia", "PH": "Philippines", "TH": "Thailand", "DE": "Germany", "FR": "France",
           "IT": "Italy", "ES": "Spain", "NL": "Netherlands"}

_urlopen = urllib.request.urlopen       # swapped out in tests
_token = {"value": None, "exp": 0.0}    # eBay's sign-in token lasts 2 hours; reused while it's good
_cache = {"finds": []}                  # the last good check's finds, reused between checks in --loop
_said = set()


class Result:
    """What one call to check() saw.
    finds   listings at or under their max (between checks: the last good check's, in a --loop)
    ran     eBay was asked this time and answered, so listings that have gone can be forgotten
    problem why eBay couldn't be checked (kind: "key", "net", "limit"), else None
    active  there's something to watch and an eBay key to watch it with"""

    def __init__(self, finds=None, ran=False, problem=None, kind=None, active=False, cards=(), every=EVERY_MINUTES):
        self.finds = list(finds or [])
        self.ran = ran
        self.problem = problem
        self.kind = kind
        self.active = active
        self.cards = list(cards)
        self.every = every


class EbayError(Exception):
    def __init__(self, msg, kind="net"):
        super().__init__(msg)
        self.kind = kind


def _say_once(text):
    if text not in _said:
        _said.add(text)
        print(text)


def _read_json(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        _say_once(f"   ! {os.path.basename(path)} couldn't be read ({e})")
        return None


def _num(x):
    if isinstance(x, bool) or x is None:
        return None
    try:
        return float(str(x).strip().replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _strings(v):
    if isinstance(v, str):
        return [v] if v.strip() else []
    return [str(s) for s in (v or []) if isinstance(s, (str, int, float)) and str(s).strip()]


# ---------------------------------------------------------------- settings
def load_watch(path=None):
    """(cards, every_minutes) from ebay_watch.json. A card that can't be used is skipped with a note."""
    data = _read_json(path or WATCH_PATH)
    if not isinstance(data, dict):
        return [], EVERY_MINUTES
    every = max(MIN_EVERY, _num(data.get("every_minutes")) or EVERY_MINUTES)
    cards = []
    for c in data.get("cards") or []:
        if not isinstance(c, dict) or c.get("enabled", True) is False:
            continue
        mx = _num(c.get("max"))
        search = _strings(c.get("search") or c.get("name"))
        if not mx or mx <= 0 or not search:
            _say_once(f"   ! ebay_watch.json: \"{c.get('name', '?')}\" needs a number for \"max\" and a "
                      f"\"search\", so it's skipped")
            continue
        cards.append({"name": str(c.get("name") or search[0]), "max": mx, "search": search,
                      "must_have": _strings(c.get("must_have")), "exclude": _strings(c.get("exclude")),
                      "note": str(c.get("note") or ""), "add_gst": c.get("add_gst", True) is not False})
    return cards, every


def credentials(cfg=None):
    """(client id, client secret) from the environment (cloud copy), config.json "alerts" or secrets.json
    (PC copy), or (None, None) if there's no key yet."""
    alerts = (cfg.get("alerts") or {}) if isinstance(cfg, dict) else {}
    sec = _read_json(SECRETS_PATH) if os.path.exists(SECRETS_PATH) else None
    if isinstance(sec, dict) and isinstance(sec.get("alerts"), dict):
        sec = sec["alerts"]
    sec = sec if isinstance(sec, dict) else {}

    def pick(env, key):
        return (os.environ.get(env, "").strip() or str(alerts.get(key) or "").strip()
                or str(sec.get(key) or "").strip())

    cid, secret = pick("EBAY_CLIENT_ID", "ebay_client_id"), pick("EBAY_CLIENT_SECRET", "ebay_client_secret")
    return (cid, secret) if cid and secret else (None, None)


# ---------------------------------------------------------------- matching and prices
def _norm(s):
    """Lower case, punctuation to spaces, padded: whole-word matching ("psa 10" isn't in "psa 100")."""
    return " " + re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip() + " "


def _has(text_n, phrase):
    p = _norm(phrase)
    return len(p) > 2 and p in text_n


def title_matches(title, card):
    """Every must_have entry ("a|b" = either) in the title, and no exclude word."""
    t = _norm(title)
    for need in card.get("must_have", []):
        if not any(_has(t, alt) for alt in str(need).split("|")):
            return False
    return not any(_has(t, x) for x in card.get("exclude", []))


def _amount(a):
    try:
        return float(a["value"]), str(a.get("currency") or "")
    except (KeyError, TypeError, ValueError):
        return None, ""


def cost(item, add_gst=True):
    """(item price, postage or None if not shown, GST estimate, total) in AUD; None without an AUD price."""
    price, cur = _amount(item.get("price"))
    if price is None:
        return None
    if cur != "AUD":
        _say_once(f"   (eBay watch: skipped a listing priced in {cur or 'an unknown currency'} instead of AUD)")
        return None
    post = None
    for o in item.get("shippingOptions") or []:
        v, c = _amount((o or {}).get("shippingCost"))
        if v is not None and c == "AUD":
            post = v if post is None else min(post, v)
    country = str((item.get("itemLocation") or {}).get("country") or "").upper()
    overseas = bool(country) and country != "AU"
    gst = round((price + (post or 0.0)) * GST_RATE, 2) if (add_gst and overseas) else 0.0
    return price, post, gst, round(price + (post or 0.0) + gst, 2)


def _money(x):
    return f"A${x:,.2f}"


def make_find(card, item, c):
    """A find in the same shape as the bot's singles, so alerts, /deals and the recap show it as usual."""
    price, post, gst, total = c
    iid = str(item.get("itemId") or item.get("legacyItemId") or "")
    url = str(item.get("itemWebUrl") or "").split("?")[0] or f"https://www.ebay.com.au/itm/{item.get('legacyItemId', '')}"
    country = str((item.get("itemLocation") or {}).get("country") or "").upper()
    where = COUNTRY.get(country, country)
    title = re.sub(r"[\[\]]", "", str(item.get("title") or "")).strip() or "eBay listing"
    parts = [f"{_money(price)} item",
             "free postage" if post == 0 else (f"{_money(post)} postage" if post else "postage not shown")]
    if gst:
        parts.append(f"{_money(gst)} GST (est.)")
    extra = []
    if "BEST_OFFER" in (item.get("buyingOptions") or []):
        extra.append("accepts offers")
    s = item.get("seller") or {}
    if s.get("feedbackPercentage"):
        score = str(s.get("feedbackScore", ""))
        extra.append(f"seller feedback {s['feedbackPercentage']}%" + (f" ({int(score):,})" if score.isdigit() else ""))
    if _has(_norm(title), "psa"):
        extra.append("check the cert number at psacard.com/cert before paying")
    note = f"[{title}]({url})\n" + " + ".join(parts) + (" · " + " · ".join(extra) if extra else "")
    if card.get("note"):
        note += "\n" + card["note"]
    return {"id": f"ebay|{iid}", "kind": "Single", "name": card["name"], "deck": "eBay watch", "qty": 1,
            "shop": "eBay" + (f" (from {where})" if where else ""), "price": total, "url": url, "cart": "",
            "note": note[:1000], "priority": True, "ebay": True}


# ---------------------------------------------------------------- talking to eBay
def _call(req, token_call=False):
    try:
        with _urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        if token_call and e.code in (400, 401):
            raise EbayError(KEY_MSG, "key")
        if e.code == 401:
            raise EbayError("eBay refused the bot's sign-in token", "auth")
        if e.code == 403:
            raise EbayError("eBay says this key isn't allowed to search (HTTP 403). It needs to be a "
                            "Production keyset.", "key")
        if e.code == 429:
            raise EbayError("eBay's daily limit for this key is used up. It resets within a day.", "limit")
        raise EbayError(f"eBay answered with an error (HTTP {e.code})", "net")
    except (urllib.error.URLError, OSError) as e:          # no internet, DNS, timeouts, TLS
        raise EbayError(f"couldn't reach eBay ({type(e).__name__})", "net")
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        raise EbayError("eBay sent a reply the bot couldn't read", "net")


def _get_token(cid, secret, now):
    if _token["value"] and now < _token["exp"] - 300:
        return _token["value"]
    basic = base64.b64encode(f"{cid}:{secret}".encode("utf-8")).decode("ascii")
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": SCOPE}).encode("ascii")
    req = urllib.request.Request(TOKEN_URL, data=body, method="POST", headers={
        "Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Basic {basic}",
        "Accept": "application/json"})
    data = _call(req, token_call=True)
    tok = data.get("access_token") if isinstance(data, dict) else None
    if not tok:
        raise EbayError(KEY_MSG, "key")
    _token.update(value=tok, exp=now + (_num(data.get("expires_in")) or 7200))
    return tok


def _search(token, q, max_aud):
    """Buy It Now listings for q that post to Australia, item price up to max_aud, cheapest first."""
    params = {"q": q[:100], "limit": "50", "sort": "price",
              "filter": (f"price:[..{max_aud:.2f}],priceCurrency:AUD,buyingOptions:{{FIXED_PRICE}},"
                         f"deliveryCountry:AU")}
    req = urllib.request.Request(SEARCH_URL + "?" + urllib.parse.urlencode(params), headers={
        "Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE,
        "X-EBAY-C-ENDUSERCTX": "contextualLocation=" + urllib.parse.quote("country=AU", safe=""),
        "Accept": "application/json"})
    data = _call(req)
    return (data.get("itemSummaries") or []) if isinstance(data, dict) else []


def _search_card(cid, secret, card, now, cap=None):
    """[(item, cost)] for one card's searches: title matches, de-duplicated, item price up to cap."""
    out, seen = [], set()
    for q in card["search"]:
        try:
            items = _search(_get_token(cid, secret, now), q, cap or card["max"])
        except EbayError as e:
            if e.kind != "auth":
                raise
            _token["value"] = None                  # token went stale early: get a new one, once
            try:
                items = _search(_get_token(cid, secret, now), q, cap or card["max"])
            except EbayError as e2:
                raise EbayError(KEY_MSG, "key") if e2.kind == "auth" else e2
        for it in items:
            iid = it.get("itemId")
            if not iid or iid in seen or not title_matches(it.get("title"), card):
                continue
            seen.add(iid)
            c = cost(it, card["add_gst"])
            if c is not None:
                out.append((it, c))
    return out


def check(cfg, status=None, force=False, now=None, watch_path=None):
    """Ask eBay about every card in ebay_watch.json, if a check is due (every_minutes) or force=True.
    Remembers when it last asked in status["ebay_ts"] (status.json). Never raises."""
    status = {} if status is None else status
    now = time.time() if now is None else now
    cards, every = load_watch(watch_path)
    if not cards:
        return Result()
    cid, secret = credentials(cfg)
    if not cid:
        _say_once("   (eBay watch is waiting for an eBay key - see the top of ebay_watch.py)")
        return Result(cards=cards, every=every)
    if not force and now - (_num(status.get("ebay_ts")) or 0) < every * 60 - 20:
        return Result(_cache["finds"], active=True, cards=cards, every=every)
    status["ebay_ts"] = round(now)
    try:
        found = {}
        for card in cards:
            for it, c in _search_card(cid, secret, card, now):
                if c[3] <= card["max"] + 0.001:
                    f = make_find(card, it, c)
                    if f["id"] not in found or f["price"] < found[f["id"]]["price"]:
                        found[f["id"]] = f
    except EbayError as e:
        print(f"   ! eBay watch: {e}")
        return Result(_cache["finds"], problem=str(e), kind=e.kind, active=True, cards=cards, every=every)
    except Exception as e:  # noqa: BLE001  (a surprise in eBay's reply must never stop the restock checks)
        print(f"   ! eBay watch: unexpected {type(e).__name__}: {e}")
        return Result(_cache["finds"], problem=f"unexpected {type(e).__name__}", kind="net", active=True,
                      cards=cards, every=every)
    finds = sorted(found.values(), key=lambda f: f["price"])
    _cache["finds"] = finds
    print(f"   (eBay checked: {len(finds)} listing(s) at or under your max)")
    return Result(finds, ran=True, active=True, cards=cards, every=every)


def status_message(status, res):
    """(text, colour) for a Discord status post (no ping) when the eBay watch starts working, has a
    problem, or recovers; None the rest of the time. Remembers in status["ebay_state"]/["ebay_fails"]."""
    if res is None or not res.active:
        return None
    before = status.get("ebay_state")
    if res.ran:
        status["ebay_state"], status["ebay_fails"] = "ok", 0
        if before == "ok":
            return None
        if before:
            return "✅ **eBay watch is working again.**", GREEN
        names = "; ".join(f"{c['name']} (up to ${c['max']:,.0f} delivered)" for c in res.cards)
        return (f"🔎 **eBay watch is on.** Checking eBay every {res.every:g} minutes for: {names}. "
                f"You'll get an alert as soon as one is listed at or under that.", GREEN)
    if not res.problem:
        return None
    fails = int(_num(status.get("ebay_fails")) or 0) + 1
    status["ebay_fails"] = fails
    if res.kind == "net" and fails < NET_FAILS_BEFORE_POST:
        return None
    if before == res.problem:
        return None
    status["ebay_state"] = res.problem
    return f"⚠️ **eBay watch:** {res.problem}" + ("" if res.kind == "key" else " It keeps trying."), AMBER


def self_test(cfg):
    """One line for tcg_bot.py --self-test. False only if there's a key and eBay refuses it."""
    cards, _ = load_watch()
    if not cards:
        print("ebay: nothing in ebay_watch.json (eBay watch off)")
        return True
    cid, secret = credentials(cfg)
    if not cid:
        print(f"ebay: {len(cards)} card(s) to watch, but no eBay key yet (see the top of ebay_watch.py)")
        return True
    try:
        _get_token(cid, secret, time.time())
    except EbayError as e:
        print(f"ebay: {e}")
        return e.kind != "key"
    print(f"ebay: key OK, watching {len(cards)} card(s)")
    return True


# ---------------------------------------------------------------- try it by hand
def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    cfg = _read_json(CONFIG_PATH) or {}
    cards, every = load_watch()
    if not cards:
        print("Nothing to watch yet: add a card to ebay_watch.json.")
        return 0
    print(f"eBay watch: {len(cards)} card(s); the bot checks every {every:g} minutes.")
    cid, secret = credentials(cfg)
    if not cid:
        print("\nNo eBay key yet. The top of ebay_watch.py says how to get one (free).")
        return 1
    try:
        _get_token(cid, secret, time.time())
        print("eBay key: OK")
        for card in cards:
            print(f"\n{card['name']}  (your max: {_money(card['max'])} delivered)")
            rows = sorted(_search_card(cid, secret, card, time.time(), cap=card["max"] * 3), key=lambda x: x[1][3])
            if not rows:
                print("   nothing listed right now that matches (Buy It Now, posts to Australia)")
            for it, c in rows[:10]:
                ok = c[3] <= card["max"] + 0.001
                where = COUNTRY.get(str((it.get("itemLocation") or {}).get("country") or "").upper(), "")
                print(f" {'✅' if ok else '▫️'} {_money(c[3])} delivered{f' from {where}' if where else ''}: "
                      f"{str(it.get('title', ''))[:80]}")
                print(f"      {str(it.get('itemWebUrl') or '').split('?')[0]}")
    except EbayError as e:
        print(f"\n! {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
