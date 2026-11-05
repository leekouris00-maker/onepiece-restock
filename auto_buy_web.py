#!/usr/bin/env python3
"""
Auto-buy dashboard and My collection: a private web page on the PC (v2.11.2, collection v2.11.4)
=================================================================================================

The PC copy of the restock bot serves a small page where you can switch auto-buy off / test / live,
change the spend limits, edit the list of things it looks for, test a link, and see what it tried
(with the checkout screenshots). Its second tab, My collection, lists what you own with what it's worth
now and the change over the week (collection.py).

Open it:  double-click open_autobuy.bat   (it opens http://localhost:8765/?t=<your key> in your browser)

Only this PC can open it, and only with the key in autobuy_web_token.txt (made the first time; never
committed). To open it from your phone on the home Wi-Fi as well, add to config.json:
    "auto_buy": {"web_lan": true}        (then open http://<PC's address>:8765/?t=<key> on the phone)
Other settings: "web_port": 8765, "web": false to switch the page off.
"""
import json
import os
import re
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(HERE, "autobuy_web_token.txt")
DEFAULT_PORT = 8765
MAX_BODY = 16_000
PHOTO_BODY = 2_200_000          # a phone photo, shrunk by the page to about 1000 px, as base64
SHOT_RE = re.compile(r"^[\w.\-]+\.png$")
PHOTO_RE = re.compile(r"^([0-9a-f]{8})\.jpg$")
_server = [None]


def web_settings(cfg):
    raw = (cfg or {}).get("auto_buy") or {}
    raw = raw if isinstance(raw, dict) else {}
    try:
        port = int(raw["web_port"]) if raw.get("web_port") is not None else DEFAULT_PORT
    except (TypeError, ValueError):
        port = DEFAULT_PORT
    return {"on": raw.get("web", True) is not False, "lan": raw.get("web_lan") is True, "port": port}


def token():
    try:
        with open(TOKEN_PATH, encoding="utf-8") as f:
            t = f.read().strip()
        if len(t) >= 20:
            return t
    except OSError:
        pass
    t = secrets.token_urlsafe(24)
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        f.write(t)
    return t


def page_url(cfg, host="localhost"):
    return f"http://{host}:{web_settings(cfg)['port']}/?t={token()}"


def _collection():
    try:
        import collection
        return collection
    except Exception:  # noqa: BLE001
        return None


