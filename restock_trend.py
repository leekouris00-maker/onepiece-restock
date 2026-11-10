#!/usr/bin/env python3
"""
Restock trends per shop for the One Piece restock bot (/restocks in Discord, v2.18)
==================================================================================
Answers "which shops restock, how often, is it getting better or worse, and how long does the stock last?"

Where the numbers come from: events.jsonl, which the bot already writes on every check. Each time a
booster box, watched sealed product or Pokémon product goes from not buyable to buyable it logs an
"in_stock" line, and a "sold_out" line (with how long it was buyable) when it goes again. Nothing here
talks to a shop.

How a restock is counted:
  * One restock = one shop putting stock up. Products that come in at the same shop within an hour of each
    other are ONE restock (a shop loading five boxes at 7pm is one drop, not five), and the products are
    listed under it.
  * Trend = restocks in the period asked for (30 days by default) against the period before it. If the bot
    wasn't logging for the whole earlier period, there is no comparison yet ("building history").
  * "Every ~N days" = the median gap between restocks. "Lasts" = the median time products stayed buyable.
  * "Next, roughly" = last restock + the usual gap. Only shown with 3+ restocks, and it is a pattern, not
    a promise.

Each copy of the bot (PC, cloud) has its own events.jsonl, so /restocks shows what that copy saw.

Try it (prints the overview and one shop; posts nothing):
    py -3 restock_trend.py
    py -3 restock_trend.py Pokebox
"""
import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime

GAP = 3600                  # in-stock lines at one shop within this many seconds = one restock
WEEKS = 8                   # the weekly sparkline covers this many weeks
SPARK = "▁▂▃▄▅▆▇█"
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
GAMES = {"all": None, "onepiece": "One Piece", "pokemon": "Pokémon"}


def game_of(event):
    return "Pokémon" if str(event.get("id", "")).startswith("poke|") else "One Piece"


def spark(values):
    if not values:
        return ""
    hi = max(values)
    if hi <= 0:
        return SPARK[0] * len(values)
    return "".join(SPARK[round(v / hi * (len(SPARK) - 1))] for v in values)


def restocks(events, game=None, gap=GAP):
    """The in-stock lines grouped into restocks, oldest first:
    [{"shop", "t", "end", "game", "items": [{"id", "name", "price", "lasted"}]}].
    "lasted" is seconds the product stayed buyable (None while it still is, or if the bot never saw it go)."""
    ins = sorted((e for e in events if e.get("event") == "in_stock" and e.get("shop") and e.get("t")),
                 key=lambda e: e["t"])
    if game:
        ins = [e for e in ins if game_of(e) == game]
    outs = defaultdict(list)
    for e in events:
        if e.get("event") == "sold_out" and e.get("id") and e.get("t"):
            outs[e["id"]].append(e)
    for v in outs.values():
        v.sort(key=lambda e: e["t"])
    open_by_shop, out = {}, []
    for e in ins:
        sold = next((o for o in outs.get(e.get("id"), ()) if o["t"] >= e["t"]), None)
        lasted = None
        if sold:
            lasted = sold.get("was") or (sold["t"] - e["t"])
        item = {"id": e.get("id"), "name": e.get("name") or "(no name)", "price": e.get("price"), "lasted": lasted}
        r = open_by_shop.get(e["shop"])
        if r and e["t"] - r["end"] <= gap:
            r["end"] = e["t"]
            if not any(i["id"] == item["id"] for i in r["items"]):
                r["items"].append(item)
            continue
        r = {"shop": e["shop"], "t": e["t"], "end": e["t"], "game": game_of(e), "items": [item]}
        open_by_shop[e["shop"]] = r
        out.append(r)
    return out


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _top(counter):
    """The most common value, only if it happened at least twice (one-offs aren't a pattern)."""
    if not counter:
        return None
    k, n = counter.most_common(1)[0]
    return (k, n) if n >= 2 else None


