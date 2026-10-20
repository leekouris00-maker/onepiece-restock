#!/usr/bin/env python3
"""
One Piece TCG restock bot (Lee's version) - v2
==============================================

Checks Australian shops for:
  1. English One Piece booster boxes in stock (or buyable on pre-order) at or under your max price
  2. Singles on your want list at Elemental Arcade, Mayhem Collectables and Good Games
  3. Other English sealed products on a watch list (starter decks, double packs, illustration boxes,
     premium collections...) at or under their max price - see DEFAULT_SEALED_WATCH
  4. NEW listings: a box or watched product a shop has just added, even before it's buyable
  5. eBay: cards and collectibles in ebay_watch.json (e.g. the Nike x One Piece TNs and DON!! cards) listed
     at or under your max, delivered (needs a free eBay key, see the top of ebay_watch.py)
  6. Pokémon (pokemon_watch.py): the upcoming English releases, each in its own Discord channel - new
     listings and pre-orders, stock at or under your max, and in-store release-day posts. Nothing posts
     until the Pokémon channels exist (add_pokemon_channels.bat, or /pokemon setup in Discord).
  7. Price drops (v2.3): every hour it reads Elemental Arcade's and Good Games' whole One Piece singles
     lists and remembers each card's near-mint price; every 6 hours (12am, 6am, 12pm, 6pm) it posts the
     10 singles in stock that got the most cheaper over those 6 hours (10%+ and $1+ off). Settings:
     "price_drops" in config.json; /pricedrops in Discord shows them any time.

Singles prices are for near mint when it's in stock, otherwise the cheapest condition that is (the
alert says which, e.g. "$2.00 (LP)"). Before v2.3 Elemental quoted its cheapest condition's price even
when that copy was sold out.

Every find comes with a one-tap "Buy" link that puts it straight into your cart at
checkout. You still press pay yourself - the bot never buys anything or logs in.

Only needs Python 3.8+ (no extra installs).

    python tcg_bot.py                 check once, show only NEW finds since last run
    python tcg_bot.py --all           check once, show everything that currently matches
    python tcg_bot.py --loop 30       keep running, check every 30 minutes
    python tcg_bot.py --sealed        only check booster boxes
    python tcg_bot.py --singles       only check singles
    python tcg_bot.py --pokemon       only check Pokémon (try: --pokemon --all --dry-run)
    python tcg_bot.py --test-discord  post a test message to your Discord channel and stop
    python tcg_bot.py --recap         post the daily recap (the GitHub copy does this every morning)
    python tcg_bot.py --dry-run       check and print, but post nothing and save nothing (safe to test with)
    python tcg_bot.py --self-test     check config.json, file access and one shop, then stop

What's new in v2 (all optional settings go in config.json; nothing to change if you're happy):
  * Much faster checks: connections to each shop are kept open and reused, replies are gzip-
    compressed, duplicate requests within a check are shared, singles and boxes are checked at the
    same time, and a shop that refuses the bot (401/403) isn't asked again in the same check.
  * Alerts can't get lost: posts wait out Discord's rate limits and retry; anything that still
    doesn't reach Discord is tried again next check instead of being marked as seen. More than 10
    finds go out over several messages instead of being cut off.
  * Shops with more than 250 products are read page by page (page 2, 3...), so nothing is missed.
  * Singles found at the same shop get one combined cart link ("🧺 one cart"), to save on shipping.
  * Box alerts show the lowest price the bot has seen (price_history.json); /history and /stats in
    Discord use it too.
  * Instant Discord commands: every check saves its results to latest.json.
  * Polite by default: follows each shop's robots.txt ("respect_robots": false to switch off), at
    most 4 requests at once per shop, and a shop that's been down 3 checks in a row is retried every
    15 minutes instead of every check ("down_retry_minutes").
  * "singles_every_minutes": 15  - in --loop, check singles less often than boxes (boxes stay fast)
  * "auto_drop_windows": true    - drop mode turns itself on for booster releases in the release list
                                   (the evening before 6pm-midnight, release day 8am-2pm), on top of
                                   any "drop_windows" you add yourself
  * "alerts": {"quiet_hours": "23:00-07:00"} - no @ping or phone push in those hours (still posted),
                                   except booster boxes; /mute in Discord silences pings for a while
  * Webhooks and the bot token can live in secrets.json (same keys as "alerts"), which is never
    committed, instead of config.json.
  * config.json is checked when loaded: a wrong value turns that one item off with a warning
    instead of stopping the bot, and a Notepad "BOM" no longer breaks it.

Drop-day mode (in --loop only): add "drop_windows" to config.json, e.g.
    "drop_windows": [
      {"name": "OP-18 release", "start": "2026-11-20 18:00", "end": "2026-11-20 20:00", "every_seconds": 60}
    ]
Between start and end (your computer's local time) it checks booster boxes every
"every_seconds" (30 at the fastest) instead of the normal --loop gap. Add
"sealed_only": false to a window to check singles too.

New-listing alerts are on by default. To switch them off: "new_listings": false

eBay finds (ebay_watch.json) go to "discord_webhook_ebay" if set, otherwise the singles channel.

Status posts (no ping) go to "discord_webhook_status" if set, otherwise the boxes channel:
bot online, drop mode on/off, a shop not loading for 3 checks / loading again, config.json
typos, failed checks, and (cloud copy) the PC going quiet or coming back.

No double posts: give both copies the same private "heartbeat_topic" (in "alerts" on the PC,
the HEARTBEAT_TOPIC secret in the cloud, plus HEARTBEAT_ROLE=listen there). The PC copy says
"I'm on" through ntfy.sh every 15 minutes; the cloud copy keeps checking and remembering, but
only posts while it hasn't heard from the PC for 20 minutes. When the PC goes quiet, the cloud
copy also posts anything it saw after the PC's last "I'm on", so nothing falls in the gap.

Alert settings can also come from environment variables, which win over config.json.
The cloud copy (GitHub Actions) uses these so the webhooks stay secret:
    DISCORD_WEBHOOK, DISCORD_WEBHOOK_BOXES, DISCORD_WEBHOOK_SINGLES, DISCORD_WEBHOOK_SEALED, DISCORD_PING,
    DISCORD_WEBHOOK_EBAY, DISCORD_WEBHOOK_STATUS, DISCORD_WEBHOOK_RECAP,
    NTFY_TOPIC, BOT_NAME (the name the Discord posts show, e.g. "One Piece Restock (cloud)"),
    HEARTBEAT_TOPIC, HEARTBEAT_ROLE, POKEMON_WEBHOOKS (one line of JSON), POKEMON_PING
"""
import argparse
import base64
import gzip
import http.client
import json
import os
import random
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections import Counter, OrderedDict, defaultdict, deque
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta

try:
    import ebay_watch          # eBay watch list (ebay_watch.json); optional
except ImportError:            # ebay_watch.py not next to the bot: eBay is skipped, everything else as normal
    ebay_watch = None
try:
    import pokemon_watch       # Pokémon releases; optional
except ImportError:            # pokemon_watch.py not next to the bot: Pokémon is skipped
    pokemon_watch = None

VERSION = "2.3.0"
POKE = "pokemon"
ONE_PIECE = "onepiece"

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
SECRETS_PATH = os.path.join(HERE, "secrets.json")        # optional; same keys as "alerts"; never commit it
STATE_PATH = os.path.join(HERE, "seen.json")
KNOWN_PATH = os.path.join(HERE, "known_products.json")
STATUS_PATH = os.path.join(HERE, "status.json")
RECAP_PATH = os.path.join(HERE, "recap.json")          # yesterday's prices, for the daily recap
PICKS_PATH = os.path.join(HERE, "market_picks.json")   # optional: value picks from the market ledger
SNAPSHOT_PATH = os.path.join(HERE, "latest.json")      # last check's results, so Discord commands answer instantly
HISTORY_PATH = os.path.join(HERE, "price_history.json")  # one price per listing per day ("lowest seen", /history)
EVENTS_PATH = os.path.join(HERE, "events.jsonl")       # restocks, sell-outs and new listings, for /stats
CONTROLS_PATH = os.path.join(HERE, "controls.json")    # switches set from Discord (e.g. /mute)
# The ledger saves its picks (and the cloud copy its recap snapshot) to the GitHub repo; the PC copy
# reads them from there. Override with "repo_raw_url" in config.json.
REPO_RAW_URL = "https://raw.githubusercontent.com/leekouris00-maker/onepiece-restock/master"
_remote_cache = {}
LOG_PATH = os.path.join(HERE, "finds.log")
LOG_MAX_BYTES = 1_000_000       # finds.log rolls over to finds.log.1 past this size

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

MIN_DROP_SECONDS = 30
SHOP_DOWN_AFTER = 3             # a shop that fails this many checks in a row gets a "can't reach" status post
OFFLINE_SHARE = 0.8             # if this share of shops fail in the same check, it's the bot's side, not the shops
OFFLINE_MIN_SHOPS = 4           # ...but only judge that when at least this many shops were checked
SINGLES_EVERY_DEFAULT = 15       # singles (3 shops, lots of product pages) every 15 min; boxes every check
DOWN_RETRY_MIN = 15             # ...and is then retried every 15 minutes instead of every check

# per-run record of which shop websites answered: host -> [ok, failed]
_host_results = {}
_host_lock = threading.Lock()

# environment variable -> key in config.json "alerts"
ENV_ALERTS = {
    "DISCORD_WEBHOOK": "discord_webhook",
    "DISCORD_WEBHOOK_BOXES": "discord_webhook_boxes",
    "DISCORD_WEBHOOK_SINGLES": "discord_webhook_singles",
    "DISCORD_WEBHOOK_SEALED": "discord_webhook_sealed",
    "DISCORD_PING": "discord_ping",
    "NTFY_TOPIC": "ntfy_topic",
    "BOT_NAME": "bot_name",
    "DISCORD_WEBHOOK_RECAP": "discord_webhook_recap",
    "DISCORD_WEBHOOK_STATUS": "discord_webhook_status",
    "DISCORD_WEBHOOK_EBAY": "discord_webhook_ebay",
    "DISCORD_WEBHOOK_DROPS": "discord_webhook_drops",      # optional: the 6-hourly price drops get their own channel
    "LEDGER_URL": "ledger_url",
    "HEARTBEAT_TOPIC": "heartbeat_topic",
    "HEARTBEAT_ROLE": "heartbeat_role",
    "POKEMON_WEBHOOKS": "pokemon_webhooks",     # {"<release>": link, "restocks": link, "in-store": link} as JSON
    "POKEMON_PING": "pokemon_ping",
}

# PC and cloud copies share a private ntfy topic. The PC says "I'm on" there now and then;
# the cloud copy reads it and stays quiet while the PC is on, so finds aren't posted twice.
HEARTBEAT_EVERY = 15 * 60       # PC sends at most one "I'm on" message every 15 minutes
HEARTBEAT_FRESH = "20m"         # cloud treats the PC as on if it heard from it in the last 20 minutes
_last_heartbeat = 0.0

# Variant words that mean "not the regular print" (used unless a card overrides it)
DEFAULT_EXCLUDE = [
    "alternate art", "alt art", "parallel", "(sp)", " sp ", "manga", "wanted", "full art",
    "treasure", "pre-release", "prerelease", "release event", "japanese", "promotion",
    "championship", "store treasure", "beginners deck", "anniversary", "sp gold", "sp silver",
    "playmat", "jumbo", "signed",
]
BOX_EXCLUDE = ["japanese", "(jp)", " jp ", "asia", "asian", "chinese", "korean",
               "case", "sleeved", "single pack", "booster pack", "display case"]

BOX_KINDS = ("Booster box", "Sealed", "New listing")

# Other English sealed products to watch (besides booster boxes). Each alerts when it's buyable at or
# under "max" (AUD), and as a new listing when a shop first lists it. Override with "sealed_watch"
# in config.json - same format. "match" is any text in the shop's product title (dashes optional).
DEFAULT_SEALED_WATCH = [
    {"name": "Starter decks ST-37 / ST-38", "match": ["ST-37", "ST-38"], "max": 45},
    {"name": "Double Pack Set DP-13", "match": ["DP-13"], "max": 35},
    {"name": "Illustration Box IB-09 / IB-10", "match": ["IB-09", "IB-10", "Illustration Box"], "max": 130},
    {"name": "Heroines Gift Collection", "match": ["Gift Collection"], "max": 120},
    {"name": "Ace, Sabo & Luffy Premium Card Collection", "match": ["Ace, Sabo", "Sabo & Luffy", "Sabo and Luffy"], "max": 150},
    {"name": "29th Anniversary Premium Card Collection", "match": ["29th Anniversary"], "max": 150},
]
# English release calendar for the recap's "coming up" section. Override with "releases" in config.json.
DEFAULT_RELEASES = [
    {"date": "2026-10-30", "name": "EB-05 Heroines Edition Vol. 2"},
    {"date": "2026-10-30", "name": "TS-03 Mini Case Set Vol. 3"},
    {"date": "2026-11-20", "name": "OP-18 The Dominance of God"},
    {"date": "2026-11-20", "name": "Heroines Gift Collection"},
    {"date": "2026-11-20", "name": "DP-13 Double Pack Set Vol. 13"},
    {"date": "2026-12-04", "name": "IB-09 / IB-10 Illustration Boxes"},
    {"date": "2026-12-18", "name": "ST-37 / ST-38 Starter Decks"},
    {"date": "2027-01-29", "name": "EB-06 Extra Booster"},
    {"date": "2027-03-01", "name": "29th Anniversary Premium Card Collection (date approx.)"},
    {"date": "2027-03-05", "name": "OP-19 Booster Set"},
    {"date": "2027-04-01", "name": "Ace, Sabo & Luffy Premium Card Collection (April, approx.)"},
]
RECAP_DAYS_AHEAD = 14
RECAP_MOVE_PCT = 5      # price changes smaller than this (%) are left out of the recap

# Extra sealed shops, added on top of config.json (skip with "extra_shops": false in config.json).
# Shops with a One Piece section are read like the others; the rest are read through their search.
EXTRA_SHOPIFY_COLLECTIONS = [
    {"name": "Alpha Gaming", "url": "https://alphagaming.com.au/collections/one-piece-sealed-products/products.json?limit=250"},
]
EXTRA_SHOPIFY_SEARCH = [
    {"name": "Grailborne", "base": "https://grailborne.com.au"},
    {"name": "Collectible Madness", "base": "https://collectiblemadness.com.au"},
    # Friendly Collectibles was removed in Oct 2026: its search refused the bot (HTTP 401) on every check.
]
SEARCH_QUERIES = ["one piece booster box", "one piece booster display", "one piece card game"]

WATCH_EXCLUDE = ["japanese", "(jp)", " jp ", "chinese", "korean", "asia", "simplified", "traditional"]

MAX_PAGES = 4                   # Shopify collections: read up to 4 pages of 250 (1,000 products)
PREORDER_RE = re.compile(r"\bpre[\s_-]?(?:orders?|sale)\b", re.I)


# ================================================================ fast, polite HTTP (stdlib only)
# Python's urllib opens a brand-new connection (TCP + TLS handshake) for every request and doesn't
# ask for compression. This small client keeps one warm connection per shop, asks for gzip, shares
# identical requests made within a few seconds, retries only what's worth retrying (with jittered
# backoff, honouring Retry-After), and follows robots.txt.
HTTP_TIMEOUT = 15               # seconds to connect / for each read (v1: 25)
HTTP_TRIES = 2                  # attempts per GET (a retry only for timeouts, 5xx, 408, 425, 429)
PER_HOST = 2                    # most requests in flight to one shop at once (v1 reached 4-5 at Good Games)
HOST_GAP = 0.5                  # at least this many seconds between two requests to the same shop
COOL_MIN = 120                  # a shop that answers 429 is left alone for at least 2 minutes...
COOL_MAX = 30 * 60              # ...doubling each time it happens again, up to 30 minutes
IDLE_MAX = 20                   # seconds an idle kept-alive connection is trusted for reuse
RETRY_STATUSES = {408, 425, 500, 502, 503, 504}   # 429 is never retried straight away (see cooldown)
MAX_RETRY_AFTER = 8             # a shop asking us to wait longer than this is left until next check
MEMO_TTL = 15                   # identical GETs within 15 s share one request (drop mode is never faster than 30 s)
REFUSED_TTL = 60                # after a 401/403, the same shop+path isn't asked again for a minute
COND_CACHE_BYTES = 24 * 1024 * 1024   # bodies kept for If-None-Match / If-Modified-Since in --loop
ROBOTS_TTL = 24 * 3600          # RFC 9309: don't trust a cached robots.txt for more than 24 hours
ROBOT_TOKEN = "onepiecerestockbot"
# Shops whose bot protection refuses a browser-looking User-Agent from a script, but whose robots.txt
# welcomes bots: tell them honestly what we are. Add more in config.json "user_agent_by_shop".
BOT_UA = f"Mozilla/5.0 (compatible; {ROBOT_TOKEN}/2.0; personal stock checker, a few requests every 5 min)"
UA_BY_HOST = {"www.jtoys.com.au": BOT_UA}
JOB_WORKERS = 16                # shop-level jobs in parallel
LEAF_WORKERS = 24               # individual requests inside a job (product pages, search queries)


class HttpError(Exception):
    """A reply we can't use. Only 'try again later' codes are retried."""

    def __init__(self, status, reason="", retry_after=None):
        super().__init__(status, reason)
        self.status, self.reason, self.retry_after = status, reason, retry_after

    def __str__(self):
        return f"HTTP Error {self.status}: {self.reason}" if self.reason else f"HTTP Error {self.status}"


class SkipHost(Exception):
    """This shop failed several checks in a row and is in its quiet period (down_retry_minutes)."""


class RobotsDisallowed(Exception):
    """The shop's robots.txt asks bots not to read this address."""

    def __init__(self, url, unreachable=False):
        super().__init__(url)
        self.url, self.unreachable = url, unreachable


def _retry_after(headers, body=b""):
    """Seconds a server asked us to wait (Retry-After header, or Discord's JSON retry_after)."""
    v = (headers or {}).get("retry-after")
    if v:
        try:
            return max(0.0, float(v))
        except ValueError:
            try:
                from email.utils import parsedate_to_datetime
                when = parsedate_to_datetime(v)
                return max(0.0, (when - datetime.now(when.tzinfo)).total_seconds())
            except Exception:  # noqa: BLE001
                pass
    try:
        ra = json.loads(body or b"{}").get("retry_after")
        if ra is not None:
            return max(0.0, float(ra))
    except Exception:  # noqa: BLE001
        pass
    return None


