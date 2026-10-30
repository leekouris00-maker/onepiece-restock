#!/usr/bin/env python3
"""
Add the bot's extra channels to the One Piece TCG Discord server (run once; safe to run again)
==============================================================================================

Creates, under 🚨 RESTOCK ALERTS:
  🛒・ebay-resale        eBay finds from ebay_watch.json (Nike TNs, Nike DON!! cards, graded promos)
  🤖・bot-status         the bot's own notices: shop not loading / back, drop mode on/off, PC went quiet
  📈・tcgplayer-prices   the daily TCGplayer price report (v2.8, tcgplayer.py)
  📍・onepiece-in-store  v2.10: "tomorrow in stores" / "out today" on release days, and /onepiece report sightings

All are read-only for members (the bot and its webhooks can still post). It makes a webhook for
each, saves them where your other webhooks are (config.json or secrets.json), and posts a hello in
each channel so you can see it worked. Then it prints the values to add to GitHub, so the cloud
copy uses the same channels.

Double-click add_channels.bat, or:  py -3 add_channels.py      (or `/onepiece setup` in Discord)
Uses the bot token already saved for the Discord commands; asks for it only if it can't find it.
Safe to run again: channels and webhooks that already exist are reused.
"""
import getpass
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request

API = "https://discord.com/api/v10"
UA = "DiscordBot (https://github.com/leekouris00-maker/onepiece-restock, 1.0)"
HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
SECRETS_PATH = os.path.join(HERE, "secrets.json")

CATEGORY = "🚨 RESTOCK ALERTS"
SEND_MESSAGES = 1 << 11
CREATE_THREADS = (1 << 35) | (1 << 36)
READ_ONLY_DENY = SEND_MESSAGES | CREATE_THREADS
HOOK_NAME = "One Piece Restock"

# (channel name, topic, alerts key, GitHub secret name, hello message)
CHANNELS = [
    ("🛒・ebay-resale", "Bot: eBay listings at or under your max, delivered (ebay_watch.json).",
     "discord_webhook_ebay", "DISCORD_WEBHOOK_EBAY",
     "🛒 **eBay finds will post here**: the Nike x One Piece TNs (US 10), the Nike DON!! cards and "
     "anything else in ebay_watch.json, once it's listed at or under your max, delivered."),
    ("🤖・bot-status", "Bot: shop not loading / back, drop mode, PC copy on or off. No pings.",
     "discord_webhook_status", "DISCORD_WEBHOOK_STATUS",
     "🤖 **Bot status will post here** from now on (shops down or back, drop mode, the PC going quiet), "
     "so the alert channels only have finds in them."),
    ("📈・tcgplayer-prices", "Bot: daily TCGplayer (US) market prices in A$ - movers, AU shop deals, boxes. No pings.",
     "discord_webhook_prices", "DISCORD_WEBHOOK_PRICES",
     "📈 **The daily TCGplayer price report will post here** (about 7:45am): biggest movers, singles cheaper "
     "at the AU shops than TCGplayer's market, booster box prices and your want list. Look anything up with "
     "`/tcgp`, e.g. `/tcgp OP13-120`."),
    ("📍・onepiece-in-store", "In-store One Piece drops: the night before a release, 7am on the day (pings), and "
     "/onepiece report sightings.",
     "discord_webhook_instore", "DISCORD_WEBHOOK_INSTORE",
     "📍 **In-store One Piece drops post here**: the night before a release (\"tomorrow in stores\") and at 7am "
     "on the day (\"out today\", with a ping), listing what's out, which shops have it online right now and "
     "where to look on a shelf. Spotted stock in a store? Type `/onepiece report` anywhere in the server and it "
     "posts here for everyone. `/onepiece releases` shows the calendar."),
]

ONEPIECE_KEYS = ("discord_webhook_instore",)        # what `/onepiece setup` in Discord makes (the rest need the .bat)


class SetupError(Exception):
    pass


try:
    sys.stdout.reconfigure(errors="replace")      # an old console can't print emoji: show ? instead of crashing
except Exception:  # noqa: BLE001
    pass


