"""
/pricecheck: what a whole deck costs to buy right now (v2.9)
============================================================

    /pricecheck deck deck:<name>          price a saved deck, or a deck from your want list ("deck" tags)
    /pricecheck deck deck:<pasted list>   price a list without saving it, e.g. 1xOP12-001 4xOP12-016 ...
    /pricecheck save name:<name> list:<decklist>   keep a decklist (or attach a .txt export instead)
    /pricecheck list                      the saved decks
    /pricecheck remove deck:<name>        forget one (admins, or whoever saved it)

Nothing is fetched, so it answers instantly. For each card number it uses:
  - the shops: the cheapest near-mint copy in stock at Elemental Arcade or Good Games, from the restock
    bot's own record of every single (singles_prices.json, read about once an hour). Collector versions
    (Wanted Poster, alt art, manga...) don't count when the regular print is sold out: a copy counts only
    if it's priced like a play copy, at most about twice TCGplayer's regular price (see fair()). A pricier
    version that is in stock is still mentioned on the card's line;
  - TCGplayer: the US market price of the regular print (the cheapest version if there's no regular),
    in A$, from the daily TCGCSV sync (tcgplayer_prices.json).

Decklists can be pasted in the usual export formats - "4xOP01-016", "4 OP01-016", "OP01-016 x4" - on
one line or many. Discord turns new lines in a slash command into spaces, which is fine.

A want-list deck counts what you still need (qty minus "owned"), so its total is what's left to buy.
Saved decks are kept in decks.json next to the bot (it's yours: the updater never touches it).
"""
import json
import os
import re
import threading
import time
from datetime import datetime

import tcg_bot as tb

DECKS_PATH = os.path.join(tb.HERE, "decks.json")
NUM = r"(?:(?:OP|EB|ST|PRB)\d{2}|P)-\d{3}"
NUM_RE = re.compile(rf"\b{NUM}\b", re.I)
# "4xOP01-016", "4 x OP01-016", "4 OP01-016" | "OP01-016 x4", "OP01-016 4x"
QTY_FIRST = re.compile(rf"(?<![\w-])(\d{{1,2}})\s*[x×*]?\s*({NUM})\b", re.I)
QTY_AFTER = re.compile(rf"\b({NUM})\s*(?:[x×*]\s*(\d{{1,2}})|(\d{{1,2}})\s*[x×])(?![\w-])", re.I)
SKIP_WORDS = ("japanese", "jp ver", "(jp)", "damaged", "played", "proxy")
SHOP_SHORT = {"Elemental Arcade": "EA", "Good Games": "GG"}
MAX_DECKS = 50
PLAIN = {"", "reprint"}
FAIR_MULT, FAIR_SLACK = 2.0, 6.0      # see fair()
COLOR, GREY = 0xE76F51, 0x6C757D
_lock = threading.Lock()


# ---------------------------------------------------------------- reading a decklist
def parse(text):
    """Decklist text -> ([(card number, qty)] in the order first seen, [warnings]).
    Lines like '4xOP01-016', '4 OP01-016', 'OP01-016 x4'; a number with no count is one copy.
    The same number twice is added up."""
    text = str(text or "")
    counts, order, used = {}, [], []

    def add(num, qty, span):
        num = num.upper()
        if num not in counts:
            order.append(num)
            counts[num] = 0
        counts[num] += qty
        used.append(span)

    for m in QTY_FIRST.finditer(text):
        add(m.group(2), int(m.group(1)), m.span())
    for m in QTY_AFTER.finditer(text):
        if any(a <= m.start() < b or a < m.end() <= b for a, b in used):
            continue
        add(m.group(1), int(m.group(2) or m.group(3)), m.span())
    for m in NUM_RE.finditer(text):                       # a bare number: one copy (e.g. the leader)
        if not any(a <= m.start() < b for a, b in used):
            add(m.group(0), 1, m.span())
    warn = []
    over = [n for n in order if counts[n] > 4]
    if over:
        warn.append("More than 4 of " + ", ".join(f"{n} ({counts[n]})" for n in over) + ": priced as listed.")
    total = sum(counts.values())
    if order and total not in (50, 51):
        warn.append(f"{total} cards in the list (a deck is 50 plus the leader).")
    return [(n, counts[n]) for n in order if counts[n] > 0], warn


