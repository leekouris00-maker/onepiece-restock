#!/usr/bin/env python3
"""
Add the Pokémon section to the Discord server (run once; safe to run again)
===========================================================================

Creates:
  role      "Pokémon Ping"   pinged for Pokémon alerts and in-store drops (One Piece keeps "Restock Ping")
  category  ⚡ POKÉMON, with these channels (read-only for members; the bot and its webhooks post):
    📍・pokemon-in-store     release-day posts (the night before, and 7am on the day) and /pokemon report sightings
    ⚡・pokemon-restocks     Pokémon alerts for releases that don't have a channel of their own
    one per upcoming release in pokemon_watch.py, e.g. 🐉・delta-reign and 🎂・30th-celebration:
                             new listings, pre-orders, and stock at or under your max for that release

It makes a webhook for each channel, saves them (and the role) in secrets.json (never uploaded
anywhere), and prints the two values to add to GitHub so the cloud copy posts to the same channels.
Run it again after adding a release in config.json: only what's missing is made.

Double-click add_pokemon_channels.bat, or:  py -3 add_pokemon_channels.py
(or type /pokemon setup in Discord, which does the same thing).
Uses the bot token already saved for the Discord commands; asks for it only if it can't find it.
"""
import getpass
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request

import pokemon_watch as pw

API = "https://discord.com/api/v10"
UA = "DiscordBot (https://github.com/leekouris00-maker/onepiece-restock, 1.0)"
HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
SECRETS_PATH = os.path.join(HERE, "secrets.json")

CATEGORY = "⚡ POKÉMON"
ROLE = "Pokémon Ping"
HOOK_NAME = "Pokémon Restock"
SEND_MESSAGES = 1 << 11
CREATE_THREADS = (1 << 35) | (1 << 36)
READ_ONLY_DENY = SEND_MESSAGES | CREATE_THREADS

_urlopen = urllib.request.urlopen          # swapped out in tests


class SetupError(Exception):
    """Something Discord refused, in words that say what to do about it."""


