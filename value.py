"""
/value: what a single is worth at the shops right now, and its price over the last week (v2.7; TCGplayer line v2.8)
=============================================================================================

    /value card:OP13-120          every version of that card number
    /value card:sabo wanted       narrow it down with words from the name or the version
    /value card:<pick from list>  one exact version: a line per shop on the chart
    /value card:... days:3        a shorter window (1 to 7 days)

Nothing is fetched: it reads the restock bot's own record of every single's near-mint price at
Elemental Arcade and Good Games (singles_prices.json, read about once an hour for the price drops).
That record keeps 8 days of changes (DROPS_KEEP_HOURS), so a week's chart always has its start.

The chart is a PNG made with matplotlib (py -3 -m pip install matplotlib). Without matplotlib the
command still works and shows a text sparkline instead of the picture.
"""
import io
import os
import re
import time
from datetime import datetime, timedelta

import tcg_bot as tb

MAX_DAYS = 7
MAX_LINES = 6                # lines on one chart; more versions than this are listed but not drawn
NUM_RE = tb.CARD_NUM_RE
GOLD = 0xE9C46A

# Chart colours: the validated categorical order, dark steps (Discord is usually dark), on a dark surface.
SURFACE = "#1a1a19"
INK, INK_2, INK_3, GRID = "#f0efec", "#c3c2b7", "#8f8e86", "#33332f"
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#9085e9"]

ABBREV = {"sp", "tr", "sec", "sr", "uc", "jp", "en", "psa", "don!!", "op"}
VARIANT_SYNONYMS = {"alt art": "alternate art", "parallel": "alternate art", "aa": "alternate art",
                    "special": "sp", "special art": "sp"}


# ---------------------------------------------------------------- reading the record
_store_cache = {"mtime": None, "store": None}


def load_store():
    """singles_prices.json, re-read only when the restock bot has written it since last time."""
    try:
        mtime = os.path.getmtime(tb.DROPS_PATH)
    except OSError:
        mtime = None
    if _store_cache["store"] is None or mtime != _store_cache["mtime"]:
        _store_cache.update(store=tb.load_drops_store(), mtime=mtime, groups=None)
    return _store_cache["store"]


def parse_name(name):
    """A shop title -> (card number, base name, version).
    'Sabo - OP13-120 (Wanted Poster) [Carrying On His Will]'      (Elemental Arcade)
    'Sabo (Wanted Poster) [Carrying On His Will] (OP13-120)'      (Good Games)
    both -> ('OP13-120', 'Sabo', 'wanted poster')."""
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    m = NUM_RE.search(name)
    num = m.group(0).upper() if m else ""
    versions = []
    for p in re.findall(r"\(([^()]*)\)", name):
        p = p.strip().lower()
        if p and not NUM_RE.fullmatch(p):
            versions.append(VARIANT_SYNONYMS.get(p, p))
    base = re.sub(r"\[[^\]]*\]|\([^()]*\)", " ", name)
    if num:
        base = re.sub(re.escape(m.group(0)), " ", base, flags=re.I)
    base = re.sub(r"\s+", " ", base.replace(" - ", " ")).strip(" -")
    return num, base, " ".join(versions)


def set_name(name):
    """The set in square brackets, the same way at both shops: 'Starter Deck 22: Ace & Newgate' and
    'Starter Deck: Ace & Newgate' -> 'starter deck: ace & newgate'. Reprints of a card number in another
    set (a Premium Booster alt art, a deck-set Arlong) are worth different amounts, so they're kept apart."""
    sets = re.findall(r"\[([^\]]*)\]", str(name or ""))
    s = re.sub(r"\s+", " ", sets[-1].strip().lower()) if sets else ""
    return re.sub(r"^starter deck \d+:", "starter deck:", s)[:40]


def group_key(name):
    num, base, version = parse_name(name)
    return f"{num or base.lower()}|{version}|{set_name(name)}"


def nice_version(version):
    """'alternate art' -> 'Alternate Art', 'sp' -> 'SP', 'tr' -> 'TR'."""
    if not version:
        return "Regular"
    return " ".join(w.upper() if w in ABBREV else (w[:1].upper() + w[1:]) for w in version.split())


def group_label(name):
    num, base, version = parse_name(name)
    return " ".join(x for x in (base, num) if x) + f" · {nice_version(version)}"