def read_json(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def _urlopen(req, timeout=20):
    return urllib.request.urlopen(req, timeout=timeout)


def api(token, method, path, body=None, auth=True, url=None):
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
                                 "one in config.json (\"discord_bot_token\") or secrets.json, and run this again.")
            if e.code == 403:
                raise SetupError("Discord says the bot isn't allowed to make channels or webhooks. In Server Settings > "
                                 "Roles, give the bot's role Administrator (or Manage Channels + Manage Webhooks).")
            raise SetupError(f"Discord error {e.code} on {method} {path}: {text[:300]}")
        except urllib.error.URLError as e:
            raise SetupError(f"Couldn't reach Discord ({e.reason}). Check the internet and try again.")
    raise SetupError("Discord kept rate-limiting. Wait a minute and run this again.")


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


def setup(token, guild_id=None, only=None, log=print, ask=True):
    """Make whatever's missing (every channel in CHANNELS, or just the alerts keys in `only`).
    -> {"guild", "hooks": {alerts key: (link, secret name, channel name)}, "created": [names]}"""
    guild = pick_guild(token, guild_id, ask)
    gid = guild["id"]
    created = []
    existing = api(token, "GET", f"/guilds/{gid}/channels") or []
    cat = next((c for c in existing if c.get("type") == 4 and c.get("name") == CATEGORY), None)
    if cat is None:
        cat = api(token, "POST", f"/guilds/{gid}/channels", {"name": CATEGORY, "type": 4})
        created.append(f"category {CATEGORY}")
        log(f"  category created: {CATEGORY}")

    hooks = {}
    for name, topic, key, secret, hello in CHANNELS:
        if only and key not in only:
            continue
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
        url = f"https://discord.com/api/webhooks/{hook['id']}/{hook['token']}"
        hooks[key] = (url, secret, name)
        if new_hook:
            api(token, "POST", "", {"username": HOOK_NAME, "content": hello, "allowed_mentions": {"parse": []}},
                auth=False, url=url + "?wait=true")
        log(f"  webhook ready:    {name}")
    return {"guild": guild.get("name", ""), "hooks": hooks, "created": created}


def save(hooks, cfg=None, sec=None):
    """Save next to the other webhooks: secrets.json if that's where they are, otherwise config.json.
    Keeps a backup. Returns the file name."""
    cfg = cfg if cfg is not None else (read_json(CONFIG_PATH) or {})
    sec = sec if sec is not None else read_json(SECRETS_PATH)
    sec_alerts = sec.get("alerts", sec) if isinstance(sec, dict) else None
    use_secrets = isinstance(sec_alerts, dict) and any(str(k).startswith("discord_webhook") for k in sec_alerts)
    path, data = (SECRETS_PATH, sec) if use_secrets else (CONFIG_PATH, cfg)
    target = sec_alerts if use_secrets else data.setdefault("alerts", {})
    if os.path.exists(path):
        shutil.copyfile(path, path + ".before-channels.bak")
    for key, (url, _, _) in hooks.items():
        target[key] = url
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    return os.path.basename(path)


def github_values(hooks):
    """{GitHub secret name: link} for the cloud copy."""
    return {secret: url for url, secret, _ in hooks.values()}


def main():
    cfg = read_json(CONFIG_PATH)
    if not isinstance(cfg, dict):
        print("config.json isn't in this folder. Put add_channels.py next to tcg_bot.py and run it there.")
        return 1
    sec = read_json(SECRETS_PATH)
    token = find_token(cfg, sec)
    if not token:
        print("No token entered.")
        return 1
    try:
        print("\nAdding the bot's channels...\n")
        res = setup(token)
        where = save(res["hooks"], cfg, sec)
    except SetupError as e:
        print(f"\n{e}")
        return 1
    print(f"\n  Saved the webhooks in {where} (a backup is in {where}.before-channels.bak).")
    print("\nDone. Two more steps:\n")
    print("  1. Restart the bot so it picks them up: double-click restart_bot.bat\n")
    print("  2. So the cloud copy uses them too: GitHub > onepiece-restock > Settings >")
    print("     Secrets and variables > Actions > New repository secret, once for each:\n")
    for secret, url in github_values(res["hooks"]).items():
        print(f"       Name:   {secret}")
        print(f"       Secret: {url}\n")
    print("  Keep those links private: anyone with one can post in that channel.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nStopped.")
