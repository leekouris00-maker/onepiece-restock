#!/usr/bin/env python3
"""
CAPTCHA detection for the restock bot (v2.15; on by itself since v2.16)
=======================================================================
Since v2.16 this runs whether or not the rest of "security" is switched on (PC copy and cloud copy).
When a shop answers with a "prove you're human" page instead of its normal reply, the bot:

  1. notices (Cloudflare challenge / Turnstile, hCaptcha, reCAPTCHA, PerimeterX, DataDome, Shopify's
     /challenge page, or a "verify you are human" page),
  2. pauses that shop - no more requests to it,
  3. tells you once (Discord #bot-status, and the Security page), and
     (unless it's a "slow down" challenge - HTTP 429 - which is temporary: the shop is paused for 10 min,
     doubling up to 4 hours, with one try after each, and you're only told if it's still going after 6 hours),
  4. waits for you. Open the shop in your own browser, do the check if you want to, then say Resume:
     /captcha resume:<shop> in Discord, or the Resume button on the Security page when security is on.
     The bot then tries the shop again; if the shop still challenges it, the shop is paused again.
     (The cloud copy has nobody to press Resume, so it tries a paused shop once a day by itself.)

v2.20 - the hand-off, so a pause costs you less attention (still nothing is solved or got round):
  * PC copy: when a shop starts waiting for you and desk mode is on (/desk on), the bot opens the shop's
    front page in YOUR browser so you can see for yourself. It also makes two tries of its own, one after
    15 minutes and one 2 hours after that, and carries on by itself if the shop answers normally; after
    those it waits for Resume as before. Passing the check in your browser doesn't pass the bot - the bot
    never uses your browser's cookies - it only shows you whether the shop is open to people.
  * Cloud copy: a shop that has refused it for 3 days running is LEFT TO THE PC COPY: one last notice,
    then no more reminders, and one try a week instead of one a day.

The bot never tries to solve, skip or get round a challenge, never copies cookies from your browser and
never switches address to dodge one: a pause stays in place whichever endpoint is in use. A shop that
keeps challenging the bot doesn't want it there, and stays paused.

Settings (config.json "security" > "captcha"):
  "enabled": true        detection on (when security is on)
  "recheck_hours": 0     0 = wait for you to press Resume. A number = try the shop once after that many
                         hours by itself (at least 6).
  "open_tab": "desk"     v2.20: open a newly paused shop in your browser - "desk" = only while desk mode is on,
                         true = always, false = never. PC copy only.
"""
import re
import time

MIN_RECHECK_HOURS = 6
BACKOFF_FIRST = 10 * 60           # a "slow down" challenge: first pause
BACKOFF_MAX = 4 * 3600            # ...doubling up to this
SAME_BURST = 60                   # challenges this close together count once
STUCK_AFTER = 6 * 3600            # still challenged after this long: wait for you, and tell you
NOTIFY_GAP = 24 * 3600
BODY_LOOK = 60_000
AUTO_TRIES = (15 * 60, 2 * 3600)  # v2.20, PC copy: the bot's own tries at a shop that's waiting for you, then no more
LEAVE_AFTER = 3 * 86400           # v2.20, cloud copy: refused this long without a break = left to the PC copy
LEFT_RECHECK_HOURS = 7 * 24.0     # ...and tried this often from then on

# (name, header test, body markers) - body markers are only looked for in HTML replies
_HEADER_SIGNS = [
    ("Cloudflare challenge", lambda h: str(h.get("cf-mitigated", "")).lower() == "challenge"),
    ("DataDome", lambda h: "datadome" in str(h.get("x-datadome", "") or h.get("x-dd-b", "")).lower()
     or str(h.get("x-datadome-cid", "")) != ""),
]
_BODY_SIGNS = [
    ("Cloudflare challenge", ("challenges.cloudflare.com", "cf-chl-", "/cdn-cgi/challenge-platform", "cf_chl_opt")),
    ("hCaptcha", ("hcaptcha.com/1/api.js", "class=\"h-captcha\"", "h-captcha-response")),
    ("reCAPTCHA", ("google.com/recaptcha", "recaptcha/api.js", "class=\"g-recaptcha\"", "g-recaptcha-response")),
    ("PerimeterX", ("px-captcha", "_pxcaptcha", "perimeterx")),
    ("DataDome", ("captcha-delivery.com", "geo.captcha-delivery")),
    ("Shopify challenge", ("action=\"/challenge\"", "shopify-challenge")),
    ("human verification", ("verify you are human", "verifying you are human", "are you a robot", "are you human?",
                            "complete the security check", "unusual traffic from your")),
]
_CHALLENGE_STATUS = (401, 403, 429, 503)


