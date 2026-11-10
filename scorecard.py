#!/usr/bin/env python3
"""
Scorecard: is the bot good enough to charge for? (/scorecard in Discord, v2.19)
================================================================================
/missed only hears about the drops you notice the bot missed, so on its own it makes the bot look worse
than it is (the wins never get logged). The scorecard fixes that by grading EVERY alert from another
group, not just the misses:

1. The feed. Pick a channel in your server with `/scorecard feed channel:#fellowship-feed`. Anything
   posted or forwarded there is graded, including Fellowship's channel itself if it lets you "Follow" it
   into your server (Discord's Follow button on announcement channels). Each product link waits
   "grade_after_minutes" (30) after it was posted, so a bot alert that comes a few minutes later still
   counts as "late" rather than "missed", then the bot replies with one line:
       ✅ first by 4 min   🐢 2 min late   👀 seen, no alert   🙈 never seen   🧹 filtered   🔭 shop not watched
   Right-click any message > Apps > "Grade against bot" does the same for one message, anywhere.

2. Uptime. The restock bot notes every hour it finished a check in (uptime.json, both copies), so the
   scorecard can say "checking 99.3% of hours, longest gap 3 hours".

3. The verdict. /scorecard rolls it up (28 days by default) against targets you can change in
   config.json under "scorecard" > "ready":
       days          28    a month of feed data, so one lucky week doesn't decide it
       comparisons   30    drops compared, at shops the bot reads
       win_rate      0.8   first, or no more than "close_minutes" (1) behind, on 8 in 10 of them
       uptime        0.99  at least one copy checking in 99% of hours
   These are starting points for "would someone pay for this", not industry figures. A weekly scorecard
   posts on Monday morning in the feed channel.

Only the feed's grades count towards the verdict; /missed reports are listed separately because they're
only ever misses. Links to shops the bot doesn't read (US shops, Pokémon-only sites...) are listed as
coverage gaps, not counted as losses: add the ones you'll never care about to "ignore_hosts".

Security: grading never looks up a shop the bot doesn't already read, so feed links can't trip the
allowed-sites check (v2.15).

Try it (prints the scorecard; posts nothing):
    py -3 scorecard.py
    py -3 scorecard.py 14
"""
import calendar
import os
import re
import statistics
import sys
import time
from collections import Counter
from datetime import datetime

import misses as ms

DEFAULTS = {
    "feed_channel_id": None,       # where Fellowship's alerts arrive (set with /scorecard feed)
    "post_channel_id": None,       # where the weekly scorecard goes (default: the feed channel)
    "grade_after_minutes": 30,     # wait this long after a feed post before grading it
    "same_drop_hours": 6,          # a bot alert more than this long before the feed post was a different drop
    "ignore_hosts": [],            # shops you'll never want the bot to read: left out of the coverage gaps
    "weekly_post": True,           # post the scorecard on Monday mornings
    "ready": {"days": 28, "comparisons": 30, "win_rate": 0.8, "close_minutes": 1, "uptime": 0.99},
}
IN_SCOPE = ("first", "late", "seen", "not_found", "filtered")
BOT_KINDS = ("Booster box", "Sealed", "New listing")      # the alerts a paying member would get first
SKIP_HOSTS = ("discord.com", "discord.gg", "discordapp.com", "discordapp.net", "twitter.com", "x.com", "t.co",
              "instagram.com", "tiktok.com", "youtube.com", "youtu.be", "imgur.com", "tenor.com", "giphy.com",
              "facebook.com", "reddit.com", "twitch.tv", "linktr.ee", "google.com", "goo.gl")
MEDIA_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".svg")
LINK_RE = re.compile(r"https?://[^\s<>()\[\]\"'`|*]+", re.I)
KEEP_RECENT = 2000


def settings(cfg):
    raw = (cfg or {}).get("scorecard") or {}
    s = {**DEFAULTS, **{k: v for k, v in raw.items() if k != "ready"}}
    s["ready"] = {**DEFAULTS["ready"], **(raw.get("ready") or {})}
    s["ignore_hosts"] = {str(h).lower().removeprefix("www.") for h in (s.get("ignore_hosts") or [])}
    for k in ("feed_channel_id", "post_channel_id"):
        s[k] = int(s[k]) if str(s.get(k) or "").isdigit() else None
    return s


def state_path(tb):
    return os.path.join(tb.HERE, "scorecard.json")


def load_state(tb):
    st = tb.read_json(state_path(tb), {}) or {}
    if not isinstance(st, dict):
        st = {}
    st.setdefault("pending", [])
    st.setdefault("recent", {})
    return st


def save_state(tb, st):
    tb.atomic_write_json(state_path(tb), st, indent=1, ensure_ascii=False)


