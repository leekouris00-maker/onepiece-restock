#!/usr/bin/env python3
"""
eBay deal finder (v2.12) - singles listed well under TCGplayer's market
=======================================================================

Every 15 minutes the PC copy reads the newest One Piece singles listed on eBay Australia (Buy It Now,
posts to Australia) and compares each one with TCGplayer's market price for the same card and version
(tcgplayer.py's daily prices, converted to A$). A listing whose delivered cost (item + postage + GST on
overseas items) is 25%+ under market, with a decent profit left after selling fees, goes to your PRIVATE
channel (🔒・auto-buy, or "discord_webhook_deals" if you give it its own), plus a phone push for the big ones.
It only reads eBay - it never buys, bids, offers or logs in. Friends in the server never see it.

It uses the same free eBay key as the eBay watch (see the top of ebay_watch.py). The PC copy only: the cloud
copy never runs it (its files are public on GitHub, and it has no private channel).

How a listing is valued - always the LOWEST price it could plausibly be, so a wrong guess means a missed deal,
never a fake one:
  1. The title must have exactly one card number (OP13-120, ST10-006, P-001, "OP13 120"...).
  2. Its version words (alt art / parallel, super alt, red super alt, manga, SP, wanted poster, treasure,
     anniversary, winner...) must be exactly the ones on the TCGplayer version. A title that doesn't say
     "alt art" is valued as the plain card, even if it's really the alt art.
  3. If several TCGplayer products still fit (reprints, promo printings), it takes the cheapest.
  Skipped outright: Japanese/Chinese/Korean, graded slabs, lots/playsets/"choose your card", damaged/creased,
  proxies and customs, sellers under 98% / 20 feedback, and anything under 20% of market (almost always a
  fake or the wrong version).

Settings (all optional) in config.json under "deal_finder":
  "enabled": true, "min_pct": 25 (% under market), "min_profit": 10 (A$ after fees), "min_market": 30 (A$),
  "sell_fee_pct": 13 (what eBay/TCGplayer take when you resell), "assume_postage": 3 (A$, when a listing
  hides postage), "push_min_profit": 25 (phone push at this profit), "every_minutes": 15,
  "searches_per_hour": 40 (shares the eBay key's 5,000 a day with the eBay watch),
  "extra_searches": [...] (typed into eBay as well as one search per valuable set).

Try it by hand (prints what it finds; posts and saves nothing):
    py -3 deal_finder.py            one round of searches, like the bot does
    py -3 deal_finder.py --all      every search (uses ~30-40 of the day's eBay searches)
"""
import argparse
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import ebay_watch as ew

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "deal_finder.json")      # PC only (in .gitignore)

DEFAULTS = {
    "enabled": True,
    "min_pct": 25.0,
    "min_profit": 10.0,
    "min_market": 30.0,
    "min_listing": 5.0,
    "sell_fee_pct": 13.0,
    "assume_postage": 3.0,
    "too_good_pct": 20.0,
    "warn_pct": 40.0,
    "push_min_profit": 25.0,
    "every_minutes": 15,
    "searches_per_hour": 40,
    "min_cards_per_set": 3,
    "min_feedback_pct": 98.0,
    "min_feedback_count": 20,
    "extra_searches": ["one piece card alt art", "one piece card manga", "one piece card sp",
                       "one piece wanted poster card", "one piece card promo"],
}
KEEP_SEEN_DAYS = 30
REALERT_DROP = 0.10          # an alerted listing alerts again only if its price drops another 10%
NO_CHANNEL_EVERY = 6 * 3600
LIMIT_PAUSE = 3 * 3600       # eBay's daily limit used up: wait this long before asking again
GOLD, GREEN = 0xE9C46A, 0x2A9D8F

# ---------------------------------------------------------------- reading a title
NUM_RE = re.compile(r"(?<![a-z0-9])(?:(op|eb|st|prb)\s?-?\s?(\d{2})|(p))\s?[-_ ]\s?(\d{3})(?!\d)|"
                    r"(?<![a-z0-9])(op|eb|st|prb)(\d{2})(\d{3})(?!\d)", re.I)
FOREIGN = re.compile(r"\b(japanese|japan|jp|jpn|jap|chinese|chi|china|korean|kor|korea|simplified|asia|asian|"
                     r"cn|thai|french|italian|german|spanish)\b|[぀-ヿ一-鿿가-힯]")
GRADED = re.compile(r"\b(psa|bgs|cgc|beckett|graded|slab|slabbed|ace grading|tag grading|ags|pca|"
                    r"gem mint|gem mt|grade)\b")