def groups(store):
    """{group key: {"label", "items": [(item key, item)], "hay"}}: the same card and version at every shop."""
    if store is _store_cache.get("store") and _store_cache.get("groups") is not None:
        return _store_cache["groups"]
    out = {}
    for key, it in (store.get("items") or {}).items():
        if not it.get("p"):
            continue
        name = it.get("n") or key.partition("|")[2]
        g = out.setdefault(group_key(name), {"label": group_label(name), "items": [], "hay": ""})
        g["items"].append((key, it))
        num = parse_name(name)[0]
        g["hay"] += f" {name} {g['label']} {num.replace('-', '')} {key.partition('|')[0]}".lower()
    # the same card number and version from two sets: say which set each is
    seen = {}
    for k in out:
        seen.setdefault(k.rsplit("|", 1)[0], []).append(k)
    for ks in seen.values():
        if len(ks) > 1:
            for k in ks:
                st = k.rsplit("|", 1)[1]
                if st:
                    out[k]["label"] += " · " + re.sub(r"\b(\w)", lambda m: m.group(1).upper(), st)
                    out[k]["hay"] += " " + st
    if store is _store_cache.get("store"):
        _store_cache["groups"] = out
    return out


def find(store, query):
    """Group keys matching what was typed: the exact key (picked from the autocomplete list), else every
    group whose names hold all the words."""
    gs = groups(store)
    q = str(query or "").strip()
    if q in gs:
        return [q]
    words = [w for w in re.split(r"[^a-z0-9]+", q.lower()) if w]
    if not words:
        return []
    joined = re.sub(r"[^a-z0-9]", "", q.lower())
    hits = []
    for k, g in gs.items():
        if all(w in g["hay"] for w in words) or (len(joined) >= 6 and joined in g["hay"].replace("-", "")):
            hits.append(k)
    return hits


# ---------------------------------------------------------------- one line on the chart
def window(pts, t0, now):
    """A listing's price points cut to [t0, now] -> [(t, price, in stock)]: starting at t0 with the price
    it had then (when the record has it), every change after, and the price now at the end."""
    pts = sorted(pts or [], key=lambda p: p[0])
    before = [p for p in pts if p[0] <= t0]
    out = [(t0, before[-1][1], bool(before[-1][2]))] if before else []
    out += [(p[0], p[1], bool(p[2])) for p in pts if t0 < p[0] <= now]
    if out:
        out.append((now, out[-1][1], out[-1][2]))
    return out


def cheapest(series_list, t0, now):
    """Several listings as one line: at every moment, the cheapest one in stock (or the cheapest listed
    when none are). -> [(t, price, in stock)]"""
    times = sorted({t for s in series_list for t, _, _ in s if t0 <= t <= now})
    out = []
    for t in times:
        live = []
        for s in series_list:
            at = [p for p in s if p[0] <= t]
            if at:
                live.append(at[-1])
        if not live:
            continue
        stocked = [p for p in live if p[2]]
        price = min(p[1] for p in (stocked or live))
        if not out or out[-1][1] != price or out[-1][2] != bool(stocked) or t == times[-1]:
            out.append((t, price, bool(stocked)))
    return out


def stats(series):
    """{"now", "in_stock", "start", "low", "high", "change", "pct", "since"} for one line, or None."""
    if not series:
        return None
    prices = [p[1] for p in series]
    start, end = series[0], series[-1]
    change = round(end[1] - start[1], 2)
    return {"now": end[1], "in_stock": end[2], "start": start[1], "low": min(prices), "high": max(prices),
            "change": change, "pct": (change / start[1] * 100) if start[1] else 0.0, "since": start[0]}


def trend(st):
    if not st or abs(st["change"]) < 0.005:
        return "▬ no change"
    arrow = "▲" if st["change"] > 0 else "▼"
    pct = f"{st['pct']:+.1f}%" if abs(st["pct"]) < 10 else f"{st['pct']:+.0f}%"
    return f"{arrow} {tb.money(abs(st['change']))} ({pct})"


SPARK = "▁▂▃▄▅▆▇█"


