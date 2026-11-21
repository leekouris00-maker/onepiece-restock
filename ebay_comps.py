"""
eBay sold prices (comps) for the cards Lee tracks on the One Piece Market page, from CompsAPI
(compsapi.com, free tier: 100 searches a month).

    COMPSAPI_KEY=... python ebay_comps.py [--max N] [--dry-run]

- Tracked cards: ebay_comps_watch.json, a list of {"id", "q", "lang", "graded"} written from the
  page's "Track eBay sold" button (the daily Claude task copies it here).
- Results: ebay_comps.json, {"updated", "usage", "items": {id: {...}}}.
- Each run refreshes at most --max cards (default 3): never-fetched ones first, then the stalest,
  and only those older than REFRESH_DAYS. It checks the month's remaining quota first (that call is
  free) and keeps RESERVE searches spare. Prices from CompsAPI are USD.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.compsapi.com/v1"
UA = "onepiece-market/1.0 (personal price tracker)"
REFRESH_DAYS = 7
RESERVE = 5
WATCH, OUT = "ebay_comps_watch.json", "ebay_comps.json"


def call(path, key, **params):
    url = f"{API}/{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"X-API-Key": key, "User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            body = {}
        return {"ok": False, "error": body.get("error") or f"HTTP {e.code}"}


def remaining(usage):
    """Searches left this month, from /v1/usage (field names guessed defensively)."""
    for k in ("requests_remaining", "remaining", "requests_left"):
        if isinstance(usage.get(k), (int, float)):
            return int(usage[k])
    for k in ("requests", "quota", "usage"):
        v = usage.get(k)
        if isinstance(v, dict):
            for a, b in (("remaining", None), ("left", None)):
                if isinstance(v.get(a), (int, float)):
                    return int(v[a])
            lim, used = v.get("limit"), v.get("used")
            if isinstance(lim, (int, float)) and isinstance(used, (int, float)):
                return int(lim - used)
    return None


def load(path, default):
    try:
        return json.load(open(path, encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def slim(resp):
    st = resp.get("stats") or {}
    sales = []
    for it in (resp.get("items") or [])[:10]:
        card = it.get("card") or {}
        sales.append({"title": (it.get("title") or "")[:140], "url": it.get("url") or "", "price": it.get("price"),
                      "sold": (it.get("last_sold") or "")[:10], "offer": bool(it.get("best_offer")),
                      "grade": " ".join(str(x) for x in (card.get("grader"), card.get("grade")) if x) if card.get("graded") else "Raw"})
    return {"count": st.get("count", resp.get("count", 0)), "median": st.get("median"), "p25": st.get("p25"),
            "p75": st.get("p75"), "min": st.get("min"), "max": st.get("max"), "newest": (st.get("newest_sale") or "")[:10],
            "sales": sales, "none": bool(resp.get("no_results"))}


def supabase_watch():
    """Tracked cards from the iPhone app's database (Supabase), if SUPABASE_URL and SUPABASE_SERVICE_KEY are set."""
    url, key = os.environ.get("SUPABASE_URL", "").rstrip("/"), os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not (url and key):
        return []
    req = urllib.request.Request(f"{url}/rest/v1/watch?select=card,q,lang,graded,updated_at",
                                 headers={"apikey": key, "Authorization": f"Bearer {key}", "User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            rows = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"  ! couldn't read tracked cards from the app's database: {e}")
        return []
    return [{"id": x["card"], "q": x["q"], "lang": x.get("lang"), "graded": x.get("graded"), "asked": x.get("updated_at")}
            for x in rows if x.get("card") and x.get("q")]


AUTO_MAX = 15        # owned cards looked up automatically (most valuable first); the free plan covers ~20 a week


def supabase_owned():
    """Cards people own in the app (TCGplayer cards only), so their eBay sold prices are looked up without
    anyone pressing Track. Needs the same SUPABASE_URL / SUPABASE_SERVICE_KEY secrets."""
    url, key = os.environ.get("SUPABASE_URL", "").rstrip("/"), os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not (url and key):
        return []
    req = urllib.request.Request(f"{url}/rest/v1/owned?select=card,lang,qty&status=eq.owned&card=like.t%3A*",
                                 headers={"apikey": key, "Authorization": f"Bearer {key}", "User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"  ! couldn't read owned cards from the app's database: {e}")
        return []


def auto_watch(owned, catalog, skip):
    """[{id, q, lang, graded, auto}] for the most valuable owned cards nobody tracks yet."""
    cards = {"t:" + str(c[0]): c for c in (catalog.get("cards") or [])}
    sets = {}
    for g in catalog.get("sets") or []:
        if isinstance(g, dict):
            sets[str(g.get("id"))] = g.get("name") or ""
        elif isinstance(g, (list, tuple)) and len(g) > 1:
            sets[str(g[0])] = str(g[1])
    by = {}
    for o in owned:
        c = cards.get(o.get("card"))
        if not c or o["card"] in skip:
            continue
        e = by.setdefault(o["card"], {"qty": 0, "langs": set(), "c": c})
        e["qty"] += int(o.get("qty") or 1)
        e["langs"].add((o.get("lang") or "EN").upper())
    out = []
    for k, e in by.items():
        pid, _g, num, name, _r, kind, m = e["c"][:7]
        if (m or 0) < 1:                      # under US$1: not worth a search
            continue
        name = re.sub(r"\s*\((?:\d{3})\)", "", name)
        q = re.sub(r"[\[\]()!]", " ", f"one piece {num} {name}" if num else f"one piece {name}")
        setname = sets.get(str(_g), "").lower()   # special printings share the number: say which one
        for word, extra in (("pre-release", "pre-release"), ("release event", "release event"), ("treasure cup", "treasure cup")):
            if word in setname and extra not in q.lower():
                q += " " + extra
        jp = e["langs"] == {"JP"}             # only Japanese copies owned: search Japanese sales
        out.append({"id": k, "q": re.sub(r"\s+", " ", q).strip(), "lang": "ja" if jp else None,
                    "graded": None if kind == "sealed" else False, "auto": True, "value": (m or 0) * e["qty"]})
    return sorted(out, key=lambda w: -w["value"])[:AUTO_MAX]


def when(t):
    """ISO time from the app or this file -> aware datetime (bad values sort as long ago)."""
    try:
        d = dt.datetime.fromisoformat(str(t).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("COMPSAPI_KEY", "").strip()
    watch = load(WATCH, [])
    seen = {w.get("id") for w in watch}
    watch += [w for w in supabase_watch() if w["id"] not in seen]   # the app's tracked cards
    watch += auto_watch(supabase_owned(), load("market_catalog.json", {}), {w["id"] for w in watch})
    out = load(OUT, {"items": {}})
    items = out.setdefault("items", {})
    ids = {w["id"] for w in watch if w.get("id") and w.get("q")}
    for gone in [k for k in items if k not in ids]:
        del items[gone]                       # untracked on the page
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date().isoformat()

    def age(w):
        at = (items.get(w["id"]) or {}).get("at")
        q_changed = (items.get(w["id"]) or {}).get("q") != w["q"]
        if not at or q_changed:
            return 10 ** 6
        if w.get("asked") and when(w["asked"]) > when(at):   # "Refresh" pressed in the app since the last lookup
            return 10 ** 6
        return (now.date() - dt.date.fromisoformat(at[:10])).days

    # cards someone pressed Track on come first, then owned cards (most valuable first), stalest first within each
    due = sorted((w for w in watch if w.get("id") and w.get("q") and age(w) >= REFRESH_DAYS),
                 key=lambda w: (bool(w.get("auto")), -min(age(w), 10 ** 5), -w.get("value", 0)))
    n_auto = sum(1 for w in watch if w.get("auto"))
    print(f"{len(ids)} card(s): {len(ids) - n_auto} tracked + {n_auto} owned (automatic); {len(due)} due for a refresh")
    if not key:
        print("::notice::COMPSAPI_KEY isn't set, so no eBay prices were fetched. Add it under Settings > Secrets > Actions.")
        return 0
    if not due:
        return 0
    usage = call("usage", key)
    left = remaining(usage)
    out["usage"] = {k: v for k, v in usage.items() if k not in ("ok",)} if usage.get("ok", True) else {"error": usage.get("error")}
    budget = a.max if left is None else max(0, min(a.max, left - RESERVE))
    print(f"searches left this month: {left if left is not None else 'unknown'}; using up to {budget}")
    for w in due[:budget]:
        params = {"q": w["q"][:300], "days": 90, "exclude": "junk", "best_offer": 1}   # accepted-offer prices
        if w.get("lang") in ("ja", "zh", "ko"):      # "en" would drop titles that don't say English
            params["lang"] = w["lang"]
        if w.get("graded") in (True, False):
            params["graded"] = "true" if w["graded"] else "false"
        if a.dry_run:
            print("would search:", params)
            continue
        resp = call("comps", key, **params)
        if not resp.get("ok", True):
            print(f"  ! {w['q']}: {resp.get('error')}")
            continue
        items[w["id"]] = {"q": w["q"], "at": now.isoformat(timespec="minutes"), **({"auto": True} if w.get("auto") else {}), **slim(resp)}
        r = items[w["id"]]
        print(f"  {w['q']}: {r['count']} sales, median US${r['median']}")
        time.sleep(7)                         # free tier: 10 searches a minute
    out["updated"] = today
    if not a.dry_run:
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
