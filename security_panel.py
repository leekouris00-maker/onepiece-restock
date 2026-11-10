#!/usr/bin/env python3
"""
The Security page for the restock bot (v2.15)
=============================================
A small private web page showing, and letting you change, the bot's security set-up:

  * Execution environment - where the bot is running (container or PC) and which Linux it uses; choose
    the Linux for the next start.
  * VPN/proxy - connected or disconnected, which endpoint, choose another.
  * Public IP - the address the shops currently see, and when it was last checked.
  * IP rotation - the interval (0 = never, otherwise at least 60 minutes).
  * CAPTCHA detection - on or off, shops waiting for you, a Resume button for each.
  * Security monitoring - allowed-sites list, file checks, the latest security events.
  * EMERGENCY STOP - stops everything at once; Resume starts it again.

Open it with open_security.bat. It listens on port 8766 ("security": {"panel_port": 8766}; 0 = off), only
answers to "localhost", and needs the key in security_panel_token.txt (the .bat passes it for you). In
the container it is published to this PC only (127.0.0.1), never to the network.
"""
import json
import os
import secrets
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import netguard

DEFAULT_PORT = 8766
MAX_BODY = 4096
IMAGES = {"debian": "python:3.12-slim-bookworm", "alpine": "python:3.12-alpine"}
ENV_FILE = "environment.txt"            # read by run_docker.bat: the Linux image for the next start
TOKEN_FILE = "security_panel_token.txt"
_server = [None]


def port(cfg):
    sec = (cfg or {}).get("security")
    try:
        return int((sec or {}).get("panel_port", DEFAULT_PORT)) if isinstance(sec, dict) else DEFAULT_PORT
    except (TypeError, ValueError):
        return DEFAULT_PORT


def token(tb):
    path = os.path.join(tb.HERE, TOKEN_FILE)
    try:
        with open(path, "r", encoding="utf-8") as f:
            t = f.read().strip()
        if len(t) >= 24:
            return t
    except OSError:
        pass
    t = secrets.token_urlsafe(24)
    with open(path, "w", encoding="utf-8") as f:
        f.write(t)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return t


def chosen_image(tb):
    try:
        with open(os.path.join(tb.HERE, ENV_FILE), "r", encoding="utf-8") as f:
            name = f.read().strip().lower()
    except OSError:
        name = ""
    return name if name in IMAGES else "debian"


def set_image(tb, name):
    name = str(name or "").lower()
    if name not in IMAGES:
        raise ValueError("choose one of: " + ", ".join(sorted(IMAGES)))
    with open(os.path.join(tb.HERE, ENV_FILE), "w", encoding="utf-8") as f:
        f.write(name + "\n")
    return name


def state(tb):
    d = netguard.snapshot(tb, tb.load_config())
    d["environment"].update(next_image=chosen_image(tb), images=sorted(IMAGES), version=tb.VERSION)
    return d


def handle_post(tb, path, d):
    """One control. Returns the note to show. Raises ValueError for a bad request."""
    if path == "/api/security/stop":
        netguard.emergency_stop(tb, "you pressed Emergency stop", by="you")
        return "Stopped. Nothing is being sent."
    if path == "/api/security/resume":
        netguard.emergency_resume(tb)
        return "Resumed. Checks start again within a minute (auto-buy stays off until you switch it on)."
    if path == "/api/security/endpoint":
        netguard.select_endpoint(tb, str(d.get("name") or ""))
        return "Endpoint chosen. The bot connects through it and verifies the address at its next check."
    if path == "/api/security/rotation":
        netguard.set_rotation(tb, d.get("minutes"))
        return "Rotation interval saved."
    if path == "/api/security/captcha/resume":
        netguard.resume_captcha(tb, str(d.get("host") or ""))
        return "The bot will try that shop again at its next check."
    if path == "/api/security/environment":
        return f"Next start uses {set_image(tb, d.get('image'))}. Run run_docker.bat to apply it."
    raise LookupError(path)