def trend_label(n, prev, have_prev):
    if not have_prev:
        return "building history"
    if prev == 0:
        return "new" if n else "none"
    pct = round((n - prev) / prev * 100)
    if abs(pct) < 15:
        return "→ steady"
    return f"{'↑' if pct > 0 else '↓'} {pct:+d}%"


def shop_stats(rs, days=30, now=None, data_since=None):
    """Per-shop numbers for restocks `rs` (from restocks()), the newest `days` days against the `days` before.
    Returns a list sorted busiest first."""
    now = now or time.time()
    span = days * 86400
    start, prev_start = now - span, now - 2 * span
    have_prev = data_since is not None and data_since <= prev_start + 86400   # a day's slack
    weeks = WEEKS                    # don't chart weeks from before the bot was logging
    if data_since is not None:
        weeks = max(1, min(WEEKS, -(-int(now - data_since) // (7 * 86400))))
    by_shop = defaultdict(list)
    for r in rs:
        by_shop[r["shop"]].append(r)
    out = []
    for shop, lst in by_shop.items():
        cur = [r for r in lst if r["t"] >= start]
        prev = [r for r in lst if prev_start <= r["t"] < start]
        if not cur and not prev:
            continue
        ts = [r["t"] for r in lst if r["t"] >= prev_start]
        gaps = [(b - a) / 86400 for a, b in zip(ts, ts[1:])]
        weekly = [sum(1 for r in lst if now - (w + 1) * 7 * 86400 <= r["t"] < now - w * 7 * 86400)
                  for w in reversed(range(weeks))]
        when = [datetime.fromtimestamp(r["t"]) for r in cur]
        last = max(r["t"] for r in lst)
        gap = _median(gaps)
        out.append({
            "shop": shop,
            "count": len(cur),
            "prev": len(prev),
            "trend": trend_label(len(cur), len(prev), have_prev),
            "products": sum(len(r["items"]) for r in cur),
            "weekly": weekly,
            "spark": spark(weekly),
            "gap_days": gap,
            "lasted_min": (lambda m: m / 60 if m is not None else None)(
                _median([i["lasted"] for r in cur for i in r["items"]])),
            "day": _top(Counter(DAYS[d.weekday()] for d in when)) if len(when) >= 3 else None,
            "hour": _top(Counter(d.hour for d in when)) if len(when) >= 3 else None,
            "last": last,
            "next": last + gap * 86400 if gap is not None and len(ts) >= 3 else None,
            "games": sorted({r["game"] for r in cur or prev}),
            "recent": sorted(lst, key=lambda r: -r["t"])[:6],
        })
    out.sort(key=lambda s: (-s["count"], -s["last"]))
    return out


def find_shop(stats, name):
    """The shop someone typed: exact (any case) first, then the one whose name contains it."""
    q = (name or "").strip().lower()
    if not q:
        return None
    for s in stats:
        if s["shop"].lower() == q:
            return s
    hits = [s for s in stats if q in s["shop"].lower()]
    return hits[0] if hits else None


def shop_names(events):
    return sorted({e["shop"] for e in events if e.get("event") == "in_stock" and e.get("shop")}, key=str.lower)


def data_since(events):
    ts = [e["t"] for e in events if e.get("t")]
    return min(ts) if ts else None


# ---------------------------------------------------------------- words
def ago(ts, now=None):
    s = max(0, (now or time.time()) - ts)
    if s < 3600:
        return f"{int(s // 60)} min ago"
    if s < 86400 * 2:
        return f"{int(s // 3600)} h ago"
    return f"{int(s // 86400)} days ago"


def duration(minutes):
    if minutes is None:
        return "?"
    if minutes < 90:
        return f"{minutes:.0f} min"
    if minutes < 60 * 48:
        return f"{minutes / 60:.1f} h"
    return f"{minutes / 1440:.1f} days"


def every(gap_days):
    if gap_days is None:
        return None
    if gap_days < 1:
        return f"every ~{gap_days * 24:.0f} h"
    return f"every ~{gap_days:.0f} day{'s' if round(gap_days) != 1 else ''}"


def next_guess(ts, now=None):
    now = now or time.time()
    if ts is None:
        return None
    if ts <= now:
        return "due now (past its usual gap)"
    d = datetime.fromtimestamp(ts)
    return f"around {DAYS[d.weekday()]} {d:%d %b}"


def overview_line(s, now=None):
    bits = [f"**{s['shop']}** · {s['count']} restock{'s' if s['count'] != 1 else ''} ({s['trend']})"]
    if any(s["weekly"]):
        bits.append(s["spark"])
    if every(s["gap_days"]):
        bits.append(every(s["gap_days"]))
    if s["lasted_min"] is not None:
        bits.append(f"lasts ~{duration(s['lasted_min'])}")
    bits.append(f"last {ago(s['last'], now)}")
    return " · ".join(bits)


def _money(x):
    try:
        return f"${float(x):,.2f}"
    except (TypeError, ValueError):
        return "?"


def recent_lines(s, now=None, limit=6):
    out = []
    for r in s["recent"][:limit]:
        d = datetime.fromtimestamp(r["t"])
        items = r["items"]
        first = items[0]
        name = first["name"] if len(first["name"]) <= 55 else first["name"][:54] + "…"
        more = f" +{len(items) - 1} more" if len(items) > 1 else ""
        lasted = [i["lasted"] for i in items if i["lasted"]]
        gone = f" · gone after {duration(max(lasted) / 60)}" if lasted else " · may still be in stock"
        out.append(f"{DAYS[d.weekday()]} {d:%d %b %I:%M %p} · {name} {_money(first['price'])}{more}{gone}")
    return out


def overview_text(stats, days, now=None):
    return [overview_line(s, now) for s in stats]


def detail_fields(s, days, now=None):
    """[(name, value)] for one shop."""
    lines = [f"**{s['count']}** restock{'s' if s['count'] != 1 else ''} in the last {days} days "
             f"({s['products']} product{'s' if s['products'] != 1 else ''}), {s['prev']} in the {days} before: "
             f"**{s['trend']}**"]
    if every(s["gap_days"]):
        lines.append(f"Restocks {every(s['gap_days'])}")
    if s["lasted_min"] is not None:
        lines.append(f"Stock usually lasts **{duration(s['lasted_min'])}**")
    lines.append(f"Last restock {ago(s['last'], now)}")
    fields = [("📈 Trend", "\n".join(lines)),
              (f"🗓️ Last {len(s['weekly'])} week{'s' if len(s['weekly']) != 1 else ''} (oldest → this week)",
               f"{s['spark']}  " + " ".join(str(n) for n in s["weekly"]))]
    when = []
    if s["day"]:
        when.append(f"Busiest day: **{s['day'][0]}** ({s['day'][1]})")
    if s["hour"]:
        h = s["hour"][0]
        when.append(f"Busiest hour: **{datetime(2000, 1, 1, h):%I %p}** ({s['hour'][1]})")
    nxt = next_guess(s["next"], now)
    if nxt:
        when.append(f"Next, roughly: **{nxt}**")
    fields.append(("🕐 When", "\n".join(when) if when else "No pattern yet (needs a few restocks on the same day or hour)."))
    fields.append(("🧾 Recent restocks", "\n".join(recent_lines(s, now)) or "-"))
    return fields


# ---------------------------------------------------------------- command line
def _read(path):
    out = []
    for p in (path + ".1", path):
        try:
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
        except OSError:
            pass
    return out


if __name__ == "__main__":
    here = os.environ.get("BOT_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
    ev = _read(os.path.join(here, "events.jsonl"))
    st = shop_stats(restocks(ev), 30, data_since=data_since(ev))
    if len(sys.argv) > 1:
        s = find_shop(st, " ".join(sys.argv[1:]))
        if not s:
            sys.exit(f"No restocks logged for a shop matching {' '.join(sys.argv[1:])!r}.")
        for name, value in detail_fields(s, 30):
            print(f"\n{name}\n{value}")
    else:
        print("\n".join(overview_text(st, 30)) or "No restocks logged yet.")
