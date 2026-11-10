set -u
python - <<'P'
import json
c = json.load(open("config.json"))
c["security"] = {"enabled": True, "files": {"enforce": True}, "allowlist": {"enforce": True, "max_violations": 50}}
json.dump(c, open("config.json", "w"), indent=2)
P
rm -f security_events.jsonl
timeout 600 python tcg_bot.py --pace 3 > out.txt 2>&1; echo "exit $?"
echo "== check summary"; grep -iE "checked|shops? (down|ok)|^Restock check|took" out.txt | tail -6
echo "== security events"
python - <<'P'
import json, collections
ev = [json.loads(l) for l in open("security_events.jsonl")] if __import__("os").path.exists("security_events.jsonl") else []
print(collections.Counter(e["event"] for e in ev))
for e in ev:
    if e["event"] != "security_on": print(json.dumps(e)[:300])
P
echo "== errors"; grep -iE "traceback|error|blocked|captcha|permission" out.txt | head -30
echo "== hosts the bot reached"; python - <<'P'
import json; s = json.load(open("status.json")); print(len(s.get("shops", s.get("health", {})) or {}), "shop entries in status")
P
P2=1
