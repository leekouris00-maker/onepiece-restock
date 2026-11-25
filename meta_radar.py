#!/usr/bin/env python3
"""Meta Radar: what's winning in One Piece tournaments on Limitless TCG, for the One Piece Market app.

Reads recent One Piece (game=OP) tournaments from the Limitless TCG API, takes the top 8 decklists of each
event with 16+ players, and compares the last 14 days with the 14 days before:
  - leaders: share of top-8 decks per leader / deck type
  - rising / falling: cards whose share of top-8 decklists moved the most
Writes meta.json (the app shows it on the Ban & Meta page and in the Morning Log).

Data: Limitless TCG (https://play.limitlesstcg.com), credited in the app. Optional secret LIMITLESS_KEY
(their docs say an access key is needed for the API; it's sent as X-Access-Key if set).
Gentle on their servers: one request every ~6.5 s (well under 50 per 5 minutes), at most ~40 requests a run.
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://play.limitlesstcg.com/api"
OUT = os.path.join(HERE, "meta.json")
CARD = re.compile(r"(?<![A-Z0-9])((?:OP|ST|EB|PRB)\d{2}-\d{3}|P-\d{3})(?![0-9])", re.I)
MIN_PLAYERS, TOP, WINDOW, MAX_EVENTS = 16, 8, 14, 30


def get(path):
    req = urllib.request.Request(API + path, headers={"User-Agent": "OnePieceMarket/1.0 (+https://leekouris00-maker.github.io/onepiece-restock/)", "Accept": "application/json"})
    if os.environ.get("LIMITLESS_KEY"):
        req.add_header("X-Access-Key", os.environ["LIMITLESS_KEY"].strip())
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    time.sleep(6.5)
    return data


def cards_in(decklist):
    """Card numbers + counts from a decklist, whatever shape Limitless uses for One Piece."""
    found = {}
    def walk(x, count=None):
        if isinstance(x, dict):
            n = x.get("count") or x.get("amount") or x.get("qty")
            st, nu = x.get("set") or x.get("set_code"), x.get("number") or x.get("num")
            if isinstance(st, str) and nu is not None and not CARD.search(str(nu)):
                k = f"{st.upper()}-{str(nu).zfill(3)}" if re.match(r"^(OP|ST|EB|PRB)\d{2}$", st, re.I) else None
                if k:
                    found[k] = max(found.get(k, 0), n if isinstance(n, int) else 1)
            for v in x.values():
                walk(v, n if isinstance(n, int) else count)
        elif isinstance(x, list):
            for v in x:
                walk(v, count)
        elif isinstance(x, str):
            for m in CARD.finditer(x):
                k = m.group(1).upper()
                found[k] = max(found.get(k, 0), count or 1)
    walk(decklist)
    return found


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        events = []
        for page in (1, 2):
            batch = get(f"/tournaments?game=OP&limit=50&page={page}")
            if not isinstance(batch, list) or not batch:
                break
            events += batch
        print(f"{len(events)} One Piece tournaments listed")
    except urllib.error.HTTPError as e:
        msg = f"Limitless API refused the request ({e.code}). It may need an access key: add LIMITLESS_KEY as a repo secret."
        print("::warning::" + msg)
        json.dump({"updated": now.isoformat(timespec="seconds"), "error": msg}, open(OUT, "w"), indent=1)
        return 0
    except Exception as e:
        print(f"::warning::Limitless not reachable: {e}")
        return 0

    def age(t):
        try:
            return (now - datetime.datetime.fromisoformat(t["date"].replace("Z", "+00:00"))).days
        except Exception:
            return 999
    use = [t for t in events if (t.get("players") or 0) >= MIN_PLAYERS and age(t) < WINDOW * 2]
    use.sort(key=lambda t: t["date"], reverse=True)
    use = use[:MAX_EVENTS]
    print(f"{len(use)} events with {MIN_PLAYERS}+ players in the last {WINDOW * 2} days")

    windows = {"now": [], "before": []}
    shown = [False]
    leader_names = {}
    for t in use:
        try:
            st = get(f"/tournaments/{t['id']}/standings")
        except Exception as e:
            print(f"  {t['name']}: standings failed ({e})")
            continue
        w = "now" if age(t) < WINDOW else "before"
        n = 0
        for s in st if isinstance(st, list) else []:
            if not s.get("placing") or s["placing"] > TOP or not s.get("decklist"):
                continue
            deck = s.get("deck") or {}
            lead = deck.get("name") or deck.get("id") or "Unknown"
            cs = cards_in(s["decklist"])
            if not cs and not shown[0]:
                print("  sample decklist (no card numbers found):", json.dumps(s["decklist"])[:600])
                shown[0] = True
            windows[w].append({"leader": lead, "cards": cs})
            leader_names[lead] = lead
            n += 1
        print(f"  {t['date'][:10]} {t['name'][:50]} ({t['players']} players): {n} top decks")

    def shares(decks, key):
        tot = len(decks) or 1
        out = {}
        for d in decks:
            for k in key(d):
                out[k] = out.get(k, 0) + 1
        return {k: v / tot for k, v in out.items()}
    now_d, before_d = windows["now"], windows["before"]
    lead_now = shares(now_d, lambda d: [d["leader"]])
    lead_before = shares(before_d, lambda d: [d["leader"]])
    card_now = shares(now_d, lambda d: d["cards"].keys())
    card_before = shares(before_d, lambda d: d["cards"].keys())
    moves = []
    for k in set(card_now) | set(card_before):
        a, b = card_now.get(k, 0), card_before.get(k, 0)
        if max(a, b) >= 0.1:
            moves.append({"num": k, "rate": round(a, 3), "prev": round(b, 3), "delta": round(a - b, 3)})
    rising = sorted([m for m in moves if m["delta"] > 0.05], key=lambda m: -m["delta"])[:15]
    falling = sorted([m for m in moves if m["delta"] < -0.05], key=lambda m: m["delta"])[:10]
    leaders = sorted(({"name": k, "share": round(v, 3), "prev": round(lead_before.get(k, 0), 3)} for k, v in lead_now.items()), key=lambda x: -x["share"])[:12]
    out = {
        "updated": now.isoformat(timespec="seconds"), "source": "Limitless TCG", "source_url": "https://play.limitlesstcg.com/tournaments?game=OP",
        "window_days": WINDOW, "top": TOP, "min_players": MIN_PLAYERS,
        "events": len(use), "decks_now": len(now_d), "decks_before": len(before_d),
        "leaders": leaders, "rising": rising, "falling": falling,
        "note": "Online community tournaments on Limitless; official paper events aren't included.",
    }
    json.dump(out, open(OUT, "w"), indent=1)
    print(f"wrote meta.json: {len(now_d)} decks now, {len(before_d)} before, {len(rising)} rising cards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
