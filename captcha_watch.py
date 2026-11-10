#!/usr/bin/env python3
"""
CAPTCHA detection for the restock bot (v2.15)
=============================================
When a shop answers with a "prove you're human" page instead of its normal reply, the bot:

  1. notices (Cloudflare challenge / Turnstile, hCaptcha, reCAPTCHA, PerimeterX, DataDome, Shopify's
     /challenge page, or a "verify you are human" page),
  2. pauses that shop - no more requests to it,
  3. tells you once (Discord #bot-status, and the Security page), and
  4. waits for you. Open the shop in your own browser, do the check if you want to, then press Resume on
     the Security page. The bot then tries the shop again; if the shop still challenges it, the shop is
     paused again.

The bot never tries to solve, skip or get round a challenge, never copies cookies from your browser and
never switches address to dodge one: a pause stays in place whichever endpoint is in use. A shop that
keeps challenging the bot doesn't want it there, and stays paused.

Settings (config.json "security" > "captcha"):
  "enabled": true        detection on (when security is on)
  "recheck_hours": 0     0 = wait for you to press Resume. A number = try the shop once after that many
                         hours by itself (at least 6).
"""
import time

MIN_RECHECK_HOURS = 6
NOTIFY_GAP = 24 * 3600
BODY_LOOK = 60_000

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
    return {"enabled": raw.get("enabled", True) is not False,
            "recheck_hours": 0.0 if hours <= 0 else max(MIN_RECHECK_HOURS, hours)}


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
    """{host: entry} for shops waiting on you."""
    c = state.get("captcha")
    return c if isinstance(c, dict) else {}


def is_paused(state, host, cfg=None, now=None):
    """True while the shop is paused. With "recheck_hours" set, False once that long has passed (one try)."""
    e = paused(state).get(host)
    if not e:
        return False
    hours = settings(cfg)["recheck_hours"]
    if hours and (now or time.time()) - float(e.get("since") or 0) >= hours * 3600:
        return False
    return True


def pause(state, host, kind, url, now=None):
    """Record the challenge. Returns True if you should be told (first time, or a day since the last notice)."""
    now = now or time.time()
    c = state.setdefault("captcha", {})
    e = c.get(host) or {}
    tell = not e.get("told") or now - float(e["told"]) >= NOTIFY_GAP
    c[host] = {"kind": kind, "since": round(now), "first": e.get("first") or round(now), "url": str(url)[:300],
               "count": int(e.get("count") or 0) + 1, "told": round(now) if tell else e.get("told")}
    return tell


def resume(state, host):
    """You've said to try again. True if the shop was paused."""
    return paused(state).pop(host, None) is not None


def message(name, host, e):
    return (f"🧩 **{name} is asking for human verification** ({e.get('kind')}). The bot has stopped checking it and "
            f"won't try to get round it. To carry on: open https://{host} in your own browser, and if it lets you in, "
            f"press **Resume** for it on the bot's Security page. If the shop challenges the bot again it'll be paused again.")
