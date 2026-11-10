import os, sys, re
sys.path.insert(0, os.getcwd())
import netguard, captcha_watch
orig = netguard.on_response
seen = {}
def wrap(url, status, headers, body):
    kind = captcha_watch.detect(status, headers, body)
    if kind and len(seen) < 6 and status not in seen.get("_s", set()) | set():
        host = re.sub(r"^https?://([^/]+).*", r"\1", url)
        if host not in seen:
            seen[host] = 1
            text = (body or b"")[:60000].decode("utf-8", "replace")
            print(f"\n######## {status} {host} kind={kind}")
            print("headers:", {k: v for k, v in dict(headers or {}).items() if k.lower() in ("server", "cf-mitigated", "content-type", "retry-after", "cf-ray", "x-shopid", "x-request-id")})
            low = text.lower()
            for m in ("/cdn-cgi/challenge-platform", "cf_chl_opt", "cf-chl-", "challenges.cloudflare.com", "just a moment", "turnstile", "too many requests", "jsd/main.js"):
                i = low.find(m)
                print(f"  {m!r}: {'-' if i < 0 else repr(text[max(0, i - 80):i + 120])}")
            print("  size", len(body or b""), "title:", re.findall(r"<title>(.*?)</title>", text, re.S)[:1])
    return orig(url, status, headers, body)
netguard.on_response = wrap
import tcg_bot
sys.argv = ["tcg_bot.py", "--pace", "3"]
tcg_bot.main()
