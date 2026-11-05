#!/usr/bin/env python3
"""
Auto-buy dashboard: a web page on the PC (v2.11.2)
==================================================

The PC copy of the restock bot serves a small page where you can switch auto-buy off / test / live,
change the spend limits, edit the list of things it looks for, test a link, and see what it tried
(with the checkout screenshots).

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
SHOT_RE = re.compile(r"^[\w.\-]+\.png$")
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

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
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
                d = self._body()
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
            try:
                tb.append_text(os.path.join(HERE, "commands_audit.log"),
                               f"web page  {path} {json.dumps(d)[:300]}\n", 500_000)
            except Exception:  # noqa: BLE001
                pass
            return self._send(200, {"ok": True, "note": note, "state": ab.snapshot(tb)})

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
</style></head><body><div class="wrap">
<header><h1>🤖 Auto-buy <small id="ver"></small></h1>
<div class="seg" id="modes"><button data-m="off">Off</button><button data-m="test">Test</button><button data-m="live" class="livebtn">Live</button></div></header>
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
  <p class="muted" style="font-size:13px">The PC opens the checkout, stops before paying and posts a screenshot in #bot-status.</p></section>
 <section class="card"><h2>Last attempts</h2><div id="recent" class="list-attempts"></div></section>
</div>
<section class="card"><h2>Checkout screenshots</h2><div id="shots" class="shots"></div></section>
</div><div class="toast" id="toast"></div>
<script>
const q=new URLSearchParams(location.search);let KEY=q.get('t')||'';
try{if(KEY){sessionStorage.setItem('abk',KEY);history.replaceState(null,'','/')}else{KEY=sessionStorage.getItem('abk')||''}}catch(e){}
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