# ---------------------------------------------------------------- saved decks and want-list decks
def load_decks():
    d = tb.read_json(DECKS_PATH, None)
    if not isinstance(d, dict) or not isinstance(d.get("decks"), dict):
        return {"v": 1, "decks": {}}
    return d


def _key(name):
    return re.sub(r"\s+", " ", str(name or "")).strip().lower()


def save_deck(name, cards, who):
    """Keep a decklist under a name (replacing one of the same name). Returns 'added' or 'updated'."""
    name = re.sub(r"\s+", " ", str(name or "")).strip()[:60]
    if not name or not cards:
        raise ValueError("Give the deck a name and a list with card numbers in it.")
    with _lock:
        d = load_decks()
        k = _key(name)
        what = "updated" if k in d["decks"] else "added"
        if what == "added" and len(d["decks"]) >= MAX_DECKS:
            raise ValueError(f"That's {MAX_DECKS} saved decks already: /pricecheck remove one first.")
        d["decks"][k] = {"name": name, "cards": [[n, q] for n, q in cards], "by": str(who),
                         "saved": datetime.now().strftime("%Y-%m-%d %H:%M")}
        tb.atomic_write_json(DECKS_PATH, d, indent=1, ensure_ascii=False)
    return what


def remove_deck(name):
    with _lock:
        d = load_decks()
        hit = d["decks"].pop(_key(name), None)
        if hit is not None:
            tb.atomic_write_json(DECKS_PATH, d, indent=1, ensure_ascii=False)
    return hit


def want_tags(cfg):
    """The "deck" tags on the want list, in the order they first appear."""
    out = []
    for c in ((cfg or {}).get("singles") or {}).get("cards") or []:
        t = str(c.get("deck") or "").strip()
        if t and t not in out:
            out.append(t)
    return out


def _shared_tag(tag, deck):
    """'both Luffy decks' belongs to 'Luffy & Ace' and 'Green/Blue Luffy'."""
    t = tag.lower()
    if not re.match(r"(both|all)\b", t):
        return False
    words = {w for w in re.findall(r"[a-z]{4,}", t) if w not in ("both", "decks", "deck")}
    return bool(words & set(re.findall(r"[a-z]{4,}", deck.lower())))


def want_deck(cfg, tag):
    """A want-list deck as [(number, still needed, wanted, owned, name)]."""
    rows = {}
    for c in ((cfg or {}).get("singles") or {}).get("cards") or []:
        t = str(c.get("deck") or "").strip()
        if not t or not (t.lower() == tag.lower() or _shared_tag(t, tag)):
            continue
        n = str(c.get("num") or "").upper()
        if not NUM_RE.fullmatch(n):
            continue
        want = int(tb._num(c.get("qty", 1)) or 1)
        have = min(want, int(tb._num(c.get("owned")) or 0))
        r = rows.setdefault(n, [n, 0, 0, 0, c.get("name") or ""])
        r[1] += want - have
        r[2] += want
        r[3] += have
    return [tuple(r) for r in rows.values()]