LOTS = re.compile(r"\b(lot|lots|bundle|bulk|playset|play set|set of|x\s?[2-9]|[2-9]\s?x|choose|pick|you pick|"
                  r"select|selection|binder|collection|complete set|master set|singles from|various|random|"
                  r"mystery|repack|booster box|booster pack|booster display|sealed box|deck list|full set)\b")
DAMAGED = re.compile(r"\b(damaged|dmg|heavily played|heavy play|hp|poor|crease|creased|bent|water damage|"
                     r"scratched|ripped|torn|miscut)\b")
FAKES = re.compile(r"\b(orica|metal|gold plated|sticker|digital|code|token|fan art|inspired|unofficial|"
                   r"display|acrylic|figure|playmat|sleeve|sleeves)\b")

# Version words that change what a card is worth, longest first. Text a tag matches is used up, so
# "super alt art" is one "saa", not "saa" + "aa".
TAGS = [
    ("red_saa", r"red super alt(?:ernate)?(?: art)?|red super parallel|red saa|red super"),
    ("saa", r"super alt(?:ernate)?(?: art)?|super parallel|super aa|saa"),
    ("aa", r"super rare alt(?:ernate)?(?: art)?"),
    ("manga", r"manga"),
    ("wanted", r"wanted(?: poster)?"),
    ("treasure", r"treasure(?: cup| rare)?|tr"),
    ("textured", r"textured"),
    ("full_art", r"full art"),
    ("sp", r"special(?: art| card| rare)?|spc|sp"),
    ("winner", r"winner"),
    ("finalist", r"finalist"),
    ("serial", r"serial(?: numbered)?|numbered|/1000"),
    ("anniversary", r"anniversary"),
    ("prerelease", r"pre ?release"),
    ("box_topper", r"box topper"),
    ("pirate_foil", r"pirate foil|jolly roger(?: foil)?"),
    ("aa", r"alt(?:ernate)? ?art|alt|aa|parallel"),
]
_TAG_RES = [(t, re.compile(r"(?<![a-z0-9])(?:" + p + r")(?![a-z0-9])")) for t, p in TAGS]
# these are all alt arts already, and sellers often add "alt art" to them anyway
IMPLY_AA = {"red_saa", "saa", "manga", "sp", "wanted", "treasure"}


def _plain(s):
    return " " + re.sub(r"[^a-z0-9/]+", " ", str(s or "").lower().replace("-", " ")).strip() + " "


def tags_of(text):
    """The value-changing version words in a title or a TCGplayer version, as a frozenset of tags."""
    t = _plain(text)
    found = set()
    for tag, rx in _TAG_RES:
        if rx.search(t):
            found.add(tag)
            t = rx.sub(" ", t)
    if found & IMPLY_AA:
        found.discard("aa")
    return frozenset(found)


def card_numbers(title):
    """Every card number in a title, normalised: {'OP13-120'}, {'P-001'}."""
    out = set()
    for m in NUM_RE.finditer(str(title or "")):
        if m.group(5):
            out.add(f"{m.group(5).upper()}{m.group(6)}-{m.group(7)}")
        elif m.group(3):
            out.add(f"P-{m.group(4)}")
        else:
            out.add(f"{m.group(1).upper()}{m.group(2)}-{m.group(4)}")
    return out


def skip_reason(title):
    """Why a title is never a deal (foreign, graded, lot...), or '' if it's worth valuing."""
    t = _plain(title)
    raw = str(title or "")
    for why, rx in (("not English", FOREIGN), ("graded", GRADED), ("lot or multiple", LOTS),
                    ("damaged", DAMAGED), ("not a real card", FAKES)):
        if rx.search(t) or (why == "not English" and rx.search(raw)):
            return why
    if any(ew._has(ew._norm(title), w) for w in ew.SKIP_ALL):
        return "not a real card"
    return ""


# ---------------------------------------------------------------- settings and memory
def settings(cfg):
    s = dict(DEFAULTS)
    mine = (cfg or {}).get("deal_finder")
    if isinstance(mine, dict):
        for k, v in mine.items():
            if k in DEFAULTS and v is not None:
                s[k] = v
    return s


def private_hook(cfg):
    a = (cfg or {}).get("alerts") or {}
    return a.get("discord_webhook_deals") or a.get("discord_webhook_autobuy")


def load_state(tb):
    st = tb.read_json(STATE_PATH, None)
    st = st if isinstance(st, dict) else {}
    st.setdefault("ts", 0)
    st.setdefault("i", 0)
    st.setdefault("seen", {})
    return st