def make_handler(tb, ab, lan=False):
    key = token()

    class H(BaseHTTPRequestHandler):
        server_version = "autobuy"

        def log_message(self, *a):
            pass

        # -------------------------------------------------------- plumbing
        def _send(self, code, body, ctype="application/json", extra=None):
            raw = body if isinstance(body, bytes) else (json.dumps(body) if ctype == "application/json" else body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith(("text", "application/json")) else ""))
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(raw)

        def _host_ok(self):
            if lan:
                return True
            host = (self.headers.get("Host") or "").split(":")[0].strip("[]").lower()
            return host in ("localhost", "127.0.0.1", "::1")

        def _authed(self, query=None):
            given = self.headers.get("X-Token") or (query or {}).get("t", [""])[0]
            return secrets.compare_digest(str(given), key)

        def _body(self, limit=MAX_BODY):
            n = int(self.headers.get("Content-Length") or 0)
            if n > limit:
                raise ValueError("too much data")
            data = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(data, dict):
                raise ValueError("expected an object")
            return data

        # -------------------------------------------------------- routes
        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {"error": "open this page as localhost"})
            u = urllib.parse.urlsplit(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path in ("/", "/index.html"):
                return self._send(200, PAGE, "text/html", {"Content-Security-Policy":
                                  "default-src 'self'; img-src 'self' data:; style-src 'unsafe-inline' 'self'; "
                                  "script-src 'unsafe-inline' 'self'; connect-src 'self'; frame-ancestors 'none'"})
            if u.path == "/api/state":
                if not self._authed(q):
                    return self._send(401, {"error": "wrong or missing key: open the page with open_autobuy.bat"})
                return self._send(200, ab.snapshot(tb))
            if u.path == "/api/collection":
                if not self._authed(q):
                    return self._send(401, {"error": "wrong or missing key: open the page with open_autobuy.bat"})
                col = _collection()
                if not col:
                    return self._send(500, {"error": "collection.py is missing: run update_bot.bat"})
                return self._send(200, col.snapshot(tb, tb.load_config()))
            if u.path.startswith("/cphoto/"):
                m = PHOTO_RE.match(urllib.parse.unquote(u.path[len("/cphoto/"):]))
                col = _collection()
                if not self._authed(q) or not m or not col:
                    return self._send(404, {"error": "not found"})
                path = col.photo_path(m.group(1))
                if not os.path.isfile(path):
                    return self._send(404, {"error": "not found"})
                with open(path, "rb") as f:
                    return self._send(200, f.read(), "image/jpeg")
            if u.path.startswith("/shot/"):
                name = urllib.parse.unquote(u.path[len("/shot/"):])
                if not self._authed(q) or not SHOT_RE.match(name):
                    return self._send(404, {"error": "not found"})
                path = os.path.join(ab.SHOTS_DIR, name)
                if not os.path.isfile(path):
                    return self._send(404, {"error": "not found"})
                with open(path, "rb") as f:
                    return self._send(200, f.read(), "image/png")
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok():
                return self._send(403, {"error": "open this page as localhost"})
            if not self._authed():
                return self._send(401, {"error": "wrong or missing key: open the page with open_autobuy.bat"})
            path = urllib.parse.urlsplit(self.path).path
            try:
                d = self._body(PHOTO_BODY if path == "/api/collection/photo" else MAX_BODY)
                if path.startswith("/api/collection"):
                    col = _collection()
                    if not col:
                        raise ValueError("collection.py is missing: run update_bot.bat")
                    if path == "/api/collection/item":
                        it = col.upsert(tb, d, tb.load_config())
                        note = ("Saved " if d.get("id") else "Added ") + it["name"] + "."
                    elif path == "/api/collection/remove":
                        col.remove(tb, str(d.get("id") or ""))
                        note = "Removed."
                    elif path == "/api/collection/photo":
                        it = col.set_photo(tb, str(d.get("id") or ""), d.get("data"))
                        d = {"id": d.get("id"), "data": "(photo)"}
                        note = f"Photo saved for {it['name']}."
                    else:
                        return self._send(404, {"error": "not found"})
                    self._audit(path, d)
                    return self._send(200, {"ok": True, "note": note, "collection": col.snapshot(tb, tb.load_config())})
                if path == "/api/mode":
                    ab.set_mode(tb, d.get("mode"), d.get("hours"))
                    note = f"Auto-buy {d.get('mode')}."
                elif path == "/api/limits":
                    ab.set_limits(tb, **{k: d.get(k) for k in ab.LIMITS})
                    note = "Limits saved."
                elif path == "/api/item":
                    it, was = ab.upsert_item(tb, code=str(d.get("code") or "").strip(), match=str(d.get("match") or ""),
                                             max=d.get("max"), qty=d.get("qty") or 1, name=str(d.get("name") or "").strip())
                    note = ("Changed " if was else "Added ") + it["name"] + "."
                elif path == "/api/item/edit":
                    ch = {k: d[k] for k in ("on", "reset", "remove", "max", "qty", "name") if k in d}
                    it = ab.edit_item(tb, str(d.get("id") or ""), **ch)
                    note = "Removed." if it is None else f"Saved {it['name']}."
                elif path == "/api/try":
                    ab.queue_try(tb, d.get("url"))
                    note = "Test queued: within a minute the PC opens the checkout, stops before paying and posts a screenshot."
                else:
                    return self._send(404, {"error": "not found"})
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            except Exception as e:  # noqa: BLE001
                return self._send(500, {"error": f"{type(e).__name__}: {str(e)[:200]}"})
            self._audit(path, d)
            return self._send(200, {"ok": True, "note": note, "state": ab.snapshot(tb)})

        def _audit(self, path, d):
            try:
                tb.append_text(os.path.join(HERE, "commands_audit.log"),
                               f"web page  {path} {json.dumps(d)[:300]}\n", 500_000)
            except Exception:  # noqa: BLE001
                pass

    return H


def start(tb, ab, cfg):
    """Start the page in the background (PC copy). Quietly does nothing if it's off or the port is taken."""
    ws = web_settings(cfg)
    if not ws["on"] or _server[0]:
        return None
    try:
        srv = ThreadingHTTPServer(("0.0.0.0" if ws["lan"] else "127.0.0.1", ws["port"]), make_handler(tb, ab, ws["lan"]))
    except OSError as e:
        print(f"   ! auto-buy page couldn't start on port {ws['port']} ({e}); set \"web_port\" in auto_buy")
        return None
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, name="auto-buy page", daemon=True).start()
    _server[0] = srv
    col = _collection()
    if col and not getattr(tb, "IN_ACTIONS", False) and ws["port"] != 0:
        col.keep_ticking(tb, tb.load_config)   # one price a day for each collection item, page open or not
    print(f"   (auto-buy page on port {srv.server_address[1]} - open_autobuy.bat opens it)")
    return srv