def resolve(cfg, query):
    """What /pricecheck deck was given -> (title, [(num, qty)], {num: (wanted, owned)}, source, warnings),
    or None. A saved deck first, then a want-list tag, then a pasted list."""
    q = str(query or "").strip()
    saved = load_decks()["decks"].get(_key(q))
    if saved:
        cards = [(str(n).upper(), int(x)) for n, x in saved.get("cards") or []]
        return saved.get("name") or q, cards, {}, f"saved by {saved.get('by', '?')} on {saved.get('saved', '?')}", []
    tags = want_tags(cfg)
    tag = next((t for t in tags if t.lower() == q.lower()), None)
    if tag is None:
        part = [t for t in tags if q.lower() in t.lower()] if len(q) >= 3 else []
        tag = part[0] if len(part) == 1 else None
    if tag is not None:
        rows = want_deck(cfg, tag)
        return (tag, [(n, need) for n, need, _, _, _ in rows], {n: (w, o) for n, _, w, o, _ in rows},
                "from your want list", [])
    cards, warn = parse(q)
    if cards:
        return "Pasted list", cards, {}, "not saved (/pricecheck save to keep it)", warn
    return None


def suggestions(cfg, current, limit=25):
    cur = str(current or "").lower()
    out = []
    for d in load_decks()["decks"].values():
        n = d.get("name", "")
        if cur in n.lower():
            out.append((f"📋 {n} ({sum(int(q) for _, q in d.get('cards') or [])} cards)", n))
    for t in want_tags(cfg):
        if cur in t.lower():
            out.append((f"📝 {t} (want list)", t))
    return [(a[:100], b[:100]) for a, b in out[:limit]]


# ---------------------------------------------------------------- prices
_shop_cache = {}


def shop_index(store):
    """card number -> [(price, shop, item key, name)] for every single in stock now, cheapest first."""
    hit = _shop_cache.get("i")
    if hit and hit[0] is store:
        return hit[1]
    by = {}
    for key, it in (store.get("items") or {}).items():
        pts = it.get("p") or []
        if not pts or not pts[-1][2] or it.get("gone"):
            continue
        name = it.get("n") or ""
        if any(w in name.lower() for w in SKIP_WORDS):
            continue
        m = NUM_RE.search(name)
        if not m or not pts[-1][1] or pts[-1][1] <= 0:
            continue
        by.setdefault(m.group(0).upper(), []).append((float(pts[-1][1]), key.partition("|")[0], key, name))
    for v in by.values():
        v.sort()
    _shop_cache["i"] = (store, by)
    return by


def version_of(name):
    """A shop title's version words ('' for the regular print): 'Sabo - OP13-120 (Wanted Poster) [...]' ->
    'wanted poster'. A reprint is the same card for play, so it counts as regular."""
    import value as cv
    v = cv.parse_name(name)[2]
    return "" if v in PLAIN else v


def fair(price_aud, tcg_aud, version):
    """Is this shop copy one you'd buy to play with? Collector versions (Wanted Poster, alt art, manga...)
    can be 50x the regular print, and pricing a deck with them would be nonsense. A copy counts when it's
    at most about twice TCGplayer's regular-print price (plus a few dollars of slack for bulk cards), or,
    with no TCGplayer price to compare, when it's the regular print."""
    if tcg_aud is None:
        return not version
    return price_aud <= tcg_aud * FAIR_MULT + FAIR_SLACK


def shop_url(store, key):
    shop, _, handle = key.partition("|")
    base = ((store.get("shops") or {}).get(shop) or {}).get("base", "")
    return f"{base}/products/{handle}" if base else ""


def tcg_price(tcg, num):
    """(US$ market, item key, name) for the regular print of a card number, else its cheapest version."""
    if not tcg or not tcg.get("items"):
        return None
    import tcgplayer as tp
    items = tcg["items"]
    keys = [k for k in tp.index(tcg).get(num, []) if items[k].get("m") is not None]
    if not keys:
        return None
    regular = [k for k in keys if not tp.tcg_version(items[k].get("n"))]
    k = min(regular or keys, key=lambda k: items[k]["m"])
    return items[k]["m"], k, items[k].get("n", "")


