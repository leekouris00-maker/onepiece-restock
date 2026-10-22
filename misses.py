#!/usr/bin/env python3
"""
/missed - "someone else posted this before the bot did" (v2.4.1)
================================================================

When Fellowship of the Ping, a friend or a shop's own email beats the bot to something, paste the link:

    /missed link:<product page>  [minutes_ago:<when you saw it elsewhere>]  [note:<anything>]

The bot looks the product up in everything it remembers (both the PC copy's files and the cloud copy's
files on GitHub) and says which of these it was:

    ✅ alerted first   the bot's alert went out before you saw it elsewhere
    🐢 late            the bot alerted, but after (how many minutes)
    👀 seen, no alert  the bot saw it but didn't alert (over your max, not buyable yet, ...)
    🙈 not found       a watched shop, and the title passes the filters, but the bot never saw it
                       (probably listed somewhere the bot doesn't read, or in and out between checks)
    🧹 filtered        a watched shop, but the bot skips titles like this one (and says why)
    🔭 not watched     a shop the bot doesn't read at all (and whether it would be easy to add)

Every report is kept in misses.json, and /misses sums up the last 30 days: which kind of miss happens
most and at which shops. That's what says whether the next fix should be speed, more shops or filters.

Alert times are recorded from v2.4.1 on, so for things seen before that the bot can only say it saw them.
Only needs the restock bot (tcg_bot.py) next to it.
"""
import json
import os
import re
import time
import urllib.parse
from collections import Counter
from datetime import datetime

KEEP = 500                      # misses.json keeps the latest 500 reports
REMOTE_MAX_AGE = 300            # the cloud copy's files on GitHub are re-read after 5 minutes

ICON = {"first": "✅", "late": "🐢", "seen": "👀", "not_found": "🙈", "filtered": "🧹", "not_watched": "🔭"}
NAME = {"first": "Bot alerted first", "late": "Bot was late", "seen": "Seen, no alert",
        "not_found": "Watched shop, never seen", "filtered": "Filtered out", "not_watched": "Shop not watched"}


# ---------------------------------------------------------------- links
def clean_link(text):
    """What someone pastes (maybe in <>, maybe without https://, maybe with ?variant=) -> (host, path) with
    host lower-case and without www., path without a trailing slash. (None, None) if it isn't a link."""
    t = str(text or "").strip().strip("<>").strip()
    m = re.search(r"https?://\S+", t) or re.search(r"[\w.-]+\.[a-z]{2,}(?:/\S*)?", t, re.I)
    t = (m.group(0) if m else t).rstrip(">)].,")
    if "://" not in t:
        t = "https://" + t
    u = urllib.parse.urlsplit(t)
    host = (u.hostname or "").lower()
    if "." not in host:
        return None, None
    return host.removeprefix("www."), urllib.parse.unquote(u.path or "/").rstrip("/") or "/"


def handle_of(path):
    """/products/<handle> (Shopify, also under /collections/x/) or /product/<slug> (WooCommerce)."""
    m = re.search(r"/products?/([^/?#]+)", path or "")
    return m.group(1).lower() if m else ""


def same_product(url, host, path):
    h2, p2 = clean_link(url)
    if h2 != host:
        return False
    return p2 == path or (handle_of(path) and handle_of(p2) == handle_of(path))


# ---------------------------------------------------------------- what the bot remembers
def _remote_text(tb, cfg, name):
    url = f"{(cfg or {}).get('repo_raw_url', tb.REPO_RAW_URL).rstrip('/')}/{name}"
    try:
        return tb.HTTP.fetch(url, tries=1, robots=False, conditional=False).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


def _events(text):
    out = []
    for line in (text or "").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict):
            out.append(e)
    return out


