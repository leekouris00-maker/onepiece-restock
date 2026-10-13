#!/usr/bin/env python3
"""
Discord slash commands for the One Piece restock bot
====================================================

Type these in your Discord server and the bot checks the shops right then and replies:

    /deals            everything buyable now within your limits, plus today's value picks
    /boxes            every English booster box in stock (any price), cheapest first
    /sealed           other sealed products in stock (starter decks, collections...)
    /card <search>    look a card up at Elemental Arcade, Good Games and Mayhem
    /drops            releases and drop windows coming up
    /recap            the daily recap, right now
    /status           is the bot healthy? last check, shops not loading
    /help             this list

Setup (once):
    py -3 -m pip install discord.py
    put your bot token in config.json under "alerts" as "discord_bot_token"
    (Discord Developer Portal > your app > Bot > Reset Token). Keep it secret.

Runs on your PC next to tcg_bot.py (start_bot_hidden.vbs starts both). It only
reads shop websites - it never buys anything or logs in anywhere.
"""
import asyncio
import json
import os
import sys
import urllib.parse
from datetime import datetime

try:
    import discord
    from discord import app_commands
except ImportError:
    sys.exit("discord.py isn't installed. Run:  py -3 -m pip install discord.py")

import tcg_bot as tb

GOLD, TEAL, ORANGE, BLUE, PURPLE, GREY = 0xE9C46A, 0x2A9D8F, 0xF4A261, 0x457B9D, 0x9B5DE5, 0x6C757D


def cfg_now():
    return tb.load_config()


def link(f):
    """Buy link if we have one, else the product page."""
    return f.get("cart") or f.get("url") or ""


def lines_field(name, items, empty, limit=10):
    return {"name": name, "value": tb._lines(items, limit) if items else empty}


def embed(title, fields, color=GOLD, description=None):
    e = discord.Embed(title=title[:256], color=color, description=description)
    for f in fields[:25]:
        e.add_field(name=f["name"][:256], value=(f["value"] or "-")[:1024], inline=False)
    e.set_footer(text=f"Checked {datetime.now():%a %d %b, %I:%M %p} · tap a name to open, ⚡ links go to checkout")
    return e


# ---------------------------------------------------------------- what each command builds
def build_deals(cfg):
    boxes, _ = tb.check_sealed(cfg)
    singles = tb.check_singles(cfg)
    picks = [f for f in singles if f.get("value_pick")]
    wants = [f for f in singles if not f.get("value_pick")]
    order = {"Booster box": 0, "Sealed": 1}
    sealed = sorted(boxes, key=lambda f: (order[f["kind"]], f["price"]))
    icon = {"Booster box": "📦", "Sealed": "🎁"}
    fields = [
        lines_field(f"📦 Sealed within your limits ({len(sealed)})",
                    [f"{icon[f['kind']]} [{tb._short(f['name'])}]({link(f)}) **{tb.money(f['price'])}** · {f['shop']}" for f in sealed],
                    "No boxes or sealed products in stock under your max right now."),
        lines_field(f"🃏 Your want list in stock ({len(wants)})",
                    [f"{'⭐' if f.get('priority') else '🃏'} [{tb._short(f['name'])}]({link(f)}) **{tb.money(f['price'])}** · "
                     f"{f['shop']} · want x{f['qty']}" for f in sorted(wants, key=lambda f: (not f.get('priority'), f['price']))],
                    "Nothing on your want list is in stock under your max."),
    ]
    if picks or tb.load_value_picks(cfg):
        fields.append(lines_field(f"💎 Value picks buyable now ({len(picks)})",
                                  [f"💎 [{tb._short(f['name'])}]({link(f)}) **{tb.money(f['price'])}** · {f['shop']}" for f in picks],
                                  "None of today's value picks are buyable at or under market right now."))
    total = len(sealed) + len(wants) + len(picks)
    return embed(f"🛒 Best buys right now ({total})", fields, TEAL if total else GREY)


def build_listings(cfg, group):
    """All in-stock listings of booster boxes (group 'box') or other sealed ('watch'), any price."""
    _, by_shop = tb.check_sealed(cfg)
    max_box = cfg["sealed"]["max_price"]
    items = [l for ls in by_shop.values() for l in (ls or [])
             if l.get("group", "box") == group and l["available"] and l["price"] > 0]
    items.sort(key=lambda l: l["price"])
    lines = []
    for l in items:
        ok = l["price"] <= l["max"]
        extra = f" · {l['note']}" if l.get("note") else ""
        lines.append(f"{'✅' if ok else '▫️'} [{tb._short(l['name'], 55)}]({link(l) if ok else l['url']}) "
                     f"**{tb.money(l['price'])}** · {l['shop']}{extra if group == 'watch' else ''}")
    down = [n for n, ls in by_shop.items() if ls is None]
    if group == "box":
        title = f"📦 English booster boxes in stock ({len(items)})"
        empty = "No English booster boxes in stock at any of the shops right now."
        desc = f"✅ = at or under your A${max_box:g} max (link goes to checkout)."
    else:
        title = f"🎁 Other sealed in stock ({len(items)})"
        empty = "None of the watched sealed products are in stock right now."
        desc = "✅ = at or under its max price (link goes to checkout)."
    fields = [lines_field("Cheapest first", lines, empty, limit=15)]
    if down:
        fields.append({"name": "⚠️ Couldn't check", "value": ", ".join(down)})
    return embed(title, fields, ORANGE if group == "box" else TEAL, desc)


