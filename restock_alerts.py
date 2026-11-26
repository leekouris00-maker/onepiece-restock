"""Restock alerts for the One Piece Market app (27 Nov 2026).

Sends a phone notification for each new post on the Restocks feed (Market > Restocks) to the people whose
restock alert choices match it (kind, top price, states, source). The database picks who and remembers who
was sent what (restock_targets), so running this twice never sends twice.

Runs from .github/workflows/restock-alerts.yml (every few minutes, as often as GitHub allows) and from the
restock bot on the PC after each check (quicker when the PC is on).

Needs SUPABASE_URL and SUPABASE_SERVICE_KEY, the notification tables (market-app/supabase/2026-11-24.sql)
and market-app/supabase/2026-11-27-restocks.sql. `--dry` lists what would be sent without sending or marking.
`--loop SECONDS --minutes N` keeps checking for N minutes.
"""
import argparse
import datetime
import os
import sys
import time
import urllib.parse

from push_alerts import SITE, sb, send

LOOKBACK_HOURS = 3
SOURCE_WORDS = {"sighting": "seen by a collector", "shop": "posted by the shop", "bot": "found by our watcher"}


def message(p):
    price = f" · A${p['price']:,.0f}" if p.get("price") else ""
    where = " ".join(x for x in [p.get("store"), p.get("suburb"), "Online" if p.get("state") == "ONLINE" else p.get("state")] if x)
    return {
        "title": f"{p['title']}{price}",
        "body": f"{where} · {SOURCE_WORDS.get(p.get('source'), 'restock')}",
        "url": SITE + "market?tab=restocks",
        "tag": "restock-" + p["id"],
    }


def new_posts(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    since = (now - datetime.timedelta(hours=LOOKBACK_HOURS)).isoformat()
    q = ("restock_posts?select=id,source,title,price,store,suburb,state,kind,user_id"
         "&hidden=eq.false&gone_at=is.null&created_at=gte." + urllib.parse.quote(since) + "&order=created_at.asc")
    return sb("GET", q) or []


def run_once(pem, dry=False):
    sent = 0
    for p in new_posts():
        if dry:
            print("  post", p["id"][:8], p["title"])
            continue
        users = [r["user_id"] for r in (sb("POST", "rpc/restock_targets", {"pid": p["id"]}) or [])]
        if not users:
            continue
        subs = sb("GET", "push_subs?select=endpoint,user_id,sub&user_id=in.(" + ",".join(users) + ")") or []
        payload = message(p)
        for s in subs:
            res = send(pem, s["sub"], payload)
            if res == "gone":
                sb("DELETE", "push_subs?endpoint=eq." + urllib.parse.quote(s["endpoint"], safe=""))
            elif res == "ok":
                sent += 1
            else:
                print("  ", res)
        print(f"  {p['title']}: {len(users)} people")
    return sent


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--loop", type=int, default=0, help="seconds between checks (0 = once)")
    ap.add_argument("--minutes", type=float, default=0, help="how long to keep looping")
    a = ap.parse_args(argv)
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY"):
        print("::notice::SUPABASE_URL / SUPABASE_SERVICE_KEY not set: no restock alerts sent")
        return 0
    try:
        keys = {x["name"]: x["value"] for x in sb("GET", "app_keys?select=name,value&name=eq.vapid_private") or []}
        new_posts()
    except RuntimeError as e:
        print(f"::notice::restocks not set up yet (run market-app/supabase/2026-11-27-restocks.sql): {e}")
        return 0
    pem = keys.get("vapid_private")
    if not pem and not a.dry:
        print("::notice::no notification key yet (the price-alert job makes it): nothing sent")
        return 0
    end = time.time() + a.minutes * 60
    while True:
        try:
            n = run_once(pem, a.dry)
            if n:
                print(f"sent {n} restock alerts")
        except RuntimeError as e:
            print("::warning::", e)
        if not a.loop or time.time() + a.loop > end:
            break
        time.sleep(a.loop)
    return 0


if __name__ == "__main__":
    sys.exit(main())
