#!/usr/bin/env python3
"""
Drop rehearsal for the One Piece restock bot (v2.21, PC copy)
=============================================================
A few hours before a drop window opens, the bot posts ONE readiness card to #bot-status, so you find out
at 3pm (not at 6pm) that a shop is paused, a settings file is broken or desk mode is off.

It makes no extra requests and sends no alerts: the card is written from the ordinary check the bot has
just finished. For a window called "OP-18 eve" it says, shop by shop:

  * ready, and already listing OP-18 (buyable / listed but not buyable yet / over your max price)
  * ready, with no OP-18 listing yet (the new-listing alert covers these when the listing appears)
  * not readable right now, and why (asked for human verification, asked the bot to slow down, not loading)

then the fast lane's target count, desk mode, auto-buy, phone alerts and the settings files.

When: once per window, on the first sealed check inside the 3 hours before it starts. A window that
follows another within a day (release morning after the eve) doesn't get its own card.
Off with "drop_rehearsal": false in config.json. By hand:  py -3 tcg_bot.py --rehearse   (add --dry-run to
print it without posting).

The bot does nothing about a shop that isn't readable: it doesn't solve or get round a human-verification
check and doesn't retry early. The card only tells you.
"""
from datetime import datetime, timedelta

LEAD = timedelta(hours=3)
FOLLOWS = timedelta(hours=24)       # a window starting this soon after another one ended: no card of its own
KEEP_DAYS = 30
STATUS_KEY = "rehearsed"
MAX_NAMES = 14


def enabled(cfg):
    return (cfg or {}).get("drop_rehearsal", True) is not False


def _op_windows(tb, cfg, now):
    return [w for w in tb.parse_windows(cfg, now) if tb.ONE_PIECE in (w.get("games") or [tb.ONE_PIECE])]


def key_for(w):
    return f"{w['name']}|{w['start']:%Y-%m-%d %H:%M}"


def due(tb, cfg, status, now=None):
    """The One Piece drop window that should get its readiness card now, or None."""
    if not enabled(cfg) or tb.IN_ACTIONS or tb.heartbeat_role(cfg) == "listen":
        return None
    now = now or datetime.now()
    done = (status or {}).get(STATUS_KEY) or {}
    wins = _op_windows(tb, cfg, now)
    for w in wins:
        if not timedelta(0) < w["start"] - now <= LEAD or key_for(w) in done:
            continue
        if any(o is not w and o["end"] <= w["start"] and w["start"] - o["end"] < FOLLOWS for o in wins):
            continue
        if any(o is not w and o["start"] <= now < o["end"] for o in wins):
            continue                                # another window is on right now: not the time for a card
        return w
    return None


def next_window(tb, cfg, now=None, name=""):
    """For --rehearse: the next One Piece window (or the next one whose name contains `name`)."""
    now = now or datetime.now()
    name = str(name or "").strip().lower()
    for w in _op_windows(tb, cfg, now):
        if w["end"] > now and name in w["name"].lower():
            return w
    return None


def _names(items, limit=MAX_NAMES):
    items = list(items)
    more = f" and {len(items) - limit} more" if len(items) > limit else ""
    return ", ".join(items[:limit]) + more