def build_card(cfg, query):
    """Search the singles shops for a card (number or name)."""
    shops = cfg["singles"]["shops"]
    rows = []
    for shop, base in shops.items():
        for p in tb.suggest(base, query):
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
    return embed(f"🔎 “{query}” at Elemental, Good Games & Mayhem", fields, BLUE,
                 "Search results can include other versions (alt art, SP, manga), so check the name. "
                 "Prices are near-mint where the shop shows one.")


def build_drops(cfg):
    now = datetime.now()
    soon = []
    for r in cfg.get("releases", tb.DEFAULT_RELEASES) or []:
        try:
            d = datetime.strptime(r["date"], "%Y-%m-%d")
        except (KeyError, ValueError):
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
    names = tb.shop_names(cfg)
    down = [names.get(h, h) for h in st.get("shop_down", [])]
    last = st.get("last_check")
    ago = ""
    if last:
        try:
            mins = int((datetime.now() - datetime.strptime(last, "%Y-%m-%d %H:%M:%S")).total_seconds() // 60)
            ago = f" ({mins} min ago)" + (" ⚠️ that's a while, is the restock bot running?" if mins > 20 else "")
        except ValueError:
            pass
    win = tb.active_window(cfg)
    nxt = [w for w in tb.parse_windows(cfg) if w["start"] > datetime.now()]
    picks = tb.load_picks_file(cfg) or {}
    cols, prods, woo, search = tb.sealed_shops(cfg)
    n_shops = len({s["name"] for s in cols + prods + woo + search})
    fields = [
        {"name": "Last restock check", "value": (last or "none yet") + ago},
        {"name": "Watching", "value": f"{n_shops} sealed shops · {len(cfg['singles']['shops'])} singles shops · "
                                      f"{sum(1 for c in cfg['singles']['cards'] if c.get('enabled', True))} cards on your want list · "
                                      f"{len(tb.load_value_picks(cfg))} value picks"
                                      + (f" (from {picks.get('date')})" if picks.get("date") else "")},
        {"name": "Not loading", "value": ", ".join(down) if down else "All shops loading ✅"},
        {"name": "Drop mode", "value": f"ON: {win['name']} until {win['end']:%I:%M %p}" if win else
         (f"Next: {nxt[0]['name']}, {nxt[0]['start']:%a %d %b %I:%M %p}" if nxt else "No windows set")},
    ]
    return embed("🩺 Bot status (PC)", fields, GREY)


HELP = (
    "`/deals` everything buyable now within your limits, plus value picks\n"
    "`/boxes` every English booster box in stock, any price, cheapest first\n"
    "`/sealed` other sealed products in stock\n"
    "`/card <search>` look up a card, e.g. `/card OP13-120` or `/card sabo`\n"
    "`/drops` releases and drop windows coming up\n"
    "`/recap` the daily recap, right now\n"
    "`/status` last check, shops not loading, drop mode\n\n"
    "Each one checks the shops live, so give it 10–30 seconds."
)


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


async def respond(inter, builder, *args):
    """Acknowledge straight away (Discord allows 3s), do the slow shop checks in a thread, then reply."""
    await inter.response.defer(thinking=True)
    try:
        cfg = cfg_now()
        result = await asyncio.to_thread(builder, cfg, *args)
        await inter.followup.send(embed=result)
    except Exception as e:  # noqa: BLE001
        print(f"   ! command failed: {e}", flush=True)
        await inter.followup.send(f"⚠️ That didn't work: `{str(e)[:300]}`")


@bot.tree.command(name="deals", description="Everything buyable right now within your limits, plus value picks")
async def deals_cmd(inter: discord.Interaction):
    await respond(inter, build_deals)


@bot.tree.command(name="boxes", description="Every English booster box in stock right now, cheapest first")
async def boxes_cmd(inter: discord.Interaction):
    await respond(inter, build_listings, "box")


@bot.tree.command(name="sealed", description="Starter decks, collections and other sealed products in stock")
async def sealed_cmd(inter: discord.Interaction):
    await respond(inter, build_listings, "watch")


@bot.tree.command(name="card", description="Look up a card at Elemental Arcade, Good Games and Mayhem")
@app_commands.describe(search="Card number or name, e.g. OP13-120 or sabo")
async def card_cmd(inter: discord.Interaction, search: str):
    await respond(inter, build_card, search.strip()[:60])


@bot.tree.command(name="drops", description="Releases and drop windows coming up")
async def drops_cmd(inter: discord.Interaction):
    await respond(inter, build_drops)


@bot.tree.command(name="recap", description="The daily recap, right now")
async def recap_cmd(inter: discord.Interaction):
    await respond(inter, build_recap)


@bot.tree.command(name="status", description="Is the bot healthy? Last check, shops not loading, drop mode")
async def status_cmd(inter: discord.Interaction):
    await respond(inter, build_status)


@bot.tree.command(name="help", description="What the restock bot's commands do")
async def help_cmd(inter: discord.Interaction):
    await inter.response.send_message(embed=discord.Embed(title="🏴‍☠️ Restock bot commands", description=HELP,
                                                          color=GOLD))


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
        sys.exit('No bot token. Add "discord_bot_token": "<token>" to the "alerts" section of config.json.')
    print(f"[{datetime.now():%H:%M:%S}] starting Discord commands...", flush=True)
    bot.run(token.strip(), log_handler=None)


if __name__ == "__main__":
    main()