def save_state(tb, st, now):
    cut = now - KEEP_SEEN_DAYS * 86400
    st["seen"] = {k: v for k, v in (st.get("seen") or {}).items() if isinstance(v, list) and v[1] >= cut}
    if not tb.DRY_RUN[0]:
        tb.atomic_write_json(STATE_PATH, st)


# ---------------------------------------------------------------- TCGplayer side
def price_index(tp, store, s):
    """card number -> [(tags, market A$, item key)] for English cards with a market price."""
    by = {}
    for key, it in (store.get("items") or {}).items():
        if it.get("t") != "card" or not it.get("num") or it.get("m") is None:
            continue
        if any("japanese" in v for v in tp.tcg_version(it.get("n"))):
            continue
        vers = " ".join(tp.tcg_version(it.get("n")))
        by.setdefault(it["num"].upper(), []).append((tags_of(vers), tp.aud(store, it["m"]), key))
    return by


def value(idx, title):
    """(market A$, item key, card number) for the cheapest TCGplayer version a title could be, or None."""
    nums = card_numbers(title)
    if len(nums) != 1:
        return None
    num = next(iter(nums))
    want = tags_of(title)
    fits = [(m, k) for tags, m, k in idx.get(num, []) if tags == want]
    if not fits:
        return None
    m, k = min(fits)
    return m, k, num


def searches(store, s):
    """What to type into eBay: the extra searches, then one per set with valuable cards (most valuable first)."""
    counts = {}
    rate = float((store.get("fx") or {}).get("rate") or 1.45)
    for it in (store.get("items") or {}).values():
        if it.get("t") == "card" and it.get("num") and (it.get("m") or 0) * rate >= float(s["min_market"]):
            code = it["num"].split("-")[0].upper()
            if code != "P":
                counts[code] = counts.get(code, 0) + 1
    sets = sorted((c for c, n in counts.items() if n >= int(s["min_cards_per_set"])), key=lambda c: (-counts[c], c))
    return [str(q) for q in s.get("extra_searches") or [] if str(q).strip()] + [f"one piece {c}" for c in sets]


def batch_size(s):
    return max(1, round(float(s["searches_per_hour"]) * float(s["every_minutes"]) / 60))


# ---------------------------------------------------------------- eBay side
def _search_newest(token, q, min_price):
    params = {"q": q[:100], "limit": "200", "sort": "newlyListed",
              "filter": (f"price:[{min_price:.2f}..],priceCurrency:AUD,buyingOptions:{{FIXED_PRICE}},"
                         f"deliveryCountry:AU")}
    req = urllib.request.Request(ew.SEARCH_URL + "?" + urllib.parse.urlencode(params), headers={
        "Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": ew.MARKETPLACE,
        "X-EBAY-C-ENDUSERCTX": "contextualLocation=" + urllib.parse.quote("country=AU", safe=""),
        "Accept": "application/json"})
    data = ew._call(req)
    return (data.get("itemSummaries") or []) if isinstance(data, dict) else []


def fetch(cid, secret, q, min_price, now):
    try:
        return _search_newest(ew._get_token(cid, secret, now), q, min_price)
    except ew.EbayError as e:
        if e.kind != "auth":
            raise
        ew._token["value"] = None                  # token went stale early: get a new one, once
        try:
            return _search_newest(ew._get_token(cid, secret, now), q, min_price)
        except ew.EbayError as e2:
            raise ew.EbayError(ew.KEY_MSG, "key") if e2.kind == "auth" else e2


def evaluate(item, idx, s):
    """A deal dict for an eBay listing, or None. Never raises on odd eBay data."""
    title = str(item.get("title") or "")
    if not title or item.get("itemGroupType") or item.get("itemGroupHref"):
        return None                                # multi-variation listing: its price is the cheapest option
    if skip_reason(title):
        return None
    if not ew.seller_ok(item, {"min_pct": float(s["min_feedback_pct"]), "min_n": float(s["min_feedback_count"])}):
        return None
    v = value(idx, title)
    if not v:
        return None
    market, key, num = v
    if market < float(s["min_market"]):
        return None
    c = ew.cost(item, add_gst=True)
    if c is None:
        return None
    price, post, gst, total = c
    guessed = post is None
    if guessed:
        total = round(total + float(s["assume_postage"]), 2)
    pct = (market - total) / market * 100
    profit = market * (1 - float(s["sell_fee_pct"]) / 100) - total
    if pct < float(s["min_pct"]) or profit < float(s["min_profit"]):
        return None
    if total < market * float(s["too_good_pct"]) / 100:
        return None                                # a $500 card for $40 is a fake or the wrong version
    iid = str(item.get("itemId") or item.get("legacyItemId") or "")
    if not iid:
        return None
    country = str((item.get("itemLocation") or {}).get("country") or "").upper()
    seller = item.get("seller") or {}
    return {"id": iid, "title": re.sub(r"[\[\]]", "", title).strip(), "num": num, "tkey": key,
            "url": str(item.get("itemWebUrl") or "").split("?")[0] or f"https://www.ebay.com.au/itm/{item.get('legacyItemId', '')}",
            "price": price, "post": post, "gst": gst, "total": total, "guessed_post": guessed,
            "market": round(market, 2), "pct": pct, "profit": round(profit, 2),
            "where": ew.COUNTRY.get(country, country), "offers": "BEST_OFFER" in (item.get("buyingOptions") or []),
            "feedback": (seller.get("feedbackPercentage"), seller.get("feedbackScore")),
            "check": total < market * float(s["warn_pct"]) / 100, "image": (item.get("image") or {}).get("imageUrl")}


