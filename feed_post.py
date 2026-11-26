"""Send the restock bot's finds to the One Piece Market app's Restocks feed (27 Nov 2026).

Only shop stock that anyone could buy goes out: booster boxes, sealed and new listings that are buyable,
One Piece only. Never singles, deal-finder picks, watched links or anything to do with auto-buy, and never
shops that are refusing the bot (only shops that let it in).

The bot uses its own feed key (config "app_feed_token", or env APP_FEED_TOKEN), not the database's master key.
The database only accepts it once the key's fingerprint is saved as app_keys 'bot_feed_sha'.
Call post(cfg, finds, refused_shops) after the Discord alerts; it never raises.
"""
import datetime
import json
import os
import re
import urllib.request

SUPABASE_URL = "https://drcrswtieglukyfgotgj.supabase.co"


def kind_of(name, bot_kind=""):
    n = (name or "").lower()
    if bot_kind == "Booster box":
        return "case" if "case" in n else "box"
    if "case" in n:
        return "case"
    if re.search(r"booster box|display|\bbox\b", n):
        return "box"
    if re.search(r"starter deck|\bdeck\b", n):
        return "deck"
    if re.search(r"pack|sleeve|blister", n):
        return "pack"
    if "promo" in n:
        return "promo"
    return "other"


def rows_for(finds, refused=(), today=None):
    """Feed rows for finds the public can buy. refused = shop names refusing the bot right now (skipped)."""
    today = today or datetime.date.today().isoformat()
    refused = {str(s).lower() for s in refused or ()}
    out, seen = [], set()
    for f in finds or ():
        kind = f.get("kind")
        if kind not in ("Booster box", "Sealed", "New listing"):
            continue                                        # singles, value picks, price drops: not restocks
        if f.get("game") not in (None, "", "onepiece", "op") or f.get("link_watch") or f.get("value_pick") or f.get("auto_buy"):
            continue
        if kind == "New listing" and not f.get("opened") and not f.get("price"):
            continue                                        # listed but not buyable yet
        url = str(f.get("url") or "")
        if not url.startswith("https://") or str(f.get("shop", "")).lower() in refused:
            continue
        ext = f"bot:{f.get('id') or url}:{today}"
        if ext in seen:
            continue
        seen.add(ext)
        name = str(f.get("name") or "").strip()
        if f.get("group") == "jp" and "japanese" not in name.lower():
            name = "Japanese " + name
        out.append({"ext_id": ext[:200], "title": name[:120], "kind": kind_of(name, kind),
                    "price": f"{float(f['price']):.2f}" if f.get("price") else "",
                    "store": str(f.get("shop") or "")[:80], "state": "ONLINE", "url": url})
    return out


def _token(cfg):
    return (cfg or {}).get("app_feed_token") or os.environ.get("APP_FEED_TOKEN") or ""


def _anon_key(cfg):
    return (cfg or {}).get("app_anon_key") or os.environ.get("APP_ANON_KEY") or ""


def post(cfg, finds, refused=(), opener=None):
    """Send to the feed. Returns how many new posts were added, or None if switched off / failed."""
    token, key = _token(cfg), _anon_key(cfg)
    if not token or not key or not (cfg or {}).get("app_feed", True):
        return None
    rows = rows_for(finds, refused)
    if not rows:
        return 0
    req = urllib.request.Request(
        ((cfg or {}).get("app_url") or SUPABASE_URL).rstrip("/") + "/rest/v1/rpc/bot_post_restock",
        data=json.dumps({"token": token, "rows": rows[:50]}).encode(),
        headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
    try:
        with (opener or urllib.request.urlopen)(req, timeout=15) as r:
            return int(json.loads(r.read().decode() or "0"))
    except Exception as e:  # noqa: BLE001 - the feed must never break the bot's own alerts
        print("app feed: not sent:", str(e)[:160])
        return None