def stop():
    if _server[0]:
        _server[0].shutdown()
        _server[0].server_close()
        _server[0] = None


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Auto-buy</title>
<style>
:root{--bg:#f6f4ef;--card:#fff;--ink:#1d1b18;--mute:#6f6a62;--line:#e6e1d8;--accent:#c8102e;--accent-ink:#fff;
--ok:#1f8a5b;--warn:#b7791f;--bad:#c8102e;--info:#2b6cb0;--chip:#f0ece4;--shadow:0 1px 2px rgba(0,0,0,.05),0 4px 16px rgba(0,0,0,.04)}
@media (prefers-color-scheme:dark){:root{--bg:#141311;--card:#1d1c19;--ink:#f1ede6;--mute:#a39d93;--line:#2e2c28;
--chip:#26241f;--shadow:none;--accent:#e5484d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:20px 16px 60px}
header{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:18px}
h1{font-size:22px;margin:0;letter-spacing:-.01em}h1 small{color:var(--mute);font-weight:500;font-size:13px;margin-left:6px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--mute);margin:0 0 12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;box-shadow:var(--shadow);margin-bottom:16px}
.grid{display:grid;gap:16px;grid-template-columns:1fr}@media(min-width:760px){.grid{grid-template-columns:1fr 1fr}}
.seg{display:inline-flex;background:var(--chip);border-radius:999px;padding:4px;gap:4px}
.seg button{border:0;background:transparent;color:var(--ink);padding:8px 16px;border-radius:999px;font:inherit;font-weight:600;cursor:pointer}
.seg button.on{background:var(--card);box-shadow:0 1px 3px rgba(0,0,0,.12)}
.seg button.on.live{background:var(--accent);color:var(--accent-ink)}
.banner{border-radius:12px;padding:12px 14px;margin-bottom:16px;font-weight:600;display:flex;gap:10px;align-items:center}
.banner.off{background:var(--chip);color:var(--mute)}.banner.test{background:rgba(43,108,176,.12);color:var(--info)}
.banner.live{background:var(--accent);color:var(--accent-ink)}
.meter{margin:10px 0}.meter .row{display:flex;justify-content:space-between;font-size:14px}
.bar{height:8px;border-radius:99px;background:var(--chip);overflow:hidden;margin-top:6px}.bar i{display:block;height:100%;background:var(--ok)}
.bar i.warn{background:var(--warn)}.bar i.bad{background:var(--bad)}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px 6px;border-bottom:1px solid var(--line);vertical-align:middle}
th{font-size:12px;color:var(--mute);font-weight:600;text-transform:uppercase;letter-spacing:.05em}
td input{width:84px}.name{font-weight:600}.sub{color:var(--mute);font-size:13px}
input,select{font:inherit;color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:7px 9px;width:100%}
label{display:block;font-size:13px;color:var(--mute);margin:8px 0 4px}
.btn{font:inherit;font-weight:600;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:9px;padding:8px 12px;cursor:pointer}
.btn.primary{background:var(--ink);color:var(--bg);border-color:var(--ink)}.btn.small{padding:5px 9px;font-size:13px}
.btn.danger{color:var(--bad)}.row2{display:grid;grid-template-columns:1fr 1fr;gap:10px}.actions{display:flex;gap:6px;flex-wrap:wrap}
.pill{display:inline-block;padding:2px 8px;border-radius:99px;font-size:12px;font-weight:700;background:var(--chip)}
.pill.paid{background:rgba(31,138,91,.15);color:var(--ok)}.pill.declined,.pill.stopped{background:rgba(200,16,46,.12);color:var(--bad)}
.pill.test{background:rgba(43,108,176,.14);color:var(--info)}.pill.unclear,.pill.bank,.pill.skipped{background:rgba(183,121,31,.15);color:var(--warn)}
.pill.done{background:rgba(31,138,91,.15);color:var(--ok)}.pill.paused{color:var(--mute)}
.shots{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.shots a{display:block;border:1px solid var(--line);border-radius:10px;overflow:hidden;color:inherit;text-decoration:none}.shots img{display:block;width:100%;height:110px;object-fit:cover;object-position:top}
.shots span{display:block;font-size:12px;color:var(--mute);padding:4px 6px}
.toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);background:var(--ink);color:var(--bg);padding:10px 16px;border-radius:10px;
font-weight:600;opacity:0;transition:opacity .2s;pointer-events:none;max-width:90vw}.toast.show{opacity:1}
.sm-only{display:none}@media(max-width:620px){.sm-only{display:inline}}.err{color:var(--bad)}.muted{color:var(--mute)}.list-attempts div{padding:8px 0;border-bottom:1px solid var(--line);font-size:14px}
@media(max-width:620px){.hide-sm{display:none}thead{display:none}
 #items tr{display:grid;grid-template-columns:1fr 1fr;gap:6px 10px;padding:12px 0;border-bottom:1px solid var(--line)}
 #items td{border:0;padding:0}#items td:first-child,#items td:last-child{grid-column:1/-1}
 #items td input{width:100%}#items td[data-l]::before{content:attr(data-l);display:block;font-size:12px;color:var(--mute);margin-bottom:3px}}
.tabs{display:inline-flex;gap:4px;background:var(--chip);border-radius:12px;padding:4px}
.tabs button{border:0;background:transparent;color:var(--mute);font:inherit;font-weight:700;font-size:16px;padding:8px 14px;border-radius:9px;cursor:pointer}
.tabs button.on{background:var(--card);color:var(--ink);box-shadow:0 1px 3px rgba(0,0,0,.12)}
.hl{display:flex;align-items:center;gap:10px;flex-wrap:wrap}#ver{color:var(--mute);font-size:13px;font-weight:500}
[hidden]{display:none!important}
.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-bottom:16px}@media(min-width:760px){.stats{grid-template-columns:1.4fr 1fr 1fr 1fr}}
.stat{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;box-shadow:var(--shadow)}
.stat .k{font-size:12px;color:var(--mute);text-transform:uppercase;letter-spacing:.06em;font-weight:600}
.stat .v{font-size:24px;font-weight:750;letter-spacing:-.02em;margin-top:4px;font-variant-numeric:tabular-nums}.stat.big .v{font-size:30px}
.stat .s{font-size:13px;color:var(--mute);margin-top:2px}
.up{color:var(--ok)}.down{color:var(--bad)}.flat{color:var(--mute)}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 12px}.chips button{font:inherit;font-size:13px;font-weight:600;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:99px;padding:6px 12px;cursor:pointer}
.chips button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}.chips button span{color:var(--mute);font-weight:500;margin-left:4px}.chips button.on span{color:inherit;opacity:.7}
.cgrid{display:grid;gap:14px;grid-template-columns:1fr;margin-bottom:16px}@media(min-width:620px){.cgrid{grid-template-columns:1fr 1fr}}@media(min-width:900px){.cgrid{grid-template-columns:1fr 1fr 1fr}}
.citem{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:var(--shadow);display:flex;flex-direction:column}
.ph{height:150px;background:var(--chip);display:flex;align-items:center;justify-content:center;font-size:54px;position:relative}
.ph img{width:100%;height:100%;object-fit:cover}.ph .flag{position:absolute;top:10px;left:10px}
.cbody{padding:14px 14px 12px;display:flex;flex-direction:column;gap:6px;flex:1}
.cbody .name{font-size:16px;font-weight:700;line-height:1.25}.tags{font-size:13px;color:var(--mute)}
.pricerow{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-top:4px}
.pricerow b{font-size:22px;letter-spacing:-.02em;font-variant-numeric:tabular-nums}.chg{font-size:14px;font-weight:700;white-space:nowrap}.chg small{font-weight:500;color:var(--mute)}
.spark{display:block;width:100%;height:38px}.src{font-size:12px;color:var(--mute)}.src a{color:inherit}
.facts{display:grid;grid-template-columns:auto 1fr;gap:3px 12px;font-size:13px;margin:6px 0 4px;padding-top:8px;border-top:1px solid var(--line)}
.facts dt{color:var(--mute)}.facts dd{margin:0;text-align:right;font-variant-numeric:tabular-nums}
.citem .actions{margin-top:auto;padding-top:6px}.pill.coming{background:rgba(43,108,176,.14);color:var(--info)}
.empty{text-align:center;padding:30px 16px;color:var(--mute)}.empty b{display:block;color:var(--ink);font-size:17px;margin-bottom:4px}
.row3{display:grid;grid-template-columns:1fr 1fr;gap:10px}@media(min-width:760px){.row3{grid-template-columns:1fr 1fr 1fr}}
fieldset{border:1px dashed var(--line);border-radius:12px;padding:6px 12px 12px;margin:14px 0 0}legend{font-size:13px;font-weight:700;padding:0 6px}
.hint{font-size:12.5px;color:var(--mute);margin:6px 0 0}
</style></head><body><div class="wrap">
<header><div class="hl"><nav class="tabs" id="tabs"><button data-tab="buy" class="on">🤖 Auto-buy</button><button data-tab="col">📦 My collection</button></nav><span id="ver"></span></div>
<div class="seg" id="modes"><button data-m="off">Off</button><button data-m="test">Test</button><button data-m="live" class="livebtn">Live</button></div></header>
<div id="pane-buy">
<div id="banner" class="banner off">Loading…</div>
<div class="grid">
 <section class="card"><h2>Spent</h2><div id="meters"></div></section>
 <section class="card"><h2>Limits</h2>
  <form id="limits"><div class="row2">
   <div><label>Per order (postage included)</label><input name="per_order" inputmode="decimal"></div>
   <div><label>Per day</label><input name="per_day" inputmode="decimal"></div>
   <div><label>Per week (Mon–Sun)</label><input name="per_week" inputmode="decimal"></div>
   <div><label>Per month</label><input name="per_month" inputmode="decimal"></div></div>
   <p style="margin:12px 0 0"><button class="btn primary">Save limits</button></p></form></section>
