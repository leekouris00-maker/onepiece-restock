#!/usr/bin/env python3
"""
One Piece in-store section (v2.10)
==================================

The One Piece counterpart of the Pokémon in-store channel. #onepiece-in-store gets:
  * "🛒 Tomorrow in stores" at 6pm the evening before a release (no ping), and
  * "📍 Out today in stores" at 7am on the day (pings the One Piece Ping role, "discord_ping"),
  each listing what comes out that day (from the release calendar: "releases" in config.json, or the bot's
  built-in list), which shops have it online right now (from the last check, latest.json), and where to
  look on a shelf ("instore": {"stores": [...]} in config.json to change the list).
  * `/onepiece report` in Discord: anyone who sees stock on a shelf posts it here (store, what, price, photo)
  and pings everyone. `/onepiece instore` lists the last 24 hours of sightings; `/onepiece releases` the calendar.

Where the posts go: "discord_webhook_instore" in alerts (DISCORD_WEBHOOK_INSTORE in the cloud). Like the
Pokémon section, it stays quiet until that channel exists (one #bot-status post says so); make it with
`/onepiece setup` in Discord or add_channels.bat. Nothing else changes: box, sealed and singles alerts carry on.

Both copies of the bot can post these; the hand-off is the same as the Pokémon one: the PC copy says in its
"I'm on" message which release-day posts it made (r=op:<date>|eve,...), the cloud copy marks those done and
only posts when the PC is off, and the PC copy skips any the cloud copy posted (status.json in the repo).

Settings, all optional, under "instore" in config.json:
    {"enabled": true, "evening": "18:00", "morning": "07:00", "ping": true, "online": true,
     "stores": ["EB Games / Zing", "Big W", "Kmart", "Target", "JB Hi-Fi", "your local game store"]}
"""
import re
from datetime import datetime, timedelta

HOOK_KEY = "discord_webhook_instore"
STATUS_KEY = "onepiece_reminders"       # status.json: {"op:2026-11-20|day": unix time, ...}
KEY_PREFIX = "op:"
EVENING, EVENING_UNTIL = "18:00", "23:59"
MORNING, MORNING_UNTIL = "07:00", "13:00"
REMINDER_KEEP_DAYS = 30
RED = 0xD62828                          # One Piece red, for the embeds
DEFAULT_STORES = ["EB Games / Zing", "Big W", "Kmart", "Target", "JB Hi-Fi", "your local game store"]
MAX_ONLINE_LINES = 8
ONLINE_FRESH = 3 * 3600                 # a check older than this is too old to call "right now"

CODE_RE = re.compile(r"\b(OP|EB|ST|DP|IB|TS|PRB|PEB|GC)-?(\d{1,2})\b", re.I)
BOOSTER_RE = re.compile(r"\b(OP|EB|PRB)-?\d{1,2}\b", re.I)      # booster sets: the eve post + drop mode matter most
_STOP = {"the", "of", "and", "vol", "set", "edition", "card", "cards", "collection", "premium", "box", "boxes",
         "starter", "decks", "deck", "pack", "double", "mini", "case", "booster", "extra", "approx", "date"}
_SKIP_ONLINE = ("japanese", "(jp)", " jp ", "[jp]", "jpn", "chinese", "korean", "asia", "sleeve", "playmat",
                "deck box", "binder", "single", "deposit")


def _hhmm(s, default):
    try:
        h, m = (int(x) for x in str(s).split(":"))
        if 0 <= h < 24 and 0 <= m < 60:
            return f"{h:02d}:{m:02d}"
    except (TypeError, ValueError):
        pass
    return default


def settings(cfg):
    """The "instore" section with defaults filled in. "instore": false switches the whole thing off."""
    raw = (cfg or {}).get("instore", True)
    if raw is False:
        return {"enabled": False, "evening": EVENING, "morning": MORNING, "ping": True, "online": True,
                "stores": list(DEFAULT_STORES)}
    raw = raw if isinstance(raw, dict) else {}
    stores = raw.get("stores")
    if not isinstance(stores, list) or not all(isinstance(s, str) and s.strip() for s in stores):
        stores = list(DEFAULT_STORES)
    return {"enabled": raw.get("enabled", True) is not False,
            "evening": _hhmm(raw.get("evening"), EVENING), "morning": _hhmm(raw.get("morning"), MORNING),
            "ping": raw.get("ping", True) is not False, "online": raw.get("online", True) is not False,
            "stores": [s.strip() for s in stores][:12]}


def warnings(cfg):
    """config.json problems in the "instore" section, as text (checked at load like the rest)."""
    raw = (cfg or {}).get("instore", True)
    if raw is False or raw is True:
        return []
    if not isinstance(raw, dict):
        return ['"instore" should be {...} or false; using the defaults']
    out = []
    for k in ("evening", "morning"):
        if k in raw and _hhmm(raw[k], None) is None:
            out.append(f'"instore" "{k}" should be a time like "18:00"; using the default')
    if "stores" in raw and (not isinstance(raw["stores"], list) or
                            not all(isinstance(s, str) and s.strip() for s in raw["stores"])):
        out.append('"instore" "stores" should be a list of store names; using the defaults')
    return out


