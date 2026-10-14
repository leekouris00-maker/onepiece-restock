#!/usr/bin/env python3
"""
Discord slash commands for the One Piece restock bot - v2
=========================================================

Type these in your Discord server:

    /deals            everything buyable now within your limits, plus today's value picks
    /boxes            every English booster box in stock (any price), cheapest first
    /sealed           other sealed products in stock (starter decks, collections...)
    /card <search>    look a card up at Elemental Arcade, Good Games and Mayhem
    /history <search> price history of a box or sealed product, and the lowest price seen
    /stats            restocks in the last 30 days: which shops, what hours, how long stock lasts
    /drops            releases and drop windows coming up
    /recap            the daily recap, right now
    /status           is the bot healthy? last check, speed, shops not loading
    /help             this list

  Admin only (people with Manage Server, or listed in "admin_user_ids" under "alerts"):
    /want list | add | remove | enable   change the singles want list without editing config.json
    /boxmax <price>                      change the booster box max price
    /mute <hours>, /unmute               no @pings or phone pushes for a while (finds still post)

v2: /deals, /boxes and /sealed answer instantly from the restock bot's last check (latest.json,
at most a few minutes old) and say how old it is. Add fresh:True to check the shops live; live
checks are shared, so ten people asking at once cause one check, not ten.

Setup (once):
    py -3 -m pip install discord.py
    put your bot token in config.json under "alerts" as "discord_bot_token" (or in secrets.json)
    (Discord Developer Portal > your app > Bot > Reset Token). Keep it secret.

Runs on your PC next to tcg_bot.py (start_bot_hidden.vbs starts both). It only
reads shop websites - it never buys anything or logs in anywhere.
"""
import asyncio
import json
import os
import re
import statistics
import sys
import threading
import time
from collections import Counter
from datetime import datetime

try:
    import discord
    from discord import app_commands
except ImportError:
    sys.exit("discord.py isn't installed. Run:  py -3 -m pip install discord.py")

import tcg_bot as tb

if not hasattr(tb, "VERSION"):
    sys.exit("This commands_bot.py needs the v2 tcg_bot.py next to it - copy both files.")

GOLD, TEAL, ORANGE, BLUE, PURPLE, GREY = 0xE9C46A, 0x2A9D8F, 0xF4A261, 0x457B9D, 0x9B5DE5, 0x6C757D
STALE_AFTER = 15 * 60        # a snapshot older than this triggers a live check instead
LIVE_REUSE = 60              # a live check this recent is reused instead of starting another
FRESH_COOLDOWN = 30          # per person, for fresh:True / live checks
AUDIT_PATH = os.path.join(tb.HERE, "audit.log")


def cfg_now():
    return tb.load_config()


def link(f):
    """Buy link if we have one, else the product page."""
    return f.get("cart") or f.get("url") or ""


def lines_field(name, items, empty, limit=10):
    return {"name": name, "value": tb._lines(items, limit) if items else empty}


def ago(ts):
    if not ts:
        return "never"
    s = max(0, int(time.time() - ts))
    if s < 90:
        return f"{s}s ago"
    if s < 5400:
        return f"{s // 60} min ago"
    return f"{s / 3600:.1f} h ago"


def embed(title, fields, color=GOLD, description=None, footer=None):
    e = discord.Embed(title=title[:256], color=color, description=description)
    for f in fields[:25]:
        e.add_field(name=f["name"][:256], value=(f["value"] or "-")[:1024], inline=False)
    e.set_footer(text=footer or f"Checked {datetime.now():%a %d %b, %I:%M %p} · tap a name to open, ⚡ links go to checkout")
    return e


# ---------------------------------------------------------------- where the data comes from
class Live:
    """One live check at a time; everyone asking while it runs gets the same result."""

    def __init__(self):
        self.task = None
        self.result = None
        self.t = 0.0

    async def get(self, cfg):
        if self.result is not None and time.time() - self.t < LIVE_REUSE:
            return self.result, self.t
        if self.task is None or self.task.done():
            self.task = asyncio.ensure_future(asyncio.to_thread(self._run, cfg))
        result = await asyncio.shield(self.task)
        return result, self.t

    def _run(self, cfg):
        # same settings as the restock bot (user agent, robots.txt cache from its status.json), but no
        # skipping of down shops: someone asking for a fresh check wants every shop tried
        tb.begin_check(cfg, None, skip_down=False)
        (finds, by_shop), singles = tb.run_checks(cfg)
        self.result = {"sealed": {"finds": finds, "listings": [l for ls in by_shop.values() for l in (ls or [])],
                                  "down": sorted(n for n, ls in by_shop.items() if ls is None)},
                       "singles": {"finds": singles}}
        self.t = time.time()
        return self.result