def daily_spark(series, t0, days):
    """Text fallback: the price at the end of each day."""
    vals = []
    for d in range(1, days + 1):
        at = [p for p in series if p[0] <= t0 + d * 86400]
        if at:
            vals.append(at[-1][1])
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    return "".join(SPARK[0 if hi == lo else int((v - lo) / (hi - lo) * (len(SPARK) - 1))] for v in vals)


# ---------------------------------------------------------------- the picture
def place_labels(ends, gap):
    """ends: [[value, label y, ...]] sorted by value. Labels closer than gap are spread out evenly around
    the middle of their bunch (not all pushed upwards), until none overlap."""
    clusters = [[e] for e in ends]
    merged = True
    while merged:
        merged = False
        for c in clusters:                          # each bunch centred on its values, gap apart
            mid = sum(e[0] for e in c) / len(c)
            for j, e in enumerate(c):
                e[1] = mid + (j - (len(c) - 1) / 2) * gap
        for i in range(len(clusters) - 1):
            if clusters[i + 1][0][1] - clusters[i][-1][1] < gap - 1e-9:
                clusters[i:i + 2] = [clusters[i] + clusters[i + 1]]
                merged = True
                break
    return ends


def chart_png(lines, t0, now, title=""):
    """lines: [{"label", "series"}] -> PNG bytes, or None if matplotlib isn't installed.
    Step lines (a price holds until the next change), solid while in stock, dashed and faded while not."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import dates as mdates
        from matplotlib.lines import Line2D
        from matplotlib.ticker import FuncFormatter
    except ImportError:
        return None
    lines = [ln for ln in lines if ln["series"]][:MAX_LINES]
    if not lines:
        return None

    def dt(t):
        return datetime.fromtimestamp(t)

    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=110)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ends = []
    for i, ln in enumerate(lines):
        c = SERIES[i]
        s = ln["series"]
        for (ta, pa, sa), (tb_, pb, _) in zip(s, s[1:]):
            ax.plot([dt(ta), dt(tb_)], [pa, pa], color=c, lw=2, solid_capstyle="round",
                    ls="-" if sa else (0, (3, 3)), alpha=1 if sa else 0.5, zorder=3)
            if abs(pb - pa) >= 0.005:
                ax.plot([dt(tb_), dt(tb_)], [pa, pb], color=c, lw=2, alpha=0.75, zorder=3)
        changes = [p for p in s[1:-1]]
        if changes:
            ax.plot([dt(p[0]) for p in changes], [p[1] for p in changes], ls="none", marker="o", ms=6, color=c,
                    mec=SURFACE, mew=1.5, zorder=4)
        ax.plot([dt(s[-1][0])], [s[-1][1]], ls="none", marker="o", ms=7, color=c, mec=SURFACE, mew=1.5, zorder=5,
                clip_on=False)
        ends.append([s[-1][1], s[-1][1], c])

    lo = min(p[1] for ln in lines for p in ln["series"])
    hi = max(p[1] for ln in lines for p in ln["series"])
    pad = max((hi - lo) * 0.15, hi * 0.04, 0.5)
    ax.set_ylim(max(0, lo - pad), hi + pad)
    first = min(ln["series"][0][0] for ln in lines)
    start = max(t0, first - (now - first) * 0.03) if first > t0 else t0
    ax.set_xlim(dt(start), dt(now))

    # price labels at the right end, nudged apart so they don't sit on top of each other
    span = (hi + pad) - max(0, lo - pad)
    gap = span * 0.075
    ends.sort(key=lambda e: e[0])
    place_labels(ends, gap)
    for y, ly, c in ends:
        ax.text(1.012, ly, tb.money(y), transform=ax.get_yaxis_transform(), va="center", ha="left",
                color=INK, fontsize=9, fontweight="bold", clip_on=False)

    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}" if hi >= 20 else f"${v:,.2f}"))
    days = (now - start) / 86400
    ax.xaxis.set_major_locator(mdates.DayLocator() if days > 1.5 else mdates.HourLocator(interval=4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d" if days > 1.5 else "%I %p"))
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.grid(axis="x", color=GRID, lw=0.5, alpha=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9, length=0, pad=6)
    if title:
        ax.set_title(title, color=INK, fontsize=12, fontweight="bold", loc="left", pad=28 if len(lines) > 1 else 10)
    if len(lines) > 1:
        handles = [Line2D([], [], color=SERIES[i], lw=2.5, marker="o", ms=6, mec=SURFACE)
                   for i in range(len(lines))]
        leg = ax.legend(handles, [tb._short(ln["label"], 32) for ln in lines], loc="lower left", bbox_to_anchor=(0, 1.0),
                        ncol=min(3, len(lines)), frameon=False, fontsize=8.5, handlelength=1.6,
                        columnspacing=1.4, borderaxespad=0.2)
        for t in leg.get_texts():
            t.set_color(INK_2)
    fig.text(0.99, 0.015, "solid = in stock · dashed = sold out · dots = price changes", color=INK_3,
             fontsize=7.5, ha="right")
    fig.subplots_adjust(left=0.09, right=0.88, top=0.84 if len(lines) > 1 else 0.9, bottom=0.12)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=SURFACE)
    plt.close(fig)
    return buf.getvalue()


# ---------------------------------------------------------------- the answer
def _url(store, key):
    shop, _, handle = key.partition("|")
    base = ((store.get("shops") or {}).get(shop) or {}).get("base", "")
    return f"{base}/products/{handle}" if base else ""


def _coverage_note(store, t0, now, days):
    scans = [t for sh in (store.get("shops") or {}).values() for t in (sh.get("scans") or [])]
    if not scans:
        return "The bot hasn't read the shops' singles lists yet (it does about once an hour)."
    first, last = min(scans), max(scans)
    note = f"Last read {_ago(now - last)}."
    if first > t0 + 3600:
        full = datetime.fromtimestamp(first) + timedelta(days=days)
        note += (f" The record starts {datetime.fromtimestamp(first):%a %d %b}, so the chart fills out to "
                 f"{days} days by {full:%a %d %b}.")
    return note


def _ago(s):
    s = max(0, int(s))
    return f"{s // 60} min ago" if s < 5400 else f"{s / 3600:.1f} h ago"


def _tcg_line(tcg, name):
    """v2.8: TCGplayer's US market for the same card and version (tcgplayer.py), or ''."""
    if not tcg or not name:
        return ""
    try:
        import tcgplayer as tp
        return tp.value_line(tcg, name)
    except Exception:  # noqa: BLE001
        return ""