</div>
<section class="card"><h2>Looking for</h2>
 <table><thead><tr><th>Item</th><th>Max each</th><th>Want</th><th class="hide-sm">Bought</th><th></th></tr></thead><tbody id="items"></tbody></table>
 <form id="add" style="margin-top:14px"><div class="row2">
  <div><label>Set code (booster box)</label><input name="code" placeholder="OP-15, EB-05, PRB-02"></div>
  <div><label>Or words in the name</label><input name="match" placeholder="premium|prb, english"></div>
  <div><label>Most you'd pay each (A$)</label><input name="max" inputmode="decimal" placeholder="240"></div>
  <div><label>How many in total</label><input name="qty" inputmode="numeric" value="1"></div></div>
  <p style="margin:12px 0 0"><button class="btn primary">➕ Add item</button> <span class="muted" style="font-size:13px">Adding one that's already there changes it.</span></p></form>
</section>
<div class="grid">
 <section class="card"><h2>Test a link (never pays)</h2>
  <form id="try"><input name="url" placeholder="https://shop.com.au/products/…"><p style="margin:12px 0 0"><button class="btn">🔗 Run a test checkout</button></p></form>
  <p class="muted" style="font-size:13px">The PC opens the checkout, stops before paying and posts a screenshot in your private 🔒・auto-buy channel.</p></section>
 <section class="card"><h2>Last attempts</h2><div id="recent" class="list-attempts"></div></section>
