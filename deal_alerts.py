"""eBay deal alerts for the One Piece Market app.

Every couple of hours (.github/workflows/deal-alerts.yml): for each card someone set a deal price on
(watchlist.deal_below, A$), search eBay Australia's live Buy It Now listings with eBay's official Browse
API, keep listings whose price + postage is at or below that price, save them to the `deals` table (shown
in the app) and send a phone notification for each new one. Each listing is announced once per person.

Needs repo secrets EBAY_CLIENT_ID and EBAY_CLIENT_SECRET (a free eBay developer keyset, Production) plus
the SUPABASE_URL / SUPABASE_SERVICE_KEY already used by the other jobs. Optional EBAY_CAMPAIGN_ID (eBay
Partner Network) turns listing links into affiliate links. Without the eBay keys it does nothing.
Listings are filtered to the card's number in the title, raw cards only (no PSA/BGS/CGC), no proxies.
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import push_alerts as P  # noqa: E402  (database helper, notification sender, key pair)

SITE = P.SITE
BAD = re.compile(r"\b(psa|bgs|cgc|beckett|graded|slab|proxy|orica|custom|fan ?art|replica|reprint card|digital|lot of|bundle|x\s?\d{2,})\b", re.I)


def token(cid, secret):
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode()
    auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    req = urllib.request.Request("https://api.ebay.com/identity/v1/oauth2/token", data=body, method="POST",
                                 headers={"Authorization": "Basic " + auth, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["access_token"]


def search(tok, q, max_aud, campaign=None):
    params = {"q": q, "limit": "50", "sort": "price",
              "filter": f"buyingOptions:{{FIXED_PRICE}},price:[..{max_aud:.2f}],priceCurrency:AUD,itemLocationCountry:AU"}
    h = {"Authorization": "Bearer " + tok, "X-EBAY-C-MARKETPLACE-ID": "EBAY_AU", "Accept": "application/json"}
    if campaign:
        h["X-EBAY-C-ENDUSERCTX"] = f"affiliateCampaignId={campaign}"
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
        return json.loads(r.read()).get("itemSummaries") or []


def total_aud(it):
    p = it.get("price") or {}
    if p.get("currency") != "AUD":
        return None
    v = float(p.get("value") or 0)
    ship = (it.get("shippingOptions") or [{}])[0].get("shippingCost") or {}
    if ship.get("currency") == "AUD":
        v += float(ship.get("value") or 0)
    return round(v, 2)


def main():
    cid, secret = os.environ.get("EBAY_CLIENT_ID", "").strip(), os.environ.get("EBAY_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        print("::notice::EBAY_CLIENT_ID / EBAY_CLIENT_SECRET not set: no deal search")
        return 0
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY"):
        print("::notice::no database secrets")
        return 0
    try:
        rows = P.sb("GET", "watchlist?select=user_id,card,deal_below&deal_below=not.is.null") or []
    except RuntimeError as e:
        print(f"::notice::deal alerts not set up in the database yet (run market-app/supabase/2026-11-24b.sql): {e}")
        return 0
    if not rows:
        print("no deal prices set")
        return 0
    cat = json.load(open(os.path.join(HERE, "market_catalog.json")))
    sets = {s["id"]: s for s in cat["sets"]}
    cards = {"t:" + c[0]: c for c in cat["cards"]}
    tok = token(cid, secret)
    campaign = os.environ.get("EBAY_CAMPAIGN_ID", "").strip() or None
    pem, _ = P.keys()
    subs = P.sb("GET", "push_subs?select=endpoint,user_id,sub") or []
    seen = {(r["user_id"], r["item_id"]) for r in (P.sb("GET", "deals?select=user_id,item_id") or [])}

    # one search per card, at the highest deal price anyone set for it
    by = {}
    for r in rows:
        if r["card"] in cards:
            by.setdefault(r["card"], []).append(r)
    found = sent = 0
    for k, people in by.items():
        c = cards[k]
        pid, g, num, name = c[0], c[1], c[2], re.sub(r"\s*\((?:\d{3})\)", "", c[3])
        base = re.sub(r"\s*\(.*$", "", name)
        q = f"one piece {num} {base}".strip()
        sname = (sets.get(g) or {}).get("name", "").lower()
        if "release event" in sname:
            q += " release event"
        if re.search(r"alternate art|parallel", name, re.I):
            q += " alt art"
        if re.search(r"\(sp\)", name, re.I):
            q += " sp"
        if re.search(r"manga", name, re.I):
            q += " manga"
        top = max(float(p["deal_below"]) for p in people)
        try:
            items = search(tok, re.sub(r"[\[\]()!]", " ", q), top, campaign)
        except urllib.error.HTTPError as e:
            print(f"  ! {num}: eBay said {e.code} {e.read().decode()[:160]}")
            continue
        want = num.replace("-", "").lower()
        hits = []
        for it in items:
            title = it.get("title") or ""
            if want not in re.sub(r"[^a-z0-9]", "", title.lower()) or BAD.search(title):
                continue
            t = total_aud(it)
            if t is not None:
                hits.append((t, it))
        for person in people:
            limit = float(person["deal_below"])
            for t, it in hits:
                if t > limit or (person["user_id"], it["itemId"]) in seen:
                    continue
                url = it.get("itemAffiliateWebUrl") or it.get("itemWebUrl")
                img = ((it.get("image") or {}).get("imageUrl")) or None
                P.sb("POST", "deals", [{"user_id": person["user_id"], "card": k, "item_id": it["itemId"], "title": it.get("title"), "price": t,
                                        "url": url, "image": img}], prefer="resolution=ignore-duplicates")
                seen.add((person["user_id"], it["itemId"]))
                found += 1
                payload = {"title": f"Deal: {base} for A${t:,.2f}", "body": f"{num} · your deal price A${limit:,.2f} · {it.get('title', '')[:80]}",
                           "url": url or (SITE + "deals"), "tag": "deal-" + it["itemId"]}
                for s in subs:
                    if s["user_id"] == person["user_id"] and P.send(pem, s["sub"], payload) == "ok":
                        sent += 1
        print(f"{num}: {len(items)} listings under A${top:.0f}, {len(hits)} matched")
    print(f"{found} new deals, {sent} notifications")
    return 0


if __name__ == "__main__":
    sys.exit(main())