def settings(cfg):
    sec = (cfg or {}).get("security")
    raw = (sec.get("captcha") if isinstance(sec, dict) else None)
    raw = raw if isinstance(raw, dict) else {}
    try:
        hours = float(raw.get("recheck_hours") or 0)
    except (TypeError, ValueError):
        hours = 0.0
    tab = raw.get("open_tab", "desk")
    return {"enabled": raw.get("enabled", True) is not False,
            "recheck_hours": 0.0 if hours <= 0 else max(MIN_RECHECK_HOURS, hours),
            "open_tab": "always" if tab is True else "never" if tab is False else "desk"}


def detect(status, headers, body, location=""):
    """The kind of challenge this reply is, or None. A normal JSON reply is never a challenge."""
    h = {str(k).lower(): v for k, v in (headers or {}).items()}
    for name, test in _HEADER_SIGNS:
        try:
            if test(h):
                return name
        except Exception:  # noqa: BLE001
            continue
    loc = str(location or h.get("location") or "").lower()
    if loc.split("?", 1)[0].rstrip("/").endswith("/challenge"):
        return "Shopify challenge"
    try:
        text = (body or b"")[:BODY_LOOK].decode("utf-8", "replace").lower()
    except Exception:  # noqa: BLE001
        return None
    head = text.lstrip()[:200]
    if not (head.startswith("<") or "<html" in head):
        return None                                   # JSON, XML feeds without markup, plain text
    ctype = str(h.get("content-type", "")).lower()
    if "xml" in ctype and "html" not in ctype:
        return None
    if status in _CHALLENGE_STATUS or 200 <= int(status or 0) < 300:
        for name, marks in _BODY_SIGNS:
            if any(m in text for m in marks):
                # a real 200 page can carry a reCAPTCHA script for its newsletter box: only a refusal counts for those
                if 200 <= int(status or 0) < 300 and name in ("reCAPTCHA", "hCaptcha"):
                    continue
                return name
        if status in (403, 503) and "just a moment" in text[:3000] and "cloudflare" in text:
            return "Cloudflare challenge"
    return None


def paused(state):
    """{host: entry} for paused shops (waiting for you, or a temporary "slow down" pause with "until")."""
    c = state.get("captcha")
    return c if isinstance(c, dict) else {}


def is_paused(state, host, cfg=None, now=None, hours=None):
    """True while the shop is paused. A temporary pause (a "slow down" challenge) ends at its "until" time
    (one try). With "recheck_hours" set, a pause waiting for you also gets one try after that long.
    "hours" overrides the setting (the cloud copy's once-a-day try)."""
    e = paused(state).get(host)
    if not e:
        return False
    now = now or time.time()
    if e.get("until"):
        return now < float(e["until"])
    if e.get("try_at") and now >= float(e["try_at"]):
        return False                    # v2.20: one of the bot's own tries is due
    hours = settings(cfg)["recheck_hours"] if hours is None else hours
    if e.get("left"):
        hours = max(hours or 0, LEFT_RECHECK_HOURS)     # v2.20: left to the PC copy - once a week
    if hours and now - float(e.get("since") or 0) >= hours * 3600:
        return False
    return True


def pause(state, host, kind, url, now=None, status=None, notify_gap=None, auto_tries=(), leave_after=None):
    """Record the challenge. Returns True if you should be told.

    A challenge sent with HTTP 429 is the shop's way of saying "slow down" (Shopify shops behind Cloudflare
    send "Verifying your connection..." with a 429 when a lot of requests arrive at once; seen 10 Nov 2026).
    It clears by itself, so it's a TEMPORARY pause: 10 min, doubling up to 4 h, with one try after each.
    Only if the shop is still challenging after STUCK_AFTER does it wait for you, and you're told.
    Any other challenge waits for you straight away. Either way nothing tries to get past it.

    v2.20: "auto_tries" (PC copy) = seconds until each of the bot's own tries at a shop that's waiting for
    you; when they're used up it just waits. "leave_after" (cloud copy) = a shop challenged this long
    without a break is marked "left" (to the PC copy): told once more, then never again."""
    now = now or time.time()
    c = state.setdefault("captcha", {})
    e = c.get(host) or {}
    if e and now - float(e.get("since") or 0) < SAME_BURST:
        return False                    # several replies from the same moment (the bot reads pages in parallel): one pause
    first = float(e.get("first") or now)
    count = int(e.get("count") or 0) + 1
    temporary = int(status or 0) == 429 and not e.get("needs_you") and now - first < STUCK_AFTER
    entry = {"kind": kind, "since": round(now), "first": round(first), "url": str(url)[:300], "count": count,
             "status": int(status or 0), "told": e.get("told")}
    if temporary:
        entry["until"] = round(now + min(BACKOFF_MAX, BACKOFF_FIRST * 2 ** (count - 1)))
        c[host] = entry
        return False
    entry["needs_you"] = True
    if e.get("tab"):
        entry["tab"] = e["tab"]
    if leave_after and (e.get("left") or now - first >= leave_after):
        entry["left"] = True
        if not e.get("left"):
            entry["told"] = round(now)
        c[host] = entry
        return not e.get("left")
    if auto_tries:
        tried = int(e.get("tried") or 0) + 1 if e.get("needs_you") else 0
        entry["tried"] = tried
        if tried < len(auto_tries):
            entry["try_at"] = round(now + auto_tries[tried])
    tell = not e.get("told") or now - float(e["told"]) >= (notify_gap or NOTIFY_GAP)
    if tell:
        entry["told"] = round(now)
    c[host] = entry
    return tell