# ---------------------------------------------------------------- reading a feed message
def _skip_host(host):
    return any(host == h or host.endswith("." + h) for h in SKIP_HOSTS)


def product_links(texts):
    """Product-page links in some text, in order, once each: https://host/path (no www., no ?query).
    Social media, Discord, image and home-page links are left out."""
    out = []
    for text in texts:
        for raw in LINK_RE.findall(str(text or "")):
            host, path = ms.clean_link(raw)
            if not host or _skip_host(host) or path == "/" or path.lower().endswith(MEDIA_EXT):
                continue
            link = f"https://{host}{path}"
            if link not in out:
                out.append(link)
    return out


def _embed_texts(embeds):
    out = []
    for e in embeds or []:
        out += [getattr(e, "url", None), getattr(e, "title", None), getattr(e, "description", None)]
        author = getattr(e, "author", None)
        out.append(getattr(author, "url", None))
        for f in getattr(e, "fields", None) or []:
            out += [getattr(f, "name", None), getattr(f, "value", None)]
    return [t for t in out if t]


def _ts(dt):
    try:
        return dt.timestamp()
    except Exception:  # noqa: BLE001
        return None


def message_links(msg):
    """(links, when it was first posted) for a Discord message: its text, its embeds (alert bots put the link
    in the embed), and forwarded messages (the original post's time counts, not the forward's)."""
    texts = [getattr(msg, "content", "")] + _embed_texts(getattr(msg, "embeds", None))
    times = [_ts(getattr(msg, "created_at", None))]
    for snap in getattr(msg, "message_snapshots", None) or []:
        texts += [getattr(snap, "content", "")] + _embed_texts(getattr(snap, "embeds", None))
        times.append(_ts(getattr(snap, "created_at", None)))
    times = [t for t in times if t]
    return product_links(texts), (min(times) if times else time.time())


# ---------------------------------------------------------------- the queue
def queue(tb, cfg, links, reported, ref=None, source="feed", who="feed", now=None):
    """Put links up for grading. -> the links actually queued (not ignored, not already queued for this drop)."""
    s = settings(cfg)
    now = now or time.time()
    st = load_state(tb)
    window = s["same_drop_hours"] * 3600
    st["recent"] = {k: t for k, t in st["recent"].items() if now - t < max(window, 86400)}
    added = []
    for link in links:
        host, path = ms.clean_link(link)
        if not host or host in s["ignore_hosts"]:
            continue
        key = f"{host}{path}"
        if reported - st["recent"].get(key, -1e18) < window:
            continue                                     # the same drop, posted twice (or forwarded again)
        st["recent"][key] = reported
        st["pending"].append({"link": f"https://{key}", "reported": round(reported), "ref": ref or {},
                              "source": source, "who": str(who)[:60],
                              "due": round(reported + s["grade_after_minutes"] * 60)})
        added.append(f"https://{key}")
    if added and source == "feed":
        st.setdefault("feed_since", round(min(reported, now)))
    if len(st["recent"]) > KEEP_RECENT:
        st["recent"] = dict(sorted(st["recent"].items(), key=lambda kv: kv[1])[-KEEP_RECENT:])
    save_state(tb, st)
    return added


def take_due(tb, now=None):
    now = now or time.time()
    st = load_state(tb)
    due = [p for p in st["pending"] if p.get("due", 0) <= now]
    if due:
        st["pending"] = [p for p in st["pending"] if p.get("due", 0) > now]
        save_state(tb, st)
    return due


def grade(tb, cfg, item, mem=None):
    """Grade one queued link and log it in misses.json (marked as from the feed)."""
    s = settings(cfg)
    host, _ = ms.clean_link(item["link"])
    names = {h.lower().removeprefix("www."): n for h, n in tb.shop_names(cfg).items()}
    res = ms.explain(tb, cfg, item["link"], reported=item["reported"], live=bool(names.get(host)), mem=mem,
                     match_hours=s["same_drop_hours"])
    if res.get("kind") in (None, "error"):
        return res
    res["source"] = item.get("source", "feed")
    ms.record(tb, res, who=item.get("who", "feed"))
    return res


def grade_due(tb, cfg, now=None):
    """Everything whose wait is over: [(item, result)]. Reads the bot's memory once for the lot."""
    items = take_due(tb, now)
    if not items:
        return []
    mem = ms.memory(tb, cfg, remote=True)
    out = []
    for it in items:
        try:
            out.append((it, grade(tb, cfg, it, mem)))
        except Exception as e:  # noqa: BLE001  one bad link never blocks the rest
            out.append((it, {"kind": "error", "headline": f"couldn't grade it ({tb.redact(e)})", "link": it["link"]}))
    return out