LIVE = Live()
_cooldown = {}


def snapshot():
    return tb.read_json(tb.SNAPSHOT_PATH, {}) or {}


def snapshot_age(snap):
    """As-of time of a snapshot that has both boxes and singles, or 0 if it can't be used."""
    if "sealed" not in snap or "singles" not in snap:
        return 0
    return min(snap["sealed"].get("ts", 0), snap["singles"].get("ts", 0))


def snapshot_usable(snap):
    ts = snapshot_age(snap)
    return bool(ts) and time.time() - ts < STALE_AFTER


async def get_data(cfg, fresh, user_id=None, snap=None):
    """(data, as-of time, 'snapshot'|'live', note). Uses the last check unless it's stale or fresh=True."""
    snap = snapshot() if snap is None else snap
    if not fresh and snapshot_usable(snap):
        return snap, snapshot_age(snap), "snapshot", ""
    note = "" if fresh else "The restock bot hasn't checked recently, so this is a live check."
    if fresh and user_id is not None:
        left = _cooldown.get(user_id, 0) - time.time()
        if left > 0 and LIVE.result is not None:
            return LIVE.result, LIVE.t, "live", f"Fresh checks are limited to one per {FRESH_COOLDOWN}s each; this one is from {ago(LIVE.t)}."
        _cooldown[user_id] = time.time() + FRESH_COOLDOWN
    data, t = await LIVE.get(cfg)
    return data, t, "live", note


def footer(kind, ts):
    if kind == "snapshot":
        return f"From the bot's last check, {ago(ts)} · add fresh:True to check the shops now · ⚡ links go to checkout"
    return f"Checked live {ago(ts)} · tap a name to open, ⚡ links go to checkout"


# ---------------------------------------------------------------- what each command builds
def build_deals(cfg, data, kind, ts, note=""):
    boxes = data.get("sealed", {}).get("finds", [])
    singles = data.get("singles", {}).get("finds", [])
    picks = [f for f in singles if f.get("value_pick")]
    wants = [f for f in singles if not f.get("value_pick")]
    order = {"Booster box": 0, "Sealed": 1}
    sealed = sorted(boxes, key=lambda f: (order.get(f["kind"], 2), f["price"]))
    icon = {"Booster box": "📦", "Sealed": "🎁"}
    want_lines = [f"🧺 [One cart at {c['shop']}: {c['n']} cards]({c['link']}) **{tb.money(c['total'])}**"
                  for c in tb.combined_carts(wants)]
    want_lines += [f"{'⭐' if f.get('priority') else '🃏'} [{tb._short(f['name'])}]({link(f)}) **{tb.money(f['price'])}** · "
                   f"{f['shop']} · want x{f['qty']}" for f in sorted(wants, key=lambda f: (not f.get('priority'), f['price']))]
    fields = [
        lines_field(f"📦 Sealed within your limits ({len(sealed)})",
                    [f"{icon.get(f['kind'], '📦')} [{tb._short(f['name'])}]({link(f)}) **{tb.money(f['price'])}** · {f['shop']}" for f in sealed],
                    "No boxes or sealed products in stock under your max right now."),
        lines_field(f"🃏 Your want list in stock ({len(wants)})", want_lines,
                    "Nothing on your want list is in stock under your max."),
    ]
    if picks or os.path.exists(tb.PICKS_PATH):          # (no network call: this path must stay instant)
        fields.append(lines_field(f"💎 Value picks buyable now ({len(picks)})",
                                  [f"💎 [{tb._short(f['name'])}]({link(f)}) **{tb.money(f['price'])}** · {f['shop']}" for f in picks],
                                  "None of today's value picks are buyable at or under market right now."))
    total = len(sealed) + len(wants) + len(picks)
    return embed(f"🛒 Best buys right now ({total})", fields, TEAL if total else GREY, note or None, footer(kind, ts))