def same_burst(state, host, now=None):
    """True if this shop was paused moments ago (parallel replies from the same check)."""
    e = paused(state).get(host)
    return bool(e) and (now or time.time()) - float(e.get("since") or 0) < SAME_BURST


def resume(state, host):
    """You've said to try again. True if the shop was paused."""
    return paused(state).pop(host, None) is not None


HOW_PAGE = "press **Resume** for it on the bot's Security page"
HOW_DISCORD = "use `/captcha resume:{name}` in Discord"
HOW_CLOUD = ("This is the cloud copy, which shops often refuse because it runs from GitHub's addresses; the PC copy on "
             "your home connection may still read them fine. The cloud copy tries each one again once a day by itself.")


HOW_LEFT = ("It has refused the cloud copy for {days} days running, so the cloud copy is leaving it to the PC copy on your "
            "home connection: no more reminders about it, and one try a week in case that changes.")
NOT_A_PASS = "Doing the check in your browser doesn't let the bot in; it only shows you the shop is open to people."


def _auto_try(e, now=None):
    """v2.20: ' The bot tries once more by itself in about N min.' while one of its own tries is still to come."""
    at = float(e.get("try_at") or 0)
    left = at - (now or time.time())
    if left <= 0:
        return ""
    return (f" The bot tries once more by itself in about {int(left // 60) + 1} min" if left < 5400
            else f" The bot tries once more by itself in about {round(left / 3600)} h") + \
        " and carries on if the shop answers normally."


def shop_link(name, host):
    """v2.19.5: the shop's name as a Discord link to its front page, so a notice can be tapped straight
    through to the shop. (The address the bot was refused on is usually a products.json feed, which is no
    use in a browser.) Markdown characters in the name are escaped so they can't break the link."""
    label = re.sub(r"([\\\[\]()*_~`|>])", r"\\\1", str(name or host))
    h = str(host or "").strip().strip("/")
    return f"[{label}](https://{h}/)" if h else label


def message(name, host, e, how=HOW_PAGE, cloud=False):
    """The notice for one shop. "how" is what Resume looks like where this copy runs."""
    how = how.replace("{name}", str(name))
    shop = shop_link(name, host)
    if cloud and e.get("left"):
        return (f"🧩 **{shop} keeps asking the cloud copy for human verification** ({e.get('kind')}). "
                + HOW_LEFT.format(days=LEAVE_AFTER // 86400))
    if cloud:
        return (f"🧩 **{shop} is asking the bot for human verification** ({e.get('kind')}). The bot has stopped checking "
                f"it and won't try to get round it. {HOW_CLOUD}")
    if int(e.get("status") or 0) == 429:
        return (f"🧩 **{shop} has been asking the bot to verify it's human for {STUCK_AFTER // 3600} hours** "
                f"({e.get('kind')}). The bot has stopped checking it and won't try to get round it.{_auto_try(e)} If the "
                f"shop opens normally in your own browser, {how} to try again sooner.")
    return (f"🧩 **{shop} is asking for human verification** ({e.get('kind')}). The bot has stopped checking it and "
            f"won't try to get round it. To carry on: open https://{host} in your own browser, and if it lets you in, "
            f"{how}.{_auto_try(e)} If the shop challenges the bot again it'll be paused again. {NOT_A_PASS}")


def digest(items, how=HOW_DISCORD, cloud=False):
    """One notice for several shops from the same check. items: [(name, host, entry), ...]"""
    lines = "\n".join(f"• **{shop_link(name, host)}** ({e.get('kind')})"
                      + (" - now left to the PC copy, one try a week" if cloud and e.get("left") else "")
                      for name, host, e in items[:40])
    more = f"\n…and {len(items) - 40} more" if len(items) > 40 else ""
    head = (f"🧩 **{len(items)} shops are asking the bot for human verification.** The bot has stopped checking them "
            f"and won't try to get round it.\n{lines}{more}\n")
    if cloud:
        return head + HOW_CLOUD
    tries = (" The bot also makes two tries of its own at each (after 15 min, then 2 h later)."
             if any(e.get("try_at") for _, _, e in items) else "")
    return head + (f"To carry on: open a shop in your own browser, and if it lets you in, "
                   f"{how.replace('{name}', '<shop>')} (or `resume:all`).{tries} A shop that challenges the bot again is paused again.")