def code_of(name):
    m = CODE_RE.search(name or "")
    return f"{m.group(1).upper()}-{int(m.group(2)):02d}" if m else ""


def releases(cfg, default_releases=(), now=None):
    """The One Piece release calendar as [{"date": datetime, "name", "code", "booster", "approx"}], sorted.
    Entries with no date or a date the bot can't read are left out."""
    out = []
    for r in (cfg or {}).get("releases", list(default_releases)) or []:
        if not isinstance(r, dict):
            continue
        try:
            d = datetime.strptime(str(r.get("date", "")), "%Y-%m-%d")
        except ValueError:
            continue
        name = str(r.get("name") or "").strip()
        if not name:
            continue
        out.append({"date": d, "name": name, "code": code_of(name), "booster": bool(BOOSTER_RE.search(name)),
                    "approx": "approx" in name.lower() or r.get("approx") is True})
    out.sort(key=lambda x: (x["date"], x["name"]))
    return out


def release_days(cfg, default_releases=(), now=None, days=120, past=0):
    """[(date, [release, ...])] for the exact (not approximate) release days from `past` days ago to `days` ahead."""
    now = now or datetime.now()
    by_day = {}
    for r in releases(cfg, default_releases, now):
        if r["approx"]:
            continue
        delta = (r["date"].date() - now.date()).days
        if -past <= delta <= days:
            by_day.setdefault(r["date"], []).append(r)
    return sorted(by_day.items())


def day_text(d):
    return f"{d:%a %d %b}"


def calendar_lines(cfg, default_releases=(), now=None, days=180):
    """One line per release day for /onepiece releases, approximate ones at the end."""
    now = now or datetime.now()
    out = []
    for when, items in release_days(cfg, default_releases, now, days):
        n = (when.date() - now.date()).days
        tail = " (today!)" if n == 0 else (" (tomorrow)" if n == 1 else f" · in {n} days")
        what = "; ".join(f"**{r['name']}**" for r in items)
        out.append((when, f"📅 **{day_text(when)}**{tail}\n{what}"))
    for r in releases(cfg, default_releases, now):
        n = (r["date"].date() - now.date()).days
        if r["approx"] and 0 <= n <= days:
            out.append((r["date"], f"🔜 **{r['name']}**"))
    return out


# ---------------------------------------------------------------- what's online right now
def _words(name):
    return {w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if len(w) >= 4 and w not in _STOP}


def matches_release(title, release):
    """Does a shop listing look like this release? By set code when the release has one, else by name words."""
    t = (title or "").lower()
    if any(x in t for x in _SKIP_ONLINE):
        return False
    if release["code"]:
        code = release["code"]
        return bool(re.search(r"\b" + code[:2] + r"-?0?" + str(int(code[3:])) + r"\b", t, re.I))
    words = _words(release["name"])
    return len(words) >= 2 and len(words & _words(t)) >= 2


def online_lines(snapshot, items, money=None, short=None, now=None, limit=MAX_ONLINE_LINES):
    """Lines for the post: shops that have today's releases listed, buyable ones first.
    snapshot is latest.json (the "sealed" part: listings from the last check)."""
    sealed = (snapshot or {}).get("sealed") or {}
    ts = sealed.get("ts") or 0
    now_ts = (now or datetime.now()).timestamp()
    if not ts or now_ts - ts > ONLINE_FRESH:
        return []
    money = money or (lambda x: f"${x:,.2f}")
    short = short or (lambda s, n=60: s if len(s) <= n else s[:n - 1] + "…")
    rows = []
    for l in sealed.get("listings") or []:
        if any(matches_release(l.get("name", ""), r) for r in items):
            rows.append(l)
    buy = sorted([l for l in rows if l.get("available") and l.get("price")], key=lambda l: l["price"])
    pre = sorted([l for l in rows if not l.get("available")], key=lambda l: (l.get("price") or 0))
    lines = [f"✅ [{short(l['name'], 55)}]({l.get('cart') or l.get('url')}) **{money(l['price'])}** · {l['shop']}"
             for l in buy]
    lines += [f"⏳ [{short(l['name'], 55)}]({l.get('url')})" + (f" {money(l['price'])}" if l.get("price") else "")
              + f" · {l['shop']}" for l in pre]
    if len(lines) > limit:
        lines = lines[:limit] + [f"…and {len(lines) - limit} more (`/sealed` shows them all)"]
    return lines


