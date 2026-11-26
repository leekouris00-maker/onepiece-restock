"""Evening streak reminder for the One Piece Market app (27 Nov 2026).

Runs once each evening (.github/workflows/streak-reminder.yml, ~7pm Melbourne in summer). Sends ONE phone
notification to people who turned the reminder on in Rewards, checked in yesterday, haven't checked in today,
and have a streak of 2+ days. Nobody else gets anything; no guilt wording, just the fact and a link.

Needs SUPABASE_URL and SUPABASE_SERVICE_KEY, the notification tables (market-app/supabase/2026-11-24.sql) and
market-app/supabase/2026-11-27-bounty.sql (notify_prefs + streak_reminders()). `--dry` lists who would get one.
"""
import argparse
import os
import sys
import urllib.parse

from push_alerts import SITE, sb, send


def message(streak):
    return {
        "title": f"Your {streak}-day streak ends at midnight",
        "body": "Today's Morning Log is ready: your movers, ban news and events. +10 points.",
        "url": SITE + "rewards",
        "tag": "streak",
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="list who would get a reminder; send nothing")
    a = ap.parse_args(argv)
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY"):
        print("::notice::SUPABASE_URL / SUPABASE_SERVICE_KEY not set: no reminders sent")
        return 0
    try:
        rows = sb("POST", "rpc/streak_reminders", {}) or []
    except RuntimeError as e:
        print(f"::notice::reminders not set up yet (run market-app/supabase/2026-11-27-bounty.sql): {e}")
        return 0
    print(f"{len(rows)} people to remind")
    if not rows or a.dry:
        for r in rows:
            print("  would remind", r["user_id"][:8], "streak", r["streak"])
        return 0
    have = {x["name"]: x["value"] for x in sb("GET", "app_keys?select=name,value&name=eq.vapid_private") or []}
    pem = have.get("vapid_private")
    if not pem:
        print("::notice::no notification key yet (the price-alert job makes it): nothing sent")
        return 0
    ids = ",".join(r["user_id"] for r in rows)
    subs = sb("GET", "push_subs?select=endpoint,user_id,sub&user_id=in.(" + ids + ")") or []
    streak = {r["user_id"]: r["streak"] for r in rows}
    sent = 0
    for s in subs:
        res = send(pem, s["sub"], message(streak[s["user_id"]]))
        if res == "gone":
            sb("DELETE", "push_subs?endpoint=eq." + urllib.parse.quote(s["endpoint"], safe=""))
        elif res == "ok":
            sent += 1
        else:
            print("  ", res)
    print(f"sent {sent} reminders")
    return 0


if __name__ == "__main__":
    sys.exit(main())
