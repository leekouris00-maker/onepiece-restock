"""Long price history for the One Piece Market app (charts beyond 35 days, 90-day highs and lows).

    python long_history.py                 # daily: add today's prices from tcgplayer_prices.json
    python long_history.py --backfill      # once: weekly prices back to Feb 2024 from tcgcsv.com's archives

Writes, for the app:
  price_history/<groupId>.json   {product key: [[day, US$ market], ...]}  (day = date.toordinal(); a point
                                  only when the price changed)
  price_signals.json             {"day": today, "items": {key: [hi90, lo90, avg90, ath, ath_day, then90]}}
  price_history/archives.txt     archive dates already read (each archive is downloaded once, ever)

Product keys match tcgplayer_prices.json / market_catalog.json ("<productId>" or "<productId>:<subtype>").
Only products that have been worth US$0.50+ are kept. Archives: tcgcsv.com, 2-4 MB a day, 7z + PPMd,
inside: <date>/<categoryId>/<groupId>/prices. Their guidelines: custom User-Agent, 100 ms between requests,
download each archive once.
"""
import argparse
import datetime as dt
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "price_history")
DONE = os.path.join(OUT, "archives.txt")
UA = "OnePieceMarket-history/1.0 (+https://github.com/leekouris00-maker/onepiece-restock)"
FIRST = dt.date(2024, 2, 8)
MIN_USD = 0.5


def load_store():
    return json.load(open(os.path.join(HERE, "tcgplayer_prices.json")))


def load_hist():
    hist = {}
    for p in glob.glob(os.path.join(OUT, "*.json")):
        g = os.path.basename(p)[:-5]
        hist[g] = json.load(open(p))
    return hist


def add(series, day, price):
    """Insert a point keeping the list sorted and only change points."""
    if price is None:
        return
    price = round(float(price), 2)
    i = 0
    while i < len(series) and series[i][0] < day:
        i += 1
    if i < len(series) and series[i][0] == day:
        series[i][1] = price
    else:
        series.insert(i, [day, price])
    # drop points equal to the one before
    j = 1
    while j < len(series):
        if series[j][1] == series[j - 1][1]:
            series.pop(j)
        else:
            j += 1


def key_group(store):
    """product key -> group, for products that matter (worth US$0.50+ at some point)"""
    out = {}
    for k, it in store["items"].items():
        ps = [it.get("m")] + [p for _, p in it.get("h") or []]
        if any(p is not None and p >= MIN_USD for p in ps):
            out[k] = str(it.get("g"))
    return out


def seed_recent(store, hist, keys):
    """Today's price and the last 35 days of changes that tcgplayer_prices.json already holds."""
    day = int(store.get("day") or dt.date.today().toordinal())
    for k, g in keys.items():
        it = store["items"][k]
        s = hist.setdefault(g, {}).setdefault(k, [])
        for d, p in it.get("h") or []:
            add(s, int(d), p)
        if it.get("m") is not None:
            add(s, day, it["m"])