# ---------------------------------------------------------------- the posts
def _at(day, hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    return day.replace(hour=h, minute=m, second=0, microsecond=0)


def key_for(day, which):
    return f"{KEY_PREFIX}{day:%Y-%m-%d}|{which}"


def is_key(key):
    return str(key).startswith(KEY_PREFIX)


def _clock(dt):
    return dt.strftime("%I:%M %p").lstrip("0")


def drop_note(windows, day, which):
    """What the bot itself does around this release, from its real drop windows (tcg_bot.parse_windows):
    'The PC copy checks the online shops every 60s tonight 6:00 PM–11:59 PM and tomorrow 8:00 AM–2:00 PM.'
    Empty when no One Piece window touches the eve or the day."""
    eve = day - timedelta(days=1)
    parts = []
    for label, d in ((("tonight" if which == "eve" else "last night"), eve), (("tomorrow" if which == "eve" else "today"), day)):
        for w in windows or []:
            games = w.get("games") or ["onepiece"]
            if "onepiece" not in games:
                continue
            if w["start"].date() <= d.date() <= w["end"].date():
                parts.append(f"{label} {_clock(w['start'])}–{_clock(w['end'])} (every {int(w.get('every', 60))}s)")
                break
    if not parts:
        return ""
    return " The bot checks the online shops " + " and ".join(parts) + "."


def reminders_due(cfg, status, default_releases=(), now=None, snapshot=None, money=None, short=None, windows=None):
    """In-store posts due now that haven't gone out: [{"key", "embed", "ping", "due"}].
    windows: the bot's drop windows, for the "the bot checks every minute tonight" line (optional)."""
    s = settings(cfg)
    if not s["enabled"]:
        return []
    now = now or datetime.now()
    sent = (status or {}).get(STATUS_KEY) or {}
    out = []
    for day, items in release_days(cfg, default_releases, now, days=1, past=0):
        eve = day - timedelta(days=1)
        key = key_for(day, "eve")
        if _at(eve, s["evening"]) <= now < _at(eve, EVENING_UNTIL) and key not in sent:
            out.append({"key": key, "ping": False, "due": _at(eve, s["evening"]),
                        "embed": build_embed(day, items, "eve", [], s, drop_note(windows, day, "eve"))})
        key = key_for(day, "day")
        if _at(day, s["morning"]) <= now < _at(day, MORNING_UNTIL) and key not in sent:
            lines = online_lines(snapshot, items, money, short, now) if s["online"] else []
            out.append({"key": key, "ping": s["ping"], "due": _at(day, s["morning"]),
                        "embed": build_embed(day, items, "day", lines, s, drop_note(windows, day, "day"))})
    return out


def recently_sent(status, seconds=1800, now=None):
    """Release-day posts this copy made (or knows were made) in the last half hour."""
    now = (now or datetime.now()).timestamp()
    sent = (status or {}).get(STATUS_KEY) or {}
    return sorted(k for k, t in sent.items() if now - (float(t) if isinstance(t, (int, float)) else 0) < seconds)


def mark_sent(status, key, now=None):
    now = now or datetime.now()
    sent = status.setdefault(STATUS_KEY, {})
    sent[key] = round(now.timestamp())
    cutoff = now.timestamp() - REMINDER_KEEP_DAYS * 86400
    for k in [k for k, t in sent.items() if (float(t) if isinstance(t, (int, float)) else 0) < cutoff]:
        sent.pop(k)


def build_embed(day, items, which, online=(), s=None, note=""):
    s = s or settings({})
    lines = [f"🏴‍☠️ **{r['name']}**" for r in sorted(items, key=lambda r: (not r["booster"], r["name"]))]  # boosters first
    stores = ", ".join(s["stores"])
    fields = []
    if which == "eve":
        title = f"🛒 Tomorrow in stores · {day_text(day)}"
        foot = (f"Most stores put new stock out from opening, but each store does its own thing and quantities are "
                f"limited. Where to look: {stores}.{note}")
    else:
        title = f"📍 Out today in stores · {day_text(day)}"
        foot = (f"Each store puts stock out on its own schedule and quantities are usually limited, so not every "
                f"store will have it on day one. Where to look: {stores}.{note} Seen some on a shelf? "
                f"`/onepiece report` pings everyone here.")
        if online:
            fields.append({"name": "Online right now (from the last check)", "value": "\n".join(online)[:1024],
                           "inline": False})
    e = {"title": title, "description": "\n".join(lines) + "\n\n" + foot, "color": RED}
    if fields:
        e["fields"] = fields
    return e


# ---------------------------------------------------------------- where it goes
def instore_hook(alerts):
    """The #onepiece-in-store webhook, or "" until the channel is set up (the section stays quiet till then,
    like the Pokémon one, so release posts never land in the wrong channel)."""
    return (alerts or {}).get(HOOK_KEY) or ""


def has_channel(alerts):
    return bool((alerts or {}).get(HOOK_KEY))