</div>
<section class="card"><h2>Checkout screenshots</h2><div id="shots" class="shots"></div></section>
</div>
<div id="pane-col" hidden>
 <div class="stats" id="cstats"></div>
 <div class="chips" id="cfilter"></div>
 <div class="cgrid" id="citems"><div class="empty">Loading…</div></div>
 <section class="card" id="cformcard"><h2 id="cformtitle">Add to my collection</h2>
 <form id="cform"><input type="hidden" name="id">
  <label>Name</label><input name="name" required maxlength="80" placeholder="Shanks tin, Nike Gomu Gomu DON!! card…">
  <div class="row3">
   <div><label>Kind</label><select name="kind"></select></div>
   <div><label>Language</label><select name="lang"></select></div>
   <div><label>Condition</label><select name="state"></select></div>
   <div id="gradebox"><label>Grade</label><input name="grade" maxlength="20" placeholder="PSA 10"></div>
   <div><label>How many</label><input name="qty" inputmode="numeric" value="1"></div>
   <div><label>Paid each (A$)</label><input name="paid" inputmode="decimal" placeholder="40"></div>
   <div><label>Got it on</label><input name="got" type="date"></div>
   <div><label>Status</label><select name="status"><option value="have">Have it</option><option value="coming">On its way</option></select></div>
  </div>
  <fieldset><legend>How to price it</legend>
   <div class="row3">
    <div><label>Card number</label><input name="card" maxlength="12" placeholder="OP05-119"></div>
    <div><label>Words to look for at shops</label><input name="match" maxlength="80" placeholder="ts-02 tin · alternate art"></div>
    <div><label>Or your own estimate (A$)</label><input name="value" inputmode="decimal" placeholder="for things shops don't sell"></div>
   </div>
   <p class="hint">Cards: the number, plus words to pick the version. Sealed: words from shop titles. The price is checked every hour and kept once a day, so the week's change builds up; new items start with the last week from the bot's records.</p>
  </fieldset>
  <label>Notes</label><input name="notes" maxlength="300" placeholder="holding sealed, birthday present…">
  <p style="margin:14px 0 0" class="actions"><button class="btn primary" id="csubmit">➕ Add to collection</button><button type="button" class="btn" id="ccancel" hidden>Cancel</button></p>
 </form></section>
 <input type="file" id="cphoto" accept="image/*" hidden>
</div>
</div><div class="toast" id="toast"></div>
<script>
const q=new URLSearchParams(location.search);let KEY=q.get('t')||'';
try{if(KEY){sessionStorage.setItem('abk',KEY);history.replaceState(null,'','/'+location.hash)}else{KEY=sessionStorage.getItem('abk')||''}}catch(e){}
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=v=>'$'+Number(v||0).toLocaleString('en-AU',{minimumFractionDigits:2,maximumFractionDigits:2});
let S=null,editing=false;
function toast(t,bad){const el=$('#toast');el.textContent=t;el.style.background=bad?'var(--bad)':'';el.classList.add('show');clearTimeout(el._t);el._t=setTimeout(()=>el.classList.remove('show'),3200)}
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'X-Token':KEY,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
 const d=await r.json().catch(()=>({error:'bad reply'}));if(!r.ok)throw new Error(d.error||('HTTP '+r.status));return d}
