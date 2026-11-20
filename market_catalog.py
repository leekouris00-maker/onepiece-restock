"""
Builds market_catalog.json for the One Piece market-data page from tcgplayer_prices.json.

    python market_catalog.py [tcgplayer_prices.json] [market_catalog.json]

Every English One Piece set on TCGplayer (boosters, extra boosters, premium boosters, starter decks,
promos, pre-release cards), each card's TCGplayer market and low price (USD) and its price changes
over the last 35 days. Sealed products are kept too. No Discord, no secrets.

Layout (one record per line, so diffs stay small):
  {"meta": {...}}
  {"sets": [...]}
  {"c": [id, set_id, number, name, rarity, type, market, low, [[days_ago, price], ...]]}
"""
import datetime as dt
import json
import re
import sys

KINDS = [
    (re.compile(r"\bPR$|PROMO", re.I), "promo"),
    (re.compile(r"\sRE$|RELEASE EVENT", re.I), "event"),
    (re.compile(r"PRE\b|PRERELEASE", re.I), "pre-release"),
    (re.compile(r"^PRB", re.I), "premium"),
    (re.compile(r"^EB", re.I), "extra"),
    (re.compile(r"^OP", re.I), "booster"),
    (re.compile(r"^ST", re.I), "starter"),
]


def kind_of(abbr, name):
    for rx, k in KINDS:
        if rx.search(abbr or "") or (k == "promo" and rx.search(name or "")):
            return k
    return "other"


def iso(day):
    try:
        return dt.date.fromordinal(int(day)).isoformat()
    except (TypeError, ValueError, OverflowError):
        return ""


def main(src="tcgplayer_prices.json", out="market_catalog.json"):
    store = json.load(open(src, encoding="utf-8-sig"))
    today = int(store.get("day") or dt.date.today().toordinal())
    fx = store.get("fx") or {}
    groups = store.get("groups") or {}
    sets = []
    for gid, g in groups.items():
        sets.append({"id": str(gid), "code": g.get("a", ""), "name": g.get("n", ""),
                     "date": g.get("d", ""), "kind": kind_of(g.get("a", ""), g.get("n", ""))})
    sets.sort(key=lambda s: (s["date"], s["code"]), reverse=True)

    rows = []
    for pid, it in (store.get("items") or {}).items():
        hist = [[today - d, p] for d, p in (it.get("h") or []) if today - d <= 35 and p is not None]
        rows.append([str(pid).split(":")[0], str(it.get("g", "")), it.get("num") or "", it.get("n", ""),
                     it.get("r") or "", it.get("t") or "card", it.get("m"), it.get("l"), hist])
    rows.sort(key=lambda r: (r[1], r[2], r[3]))

    meta = {"source": "TCGplayer market prices via tcgcsv.com", "updated": iso(today),
            "fx": fx.get("rate"), "fx_date": fx.get("date", ""), "cards": len(rows), "sets": len(sets)}
    with open(out, "w", encoding="utf-8") as f:
        f.write('{"meta": ' + json.dumps(meta, ensure_ascii=False) + ",\n")
        f.write(' "sets": ' + json.dumps(sets, ensure_ascii=False, separators=(",", ":")) + ",\n")
        f.write(' "cards": [\n')
        f.write(",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in rows))
        f.write("\n]}\n")
    print(f"market_catalog.json: {len(rows):,} products in {len(sets)} sets, prices of {meta['updated']}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