def is_new(st, d):
    prev = (st.get("seen") or {}).get(d["id"])
    return not prev or d["total"] <= float(prev[0]) * (1 - REALERT_DROP)


# ---------------------------------------------------------------- Discord
def embed(tb, tp, store, d, s):
    it = store["items"][d["tkey"]]
    buy = [f"A${d['price']:,.2f} item"]
    if d["guessed_post"]:
        buy.append(f"~A${float(s['assume_postage']):g} postage (not shown, guessed)")
    else:
        buy.append("free postage" if d["post"] == 0 else f"A${d['post']:,.2f} postage")
    if d["gst"]:
        buy.append(f"A${d['gst']:,.2f} GST (est.)")
    extra = []
    if d["where"]:
        extra.append(f"from {d['where']}")
    if d["offers"]:
        extra.append("accepts offers")
    pct_fb, n_fb = d["feedback"]
    if pct_fb:
        extra.append(f"seller {pct_fb}%" + (f" ({int(n_fb):,})" if str(n_fb).isdigit() else ""))
    lines = [f"[{tb.link_text(d['title'], 120)}]({d['url']})",
             f"**Buy: A${d['total']:,.2f} delivered** ({' + '.join(buy)})",
             f"**TCGplayer market: A${d['market']:,.2f}** (US${it['m']:,.2f}) · "
             f"[{tp.label(store, it, 50)}]({tp.url(d['tkey'])})",
             f"**{d['pct']:.0f}% under · est. profit A${d['profit']:,.2f}** if resold at market after "
             f"{float(s['sell_fee_pct']):g}% fees"]
    if extra:
        lines.append(" · ".join(extra))
    if d["check"]:
        lines.append("⚠️ Very cheap for this card: check the photos are this exact version and it's genuine.")
    e = {"title": f"💰 {d['pct']:.0f}% under · +A${d['profit']:,.0f} · {d['num']}"[:256], "color": GOLD,
         "description": "\n".join(lines)[:4000],
         "footer": {"text": "Deal finder · PC copy · eBay Buy It Now vs TCGplayer US market in A$ · valued as the "
                            "cheapest version the title fits"}}
    if d.get("image"):
        e["thumbnail"] = {"url": d["image"]}
    return e


_no_channel_said = [0.0]


def post(tb, tp, cfg, store, deals, s):
    """To the private channel only, then a phone push for the big ones. True once the deals are handled
    (posted, or logged when there's no private channel yet), so they aren't repeated."""
    alerts = (cfg or {}).get("alerts") or {}
    hook = private_hook(cfg)
    for d in deals:
        print(f"   [deal] {d['pct']:.0f}% under, +A${d['profit']:.0f}: A${d['total']:.2f} vs A${d['market']:.2f} "
              f"· {d['title'][:70]} · {d['url']}")
    if tb.DRY_RUN[0] or not deals:
        return True
    deals = sorted(deals, key=lambda d: -d["profit"])
    ok = True
    if hook:
        for i in range(0, len(deals), 10):
            payload = {"username": alerts.get("bot_name") or "One Piece Restock",
                       "embeds": [embed(tb, tp, store, d, s) for d in deals[i:i + 10]],
                       "allowed_mentions": {"parse": []}}
            ok = tb.discord_send(alerts, hook, payload) and ok
    elif time.time() - _no_channel_said[0] > NO_CHANNEL_EVERY:
        _no_channel_said[0] = time.time()
        tb.post_status(cfg, "💰 The deal finder found something, but your private channel isn't set up yet, so "
                            "it's only in bot_output.log on the PC. Open `/autobuy panel` once to make it.", tb.AMBER)
    big = [d for d in deals if d["profit"] >= float(s["push_min_profit"])]
    if ok and big:
        b = big[0]
        more = f" (+{len(big) - 1} more)" if len(big) > 1 else ""
        tb.push_phone(cfg, f"eBay deal: +A${b['profit']:.0f} on {b['num']}{more}",
                      f"{b['title'][:120]}\nA${b['total']:.2f} delivered vs A${b['market']:.2f} market "
                      f"({b['pct']:.0f}% under)\n{b['url']}")
    return ok