def make_handler(tb):
    key = token(tb)

    class H(BaseHTTPRequestHandler):
        server_version = "security"

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            raw = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; "
                             "script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def _host_ok(self):
            host = (self.headers.get("Host") or "").split(":")[0].strip("[]").lower()
            return host in ("localhost", "127.0.0.1", "::1")

        def _authed(self):
            return secrets.compare_digest(str(self.headers.get("X-Token") or ""), key)

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {"error": "open this page as localhost"})
            path = urllib.parse.urlsplit(self.path).path
            if path in ("/", "/index.html", "/security"):
                return self._send(200, PAGE, "text/html")
            if path == "/api/security":
                if not self._authed():
                    return self._send(401, {"error": "wrong or missing key: open the page with open_security.bat"})
                try:
                    return self._send(200, state(tb))
                except Exception as e:  # noqa: BLE001
                    return self._send(500, {"error": f"{type(e).__name__}: {str(e)[:200]}"})
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok():
                return self._send(403, {"error": "open this page as localhost"})
            if not self._authed():
                return self._send(401, {"error": "wrong or missing key: open the page with open_security.bat"})
            path = urllib.parse.urlsplit(self.path).path
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_BODY:
                    raise ValueError("too much data")
                d = json.loads(self.rfile.read(n) or b"{}")
                if not isinstance(d, dict):
                    raise ValueError("expected an object")
                note = handle_post(tb, path, d)
            except LookupError:
                return self._send(404, {"error": "not found"})
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            except Exception as e:  # noqa: BLE001
                return self._send(500, {"error": f"{type(e).__name__}: {str(e)[:200]}"})
            return self._send(200, {"ok": True, "note": note, "state": state(tb)})

    return H


def start(tb, cfg=None):
    """Start the page (once). In the container it listens on every interface of the container, which Docker
    publishes to 127.0.0.1 on the PC only; on the PC it listens on 127.0.0.1."""
    if _server[0]:
        return _server[0]
    p = port(cfg if cfg is not None else tb.load_config())
    if p == 0:
        return None
    bind = "0.0.0.0" if getattr(tb, "IN_CONTAINER", False) else "127.0.0.1"
    srv = ThreadingHTTPServer((bind, p), make_handler(tb))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, name="security-page", daemon=True).start()
    _server[0] = srv
    print(f"   (security page on port {srv.server_address[1]} - open_security.bat opens it)")
    return srv