def card_name(shop_name, tcg_name, fallback=""):
    for n in (tcg_name, shop_name):
        if n:
            n = re.sub(r"\[[^\]]*\]|\([^()]*\)", " ", n)
            n = NUM_RE.sub(" ", n)
            n = re.sub(r"\s+", " ", n.replace(" - ", " ")).strip(" -")
            if n:
                return n
    return fallback


def price(cards, shops, tcg, have=None):
    """Price every card. Returns (rows, totals). A row:
    {num, qty, name, shop: (price, shop, key) or None, tcg_usd, tcg_key, wanted, owned}."""
    idx = shop_index(shops or {})
    rate = None
    if tcg and tcg.get("items"):
        import tcgplayer as tp
        rate = tp.rate(tcg)
    rows = []
    for num, qty in cards:
        s = idx.get(num, [])
        t = tcg_price(tcg, num)
        tcg_aud = t[0] * rate if t and rate else None
        ok = [c for c in s if fair(c[0], tcg_aud, version_of(c[3]))]
        other = next((c for c in s if c not in ok), None)
        w, o = (have or {}).get(num, (qty, 0))
        rows.append({"num": num, "qty": qty, "name": card_name(s[0][3] if s else "", t[2] if t else ""),
                     "shop": ok[0][:3] if ok else None, "tcg_usd": t[0] if t else None, "tcg_key": t[1] if t else None,
                     "other": (other[0], other[1], other[2], version_of(other[3])) if other and not ok else None,
                     "wanted": w, "owned": o})
    need = [r for r in rows if r["qty"] > 0]
    tot = {
        "cards": sum(r["qty"] for r in need),
        "shop_aud": sum(r["shop"][0] * r["qty"] for r in need if r["shop"]),
        "shop_cards": sum(r["qty"] for r in need if r["shop"]),
        "tcg_usd": sum(r["tcg_usd"] * r["qty"] for r in need if r["tcg_usd"] is not None),
        "tcg_cards": sum(r["qty"] for r in need if r["tcg_usd"] is not None),
        "rate": rate,
        "missing": [r for r in need if not r["shop"]],
    }
    tot["tcg_aud"] = tot["tcg_usd"] * rate if rate else None
    # what the cards with no shop copy would add, at TCGplayer market
    tot["gap_aud"] = (sum(r["tcg_usd"] * r["qty"] for r in tot["missing"] if r["tcg_usd"] is not None) * rate
                      if rate else None)
    return rows, tot


# ---------------------------------------------------------------- the answer
def cvnice(version):
    import value as cv
    return cv.nice_version(version) if version else "another print"


def _m(x):
    return f"A${x:,.2f}"


def _fit(lines, limit=3500):
    out, n = [], 0
    for i, ln in enumerate(lines):
        if n + len(ln) + 1 > limit:
            out.append(f"…and {len(lines) - i} more")
            break
        out.append(ln)
        n += len(ln) + 1
    return "\n".join(out)