def build_listings(cfg, data, kind, ts, group, note=""):
    """All in-stock listings of booster boxes (group 'box') or other sealed ('watch'), any price."""
    max_box = cfg["sealed"]["max_price"]
    items = [l for l in data.get("sealed", {}).get("listings", [])
             if l.get("group", "box") == group and l["available"] and l["price"] > 0]
    items.sort(key=lambda l: l["price"])
    lines = []
    for l in items:
        ok = l["price"] <= l["max"]
        extra = f" · {l['note']}" if l.get("note") else ""
        lines.append(f"{'✅' if ok else '▫️'} [{tb._short(l['name'], 55)}]({link(l) if ok else l['url']}) "
                     f"**{tb.money(l['price'])}** · {l['shop']}{extra if group == 'watch' else ''}")
    down = data.get("sealed", {}).get("down", [])
    if group == "box":
        title = f"📦 English booster boxes in stock ({len(items)})"
        empty = "No English booster boxes in stock at any of the shops right now."
        desc = f"✅ = at or under your A${max_box:g} max (link goes to checkout)."
    else:
        title = f"🎁 Other sealed in stock ({len(items)})"
        empty = "None of the watched sealed products are in stock right now."
        desc = "✅ = at or under its max price (link goes to checkout)."
    if note:
        desc += "\n" + note
    fields = [lines_field("Cheapest first", lines, empty, limit=15)]
    if down:
        fields.append({"name": "⚠️ Couldn't check", "value": ", ".join(down)})
    return embed(title, fields, ORANGE if group == "box" else TEAL, desc, footer(kind, ts))


_card_cache = {}


def build_card(cfg, query):
    """Search the singles shops for a card (number or name). Results are reused for 2 minutes."""
    key = query.lower()
    hit = _card_cache.get(key)
    if hit and time.time() - hit[0] < 120:
        return hit[1]
    shops = cfg["singles"]["shops"]
    per_shop = tb.pmap(lambda s: (s[0], s[1], tb.suggest(s[1], query)), list(shops.items()))
    rows = []
    for shop, base, products in per_shop:
        for p in products:
            price = float(p.get("price_min") or p.get("price") or 0)
            if price <= 0:
                continue
            rows.append({"name": p.get("title", ""), "price": price, "available": bool(p.get("available")),
                         "url": f"{base}/products/{p.get('handle')}", "shop": shop})
    rows.sort(key=lambda r: (not r["available"], r["price"]))
    stock = [f"✅ [{tb._short(r['name'], 60)}]({r['url']}) **{tb.money(r['price'])}** · {r['shop']}" for r in rows if r["available"]]
    gone = [f"▫️ [{tb._short(r['name'], 60)}]({r['url']}) {tb.money(r['price'])} · {r['shop']}" for r in rows if not r["available"]]
    fields = [lines_field(f"In stock ({len(stock)})", stock, "None in stock.", 10)]
    if gone:
        fields.append(lines_field(f"Sold out ({len(gone)})", gone, "-", 6))
    e = embed(f"🔎 “{query}” at {', '.join(shops)}"[:256], fields, BLUE,
              "Search results can include other versions (alt art, SP, manga), so check the name. "
              "Prices are near-mint where the shop shows one.")
    _card_cache[key] = (time.time(), e)
    if len(_card_cache) > 200:
        _card_cache.clear()
    return e


def build_drops(cfg):
    now = datetime.now()
    soon = []
    for r in cfg.get("releases", tb.DEFAULT_RELEASES) or []:
        try:
            d = datetime.strptime(r["date"], "%Y-%m-%d")
        except (KeyError, ValueError, TypeError):
            continue
        days = (d.date() - now.date()).days
        if 0 <= days <= 120:
            soon.append((d, f"📅 **{d:%a %d %b}** {r['name']}" + (" (today!)" if days == 0 else f" · in {days} days")))
    windows = []
    for w in tb.parse_windows(cfg):
        if w["end"] > now:
            live = " **(ON NOW)**" if w["start"] <= now else ""
            windows.append((w["start"], f"🚨 {w['name']}: {w['start']:%a %d %b %I:%M %p} to {w['end']:%I:%M %p}, "
                                        f"every {w['every']}s{live}"))
    soon.sort(key=lambda x: x[0])
    windows.sort(key=lambda x: x[0])
    return embed("🗓️ Coming up", [
        lines_field("Releases (next 4 months)", [x[1] for x in soon], "Nothing in the next 4 months.", 12),
        lines_field("Drop-mode windows (PC checks every minute)", [x[1] for x in windows], "None set.", 8),
    ], PURPLE)