def stop():
    if _server[0]:
        _server[0].shutdown()
        _server[0].server_close()
        _server[0] = None


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bot security</title>
<style>
:root{--bg:#f4f5f7;--card:#fff;--ink:#16181d;--mute:#667085;--line:#e3e6ec;--ok:#12805c;--warn:#b54708;--bad:#c01c28;--acc:#1f3a5f}
@media(prefers-color-scheme:dark){:root{--bg:#101318;--card:#181c23;--ink:#eceff4;--mute:#98a2b3;--line:#2a303a;--ok:#3ecf8e;--warn:#f5a524;--bad:#ff6b6b;--acc:#9cc2ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:860px;margin:0 auto;padding:16px}h1{font-size:20px;margin:6px 0 14px}h2{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--mute);margin:0 0 10px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.big{font-size:19px;font-weight:650;font-variant-numeric:tabular-nums;word-break:break-all}.mute{color:var(--mute);font-size:13px}
.pill{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;font-weight:650;border:1px solid currentColor}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
select,input,button{font:inherit;color:inherit;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:7px 10px;min-height:38px}
button{cursor:pointer;font-weight:600}button.stop{background:var(--bad);color:#fff;border-color:var(--bad);width:100%;padding:12px;font-size:16px}
button.go{background:var(--ok);color:#fff;border-color:var(--ok);width:100%;padding:12px;font-size:16px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px}
table{width:100%;border-collapse:collapse;font-size:13px}td{padding:5px 6px;border-top:1px solid var(--line);vertical-align:top}td.t{white-space:nowrap;color:var(--mute)}
#banner{padding:10px 14px;border-radius:10px;margin-bottom:12px;font-weight:600;display:none}
#banner.bad{display:block;background:var(--bad);color:#fff}#banner.warn{display:block;background:var(--warn);color:#fff}
#toast{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);background:var(--ink);color:var(--bg);padding:9px 14px;border-radius:10px;opacity:0;transition:opacity .2s;max-width:90vw}
#toast.show{opacity:1}.scroll{overflow-x:auto}
</style></head><body><main>
<h1>🔒 Bot security <span class="mute" id="ver"></span></h1>
<div id="banner"></div>
<div class="grid">
<section class="card"><h2>Emergency shutdown</h2><div id="stopbox"></div></section>
<section class="card"><h2>Execution environment</h2><div class="big" id="env"></div><div class="mute" id="envd"></div>
 <div class="row"><label for="img" class="mute">Linux for next start</label><select id="img"></select></div></section>
<section class="card"><h2>VPN / proxy</h2><div id="vpn"></div>
 <div class="row"><label for="ep" class="mute">Endpoint</label><select id="ep"></select></div></section>
<section class="card"><h2>Public IP</h2><div class="big" id="ip"></div><div class="mute" id="ipd"></div></section>
<section class="card"><h2>IP rotation</h2><div class="mute" id="rotd"></div>
 <form class="row" id="rot"><input id="rotm" type="number" min="0" step="1" style="width:110px" aria-label="Rotation interval in minutes"><span class="mute">minutes</span><button>Save</button></form></section>
<section class="card"><h2>CAPTCHA detection</h2><div id="cap"></div></section>
<section class="card"><h2>Security monitoring</h2><div id="mon"></div></section>
</div>
<section class="card" style="margin-top:12px"><h2>Latest security events</h2><div class="scroll"><table id="ev"></table></div></section>
</main><div id="toast"></div>
<script>
let KEY='';const q=new URLSearchParams(location.search);
if(q.get('t')){KEY=q.get('t');try{sessionStorage.setItem('sk',KEY)}catch(e){}history.replaceState(null,'','/')}else{try{KEY=sessionStorage.getItem('sk')||''}catch(e){}}
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(t){const el=$('#toast');el.textContent=t;el.classList.add('show');clearTimeout(el._t);el._t=setTimeout(()=>el.classList.remove('show'),3500)}
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'X-Token':KEY,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
 const d=await r.json().catch(()=>({error:'bad reply'}));if(!r.ok)throw new Error(d.error||('HTTP '+r.status));return d}
async function act(path,body){try{const d=await api(path,body||{});toast(d.note||'Saved');S=d.state;render()}catch(e){toast(e.message)}}
const ago=t=>{if(!t)return 'never';const s=Math.max(0,Date.now()/1000-t);return s<90?Math.round(s)+' s ago':s<5400?Math.round(s/60)+' min ago':Math.round(s/3600)+' h ago'};
const pill=(c,t)=>`<span class="pill ${c}">${esc(t)}</span>`;
let S=null,typing=false;
function render(){if(!S)return;const n=S.network,b=$('#banner');
 $('#ver').textContent='v'+S.environment.version;
 b.className='';b.textContent='';
 if(S.stopped){b.className='bad';b.textContent='EMERGENCY STOP: '+S.stopped.reason+' ('+ago(S.stopped.t)+')'}
 else if(!S.enabled){b.className='warn';b.textContent='Security is switched off. Turn it on with "security": {"enabled": true} in config.json, or run the bot with run_docker.bat.'}
 else if(n.mode==='proxy'&&!n.connected){b.className='bad';b.textContent='VPN/proxy disconnected: '+(n.reason||'not verified yet')+'. Nothing is being sent.'}
 $('#stopbox').innerHTML=S.stopped?`<button class="go" id="resume">Resume</button><div class="mute" style="margin-top:8px">Stopped by ${esc(S.stopped.by)}.</div>`
  :`<button class="stop" id="stop">EMERGENCY STOP</button><div class="mute" style="margin-top:8px">Stops every request and switches auto-buy off, straight away.</div>`;
 const e=S.environment;$('#env').textContent=e.container?'Isolated container':'This PC (not isolated)';
 $('#envd').textContent=(e.image?e.image+' · ':'')+'runs as '+e.user+' · data in '+e.data_dir;
 $('#img').innerHTML=e.images.map(i=>`<option ${i===e.next_image?'selected':''}>${esc(i)}</option>`).join('');
 $('#vpn').innerHTML=n.mode==='proxy'?(n.connected?pill('ok','Connected'):pill('bad','Disconnected'))+` <span class="mute">through ${esc(n.endpoint||'no endpoint')}</span>`
  :pill('warn','Direct')+' <span class="mute">your normal connection, no VPN</span>';
 $('#ep').innerHTML=n.endpoints.length?n.endpoints.map(x=>`<option ${x===n.endpoint?'selected':''}>${esc(x)}</option>`).join(''):'<option>none set up</option>';$('#ep').disabled=!n.endpoints.length;
 $('#ip').textContent=n.ip||'not checked yet';$('#ipd').textContent='checked '+ago(n.ip_checked)+(n.vpn_flag===true?' · a VPN exit address':n.vpn_flag===false?' · NOT a VPN address':'');
 $('#rotd').textContent=(n.rotate_minutes>0?'Every '+n.rotate_minutes+' minutes':'Off')+(n.endpoints.length<2?' · needs two or more endpoints':'')+' · last change '+ago(n.last_rotation)+' · shortest allowed '+n.min_rotate_minutes+' min';
 if(!typing)$('#rotm').value=n.rotate_minutes;
 const c=S.captcha;$('#cap').innerHTML=(c.enabled&&S.enabled?pill('ok','Watching'):pill('warn','Off'))+
  (c.paused.length?'<table style="margin-top:8px">'+c.paused.map(p=>`<tr><td><b>${esc(p.host)}</b><div class="mute">${esc(p.kind)} · ${ago(p.since)} · ${p.needs_you?'waiting for you':'slow-down pause, retries by itself in '+Math.max(1,Math.round((p.until-Date.now()/1000)/60))+' min'}</div></td><td style="text-align:right"><button data-host="${esc(p.host)}">Resume</button></td></tr>`).join('')+'</table>'
  :'<div class="mute" style="margin-top:8px">No shop is asking for human verification.</div>');
 if(c.paused.some(p=>p.needs_you)&&!S.stopped&&!$('#banner').className){const b2=$('#banner');b2.className='warn';b2.textContent=c.paused.filter(p=>p.needs_you).length+' shop(s) need human verification - see CAPTCHA detection below.'}
 const m=S.monitoring;$('#mon').innerHTML=`<div>${pill(m.allowlist&&S.active?'ok':'warn',m.allowlist&&S.active?'Allowed sites only':'Not restricted')} <span class="mute">${m.allowed_sites} sites</span></div>
  <div style="margin-top:6px">${pill(m.files&&S.active?'ok':'warn',m.files&&S.active?'File checks on':'File checks off')} <span class="mute">${m.blocked_files} blocked</span></div>
  <div class="mute" style="margin-top:6px">Unexpected sites this hour: ${m.violations_this_hour} of ${m.max_violations} before an automatic stop</div>`;
 $('#ev').innerHTML=S.events.length?S.events.map(v=>{const {t,event,level,...rest}=v;return `<tr><td class="t">${new Date(t*1000).toLocaleString('en-AU',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})}</td><td class="${level==='critical'?'bad':level==='warning'?'warn':''}"><b>${esc(event)}</b></td><td class="mute">${esc(Object.entries(rest).map(([k,x])=>k+': '+(typeof x==='object'?JSON.stringify(x):x)).join(' · '))}</td></tr>`}).join(''):'<tr><td class="mute">Nothing yet.</td></tr>'}
async function load(){try{S=await api('/api/security');render()}catch(e){const b=$('#banner');b.className='bad';b.textContent=e.message}}
document.addEventListener('click',e=>{const t=e.target;
 if(t.id==='stop'&&confirm('Stop the bot now? Nothing will be sent until you press Resume.'))act('/api/security/stop');
 if(t.id==='resume'&&confirm('Start the bot again?'))act('/api/security/resume');
 if(t.dataset&&t.dataset.host)act('/api/security/captcha/resume',{host:t.dataset.host})});
$('#ep').addEventListener('change',e=>act('/api/security/endpoint',{name:e.target.value}));
$('#img').addEventListener('change',e=>act('/api/security/environment',{image:e.target.value}));
$('#rotm').addEventListener('focus',()=>typing=true);$('#rotm').addEventListener('blur',()=>typing=false);
$('#rot').addEventListener('submit',e=>{e.preventDefault();typing=false;act('/api/security/rotation',{minutes:$('#rotm').value})});
load();setInterval(load,10000);
</script></body></html>
"""