def read_json(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def api(token, method, path, body=None, url=None, auth=True):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"User-Agent": UA, "Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = f"Bot {token}"
    for _ in range(6):
        req = urllib.request.Request(url or API + path, data=data, method=method, headers=headers)
        try:
            with _urlopen(req, timeout=20) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            if e.code == 429:
                try:
                    wait = float(json.loads(text).get("retry_after", 2))
                except Exception:  # noqa: BLE001
                    wait = 2
                time.sleep(min(wait, 30) + 0.3)
                continue
            if e.code == 401:
                raise SetupError("Discord says the bot token is wrong. Reset it in the Developer Portal, put the new "
                                 "one in secrets.json (\"discord_bot_token\"), and try again.")
            if e.code == 403:
                raise SetupError("Discord says the bot isn't allowed to make roles, channels or webhooks. In Server "
                                 "Settings > Roles, give the bot's role Administrator (or Manage Roles, Manage "
                                 "Channels and Manage Webhooks).")
            raise SetupError(f"Discord error {e.code} on {method} {path}: {text[:300]}")
        except urllib.error.URLError as e:
            raise SetupError(f"Couldn't reach Discord ({e.reason}). Check the internet and try again.")
    raise SetupError("Discord kept rate-limiting. Wait a minute and try again.")


def plan(cfg):
    """[(webhook key, channel name, topic, hello message)] for the channels this setup wants."""
    pc = pw.settings(cfg)
    out = [
        ("in-store", "📍・pokemon-in-store",
         "In-store Pokémon drops: the night before a release, 7am on the day, and /pokemon report sightings.",
         "📍 **In-store Pokémon drops post here**: the night before a release (\"tomorrow in stores\") and at 7am "
         "on the day (\"out today\", pinging Pokémon Ping). Spotted stock on a shelf? Type `/pokemon report` "
         "anywhere in the server and it posts here for everyone."),
        ("restocks", "⚡・pokemon-restocks",
         "Pokémon alerts for releases that don't have a channel of their own.",
         "⚡ **Pokémon alerts for releases without their own channel post here.**"),
    ]
    for s in pc["sections"]:
        if not (s["enabled"] and s["channel"]):
            continue
        label = s["name"] + (f" ({s['code']})" if s["code"] else "")
        nxt = pw.next_day(s)
        when = f" Next in stores: {pw.day_text(nxt[0])}, {nxt[1]['what']}." if nxt else ""
        out.append((s["slug"], f"{s['emoji']}・{s['slug']}"[:100],
                    f"{label}: new listings, pre-orders and stock at or under your max.{when}"[:1024],
                    f"{s['emoji']} **{label} posts here**: every new listing and pre-order the shops put up, and an "
                    f"alert whenever something's in stock at or under your max.{when}"))
    return out


def pick_guild(token, guild_id=None, ask=True):
    guilds = api(token, "GET", "/users/@me/guilds") or []
    if guild_id is not None:
        g = next((g for g in guilds if str(g["id"]) == str(guild_id)), None)
        if g is None:
            raise SetupError("The bot isn't in that server.")
        return g
    if not guilds:
        raise SetupError("The bot isn't in any server.")
    if len(guilds) == 1 or not ask:
        return guilds[0]
    for i, g in enumerate(guilds, 1):
        print(f"  {i}. {g['name']}")
    return guilds[int(input("Which server? Type the number: ").strip()) - 1]


def setup(token, guild_id=None, cfg=None, log=print, ask=True):
    """Make whatever's missing. -> {"guild", "hooks": {key: link}, "ping": "<@&id>", "created": [names]}"""
    cfg = cfg if cfg is not None else (read_json(CONFIG_PATH) or {})
    guild = pick_guild(token, guild_id, ask)
    gid = guild["id"]
    created = []

    roles = api(token, "GET", f"/guilds/{gid}/roles") or []
    role = next((r for r in roles if r.get("name") == ROLE), None)
    if role is None:
        role = api(token, "POST", f"/guilds/{gid}/roles", {"name": ROLE, "permissions": "0", "color": pw.YELLOW,
                                                            "hoist": False, "mentionable": True})
        created.append(f"role {ROLE}")
        log(f"  role created:     {ROLE}")
    else:
        log(f"  role exists:      {ROLE}")

    existing = api(token, "GET", f"/guilds/{gid}/channels") or []
    cat = next((c for c in existing if c.get("type") == 4 and c.get("name") == CATEGORY), None)
    if cat is None:
        cat = api(token, "POST", f"/guilds/{gid}/channels", {"name": CATEGORY, "type": 4})
        created.append(f"category {CATEGORY}")
        log(f"  category created: {CATEGORY}")

    hooks = {}
    for key, name, topic, hello in plan(cfg):
        ch = next((c for c in existing if c.get("type") == 0 and c.get("name") == name), None)
        if ch:
            log(f"  exists:           {name}")
        else:
            ch = api(token, "POST", f"/guilds/{gid}/channels", {
                "name": name, "type": 0, "parent_id": cat["id"], "topic": topic,
                "permission_overwrites": [{"id": gid, "type": 0, "allow": "0", "deny": str(READ_ONLY_DENY)}]})
            created.append(name)
            log(f"  created:          {name}")
        current = api(token, "GET", f"/channels/{ch['id']}/webhooks") or []
        hook = next((h for h in current if h.get("name") == HOOK_NAME and h.get("token")), None)
        new_hook = hook is None
        if new_hook:
            hook = api(token, "POST", f"/channels/{ch['id']}/webhooks", {"name": HOOK_NAME})
        link = f"https://discord.com/api/webhooks/{hook['id']}/{hook['token']}"
        hooks[key] = link
        if new_hook:
            api(token, "POST", "", {"username": HOOK_NAME, "content": hello, "allowed_mentions": {"parse": []}},
                auth=False, url=link + "?wait=true")
        log(f"  webhook ready:    {name}")
    return {"guild": guild.get("name", ""), "hooks": hooks, "ping": f"<@&{role['id']}>", "created": created}


def save(hooks, ping):
    """Store the webhooks and the role in secrets.json (made if it isn't there), which the bot reads like
    config.json but which is never uploaded anywhere, so the links can't end up on GitHub if config.json
    is copied there. Keeps a backup. Returns the file name."""
    sec = read_json(SECRETS_PATH)
    if sec is None:
        sec = {}
    if not isinstance(sec, dict):
        raise SetupError("secrets.json isn't a {...} JSON file, so the webhooks couldn't be saved in it.")
    target = sec["alerts"] if isinstance(sec.get("alerts"), dict) else sec      # same layout the file already uses
    if os.path.exists(SECRETS_PATH):
        shutil.copyfile(SECRETS_PATH, SECRETS_PATH + ".before-pokemon.bak")
    old = target.get("pokemon_webhooks") if isinstance(target.get("pokemon_webhooks"), dict) else {}
    target["pokemon_webhooks"] = {**old, **hooks}
    target["pokemon_ping"] = ping
    tmp = SECRETS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sec, f, indent=1, ensure_ascii=False)
    os.replace(tmp, SECRETS_PATH)
    return os.path.basename(SECRETS_PATH)


def github_values(hooks, ping):
    """The two GitHub secrets for the cloud copy."""
    return {"POKEMON_WEBHOOKS": json.dumps(hooks, separators=(",", ":")), "POKEMON_PING": ping}


def find_token(cfg, sec):
    env = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if env:
        return env
    for src in (sec, cfg):
        if isinstance(src, dict):
            for d in (src.get("alerts") if isinstance(src.get("alerts"), dict) else {}, src):
                tok = str(d.get("discord_bot_token") or "").strip()
                if tok:
                    return tok
    print("Couldn't find the bot token in config.json or secrets.json.")
    print("Paste it and press Enter (it stays hidden, and isn't saved):")
    return getpass.getpass("Token: ").strip().strip('"')


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    cfg = read_json(CONFIG_PATH)
    if not isinstance(cfg, dict):
        print("config.json isn't in this folder. Put add_pokemon_channels.py next to tcg_bot.py and run it there.")
        return 1
    token = find_token(cfg, read_json(SECRETS_PATH))
    if not token:
        print("No token entered.")
        return 1
    try:
        print("\nAdding the Pokémon section...\n")
        res = setup(token, cfg=cfg)
        where = save(res["hooks"], res["ping"])
    except SetupError as e:
        print(f"\n{e}")
        return 1
    print(f"\n  Saved the Pokémon webhooks and role in {where} (backup: {where}.before-pokemon.bak).")
    print("\nDone. The restock bot picks them up on its next check (no restart needed).\n")
    print("So the cloud copy posts there too: GitHub > onepiece-restock > Settings > Secrets and variables >")
    print("Actions > New repository secret, once for each (or update them if they're already there):\n")
    for name, value in github_values(res["hooks"], res["ping"]).items():
        print(f"    Name:   {name}")
        print(f"    Secret: {value}\n")
    print("Keep those links private: anyone with one can post in that channel.")
    print("Give yourself the Pokémon Ping role (Server Settings > Members) to get pinged.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nStopped.")