def build(cfg, query, shops=None, tcg=None):
    """The /pricecheck deck embed, as a dict."""
    got = resolve(cfg, query)
    if got is None:
        return {"title": f"🃏 No deck called “{str(query)[:60]}”", "color": GREY,
                "description": "Pick one from the list as you type, paste a decklist (e.g. `1xOP12-001 4xOP12-016 ...`), "
                               "or keep one with `/pricecheck save`."}
    title, cards, have, source, warn = got
    if shops is None:
        shops = tb.load_drops_store()
    rows, tot = price(cards, shops, tcg, have)
    rate = tot["rate"]

    def line_cost(r):
        if r["shop"]:
            return r["shop"][0] * r["qty"]
        return (r["tcg_usd"] or 0) * (rate or 0) * r["qty"]

    need = sorted([r for r in rows if r["qty"] > 0], key=lambda r: -line_cost(r))
    done = [r for r in rows if r["qty"] <= 0]
    lines = []
    for r in need:
        name = tb.link_text(r["name"] or r["num"], 28)
        head = f"{r['qty']}× **{name}** {r['num']}"
        if have and r["owned"]:
            head += f" (have {r['owned']}/{r['wanted']})"
        if r["shop"]:
            p, shop, key = r["shop"]
            sh = f"[{_m(p)}]({shop_url(shops, key)}) {SHOP_SHORT.get(shop, shop)}"
            if r["qty"] > 1:
                sh += f" = **{_m(p * r['qty'])}**"
        elif r.get("other"):
            p, shop, key, ver = r["other"]
            sh = (f"❌ no play copy in stock (only {cvnice(ver)} [{_m(p)}]({shop_url(shops, key)}) "
                  f"{SHOP_SHORT.get(shop, shop)})")
        else:
            sh = "❌ not in stock"
        tp_ = f" · TCG {_m(r['tcg_usd'] * rate)}" if r["tcg_usd"] is not None and rate else ""
        lines.append(f"{head} · {sh}{tp_}")
    if done:
        lines.append("✔️ Got them all: " + ", ".join(f"{r['name'] or r['num']} {r['num']}" for r in done))

    summary = []
    if tot["cards"] == 0:
        summary.append("🎉 Nothing left to buy for this deck.")
    else:
        summary.append(f"🛒 **{_m(tot['shop_aud'])}** for the {tot['shop_cards']} of {tot['cards']} cards in stock at "
                       "Elemental Arcade / Good Games now")
        if tot["missing"]:
            gap = f", about **{_m(tot['gap_aud'])}** more at TCGplayer market" if tot["gap_aud"] else ""
            summary.append(f"❌ {tot['cards'] - tot['shop_cards']} card(s) not in stock at either{gap}")
        if tot["tcg_aud"] is not None:
            part = "" if tot["tcg_cards"] == tot["cards"] else f" ({tot['tcg_cards']} of {tot['cards']} cards priced)"
            summary.append(f"🇺🇸 TCGplayer market for the lot: **{_m(tot['tcg_aud'])}** (US${tot['tcg_usd']:,.2f}){part}")
    summary += [f"⚠️ {w}" for w in warn]
    total = tot["shop_aud"] + (tot["gap_aud"] or 0)
    head = f" · {_m(total)}" if tot["cards"] else ""
    reads = [max(sh.get("scans") or [0]) for sh in (shops.get("shops") or {}).values()]
    last = max(reads, default=0)
    when = (f"shop prices read {int((time.time() - last) // 60)} min ago" if last and time.time() - last < 5400
            else f"shop prices read {datetime.fromtimestamp(last):%a %I:%M %p}" if last else "no shop prices recorded yet")
    fx = f" · US$1 = A${rate:g}" if rate else " · no TCGplayer prices yet"
    return {"title": f"🃏 {title}{head}"[:256], "color": COLOR,
            "description": "\n".join(summary) + "\n\n" + _fit(lines, 3900 - sum(len(s) + 1 for s in summary)),
            "footer": {"text": f"{source} · cheapest near-mint copy in stock that's priced like a play copy (collector "
                               f"versions left out) · {when}{fx} · the shops may hold fewer copies than you need"[:2048]}}


def list_embed(cfg):
    saved = sorted(load_decks()["decks"].values(), key=lambda d: d.get("name", "").lower())
    lines = [f"📋 **{d.get('name')}** · {sum(int(q) for _, q in d.get('cards') or [])} cards · "
             f"{len(d.get('cards') or [])} different · saved by {d.get('by', '?')}" for d in saved]
    tags = want_tags(cfg)
    if tags:
        lines.append("\n📝 From the want list: " + ", ".join(f"**{t}**" for t in tags))
    return {"title": f"🃏 Decks to price ({len(saved)} saved)", "color": COLOR,
            "description": "\n".join(lines)[:4000] or "None yet.",
            "footer": {"text": "/pricecheck deck to price one · /pricecheck save to add one"}}