def one_line(res):
    """The short reply under a feed post."""
    k = res.get("kind")
    where = res.get("shop") or res.get("host") or ""
    if k == "first":
        return f"✅ Bot was first by {res.get('lead_min', 0)} min · {where}"
    if k == "late":
        return f"🐢 Bot was {res.get('late_min', 0)} min late · {where}"
    if k == "seen":
        why = res["headline"].split(": ", 1)[1].rstrip(".") if ": " in res.get("headline", "") else "no alert"
        return f"👀 Seen, no alert ({why[:140]}) · {where}"
    if k == "not_found":
        return f"🙈 Watched shop, never seen · {where}"
    if k == "filtered":
        return f"🧹 Filtered out ({str(res.get('reason', ''))[:140]}) · {where}"
    if k == "not_watched":
        return f"🔭 Not a shop the bot reads · {where}"
    return f"🤔 {res.get('headline', 'Not graded')}"


# ---------------------------------------------------------------- uptime
def _hours(day_lines):
    out = set()
    for day, line in (day_lines or {}).items():
        try:
            base = calendar.timegm(time.strptime(day, "%Y-%m-%d")) // 3600
        except (TypeError, ValueError):
            continue
        out |= {base + h for h, c in enumerate(str(line)[:24]) if c == "1"}
    return out