def parse_robots(text, token=ROBOT_TOKEN):
    """RFC 9309 robots.txt -> [[allow 1/0, pattern], ...] for our token's group(s), else the '*' group(s)."""
    groups, agents, rules, in_rules = [], [], [], False
    for raw in text.splitlines()[:20000]:
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, val = (s.strip() for s in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if in_rules:
                groups.append((agents, rules))
                agents, rules, in_rules = [], [], False
            agents.append(val.lower())
        elif key in ("allow", "disallow") and agents:
            in_rules = True
            if val:
                rules.append([1 if key == "allow" else 0, val])
    if agents:
        groups.append((agents, rules))
    if any(token in a for a, _ in groups):
        return [r for a, rs in groups if token in a for r in rs]
    return [r for a, rs in groups if "*" in a for r in rs]


_robots_re_cache = {}


def _robots_match(pattern, path):
    rx = _robots_re_cache.get(pattern)
    if rx is None:
        end = pattern.endswith("$")
        body = re.escape(pattern[:-1] if end else pattern).replace(r"\*", ".*")
        rx = _robots_re_cache[pattern] = re.compile(body + ("$" if end else ""))
    return rx.match(path) is not None


def robots_allows(rules, path):
    """Longest matching rule wins; on a tie, allow wins (RFC 9309 section 2.2.2)."""
    best, allowed = -1, True
    for allow, pat in rules:
        if _robots_match(pat, path) and (len(pat) > best or (len(pat) == best and allow)):
            best, allowed = len(pat), bool(allow)
    return allowed


def tls_context(cafile=None):
    """The same TLS handshake urllib (and so v1) sends: ALPN "http/1.1" plus post-handshake auth.
    A bare ssl.create_default_context() leaves both out, and the shops' bot protection answered
    that handshake with 403 Forbidden for every request on 14 Oct 2026."""
    ctx = ssl.create_default_context(cafile=cafile)
    ctx.set_alpn_protocols(["http/1.1"])
    if ctx.post_handshake_auth is not None:
        ctx.post_handshake_auth = True
    return ctx


class _Http:
    def __init__(self):
        self.lock = threading.Lock()
        self.idle = defaultdict(list)       # (scheme, host, port) -> [(conn, idle since)]
        self.sems = {}
        self.memo = {}                      # url -> (expires, Future)
        self.cond = OrderedDict()           # url -> (validators, body)
        self.cond_bytes = 0
        self.refused = {}                   # (host, first path part) -> (until, HttpError)
        self.cool = {}                    # host -> [until, strikes]: shops that said 429, left alone
        self.next_at = {}                 # host -> earliest time for its next request (HOST_GAP)
        self.skip_hosts = set()
        self.robots = {}                    # host -> {"t": fetched at, "rules": [[allow, pattern], ...]}
        self.robots_on = True
        self.user_agent = UA
        self.gzip_urls = set()              # addresses (no ?query) also asked for gzip in classic mode: the big singles lists
        self.classic = True                 # send requests the v1 way (see _exchange_classic)
        self.ua_by_host = dict(UA_BY_HOST)
        self.timeout = HTTP_TIMEOUT
        self._ctx = None
        self.reset_metrics()

    # ------------------------------------------------------------ bookkeeping
    def reset_metrics(self):
        with self.lock:
            self.m = Counter()
            self.lat = defaultdict(lambda: deque(maxlen=500))   # bounded: the commands bot never resets
            self.refused.clear()

    @property
    def ctx(self):
        if self._ctx is None:
            self._ctx = tls_context()
        return self._ctx

    def _sem(self, host):
        with self.lock:
            s = self.sems.get(host)
            if s is None:
                s = self.sems[host] = threading.BoundedSemaphore(PER_HOST)
            return s

    # ------------------------------------------------------------ connections
    def _new_conn(self, scheme, host, port):
        proxy = None
        try:
            proxy = urllib.request.getproxies().get(scheme)
            if proxy and urllib.request.proxy_bypass(host):
                proxy = None
        except Exception:  # noqa: BLE001
            proxy = None
        if proxy and scheme == "https":     # same proxy settings urllib would have used
            p = urllib.parse.urlsplit(proxy if "://" in proxy else "http://" + proxy)
            hdrs = {}
            if p.username:
                cred = f"{urllib.parse.unquote(p.username)}:{urllib.parse.unquote(p.password or '')}"
                hdrs["Proxy-Authorization"] = "Basic " + base64.b64encode(cred.encode()).decode()
            conn = http.client.HTTPSConnection(p.hostname, p.port or 8080, timeout=self.timeout, context=self.ctx)
            conn.set_tunnel(host, port, headers=hdrs)
            return conn
        if scheme == "https":
            return http.client.HTTPSConnection(host, port, timeout=self.timeout, context=self.ctx)
        return http.client.HTTPConnection(host, port, timeout=self.timeout)

    def _checkout(self, key):
        now = time.time()
        stale = []
        with self.lock:
            pool = self.idle.get(key)
            while pool:
                conn, since = pool.pop()
                if now - since <= IDLE_MAX:
                    self.m["reused"] += 1
                    for c in stale:
                        c.close()
                    return conn, True
                stale.append(conn)
            self.m["connections"] += 1
        for c in stale:
            c.close()
        return self._new_conn(*key), False

    def _checkin(self, key, conn):
        with self.lock:
            pool = self.idle[key]
            if len(pool) <= PER_HOST:
                pool.append((conn, time.time()))
                return
        conn.close()

    def close_idle(self):
        with self.lock:
            pools, self.idle = self.idle, defaultdict(list)
        for pool in pools.values():
            for conn, _ in pool:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

    def _drop_idle(self, key):
        with self.lock:
            pool = self.idle.pop(key, [])
        for conn, _ in pool:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def _exchange(self, method, url, body=None, headers=None):
        """One request on a pooled connection -> (status, headers, body). If a kept-alive connection
        turns out to have been closed by the shop while idle, the request is resent once on a new one."""
        u = urllib.parse.urlsplit(url)
        scheme = (u.scheme or "https").lower()
        host = (u.hostname or "").lower()
        port = u.port or (443 if scheme == "https" else 80)
        if self.classic and method == "GET" and body is None:
            return self._exchange_classic(url, host, headers)
        target = (u.path or "/") + (("?" + u.query) if u.query else "")
        h = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate",
             "Accept": "application/json, text/plain, */*"}
        h.update(headers or {})
        key = (scheme, host, port)
        with self._sem(host):
            if method == "GET":
                self._pace(host)
            for fresh in (False, True):
                conn, reused = self._checkout(key)
                t0 = time.perf_counter()
                try:
                    conn.request(method, target, body=body, headers=h)
                    resp = conn.getresponse()
                    raw = resp.read()
                except (http.client.RemoteDisconnected, http.client.CannotSendRequest, http.client.BadStatusLine,
                        ConnectionResetError, BrokenPipeError, ssl.SSLEOFError):
                    conn.close()
                    if reused and not fresh:
                        self._drop_idle(key)     # the idle connection had gone stale; so have its siblings
                        continue
                    raise
                except BaseException:
                    conn.close()
                    raise
                ms = (time.perf_counter() - t0) * 1000
                hdrs = {k.lower(): v for k, v in resp.getheaders()}
                if resp.will_close:
                    conn.close()
                else:
                    self._checkin(key, conn)
                enc = hdrs.get("content-encoding", "").lower()
                data = raw
                if raw and enc == "gzip":
                    data = gzip.decompress(raw)
                elif raw and enc == "deflate":
                    try:
                        data = zlib.decompress(raw)
                    except zlib.error:
                        data = zlib.decompress(raw, -zlib.MAX_WBITS)
                with self.lock:
                    self.m["requests"] += 1
                    self.m["bytes_wire"] += len(raw)
                    self.m["bytes"] += len(data)
                    self.lat[host].append(ms)
                return resp.status, hdrs, data
        raise http.client.HTTPException("unreachable")  # pragma: no cover

    def _exchange_classic(self, url, host, headers=None):
        """One GET sent exactly the way v1 sent it (urllib: same headers, one connection per request).
        The shops' bot protection refused v2's own request style with 403 on 14-15 Oct 2026 while the
        same PC loaded the same pages fine in a browser and v1 had been fine, so this is the default.
        Set "classic_requests": false in config.json to go back to v2's pooled connections."""
        ua = self.ua_by_host.get(host) or self.ua_by_host.get(host.removeprefix("www.")) or self.user_agent
        h = {"User-Agent": ua, "Accept": "application/json"}
        h.update(headers or {})
        with self._sem(host):
            self._pace(host)
            t0 = time.perf_counter()
            req = urllib.request.Request(url, headers=h)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
                    status, hdrs, raw = r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
            except urllib.error.HTTPError as e:
                status, hdrs = e.code, {k.lower(): v for k, v in (e.headers or {}).items()}
                try:
                    raw = e.read()
                except Exception:  # noqa: BLE001
                    raw = b""
            except urllib.error.URLError as e:
                reason = e.reason
                raise reason if isinstance(reason, OSError) else OSError(str(reason))
            ms = (time.perf_counter() - t0) * 1000
            data = raw
            enc = hdrs.get("content-encoding", "").lower()
            if raw and enc == "gzip":         # only when asked for (see gzip_urls); urllib doesn't unpack it itself
                data = gzip.decompress(raw)
            elif raw and enc == "deflate":
                try:
                    data = zlib.decompress(raw)
                except zlib.error:
                    data = zlib.decompress(raw, -zlib.MAX_WBITS)
            with self.lock:
                self.m["requests"] += 1
                self.m["connections"] += 1
                self.m["bytes_wire"] += len(raw)
                self.m["bytes"] += len(data)
                self.lat[host].append(ms)
            return status, hdrs, data

    # ------------------------------------------------------------ GET with the works
    def fetch(self, url, tries=HTTP_TRIES, conditional=True, robots=True, memo=True):
        """GET -> body bytes. Raises HttpError, SkipHost, RobotsDisallowed or a network error."""
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        if host in self.skip_hosts:
            raise SkipHost(host)
        if robots and self.robots_on and not self.allowed(url):
            raise RobotsDisallowed(url, self.robots.get(host, {}).get("unreachable", False))
        if not memo:
            return self._fetch(url, tries, conditional)
        now = time.time()
        with self.lock:
            hit = self.memo.get(url)
            if hit and hit[0] > now:
                fut, owner = hit[1], False
                self.m["shared"] += 1
            else:
                fut, owner = Future(), True
                self.memo[url] = (now + MEMO_TTL, fut)
                if len(self.memo) > 4000:
                    for k in [k for k, v in self.memo.items() if v[0] <= now]:
                        self.memo.pop(k, None)
        if not owner:
            return fut.result()
        try:
            data = self._fetch(url, tries, conditional)
        except BaseException as e:
            fut.set_exception(e)
            raise
        fut.set_result(data)
        return data

    def _fetch(self, url, tries, conditional):
        u = urllib.parse.urlsplit(url)
        host = (u.hostname or "").lower()
        rkey = (host, (u.path.split("/") + [""])[1])
        with self.lock:
            cool = self.cool.get(host)
        if cool and cool[0] > time.time():
            with self.lock:
                self.m["cooling_skips"] += 1
            raise HttpError(429, f"Too Many Requests - shop asked us to slow down, trying again in "
                                 f"{int(cool[0] - time.time()) // 60 + 1} min", cool[0] - time.time())
        with self.lock:
            hit = self.refused.get(rkey)
        if hit and hit[0] > time.time():
            raise hit[1]               # the shop said no to this a moment ago - don't ask again
        last = None
        zipped = url.split("?", 1)[0] in self.gzip_urls
        if zipped:
            conditional = False              # big lists that change all the time: not worth keeping a copy of
        for attempt in range(max(1, tries)):
            hdrs, cached = ({"Accept-Encoding": "gzip"} if zipped else {}), None
            if conditional:
                with self.lock:
                    cached = self.cond.get(url)
                if cached:
                    if cached[0].get("etag"):
                        hdrs["If-None-Match"] = cached[0]["etag"]
                    if cached[0].get("last-modified"):
                        hdrs["If-Modified-Since"] = cached[0]["last-modified"]
            try:
                status, h, data = self._get_following(url, hdrs)
            except (OSError, http.client.HTTPException, ssl.SSLError) as e:
                last = e
                with self.lock:
                    self.m["net_errors"] += 1
                if attempt + 1 < tries:
                    self._backoff(attempt, None)
                    continue
                raise
            if 200 <= status < 300:
                self._calm(host)
                if conditional:
                    self._remember(url, h, data)
                return data
            if status == 304 and cached:
                with self.lock:
                    self.m["not_modified"] += 1
                    if url in self.cond:
                        self.cond.move_to_end(url)
                return cached[1]
            ra = _retry_after(h, data if status == 429 else b"")
            if status == 429:
                wait = self._cool_down(host, ra)
                raise HttpError(429, f"Too Many Requests - leaving this shop alone for {int(wait) // 60 + (wait % 60 > 0)} min", wait)
            err = HttpError(status, http.client.responses.get(status, ""), ra)
            if status in RETRY_STATUSES and attempt + 1 < tries and (ra is None or ra <= MAX_RETRY_AFTER):
                last = err
                self._backoff(attempt, ra)
                continue
            if status in (401, 403, 451) or (status == 429 and (ra or 0) > MAX_RETRY_AFTER):
                with self.lock:
                    self.refused[rkey] = (time.time() + REFUSED_TTL, err)
            raise err
        raise last  # pragma: no cover

    def _cool_down(self, host, retry_after):
        """The shop said 429: stop asking it anything (every page) until it's had a rest.
        Honours Retry-After; otherwise 2, 4, 8 ... up to 30 minutes for repeat 429s."""
        with self.lock:
            until, strikes = self.cool.get(host, [0, 0])
            wait = min(COOL_MAX, max(float(retry_after or 0), COOL_MIN * (2 ** strikes)))
            self.cool[host] = [time.time() + wait, strikes + 1]
            self.m["rate_limited"] += 1
        return wait

    def _calm(self, host):
        """A good answer: the shop is happy again, so the next 429 starts back at 2 minutes."""
        with self.lock:
            c = self.cool.get(host)
            if c and c[0] <= time.time():
                del self.cool[host]

    def cooling(self):
        """{host: seconds left} for shops currently being left alone after a 429."""
        now = time.time()
        with self.lock:
            return {h: c[0] - now for h, c in self.cool.items() if c[0] > now}

    def _pace(self, host):
        """Space requests to one shop at least HOST_GAP seconds apart (call while holding its slot)."""
        with self.lock:
            now = time.time()
            at = max(now, self.next_at.get(host, 0))
            self.next_at[host] = at + HOST_GAP
        if at > now:
            time.sleep(at - now)

    def _get_following(self, url, hdrs):
        for _ in range(6):                       # urllib followed redirects; so do we (up to 5)
            status, h, data = self._exchange("GET", url, headers=hdrs)
            loc = h.get("location")
            if status in (301, 302, 303, 307, 308) and loc:
                url = urllib.parse.urljoin(url, loc)
                hdrs = {k: v for k, v in hdrs.items() if not k.startswith("If-")}
                continue
            return status, h, data
        return status, h, data

    def _backoff(self, attempt, retry_after):
        with self.lock:
            self.m["retries"] += 1
        # exponential backoff with full jitter (AWS Builders' Library), or exactly what the server asked
        time.sleep(retry_after if retry_after is not None else random.uniform(0.25, 0.6 * (2 ** attempt)))

    def _remember(self, url, h, data):
        v = {k: h[k] for k in ("etag", "last-modified") if h.get(k)}
        if not v:
            return
        with self.lock:
            old = self.cond.pop(url, None)
            if old:
                self.cond_bytes -= len(old[1])
            self.cond[url] = (v, data)
            self.cond_bytes += len(data)
            while self.cond_bytes > COND_CACHE_BYTES and self.cond:
                _, (_, d) = self.cond.popitem(last=False)
                self.cond_bytes -= len(d)

    def post(self, url, data, headers=None):
        """One POST, no automatic retry (callers decide what's safe to resend)."""
        return self._exchange("POST", url, body=data, headers=headers)

    # ------------------------------------------------------------ robots.txt
    def allowed(self, url):
        u = urllib.parse.urlsplit(url)
        if u.path == "/robots.txt":
            return True
        host = (u.hostname or "").lower()
        e = self._robots_entry((u.scheme or "https").lower(), host, u.port)
        return robots_allows(e.get("rules") or [], (u.path or "/") + (("?" + u.query) if u.query else ""))

    def _robots_entry(self, scheme, host, port):
        now = time.time()
        with self.lock:
            old = self.robots.get(host)
        if old and now - old.get("t", 0) < ROBOTS_TTL:
            return old
        url = f"{scheme}://{host}{':' + str(port) if port else ''}/robots.txt"
        try:
            text = self.fetch(url, tries=1, conditional=False, robots=False).decode("utf-8", "replace")
            e = {"t": now, "rules": parse_robots(text)}
        except HttpError as err:
            if 400 <= err.status < 500:
                e = {"t": now, "rules": []}      # no robots.txt: everything is allowed (RFC 9309 2.3.1.3)
            else:
                e = self._robots_unreachable(old, now)
        except SkipHost:
            raise
        except Exception:  # noqa: BLE001
            e = self._robots_unreachable(old, now)
        with self.lock:
            self.robots[host] = e
        return e

    @staticmethod
    def _robots_unreachable(old, now):
        if old and not old.get("unreachable"):   # keep using the last good copy for now
            return dict(old, t=now - ROBOTS_TTL + 3600)
        # never read it: RFC 9309 says assume "disallow all"; look again in 10 minutes
        return {"t": now - ROBOTS_TTL + 600, "rules": [[0, "/"]], "unreachable": True}


HTTP = _Http()
_pool_lock = threading.Lock()
_POOLS = {}
_run_t0 = [time.perf_counter()]
_seen_errors = set()
DRY_RUN = [False]


def _pool(name, n):
    with _pool_lock:
        p = _POOLS.get(name)
        if p is None:
            p = _POOLS[name] = ThreadPoolExecutor(max_workers=n, thread_name_prefix=f"restock-{name}")
        return p


def pmap(fn, items, leaf=True):
    """fn over items in parallel, results in order. Leaf work (single requests) uses its own pool so a
    shop-level job can fan out without ever waiting on its own pool."""
    items = list(items)
    if len(items) <= 1:
        return [fn(x) for x in items]
    return list(_pool("leaf" if leaf else "jobs", LEAF_WORKERS if leaf else JOB_WORKERS).map(fn, items))


def begin_check(cfg, status=None, drop=None, skip_down=True):
    """Reset the per-check counters and apply settings (user agent, robots, shops in their quiet period)."""
    with _host_lock:
        _host_results.clear()
    _seen_errors.clear()
    HTTP.reset_metrics()
    HTTP.user_agent = (cfg or {}).get("user_agent") or UA
    HTTP.classic = bool((cfg or {}).get("classic_requests", True))
    HTTP.ua_by_host = {**UA_BY_HOST, **{str(k).lower(): v for k, v in
                                        ((cfg or {}).get("user_agent_by_shop") or {}).items() if v}}
    HTTP.robots_on = bool((cfg or {}).get("respect_robots", True))
    status = load_status() if status is None else status
    for host, e in (status.get("robots") or {}).items():
        if isinstance(e, dict) and e.get("t", 0) > HTTP.robots.get(host, {}).get("t", 0):
            HTTP.robots[host] = e
    now = time.time()
    retry = status.get("shop_retry") or {}
    HTTP.skip_hosts = set() if (drop or not skip_down) else {h for h, t in retry.items() if float(t) > now}
    hints = status.get("page_hints")
    if isinstance(hints, dict):
        PAGE_HINTS.update(hints)
    _run_t0[0] = time.perf_counter()
    return status