def build(cfg, query, days=MAX_DAYS, now=None, store=None, tcg=None):
    """-> (embed dict, PNG bytes or None). tcg: the TCGplayer price store (tcgplayer.load_for), if any,
    for a "TCGplayer (US) market" line on each version."""
    now = float(now or time.time())
    days = max(1, min(MAX_DAYS, int(days or MAX_DAYS)))
    t0 = now - days * 86400
    store = store if store is not None else load_store()
    if not (store.get("items")):
        s = tb.drops_settings(cfg)
        why = ("No prices recorded yet: the restock bot reads the singles lists about once an hour, so give it "
               "an hour." if s["enabled"] and s["shops"] else
               "The price record is switched off (\"price_drops\" in config.json), and /value reads from it.")
        return {"title": "💰 Card value", "description": why, "color": tb.GREY}, None
    keys = find(store, query)
    gs = groups(store)
    if not keys:
        return {"title": f"💰 Nothing matches “{query}”"[:256], "color": tb.GREY,
                "description": "Try a card number like `OP13-120`, a name like `sabo`, or pick from the list as "
                               "you type. `/card` checks Mayhem too, live."}, None

    one = len(keys) == 1
    if one:
        g = gs[keys[0]]
        items = sorted(g["items"], key=lambda kv: (kv[0].partition("|")[0]))
        lines = []
        for key, it in items:
            s = window(it.get("p"), t0, now)
            if s:
                lines.append({"label": key.partition("|")[0], "series": s, "key": key, "name": it.get("n")})
        title = g["label"]
    else:
        lines = []
        for k in keys:
            g = gs[k]
            ser = [window(it.get("p"), t0, now) for _, it in g["items"]]
            ser = [s for s in ser if s]
            if not ser:
                continue
            best = min(g["items"], key=lambda kv: (not (kv[1]["p"][-1][2]), kv[1]["p"][-1][1]))
            lines.append({"label": g["label"], "series": cheapest(ser, t0, now) if len(ser) > 1 else ser[0],
                          "key": best[0], "name": best[1].get("n"), "shops": len(ser)})
        # the versions people care about most first: in stock, then most valuable
        lines.sort(key=lambda ln: (not ln["series"][-1][2], -ln["series"][-1][1]))
        title = f"“{query}” · {len(lines)} versions"

    for ln in lines:
        ln["st"] = stats(ln["series"])

    stocked = [ln for ln in lines if ln["st"]["in_stock"]]
    rows = []
    for i, ln in enumerate(lines[:12]):
        st = ln["st"]
        mark = "✅" if st["in_stock"] else "▫️"
        url = _url(store, ln["key"])
        name = ln["label"] if not one else f"{ln['label']}"
        head = f"[{tb.link_text(name, 60)}]({url})" if url else tb.link_text(name, 60)
        extra = f" · {ln['shops']} shops" if ln.get("shops", 1) > 1 else ""
        stock = "in stock" if st["in_stock"] else "sold out"
        line = (f"{mark} {head}{extra}\n   now **{tb.money(st['now'])}** {stock} · {days}d low {tb.money(st['low'])}"
                f" · high {tb.money(st['high'])} · {trend(st)}")
        tl = _tcg_line(tcg, ln.get("name"))
        if tl:
            line += f"\n   {tl}"
        if i >= MAX_LINES:
            line += " · *(not on the chart)*"
        rows.append(line)

    if stocked:
        top = min(stocked, key=lambda ln: ln["st"]["now"]) if one else None
        if one:
            lo = min(ln["st"]["low"] for ln in lines)
            hi = max(ln["st"]["high"] for ln in lines)
            desc = (f"Worth about **{tb.money(top['st']['now'])}** right now: the cheapest near-mint copy in stock "
                    f"({top['label']}). {days}-day range {tb.money(lo)} to {tb.money(hi)}.")
        else:
            desc = ("Each line is the cheapest near-mint copy of that version across the shops. Pick one version "
                    "from the list as you type for a line per shop.")
    else:
        desc = ("Not in stock at Elemental Arcade or Good Games right now; prices are what they're listed at."
                if one else "None of these are in stock right now; prices are what they're listed at.")
    if not one and len(lines) > MAX_LINES:
        desc += f" The chart shows the first {MAX_LINES}."

    png = chart_png(lines, t0, now, title=title if one else "")
    if png is None:
        sparks = [f"`{daily_spark(ln['series'], t0, days) or '-'}` {tb.link_text(ln['label'], 50)}"
                  for ln in lines[:MAX_LINES]]
        rows.append("**Last {} days, one bar a day**\n".format(days) + "\n".join(sparks))
        desc += "\n(Chart picture needs matplotlib on the PC: `py -3 -m pip install matplotlib`.)"

    body, size = [], 0
    for r in rows:
        if size + len(r) > 3300:
            body.append(f"…and {len(rows) - len(body)} more. Add words to narrow it down.")
            break
        body.append(r)
        size += len(r) + 2
    e = {"title": f"💰 {title}"[:256], "color": GOLD, "description": (desc + "\n\n" + "\n\n".join(body))[:4096],
         "footer": {"text": f"Near-mint prices at {', '.join(sorted((store.get('shops') or {}))) or 'the shops'} "
                            f"· {_coverage_note(store, t0, now, days)}"[:2048]}}
    if one and lines:
        u = _url(store, (min(stocked, key=lambda ln: ln["st"]["now"]) if stocked else lines[0])["key"])
        if u:
            e["url"] = u
    if png:
        e["image"] = {"url": "attachment://value.png"}
    return e, png


def suggestions(store, current, limit=25):
    """Autocomplete: [(label, group key)] for what's been typed, in stock and valuable first."""
    gs = groups(store)
    keys = find(store, current) if str(current or "").strip() else list(gs)
    out = []
    for k in keys:
        g = gs[k]
        last = [it["p"][-1] for _, it in g["items"] if it.get("p")]
        stocked = [p[1] for p in last if p[2]]
        price = min(stocked) if stocked else (min(p[1] for p in last) if last else 0)
        out.append((not stocked, -price, f"{g['label']} · {tb.money(price)}" + ("" if stocked else " (sold out)"), k))
    out.sort()
    return [(label[:100], k[:100]) for _, _, label, k in out[:limit]]
