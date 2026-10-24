#!/usr/bin/env python3
"""
Add the bot's extra channels to the One Piece TCG Discord server (run once)
===========================================================================

Creates, under 🚨 RESTOCK ALERTS:
  🛒・ebay-resale   eBay finds from ebay_watch.json (Nike TNs, Nike DON!! cards, graded promos)
  🤖・bot-status    the bot's own notices: shop not loading / back, drop mode on/off, PC went quiet
  📈・tcgplayer-prices  the daily TCGplayer price report (v2.8, tcgplayer.py)

All are read-only for members (the bot and its webhooks can still post). It makes a webhook for
each, saves them where your other webhooks are (config.json or secrets.json), and posts a hello in
each channel so you can see it worked. Then it prints the values to add to GitHub, so the cloud
copy uses the same channels.

Double-click add_channels.bat, or:  py -3 add_channels.py
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
]

TOKEN = None
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


def api(method, path, body=None, auth=True, url=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"User-Agent": UA, "Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = f"Bot {TOKEN}"
    for _ in range(6):
        req = urllib.request.Request(url or API + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            if e.code == 429:
                try:
                    wait = float(json.loads(text).get("retry_after", 2))
                except Exception:  # noqa: BLE001
                    wait = 2
                time.sleep(wait + 0.3)
                continue
            if e.code == 401:
                stop("Discord says the bot token is wrong. Reset it in the Developer Portal, put the new one "
                     "in config.json (\"discord_bot_token\"), and run this again.")
            if e.code == 403:
                stop("Discord says the bot isn't allowed to make channels or webhooks. In Server Settings > "
                     "Roles, give the bot's role Administrator (or Manage Channels + Manage Webhooks).")
            stop(f"Discord error {e.code} on {method} {path}: {text[:300]}")
        except urllib.error.URLError as e:
            stop(f"Couldn't reach Discord ({e.reason}). Check the internet and try again.")
    stop("Discord kept rate-limiting. Wait a minute and run this again.")


def stop(msg):
    print("\n" + msg)
    sys.exit(1)


def find_token(cfg, sec):
    for src in (sec, cfg):
        if isinstance(src, dict):
            for d in (src.get("alerts") if isinstance(src.get("alerts"), dict) else {}, src):
                tok = str(d.get("discord_bot_token") or "").strip()
                if tok:
                    return tok
    print("Couldn't find the bot token in config.json or secrets.json.")
    print("Paste it and press Enter (it stays hidden, and isn't saved):")
    return getpass.getpass("Token: ").strip().strip('"')


def pick_guild():
    guilds = api("GET", "/users/@me/guilds")
    if not guilds:
        stop("The bot isn't in any server.")
    if len(guilds) == 1:
        return guilds[0]
    for i, g in enumerate(guilds, 1):
        print(f"  {i}. {g['name']}")
    return guilds[int(input("Which server? Type the number: ").strip()) - 1]


def main():
    global TOKEN
    cfg = read_json(CONFIG_PATH)
    if not isinstance(cfg, dict):
        stop("config.json isn't in this folder. Put add_channels.py next to tcg_bot.py and run it there.")
    sec = read_json(SECRETS_PATH)
    TOKEN = find_token(cfg, sec)
    if not TOKEN:
        stop("No token entered.")

    guild = pick_guild()
    gid = guild["id"]
    print(f"\nAdding channels to '{guild['name']}'...\n")

    existing = api("GET", f"/guilds/{gid}/channels")
    cat = next((c for c in existing if c["type"] == 4 and c["name"] == CATEGORY), None)
    if not cat:
        cat = api("POST", f"/guilds/{gid}/channels", {"name": CATEGORY, "type": 4})
        print(f"  category created: {CATEGORY}")

    hooks = {}
    for name, topic, key, secret, hello in CHANNELS:
        ch = next((c for c in existing if c["type"] == 0 and c["name"] == name), None)
        if ch:
            print(f"  exists:           {name}")
        else:
            ch = api("POST", f"/guilds/{gid}/channels", {
                "name": name, "type": 0, "parent_id": cat["id"], "topic": topic,
                "permission_overwrites": [{"id": gid, "type": 0, "allow": "0", "deny": str(READ_ONLY_DENY)}]})
            print(f"  created:          {name}")
        current = api("GET", f"/channels/{ch['id']}/webhooks") or []
        hook = next((h for h in current if h.get("name") == HOOK_NAME and h.get("token")), None)
        new_hook = hook is None
        if new_hook:
            hook = api("POST", f"/channels/{ch['id']}/webhooks", {"name": HOOK_NAME})
        url = f"https://discord.com/api/webhooks/{hook['id']}/{hook['token']}"
        hooks[key] = (url, secret, name)
        if new_hook:
            api("POST", "", {"content": hello, "allowed_mentions": {"parse": []}}, auth=False, url=url)
        print(f"  webhook ready:    {name}")

    # Save next to the other webhooks: secrets.json if that's where they are, otherwise config.json.
    sec_alerts = sec.get("alerts", sec) if isinstance(sec, dict) else None
    use_secrets = isinstance(sec_alerts, dict) and any(str(k).startswith("discord_webhook") for k in sec_alerts)
    path, data = (SECRETS_PATH, sec) if use_secrets else (CONFIG_PATH, cfg)
    target = sec_alerts if use_secrets else data.setdefault("alerts", {})
    shutil.copyfile(path, path + ".before-channels.bak")
    for key, (url, _, _) in hooks.items():
        target[key] = url
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    print(f"\n  Saved the webhooks in {os.path.basename(path)} "
          f"(a backup is in {os.path.basename(path)}.before-channels.bak).")

    print("\nDone. Two more steps:\n")
    print("  1. Restart the bot so it picks them up: double-click restart_bot.bat\n")
    print("  2. So the cloud copy uses them too: GitHub > onepiece-restock > Settings >")
    print("     Secrets and variables > Actions > New repository secret, once for each:\n")
    for _, (url, secret, _) in hooks.items():
        print(f"       Name:   {secret}")
        print(f"       Secret: {url}\n")
    print("  Keep those links private: anyone with one can post in that channel.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