def build_recap(cfg):
    e = tb.run_recap(cfg, post=False, save=False)
    d = discord.Embed.from_dict(e)
    d.set_footer(text=f"Checked {datetime.now():%a %d %b, %I:%M %p} · price changes compare with this morning's recap")
    return d


def build_status(cfg):
    st = tb.load_status()
    snap = snapshot()
    names = tb.shop_names(cfg)
    down = [names.get(h, h) for h in st.get("shop_down", [])]
    last = st.get("last_check")
    when = ""
    if last:
        try:
            mins = int((datetime.now() - datetime.strptime(last, "%Y-%m-%d %H:%M:%S")).total_seconds() // 60)
            when = f" ({mins} min ago)" + (" ⚠️ that's a while, is the restock bot running?" if mins > 20 else "")
        except ValueError:
            pass
    run = st.get("last_run") or snap.get("metrics") or {}
    speed = (f"{run['secs']:.1f}s · {run['requests']} requests · {run['new_connections']} new connections · "
             f"{run['kb_wire']} KB" if run.get("secs") is not None else "no timing yet")
    slow = sorted(((h, v["p50_ms"]) for h, v in (run.get("hosts") or {}).items()), key=lambda x: -x[1])[:3]
    if slow:
        speed += "\nSlowest shops: " + ", ".join(f"{names.get(h, h)} {ms} ms" for h, ms in slow)
    win = tb.active_window(cfg)
    nxt = [w for w in tb.parse_windows(cfg) if w["start"] > datetime.now()]
    picks = tb.load_picks_file(cfg) or {}
    cols, prods, woo, search = tb.sealed_shops(cfg)
    n_shops = len({s["name"] for s in cols + prods + woo + search})
    mute = float(tb.read_controls().get("mute_until", 0) or 0)
    fields = [
        {"name": "Last restock check", "value": (last or "none yet") + when},
        {"name": "Speed (last check)", "value": speed},
        {"name": "Watching", "value": f"{n_shops} sealed shops · {len(cfg['singles']['shops'])} singles shops · "
                                      f"{sum(1 for c in cfg['singles']['cards'] if c.get('enabled', True))} cards on your want list · "
                                      f"{len(tb.load_value_picks(cfg))} value picks"
                                      + (f" (from {picks.get('date')})" if isinstance(picks, dict) and picks.get("date") else "")},
        {"name": "Not loading", "value": (", ".join(down) + " (retried every "
                                          f"{int(tb._num(cfg.get('down_retry_minutes', tb.DOWN_RETRY_MIN)) or 0)} min)")
         if down else "All shops loading ✅"},
        {"name": "Drop mode", "value": f"ON: {win['name']} until {win['end']:%I:%M %p}" if win else
         (f"Next: {nxt[0]['name']}, {nxt[0]['start']:%a %d %b %I:%M %p}" if nxt else "No windows set")},
        {"name": "Pings", "value": f"🔕 muted until {datetime.fromtimestamp(mute):%a %I:%M %p}" if mute > time.time() else "🔔 on"},
    ]
    if tb.CONFIG_WARNINGS:
        fields.append({"name": "⚠️ config.json", "value": "\n".join("• " + w for w in tb.CONFIG_WARNINGS)[:1000]})
    return embed(f"🩺 Bot status (PC, v{tb.VERSION})", fields, GREY)


SPARK = "▁▂▃▄▅▆▇█"


def spark(values):
    if not values:
        return ""
    lo, hi = min(values), max(values)
    return "".join(SPARK[0 if hi == lo else int((v - lo) / (hi - lo) * (len(SPARK) - 1))] for v in values)


def build_history(cfg, query):
    hist = tb.read_json(tb.HISTORY_PATH, {}) or {}
    toks = [t for t in re.split(r"\W+", query.lower()) if t]
    rows = []
    for key, h in hist.items():
        hay = f"{h.get('name', '')} {h.get('shop', '')}".lower()
        if toks and all(t in hay for t in toks):
            rows.append((key, h))
    rows.sort(key=lambda kv: (not kv[1].get("avail"), kv[1]["points"][-1][1] if kv[1].get("points") else 0))
    lines = []
    for key, h in rows[:8]:
        pts = h.get("points") or []
        cur = pts[-1] if pts else None
        low = tb.lowest_seen(hist, key, days=365)
        trend = spark([p[1] for p in pts[-14:] if p[1] > 0])
        lines.append(f"{'✅' if h.get('avail') else '▫️'} [{tb._short(h['name'], 50)}]({h['url']}) · {h['shop']}\n"
                     f"   now **{tb.money(cur[1]) if cur else '?'}**"
                     + (f" · lowest in stock {tb.money(low[0])} ({low[1]})" if low else " · never in stock while watched")
                     + (f" · {trend}" if len(trend) > 1 else "") + f" · tracked {len(pts)} day(s)")
    return embed(f"📈 Price history: “{query}”"[:256],
                 [lines_field(f"Matches ({len(rows)})", lines, "Nothing matches. Try a set code like OP-13, or a shop name.", 8)],
                 BLUE, "Booster boxes and watched sealed products, one price per day (lowest in-stock price that day).",
                 footer="✅ in stock now · ▫️ not buyable · the sparkline is the last two weeks")


def build_stats(cfg):
    ev = tb.read_events(30)
    ins = [e for e in ev if e.get("event") == "in_stock"]
    outs = [e for e in ev if e.get("event") == "sold_out" and e.get("was")]
    by_shop = Counter(e["shop"] for e in ins)
    hours = Counter(datetime.fromtimestamp(e["t"]).hour for e in ins)
    lasted = [e["was"] / 60 for e in outs]
    fields = [
        lines_field(f"🔁 Back-in-stock events, last 30 days ({len(ins)})",
                    [f"**{s}**: {n}" for s, n in by_shop.most_common(8)], "None recorded yet - give it a few days."),
        {"name": "⏱️ How long stock lasted", "value": (f"median {statistics.median(lasted):.0f} min, "
                                                     f"shortest {min(lasted):.0f} min over {len(lasted)} sell-outs")
         if lasted else "No sell-outs recorded yet."},
        {"name": "🕐 Busiest hours for restocks", "value": ", ".join(f"{h:02d}:00 ({n})" for h, n in hours.most_common(4))
         if hours else "Not enough data yet."},
    ]
    return embed("📊 Restock stats", fields, PURPLE,
                 "From the bot's own price history (booster boxes and watched sealed products).")


HELP = (
    "`/deals` everything buyable now within your limits, plus value picks\n"
    "`/boxes` every English booster box in stock, any price, cheapest first\n"
    "`/sealed` other sealed products in stock\n"
    "`/card <search>` look up a card, e.g. `/card OP13-120` or `/card sabo`\n"
    "`/history <search>` price history and lowest price seen, e.g. `/history op-18`\n"
    "`/stats` restock patterns over the last 30 days\n"
    "`/drops` releases and drop windows coming up\n"
    "`/recap` the daily recap, right now\n"
    "`/status` last check, speed, shops not loading, drop mode\n\n"
    "`/deals`, `/boxes` and `/sealed` answer instantly from the last check; add `fresh:True` to check the shops now.\n\n"
    "Admins: `/want list|add|remove|enable`, `/boxmax`, `/mute`, `/unmute`."
)


# ---------------------------------------------------------------- admin: safe config edits
_cfg_lock = threading.Lock()


def is_admin(inter, cfg):
    ids = {str(x) for x in ((cfg.get("alerts") or {}).get("admin_user_ids") or [])}
    perms = getattr(inter.user, "guild_permissions", None)
    return str(inter.user.id) in ids or bool(perms and (perms.manage_guild or perms.administrator))


def edit_config(change, who, what):
    """Change config.json safely: re-read the file itself (not the merged settings, so secrets from
    secrets.json or the environment are never written into it), keep a backup, write atomically,
    and note who changed what in audit.log."""
    with _cfg_lock:
        with open(tb.CONFIG_PATH, encoding="utf-8-sig") as f:
            raw = json.load(f)
        result = change(raw)
        problems = tb.check_config(json.loads(json.dumps(raw)))
        with open(tb.CONFIG_PATH, encoding="utf-8-sig") as f:
            old = f.read()
        with open(tb.CONFIG_PATH + ".bak", "w", encoding="utf-8") as f:
            f.write(old)
        tb.atomic_write_json(tb.CONFIG_PATH, raw, indent=1, ensure_ascii=False)
        tb.append_text(AUDIT_PATH, f"{datetime.now():%Y-%m-%d %H:%M:%S}  {who}  {what}\n", 500_000)
        return result, problems


def norm_num(num):
    n = re.sub(r"\s+", "", num.upper())
    m = re.fullmatch(r"([A-Z]{1,4})(\d{2})-?(\d{3})", n)
    if m:
        return f"{m.group(1)}{m.group(2)}-{m.group(3)}"
    m = re.fullmatch(r"P-?(\d{3})", n)
    if m:
        return f"P-{m.group(1)}"
    return None


# ---------------------------------------------------------------- Discord wiring
class Bot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.synced = False

    async def on_ready(self):
        if not self.synced:
            for g in self.guilds:                  # per-server commands appear instantly
                self.tree.copy_global_to(guild=g)
                await self.tree.sync(guild=g)
            self.synced = True
        print(f"[{datetime.now():%H:%M:%S}] commands ready as {self.user} in: {', '.join(g.name for g in self.guilds)}",
              flush=True)


bot = Bot()


async def fail(inter, e):
    print(f"   ! command failed: {tb.redact(e)}", flush=True)
    msg = f"⚠️ That didn't work: `{tb.redact(str(e))[:300]}`"
    if inter.response.is_done():
        await inter.followup.send(msg)
    else:
        await inter.response.send_message(msg, ephemeral=True)


async def respond(inter, builder, *args):
    """For commands that always go to the shops: acknowledge straight away (Discord allows 3s),
    do the slow part in a thread, then reply."""
    await inter.response.defer(thinking=True)
    try:
        cfg = cfg_now()
        result = await asyncio.to_thread(builder, cfg, *args)
        await inter.followup.send(embed=result)
    except Exception as e:  # noqa: BLE001
        await fail(inter, e)


async def respond_data(inter, builder, fresh, *args):
    """For /deals, /boxes, /sealed: instant from the last check, or a shared live check."""
    try:
        cfg = cfg_now()
        snap = snapshot()
        if fresh or not snapshot_usable(snap):     # going to the shops: tell Discord we're on it first
            await inter.response.defer(thinking=True)
        data, t, kind, note = await get_data(cfg, fresh, inter.user.id, snap)
        e = builder(cfg, data, kind, t, *args, note=note)
        if inter.response.is_done():
            await inter.followup.send(embed=e)
        else:
            await inter.response.send_message(embed=e)
    except Exception as e:  # noqa: BLE001
        await fail(inter, e)


@bot.tree.command(name="deals", description="Everything buyable right now within your limits, plus value picks")
@app_commands.describe(fresh="Check the shops right now instead of using the last check")
async def deals_cmd(inter: discord.Interaction, fresh: bool = False):
    await respond_data(inter, build_deals, fresh)


@bot.tree.command(name="boxes", description="Every English booster box in stock right now, cheapest first")
@app_commands.describe(fresh="Check the shops right now instead of using the last check")
async def boxes_cmd(inter: discord.Interaction, fresh: bool = False):
    await respond_data(inter, build_listings, fresh, "box")


@bot.tree.command(name="sealed", description="Starter decks, collections and other sealed products in stock")
@app_commands.describe(fresh="Check the shops right now instead of using the last check")
async def sealed_cmd(inter: discord.Interaction, fresh: bool = False):
    await respond_data(inter, build_listings, fresh, "watch")


async def want_autocomplete(inter: discord.Interaction, current: str):
    try:
        cards = cfg_now()["singles"]["cards"]
    except Exception:  # noqa: BLE001
        return []
    cur = current.lower()
    out = []
    for c in cards:
        label = f"{c.get('name', '')} {c.get('num', '')}" + ("" if c.get("enabled", True) else " (off)")
        if cur in label.lower():
            out.append(app_commands.Choice(name=label[:100], value=str(c.get("num", ""))[:100]))
    return out[:25]


@bot.tree.command(name="card", description="Look up a card at Elemental Arcade, Good Games and Mayhem")
@app_commands.describe(search="Card number or name, e.g. OP13-120 or sabo")
@app_commands.autocomplete(search=want_autocomplete)
async def card_cmd(inter: discord.Interaction, search: str):
    await respond(inter, build_card, search.strip()[:60])


@bot.tree.command(name="history", description="Price history and lowest price seen for a box or sealed product")
@app_commands.describe(search="e.g. op-18, eb-05 gameology, illustration box")
async def history_cmd(inter: discord.Interaction, search: str):
    try:
        await inter.response.send_message(embed=build_history(cfg_now(), search.strip()[:60]))
    except Exception as e:  # noqa: BLE001
        await fail(inter, e)


@bot.tree.command(name="stats", description="Restocks over the last 30 days: shops, hours, how long stock lasted")
async def stats_cmd(inter: discord.Interaction):
    try:
        await inter.response.send_message(embed=build_stats(cfg_now()))
    except Exception as e:  # noqa: BLE001
        await fail(inter, e)


@bot.tree.command(name="drops", description="Releases and drop windows coming up")
async def drops_cmd(inter: discord.Interaction):
    try:
        await inter.response.send_message(embed=build_drops(cfg_now()))
    except Exception as e:  # noqa: BLE001
        await fail(inter, e)


@bot.tree.command(name="recap", description="The daily recap, right now")
async def recap_cmd(inter: discord.Interaction):
    await respond(inter, build_recap)


@bot.tree.command(name="status", description="Is the bot healthy? Last check, speed, shops not loading, drop mode")
async def status_cmd(inter: discord.Interaction):
    try:
        await inter.response.send_message(embed=build_status(cfg_now()))
    except Exception as e:  # noqa: BLE001
        await fail(inter, e)


@bot.tree.command(name="help", description="What the restock bot's commands do")
async def help_cmd(inter: discord.Interaction):
    await inter.response.send_message(embed=discord.Embed(title="🏴‍☠️ Restock bot commands", description=HELP,
                                                          color=GOLD))


# ---- admin commands
want = app_commands.Group(name="want", description="Your singles want list (admins)",
                          default_permissions=discord.Permissions(manage_guild=True))


async def admin_only(inter):
    cfg = cfg_now()
    if is_admin(inter, cfg):
        return cfg
    await inter.response.send_message("Only server admins can change the bot's settings.", ephemeral=True)
    return None


@want.command(name="list", description="Show the want list")
async def want_list(inter: discord.Interaction):
    cfg = await admin_only(inter)
    if cfg is None:
        return
    cards = cfg["singles"]["cards"]
    on = [c for c in cards if c.get("enabled", True)]
    lines = [f"{'⭐' if c.get('priority') else '🃏'} **{c.get('name', '')} {c['num']}** x{c['qty']} · max "
             f"{tb.money(c['max'])}" + (f" · {c['deck']}" if c.get("deck") else "") for c in on]
    await inter.response.send_message(embed=embed(f"📝 Want list ({len(on)} on, {len(cards) - len(on)} off)",
                                                  [lines_field("Watching", lines, "Nothing switched on.", 20)], BLUE),
                                      ephemeral=True)


@want.command(name="add", description="Add a card, or change one already on the list")
@app_commands.describe(num="Card number, e.g. OP13-120", max="Most you'd pay each (AUD)", qty="How many you want",
                       name="Card name (used to search Good Games and Mayhem)", deck="Which deck it's for",
                       priority="Show it first and highlight it")
async def want_add(inter: discord.Interaction, num: str, max: float, qty: int = 1, name: str = "", deck: str = "",
                   priority: bool = False):
    cfg = await admin_only(inter)
    if cfg is None:
        return
    n = norm_num(num)
    if not n or max <= 0 or not 1 <= qty <= 50:
        await inter.response.send_message("Use a card number like OP13-120 (or P-105), a max above $0 and a qty "
                                          "from 1 to 50.", ephemeral=True)
        return

    def change(raw):
        cards = raw.setdefault("singles", {}).setdefault("cards", [])
        for c in cards:
            if str(c.get("num", "")).upper() == n:
                c.update({"max": max, "qty": qty, "enabled": True})
                if name:
                    c["name"] = name
                if deck:
                    c["deck"] = deck
                if priority:
                    c["priority"] = True
                return "updated", c
        c = {"name": name or n, "num": n, "qty": qty, "max": max, "deck": deck, "priority": priority, "enabled": True}
        cards.append(c)
        return "added", c
    try:
        (what, c), problems = await asyncio.to_thread(edit_config, change, f"{inter.user} ({inter.user.id})",
                                                      f"want {num} max={max} qty={qty} name={name!r}")
    except Exception as e:  # noqa: BLE001
        await fail(inter, e)
        return
    tip = "" if name or c.get("name") != n else " Tip: add name:... so Good Games and Mayhem can be searched too."
    await inter.response.send_message(f"✅ {what.capitalize()} **{c['name']} {n}**: x{qty}, max {tb.money(max)}. "
                                      f"The restock bot picks it up on its next check.{tip}", ephemeral=True)


async def _set_enabled(inter, num, on):
    cfg = await admin_only(inter)
    if cfg is None:
        return
    n = norm_num(num) or num.upper()

    def change(raw):
        for c in raw.get("singles", {}).get("cards", []):
            if str(c.get("num", "")).upper() == n:
                c["enabled"] = on
                return c
        return None
    try:
        c, _ = await asyncio.to_thread(edit_config, change, f"{inter.user} ({inter.user.id})",
                                       f"want {'enable' if on else 'remove'} {n}")
    except Exception as e:  # noqa: BLE001
        await fail(inter, e)
        return
    if c is None:
        await inter.response.send_message(f"{n} isn't on the want list.", ephemeral=True)
    else:
        await inter.response.send_message(f"{'✅ Watching' if on else '⏸️ Stopped watching'} **{c.get('name', '')} {n}**"
                                          + ("" if on else " (kept on the list switched off; /want enable to bring it back)."),
                                          ephemeral=True)


@want.command(name="remove", description="Stop watching a card (kept on the list, switched off)")
@app_commands.autocomplete(num=want_autocomplete)
async def want_remove(inter: discord.Interaction, num: str):
    await _set_enabled(inter, num, False)


@want.command(name="enable", description="Start watching a switched-off card again")
@app_commands.autocomplete(num=want_autocomplete)
async def want_enable(inter: discord.Interaction, num: str):
    await _set_enabled(inter, num, True)


bot.tree.add_command(want)


@bot.tree.command(name="boxmax", description="Set the most you'd pay for a booster box (AUD)")
@app_commands.default_permissions(manage_guild=True)
async def boxmax_cmd(inter: discord.Interaction, price: float):
    cfg = await admin_only(inter)
    if cfg is None:
        return
    if not 20 <= price <= 5000:
        await inter.response.send_message("Pick a price between $20 and $5,000.", ephemeral=True)
        return
    try:
        await asyncio.to_thread(edit_config, lambda raw: raw.setdefault("sealed", {}).__setitem__("max_price", price),
                                f"{inter.user} ({inter.user.id})", f"boxmax {price}")
    except Exception as e:  # noqa: BLE001
        await fail(inter, e)
        return
    await inter.response.send_message(f"✅ Booster box max is now **{tb.money(price)}**.", ephemeral=True)


@bot.tree.command(name="mute", description="No @pings or phone pushes for a while (finds still post)")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(hours="How long, up to 72 hours")
async def mute_cmd(inter: discord.Interaction, hours: float = 8.0):
    cfg = await admin_only(inter)
    if cfg is None:
        return
    hours = min(max(hours, 0.25), 72)
    until = time.time() + hours * 3600
    controls = tb.read_controls()
    controls["mute_until"] = round(until)
    tb.atomic_write_json(tb.CONTROLS_PATH, controls)
    tb.append_text(AUDIT_PATH, f"{datetime.now():%Y-%m-%d %H:%M:%S}  {inter.user} ({inter.user.id})  mute {hours}h\n", 500_000)
    await inter.response.send_message(f"🔕 Pings off until **{datetime.fromtimestamp(until):%a %I:%M %p}**. "
                                      f"Finds still post in the channels. `/unmute` to turn them back on.", ephemeral=True)


@bot.tree.command(name="unmute", description="Turn @pings and phone pushes back on")
@app_commands.default_permissions(manage_guild=True)
async def unmute_cmd(inter: discord.Interaction):
    cfg = await admin_only(inter)
    if cfg is None:
        return
    controls = tb.read_controls()
    controls.pop("mute_until", None)
    tb.atomic_write_json(tb.CONTROLS_PATH, controls)
    await inter.response.send_message("🔔 Pings are back on.", ephemeral=True)


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    try:
        cfg = cfg_now()
    except (FileNotFoundError, json.JSONDecodeError) as e:
        sys.exit(f"Couldn't read config.json: {e}")
    token = os.environ.get("DISCORD_BOT_TOKEN") or (cfg.get("alerts") or {}).get("discord_bot_token")
    if not token:
        sys.exit('No bot token. Add "discord_bot_token": "<token>" to the "alerts" section of config.json '
                 '(or to secrets.json).')
    print(f"[{datetime.now():%H:%M:%S}] starting Discord commands (v{tb.VERSION})...", flush=True)
    bot.run(token.strip(), log_handler=None)


if __name__ == "__main__":
    main()