def memory(tb, cfg, remote=True):
    """Everything the PC copy (files next to the bot) and the cloud copy (its files on GitHub) remember."""
    hist = [tb.read_json(tb.HISTORY_PATH, {}) or {}]
    known = [tb.read_json(tb.KNOWN_PATH, {}) or {}]
    drops = [tb.read_json(tb.DROPS_PATH, {}) or {}]
    events = []
    for path in (tb.EVENTS_PATH + ".1", tb.EVENTS_PATH):
        try:
            with open(path, encoding="utf-8") as fh:
                events += _events(fh.read())
        except OSError:
            pass
    if remote:
        for name, into in (("price_history.json", hist), ("known_products.json", known), ("singles_prices.json", drops)):
            data = tb.repo_json(cfg, name, max_age=REMOTE_MAX_AGE)
            if isinstance(data, dict):
                into.append(data)
        events += _events(_remote_text(tb, cfg, "events.jsonl"))
    return {"hist": hist, "known": known, "drops": drops, "events": events}


def _day_ts(day):
    try:
        return datetime.strptime(day, "%Y-%m-%d").timestamp()
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- why the bot skips a title
def skip_reason(tb, cfg, title, variants=None):
    """Why the sealed check skips this title, or None if the bot watches titles like it."""
    if not title:
        return "the shop didn't give a product title"
    low = title.lower()
    if "pokemon" in low or "pokémon" in low:
        return None                          # Pokémon has its own release list (pokemon_watch); judged elsewhere
    if "one piece" not in low and not tb.TCG_RE.search(title):
        return "its title doesn't say One Piece or the card game"
    watch = cfg.get("sealed_watch", tb.DEFAULT_SEALED_WATCH) or []
    if tb.is_box_title(title) or tb.watch_item(title, watch):
        return None
    t = tb.norm(title)
    if tb.is_excluded(title, tb.BOX_EXCLUDE) and ("booster box" in low or "booster display" in low):
        word = next(w.strip() for w in tb.BOX_EXCLUDE if w.lower() in t)
        return f"its title has \"{word}\", which the bot treats as not an English booster box"
    if tb.is_excluded(title, tb.WATCH_EXCLUDE):
        word = next(w.strip() for w in tb.WATCH_EXCLUDE if w.lower() in t)
        return f"its title has \"{word}\", so the bot takes it for a non-English print"
    word = next((w.strip() for w in tb.NOT_SEALED if w in t), None)
    if word:
        return f"its title has \"{word}\", which the bot treats as an accessory or graded card, not sealed product"
    if tb.SINGLE_NUM_RE.search(title) or tb.SINGLE_HINT_RE.search(title):
        return "it looks like a single card (card number or rarity in the title)"
    if not tb.TCG_RE.search(title):
        return "its title doesn't say it's the card game (no \"card game\", \"TCG\" or set code like OP-18)"
    if any(tb.condition(v.get("title")) for v in variants or [] if isinstance(v, dict)):
        return "it's sold by condition (Near Mint, Played...), so the bot takes it for a single"
    if not cfg.get("new_sealed", True):
        return "new sealed listings are switched off (\"new_sealed\": false)"
    if not cfg.get("new_sealed_packs", False) and any(w in t for w in tb.PACK_WORDS):
        return "it's a single booster pack, and packs are off (\"new_sealed_packs\": true turns them on)"
    if not tb.SEALED_WORD_RE.search(title):
        return "its title has no sealed-product word (booster, deck, box, collection, tin, set...)"
    return None


def seen_reason(tb, cfg, entries):
    """Why a listing the bot remembers didn't alert, from what it last saw of it."""
    key, h = max(entries, key=lambda kh: len(kh[1].get("points") or []))
    pts = h.get("points") or []
    price = pts[-1][1] if pts else 0
    if key.startswith("item|"):
        return ("it's in the \"all sealed\" group, which alerts once when first listed and again when it becomes "
                "buyable, and the bot has no record of either (it may already have been listed when the bot "
                "started reading that shop)")
    if not h.get("avail"):
        return f"it was listed but not buyable when the bot last looked ({tb.money(price)})"
    limit = None
    if key.startswith("box|"):
        limit = (cfg.get("sealed") or {}).get("max_price")
    elif key.startswith("sealed|"):
        w = tb.watch_item(h.get("name", ""), cfg.get("sealed_watch", tb.DEFAULT_SEALED_WATCH) or [])
        limit = w["max"] if w else None
    if limit and price > limit:
        return f"it was buyable at {tb.money(price)}, over your {tb.money(limit)} max"
    if key.startswith("poke|"):
        return f"it was buyable at {tb.money(price)}: probably over your Pokémon max for that product type"
    return f"it was buyable at {tb.money(price)}"