# ---------------------------------------------------------------- one round
def run(tb, cfg, now=None, force=False, every_search=False, quiet=False):
    """One round of eBay searches, if one is due. Returns the deals it found (new or not). Never raises."""
    now = time.time() if now is None else now
    s = settings(cfg)
    if not s["enabled"] or getattr(tb, "IN_ACTIONS", False):
        return []
    st = load_state(tb)
    if not force and now - float(st.get("ts") or 0) < float(s["every_minutes"]) * 60 - 20:
        return []
    if not force and now < float(st.get("pause_until") or 0):
        return []
    cid, secret = ew.credentials(cfg)
    if not cid:
        return []
    try:
        import tcgplayer as tp
        store = tp.load_for(cfg)
    except Exception as e:  # noqa: BLE001
        print(f"   ! deal finder: no TCGplayer prices ({tb.redact(str(e))[:120]})")
        return []
    if not (store or {}).get("items"):
        return []
    idx = price_index(tp, store, s)
    qs = searches(store, s)
    if not qs:
        return []
    n = len(qs) if every_search else min(batch_size(s), len(qs))
    start = int(st.get("i") or 0) % len(qs)
    todo = [qs[(start + j) % len(qs)] for j in range(n)]
    st["ts"] = round(now)
    found, looked = {}, 0
    try:
        for q in todo:
            for item in fetch(cid, secret, q, float(s["min_listing"]), now):
                looked += 1
                d = evaluate(item, idx, s)
                if d and (d["id"] not in found or d["total"] < found[d["id"]]["total"]):
                    found[d["id"]] = d
            st["i"] = (int(st.get("i") or 0) + 1) % len(qs)
    except ew.EbayError as e:
        print(f"   ! deal finder: {e}")
        if e.kind == "limit":
            st["pause_until"] = round(now + LIMIT_PAUSE)
    except Exception as e:  # noqa: BLE001  (a surprise in eBay's reply must never stop the restock checks)
        print(f"   ! deal finder: unexpected {type(e).__name__}: {tb.redact(str(e))[:150]}")
    deals = sorted(found.values(), key=lambda d: -d["profit"])
    new = [d for d in deals if is_new(st, d)]
    if not quiet:
        print(f"   (deal finder: {len(todo)} eBay search(es), {looked} listings, {len(deals)} deal(s), {len(new)} new)")
    if new:
        if post(tb, tp, cfg, store, new, s):
            for d in new:
                st["seen"][d["id"]] = [d["total"], round(now)]
            st["on"] = True
    elif not st.get("on") and not tb.DRY_RUN[0] and private_hook(cfg):
        alerts = (cfg or {}).get("alerts") or {}
        if tb.discord_send(alerts, private_hook(cfg), {
                "username": alerts.get("bot_name") or "One Piece Restock",
                "embeds": [{"color": GREEN, "description": (
                    f"💰 **Deal finder is on.** Every {float(s['every_minutes']):g} minutes it reads the newest One "
                    f"Piece singles on eBay ({len(qs)} searches, taken in turns) and posts here when one is "
                    f"{float(s['min_pct']):g}%+ under TCGplayer's market with at least A${float(s['min_profit']):g} "
                    f"profit after fees. Only you can see this channel.")}],
                "allowed_mentions": {"parse": []}}):
            st["on"] = True
    save_state(tb, st, now)
    return deals


# ---------------------------------------------------------------- try it by hand
def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="eBay deal finder: prints deals now, posts nothing")
    ap.add_argument("--all", action="store_true", help="run every search, not just one round")
    a = ap.parse_args()
    import tcg_bot as tb
    tb.DRY_RUN[0] = True
    cfg = tb.load_config()
    if not ew.credentials(cfg)[0]:
        print("No eBay key yet. The top of ebay_watch.py says how to get one (free).")
        return 1
    deals = run(tb, cfg, force=True, every_search=a.all)
    if not deals:
        print("\nNo deals right now. That's normal: good ones are rare and go fast.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