def uptime(tb, cfg, days=28, now=None, remote=True):
    """How much of the time each copy was checking. Hours are whole UTC hours; the current hour isn't over,
    so it isn't counted. The window starts when the log does, so a new install isn't marked down."""
    now = now or time.time()
    local = tb.read_json(tb.UPTIME_PATH, {}) or {}
    other = (tb.repo_json(cfg, "uptime.json", max_age=600) or {}) if remote else {}
    copies = {}
    for name in ("pc", "cloud"):
        hrs = set()
        for src in (local, other):
            if isinstance(src, dict):
                hrs |= _hours(src.get(name))
        copies[name] = hrs
    every = copies["pc"] | copies["cloud"]
    if not every:
        return None
    end = int(now // 3600)
    start = max(int((now - days * 86400) // 3600), min(every))
    total = end - start
    if total <= 0:
        return None
    rng = range(start, end)
    gap = run = 0
    for h in rng:
        run = 0 if h in every else run + 1
        gap = max(gap, run)
    return {"pc": len(copies["pc"] & set(rng)) / total, "cloud": len(copies["cloud"] & set(rng)) / total,
            "either": len(every & set(rng)) / total, "longest_gap_h": gap, "hours": total, "since": start * 3600}


# ---------------------------------------------------------------- the scorecard
def _key(url):
    host, path = ms.clean_link(url)
    return f"{host}{ms.handle_of(path) or path}" if host else None


def summary(tb, cfg, days=28, now=None, remote=True, mem=None):
    now = now or time.time()
    s = settings(cfg)
    r = s["ready"]
    st = load_state(tb)
    since = now - days * 86400
    log = [m for m in (tb.read_json(ms.misses_path(tb), []) or []) if isinstance(m, dict)
           and (m.get("reported") or m.get("t", 0)) >= since]
    feed = [m for m in log if m.get("source") == "feed"]
    manual = [m for m in log if m.get("source") != "feed"]
    scope = [m for m in feed if m.get("kind") in IN_SCOPE]
    kinds = Counter(m.get("kind") for m in scope)
    close = r["close_minutes"]
    wins = kinds["first"] + sum(1 for m in scope if m.get("kind") == "late" and (m.get("late_min") or 0) <= close)
    leads = sorted(m["lead_min"] for m in scope if m.get("kind") == "first" and m.get("lead_min") is not None)
    lates = sorted(m["late_min"] for m in scope if m.get("kind") == "late" and m.get("late_min") is not None)
    gaps = Counter(m.get("host") for m in feed if m.get("kind") == "not_watched"
                   and m.get("host") not in s["ignore_hosts"])
    weak = Counter(m.get("shop") or m.get("host") for m in scope if m.get("kind") != "first"
                   and not (m.get("kind") == "late" and (m.get("late_min") or 0) <= close))

    feed_since = st.get("feed_since") or (min(m.get("reported") or m["t"] for m in feed) if feed else None)
    data_days = (now - feed_since) / 86400 if feed_since else 0

    # bot-only finds: drops the bot alerted that the feed never mentioned (only while the feed was running)
    bot_only = []
    if feed_since:
        mem = mem or ms.memory(tb, cfg, remote)
        seen_keys = {_key(m.get("link", "")) for m in feed}
        start = max(since, feed_since)
        alerted = {}
        for e in mem["events"]:
            if (e.get("event") == "alert" and e.get("kind") in BOT_KINDS and e.get("t", 0) >= start
                    and not str(e.get("shop", "")).startswith("eBay")):
                k = _key(e.get("url", ""))
                if k and k not in seen_keys:
                    alerted.setdefault(k, e)
        bot_only = sorted(alerted.values(), key=lambda e: e["t"])

    up = uptime(tb, cfg, days, now, remote)
    win_rate = wins / len(scope) if scope else None
    checks = [
        (data_days >= r["days"], f"{min(data_days, days):.0f} of {r['days']} days of feed data"),
        (len(scope) >= r["comparisons"], f"{len(scope)} of {r['comparisons']} drops compared"),
        (win_rate is not None and win_rate >= r["win_rate"],
         f"first or within {close} min on {win_rate:.0%} (target {r['win_rate']:.0%})" if win_rate is not None
         else f"first or within {close} min: no comparisons yet (target {r['win_rate']:.0%})"),
        (bool(up) and up["either"] >= r["uptime"],
         f"checking {up['either']:.1%} of hours (target {r['uptime']:.0%})" if up
         else f"uptime: no log yet (target {r['uptime']:.0%})"),
    ]
    return {"days": days, "feed": len(feed), "scope": len(scope), "kinds": kinds, "wins": wins, "win_rate": win_rate,
            "leads": leads, "lates": lates, "gaps": gaps, "weak": weak, "manual": len(manual),
            "bot_only": bot_only, "uptime": up, "checks": checks, "ready": all(ok for ok, _ in checks),
            "feed_since": feed_since, "pending": len(st["pending"]), "settings": s}


def _mid(xs):
    return statistics.median(xs) if xs else None


def render(sc):
    """(title, [lines]) for Discord or the console."""
    days = sc["days"]
    title = ("🟢 Ready to charge for" if sc["ready"] else "🟡 Not ready to charge for yet") + f" · last {days} days"
    lines = ["**Readiness**"] + [("✅ " if ok else "❌ ") + text for ok, text in sc["checks"]]
    if not sc["feed_since"]:
        lines += ["", "No feed yet. Pick the channel Fellowship's alerts arrive in with `/scorecard feed`, or "
                      "forward their alerts into it, and the bot grades every one."]
    if sc["scope"]:
        k = sc["kinds"]
        lines += ["", f"**Head to head** ({sc['scope']} drops at shops the bot reads)"]
        for kind in IN_SCOPE:
            if k[kind]:
                lines.append(f"{ms.ICON[kind]} {ms.NAME[kind]}: {k[kind]}")
        if sc["leads"]:
            lines.append(f"When first: ahead by {_mid(sc['leads']):.0f} min in the middle case")
        if sc["lates"]:
            lines.append(f"When late: behind by {_mid(sc['lates']):.0f} min in the middle case "
                         f"(worst {sc['lates'][-1]} min)")
        if sc["weak"]:
            lines.append("Where it loses most: " + ", ".join(f"{h} ({n})" for h, n in sc["weak"].most_common(5)))
    if sc["bot_only"]:
        names = ", ".join(f"{e.get('shop', '?')}" for e in sc["bot_only"][-5:])
        lines += ["", f"**Bot-only finds**: {len(sc['bot_only'])} drop(s) the bot alerted that the feed never "
                      f"posted (latest: {names})"]
    if sc["gaps"]:
        lines += ["", "**Shops in the feed the bot doesn't read**: "
                  + ", ".join(f"{h} ({n})" for h, n in sc["gaps"].most_common(6))
                  + "\nWorth adding if they're Australian; put the rest in \"ignore_hosts\"."]
    up = sc["uptime"]
    if up:
        lines += ["", f"**Uptime** since {datetime.fromtimestamp(up['since']):%d %b}: PC {up['pc']:.1%}, "
                      f"cloud {up['cloud']:.1%}, either {up['either']:.1%} · longest gap {up['longest_gap_h']} h"]
    extra = []
    if sc["pending"]:
        extra.append(f"{sc['pending']} feed link(s) waiting to be graded")
    if sc["manual"]:
        extra.append(f"{sc['manual']} /missed report(s) (not in the verdict: they're only ever misses)")
    if extra:
        lines += ["", " · ".join(extra)]
    return title, lines


# ---------------------------------------------------------------- the weekly post
def weekly_due(tb, cfg, now=None):
    """True once a week, on Monday from 9am (the PC's time), and remembers that it said so."""
    s = settings(cfg)
    if not s["weekly_post"]:
        return False
    d = datetime.fromtimestamp(now or time.time())
    if d.weekday() != 0 or d.hour < 9:
        return False
    week = d.strftime("%G-W%V")
    st = load_state(tb)
    if st.get("weekly") == week:
        return False
    st["weekly"] = week
    save_state(tb, st)
    return True


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    import tcg_bot as tb
    days = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 28
    title, lines = render(summary(tb, tb.load_config(), days))
    print(title)
    print("\n".join(lines).replace("**", ""))


if __name__ == "__main__":
    main()