def live_look(tb, host, handle):
    """The product's own Shopify page data (title, buyable, price), or None (not Shopify, gone, or blocked)."""
    if not handle:
        return None
    for h in (host, "www." + host):
        data = tb.fetch_json(f"https://{h}/products/{handle}.js", tries=1)
        if isinstance(data, dict) and data.get("title"):
            price = tb._num(data.get("price"))
            return {"title": data["title"], "available": bool(data.get("available")),
                    "price": price / 100 if price else None, "variants": data.get("variants") or []}
    return None


# ---------------------------------------------------------------- the lookup
def explain(tb, cfg, link, reported=None, remote=True, live=True, mem=None):
    """What the bot knew about a product someone else posted first. -> dict with "kind" (see ICON),
    "headline", "lines" (extra detail) and the facts behind them."""
    reported = float(reported or time.time())
    host, path = clean_link(link)
    if not host:
        return {"kind": "error", "headline": "That doesn't look like a link to a product page.", "lines": []}
    handle = handle_of(path)
    res = {"link": f"https://{host}{path}", "host": host, "handle": handle, "reported": round(reported), "lines": []}
    names = {h.lower().removeprefix("www."): n for h, n in tb.shop_names(cfg).items()}
    shop = names.get(host)
    res["shop"] = shop
    mem = mem or memory(tb, cfg, remote)

    # every history entry (sealed, Pokémon) for this product, from both copies
    entries = [(k, h) for hist in mem["hist"] for k, h in hist.items()
               if isinstance(h, dict) and same_product(h.get("url", ""), host, path)]
    ids = {k for k, _ in entries}
    firsts = [(h["first"], True) if h.get("first") else (_day_ts((h.get("points") or [[None]])[0][0]), False)
              for _, h in entries]
    firsts = sorted(f for f in firsts if f[0])
    alerts = sorted({e["t"] for e in mem["events"] if e.get("event") == "alert" and e.get("t")
                     and same_product(e.get("url", ""), host, path)})
    stocked = sorted({e["t"] for e in mem["events"] if e.get("event") == "in_stock" and e.get("id") in ids})
    known = bool(shop and handle and any(i.endswith("|" + handle) for kn in mem["known"] for key, lst in kn.items()
                                         if key.split(" (")[0] == shop for i in lst))
    single = bool(shop and handle and any(f"{shop}|{handle}" in (d.get("items") or {}) for d in mem["drops"]))
    res.update(first_seen=firsts[0][0] if firsts else None, alerts=alerts, in_stock=stocked, known=known, single=single)

    def when(ts, exact=True):
        d = datetime.fromtimestamp(ts)
        return (f"{d:%a} {d.day} {d:%b} " + f"{d:%I:%M %p}".lstrip("0")) if exact else f"on {d:%a} {d.day} {d:%b}"

    def gap(ts):
        mins = round(abs(reported - ts) / 60)
        return f"{mins} min" if mins < 120 else f"{mins / 60:.1f} hours" if mins < 2880 else f"{mins / 1440:.0f} days"

    if alerts:
        before = [a for a in alerts if a <= reported]
        if before:
            res.update(kind="first", headline=f"The bot alerted at {when(before[-1])}, {gap(before[-1])} before you "
                                              f"saw it elsewhere.")
            res["lines"].append("If you didn't get it: check the channel's notification settings, /mute and quiet hours.")
        else:
            res.update(kind="late", late_min=round((alerts[0] - reported) / 60),
                       headline=f"The bot alerted {gap(alerts[0])} after you saw it elsewhere ({when(alerts[0])}).")
            if res.get("first_seen") and res["first_seen"] < alerts[0] - 120:
                res["lines"].append(f"It had seen the listing earlier ({when(res['first_seen'])}) but only alerted "
                                    f"when it became buyable or dropped under your max.")
        return res

    if entries or known or single:
        res["kind"] = "seen"
        seen_at = (f"first saw it {when(*firsts[0])}" if firsts else "has it in its memory")
        why = seen_reason(tb, cfg, entries) if entries else (
            "it's a single, and singles only alert for cards on your want list (or the day's value picks)" if single
            else "")
        if not why and (res.get("first_seen") or 0) < tb.ALERT_LOG_SINCE:
            why = "it was seen before v2.4.1, when alert times weren't recorded yet"
        res["headline"] = (f"The bot {seen_at} at {shop or host}, but has no record of alerting"
                           + (f": {why}." if why else "."))
        if stocked:
            res["lines"].append("Came into stock: " + ", ".join(when(t) for t in stocked[-3:]))
        return res

    look = live_look(tb, host, handle) if live else None
    if look:
        res.update(title=look["title"], available=look["available"], price=look["price"])
    if not shop:
        res["kind"] = "not_watched"
        res["headline"] = f"{host} isn't one of the bot's shops."
        if look:
            res["lines"].append("It's a Shopify shop, so it's quick to add: say the word and it goes in the list.")
        elif live:
            res["lines"].append("It isn't a standard Shopify shop (or blocks bots), so it'd need its own code.")
        return res
    reason = skip_reason(tb, cfg, look["title"], look["variants"]) if look else None
    if reason:
        res.update(kind="filtered", reason=reason,
                   headline=f"The bot reads {shop} but skipped this one: {reason}.")
        return res
    res["kind"] = "not_found"
    res["headline"] = (f"{shop} is watched" + (" and the title passes the filters" if look else "")
                       + ", but the bot never saw this product.")
    res["lines"].append("Most likely it's listed somewhere the bot doesn't read (outside the shop's One Piece section "
                        "and its searches), or it came and sold out between two checks.")
    if look and not look["available"]:
        res["lines"].append("It isn't buyable right now.")
    return res