async function act(path,body){try{const d=await api(path,body);toast(d.note||'Saved');S=d.state;render()}catch(e){toast(e.message,true)}}
function when(t){return new Date(t*1000).toLocaleString('en-AU',{weekday:'short',day:'numeric',month:'short',hour:'numeric',minute:'2-digit'})}
function render(){
 $('#ver').textContent=S.version?'v'+S.version:'';
 document.querySelectorAll('#modes button').forEach(b=>{b.classList.toggle('on',b.dataset.m===S.mode);b.classList.toggle('live',b.dataset.m==='live'&&S.mode==='live')});
 const ban=$('#banner');ban.className='banner '+S.mode;
 ban.textContent={off:'⚪ Off: alerts carry on as usual, nothing is bought.',test:'🧪 Test mode: restocks on your list go to the Pay button and stop, with a screenshot.',
  live:'🔴 LIVE: the PC really buys list items that restock within your limits.'}[S.mode]+(S.until&&S.mode!=='off'?'  Until '+when(S.until)+'.':'');
 const L=S.limits,sp=S.spend;
 $('#meters').innerHTML=[['Today','day','per_day'],['This week','week','per_week'],['This month','month','per_month']].map(([n,p,k])=>{
  const v=sp[p].spent,lim=L[k]||0,pct=lim?Math.min(100,v/lim*100):0,c=pct>=100?'bad':pct>=75?'warn':'';
  return `<div class="meter"><div class="row"><span>${n} <span class="muted">· ${sp[p].orders} order(s)</span></span><b>${money(v)} <span class="muted">of ${money(lim)}</span></b></div><div class="bar"><i class="${c}" style="width:${pct}%"></i></div></div>`}).join('')
  +`<p class="muted" style="font-size:13px;margin:10px 0 0">Max ${money(L.per_order)} an order · ${S.orders_per_day} orders a day${S.preorders?'':' · no pre-orders'}</p>`;
 if(!editing){const f=$('#limits');for(const k in L)f.elements[k].value=L[k]}
 $('#items').innerHTML=S.items.length?S.items.map(it=>{const done=it.bought>=it.qty,st=done?'<span class="pill done">done</span>':!it.on?'<span class="pill paused">paused</span>':'<span class="pill">looking</span>';
  const how=it.code?'code '+esc(it.code):'';const words=it.match.length?(how?' + ':'')+'words: '+esc(it.match.join(', ')):'';
  return `<tr data-id="${esc(it.id)}"><td><div class="name">${esc(it.name)} ${st}</div><div class="sub">${how}${words}<span class="sm-only"> · ${it.bought}/${it.qty} bought</span></div></td>
  <td data-l="Max each (A$)"><input data-f="max" value="${it.max}" inputmode="decimal" aria-label="Max each"></td><td data-l="Want in total"><input data-f="qty" value="${it.qty}" inputmode="numeric" aria-label="Want in total"></td>
  <td class="hide-sm">${it.bought}</td><td><div class="actions"><button class="btn small" data-a="save">Save</button>
  <button class="btn small" data-a="toggle">${it.on?'Pause':'Resume'}</button>${it.bought?'<button class="btn small" data-a="reset">Reset</button>':''}
  <button class="btn small danger" data-a="remove">Remove</button></div></td></tr>`}).join(''):'<tr><td colspan="5" class="muted">Nothing on the list yet: add a set code below.</td></tr>';
 $('#recent').innerHTML=S.recent.length?S.recent.slice(0,8).map(o=>`<div><span class="pill ${esc(o.status)}">${esc(o.status)}</span> ${esc(o.name)} <span class="muted">· ${esc(o.shop)} · ${when(o.t)}${o.total?' · '+money(o.total):''}</span>${o.detail&&!['paid','test'].includes(o.status)?`<div class="sub">${esc(o.detail)}</div>`:''}</div>`).join(''):'<p class="muted">Nothing yet.</p>';
 $('#shots').innerHTML=S.shots.length?S.shots.map(n=>{const u='/shot/'+encodeURIComponent(n)+'?t='+encodeURIComponent(KEY);
  return `<a href="${u}" target="_blank" rel="noopener"><img src="${u}" alt="checkout screenshot" loading="lazy"><span>${esc(n.replace(/\.png$/,''))}</span></a>`}).join(''):'<p class="muted">Screenshots of each checkout show up here.</p>';
}
async function load(){try{S=await api('/api/state');render()}catch(e){$('#banner').className='banner off';$('#banner').innerHTML='<span class="err">'+esc(e.message)+'</span>'}}
$('#modes').addEventListener('click',e=>{const m=e.target.dataset.m;if(!m||!S||m===S.mode)return;
 if(m==='live'&&!confirm('Go LIVE? The PC will really pay for list items that restock within your limits.'))return;act('/api/mode',{mode:m})});
$('#limits').addEventListener('focusin',()=>editing=true);
$('#limits').addEventListener('submit',e=>{e.preventDefault();editing=false;const d=Object.fromEntries(new FormData(e.target));act('/api/limits',d)});
$('#add').addEventListener('submit',e=>{e.preventDefault();const d=Object.fromEntries(new FormData(e.target));act('/api/item',d).then(()=>e.target.reset())});
$('#try').addEventListener('submit',e=>{e.preventDefault();act('/api/try',{url:e.target.elements.url.value}).then(()=>e.target.reset())});
$('#items').addEventListener('click',e=>{const a=e.target.dataset.a;if(!a)return;const tr=e.target.closest('tr'),id=tr.dataset.id,it=S.items.find(x=>x.id===id);
 if(a==='save')act('/api/item/edit',{id,max:tr.querySelector('[data-f=max]').value,qty:tr.querySelector('[data-f=qty]').value});
 if(a==='toggle')act('/api/item/edit',{id,on:!it.on});
 if(a==='reset')act('/api/item/edit',{id,reset:true});
 if(a==='remove'&&confirm('Remove '+it.name+'?'))act('/api/item/edit',{id,remove:true})});

