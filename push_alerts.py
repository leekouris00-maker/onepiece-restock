"""Price-alert phone notifications for the One Piece Market app.

Runs on GitHub each morning after the price files update (.github/workflows/push-alerts.yml):
  1. makes the notification key pair once and keeps the private half in the app's database (table app_keys,
     readable only with the service key); the public half goes in push_public_key.txt for the app;
  2. checks every watchlist price alert against today's prices (same rule as the app: eBay sold median when
     there are 3+ sales and it isn't 4x off TCGplayer, else TCGplayer market), in A$;
  3. sends one notification per alert when it's first crossed (remembered in watchlist.notified), and
     forgets it again once the price moves back, so it can fire next time.

Needs SUPABASE_URL and SUPABASE_SERVICE_KEY (already repo secrets for ebay_comps.py) and the tables from
market-app/supabase/2026-11-24.sql. `--test` sends a "notifications are on" message to every phone.
"""
import argparse
import base64
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SITE = "https://leekouris00-maker.github.io/onepiece-restock/"
HERE = os.path.dirname(os.path.abspath(__file__))


def key_kind(key):
    """What sort of Supabase key the secret holds (never prints the key itself)."""
    if key.startswith("sb_secret_"):
        return "secret key"
    if key.startswith("sb_publishable_"):
        return "PUBLISHABLE key (public, can't read other people's rows)"
    if key.count(".") == 2:
        try:
            part = key.split(".")[1]
            role = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))).get("role")
            return f"legacy JWT key, role={role}"
        except Exception:  # noqa: BLE001
            return "unreadable JWT"
    return "unknown format"


def sb(method, path, body=None, prefer=None):
    url = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/" + path
    key = os.environ["SUPABASE_SERVICE_KEY"].strip()
    h = {"apikey": key, "Content-Type": "application/json"}
    if key.count(".") == 2:          # legacy JWT keys also go in Authorization; new sb_secret_ keys only in apikey
        h["Authorization"] = "Bearer " + key
    if prefer:
        h["Prefer"] = prefer
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            t = r.read().decode()
            return json.loads(t) if t.strip() else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path}: {e.code} {e.read().decode()[:300]}")


def keys():
    """VAPID key pair: (private PEM, public key for the app). Made once, kept in app_keys."""
    rows = sb("GET", "app_keys?select=name,value&name=in.(vapid_private,vapid_public)")
    have = {r["name"]: r["value"] for r in rows or []}
    if "vapid_private" in have and "vapid_public" in have:
        return have["vapid_private"], have["vapid_public"]
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    k = ec.generate_private_key(ec.SECP256R1())
    pem = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    pub = k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    pub64 = base64.urlsafe_b64encode(pub).decode().rstrip("=")
    sb("POST", "app_keys", [{"name": "vapid_private", "value": pem}, {"name": "vapid_public", "value": pub64}], prefer="resolution=merge-duplicates")
    print("made a new notification key pair")
    return pem, pub64


def prices():
    cat = json.load(open(os.path.join(HERE, "market_catalog.json")))
    try:
        comps = json.load(open(os.path.join(HERE, "ebay_comps.json"))).get("items", {})
    except FileNotFoundError:
        comps = {}
    fx = cat["meta"].get("fx") or 1.5
    cards = {"t:" + c[0]: {"num": c[2], "name": c[3], "m": c[6]} for c in cat["cards"]}

    def ref_usd(k):
        c, e = cards.get(k), comps.get(k)
        m = c["m"] if c else None
        med = e.get("median") if e and not e.get("none") else None
        off = med is not None and m is not None and m >= 3 and (med < m / 4 or med > m * 4)
        if med is not None and (e.get("count") or 0) >= 3 and not off:
            return med
        if m is not None:
            return m
        return med if med is not None and not off else None

    return cards, ref_usd, fx


def send(pem, sub, payload):
    from py_vapid import Vapid
    from pywebpush import WebPushException, webpush
    try:
        webpush(subscription_info=sub, data=json.dumps(payload), vapid_private_key=Vapid.from_pem(pem.encode()), vapid_claims={"sub": "https://leekouris00-maker.github.io"}, ttl=86400)
        return "ok"
    except WebPushException as e:
        code = getattr(e.response, "status_code", None)
        return "gone" if code in (404, 410) else f"error {code}: {str(e)[:120]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="send a test message to every phone")
    a = ap.parse_args()
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY"):
        print("::notice::SUPABASE_URL / SUPABASE_SERVICE_KEY not set: no notifications sent")
        return 0
    print("database key:", key_kind(os.environ["SUPABASE_SERVICE_KEY"].strip()))
    try:
        pem, pub = keys()
    except RuntimeError as e:
        print(f"::notice::notification tables not set up yet (run market-app/supabase/2026-11-24.sql): {e}")
        return 0
    path = os.path.join(HERE, "push_public_key.txt")
    if not os.path.exists(path) or open(path).read().strip() != pub:
        open(path, "w").write(pub + "\n")
        print("wrote push_public_key.txt")

    subs = sb("GET", "push_subs?select=endpoint,user_id,sub") or []
    by_user = {}
    for s in subs:
        by_user.setdefault(s["user_id"], []).append(s)
    print(f"{len(subs)} phones signed up for notifications")

    def deliver(uid, payload):
        n = 0
        for s in by_user.get(uid, []):
            r = send(pem, s["sub"], payload)
            if r == "gone":
                sb("DELETE", "push_subs?endpoint=eq." + urllib.parse.quote(s["endpoint"], safe=""))
            elif r == "ok":
                n += 1
            else:
                print("  ", r)
        return n

    if a.test:
        for uid in by_user:
            print("test →", deliver(uid, {"title": "Notifications are on", "body": "Your price alerts will arrive here.", "url": SITE, "tag": "test"}))
        return 0

    cards, ref_usd, fx = prices()
    rows = sb("GET", "watchlist?select=user_id,card,below,above,notified") or []
    sent = 0
    for w in rows:
        k = w["card"]
        if not k.startswith("t:") or (w.get("below") is None and w.get("above") is None):
            continue
        usd = ref_usd(k)
        if usd is None:
            continue
        aud = usd * fx
        hit = "below" if w.get("below") is not None and aud <= float(w["below"]) else "above" if w.get("above") is not None and aud >= float(w["above"]) else None
        q = f"watchlist?user_id=eq.{w['user_id']}&card=eq.{urllib.parse.quote(k, safe='')}"
        if hit and w.get("notified") != hit:
            c = cards.get(k, {"name": k, "num": ""})
            at = float(w[hit])
            payload = {"title": f"{c['name']} {'dropped to' if hit == 'below' else 'rose to'} A${aud:,.2f}",
                       "body": f"{c['num']} · your alert was A${at:,.2f}", "url": SITE + "card/" + k, "tag": k}
            n = deliver(w["user_id"], payload)
            sent += n
            if n:
                sb("PATCH", q, {"notified": hit, "notified_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
            print(f"{c['num']} {hit} {aud:.2f} → {n} phones")
        elif not hit and w.get("notified"):
            sb("PATCH", q, {"notified": None, "notified_at": None})
    print(f"sent {sent} notifications")
    return 0


if __name__ == "__main__":
    sys.exit(main())