def fetch(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as f:
        shutil.copyfileobj(r, f)


def backfill(store, hist, keys, every=7, limit=200):
    cat = int(store.get("category") or 68)
    done = set(open(DONE).read().split()) if os.path.exists(DONE) else set()
    today = dt.date.today()
    want, d = [], FIRST
    while d < today - dt.timedelta(days=36):          # the last 35 days come from tcgplayer_prices.json
        want.append(d)
        d += dt.timedelta(days=every)
    todo = [x for x in want if x.isoformat() not in done][:limit]
    print(f"{len(todo)} archives to read (every {every} days from {FIRST})")
    if not todo:
        return
    if not shutil.which("7z"):
        sys.exit("7z is needed to open the archives (apt install p7zip-full)")
    tmp = tempfile.mkdtemp()
    n = 0
    for day in todo:
        name = f"prices-{day.isoformat()}.ppmd.7z"
        arc = os.path.join(tmp, name)
        ok = False
        for wait in (0, 30, 90):                     # back off politely if the site says "too many requests"
            time.sleep(wait)
            try:
                fetch(f"https://tcgcsv.com/archive/tcgplayer/{name}", arc)
                ok = True
                break
            except Exception as e:  # noqa: BLE001
                print(f"  ! {day}: {e}")
                if "429" not in str(e):
                    break
        if not ok:
            continue
        out = os.path.join(tmp, "x")
        subprocess.run(["7z", "x", "-y", f"-o{out}", arc, f"-ir!*/{cat}/*"], check=False, capture_output=True)
        found = 0
        for pf in glob.glob(os.path.join(out, "*", str(cat), "*", "prices")):
            g = os.path.basename(os.path.dirname(pf))
            try:
                rows = json.load(open(pf)).get("results") or []
            except Exception:  # noqa: BLE001
                continue
            by = {}
            for r in rows:
                if r.get("productId") is not None:
                    by.setdefault(int(r["productId"]), []).append(r)
            for pid, rs in by.items():
                for r in rs:
                    k = str(pid) if len(rs) == 1 else f"{pid}:{r.get('subTypeName') or 'Normal'}"
                    if k not in keys:
                        # the key style can change if a second printing appears later; try the other form
                        alt = f"{pid}:{r.get('subTypeName') or 'Normal'}" if len(rs) == 1 else str(pid)
                        if alt not in keys:
                            continue
                        k = alt
                    add(hist.setdefault(keys[k], {}).setdefault(k, []), day.toordinal(), r.get("marketPrice"))
                    found += 1
        shutil.rmtree(out, ignore_errors=True)
        os.remove(arc)
        done.add(day.isoformat())
        n += 1
        print(f"  {day}: {found} prices")
        time.sleep(1.5)
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)
    open(DONE, "w").write("\n".join(sorted(done)) + "\n")
    print(f"read {n} archives")


def signals(store, hist):
    """Per product: 90-day high, low and average, all-time high (and when), price 90 days ago."""
    today = int(store.get("day") or dt.date.today().toordinal())
    out = {}
    for g, items in hist.items():
        for k, s in items.items():
            if not s:
                continue
            last = s[-1][1]
            # daily values over the last 90 days (prices hold until the next change)
            vals, j, cur = [], 0, None
            for d in range(today - 90, today + 1):
                while j < len(s) and s[j][0] <= d:
                    cur = s[j][1]
                    j += 1
                if cur is not None:
                    vals.append(cur)
            if not vals:
                vals = [last]
            ath = max(s, key=lambda p: p[1])
            then = vals[0]
            out[k] = [max(vals), min(vals), round(sum(vals) / len(vals), 2), ath[1], ath[0], then]
    return {"day": today, "items": out}


def save(hist, sig):
    os.makedirs(OUT, exist_ok=True)
    for g, items in hist.items():
        items = {k: v for k, v in items.items() if v}
        # one product per line, so each day's git change stays small
        lines = [json.dumps(k) + ":" + json.dumps(items[k], separators=(",", ":")) for k in sorted(items)]
        with open(os.path.join(OUT, f"{g}.json"), "w") as f:
            f.write("{\n" + ",\n".join(lines) + "\n}\n")
    with open(os.path.join(HERE, "price_signals.json"), "w") as f:
        json.dump(sig, f, separators=(",", ":"), sort_keys=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true", help="read tcgcsv.com's archives (once)")
    ap.add_argument("--every", type=int, default=7, help="days between archive points when back-filling")
    ap.add_argument("--limit", type=int, default=200, help="most archives to read in one run")
    a = ap.parse_args()
    store = load_store()
    keys = key_group(store)
    hist = load_hist()
    if a.backfill:
        backfill(store, hist, keys, a.every, a.limit)
    seed_recent(store, hist, keys)
    sig = signals(store, hist)
    save(hist, sig)
    pts = sum(len(v) for g in hist.values() for v in g.values())
    print(f"{sum(len(g) for g in hist.values())} products, {pts} price points, signals for {len(sig['items'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