def run_metrics():
    m = HTTP.m
    hosts = {}
    with HTTP.lock:
        for h, v in HTTP.lat.items():
            v = sorted(v)
            hosts[h] = {"n": len(v), "p50_ms": round(v[len(v) // 2]), "max_ms": round(v[-1])}
    return {"secs": round(time.perf_counter() - _run_t0[0], 2), "requests": m["requests"], "shared": m["shared"],
            "new_connections": m["connections"], "reused": m["reused"], "kb_wire": round(m["bytes_wire"] / 1024),
            "kb": round(m["bytes"] / 1024), "not_modified": m["not_modified"], "retries": m["retries"],
            "skipped_hosts": sorted(HTTP.skip_hosts), "hosts": hosts}


# ---------------------------------------------------------------- helpers
def read_json(path, default=None):
    """A JSON file, or `default` if it's missing or unreadable (a Notepad BOM is fine)."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (ValueError, OSError) as e:
        print(f"   ! {os.path.basename(path)} couldn't be read ({e}); starting it fresh")
        return default


def atomic_write_json(path, obj, indent=1, sort_keys=False, ensure_ascii=True):
    """Write JSON so a crash or a reader never sees half a file: temp file, flush, then rename over."""
    atomic_write_text(path, json.dumps(obj, indent=indent, sort_keys=sort_keys, ensure_ascii=ensure_ascii))


def atomic_write_text(path, data):
    """atomic_write_json's file writing, for text that's already laid out."""
    if DRY_RUN[0]:
        return
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    for i in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:          # Windows: another program has it open for a moment
            time.sleep(0.05 * (i + 1))
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(data)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def append_text(path, text, max_bytes=LOG_MAX_BYTES):
    """Append to a log file, rolling it over to <name>.1 once it's past max_bytes."""
    if DRY_RUN[0]:
        return
    try:
        if os.path.getsize(path) > max_bytes:
            os.replace(path, path + ".1")
    except OSError:
        pass
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(text)


_REDACT = [(re.compile(r"(discord(?:app)?\.com/api/webhooks/\d+/)[\w-]+"), r"\1***"),
           (re.compile(r"\b[MN][\w-]{23,25}\.[\w-]{6}\.[\w-]{27,40}\b"), "***bot-token***")]


def redact(text):
    """Hide webhook tokens and bot tokens before anything is printed or posted."""
    text = str(text)
    for rx, rep in _REDACT:
        text = rx.sub(rep, text)
    return text


def _num(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(str(x).strip().replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


KNOWN_SETTINGS = {"_help", "alerts", "sealed", "singles", "sealed_watch", "releases", "drop_windows", "new_listings",
                  "extra_shops", "value_picks", "value_picks_per_check", "repo_raw_url", "ledger_url", "singles_every_minutes",
                  "down_retry_minutes", "respect_robots", "user_agent", "auto_drop_windows", "history",
                  "classic_requests", "user_agent_by_shop", "pokemon", "price_drops"}
DISCORD_HOOK_RE = re.compile(r"https://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/\d+/")
CONFIG_WARNINGS = []


def check_config(cfg):
    """Fix what can be fixed (numbers typed as text) and switch off what can't, with a warning each,
    so one bad value never stops the whole bot. Returns the warnings."""
    w = []
    for k in list(cfg):
        if k not in KNOWN_SETTINGS and not k.startswith("_"):
            import difflib                 # only needed when there's a typo to explain
            close = difflib.get_close_matches(k, KNOWN_SETTINGS, 1)
            w.append(f'unknown setting "{k}"' + (f' (did you mean "{close[0]}"?)' if close else ""))
    sealed = cfg.get("sealed")
    if not isinstance(sealed, dict):
        w.append('"sealed" section is missing, so booster boxes aren\'t checked')
        sealed = cfg["sealed"] = {"max_price": 0}
    mp = _num(sealed.get("max_price"))
    if mp is None:
        w.append(f'sealed "max_price" should be a number (it\'s {sealed.get("max_price")!r}); box price alerts are off')
        mp = 0.0
    sealed["max_price"] = mp
    for key, need in (("shopify_collections", "url"), ("shopify_products", "url"), ("woocommerce", "url"),
                      ("shopify_search", "base")):
        keep = []
        for shop in sealed.get(key) or []:
            if isinstance(shop, dict) and shop.get("name") and str(shop.get(need, "")).startswith("https://"):
                keep.append(shop)
            else:
                w.append(f'sealed "{key}" entry {shop!r} needs a "name" and an https:// "{need}"; skipped')
        if key in sealed:
            sealed[key] = keep
    singles = cfg.get("singles")
    if not isinstance(singles, dict):
        singles = cfg["singles"] = {"shops": {}, "cards": []}
    shops = singles.get("shops") or {}
    singles["shops"] = {n: u.rstrip("/") for n, u in shops.items() if isinstance(u, str) and u.startswith("https://")}
    for n in set(shops) - set(singles["shops"]):
        w.append(f'singles shop "{n}" needs an https:// address; skipped')
    cards = singles.get("cards") or []
    for c in cards:
        if not isinstance(c, dict):
            continue
        label = f"{c.get('name', '?')} {c.get('num', '')}".strip()
        mx, qty = _num(c.get("max")), _num(c.get("qty", 1))
        if not c.get("num") or mx is None:
            if c.get("enabled", True):
                w.append(f'card "{label}" needs a "num" and a number for "max"; switched off')
            c["enabled"] = False
            c["max"] = mx or 0.0
        else:
            c["max"] = mx
        c["qty"] = max(1, int(qty or 1))
        c.setdefault("name", c.get("num", ""))
    singles["cards"] = [c for c in cards if isinstance(c, dict)]
    watch = cfg.get("sealed_watch")
    if watch is not None:
        good = []
        for x in watch if isinstance(watch, list) else []:
            if isinstance(x, dict) and x.get("match") and _num(x.get("max")) is not None:
                x["max"] = _num(x["max"])
                x["match"] = [x["match"]] if isinstance(x["match"], str) else list(x["match"])
                x.setdefault("name", x["match"][0])
                good.append(x)
            else:
                w.append(f"sealed_watch entry {x!r} needs \"match\" and a number for \"max\"; skipped")
        cfg["sealed_watch"] = good
    alerts = cfg.get("alerts") or {}
    for k, v in alerts.items():
        if k.startswith("discord_webhook") and v and not DISCORD_HOOK_RE.match(str(v)):
            w.append(f'alerts "{k}" doesn\'t look like a Discord webhook address')
    ph = alerts.get("pokemon_webhooks")
    if isinstance(ph, str) and ph.strip():
        try:
            ph = alerts["pokemon_webhooks"] = json.loads(ph)       # the cloud copy gets it as one line of JSON
        except ValueError:
            w.append('alerts "pokemon_webhooks" (POKEMON_WEBHOOKS) isn\'t valid JSON, so Pokémon alerts are off')
            ph = alerts["pokemon_webhooks"] = {}
    if ph is not None and not isinstance(ph, dict):
        w.append('alerts "pokemon_webhooks" should be {"<channel>": "<webhook link>", ...}; Pokémon alerts are off')
        alerts["pokemon_webhooks"] = {}
    elif isinstance(ph, dict):
        for k, v in list(ph.items()):
            if not DISCORD_HOOK_RE.match(str(v or "")):
                w.append(f'alerts "pokemon_webhooks" → "{k}" doesn\'t look like a Discord webhook address; skipped')
                ph.pop(k)
    qh = alerts.get("quiet_hours")
    if qh and not re.fullmatch(r"\s*\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\s*", str(qh)):
        w.append(f'alerts "quiet_hours" should look like "23:00-07:00" (it\'s {qh!r}); ignored')
        alerts.pop("quiet_hours", None)
    for d in cfg.get("drop_windows") or []:
        if isinstance(d, dict) and str(d.get("game", ONE_PIECE)).lower() not in (ONE_PIECE, POKE, "one piece", "pokémon"):
            w.append(f'drop window "{d.get("name", "?")}": "game" should be "onepiece" or "pokemon"')
    w += check_drops_config(cfg)
    if pokemon_watch:
        w += pokemon_watch.warnings(cfg)
    return w


def load_config():
    """Read config.json (+ secrets.json), then let environment variables override the alert settings."""
    with open(CONFIG_PATH, encoding="utf-8-sig") as f:
        cfg = json.load(f)
    alerts = cfg.setdefault("alerts", {})
    secrets = read_json(SECRETS_PATH, {}) or {}
    for k, v in (secrets.get("alerts", secrets) if isinstance(secrets, dict) else {}).items():
        if v and not str(k).startswith("_"):
            alerts[k] = v
    for env, k in ENV_ALERTS.items():
        val = os.environ.get(env, "").strip()
        if val:
            alerts[k] = val
    CONFIG_WARNINGS[:] = check_config(cfg)
    return cfg


def fetch_json(url, tries=HTTP_TRIES):
    """GET a URL and parse JSON. Returns None on failure (and says why, once per shop per check)."""
    try:
        data = json.loads(HTTP.fetch(url, tries=tries).decode("utf-8", "replace"))
    except SkipHost:
        return None
    except RobotsDisallowed as e:
        if e.unreachable:
            _fail(url, "its robots.txt couldn't be read, so the bot is holding off")
        else:
            _say_once(("robots", short(url)), f"   ! skipped {short(url)}: the shop's robots.txt asks bots not to read it")
        return None
    except (HttpError, OSError, http.client.HTTPException, ssl.SSLError, ValueError, EOFError, zlib.error) as e:
        _fail(url, e)
        return None
    _note_host(url, True)
    return data


def _say_once(key, text):
    with _host_lock:
        if key in _seen_errors:
            return
        if len(_seen_errors) > 500:      # long-running commands bot: don't grow forever
            _seen_errors.clear()
        _seen_errors.add(key)
    print(text)


def _fail(url, err):
    host = urllib.parse.urlparse(url).netloc
    if isinstance(err, HttpError) and err.status == 429:
        # Rate-limited: the shop is up, it just wants fewer requests. Say so once per check and don't
        # count it as the shop being down (no "hasn't loaded" posts, no "can't reach the shops" alarm).
        _say_once((host, 429), f"   ~ {host} asked the bot to slow down ({redact(err)})")
        return
    _say_once((host, str(err)), f"   ! couldn't read {short(url)} ({redact(err)})")
    _note_host(url, False)


def _note_host(url, ok):
    host = urllib.parse.urlparse(url).netloc
    with _host_lock:
        _host_results.setdefault(host, [0, 0])[0 if ok else 1] += 1


def short(url):
    p = urllib.parse.urlparse(url)
    return p.netloc + p.path


def origin(url):
    p = urllib.parse.urlparse(url)
    return f"{p.scheme or 'https'}://{p.netloc}"


def money(x):
    return f"${x:,.2f}"


def price_label(f):
    """'$2.00' or, for a single in a known condition, '$2.00 (NM)'."""
    return money(f["price"]) + (f" ({f['cond']})" if f.get("cond") else "")


def norm(s):
    return " " + re.sub(r"\s+", " ", (s or "").lower()) + " "


def is_excluded(title, words):
    t = norm(title)
    return any(w.lower() in t for w in words)


def is_box_title(title):
    t = (title or "").lower()
    return ("booster box" in t or "booster display" in t) and not is_excluded(title, BOX_EXCLUDE)


def is_preorder(title, tags=""):
    """Pre-order / pre-sale wording in the title or tags (v1 matched any 'pre', e.g. 'PREmium')."""
    blob = (json.dumps(tags) if not isinstance(tags, str) else tags) + " " + (title or "")
    return bool(PREORDER_RE.search(blob))


def watch_item(title, watch):
    """The sealed_watch entry this product title matches, or None (box titles are left to the box check)."""
    if not title or is_box_title(title) or is_excluded(title, WATCH_EXCLUDE):
        return None
    t = title.lower()
    squashed = re.sub(r"[\s\-]", "", t)
    for w in watch:
        for m in w.get("match", []):
            m = m.lower()
            if m in t or re.sub(r"[\s\-]", "", m) in squashed:
                return w
    return None


def card_num_variants(num):
    """OP13-120 -> ['op13-120', 'op13120'] (Elemental sometimes drops the dash in handles)."""
    n = num.lower()
    return [n, n.replace("-", "")]


def shopify_cart_link(base, variant_id, qty=1):
    """Shopify cart permalink: opens checkout with this item already in the cart."""
    if not variant_id:
        return ""
    return f"{origin(base)}/cart/{variant_id}:{max(1, int(qty))}"


def woo_cart_link(url, product_id, qty=1):
    """WooCommerce: add to cart and jump to checkout."""
    if not product_id:
        return ""
    return f"{origin(url)}/checkout/?add-to-cart={product_id}&quantity={max(1, int(qty))}"


def cheapest_available(variants, cents):
    """(price in dollars, variant id) of the cheapest in-stock variant, or (None, None)."""
    avail = [v for v in variants or [] if v.get("available")]
    if not avail:
        return None, None
    v = min(avail, key=lambda v: float(v.get("price") or 0))
    price = float(v.get("price") or 0)
    return (price / 100 if cents else price), v.get("id")


# ---------------------------------------------------------------- sealed
PAGE_HINTS = {}                 # collection URL -> pages it filled last check (kept in status.json "page_hints")


def shopify_collection(url, max_pages=MAX_PAGES):
    """Every product in a Shopify collection: page 1, then page=2, 3... while pages come back full
    (v1 only ever saw the first 250). The pages a collection filled last time are asked for together,
    which saves a round trip per extra page. -> (products, {handle: page}) or (None, {}) if page 1 failed."""
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    try:
        limit = max(1, int(q.get("limit", 30)))
    except ValueError:
        limit = 30

    def page_url(n):
        return url if n == 1 else url + ("&" if "?" in url else "?") + f"page={n}"

    try:
        hint = 1 if "page" in q else max(1, min(max_pages, int(PAGE_HINTS.get(url, 1))))
    except (TypeError, ValueError):
        hint = 1
    first_pages = pmap(lambda n: fetch_json(page_url(n)), range(1, hint + 1))
    if not isinstance(first_pages[0], dict):
        return None, {}
    products, pages, page, batch = [], {}, 0, []
    for data in first_pages:
        page += 1
        batch = (data or {}).get("products") or [] if isinstance(data, dict) else []
        new = [p for p in batch if p.get("handle") not in pages]
        for p in new:
            pages[p.get("handle")] = page
        products.extend(new)
        if len(batch) < limit or (page > 1 and not new):
            break
    while len(batch) >= limit and page < max_pages and "page" not in q:
        page += 1
        nxt = fetch_json(page_url(page))
        batch = (nxt or {}).get("products") or [] if isinstance(nxt, dict) else []
        new = [p for p in batch if p.get("handle") not in pages]
        if not new:
            break
        for p in new:
            pages[p.get("handle")] = page
        products.extend(new)
    PAGE_HINTS[url] = max(pages.values(), default=1)
    return products, pages


def shopify_boxes(shop_name, url, max_price, watch=()):
    """Returns (finds, listings). listings is None if the shop couldn't be read.
    Covers booster boxes and the other sealed products in the watch list."""
    products, pages = shopify_collection(url)
    if products is None:
        return [], None
    base = origin(url)
    finds, listings = [], []
    for p in products:
        title = p.get("title", "")
        w = None if is_box_title(title) else watch_item(title, watch)
        if not is_box_title(title) and not w:
            continue
        kind, prefix, group = ("Sealed", "sealed", "watch") if w else ("Booster box", "box", "box")
        limit = w["max"] if w else max_price
        handle = p.get("handle")
        page = f"{base}/products/{handle}"
        is_pre = is_preorder(title, p.get("tags", ""))
        variants = p.get("variants", [])
        price, vid = cheapest_available(variants, cents=False)
        all_prices = [float(v["price"]) for v in variants if v.get("price")]
        note = ", ".join(x for x in ((w["name"] if w else ""), ("pre-order" if is_pre else "")) if x)
        listings.append({
            "id": f"list|{shop_name}|{handle}", "box_id": f"{prefix}|{shop_name}|{handle}", "group": group,
            "kind": "New listing", "name": title, "shop": shop_name,
            "price": price if price is not None else (min(all_prices) if all_prices else 0.0),
            "available": price is not None, "url": page,
            "cart": shopify_cart_link(base, vid) if vid else "",
            "note": note, "max": limit, "page": pages.get(handle, 1),
        })
        if price is None or price > limit:
            continue
        finds.append({
            "id": f"{prefix}|{shop_name}|{handle}", "kind": kind, "name": title, "shop": shop_name,
            "price": price, "url": page, "cart": shopify_cart_link(base, vid), "note": note,
        })
    return finds, listings


def _suggest_url(base, q):
    return (f"{base}/search/suggest.json?q={urllib.parse.quote(q)}"
            f"&resources[type]=product&resources[limit]=10")


def shopify_search_boxes(shop_name, base, max_price, watch=()):
    """For shops without a One Piece section: read their search results instead.
    Returns (finds, listings) like shopify_boxes; listings is None if every search failed."""
    base = base.rstrip("/")
    results = pmap(lambda q: fetch_json(_suggest_url(base, q)), SEARCH_QUERIES)   # all three at once
    products, any_ok = {}, False
    for data in results:
        if data is None:
            continue
        any_ok = True
        for p in data.get("resources", {}).get("results", {}).get("products", []):
            products.setdefault(p.get("handle"), p)
    if not any_ok:
        return [], None
    rows = []
    for handle, p in products.items():
        title = p.get("title", "")
        if "one piece" not in title.lower():
            continue
        w = None if is_box_title(title) else watch_item(title, watch)
        if not is_box_title(title) and not w:
            continue
        limit = w["max"] if w else max_price
        price = float(p.get("price") or p.get("price_min") or 0)
        rows.append((handle, p, w, limit, price, bool(p.get("available"))))
    # only look up cart IDs for what's worth alerting, all at once
    want = [r[0] for r in rows if r[5] and 0 < r[4] <= r[3]]
    carts = dict(zip(want, pmap(lambda h: product_js(base, h) or {}, want)))
    finds, listings = [], []
    for handle, p, w, limit, price, available in rows:
        title = p.get("title", "")
        kind, prefix, group = ("Sealed", "sealed", "watch") if w else ("Booster box", "box", "box")
        page = f"{base}/products/{handle}"
        note = ", ".join(x for x in ((w["name"] if w else ""), ("pre-order" if is_preorder(title, p.get("tags", "")) else "")) if x)
        cart = ""
        if handle in carts:
            _, vid = cheapest_available(carts[handle].get("variants"), cents=True)
            cart = shopify_cart_link(base, vid)
        listings.append({"id": f"list|{shop_name}|{handle}", "box_id": f"{prefix}|{shop_name}|{handle}",
                         "group": group, "kind": "New listing", "name": title, "shop": shop_name,
                         "price": price, "available": available, "url": page, "cart": cart,
                         "note": note, "max": limit, "page": 1})
        if available and 0 < price <= limit:
            finds.append({"id": f"{prefix}|{shop_name}|{handle}", "kind": kind, "name": title,
                          "shop": shop_name, "price": price, "url": page, "cart": cart, "note": note})
    return finds, listings


def sealed_shops(cfg):
    """(collections, single products, woocommerce, search) shop lists, with the extra shops added."""
    s = cfg["sealed"]
    cols = list(s.get("shopify_collections", []))
    search = list(s.get("shopify_search", []))
    if cfg.get("extra_shops", True):
        have = {x["name"] for x in cols + search}
        cols += [x for x in EXTRA_SHOPIFY_COLLECTIONS if x["name"] not in have]
        search += [x for x in EXTRA_SHOPIFY_SEARCH if x["name"] not in have]
    return cols, s.get("shopify_products", []), s.get("woocommerce", []), search


def shopify_product_box(shop_name, url, max_price, watch=()):
    """A single product .js URL (Shopify prices are in cents here). Not used for new-listing alerts."""
    p = fetch_json(url)
    if not p:
        return [], []
    price, vid = cheapest_available(p.get("variants", []), cents=True)
    if price is None or price > max_price:
        return [], []
    return [{"id": f"box|{shop_name}|{p.get('handle')}", "kind": "Booster box", "name": p.get("title") or p.get("handle") or "Booster box",
             "shop": shop_name, "price": price, "url": url.replace(".js", ""),
             "cart": shopify_cart_link(url, vid), "note": ""}], []


def woo_boxes(shop_name, url, max_price, watch=()):
    data = fetch_json(url)
    if not isinstance(data, list):
        return [], None
    finds, listings = [], []
    for p in data:
        name = re.sub("<[^>]+>", "", p.get("name", ""))
        if "one piece" not in name.lower():
            continue
        w = None if is_box_title(name) else watch_item(name, watch)
        if not is_box_title(name) and not w:
            continue
        kind, prefix, group = ("Sealed", "sealed", "watch") if w else ("Booster box", "box", "box")
        limit = w["max"] if w else max_price
        prices = p.get("prices", {})
        minor = int(prices.get("currency_minor_unit", 2))
        price = int(prices.get("price", 0) or 0) / (10 ** minor)
        buyable = bool(p.get("is_in_stock") and p.get("is_purchasable", True))
        link = woo_cart_link(url, p.get("id")) if buyable else ""
        note = w["name"] if w else ""
        listings.append({
            "id": f"list|{shop_name}|{p.get('id')}", "box_id": f"{prefix}|{shop_name}|{p.get('id')}",
            "group": group, "kind": "New listing", "name": name, "shop": shop_name, "price": price,
            "available": buyable, "url": p.get("permalink"), "cart": link, "note": note, "max": limit, "page": 1,
        })
        if not buyable or price <= 0 or price > limit:
            continue
        finds.append({"id": f"{prefix}|{shop_name}|{p.get('id')}", "kind": kind, "name": name,
                      "shop": shop_name, "price": price, "url": p.get("permalink"), "cart": link, "note": note})
    return finds, listings


def check_sealed(cfg):
    """Returns (finds, listings_by_shop). listings_by_shop[shop] is None when that shop failed."""
    mx = cfg["sealed"]["max_price"]
    watch = cfg.get("sealed_watch", DEFAULT_SEALED_WATCH) or []
    cols, prods, woo, search = sealed_shops(cfg)
    jobs = []
    for shop in cols:
        jobs.append((shopify_boxes, shop["name"], shop["url"], mx, watch))
    for shop in prods:
        jobs.append((shopify_product_box, shop["name"], shop["url"], mx, watch))
    for shop in woo:
        jobs.append((woo_boxes, shop["name"], shop["url"], mx, watch))
    for shop in search:
        jobs.append((shopify_search_boxes, shop["name"], shop["base"], mx, watch))
    results = pmap(lambda j: (j, j[0](*j[1:])), jobs, leaf=False)
    finds, by_shop = [], {}
    for job, (f, listings) in results:
        finds += f
        if job[0] is shopify_product_box:
            continue
        name = job[1]
        if listings is None:
            by_shop[name] = None            # failed: don't touch what we know about this shop
        elif by_shop.get(name, []) is not None:
            by_shop.setdefault(name, []).extend(listings)
    # de-dupe (same product listed twice)
    seen, out = set(), []
    for f in finds:
        if f["id"] not in seen:
            seen.add(f["id"])
            out.append(f)
    return out, by_shop


# ---------------------------------------------------------------- new listings
def load_known():
    return read_json(KNOWN_PATH, {}) or {}


def save_known(known):
    atomic_write_json(KNOWN_PATH, known, indent=1, sort_keys=True)


def new_listings(by_shop, known, box_finds, pages_seen=None):
    """Listings never seen before at that shop. The first good read of a shop only remembers
    what's there (no alerts), so a fresh install doesn't flood you. The same goes for products the
    bot reads for the first time because it now reads past page 1 of a big shop."""
    pages_seen = {} if pages_seen is None else pages_seen
    finds_ids = {f["id"] for f in box_finds}
    out = []
    groups = {}
    for shop, listings in by_shop.items():
        if listings is None:
            continue
        for l in listings:
            key = shop if l.get("group", "box") == "box" else f"{shop} (other sealed)"
            groups.setdefault(key, []).append(l)
        groups.setdefault(shop, [])              # a shop with no boxes still gets remembered
    deepest = {}
    for shop, listings in groups.items():
        base_shop = shop.replace(" (other sealed)", "")
        for l in listings:
            deepest[base_shop] = max(deepest.get(base_shop, 1), int(l.get("page", 1)))
    for shop, listings in groups.items():
        ids = {l["id"] for l in listings}
        base_shop = shop.replace(" (other sealed)", "")
        if shop not in known:
            what = "other sealed" if shop.endswith("(other sealed)") else "box"
            print(f"   (remembering {len(ids)} existing {what} listing(s) at {base_shop}; new ones will alert)")
            known[shop] = sorted(ids)
            continue
        before = set(known[shop])
        read_to = int(pages_seen.get(base_shop, 1))
        for l in listings:
            if l["id"] in before or l["box_id"] in finds_ids:
                continue            # already known, or already alerting as a buyable box
            if int(l.get("page", 1)) > read_to:
                continue            # first time we've read this deep into the shop: just remember it
            status = ("in stock" if l["available"] else "listed, not buyable yet")
            if l["available"] and l["price"] > l["max"]:
                status += f" (over your {money(l['max'])} max)"
            l = dict(l, note=(l["note"] + ", " if l["note"] else "") + status)
            out.append(l)
        known[shop] = sorted(before | ids)
    for shop, page in deepest.items():
        if page > int(pages_seen.get(shop, 1)):
            pages_seen[shop] = page
    return out


# ---------------------------------------------------------------- singles
def suggest(base, q):
    data = fetch_json(_suggest_url(base, q))
    if not data:
        return []
    return data.get("resources", {}).get("results", {}).get("products", [])


def product_js(base, handle):
    return fetch_json(f"{base}/products/{handle}.js")


def elemental_card(card, base):
    """Elemental titles include the card number, e.g. 'Sabo - OP13-120 [Carrying On His Will]'.
    Its search results only give the cheapest condition's price, sold out or not (a Damaged copy at $1
    when the only copy left is Near Mint at $2), so the price comes from the product page, by the same
    rule as the other shops: near mint if it's in stock, otherwise the cheapest condition that is."""
    excl = card.get("exclude", DEFAULT_EXCLUDE)
    hits = []
    for p in suggest(base, card["num"]):
        title = p.get("title", "")
        if not any(n in title.lower() or n in p.get("handle", "") for n in card_num_variants(card["num"])):
            continue
        if is_excluded(title, excl) or not p.get("available"):
            continue
        cheapest = float(p.get("price_min") or p.get("price") or 0)
        if cheapest <= 0 or cheapest > card["max"]:
            continue                 # even its cheapest condition is over your max: no need to open the page
        hits.append(p)
    pages = pmap(lambda p: product_js(base, p["handle"]), hits)
    out = []
    for p, page in zip(hits, pages):
        price, vid, cond = nm_copy((page or {}).get("variants"), cents=True)
        if price is None or price > card["max"]:
            continue                 # page didn't load, nothing left in stock, or the copy left is over your max
        out.append(single_find(card, "Elemental Arcade", price, base + "/products/" + p["handle"],
                               p.get("title", ""), shopify_cart_link(base, vid, card.get("qty", 1)), cond))
    return out


def js_matches_number(p, num):
    blob = json.dumps(p).lower()
    return any(n in blob for n in card_num_variants(num))


CONDITIONS = (("near mint", "NM"), ("lightly played", "LP"), ("moderately played", "MP"),
              ("heavily played", "HP"), ("damaged", "Damaged"))


def condition(variant_title):
    """'Lightly Played Foil' -> 'LP'; '' when the variant isn't a condition (e.g. 'Default Title')."""
    t = str(variant_title or "").lower()
    return next((short for word, short in CONDITIONS if word in t), "")


def nm_copy(variants, cents):
    """The copy of a single to quote: near mint if it's in stock, otherwise the cheapest condition that is.
    -> (price in dollars, variant id, condition e.g. 'NM'), or (None, None, '') when none are in stock."""
    avail = [v for v in variants or [] if v.get("available") and _num(v.get("price"))]
    if not avail:
        return None, None, ""
    nm = [v for v in avail if "near mint" in str(v.get("title") or "").lower()]
    v = min(nm or avail, key=lambda v: _num(v["price"]))
    price = _num(v["price"])
    return (price / 100 if cents else price), v.get("id"), condition(v.get("title"))


def nm_price(p):
    """(near-mint available price in dollars, variant id). Mayhem/GG .js prices are cents."""
    price, vid, _ = nm_copy(p.get("variants", []), cents=True)
    return price, vid


def handle_shop_card(card, shop_name, base):
    excl = card.get("exclude", DEFAULT_EXCLUDE)
    handles = list(card.get("handles", {}).get(shop_name, []))
    if not handles:  # search by name and confirm number below
        for p in suggest(base, card.get("search", card["name"])):
            if not is_excluded(p.get("title", ""), excl):
                handles.append(p["handle"])
        handles = handles[:8]
    pages = pmap(lambda h: product_js(base, h), handles)      # all product pages at once (v1: one by one)
    out = []
    for h, p in zip(handles, pages):
        if not p or not js_matches_number(p, card["num"]):
            continue
        if is_excluded(p.get("title", ""), excl):
            continue
        price, vid, cond = nm_copy(p.get("variants"), cents=True)
        if price is None or price > card["max"]:
            continue
        out.append(single_find(card, shop_name, price, f"{base}/products/{h}", p.get("title", ""),
                               shopify_cart_link(base, vid, card.get("qty", 1)), cond))
    return out


def single_find(card, shop, price, url, title, cart="", cond=""):
    """cond: the condition of the copy the price and Buy link are for ('NM', 'LP'...), if the shop says."""
    return {"id": f"card|{shop}|{card['num']}|{url.rsplit('/', 1)[-1]}", "kind": "Single",
            "name": f"{card['name']} {card['num']}".strip(), "deck": card.get("deck", ""), "qty": card.get("qty", 1),
            "shop": shop, "price": price, "url": url, "cart": cart, "note": title,
            "priority": card.get("priority", False), "cond": cond}


MAX_VALUE_PICKS = 80              # the ledger sends every listing worth watching (up to ~80)
VALUE_PICKS_PER_RUN = 15          # ...but each singles check only looks at 15 of them, taking turns,
_pick_turn = [0]                  # so every pick is still seen about once an hour without flooding the shops


def repo_json(cfg, name, max_age=1800):
    """A JSON file from the bot's GitHub repo (cached for max_age seconds). None if unavailable."""
    url = f"{(cfg or {}).get('repo_raw_url', REPO_RAW_URL).rstrip('/')}/{name}"
    hit = _remote_cache.get(url)
    if hit and time.time() - hit[0] < max_age:
        return hit[1]
    try:
        data = json.loads(HTTP.fetch(url, tries=1, robots=False).decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        data = None      # not there yet (e.g. before the ledger's first run) - that's fine
    _remote_cache[url] = (time.time(), data)
    return data


def load_picks_file(cfg=None):
    """market_picks.json: the local copy if it's today's (the cloud copy has it from the repo),
    otherwise the latest one from GitHub (the PC copy)."""
    local = read_json(PICKS_PATH, None)
    if isinstance(local, dict) and local.get("date") == f"{datetime.now():%Y-%m-%d}":
        return local
    remote = repo_json(cfg, "market_picks.json")
    if isinstance(remote, dict):
        try:
            atomic_write_json(PICKS_PATH, remote, indent=1)
        except Exception:  # noqa: BLE001
            pass
        return remote
    return local


# Cards you already have enough of: give a want-list card "owned": 4 (as many as its "qty") and the
# bot skips it, including the daily ledger's value picks for that card number. Collector versions
# with one of these words in the name are still shown, in case you want one as a pickup.
COLLECTOR_WORDS = ("wanted", "manga", "treasure", "super alternate", "serial", "signed", "championship")


def _flat(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def owned_nums(cfg):
    """Card numbers (flattened, e.g. "op13120") you have at least "qty" copies of."""
    out = set()
    for c in ((cfg or {}).get("singles") or {}).get("cards") or []:
        if isinstance(c, dict) and c.get("num"):
            have = _num(c.get("owned")) or 0
            if have > 0 and have >= (_num(c.get("qty", 1)) or 1):
                out.add(_flat(c["num"]))
    return out


def is_owned_pick(cfg, name, url="", owned=None):
    """True for a value pick of a card you already own enough of (collector versions excepted)."""
    owned = owned_nums(cfg) if owned is None else owned
    if not owned or any(w in str(name or "").lower() for w in COLLECTOR_WORDS):
        return False
    text = _flat(name) + " " + _flat(url)
    return any(n in text for n in owned)


def load_value_picks(cfg=None):
    """Cards the daily market ledger thinks are good value, from market_picks.json:
    {"watch": [{"name", "product_url", "max", "market", "note"}, ...]}. Missing file = none."""
    data = load_picks_file(cfg)
    if not data:
        return []
    out = []
    owned = owned_nums(cfg)
    for x in (data.get("watch", []) if isinstance(data, dict) else [])[:MAX_VALUE_PICKS]:
        try:
            if is_owned_pick(cfg, x.get("name"), x.get("product_url"), owned):
                continue
            if x["product_url"].startswith("https://") and float(x["max"]) > 0:
                out.append(x)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return out


def value_pick_card(pick):
    """Check one value pick's product page; returns a find if it's buyable at or under its max."""
    url = pick["product_url"].split("?")[0].rstrip("/")
    p = fetch_json(url + ".js")
    if not p:
        return []
    price, vid, cond = nm_copy(p.get("variants"), cents=True)
    if price is None or price > float(pick["max"]):
        return []
    card = {"name": pick.get("name", p.get("title", "Value pick")), "num": "", "qty": 1, "max": float(pick["max"]),
            "deck": "value pick", "priority": False}
    host = urllib.parse.urlparse(url).netloc
    shop = {"elementalarcade.com.au": "Elemental Arcade", "tcg.goodgames.com.au": "Good Games"}.get(
        host, "Mayhem" if "mayhem" in host else host)
    f = single_find(card, shop, price, url, p.get("title", ""), shopify_cart_link(url, vid), cond)
    f["id"] = f"card|pick|{url}"
    f["kind"] = "Single"
    f["value_pick"] = True
    market = pick.get("market")
    f["note"] = (p.get("title", "") + (f" · US market ≈ {money(float(market))}" if market else "") +
                 (f" · {pick['note']}" if pick.get("note") else ""))
    return [f]


def picks_this_turn(picks, n):
    """The next n value picks, wrapping round, so all of them get checked over a few singles checks."""
    if len(picks) <= n:
        return picks
    start = _pick_turn[0] % len(picks)
    _pick_turn[0] = start + n
    return (picks + picks)[start:start + n]


def check_singles(cfg):
    shops = cfg["singles"]["shops"]
    cards = [c for c in cfg["singles"]["cards"] if c.get("enabled", True)]
    jobs = []
    for c in cards:
        only = c.get("shops")          # optional per card, e.g. ["Elemental Arcade"]: check just those shops
        want = set(only) if isinstance(only, list) and only else None
        if "Elemental Arcade" in shops and (want is None or "Elemental Arcade" in want):
            jobs.append((elemental_card, c, shops["Elemental Arcade"]))
        for name in ("Mayhem", "Good Games"):
            if name in shops and (want is None or name in want):
                jobs.append((handle_shop_card, c, name, shops[name]))
    if cfg.get("value_picks", True):
        for pick in picks_this_turn(load_value_picks(cfg), int(_num(cfg.get("value_picks_per_check")) or VALUE_PICKS_PER_RUN)):
            jobs.append((value_pick_card, pick))
    results = pmap(lambda j: j[0](*j[1:]), jobs, leaf=False)
    return [f for r in results for f in r]


# ---------------------------------------------------------------- singles price drops
# About once an hour the bot reads each singles shop's whole One Piece singles list (about 3,300 at
# Elemental Arcade, 1,300 in stock at Good Games) and notes each card's near-mint price whenever it
# changes (singles_prices.json). Every 6 hours (12am, 6am, 12pm, 6pm) it posts the singles in stock now
# that got the most cheaper over those 6 hours. All optional, in config.json:
#     "price_drops": {"every_hours": 6, "top": 10, "min_pct": 10, "min_drop": 1, "rank_by": "percent"}
# "rank_by": "dollars" puts the biggest saving first; "price_drops": false switches it off. Posts go to
# "discord_webhook_drops" if set (DISCORD_WEBHOOK_DROPS in the cloud), otherwise the singles channel.
DROPS_PATH = os.path.join(HERE, "singles_prices.json")
CATALOGS = {        # each singles shop's whole One Piece list (Mayhem's store is behind a password, so not Mayhem)
    "Elemental Arcade": "/collections/one-piece-singles/products.json?limit=250",
    "Good Games": "/collections/one-piece-card-game-singles-in-stock/products.json?limit=250",
}
DROPS_DEFAULTS = {"enabled": True, "every_hours": 6, "top": 10, "min_pct": 10.0, "min_drop": 1.0,
                  "rank_by": "percent", "scan_every_minutes": 60, "shops": None}
DROPS_HOURS = (1, 2, 3, 4, 6, 8, 12, 24)    # posts start on the hour from midnight, so it has to divide 24
CATALOG_MAX_PAGES = 30          # 250 a page, so up to 7,500 singles per shop
DROPS_KEEP_HOURS = 48           # price changes older than this are let go (the last one before stays as "before")
DROPS_FORGET_DAYS = 14          # a single that's been off its shop's list this long is forgotten
DROPS_FRESH = 15 * 60           # just before a post, a shop list read longer ago than this is read again
CARD_NUM_RE = re.compile(r"\b(?:(?:OP|EB|ST|PRB)\d{2}|P)-\d{3}\b", re.I)


def check_drops_config(cfg):
    """Tidy "price_drops" in config.json in place; returns warnings for anything that had to be ignored."""
    pd, w = cfg.get("price_drops"), []
    if pd is None or isinstance(pd, bool):
        return w
    if not isinstance(pd, dict):
        cfg["price_drops"] = {}
        return ['"price_drops" should be {...} or false; using the defaults']
    for k in [k for k in pd if k not in DROPS_DEFAULTS and not str(k).startswith("_")]:
        w.append(f'price_drops: unknown setting "{k}"')
        pd.pop(k)
    for k in ("every_hours", "top", "min_pct", "min_drop", "scan_every_minutes"):
        if k in pd:
            v = _num(pd[k])
            if v is None or v < 0:
                w.append(f'price_drops "{k}" should be a number; using {DROPS_DEFAULTS[k]}')
                pd.pop(k)
            else:
                pd[k] = v
    if "every_hours" in pd and pd["every_hours"] not in DROPS_HOURS:
        w.append(f'price_drops "every_hours" should be one of {", ".join(map(str, DROPS_HOURS))}; using 6')
        pd.pop("every_hours")
    if "rank_by" in pd and pd["rank_by"] not in ("percent", "dollars"):
        w.append('price_drops "rank_by" should be "percent" or "dollars"; using "percent"')
        pd.pop("rank_by")
    if "enabled" in pd and not isinstance(pd["enabled"], bool):
        w.append('price_drops "enabled" should be true or false')
        pd.pop("enabled")
    if pd.get("shops") is not None:
        given = pd["shops"] if isinstance(pd["shops"], list) else []
        good = [x for x in given if isinstance(x, dict) and x.get("name") and str(x.get("url", "")).startswith("https://")]
        if len(good) != len(given) or not isinstance(pd["shops"], list):
            w.append('price_drops "shops" entries need a "name" and an https:// "url" (a products.json list); '
                     'skipped the rest')
        pd["shops"] = good
    return w


def drops_settings(cfg):
    """The price-drop settings: the defaults with config.json's "price_drops" on top. Unless "shops" is
    given, the lists read are those of your singles shops that have one (see CATALOGS)."""
    s = dict(DROPS_DEFAULTS)
    user = (cfg or {}).get("price_drops")
    if user is False:
        s["enabled"] = False
    elif isinstance(user, dict):
        s.update({k: v for k, v in user.items() if k in DROPS_DEFAULTS})
    if s["shops"] is None:
        mine = ((cfg or {}).get("singles") or {}).get("shops") or {}
        s["shops"] = [{"name": n, "url": str(b).rstrip("/") + CATALOGS[n]} for n, b in mine.items() if n in CATALOGS]
    s["every_hours"] = int(s["every_hours"]) if s["every_hours"] in DROPS_HOURS else 6
    return s


def read_catalog(url, max_pages=CATALOG_MAX_PAGES):
    """Every product in a shop's (big) collection, 250 a page -> (products, complete), or (None, False)
    if the first page couldn't be read. complete is False if a later page failed or the list ran past
    max_pages (products is then what was read). The number of pages from last time is asked for at once."""
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    try:
        limit = max(1, int(q.get("limit", 30)))
    except ValueError:
        limit = 30

    def page_url(n):
        return url if n == 1 else url + ("&" if "?" in url else "?") + f"page={n}"

    HTTP.gzip_urls.add(url.split("?", 1)[0])          # a page of 250 singles is ~1 MB, ~10x less zipped
    try:
        hint = max(1, min(max_pages, int(PAGE_HINTS.get(url, 1))))
    except (TypeError, ValueError):
        hint = 1
    pages = pmap(lambda n: fetch_json(page_url(n)), range(1, hint + 1))
    if not isinstance(pages[0], dict):
        return None, False
    products, handles, complete, n = [], set(), True, 0
    while True:
        if n >= max_pages:
            complete = False                           # longer than max_pages: what's been read will do
            break
        data = pages[n] if n < len(pages) else fetch_json(page_url(n + 1))
        n += 1
        if not isinstance(data, dict):
            complete = False                           # this page failed, so the rest is unknown
            break
        batch = data.get("products") or []
        new = [p for p in batch if p.get("handle") and p["handle"] not in handles]
        handles.update(p["handle"] for p in new)
        products.extend(new)
        if len(batch) < limit or not new:
            break                                      # the last page (or a shop that ignores page=)
    PAGE_HINTS[url] = n
    return products, complete


def catalog_entry(p):
    """One single from a shop's product list -> {"name", "price", "avail", "vid"}, or None. The near-mint
    copy is the one followed (it's listed in stock or not), so a price change is a real change and not
    a different condition being cheapest."""
    variants = [v for v in p.get("variants") or [] if (_num(v.get("price")) or 0) > 0]
    if not variants:
        return None
    nm = [v for v in variants if "near mint" in str(v.get("title") or "").lower()]
    v = nm[0] if nm else min(variants, key=lambda v: _num(v["price"]))
    name = re.sub(r"\s+", " ", str(p.get("title") or p.get("handle") or "")).strip()
    if not CARD_NUM_RE.search(name):                   # Good Games leaves the card number out of the title
        m = CARD_NUM_RE.search(re.sub(r"<[^>]+>", " ", str(p.get("body_html") or "")))
        if m:
            name += f" ({m.group(0).upper()})"
    return {"name": name, "price": round(_num(v["price"]), 2), "avail": bool(v.get("available")), "vid": v.get("id")}


def load_drops_store():
    s = read_json(DROPS_PATH, None)
    if not isinstance(s, dict) or s.get("v") != 1 or not isinstance(s.get("items"), dict):
        s = {"v": 1, "shops": {}, "items": {}}
    if not isinstance(s.get("shops"), dict):
        s["shops"] = {}
    return s


def save_drops_store(store):
    """One single per line, so the cloud copy's commits of this file stay small."""
    rows = ",\n".join(f"{json.dumps(k)}:{json.dumps(v, separators=(',', ':'))}" for k, v in sorted(store["items"].items()))
    atomic_write_text(DROPS_PATH, '{"v":1,"shops":' + json.dumps(store.get("shops", {}), separators=(",", ":"),
                                                                  sort_keys=True) + ',"items":{\n' + rows + "\n}}\n")


def record_catalog(store, shop, base, products, complete, now=None):
    """Note one read of a shop's singles list: a point [time, price, 1 in stock / 0 not] for each single
    whose near-mint price or stock changed since the last read. A complete read also marks singles that
    have left the list (sold out at Good Games) as not buyable. Returns how many changes there were."""
    now = int(now or time.time())
    items = store.setdefault("items", {})
    sh = store.setdefault("shops", {}).setdefault(shop, {})
    sh.update(base=base, n=len(products))
    sh["scans"] = [t for t in sh.get("scans", []) if now - t < DROPS_KEEP_HOURS * 3600] + [now]
    changes, seen = 0, set()
    for p in products:
        e = catalog_entry(p) if p.get("handle") else None
        if not e:
            continue
        key = f"{shop}|{p['handle']}"
        seen.add(key)
        point = [now, e["price"], 1 if e["avail"] else 0]
        it = items.get(key)
        if it is None:
            items[key] = {"n": e["name"], "v": e["vid"], "p": [point]}
            changes += 1
            continue
        pts = it.setdefault("p", [])
        if not pts or abs(pts[-1][1] - point[1]) >= 0.005 or pts[-1][2] != point[2]:
            pts.append(point)
            changes += 1
        for k, val in (("n", e["name"]), ("v", e["vid"])):
            if it.get(k) != val:
                it[k] = val
                changes += 1
        if it.pop("gone", None) is not None:
            changes += 1
    if complete:
        for key, it in items.items():
            if key.startswith(shop + "|") and key not in seen:
                if it.get("p") and it["p"][-1][2]:
                    it["p"].append([now, it["p"][-1][1], 0])       # gone from the list: not buyable now
                    changes += 1
                if "gone" not in it:
                    it["gone"] = now
                    changes += 1
    return changes + prune_drops(store, now)


def prune_drops(store, now=None):
    """Let go of price changes older than DROPS_KEEP_HOURS (keeping the last one before that, which is the
    price going into any window) and of singles gone from their shop for DROPS_FORGET_DAYS."""
    now = now or time.time()
    cut, forget = now - DROPS_KEEP_HOURS * 3600, now - DROPS_FORGET_DAYS * 86400
    items, changes = store.get("items", {}), 0
    for key in list(items):
        it = items[key]
        if not it.get("p") or it.get("gone", now) < forget:
            del items[key]
            changes += 1
            continue
        pts, i = it["p"], 0
        while i + 1 < len(pts) and pts[i + 1][0] <= cut:
            i += 1
        if i:
            del pts[:i]
            changes += 1
    return changes


def best_drops(store, now=None, hours=6, min_pct=10, min_drop=1.0, top=10, rank_by="percent"):
    """Singles in stock now whose near-mint price fell the most over the last `hours`, compared with the
    shop's last read before the window (or, when that's from long before because the bot was off, its
    first read inside the window). -> [{"name", "shop", "was", "price", "drop", "pct", "url", "cart", "since"}]"""
    now = float(now or time.time())
    t0 = now - hours * 3600
    slack = min(hours, 3) * 3600
    shops = store.get("shops") or {}
    before_read = {}
    for shop, sh in shops.items():
        scans = sorted(sh.get("scans") or [])
        earlier = [t for t in scans if t <= t0]
        inside = [t for t in scans if t0 < t <= now]
        if earlier and t0 - earlier[-1] <= slack:
            before_read[shop] = earlier[-1]
        elif inside:
            before_read[shop] = inside[0]
    out = []
    for key, it in (store.get("items") or {}).items():
        shop, _, handle = key.partition("|")
        b, pts = before_read.get(shop), it.get("p") or []
        if b is None or not pts:
            continue
        cur = pts[-1]
        if not cur[2] or cur[0] <= b:
            continue                              # not buyable now, or no change since the "before" read
        prev = None
        for p in pts:
            if p[0] > b:
                break
            prev = p
        if prev is None:                          # first listed after the "before" read: its first price
            prev = pts[0]
            if prev is cur:
                continue
        was, price = prev[1], cur[1]
        drop = round(was - price, 2)
        if was <= 0 or drop < min_drop - 0.001:
            continue
        pct = drop / was * 100
        if pct < min_pct - 0.001:
            continue
        base = (shops.get(shop) or {}).get("base", "")
        out.append({"key": key, "name": it.get("n") or handle, "shop": shop, "was": was, "price": price,
                    "drop": drop, "pct": pct, "since": b, "url": f"{base}/products/{handle}",
                    "cart": shopify_cart_link(base, it.get("v")) if base and it.get("v") else ""})
    if rank_by == "dollars":
        out.sort(key=lambda d: (-d["drop"], -d["pct"], d["name"]))
    else:
        out.sort(key=lambda d: (-d["pct"], -d["drop"], d["name"]))
    return out[:int(top)] if top else out


def _clock(ts):
    """6:00 PM -> '6:00 PM' (no leading zero, on Windows too)."""
    return datetime.fromtimestamp(ts).strftime("%I:%M %p").lstrip("0")


def drops_embed(drops, hours, store=None, settings=None, now=None):
    """The Discord post (an embed dict) for best_drops()."""
    s = settings or DROPS_DEFAULTS
    now = float(now or time.time())
    store = store or {}
    lines, size = [], 0
    for i, d in enumerate(drops, 1):
        buy = f" · [⚡ Buy]({d['cart']})" if d.get("cart") else ""
        line = (f"**{i}.** [{link_text(d['name'], 70)}]({d['url']}) **{money(d['price'])}** ~~{money(d['was'])}~~ "
                f"· {d['pct']:.0f}% off ({money(d['drop'])}) · {d['shop']}{buy}")
        if size + len(line) > 3900:
            break
        lines.append(line)
        size += len(line) + 1
    if not lines:
        lines = [f"No single in stock got {float(s['min_pct']):g}% or more (and {money(float(s['min_drop']))}+) "
                 f"cheaper in the last {hours} hours."]
    since = min((d["since"] for d in drops), default=now - hours * 3600)
    shops = sorted((store.get("shops") or {}))
    rank = "biggest saving first" if s.get("rank_by") == "dollars" else "biggest % first"
    n = len(store.get("items") or {})
    return {"title": f"📉 Best single price drops · last {hours} hours", "color": GREEN,
            "description": "\n".join(lines),
            "footer": {"text": f"Near-mint copies in stock now, vs. {_clock(since)} · {rank} · tracking "
                               f"{n:,} single{'' if n == 1 else 's'} at {', '.join(shops) or 'no shops yet'}"}}


def pc_heard_since(cfg, ts):
    """Cloud copy: has the PC copy said "I'm on" since unix time ts? (ntfy keeps messages 12 hours.)
    False if ntfy can't be read."""
    topic = (cfg.get("alerts") or {}).get("heartbeat_topic")
    if not topic:
        return False
    try:
        body = HTTP.fetch(f"https://ntfy.sh/{urllib.parse.quote(topic)}/json?poll=1&since={int(ts)}",
                          tries=1, conditional=False, robots=False, memo=False)
        return any(json.loads(line).get("event") == "message"
                   for line in body.decode("utf-8", "replace").splitlines() if line.strip())
    except Exception:  # noqa: BLE001
        return False


def run_price_drops(cfg, status, show_all=False, role=None, pc_on=False, now=None):
    """Read the singles shops' whole lists when they're due, note the price changes, and once per slot
    (every 6 hours: 12am, 6am, 12pm, 6pm) post the best drops. -> the drops when a post was due or
    show_all is set, else None."""
    s = drops_settings(cfg)
    if not s["enabled"] or not s["shops"]:
        return None
    now = float(now or time.time())
    hours = s["every_hours"]
    now_dt = datetime.fromtimestamp(now)
    slot_dt = now_dt.replace(hour=now_dt.hour // hours * hours, minute=0, second=0, microsecond=0)
    slot = f"{slot_dt:%Y-%m-%d %H}"
    status.setdefault("drops_slot", slot)            # first run: the first post comes when the next slot starts
    post_due = status["drops_slot"] != slot and not show_all
    if post_due and role == "listen" and (pc_on or pc_heard_since(cfg, slot_dt.timestamp())):
        status["drops_slot"] = slot                  # the PC copy is on (or was, this slot) and posts it itself
        post_due = False

    scans = status.setdefault("drops_scan", {})
    gap = (DROPS_FRESH if post_due else float(s["scan_every_minutes"]) * 60) - 30
    due = [sh for sh in s["shops"] if now - float(scans.get(sh["name"], 0) or 0) >= gap]
    store = None
    if due:
        store = load_drops_store()
        read = False
        for sh, (products, complete) in pmap(lambda sh: (sh, read_catalog(sh["url"])), due, leaf=False):
            if products is None:
                print(f"   ! price drops: couldn't read {sh['name']}'s singles list; trying again next check")
                continue
            record_catalog(store, sh["name"], origin(sh["url"]), products, complete, now)
            scans[sh["name"]] = round(now)
            read = True
            print(f"   (price drops: read {len(products):,} singles at {sh['name']}"
                  + ("" if complete else ", not the whole list") + ")")
        if read:
            save_drops_store(store)
    if not (post_due or show_all):
        return None

    store = store or load_drops_store()
    drops = best_drops(store, now, hours, float(s["min_pct"]), float(s["min_drop"]), int(s["top"]), s["rank_by"])
    if show_all:
        return drops
    alerts = cfg.get("alerts") or {}
    hook = alerts.get("discord_webhook_drops") or alerts.get("discord_webhook_singles") or alerts.get("discord_webhook")
    if not drops or not hook or DRY_RUN[0]:
        print(f"   (price drops: {len(drops)} single(s) {float(s['min_pct']):g}%+ cheaper in the last {hours} hours"
              + (", nothing to post)" if not drops else ", not posted)"))
        if not DRY_RUN[0]:
            status["drops_slot"] = slot
        return drops
    payload = {"username": alerts.get("bot_name") or "One Piece Restock",
               "embeds": [drops_embed(drops, hours, store, s, now)], "allowed_mentions": {"parse": []}}
    if discord_send(alerts, hook, payload):
        status["drops_slot"] = slot
        print(f"   (price drops: posted the best {len(drops)} of the last {hours} hours to Discord)")
    else:
        print("   ! price drops didn't reach Discord; trying again next check")
    return drops


def drops_report(drops, hours, min_pct=10):
    """Console lines for --all."""
    if not drops:
        return f"PRICE DROPS (last {hours}h): none of {float(min_pct):g}%+ yet."
    lines = [f"PRICE DROPS (last {hours}h)"]
    for d in drops:
        lines.append(f"  {d['name']}  {money(d['price'])} (was {money(d['was'])}, {d['pct']:.0f}% off)  @ {d['shop']}")
        lines.append(f"    {d['url']}")
    return "\n".join(lines)


def _me():
    """This module, whether it's running as the bot (__main__) or imported (commands_bot.py, tests)."""
    return sys.modules[__name__]


def run_checks(cfg, sealed=True, singles=True):
    """Boxes and singles at the same time (v1 did one after the other). -> ((finds, by_shop) | None, singles | None)"""
    s, g, _ = run_checks_all(cfg, sealed, singles, False)
    return s, g


def run_checks_all(cfg, sealed=True, singles=True, pokemon=True, poke_only=None):
    """Boxes, singles and Pokémon at the same time.
    -> ((finds, by_shop) | None, singles | None, pokemon_watch.Result | None)"""
    ex = _pool("phases", 4)
    fs = ex.submit(check_sealed, cfg) if sealed else None
    fg = ex.submit(check_singles, cfg) if singles else None
    fp = ex.submit(pokemon_watch.check, cfg, _me(), poke_only) if (pokemon and pokemon_watch) else None
    return (fs.result() if fs else None), (fg.result() if fg else None), (fp.result() if fp else None)


# ---------------------------------------------------------------- drop-day mode
AUTO_DROP_RE = re.compile(r"\b(OP|EB|PRB)-?(\d{1,2})\b", re.I)


def auto_windows(cfg, now=None):
    """Drop windows for booster releases in the release list: the evening before (6pm-midnight) and
    release morning (8am-2pm), checking every 60 seconds. Off with "auto_drop_windows": false."""
    if not cfg.get("auto_drop_windows", True):
        return []
    now = now or datetime.now()
    out = []
    for r in cfg.get("releases", DEFAULT_RELEASES) or []:
        m = AUTO_DROP_RE.search(r.get("name", "") if isinstance(r, dict) else "")
        if not m:
            continue
        try:
            d = datetime.strptime(r["date"], "%Y-%m-%d")
        except (KeyError, ValueError, TypeError):
            continue
        if "approx" in r.get("name", "").lower() or d.date() < now.date() - timedelta(days=1):
            continue
        code = f"{m.group(1).upper()}-{int(m.group(2)):02d}"
        out.append({"name": f"{code} eve (auto)", "start": d - timedelta(hours=6), "end": d - timedelta(minutes=1),
                    "every": 60, "sealed_only": True})
        out.append({"name": f"{code} release day (auto)", "start": d + timedelta(hours=8), "end": d + timedelta(hours=14),
                    "every": 60, "sealed_only": True})
    return out


def _game(x):
    """"pokemon" / "Pokémon" -> "pokemon"; anything else (or nothing) -> "onepiece"."""
    g = str(x or ONE_PIECE).lower().replace("é", "e")
    return POKE if g.startswith("poke") else ONE_PIECE


def parse_windows(cfg):
    out = []
    for w in cfg.get("drop_windows", []) or []:
        try:
            start = datetime.strptime(w["start"], "%Y-%m-%d %H:%M")
            end = datetime.strptime(w["end"], "%Y-%m-%d %H:%M")
        except (KeyError, ValueError, TypeError, AttributeError) as e:
            print(f"   ! drop window {w.get('name', '?') if isinstance(w, dict) else w} skipped: use \"YYYY-MM-DD HH:MM\" ({e})")
            continue
        if end <= start:
            continue
        every = max(MIN_DROP_SECONDS, int(_num(w.get("every_seconds", 60)) or 60))
        out.append({"name": w.get("name", "drop"), "start": start, "end": end, "every": every,
                    "sealed_only": w.get("sealed_only", True), "games": [_game(w.get("game"))],
                    "sections": [str(x) for x in w.get("sections") or []]})
    mine = list(out)
    autos = [dict(w, games=w.get("games") or [ONE_PIECE]) for w in auto_windows(cfg)]
    if pokemon_watch:
        try:
            autos += pokemon_watch.auto_windows(cfg)
        except Exception as e:  # noqa: BLE001
            print(f"   ! Pokémon drop windows skipped ({e})")
    for w in autos:                    # yours win where they overlap (for the same game)
        g = w["games"][0]
        if not any(g in x["games"] and w["start"] < x["end"] and x["start"] < w["end"] for x in mine):
            out.append(w)
    out.sort(key=lambda w: w["start"])
    return out


def active_window(cfg, now=None):
    """The drop window on now. If several overlap (e.g. a One Piece and a Pokémon release), one merged
    window: the fastest pace, every game and Pokémon release in any of them."""
    now = now or datetime.now()
    act = [w for w in parse_windows(cfg) if w["start"] <= now < w["end"]]
    if len(act) <= 1:
        return act[0] if act else None
    op = [w for w in act if ONE_PIECE in w.get("games", [ONE_PIECE])]
    pk = [w for w in act if POKE in w.get("games", [])]
    return {"name": " + ".join(dict.fromkeys(w["name"] for w in act)), "start": min(w["start"] for w in act),
            "end": max(w["end"] for w in act), "every": min(w["every"] for w in act),
            "sealed_only": all(w.get("sealed_only", True) for w in op) if op else True,
            "games": sorted({g for w in act for g in w.get("games", [ONE_PIECE])}),
            # a Pokémon window without "sections" means every Pokémon release
            "sections": [] if any(not w.get("sections") for w in pk) else sorted({s for w in pk for s in w["sections"]})}


def drop_label(drop):
    """What a drop window checks every minute, for the status posts."""
    games = set(drop.get("games") or [ONE_PIECE])
    if games == {POKE}:
        return "Pokémon"
    return "booster boxes" + (" and Pokémon" if POKE in games else "")


def seconds_until_next_check(cfg, normal_minutes, now=None):
    """Normal gap, the drop-window gap while one is on, or a short wait so a window starts on time."""
    now = now or datetime.now()
    w = active_window(cfg, now)
    if w:
        return min(w["every"], max(1.0, (w["end"] - now).total_seconds()))
    normal = normal_minutes * 60
    starts = [x["start"] for x in parse_windows(cfg) if x["start"] > now]
    if starts:
        wait = (min(starts) - now).total_seconds()
        if wait < normal:
            return max(1.0, wait)
    return normal


# ---------------------------------------------------------------- PC/cloud hand-off
def heartbeat_role(cfg):
    a = cfg.get("alerts") or {}
    if not a.get("heartbeat_topic"):
        return None
    return (a.get("heartbeat_role") or "send").lower()


def heartbeat_body(cfg, status=None):
    """What the PC copy tells the cloud copy: "pc-on", plus "pokemon" if the PC posts Pokémon alerts itself,
    plus "r=<key>,..." for the release-day posts it made in the last half hour."""
    body = "pc-on"
    alerts = cfg.get("alerts") or {}
    if pokemon_watch and pokemon_watch.enabled(cfg) and pokemon_watch.hooks(alerts):
        body += " pokemon"
        recent = pokemon_watch.recently_sent(status or {})
        if recent:
            body += " r=" + ",".join(recent)
    return body


def send_heartbeat(cfg, force=False, status=None):
    """PC copy: tell the cloud copy we're on (every 15 minutes, and straight after posting finds, at most
    once a minute: ntfy.sh allows 250 messages a day)."""
    global _last_heartbeat
    gap = time.time() - _last_heartbeat
    if DRY_RUN[0] or gap < (60 if force else HEARTBEAT_EVERY):
        return
    topic = cfg["alerts"]["heartbeat_topic"]
    try:
        status_code, _, _ = HTTP.post(f"https://ntfy.sh/{urllib.parse.quote(topic)}",
                                      heartbeat_body(cfg, status).encode("utf-8"), {"Cache": "yes"})
        if status_code >= 400:
            raise HttpError(status_code)
        _last_heartbeat = time.time()
    except Exception as e:  # noqa: BLE001
        print(f"   ! couldn't tell the cloud copy the PC is on ({e})")


# What the PC copy's latest "I'm on" said (cloud copy): does it post Pokémon itself, and which
# release-day posts has it made. Filled in by pc_last_seen().
PC_INFO = {"pokemon": False, "posted": set()}


def pc_last_seen(cfg):
    """Cloud copy: when did the PC copy last check in (unix time), or None if not in the last 20 minutes.
    If ntfy can't be read, None (a doubled alert is better than a missed one)."""
    topic = cfg["alerts"]["heartbeat_topic"]
    PC_INFO.update(pokemon=False, posted=set())
    try:
        body = HTTP.fetch(f"https://ntfy.sh/{urllib.parse.quote(topic)}/json?poll=1&since={HEARTBEAT_FRESH}",
                          tries=1, conditional=False, robots=False, memo=False)
        msgs = []
        for line in body.decode("utf-8", "replace").splitlines():
            if line.strip():
                m = json.loads(line)
                if m.get("event") == "message":
                    msgs.append((float(m.get("time") or time.time()), str(m.get("message") or "")))
        if not msgs:
            return None
        msgs.sort()
        PC_INFO["pokemon"] = "pokemon" in msgs[-1][1].split()
        for _, text in msgs:
            for word in text.split():
                if word.startswith("r="):
                    PC_INFO["posted"].update(k for k in word[2:].split(",") if k)
        return msgs[-1][0]
    except Exception as e:  # noqa: BLE001
        print(f"   ! couldn't check whether the PC is on ({e}), posting anyway")
        return None


def pc_is_on(cfg):
    """Cloud copy: has the PC copy checked in recently? (kept for older callers)"""
    return pc_last_seen(cfg) is not None


# ---------------------------------------------------------------- status posts
# Short, no-ping Discord posts about the bot itself (not finds). They go to "discord_webhook_status"
# if you add one, otherwise to the booster-boxes channel.
GREEN, AMBER, RED, BLUE, GREY = 0x2A9D8F, 0xF4A261, 0xE63946, 0x457B9D, 0x6C757D


def load_status():
    return read_json(STATUS_PATH, {}) or {}


def save_status(status):
    atomic_write_json(STATUS_PATH, status, indent=1, sort_keys=True)


def post_status(cfg, text, color=GREY):
    alerts = (cfg or {}).get("alerts") or {}
    hook = alerts.get("discord_webhook_status") or alerts.get("discord_webhook_boxes") or alerts.get("discord_webhook")
    text = redact(text)
    print(f"   [status] {text}")
    if not hook or DRY_RUN[0]:
        return
    payload = {"username": alerts.get("bot_name") or "One Piece Restock",
               "embeds": [{"description": text[:4000], "color": color,
                           "footer": {"text": f"Sent by the {copy_label(cfg)}"}}],
               "allowed_mentions": {"parse": []}}
    discord_send(alerts, hook, payload)


def copy_label(cfg):
    """Which copy of the bot is running: the cloud one (GitHub Actions) or the PC one."""
    if os.environ.get("GITHUB_ACTIONS") == "true" or heartbeat_role(cfg) == "listen":
        return "cloud copy (GitHub)"
    return "PC copy"


def shop_names(cfg):
    names = {}
    for group in sealed_shops(cfg):
        for shop in group:
            names.setdefault(urllib.parse.urlparse(shop.get("url") or shop.get("base")).netloc, shop["name"])
    for name, base in cfg.get("singles", {}).get("shops", {}).items():
        names.setdefault(urllib.parse.urlparse(base).netloc, name)
    if pokemon_watch:
        try:
            for s in pokemon_watch.shops(cfg, _me()):
                names.setdefault(urllib.parse.urlparse(s["base"]).netloc, s["name"])
        except Exception:  # noqa: BLE001
            pass
    return names


def store_locked(host):
    """True if a Shopify shop has put its whole store behind a password page (closed, 'opening soon'
    or members-only). Its product feeds then answer 401, which isn't a fault the bot can get round."""
    try:
        req = urllib.request.Request(f"https://{host}/", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            return urllib.parse.urlsplit(r.geturl()).path.rstrip("/") == "/password"
    except Exception:  # noqa: BLE001
        return False


def shop_health(cfg, status):
    """Compare this run's shop results with earlier runs. Returns (text, color) posts for
    shops that just went down (failed SHOP_DOWN_AFTER checks in a row) or just came back.
    A shop that's down is then retried every down_retry_minutes instead of every check."""
    names = shop_names(cfg)
    fails = status.setdefault("shop_fails", {})
    retry = status.setdefault("shop_retry", {})
    down = set(status.get("shop_down", []))
    locked = set(status.get("shop_locked", []))
    gap = 60 * float(_num(cfg.get("down_retry_minutes", DOWN_RETRY_MIN)) or 0)
    posts = []
    with _host_lock:
        results = dict(_host_results)

    # A shop taken off the list (e.g. Friendly Collectibles) shouldn't stay "down" in /status forever.
    for host in [h for h in set(down) | set(fails) | set(retry) if h not in names and h not in results]:
        down.discard(host)
        locked.discard(host)
        fails.pop(host, None)
        retry.pop(host, None)

    # Nearly every shop failing in the same check means the bot lost its connection or is being
    # blocked, not that the shops went down. Post one message instead of one per shop, and leave the
    # per-shop counters alone so every shop keeps being checked and recovery is spotted straight away.
    failed = [h for h, (ok, bad) in results.items() if bad and not ok]
    if len(results) >= OFFLINE_MIN_SHOPS and len(failed) >= OFFLINE_SHARE * len(results):
        streak = status.get("offline_streak", 0) + 1
        status["offline_streak"] = streak
        if streak == SHOP_DOWN_AFTER:
            posts.append((f"📡 **The bot can't reach the shops.** {len(failed)} of {len(results)} sites failed "
                          f"for {streak} checks in a row, so the problem is on the bot's side (no internet, or "
                          f"the shops are blocking it), not the shops. Stock isn't being watched until it's "
                          f"back. You'll get a post when it is.", RED))
        status["shop_down"] = sorted(down)
        return posts
    if any(ok for ok, bad in results.values()):
        if status.get("offline_streak", 0) >= SHOP_DOWN_AFTER:
            posts.append(("📡 **Connection is back**, so the bot can see the shops again.", GREEN))
        status["offline_streak"] = 0

    for host, (ok, bad) in results.items():
        name = names.get(host, host)
        if ok:
            fails[host] = 0
            retry.pop(host, None)
            if host in down:
                down.discard(host)
                if host in locked:
                    posts.append((f"🔓 **{name}** has opened its store (no more password page), so it's on watch now.", GREEN))
                else:
                    posts.append((f"✅ **{name}** is loading again, so it's back on watch.", GREEN))
            locked.discard(host)
        elif bad:
            fails[host] = min(fails.get(host, 0) + 1, SHOP_DOWN_AFTER)   # stops counting once it's down
            if fails[host] >= SHOP_DOWN_AFTER:
                if host not in down:
                    down.add(host)
                    if store_locked(host):
                        locked.add(host)
                        posts.append((f"🔒 **{name}** has locked its whole store behind a password (closed, opening "
                                      f"soon, or members only), so nobody can see its stock. The bot keeps checking "
                                      f"and will post when it opens.", GREY))
                    else:
                        posts.append((f"⚠️ **{name}** hasn't loaded for {fails[host]} checks in a row, so the bot "
                                      f"can't see its stock right now. You'll get a post when it's back.", AMBER))
                if gap > 0:
                    retry[host] = round(time.time() + gap)
    status["shop_locked"] = sorted(locked & down)
    status["shop_down"] = sorted(down)
    return posts


# ---------------------------------------------------------------- state + alerts
def load_state():
    return read_json(STATE_PATH, {}) or {}


def save_state(state):
    atomic_write_json(STATE_PATH, state, indent=1, sort_keys=True)


def new_only(finds, state):
    """New = not seen in stock last time, or cheaper than last time."""
    out = []
    for f in finds:
        prev = state.get(f["id"])
        if prev is None or f["price"] < prev - 0.001:
            out.append(f)
    return out


def read_controls():
    return read_json(CONTROLS_PATH, {}) or {}


def _in_quiet_hours(spec, now=None):
    try:
        a, b = [datetime.strptime(x.strip(), "%H:%M").time() for x in str(spec).split("-")]
    except ValueError:
        return False
    t = (now or datetime.now()).time()
    return (a <= t < b) if a <= b else (t >= a or t < b)


def ping_allowed(cfg, finds, now=None):
    """@ping and phone push allowed right now? /mute silences everything; quiet hours silence all but boxes."""
    if float(read_controls().get("mute_until", 0) or 0) > time.time():
        return False
    alerts = cfg.get("alerts") or {}
    qh = alerts.get("quiet_hours")
    if qh and _in_quiet_hours(qh, now):
        boxes = any(f.get("kind") == "Booster box" for f in finds)
        return boxes and alerts.get("quiet_hours_ping_boxes", True)
    return True


def push_phone(cfg, title, body):
    topic = (cfg.get("alerts") or {}).get("ntfy_topic")
    if not topic or DRY_RUN[0]:
        return
    try:
        status, _, _ = HTTP.post(f"https://ntfy.sh/{urllib.parse.quote(topic)}", body.encode("utf-8"),
                                 {"Title": title.encode("latin-1", "replace").decode("latin-1")})
        if status >= 400:
            raise HttpError(status)
        print("   (sent to your phone via ntfy)")
    except Exception as e:  # noqa: BLE001
        print(f"   ! phone alert failed: {e}")


_hook_pace = {}            # webhook -> earliest time the next post may go (from Discord's rate-limit headers)
_buttons_ok = [True]


def _hook_url(hook, components=False):
    sep = "&" if "?" in hook else "?"
    return f"{hook}{sep}wait=true" + ("&with_components=true" if components else "")


def discord_send(alerts, hook, payload, tries=3):
    """One webhook message. Waits out Discord's rate limits, retries its server errors, and returns True
    only once Discord confirms the message was saved (?wait=true)."""
    comps = bool(payload.get("components")) and _buttons_ok[0]
    if not comps:
        payload = {k: v for k, v in payload.items() if k != "components"}
    last = None
    for attempt in range(tries):
        wait = _hook_pace.get(hook, 0) - time.time()
        if wait > 0:
            time.sleep(min(wait, 10))
        try:
            status, h, body = HTTP.post(_hook_url(hook, comps), json.dumps(payload).encode("utf-8"),
                                        {"Content-Type": "application/json"})
        except (OSError, http.client.HTTPException, ssl.SSLError) as e:
            last = e
            time.sleep(1.0 + attempt)
            continue
        if h.get("x-ratelimit-remaining") == "0" and h.get("x-ratelimit-reset-after"):
            try:
                _hook_pace[hook] = time.time() + float(h["x-ratelimit-reset-after"])
            except ValueError:
                pass
        if 200 <= status < 300:
            return True
        if status == 429:
            ra = _retry_after(h, body) or 1.0
            last = f"rate limited for {ra:.1f}s"
            if ra > 60:
                break
            time.sleep(ra + 0.05)
            continue
        if status == 400 and comps:            # buttons not accepted on this webhook: plain message
            _buttons_ok[0] = comps = False
            payload = {k: v for k, v in payload.items() if k != "components"}
            last = "HTTP 400 with buttons"
            continue
        if status >= 500:
            last = f"HTTP {status}"
            time.sleep(1.5 * (attempt + 1))
            continue
        last = f"HTTP {status}: {body[:200].decode('utf-8', 'replace')}"
        if status == 404:
            last += " (this webhook was deleted - make a new one)"
        break
    print(f"   ! Discord post failed: {redact(last)}")
    return False


EMBED_BUDGET = 5600       # Discord allows 6000 characters across a message's embeds; keep a margin
MAX_MESSAGES = 6          # per channel per check; anything past that is summed up in the last one


def _embed_size(e):
    return len(json.dumps(e, ensure_ascii=False))


def _chunks(items):
    """[(embed, ids)] -> messages of at most 10 embeds and EMBED_BUDGET characters."""
    out, cur, size = [], [], 0
    for e, ids in items:
        n = _embed_size(e)
        if cur and (len(cur) == 10 or size + n > EMBED_BUDGET):
            out.append(cur)
            cur, size = [], 0
        cur.append((e, ids))
        size += n
    if cur:
        out.append(cur)
    return out


def push_discord(cfg, title, body, finds=None, ping=True):
    """Post to Discord through webhook URLs. Boxes and new listings go to the boxes channel,
    singles to the singles channel. True if everything was delivered."""
    return push_discord_detailed(cfg, title, body, finds, ping)[0]


def push_discord_detailed(cfg, title, body, finds=None, ping=True):
    """Like push_discord, and also returns the set of find ids Discord confirmed. Pokémon finds go to
    their release's channel (or the catch-all Pokémon channel); with no Pokémon channels set up yet they
    aren't posted anywhere and count as done, so they aren't retried every check."""
    alerts = cfg.get("alerts") or {}
    default = alerts.get("discord_webhook")
    boxes_hook = alerts.get("discord_webhook_boxes") or default
    singles_hook = alerts.get("discord_webhook_singles") or default
    sealed_hook = alerts.get("discord_webhook_sealed") or boxes_hook
    ebay_hook = alerts.get("discord_webhook_ebay") or singles_hook   # eBay resale finds: their own channel if set up
    poke_hooks = pokemon_watch.hooks(alerts) if pokemon_watch else {}
    if not (default or boxes_hook or singles_hook or poke_hooks):
        return False, set()
    if finds is None:  # test message: post to every channel that's set up
        ok = True
        for hook in dict.fromkeys(h for h in (boxes_hook, singles_hook, sealed_hook, ebay_hook, default) if h):
            ok = _discord_post(alerts, hook, title, [{"title": title[:256], "description": body[:4000],
                                                       "color": 0x2A9D8F}], 0) and ok
        for hook in dict.fromkeys(poke_hooks.values()):
            ok = discord_send(alerts, hook, {"username": pokemon_watch.bot_name(alerts), "allowed_mentions": {"parse": []},
                                             "embeds": [{"title": title[:256], "description": body[:4000],
                                                         "color": pokemon_watch.YELLOW}]}) and ok
        return ok, set()
    groups, poke_group, delivered = {}, set(), set()
    for f in finds:
        if f.get("game") == POKE:
            hook = pokemon_watch.hook_for(alerts, f.get("section")) if pokemon_watch else None
            if not hook:
                delivered.add(f["id"])        # no Pokémon channel yet: nowhere to post it, so don't retry it
                continue
            poke_group.add(hook)
        elif f.get("ebay"):
            hook = ebay_hook                 # eBay watch (ebay_watch.json): Nike TNs, promos, graded cards
        elif f["kind"] == "Sealed" or (f["kind"] == "New listing" and f.get("group") == "watch"):
            hook = sealed_hook               # other sealed products: their own channel if set up
        elif f["kind"] in BOX_KINDS:
            hook = boxes_hook
        else:
            hook = singles_hook
        if hook:
            groups.setdefault(hook, []).append(f)
    ok = True
    for hook, group in groups.items():
        n_box = sum(1 for f in group if f["kind"] == "Booster box")
        n_new = sum(1 for f in group if f["kind"] == "New listing")
        is_poke = hook in poke_group
        if is_poke:
            t = f"⚡ {len(group)} new Pokémon find(s)" + (f", {n_new} new listing(s)" if n_new else "")
        else:
            t = f"{len(group)} new find(s)" + (f", {n_box} box(es)" if n_box else "") + \
                (f", {n_new} new listing(s)" if n_new else "")
        role = pokemon_watch.ping(alerts) if is_poke else alerts.get("discord_ping", "")
        username = pokemon_watch.bot_name(alerts) if is_poke else (alerts.get("bot_name") or "One Piece Restock")
        items = [(e, {f["id"]}) for e, f in zip(_discord_embeds(group, cfg), group)]
        carts = combined_carts(group)
        if carts:     # the one-cart links go first: they're the quickest way to buy the lot
            items = [(_cart_embed(c), set()) for c in carts] + items
        msgs = _chunks(items)
        overflow = msgs[MAX_MESSAGES:]
        msgs = msgs[:MAX_MESSAGES]
        for i, msg in enumerate(msgs):
            more = sum(len(m) for m in overflow) if i == len(msgs) - 1 else 0
            label = t + (f" ({i + 1}/{len(msgs)})" if len(msgs) > 1 else "")
            if more:
                label += f" (+{more} more - see {'/pokemon stock' if is_poke else '/deals'})"
            content = ((role + " ") if (ping and i == 0 and role) else "") + label
            payload = {"username": username, "content": content.strip()[:2000],
                       "embeds": [e for e, _ in msg],
                       "allowed_mentions": {"parse": ["roles", "users", "everyone"]} if (ping and i == 0) else {"parse": []}}
            if len(msg) == 1:            # a single find gets big tap-friendly buttons
                f = next((x for x in group if x["id"] in msg[0][1]), None)
                if f and f.get("cart"):
                    payload["components"] = [{"type": 1, "components": [
                        {"type": 2, "style": 5, "label": "⚡ Buy now", "url": f["cart"][:512]},
                        {"type": 2, "style": 5, "label": "Open listing", "url": (f.get("url") or f["cart"])[:512]}]}]
            if discord_send(alerts, hook, payload):
                for _, ids in msg:
                    delivered |= ids
                if more:
                    for m in overflow:
                        for _, ids in m:
                            delivered |= ids     # summed up in the label; don't retry them forever
                print("   (posted to Discord)")
            else:
                ok = False
    return ok, delivered


def combined_carts(finds):
    """One Shopify cart per shop holding the cheapest in-stock copy of each wanted single there,
    so you can buy them all in one order (one shipping fee). Only shops with 2+ different cards."""
    best = {}
    for f in finds:
        if f.get("kind") != "Single" or f.get("value_pick"):
            continue
        m = re.match(r"(https?://[^/]+)/cart/(\d+):(\d+)$", f.get("cart") or "")
        if not m:
            continue
        key = (f["shop"], m.group(1), f["name"])
        if key not in best or f["price"] < best[key][0]["price"]:
            best[key] = (f, m.group(2), int(m.group(3)))
    by_shop = {}
    for (shop, base, _), (f, vid, qty) in best.items():
        by_shop.setdefault((shop, base), []).append((f, vid, qty))
    out = []
    for (shop, base), items in by_shop.items():
        if len(items) < 2:
            continue
        items.sort(key=lambda x: (not x[0].get("priority"), x[0]["name"]))
        out.append({"shop": shop, "link": f"{base}/cart/" + ",".join(f"{vid}:{qty}" for _, vid, qty in items),
                    "n": len(items), "total": sum(f["price"] * qty for f, _, qty in items),
                    "names": [f"{f['name']} x{qty}" for f, _, qty in items]})
    return out


def _cart_embed(c):
    return {"title": f"🧺 One cart at {c['shop']}: {c['n']} cards, {money(c['total'])}"[:256], "url": c["link"],
            "color": 0x2A9D8F, "description": ("Cheapest in-stock copy of each, quantities from your want list, "
                                               "all in one checkout (one shipping fee).\n" + "\n".join(c["names"]))[:2000],
            "fields": [{"name": "⚡ Buy", "value": f"[Add them all to cart → checkout]({c['link']})", "inline": False}]}


def _discord_embeds(finds, cfg=None):
    embeds = []
    hist = None
    for f in finds:
        kind = f["kind"]
        fields = [{"name": "Price", "value": price_label(f) if f.get("price") else "not set yet", "inline": True},
                  {"name": "Shop", "value": f["shop"], "inline": True}]
        poke = f.get("game") == POKE and pokemon_watch
        if poke:
            p_icon, p_color, p_fields = pokemon_watch.embed_extras(f)
            fields += p_fields
        if kind == "Single":
            fields.append({"name": "Want", "value": f"x{f['qty']}" + (f" ({f['deck']})" if f.get("deck") else ""),
                           "inline": True})
        if kind in ("Booster box", "Sealed"):
            hist = read_json(HISTORY_PATH, {}) if hist is None else hist
            low = lowest_seen(hist, f["id"])
            if low:
                tag = " (today's price is the lowest yet)" if f["price"] <= low[0] + 0.001 else ""
                fields.append({"name": "Lowest seen", "value": f"{money(low[0])} on {low[1]}{tag}", "inline": True})
        if f.get("cart"):
            qty = f" (x{f['qty']})" if kind == "Single" and f.get("qty", 1) > 1 else ""
            fields.append({"name": "⚡ Buy", "value": f"[Add to cart → checkout{qty}]({f['cart']})", "inline": False})
        if f.get("note"):
            fields.append({"name": "Status" if kind == "New listing" else "Listing",
                           "value": str(f["note"])[:1000], "inline": False})
        if poke:
            icon, color = (("🆕 " if kind == "New listing" else "") + p_icon + " "), p_color
        elif kind == "Booster box":
            icon, color = "📦 ", 0xF4A261
        elif kind == "Sealed":
            icon, color = "🎁 ", 0x2A9D8F
        elif kind == "New listing":
            icon, color = "🆕 ", 0x9B5DE5
        elif f.get("value_pick"):
            icon, color = "💎 Value pick: ", 0x9B5DE5
        else:
            icon, color = ("⭐ ", 0xE63946) if f.get("priority") else ("🃏 ", 0x457B9D)
        embeds.append({"title": (icon + f["name"])[:256], "url": f["url"], "color": color, "fields": fields})
    return embeds


def _discord_post(alerts, hook, title, embeds, extra):
    content = alerts.get("discord_ping", "") + (f" {title}" if title else "")
    if extra > 0:
        content += f" (+{extra} more, see finds.log)"
    payload = {"username": alerts.get("bot_name") or "One Piece Restock",
               "content": content.strip()[:2000], "embeds": embeds[:10],
               "allowed_mentions": {"parse": ["roles", "users", "everyone"]}}
    ok = discord_send(alerts, hook, payload)
    if ok:
        print("   (posted to Discord)")
    return ok


def desktop_beep():
    if DRY_RUN[0]:
        return
    try:
        if sys.platform.startswith("win"):
            import winsound
            winsound.MessageBeep()
        else:
            print("\a", end="", flush=True)
    except Exception:  # noqa: BLE001
        pass


def best_single_shop(finds):
    by = {}
    for f in finds:
        if f["kind"] == "Single":
            by.setdefault(f["shop"], set()).add(f["name"])
    if not by:
        return None
    shop, names = max(by.items(), key=lambda kv: len(kv[1]))
    return shop, len(names)


def report(finds, label):
    poke = [f for f in finds if f.get("game") == POKE]
    finds = [f for f in finds if f.get("game") != POKE]
    boxes = [f for f in finds if f["kind"] == "Booster box"]
    sealed = [f for f in finds if f["kind"] == "Sealed"]
    listed = [f for f in finds if f["kind"] == "New listing"]
    singles = sorted([f for f in finds if f["kind"] == "Single"],
                     key=lambda f: (not f.get("priority"), f["name"], f["price"]))
    lines = []
    if boxes:
        lines.append("BOOSTER BOXES")
        for f in sorted(boxes, key=lambda f: f["price"]):
            lines.append(f"  {f['name']}  {money(f['price'])}  @ {f['shop']} {f['note']}".rstrip())
            lines.append(f"    {f['url']}")
            if f.get("cart"):
                lines.append(f"    BUY: {f['cart']}")
    if sealed:
        lines.append("OTHER SEALED")
        for f in sorted(sealed, key=lambda f: f["price"]):
            lines.append(f"  {f['name']}  {money(f['price'])}  @ {f['shop']}  ({f['note']})")
            lines.append(f"    {f['url']}")
            if f.get("cart"):
                lines.append(f"    BUY: {f['cart']}")
    if listed:
        lines.append("NEW LISTINGS")
        for f in listed:
            lines.append(f"  {f['name']}  {money(f['price'])}  @ {f['shop']}  ({f['note']})")
            lines.append(f"    {f['url']}")
            if f.get("cart"):
                lines.append(f"    BUY: {f['cart']}")
    if singles:
        lines.append("SINGLES")
        for f in singles:
            star = "*" if f.get("priority") else " "
            deck = f" [{f['deck']}]" if f.get("deck") else ""
            lines.append(f" {star}{f['name']} x{f['qty']}{deck}  {price_label(f)}  @ {f['shop']}")
            lines.append(f"    {f['url']}")
            if f.get("cart"):
                lines.append(f"    BUY: {f['cart']}")
        b = best_single_shop(singles)
        carts = {c["shop"]: c for c in combined_carts(singles)}
        if b and b[1] > 1:
            tip = f"  Tip: {b[0]} has {b[1]} of these cards - one order saves shipping."
            if b[0] in carts:
                tip += f"\n    ONE CART ({money(carts[b[0]]['total'])}): {carts[b[0]]['link']}"
            lines.append(tip)
    if poke:
        lines.append("POKÉMON")
        for f in sorted(poke, key=lambda f: (f.get("section_name", ""), f["kind"] == "New listing", f["price"])):
            tag = "NEW LISTING " if f["kind"] == "New listing" else ""
            lines.append(f"  [{f.get('section_name', '')}] {tag}{f['name']}  {money(f['price'])}  @ {f['shop']}"
                         + (f"  ({f['note']})" if f.get("note") else ""))
            lines.append(f"    {f['url']}")
            if f.get("cart"):
                lines.append(f"    BUY: {f['cart']}")
    if not lines:
        return f"{label}: nothing new in stock."
    return f"{label}:\n" + "\n".join(lines)


# ---------------------------------------------------------------- snapshot, price history, events
def write_snapshot(sealed=None, singles=None, metrics=None, pokemon=None):
    """latest.json: what the last check saw, so Discord commands can answer straight away."""
    if DRY_RUN[0]:
        return
    snap = read_json(SNAPSHOT_PATH, {}) or {}
    now = time.time()
    if sealed is not None:
        finds, by_shop = sealed
        snap["sealed"] = {"ts": now, "finds": finds,
                          "listings": [l for ls in by_shop.values() for l in (ls or [])],
                          "down": sorted(n for n, ls in by_shop.items() if ls is None)}
    if singles is not None:
        snap["singles"] = {"ts": now, "finds": singles}
    if pokemon is not None and pokemon.sections and not pokemon.problem:
        prev = snap.get("pokemon") or {}
        checked = set(pokemon.sections)          # a drop-mode check may cover just one release: keep the rest
        snap["pokemon"] = {"ts": now,
                           "finds": [f for f in prev.get("finds", []) if f.get("section") not in checked] + pokemon.finds,
                           "listings": [l for l in prev.get("listings", []) if l.get("section") not in checked]
                           + pokemon.all_listings(),
                           "down": sorted({shop for (shop, _), ls in pokemon.listings.items() if ls is None})}
    snap.update(version=2, ts=now, updated=f"{datetime.now():%Y-%m-%d %H:%M:%S}")
    if metrics:
        snap["metrics"] = metrics
    atomic_write_json(SNAPSHOT_PATH, snap, indent=None, ensure_ascii=False)


HISTORY_DAYS = 180


def lowest_seen(hist, key, days=90):
    """(price, 'DD Mon') of the lowest in-stock price in the last `days` days, or None."""
    h = (hist or {}).get(key)
    if not h:
        return None
    cutoff = f"{datetime.now() - timedelta(days=days):%Y-%m-%d}"
    pts = [p for p in h.get("points", []) if p[0] >= cutoff and p[2] and p[1] > 0]
    if not pts:
        return None
    p = min(pts, key=lambda p: (p[1], p[0]))
    return p[1], datetime.strptime(p[0], "%Y-%m-%d").strftime("%d %b")


def record_history(by_shop, now=None):
    """price_history.json: one point per listing per day ([date, price, in stock]) plus a line in
    events.jsonl whenever something comes into or goes out of stock."""
    if DRY_RUN[0] or not by_shop:
        return
    now = now or datetime.now()
    day, ts = f"{now:%Y-%m-%d}", round(time.time())
    hist = read_json(HISTORY_PATH, {}) or {}
    events, changed = [], False
    for listings in by_shop.values():
        for l in listings or []:
            key = l["box_id"]
            price, avail = round(float(l.get("price") or 0), 2), bool(l.get("available"))
            h = hist.get(key)
            if h is None:
                h = hist[key] = {"name": l["name"], "shop": l["shop"], "url": l["url"], "points": [],
                                 "avail": avail, "since": ts}
                changed = True
            elif h.get("avail") != avail:
                events.append({"t": ts, "event": "in_stock" if avail else "sold_out", "id": key, "name": l["name"],
                               "shop": l["shop"], "price": price, "was": round(ts - h.get("since", ts))})
                h["avail"], h["since"] = avail, ts
                changed = True
            pts = h["points"]
            if pts and pts[-1][0] == day:
                p = pts[-1]
                if avail and (not p[2] or price < p[1]):
                    p[1], p[2] = price, True
                    changed = True
                elif not avail and not p[2] and p[1] != price:
                    p[1] = price
                    changed = True
            else:
                pts.append([day, price, avail])
                del pts[:-400]
                changed = True
            if h.get("seen") != day:
                h["seen"] = day
                changed = True
    cutoff = f"{now - timedelta(days=HISTORY_DAYS):%Y-%m-%d}"
    for k in [k for k, h in hist.items() if h.get("seen", "") < cutoff]:
        hist.pop(k)
        changed = True
    if changed:
        atomic_write_json(HISTORY_PATH, hist, indent=None, ensure_ascii=False)
    log_events(events)


def log_events(events):
    if events and not DRY_RUN[0]:
        append_text(EVENTS_PATH, "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events), 2_000_000)


def read_events(days=30):
    cutoff = time.time() - days * 86400
    out = []
    for path in (EVENTS_PATH + ".1", EVENTS_PATH):
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if e.get("t", 0) >= cutoff:
                        out.append(e)
        except OSError:
            continue
    return out


# ---------------------------------------------------------------- daily recap
def _lines(items, limit=8):
    out = "\n".join(items[:limit])
    if len(items) > limit:
        out += f"\n…and {len(items) - limit} more"
    return out[:1020] or "-"


def _short(name, n=60):
    name = name or "(no name)"
    return name if len(name) <= n else name[:n - 1] + "…"


def link_text(name, n=60):
    """A shop title for inside a Discord [link](...): square brackets (Elemental's '[Romance Dawn]') become
    round ones, so a title cut short can't leave a stray '[' that breaks the link."""
    return _short(str(name or "").replace("[", "(").replace("]", ")"), n)


def run_recap(cfg, now=None, post=True, save=True):
    """One Discord post summing up the day: what's buyable within your limits, price moves and
    new listings since yesterday's recap, what's coming up, and shops that are down.
    Returns the embed (the /recap command replies with it instead of posting)."""
    now = now or datetime.now()
    print(f"\n=== Daily recap - {now:%a %d %b %Y %I:%M %p} ===")
    (box_finds, by_shop), singles, poke = run_checks_all(cfg, True, True,
                                                          bool(pokemon_watch and pokemon_watch.enabled(cfg)))
    if ebay_watch:
        singles += ebay_watch.check(cfg, {}, force=True).finds

    # today's snapshot: every box / watched listing (in stock or not) plus in-stock singles
    snap = {}
    for listings in by_shop.values():
        for l in listings or []:
            snap[l["id"]] = {"name": l["name"], "shop": l["shop"], "price": round(l["price"], 2),
                             "available": l["available"], "url": l["url"]}
    for f in singles:
        snap[f["id"]] = {"name": f["name"], "shop": f["shop"], "price": round(f["price"], 2),
                         "available": True, "url": f["url"]}
    prev_file = read_json(RECAP_PATH, None)
    if isinstance(prev_file, dict):
        prev = prev_file.get("snapshot", {})
    else:
        remote = repo_json(cfg, "recap.json")       # the PC copy compares with the cloud's last recap
        prev = remote.get("snapshot") if isinstance(remote, dict) else None

    fields = []
    # 1. buyable now within your limits
    order = {"Booster box": 0, "Sealed": 1, "Single": 2}
    buy = sorted(box_finds + singles, key=lambda f: (order[f["kind"]], not f.get("priority"), f["price"]))
    icon = {"Booster box": "📦", "Sealed": "🎁", "Single": "🃏"}
    lines = [f"{icon[f['kind']]} [{_short(f['name'])}]({f.get('cart') or f['url']}) **{price_label(f)}** · {f['shop']}"
             for f in buy]
    for c in combined_carts(singles):
        lines.insert(0, f"🧺 [One cart at {c['shop']}: {c['n']} cards]({c['link']}) **{money(c['total'])}**")
    fields.append({"name": f"🛒 Buyable now within your limits ({len(buy)})",
                   "value": _lines(lines) if lines else "Nothing on your list is in stock under your max right now."})
    if poke is not None and poke.sections and not poke.problem:
        pk = sorted(poke.finds, key=lambda f: (f.get("section_name", ""), f["price"]))
        pl = [f"{pokemon_watch.TYPE_ICON.get(f.get('ptype'), '⚡')} [{_short(f['name'])}]({f.get('cart') or f['url']}) "
              f"**{money(f['price'])}** · {f['shop']}" for f in pk]
        fields.append({"name": f"⚡ Pokémon within your max ({len(pl)})",
                       "value": _lines(pl, 6) if pl else "Nothing from the watched Pokémon releases is in stock at or "
                                                         "under your max right now."})

    # 2. price moves, restocks and new listings since the last recap
    if prev is not None:
        moves, back, new = [], [], []
        for k, v in snap.items():
            p = prev.get(k)
            if not p:
                new.append(f"[{_short(v['name'])}]({v['url']}) {money(v['price'])} · {v['shop']}")
                continue
            if v["available"] and not p.get("available"):
                back.append(f"[{_short(v['name'])}]({v['url']}) {money(v['price'])} · {v['shop']}")
            if p.get("price") and v["price"] and abs(v["price"] - p["price"]) >= 1:
                pct = (v["price"] - p["price"]) / p["price"] * 100
                if abs(pct) >= RECAP_MOVE_PCT:
                    moves.append((pct, f"{'📉' if pct < 0 else '📈'} [{_short(v['name'], 50)}]({v['url']}) "
                                       f"{money(p['price'])} → **{money(v['price'])}** ({pct:+.0f}%) · {v['shop']}"))
        moves.sort(key=lambda m: m[0])           # biggest drops first
        fields.append({"name": "💸 Price changes since yesterday",
                       "value": _lines([m[1] for m in moves]) if moves else "No moves of 5% or more."})
        if back:
            fields.append({"name": "🔁 Back in stock", "value": _lines(back)})
        if new:
            fields.append({"name": "🆕 Newly listed", "value": _lines(new)})
    else:
        fields.append({"name": "💸 Price changes", "value": "First recap: price changes start showing from tomorrow."})

    # 3. market value picks from the ledger, if they've been shared with the bot
    try:
        picks = load_picks_file(cfg) or {}
        if isinstance(picks, dict):
            picks = picks.get("picks", [])
        pl = [f"⭐ [{_short(x['name'])}]({x.get('url', '')}) **{money(float(x['price']))}** · {x.get('shop', '')}"
              + (f" · {x['note']}" if x.get("note") else "") for x in picks if x.get("name") and x.get("price")
              and not is_owned_pick(cfg, x.get("name"), x.get("url", ""))]
        if pl:
            fields.append({"name": "📊 Worth a look (vs US market)", "value": _lines(pl, 6)})
    except Exception:  # noqa: BLE001
        pass

    # 4. coming up: releases and drop windows in the next two weeks
    soon = []
    for r in cfg.get("releases", DEFAULT_RELEASES) or []:
        try:
            d = datetime.strptime(r["date"], "%Y-%m-%d")
        except (KeyError, ValueError, TypeError):
            continue
        days = (d.date() - now.date()).days
        if 0 <= days <= RECAP_DAYS_AHEAD:
            soon.append((d, f"📅 **{d:%a %d %b}** {r['name']}" + (" (today!)" if days == 0 else f" (in {days} days)")))
    if pokemon_watch:
        try:
            soon += pokemon_watch.short_calendar(cfg, now, RECAP_DAYS_AHEAD)
        except Exception as e:  # noqa: BLE001
            print(f"   ! Pokémon release dates skipped ({e})")
    for w in parse_windows(cfg):
        if now < w["end"] and (w["start"] - now).days <= RECAP_DAYS_AHEAD:
            soon.append((w["start"], f"🚨 Drop mode: {w['name']}, {w['start']:%a %d %b %I:%M %p}"))
    soon.sort(key=lambda x: x[0])
    fields.append({"name": f"🗓️ Next {RECAP_DAYS_AHEAD} days",
                   "value": _lines([x[1] for x in soon]) if soon else "No releases in the next two weeks."})

    # 5. shops the bot can't see
    down = load_status().get("shop_down", [])
    if down:
        names = shop_names(cfg)
        fields.append({"name": "⚠️ Not loading", "value": ", ".join(names.get(h, h) for h in down)})

    alerts = cfg.get("alerts") or {}
    ledger = alerts.get("ledger_url") or cfg.get("ledger_url")
    embed = {"title": f"☀️ Daily recap · {now:%A %d %B}", "color": 0xE9C46A, "fields": fields[:25]}
    if ledger:
        embed["description"] = f"Full market report (US prices, PSA, movers): [Grand Line Ledger]({ledger})"
        embed["url"] = ledger
    fit_embed(embed)
    hook = alerts.get("discord_webhook_recap") or alerts.get("discord_webhook_status") or \
        alerts.get("discord_webhook_boxes") or alerts.get("discord_webhook")
    for fld in fields:
        print(f"\n{fld['name']}\n{fld['value']}")
    if hook and post and not DRY_RUN[0]:
        payload = {"username": alerts.get("bot_name") or "One Piece Restock", "embeds": [embed],
                   "allowed_mentions": {"parse": []}}
        if discord_send(alerts, hook, payload):
            print("\n   (recap posted to Discord)")
        else:
            print("\n   ! recap post failed")
    if save:
        atomic_write_json(RECAP_PATH, {"date": f"{now:%Y-%m-%d}", "snapshot": snap}, indent=1)
        write_snapshot((box_finds, by_shop), singles, None, poke)
    return embed


EMBED_TOTAL_MAX = 5900          # Discord refuses an embed whose title + fields add up to more than 6,000 characters


def fit_embed(embed, limit=EMBED_TOTAL_MAX):
    """Shorten the longest field values (whole lines at a time) until the embed fits Discord's limit."""
    def size():
        return (len(embed.get("title", "")) + len(embed.get("description", ""))
                + sum(len(f["name"]) + len(f["value"]) for f in embed.get("fields", [])))
    while size() > limit:
        f = max(embed.get("fields", []), key=lambda f: len(f["value"]), default=None)
        if f is None or len(f["value"]) < 80:
            break
        lines = f["value"].split("\n")
        if len(lines) > 2:
            f["value"] = "\n".join(lines[:-2] + ["…"])
        else:
            f["value"] = f["value"][: len(f["value"]) // 2] + "…"
    return embed


# ---------------------------------------------------------------- main
IN_ACTIONS = bool(os.environ.get("GITHUB_ACTIONS"))


def run_once(cfg, args, drop=None):
    stamp = datetime.now().strftime("%a %d %b %Y %I:%M:%S %p")
    status = load_status()
    begin_check(cfg, status, drop, skip_down=not args.all)
    tag = f" [DROP MODE: {drop['name']}]" if drop else ""
    print(f"\n=== One Piece restock check - {stamp}{tag} ===")
    loop = getattr(args, "loop", None)
    only_poke = bool(getattr(args, "pokemon", False))
    games = set(drop.get("games") or [ONE_PIECE]) if drop else set()
    op_drop = drop if (drop and ONE_PIECE in games) else None      # a Pokémon-only window leaves One Piece alone
    do_sealed = not args.singles and not only_poke
    do_singles = not args.sealed and not only_poke and not (op_drop and op_drop["sealed_only"])
    if do_sealed and drop and not op_drop and loop and not args.all:
        # a Pokémon drop window runs the loop every minute: One Piece boxes stay at their normal pace
        if time.time() - float(status.get("sealed_ts", 0) or 0) < loop * 60 - 20:
            do_sealed = False
    every = _num(cfg.get("singles_every_minutes", SINGLES_EVERY_DEFAULT)) or 0
    if do_singles and not args.singles and every > 0 and loop and not args.all:
        if time.time() - float(status.get("singles_ts", 0) or 0) < every * 60 - 20:
            do_singles = False         # boxes this time; singles when they're due
    poke_on = bool(pokemon_watch) and not args.sealed and not args.singles and pokemon_watch.enabled(cfg)
    poke_only = None
    if poke_on and loop and not args.all:
        due = time.time() - float(status.get("pokemon_ts", 0) or 0) >= pokemon_watch.every_minutes(cfg) * 60 - 20
        if drop and POKE in games:
            if not due and drop.get("sections"):
                poke_only = set(drop["sections"])      # the releases out today every minute; the rest when due
        elif not due:
            poke_on = False
    if do_sealed:
        print(" checking booster boxes...")
    if do_singles:
        print(" checking singles...")
    if poke_on:
        print(" checking Pokémon..." + (f" ({', '.join(sorted(poke_only))})" if poke_only else ""))
    sealed_res, singles, poke = run_checks_all(cfg, do_sealed, do_singles, poke_on, poke_only)
    finds, listed, known = [], [], None
    box_finds, by_shop = sealed_res if sealed_res else ([], {})
    finds += box_finds
    if do_sealed and loop:
        status["sealed_ts"] = round(time.time())
    if do_sealed and cfg.get("new_listings", True):
        known = load_known()
        listed = new_listings(by_shop, known, box_finds, status.setdefault("pages_seen", {}))
    alerts = cfg.get("alerts") or {}
    poke_ok, poke_secs, poke_shops, intro = set(), set(), set(), []
    if poke is not None and not poke.problem:
        poke_ok = poke.ok_pairs
        poke_secs = set(poke.sections)
        poke_shops = {shop for shop, _ in poke.listings}    # every shop asked, whether it answered or not
        finds += poke.finds
        if cfg.get("new_listings", True):
            known = load_known() if known is None else known
            listed += pokemon_watch.new_listings(poke, known, {f["id"] for f in poke.finds})
        if loop and poke_only is None:
            status["pokemon_ts"] = round(time.time())
        if not args.all:
            # a release channel that's just been set up gets one post listing everything the shops have,
            # instead of a separate alert for each of them (by the PC copy; the cloud copy just notes it)
            intro = pokemon_watch.intro_posts(cfg, poke, status, alerts)
            if heartbeat_role(cfg) == "listen":
                for slug, _, _ in intro:
                    pokemon_watch.mark_intro(status, slug)
                intro = []
    ebay = None
    if do_singles:
        finds += singles
        if loop:
            status["singles_ts"] = round(time.time())
        if ebay_watch:
            ebay = ebay_watch.check(cfg, status, force=args.all)
            finds += ebay.finds

    state = load_state()
    show = finds if args.all else new_only(finds, state)
    show = show + listed
    if intro:
        new_sections = {slug for slug, _, _ in intro}
        show = [f for f in show if not (f.get("game") == POKE and f.get("section") in new_sections)]
    text = report(show, "Everything currently matching" if args.all else "New since last check")
    print("\n" + text)

    # remember what's in stock now (items that sold out drop off, so a restock counts as new).
    # Keep entries for whatever this run didn't check (e.g. singles during drop mode, a shop that failed).
    checked = {"Booster box"} if do_sealed else set()
    if do_singles:
        checked.add("Single")

    def forget(k):
        if k.startswith(("box|", "sealed|")):
            return "Booster box" in checked
        if k.startswith("card|"):
            return "Single" in checked
        if k.startswith("ebay|"):
            return ebay is not None and ebay.ran
        if k.startswith("poke|"):
            parts = k.split("|", 3)
            if len(parts) != 4:
                return False
            slug, shop = parts[1], parts[2]
            # checked just now, or a shop that's no longer on the Pokémon list
            return (shop, slug) in poke_ok or (slug in poke_secs and shop not in poke_shops)
        return False

    kept = {k: v for k, v in state.items() if not forget(k)}
    kept.update({f["id"]: f["price"] for f in finds})

    role = heartbeat_role(cfg)
    pc_seen = pc_last_seen(cfg) if role == "listen" else None
    pc_on = pc_seen is not None
    pc_poke = pc_on and PC_INFO["pokemon"]        # the PC copy says it posts Pokémon alerts itself
    poke_live = bool(pokemon_watch and pokemon_watch.hooks(alerts))

    def pc_does(f):
        """Cloud copy: the PC copy is on and posts this one itself."""
        return pc_on and (f.get("game") != POKE or pc_poke)

    # status posts: shop health, and (cloud copy) the PC going quiet or coming back
    if not IN_ACTIONS:         # the cloud copy commits status.json; keep it free of per-run noise
        status["last_check"] = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
        status["last_found"] = len(finds)
    posts = shop_health(cfg, status)
    if ebay_watch:
        msg = ebay_watch.status_message(status, ebay)
        if msg:
            posts.append(msg)
    if poke is not None:
        posts += pokemon_status_posts(cfg, status, poke)
    if role == "listen":
        before = status.get("pc_on")
        if before is True and not pc_on:
            posts.append(("🖥️ Your PC copy has gone quiet (off or asleep). The **cloud copy** is posting alerts now.", BLUE))
        elif before is False and pc_on:
            post_status(cfg, "🖥️ Your PC copy is back on and posting alerts. The cloud copy is going quiet.", BLUE)
        status["pc_on"] = pc_on
    if not pc_on:            # while the PC is on, it reports these itself
        for msg, color in posts:
            post_status(cfg, msg, color)
    if CONFIG_WARNINGS:
        print("   ! config.json: " + "; ".join(CONFIG_WARNINGS))
    if do_singles:
        try:            # the 6-hourly price drops: never let them get in the way of restock alerts
            drops = run_price_drops(cfg, status, show_all=args.all, role=role, pc_on=pc_on)
            if args.all and drops is not None:
                ds = drops_settings(cfg)
                print("\n" + drops_report(drops, ds["every_hours"], ds["min_pct"]))
        except Exception as e:  # noqa: BLE001
            print(f"   ! price drops skipped this check ({redact(e)})")
    poke_posted = pokemon_posts(cfg, status, intro, role, pc_poke) if not args.all else []

    deliver, from_held = [], False
    if show and not args.all:
        deliver = [f for f in show if not pc_does(f)]
        if len(deliver) < len(show):
            print("   (your PC copy is on and posts these itself - cloud copy staying quiet)")
    if role == "listen":
        # Hold what we saw while the PC was on. Once the PC checks in after we first saw something,
        # it has posted it. If the PC goes quiet first, post what it may have missed.
        held = status.get("held") or {}
        nowts = time.time()
        for f in show if not args.all else []:
            if pc_does(f):
                held.setdefault(f["id"], {"t": int(nowts), "f": f})
        in_stock = {f["id"] for f in finds}
        looked = {"Single": do_singles, "Booster box": do_sealed, "Sealed": do_sealed}

        def was_looked(f):
            if f.get("game") == POKE:
                return (f.get("shop"), f.get("section")) in poke_ok and f.get("kind") != "New listing"
            return looked.get(f.get("kind"), False)

        for k, v in list(held.items()):
            f = v.get("f") or {}
            if v.get("t", 0) <= (pc_seen or 0) or nowts - v.get("t", 0) > 6 * 3600 or \
                    (was_looked(f) and k not in in_stock):
                held.pop(k)
        have = {f["id"] for f in deliver}
        extra = [v["f"] for k, v in held.items() if k not in have and not pc_does(v.get("f") or {})]
        deliver += extra
        from_held = bool(extra)
        status["held"] = held
    if not poke_live and deliver:
        # no Pokémon channels yet: remembered as seen, but not posted, pushed or logged anywhere
        deliver = [f for f in deliver if f.get("game") != POKE]

    undelivered = set()
    if deliver and not args.all:
        desktop_beep()
        dtext = text if deliver == show else report(deliver, "New since the PC copy went quiet" if from_held
                                                    else "New since last check")
        append_text(LOG_PATH, f"\n--- {stamp} ---\n{dtext}\n")
        title = finds_title(deliver)
        ping = ping_allowed(cfg, deliver)
        if ping:
            push_phone(cfg, title, dtext[:3500])
        # boxes first, then new listings, then priority singles, so the important ones fill the first message
        order = {"Booster box": 0, "Sealed": 1, "New listing": 2, "Single": 3}
        ordered = sorted(deliver, key=lambda f: (order.get(f["kind"], 4), not f.get("priority"), f["price"]))
        if (any(alerts.get(k) for k in ("discord_webhook", "discord_webhook_boxes", "discord_webhook_singles"))
                or (pokemon_watch and pokemon_watch.hooks(alerts))) and not DRY_RUN[0]:
            _, delivered = push_discord_detailed(cfg, title, dtext, ordered, ping=ping)
            undelivered = {f["id"] for f in ordered} - delivered
        if role == "listen":
            for f in deliver:
                if f["id"] not in undelivered:
                    status.get("held", {}).pop(f["id"], None)
    if role == "send":
        send_heartbeat(cfg, force=(bool(deliver) and not undelivered) or bool(poke_posted), status=status)
    if undelivered:
        # not marked as seen, so the next check tries again (a doubled alert beats a missed one)
        for k in undelivered:
            kept.pop(k, None)
        if known is not None:
            for f in deliver:
                if f["id"] in undelivered and f["kind"] == "New listing":
                    keys = ((pokemon_watch.known_key(f["shop"], f.get("section")),) if f.get("game") == POKE
                            else (f["shop"], f"{f['shop']} (other sealed)"))
                    for shop in keys:
                        if shop in known and f["id"] in known[shop]:
                            known[shop].remove(f["id"])
        print(f"   ! {len(undelivered)} alert(s) didn't reach Discord - they'll go out next check")

    metrics = run_metrics()
    if not DRY_RUN[0]:
        save_state(kept)
        if known is not None:
            save_known(known)
        status["robots"] = {h: e for h, e in HTTP.robots.items() if time.time() - e.get("t", 0) < 7 * 86400}
        status["page_hints"] = {u: n for u, n in PAGE_HINTS.items() if n > 1}
        if not IN_ACTIONS:
            status["last_run"] = metrics
        save_status(status)
        write_snapshot(sealed_res if do_sealed else None, singles if do_singles else None, metrics, poke)
        if cfg.get("history", True):
            hist_src = dict(by_shop) if do_sealed else {}
            if poke is not None and not poke.problem:
                for (shop, slug), ls in poke.listings.items():
                    hist_src[f"pokemon|{shop}|{slug}"] = ls
            if hist_src:
                record_history(hist_src)
    print(f"   (checked in {metrics['secs']:.1f}s · {metrics['requests']} requests, "
          f"{metrics['new_connections']} new connections, {metrics['kb_wire']} KB"
          + (f", skipped {len(metrics['skipped_hosts'])} down shop(s)" if metrics["skipped_hosts"] else "") + ")")


def finds_title(finds):
    """'One Piece: 2 new find(s), 1 box(es) · Pokémon: 3 new' for the phone push and the log."""
    op = [f for f in finds if f.get("game") != POKE]
    pk = [f for f in finds if f.get("game") == POKE]
    parts = []
    if op:
        n_box = sum(1 for f in op if f["kind"] in ("Booster box", "Sealed"))
        n_new = sum(1 for f in op if f["kind"] == "New listing")
        parts.append(f"One Piece: {len(op)} new find(s)" + (f", {n_box} box(es)" if n_box else "")
                     + (f", {n_new} new listing(s)" if n_new else ""))
    if pk:
        n_new = sum(1 for f in pk if f["kind"] == "New listing")
        parts.append(f"Pokémon: {len(pk)} new" + (f" ({n_new} new listing(s))" if n_new else ""))
    return " · ".join(parts) or "No new finds"


def pokemon_status_posts(cfg, status, poke):
    """(text, colour) status posts about the Pokémon watch: on (quietly, or live) and problems."""
    posts = []
    alerts = cfg.get("alerts") or {}
    prob = poke.problem or ""
    if prob != status.get("pokemon_problem", ""):
        if prob:
            posts.append((f"⚠️ **The Pokémon check hit a snag**, so Pokémon is skipped until it's sorted (One Piece "
                          f"checks carry on): `{redact(prob)[:250]}`", AMBER))
        elif status.get("pokemon_problem"):
            posts.append(("✅ The Pokémon check is working again.", GREEN))
        status["pokemon_problem"] = prob
    if prob or not poke.sections:
        return posts
    live = bool(pokemon_watch.hooks(alerts))
    now_state = "live" if live else "quiet"
    if status.get("pokemon_state") != now_state:
        status["pokemon_state"] = now_state
        pc = pokemon_watch.settings(cfg)
        names = ", ".join(s["name"] for s in pc["sections"] if s["enabled"] and s["queries"])
        n = len(pokemon_watch.shops(cfg, _me(), pc))
        if live:
            posts.append((f"⚡ **Pokémon alerts are live**: {names} at {n} shops. New listings, pre-orders and stock "
                          f"at or under your max go to each release's channel; release-day posts go to "
                          f"#pokemon-in-store.", GREEN))
        else:
            posts.append((f"⚡ **Pokémon watch is on, quietly.** It's checking {n} shops for {names}, but won't post "
                          f"anything until the Pokémon channels exist. Set them up with `/pokemon setup` in Discord "
                          f"(or add_pokemon_channels.bat on the PC).", BLUE))
    return posts


def pokemon_posts(cfg, status, intro, role=None, pc_posts_pokemon=False):
    """Release-day posts in #pokemon-in-store, and the first post in a newly set-up release channel
    (intro is always empty on the cloud copy). Returns the keys of the release-day posts made.

    Hand-off between the copies: the PC copy says in its "I'm on" message which release-day posts it
    made; the cloud copy marks those as done, waits while the PC copy posts Pokémon itself, and posts
    them when the PC is off. The PC copy skips any the cloud copy already posted (the repo's status.json)."""
    if not pokemon_watch:
        return []
    alerts = cfg.get("alerts") or {}
    name = pokemon_watch.bot_name(alerts)
    for slug, hook, emb in intro:
        if DRY_RUN[0]:
            print(f"   [dry run] would post the first {slug} channel post: {emb['title']}")
        elif discord_send(alerts, hook, {"username": name, "embeds": [emb], "allowed_mentions": {"parse": []}}):
            pokemon_watch.mark_intro(status, slug)
    try:
        due = pokemon_watch.reminders_due(cfg, status)
    except Exception as e:  # noqa: BLE001
        print(f"   ! Pokémon release-day posts skipped ({e})")
        return []
    if not due:
        return []
    hook = pokemon_watch.instore_hook(alerts)
    if not hook:
        return []           # no Pokémon channel yet: it goes out once there is one, if it's still that day
    if role == "listen":
        done = PC_INFO["posted"]
        if pc_posts_pokemon:
            done = done | {r["key"] for r in due}       # the PC copy is on and posts them
    elif role == "send":
        remote = repo_json(cfg, "status.json", max_age=300)
        done = remote.get("pokemon_reminders") if isinstance(remote, dict) else None
        done = set(done) if isinstance(done, dict) else set()
    else:
        done = set()
    posted = []
    for r in due:
        if r["key"] in done:
            if role != "listen" or r["key"] in PC_INFO["posted"]:
                pokemon_watch.mark_sent(status, r["key"])   # the other copy posted it
            continue
        ping = pokemon_watch.ping(alerts) if (r["ping"] and ping_allowed(cfg, [])) else ""
        if DRY_RUN[0]:
            print(f"   [dry run] would post in #pokemon-in-store: {r['embed']['title']}" + (" (with ping)" if ping else ""))
            continue
        payload = {"username": name, "content": ping, "embeds": [r["embed"]],
                   "allowed_mentions": {"parse": ["roles"]} if ping else {"parse": []}}
        if discord_send(alerts, hook, payload):
            pokemon_watch.mark_sent(status, r["key"])
            posted.append(r["key"])
            print(f"   (posted in #pokemon-in-store: {r['embed']['title']})")
    return posted


def self_test(cfg):
    """Quick health check before going live: config, file access, one shop, alert settings."""
    ok = True
    print(f"One Piece restock bot v{VERSION} self-test\n")
    print("config.json:", "OK" if not CONFIG_WARNINGS else "")
    for w in CONFIG_WARNINGS:
        print("   !", w)
    try:
        probe = os.path.join(HERE, ".write-test.json")
        atomic_write_json(probe, {"ok": True})
        os.remove(probe)
        print("files: OK (can save state next to the bot)")
    except OSError as e:
        ok = False
        print(f"files: CAN'T WRITE in {HERE} ({e})")
    cols = sealed_shops(cfg)[0]
    if cols:
        t0 = time.perf_counter()
        products, _ = shopify_collection(cols[0]["url"], max_pages=1)
        ms = (time.perf_counter() - t0) * 1000
        if products is None:
            ok = False
            print(f"network: couldn't read {cols[0]['name']}")
        else:
            print(f"network: OK ({cols[0]['name']}: {len(products)} products in {ms:.0f} ms)")
    alerts = cfg.get("alerts") or {}
    hooks = [k for k in alerts if k.startswith("discord_webhook") and alerts[k]]
    print("discord:", ", ".join(hooks) if hooks else "no webhooks set (finds are only printed)")
    if pokemon_watch:
        pc = pokemon_watch.settings(cfg)
        secs = [s["name"] for s in pc["sections"] if s["enabled"] and s["queries"]]
        ph = pokemon_watch.hooks(alerts)
        print(f"pokemon: {'on' if pc['enabled'] and secs else 'off'} · {', '.join(secs) or 'no releases to search'} · "
              f"{len(pokemon_watch.shops(cfg, _me(), pc))} shops · "
              + (f"channels: {', '.join(ph)}" if ph else "no Pokémon channels yet (quiet: run add_pokemon_channels.bat)"))
    else:
        print("pokemon: off (pokemon_watch.py isn't next to the bot)")
    print("\nPASS" if ok else "\nFAIL")
    return ok


def main():
    # Windows writes bot_output in an old encoding that has no emoji; don't let that crash the bot
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=f"One Piece TCG restock bot v{VERSION}")
    ap.add_argument("--all", action="store_true", help="show everything matching, not just new finds")
    ap.add_argument("--loop", type=float, metavar="MINUTES", help="keep checking every N minutes")
    ap.add_argument("--sealed", action="store_true", help="only booster boxes")
    ap.add_argument("--singles", action="store_true", help="only singles")
    ap.add_argument("--pokemon", action="store_true", help="only Pokémon")
    ap.add_argument("--test-discord", action="store_true", help="post a test message to Discord and stop")
    ap.add_argument("--recap", action="store_true", help="post the daily recap to Discord and stop")
    ap.add_argument("--dry-run", action="store_true", help="check and print, but post and save nothing")
    ap.add_argument("--self-test", action="store_true", help="check config, files and one shop, then stop")
    args = ap.parse_args()
    DRY_RUN[0] = args.dry_run

    try:
        cfg = load_config()
    except FileNotFoundError:
        sys.exit(f"config.json not found next to {os.path.basename(__file__)}")
    except json.JSONDecodeError as e:
        sys.exit(f"config.json has a typo: {e}")

    if args.self_test:
        sys.exit(0 if self_test(cfg) else 1)

    if args.test_discord:
        alerts = cfg.get("alerts") or {}
        if not any(alerts.get(k) for k in ("discord_webhook", "discord_webhook_boxes", "discord_webhook_singles")) \
                and not (pokemon_watch and pokemon_watch.hooks(alerts)):
            sys.exit('No "discord_webhook" in the "alerts" section of config.json yet.')
        ok = push_discord(cfg, "Test from your One Piece restock bot",
                          "If you can see this, Discord alerts are working.")
        sys.exit(0 if ok else 1)

    if args.recap:
        begin_check(cfg)
        run_recap(cfg)
        return

    if not args.loop:
        run_once(cfg, args)
        return
    print(f"Running every {args.loop:g} minutes (faster inside drop windows). Press Ctrl+C to stop.")
    every = f"{args.loop:g} minute" + ("" if args.loop == 1 else "s")
    windows = [w for w in parse_windows(cfg) if w["end"] > datetime.now()]
    nxt = f" Next drop window: **{windows[0]['name']}**, {windows[0]['start']:%a %d %b %I:%M %p}." if windows else ""
    poke = ""
    if pokemon_watch and pokemon_watch.enabled(cfg):
        poke = f" Pokémon every {pokemon_watch.every_minutes(cfg):g} minutes."
    post_status(cfg, f"🟢 **Bot online** ({'PC' if heartbeat_role(cfg) != 'listen' else 'cloud'}, v{VERSION}). "
                     f"Checking every {every}.{poke}{nxt}", GREEN)
    good_cfg, was_dropping, problem, warned = cfg, None, None, ""
    while True:
        try:
            try:
                cfg = load_config()  # pick up edits without restarting
            except json.JSONDecodeError as e:
                if problem != "config":
                    post_status(good_cfg, f"⚠️ **config.json has a typo**, so the bot is paused until it's fixed "
                                          f"and saved.\n`{e}`", RED)
                problem = "config"
                print(f"   ! config.json has a typo, fix and save it: {e}")
                time.sleep(60)
                continue
            if problem == "config":
                post_status(cfg, "✅ config.json is fixed. Checking again.", GREEN)
            sig = "; ".join(CONFIG_WARNINGS)
            if sig != warned:
                if sig:
                    post_status(cfg, "⚠️ **config.json needs a look** (the bot skips just these and keeps going):\n• "
                                     + "\n• ".join(CONFIG_WARNINGS)[:1500], AMBER)
                warned = sig
            good_cfg = cfg
            drop = active_window(cfg)
            if drop and was_dropping != drop["name"]:
                print(f"\n>>> DROP MODE ON: {drop['name']} until {drop['end']:%I:%M %p}, "
                      f"checking every {drop['every']}s")
                post_status(cfg, f"🚨 **Drop mode ON: {drop['name']}.** Checking {drop_label(drop)} every "
                                 f"{drop['every']}s until {drop['end']:%I:%M %p}.", RED)
            elif not drop and was_dropping:
                print(f"\n>>> DROP MODE OFF, back to every {args.loop:g} minutes")
                post_status(cfg, f"Drop mode off ({was_dropping} finished). Back to every {every}.", GREY)
            was_dropping = drop["name"] if drop else None
            run_once(cfg, args, drop)
            if problem == "crash":
                post_status(cfg, "✅ Checks are working again.", GREEN)
            problem = None
            wait = seconds_until_next_check(cfg, args.loop)
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001
            print(f"   ! check failed: {redact(e)}")
            if problem != "crash":
                post_status(good_cfg, f"⚠️ **A check failed:** `{str(e)[:300]}`\nIt'll keep retrying every {every}.", RED)
            problem = "crash"
            wait = args.loop * 60
        sys.stdout.flush()
        if wait > IDLE_MAX:
            HTTP.close_idle()        # shops drop idle connections anyway; don't hold sockets open for nothing
        time.sleep(wait)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        HTTP.close_idle()
        print("\nStopped.")