// ---------------------------------------------------------------- My collection
const EMOJI={Tin:'🥫',Sealed:'📦',Card:'🃏',Promo:'⭐',Collectible:'🏆',Other:'🎁'};
const PLURAL={Tin:'Tins',Sealed:'Sealed',Card:'Cards',Promo:'Promos',Collectible:'Collectibles',Other:'Other'};
let C=null,TAB='buy',FILTER='all',photoFor=null;
const pct=v=>(v>0?'+':'')+v.toFixed(1)+'%',cls=v=>v>0.05?'up':v<-0.05?'down':'flat',arrow=v=>v>0.05?'▲':v<-0.05?'▼':'■';
const dshort=d=>d?new Date(d+'T00:00').toLocaleDateString('en-AU',{day:'numeric',month:'short'}):'';
function spark(pts,dir){if(!pts||pts.length<2)return '';const v=pts.map(p=>p[1]),lo=Math.min(...v),hi=Math.max(...v),r=hi-lo||1,W=300,H=38;
 const xy=v.map((y,i)=>[(i/(v.length-1))*(W-6)+3,H-4-((y-lo)/r)*(H-10)]),col=dir==='up'?'var(--ok)':dir==='down'?'var(--bad)':'var(--mute)';
 const last=xy[xy.length-1];return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-label="price over the last ${v.length} days"><polyline fill="none" stroke="${col}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" points="${xy.map(p=>p.map(n=>n.toFixed(1)).join(',')).join(' ')}"/><circle cx="${last[0]}" cy="${last[1]}" r="3" fill="${col}"/></svg>`}
function renderCol(){
 const T=C.totals,g=T.gain,gp=T.paid?g/T.paid*100:0;
 $('#cstats').innerHTML=`<div class="stat big"><div class="k">Worth now</div><div class="v">${money(T.worth)}</div><div class="s">${T.items} item(s) · ${T.priced} priced</div></div>
  <div class="stat"><div class="k">Total cost</div><div class="v">${money(T.paid)}</div><div class="s">${T.no_cost?T.no_cost+' item(s) with no price paid':'everything you paid'}</div></div>
  <div class="stat"><div class="k">Up / down</div><div class="v ${cls(g)}">${g<0?'−':'+'}${money(Math.abs(g))}</div><div class="s ${cls(gp)}">${T.paid?pct(gp)+' on what you paid':'&nbsp;'}</div></div>
  <div class="stat"><div class="k">This week</div><div class="v ${T.week_pct==null?'flat':cls(T.week_pct)}">${T.week_pct==null?'—':arrow(T.week_pct)+' '+pct(T.week_pct)}</div><div class="s">${T.week_pct==null?'builds up day by day':'last 7 days'}</div></div>`;
 const counts={};C.items.forEach(i=>counts[i.kind]=(counts[i.kind]||0)+1);
 $('#cfilter').innerHTML=C.items.length?[['all','All',C.items.length],...C.kinds.filter(k=>counts[k]).map(k=>[k,PLURAL[k],counts[k]])].map(([k,n,c])=>`<button data-f="${k}" class="${FILTER===k?'on':''}">${n}<span>${c}</span></button>`).join(''):'';
 const list=C.items.filter(i=>FILTER==='all'||i.kind===FILTER);
 $('#citems').innerHTML=list.length?list.map(i=>{
  const w=i.week,dir=w?cls(w.pct):'flat',q=i.qty||1,gain=(i.now!=null&&i.paid!=null)?(i.now-i.paid)*q:null;
  const img=i.photo?`<img src="/cphoto/${i.id}.jpg?t=${encodeURIComponent(KEY)}&v=${i.photo}" alt="${esc(i.name)}" loading="lazy">`:EMOJI[i.kind]||'🎁';
  const tags=[i.kind,i.lang,i.state==='Graded'&&i.grade?i.grade:i.state,q>1?'×'+q:'',i.card].filter(Boolean).map(esc).join(' · ');
  const src=i.url?`<a href="${esc(i.url)}" target="_blank" rel="noopener noreferrer">${esc(i.source)}${i.where&&i.where!=='TCGplayer'?' · '+esc(i.where):''}</a>`:esc(i.source)+(i.where?' · '+esc(i.where):'');
  return `<article class="citem" data-id="${esc(i.id)}"><div class="ph">${img}${i.status==='coming'?'<span class="pill coming flag">On its way</span>':''}</div><div class="cbody">
   <div class="name">${esc(i.name)}</div><div class="tags">${tags}</div>
   <div class="pricerow"><b>${i.now!=null?money(i.now):'<span class="muted">—</span>'}</b>${w?`<span class="chg ${dir}">${arrow(w.pct)} ${pct(w.pct)} <small>${esc(w.label)}</small></span>`:`<span class="chg flat"><small>${i.source==='your estimate'?'changes when you edit it':i.now!=null?'change shows after a day':''}</small></span>`}</div>
   ${spark(i.spark,dir)}<div class="src">${src}</div>
   <dl class="facts">${i.paid!=null?`<dt>Paid</dt><dd>${money(i.paid)}${q>1?' each':''}${i.got?' · '+dshort(i.got):''}</dd>`:''}
    ${i.start?`<dt>When added</dt><dd>${money(i.start.price)} · ${dshort(i.start.date)}</dd>`:''}
    ${w?`<dt>A week ago</dt><dd>${money(w.from)}</dd>`:''}
    ${gain!=null?`<dt>Up / down</dt><dd class="${cls(gain)}">${gain<0?'−':'+'}${money(Math.abs(gain))}${i.paid?' ('+pct((i.now-i.paid)/i.paid*100)+')':''}</dd>`:''}
    ${i.notes?`<dt>Notes</dt><dd>${esc(i.notes)}</dd>`:''}</dl>
   <div class="actions"><button class="btn small" data-c="edit">Edit</button><button class="btn small" data-c="photo">📷 Photo</button>${i.status==='coming'?'<button class="btn small" data-c="arrived">Arrived</button>':''}<button class="btn small danger" data-c="remove">Remove</button></div>
  </div></article>`}).join(''):`<div class="empty card" style="grid-column:1/-1"><b>Nothing here yet</b>Add your tins, sealed product and special cards below.</div>`;
}
async function loadCol(){try{C=await api('/api/collection');renderCol()}catch(e){$('#citems').innerHTML='<div class="empty err" style="grid-column:1/-1">'+esc(e.message)+'</div>'}}
async function cact(path,body){try{const d=await api(path,body);toast(d.note||'Saved');C=d.collection;renderCol();return true}catch(e){toast(e.message,true);return false}}
function fillSelects(){const f=$('#cform');[['kind',['Tin','Sealed','Card','Promo','Collectible','Other']],['lang',['EN','JP','Other']],['state',['Sealed','Opened','Raw','Graded']]].forEach(([n,o])=>{
 f.elements[n].innerHTML=o.map(x=>`<option>${x}</option>`).join('')});f.elements.state.addEventListener('change',gradeBox);gradeBox()}
function gradeBox(){$('#gradebox').hidden=$('#cform').elements.state.value!=='Graded'}
function resetForm(){const f=$('#cform');f.reset();f.elements.id.value='';$('#cformtitle').textContent='Add to my collection';$('#csubmit').textContent='➕ Add to collection';$('#ccancel').hidden=true;gradeBox()}
function editItem(i){const f=$('#cform');for(const k of ['id','name','kind','lang','state','grade','qty','paid','got','status','card','match','value','notes'])f.elements[k].value=i[k]??'';
 $('#cformtitle').textContent='Edit '+i.name;$('#csubmit').textContent='Save changes';$('#ccancel').hidden=false;gradeBox();$('#cformcard').scrollIntoView({behavior:'smooth'})}
function showTab(t){TAB=t;document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on',b.dataset.tab===t));
 $('#pane-buy').hidden=t!=='buy';$('#pane-col').hidden=t!=='col';$('#modes').hidden=t!=='buy';document.title=t==='col'?'My collection':'Auto-buy';
 try{history.replaceState(null,'',t==='col'?'#collection':location.pathname);sessionStorage.setItem('abtab',t)}catch(e){}if(t==='col'&&!C)loadCol()}
$('#tabs').addEventListener('click',e=>{const t=e.target.closest('button')?.dataset.tab;if(t)showTab(t)});
$('#cfilter').addEventListener('click',e=>{const f=e.target.closest('button')?.dataset.f;if(f){FILTER=f;renderCol()}});
$('#cform').addEventListener('submit',async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(e.target));if(!d.id)delete d.id;if(await cact('/api/collection/item',d))resetForm()});
$('#ccancel').addEventListener('click',resetForm);
$('#citems').addEventListener('click',e=>{const a=e.target.dataset.c;if(!a)return;const id=e.target.closest('.citem').dataset.id,i=C.items.find(x=>x.id===id);
 if(a==='edit')editItem(i);
 if(a==='arrived')cact('/api/collection/item',{id,status:'have'});
 if(a==='remove'&&confirm('Remove '+i.name+' from your collection?'))cact('/api/collection/remove',{id});
 if(a==='photo'){photoFor=id;$('#cphoto').click()}});
$('#cphoto').addEventListener('change',async e=>{const file=e.target.files[0];e.target.value='';if(!file||!photoFor)return;
 try{const img=await new Promise((ok,bad)=>{const im=new Image();im.onload=()=>ok(im);im.onerror=()=>bad(new Error("couldn't read that picture"));im.src=URL.createObjectURL(file)});
  const k=Math.min(1,1000/Math.max(img.naturalWidth,img.naturalHeight)),cv=document.createElement('canvas');cv.width=Math.round(img.naturalWidth*k);cv.height=Math.round(img.naturalHeight*k);
  cv.getContext('2d').drawImage(img,0,0,cv.width,cv.height);URL.revokeObjectURL(img.src);await cact('/api/collection/photo',{id:photoFor,data:cv.toDataURL('image/jpeg',.82)})}catch(err){toast(err.message,true)}});
fillSelects();{let t='buy';try{t=location.hash==='#collection'?'col':(sessionStorage.getItem('abtab')||'buy')}catch(e){}if(t==='col')showTab('col')}
setInterval(()=>{if(TAB==='col'&&!document.hidden&&!document.activeElement.matches('input,select'))loadCol()},60000);
load();setInterval(()=>{if(!document.hidden&&!document.activeElement.matches('input'))load()},10000);
</script></body></html>"""


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    sys.path.insert(0, HERE)
    import tcg_bot
    import auto_buy
    cfg = tcg_bot.load_config()
    ws = web_settings(cfg)
    url = page_url(cfg)
    import urllib.request
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{ws['port']}/", timeout=3).read(100)
        running = True
    except Exception:  # noqa: BLE001
        running = False
    if running:
        print(f"Opening {url}")
        webbrowser.open(url)
        sys.exit(0)
    print("The bot isn't running (or its page is off), so this window is serving the page. Close it to stop.")
    tcg_bot.CONFIG_WARNINGS.clear()
    srv = ThreadingHTTPServer(("0.0.0.0" if ws["lan"] else "127.0.0.1", ws["port"]),
                              make_handler(tcg_bot, auto_buy, ws["lan"]))
    print(f"Opening {url}")
    webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