# ---------------------------------------------------------------- the log and the summary
def misses_path(tb):
    return os.path.join(tb.HERE, "misses.json")


def record(tb, res, who="", note=""):
    if res.get("kind") in (None, "error"):
        return
    log = tb.read_json(misses_path(tb), []) or []
    if not isinstance(log, list):
        log = []
    keep = {k: res.get(k) for k in ("link", "host", "shop", "kind", "headline", "first_seen", "late_min", "title",
                                     "reason", "reported") if res.get(k) is not None}
    keep.update(t=round(time.time()), who=str(who)[:60], note=str(note)[:200])
    log.append(keep)
    tb.atomic_write_json(misses_path(tb), log[-KEEP:], indent=1, ensure_ascii=False)


def summary(tb, days=30, now=None):
    """(headline, [lines]) for /misses."""
    now = now or time.time()
    log = [m for m in (tb.read_json(misses_path(tb), []) or []) if isinstance(m, dict)
           and m.get("t", 0) >= now - days * 86400]
    if not log:
        return (f"No misses reported in the last {days} days.",
                ["When someone posts something before the bot, use `/missed` with the link."])
    kinds = Counter(m.get("kind") for m in log)
    lines = [f"{ICON.get(k, '•')} **{NAME.get(k, k)}**: {n}" for k, n in kinds.most_common()]
    late = sorted(m["late_min"] for m in log if m.get("kind") == "late" and m.get("late_min") is not None)
    if late:
        lines.append(f"Late by {late[len(late) // 2]} min in the middle case (worst {late[-1]} min).")
    hosts = Counter(m.get("shop") or m.get("host") for m in log if m.get("kind") in ("not_watched", "not_found", "filtered"))
    if hosts:
        lines.append("Where the misses are: " + ", ".join(f"{h} ({n})" for h, n in hosts.most_common(6)))
    top = kinds.most_common(1)[0][0]
    advice = {"not_watched": "Most misses are shops the bot doesn't read: adding shops is the fix that pays most.",
              "late": "Most misses are timing: faster checks / an always-on machine is the fix that pays most.",
              "not_found": "Most misses are products at watched shops the bot never saw: more searches per shop.",
              "filtered": "Most misses are titles the filters skip: the filters need loosening (see the reasons).",
              "first": "The bot was first most of the time: check notification settings so you don't miss its pings.",
              "seen": "The bot saw most of them but didn't alert: check your max prices."}.get(top)
    if advice:
        lines.append(advice)
    return f"{len(log)} miss(es) reported in the last {days} days", lines