def _when(start, now):
    mins = int((start - now).total_seconds() // 60)
    if mins <= 0:
        return "on now"
    if mins < 90:
        return f"in {mins} min"
    if mins < 36 * 60:
        return f"in about {round(mins / 60)} h"
    return f"in {round(mins / 1440)} days"


def survey(tb, cfg, window, by_shop):
    """Sort the shops of one finished sealed check: {"listing": [(shop, state, price)], "ready": [shop],
    "blocked": [(shop, why)], "codes": [...]}. state is "buyable", "over max" or "not buyable yet"."""
    fl = getattr(tb, "fast_lane", None)
    codes = fl.window_codes(window) if fl else []
    rx = fl.code_pattern(codes) if fl and codes else None
    try:
        host_of = {name: host for host, name in tb.shop_names(cfg).items()}
    except Exception:  # noqa: BLE001
        host_of = {}
    waiting, slowed = set(), set()
    ng = getattr(tb, "netguard", None)
    if ng:
        try:
            for r in ng.watch_list(tb, cfg):
                (waiting if r.get("needs_you") else slowed).add(r["host"])
        except Exception:  # noqa: BLE001
            pass
    try:
        slowed |= set(tb.HTTP.cooling())
    except Exception:  # noqa: BLE001
        pass
    out = {"listing": [], "ready": [], "blocked": [], "codes": codes}
    for shop in sorted(by_shop or {}, key=str.lower):
        listings = by_shop[shop]
        host = host_of.get(shop, "")
        if listings is None:
            why = ("asked for human verification" if host in waiting else
                   "asked the bot to slow down" if host in slowed else "didn't load")
            out["blocked"].append((shop, why))
            continue
        hits = [l for l in listings if rx and rx.search(l.get("name") or "") and l.get("group") in ("box", "watch")]
        if not hits:
            out["ready"].append(shop)
            continue
        hits.sort(key=lambda l: (l.get("group") != "box", not l.get("available"), l.get("price") or 0))
        best = hits[0]
        price, mx = best.get("price") or 0, best.get("max") or 0
        state = ("not buyable yet" if not best.get("available") else
                 "over max" if mx and price > mx else "buyable")
        out["listing"].append((shop, state, price))
    return out


def build(tb, cfg, window, by_shop, now=None):
    """(text, colour) for the readiness card."""
    now = now or datetime.now()
    s = survey(tb, cfg, window, by_shop)
    what = " / ".join(s["codes"]) or "the release"
    total = len(s["listing"]) + len(s["ready"]) + len(s["blocked"])
    lines = [f"🧪 **Drop rehearsal: {window['name']}** starts {window['start']:%a %d %b %I:%M %p} "
             f"({_when(window['start'], now)}). The bot read {total - len(s['blocked'])} of {total} shops just now."]
    if s["listing"]:
        label = {"buyable": "buyable now", "over max": "in stock, over your max", "not buyable yet": "listed, not buyable yet"}
        parts = [f"{shop} ({label[state]}" + (f", {tb.money(price)}" if price else "") + ")"
                 for shop, state, price in s["listing"]]
        lines.append(f"✅ **Already listing {what} ({len(parts)}):** {_names(parts)}")
    if s["ready"]:
        note = f"no {what} listing yet; you'll get the new-listing alert when one appears" if s["codes"] else "readable"
        lines.append(f"🟢 **Ready ({len(s['ready'])}, {note}):** {_names(s['ready'], 30)}")
    if s["blocked"]:
        by_why = {}
        for shop, why in s["blocked"]:
            by_why.setdefault(why, []).append(shop)
        for why, shops in by_why.items():
            lines.append(f"⚠️ **Not readable right now, {why} ({len(shops)}):** {_names(shops, 30)}")
        if any(why == "asked for human verification" for _, why in s["blocked"]):
            lines.append("The bot won't get round a human-verification check. Open those shops in your own browser; "
                         "if they let you in, `/captcha resume:all` has the bot try them again.")
    setup = []
    fl = getattr(tb, "fast_lane", None)
    if fl:
        fs = fl.settings(cfg)
        if fs:
            try:
                lw = getattr(fl, "lw", None)
                n = len(fl.build_targets(window, by_shop, lw.load() if lw else [], fs["max_targets"]))
            except Exception:  # noqa: BLE001
                n = 0
            setup.append(f"Fast lane: {n} target(s) every {fs['seconds']:g}s" if n else
                         "Fast lane: nothing to target yet (it picks up listings as they appear)")
        else:
            setup.append("Fast lane: off")
        until = fl.desk_until(tb)
        if until > window["start"].timestamp():
            setup.append(f"Desk mode: on until {datetime.fromtimestamp(until):%a %I:%M %p}")
        else:
            setup.append("Desk mode: **off for the window** (`/desk on` if you want checkout tabs opened)")
    ab = getattr(tb, "auto_buy", None)
    if ab:
        try:
            setup.append(f"Auto-buy: {ab.settings(tb, cfg).get('mode', 'off')}")
        except Exception:  # noqa: BLE001
            pass
    alerts = (cfg or {}).get("alerts") or {}
    setup.append("Phone alerts: " + ("on" if alerts.get("ntfy_topic") else "off (no ntfy topic set)"))
    lines.append("⚙️ " + " · ".join(setup))
    trouble = bool(s["blocked"])
    sp = getattr(tb, "SECRETS_PROBLEM", [None])[0]
    if sp:
        trouble = True
        lines.append(f"⚠️ **secrets.json won't load.** {sp}")
    warns = list(getattr(tb, "CONFIG_WARNINGS", []) or [])
    if warns:
        trouble = True
        lines.append("⚠️ config.json needs a look: " + "; ".join(warns)[:500])
    if not trouble:
        lines.append("Nothing needs doing.")
    return "\n".join(lines)[:3900], (tb.AMBER if trouble else tb.GREEN)


def mark(status, window, now=None):
    now = now or datetime.now()
    done = status.setdefault(STATUS_KEY, {})
    done[key_for(window)] = round(now.timestamp())
    cutoff = now.timestamp() - KEEP_DAYS * 86400
    for k in [k for k, t in done.items() if not isinstance(t, (int, float)) or t < cutoff]:
        done.pop(k)


def maybe_post(tb, cfg, status, by_shop, now=None):
    """Called after a normal sealed check. Posts the card if one is due; returns the window it was for."""
    w = due(tb, cfg, status, now)
    if not w or not by_shop:
        return None
    text, colour = build(tb, cfg, w, by_shop, now)
    tb.post_status(cfg, text, colour)
    mark(status, w, now)
    return w
