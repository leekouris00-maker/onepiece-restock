#!/usr/bin/env python3
"""
Network guard for the restock bot (v2.15)
=========================================
Off unless config.json has  "security": {"enabled": true}  (or the container sets BOT_SECURITY=1).
With it on, every request the bot makes passes through here first.

WHAT IT DOES
  * ENDPOINT - sends all traffic through the VPN/proxy endpoint you chose ("endpoints" + "endpoint").
    An endpoint is an http:// proxy address, normally the VPN container next to the bot
    (http://vpn:8888). Write "env:NAME" to keep the address (and any password in it) in an environment
    variable instead of config.json. Addresses are never printed or logged.
  * VERIFY - asks an "what's my IP" page through that endpoint (every "verify_minutes", and after any
    change) and remembers the answer. If the check fails, or the answer is one of "never_ips" (put your
    home IP there), or "require_vpn_flag" is on and the page says it isn't a VPN address, the bot goes
    DISCONNECTED: it sends nothing at all until a check passes again. It never falls back to a direct
    connection.
  * ROTATE - with two or more endpoints and "rotate_minutes" set, moves to the next endpoint on that
    schedule (never more often than hourly), then verifies the address changed. Rotation is a timer and
    nothing else: a shop saying "slow down", refusing the bot or showing a CAPTCHA never causes a switch,
    and those pauses stay in force on the new address.
  * ALLOWED SITES - the bot may only talk to its shops, Discord, eBay's API, TCGCSV, ntfy, GitHub and the
    IP-check page (plus "extra_hosts"). Anything else is refused and logged. "max_violations" different
    unexpected sites within an hour triggers an EMERGENCY STOP.
  * EMERGENCY STOP - everything stops: no requests, auto-buy off. Stays stopped (also after a restart)
    until you press Resume on the Security page. Also available as a button there.
  * CAPTCHA - see captcha_watch.py.   * FILES - see fileguard.py.   * LOG - see security_log.py.

SETTINGS (config.json, all optional; defaults shown)
  "security": {
    "enabled": false,
    "network": {
      "mode": "direct",                  "direct" = your normal connection, "proxy" = through an endpoint
      "endpoints": {},                   {"melbourne": "http://vpn:8888", "sydney": "env:VPN_SYDNEY"}
      "endpoint": "",                    which one to use (the first, if empty)
      "rotate_minutes": 0,               0 = never. Otherwise at least 60.
      "verify_minutes": 10,
      "ip_check_url": "https://am.i.mullvad.net/json",
      "never_ips": [],                   addresses that must never be seen, e.g. your home IP
      "require_vpn_flag": false          true = the check page must say it's a Mullvad exit
    },
    "allowlist": {"enforce": true, "extra_hosts": [], "max_violations": 5},
    "captcha": {"enabled": true, "recheck_hours": 0},
    "files": {"enforce": true, "extra_write_dirs": []}
  }
Environment variables (used by the container): BOT_SECURITY=1, BOT_NET_MODE=proxy,
BOT_ENDPOINTS="melbourne=http://vpn:8888,sydney=http://vpn2:8888", BOT_ENDPOINT=melbourne, BOT_CONTAINER=1.

What you choose on the Security page (endpoint, rotation interval) is kept in security_state.json and
wins over config.json.
"""
import ipaddress
import json
import os
import re
import socket
import threading
import time
import urllib.parse
import urllib.request

import captcha_watch
import fileguard
import security_log

STATE_NAME = "security_state.json"
MIN_ROTATE_MINUTES = 60
VERIFY_RETRY = 60                 # while disconnected, look again this often
VIOLATION_WINDOW = 3600
CORE_HOSTS = ("discord.com", "discordapp.com", "discord.gg", "discordapp.net", "ntfy.sh", "api.ebay.com",
              "tcgcsv.com", "raw.githubusercontent.com", "api.github.com")
LOCAL_NAMES = ("localhost", "ip6-localhost", "host.docker.internal")
PROXY_VARS = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[0-9a-f]{1,4}:){2,7}[0-9a-f]{1,4}\b", re.I)

_lock = threading.RLock()
_tls = threading.local()
RT = {"on": False, "tb": None, "cfg": None, "s": None, "allow": set(), "proxy_hosts": set(), "applied": None,
      "orig_getaddrinfo": None, "opener": False, "saved_env": None, "violations": [], "state": None}


class Blocked(OSError):
    """A request the guard refused."""


# ---------------------------------------------------------------- settings and saved state
def _env_on(name):
    return str(os.environ.get(name, "")).strip().lower() in ("1", "true", "yes", "on")


def in_container():
    return _env_on("BOT_CONTAINER")


def _resolve(value):
    """"env:NAME" -> that environment variable's value (or "")."""
    v = str(value or "").strip()
    return os.environ.get(v[4:].strip(), "").strip() if v.lower().startswith("env:") else v


def settings(cfg, problems=None):
    """config.json "security" merged with defaults and the container's environment variables."""
    problems = [] if problems is None else problems
    raw = (cfg or {}).get("security")
    raw = raw if isinstance(raw, dict) else {}
    net = raw.get("network") if isinstance(raw.get("network"), dict) else {}
    al = raw.get("allowlist") if isinstance(raw.get("allowlist"), dict) else {}
    fl = raw.get("files") if isinstance(raw.get("files"), dict) else {}
    endpoints = {}
    for k, v in (net.get("endpoints") or {}).items() if isinstance(net.get("endpoints"), dict) else []:
        endpoints[str(k)] = str(v)
    for part in [x for x in os.environ.get("BOT_ENDPOINTS", "").split(",") if "=" in x]:
        k, v = part.split("=", 1)
        endpoints[k.strip()] = v.strip()
    good = {}
    for name, v in endpoints.items():
        url = _resolve(v)
        u = urllib.parse.urlsplit(url)
        if u.scheme in ("http", "https") and u.hostname:
            good[name] = url
        else:
            problems.append(f"security endpoint \"{name}\" needs an http:// proxy address (or env:NAME holding one); skipped")
    mode = str(os.environ.get("BOT_NET_MODE") or net.get("mode") or "direct").lower()
    if mode not in ("direct", "proxy"):
        problems.append(f"security network mode \"{mode}\" isn't known (direct or proxy); using direct")
        mode = "direct"
    if mode == "proxy" and not good:
        problems.append("security network mode is \"proxy\" but there are no usable endpoints: the bot will stay disconnected")

    def num(v, default):
        try:
            return float(v)
        except (TypeError, ValueError):
            return default
    rotate = num(net.get("rotate_minutes"), 0.0)
    if 0 < rotate < MIN_ROTATE_MINUTES:
        problems.append(f"security rotate_minutes {rotate:g} is too short; using {MIN_ROTATE_MINUTES}")
        rotate = float(MIN_ROTATE_MINUTES)
    return {
        "enabled": bool(raw.get("enabled")) or _env_on("BOT_SECURITY"),
        "mode": mode, "endpoints": good,
        "endpoint": str(os.environ.get("BOT_ENDPOINT") or net.get("endpoint") or ""),
        "rotate_minutes": max(0.0, rotate),
        "verify_minutes": max(1.0, num(net.get("verify_minutes"), 10.0)),
        "ip_check_url": str(net.get("ip_check_url") or "https://am.i.mullvad.net/json"),
        "never_ips": {str(x).strip() for x in net.get("never_ips") or [] if str(x).strip()},
        "require_vpn_flag": bool(net.get("require_vpn_flag")),
        "enforce": al.get("enforce", True) is not False,
        "extra_hosts": {str(x).strip().lower() for x in al.get("extra_hosts") or [] if str(x).strip()},
        "max_violations": max(1, int(num(al.get("max_violations"), 5))),
        "files": fl.get("enforce", True) is not False,
        "extra_write_dirs": [str(x) for x in fl.get("extra_write_dirs") or []],
    }


def state_path(tb):
    return os.path.join(tb.HERE, STATE_NAME)


def load_state(tb):
    with _lock:
        if RT["state"] is None or RT["tb"] is not tb:
            st = tb.read_json(state_path(tb), {})
            RT["state"] = st if isinstance(st, dict) else {}
        return RT["state"]


def save_state(tb):
    with _lock:
        st = RT["state"] or {}
        try:
            tb.atomic_write_json(state_path(tb), st, sort_keys=True)
        except OSError as e:
            print(f"   ! couldn't save {STATE_NAME} ({e})")


def _log(event, level="info", **fields):
    if RT["tb"] is not None:
        security_log.log(RT["tb"], event, level, **fields)


# ---------------------------------------------------------------- allowed sites
def _host_of(url):
    try:
        return (urllib.parse.urlsplit(url if "://" in str(url) else "//" + str(url)).hostname or "").lower()
    except ValueError:
        return ""


def build_allowlist(tb, cfg, s):
    hosts = set(CORE_HOSTS) | set(s["extra_hosts"])
    try:
        hosts |= {h.lower() for h in tb.shop_names(cfg)}
    except Exception:  # noqa: BLE001
        pass
    for name, path in (getattr(tb, "CATALOGS", {}) or {}).items():
        base = (cfg.get("singles", {}).get("shops", {}) or {}).get(name)
        if base:
            hosts.add(_host_of(base))
    for v in (cfg.get("alerts") or {}).values():                 # webhooks, ntfy server
        if isinstance(v, str) and v.startswith("http"):
            hosts.add(_host_of(v))
    hosts.add(_host_of(s["ip_check_url"]))
    try:                                                          # /watch links you added from Discord
        import link_watch
        for item in link_watch.load() or []:
            if isinstance(item, dict) and item.get("url"):
                hosts.add(_host_of(item["url"]))
    except Exception:  # noqa: BLE001
        pass
    hosts.discard("")
    return hosts


def host_allowed(host, allow):
    """Exactly listed, or a subdomain of a listed site (cdn.discordapp.com under discordapp.com)."""
    host = (host or "").lower().rstrip(".")
    if host in allow:
        return True
    return any(host.endswith("." + a) for a in allow)


def _is_local(host):
    if host in LOCAL_NAMES:
        return True
    try:
        a = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return a.is_loopback or a.is_private or a.is_link_local


# ---------------------------------------------------------------- the gate
def stopped(tb=None):
    tb = tb or RT["tb"]
    if tb is None:
        return None
    st = load_state(tb).get("stopped")
    return st if isinstance(st, dict) else None


def _violation(kind, host, detail=""):
    """An attempt to reach a site that isn't on the list. Too many different ones in an hour stops the bot."""
    now = time.time()
    with _lock:
        RT["violations"] = [(t, h) for t, h in RT["violations"] if now - t < VIOLATION_WINDOW]
        fresh = host not in {h for _, h in RT["violations"]}
        RT["violations"].append((now, host))
        distinct = len({h for _, h in RT["violations"]})
        limit = (RT["s"] or {}).get("max_violations", 5)
    if fresh:
        _log(kind, "warning", host=host, detail=detail, different_sites_this_hour=distinct, limit=limit)
    if distinct >= limit and not stopped():
        emergency_stop(RT["tb"], f"unexpected network activity: {distinct} sites that aren't on the allowed list "
                                 f"in an hour (last: {host})")


def gate(url):
    """Called by the bot before every request. Raises Blocked if the request may not go out."""
    if not RT["on"] or getattr(_tls, "internal", False):
        return
    host = _host_of(url)
    st = load_state(RT["tb"])
    if st.get("stopped"):
        raise Blocked(f"emergency stop is on: nothing is sent ({host})")
    if _is_local(host):
        return
    s = RT["s"]
    if s["enforce"] and not host_allowed(host, RT["allow"]):
        _violation("blocked_host", host, "not on the allowed list")
        raise Blocked(f"{host} isn't on the bot's allowed list")
    if s["mode"] == "proxy" and not st.get("connected"):
        raise Blocked(f"VPN/proxy is disconnected: nothing is sent ({host})")
    if s["captcha"]["enabled"] and captcha_watch.is_paused(st, host, RT["cfg"]):
        raise Blocked(f"{host} asked for human verification: paused until you press Resume")


def on_response(url, status, headers, body):
    """Called with each reply. True if it was a CAPTCHA challenge (the shop is now paused)."""
    if not RT["on"] or getattr(_tls, "internal", False) or not RT["s"]["captcha"]["enabled"]:
        return False
    kind = captcha_watch.detect(status, headers, body)
    host = _host_of(url)
    tb, cfg = RT["tb"], RT["cfg"]
    st = load_state(tb)
    if not kind:
        if host in captcha_watch.paused(st) and 200 <= int(status or 0) < 300:     # a recheck that went through
            captcha_watch.resume(st, host)
            save_state(tb)
            _log("captcha_resumed", host=host, how="the shop answered normally")
        return False
    with _lock:
        tell = captcha_watch.pause(st, host, kind, url)
        save_state(tb)
    _log("captcha_detected", "warning", host=host, kind=kind, status=status)
    if tell:
        try:
            name = tb.shop_names(cfg).get(host, host)
            _internal(lambda: tb.post_status(cfg, captcha_watch.message(name, host, st["captcha"][host]), tb.AMBER))
        except Exception:  # noqa: BLE001
            pass
    return True


def _internal(fn):
    """Run fn with the gate open (the guard's own IP check and its notices)."""
    _tls.internal = True
    try:
        return fn()
    finally:
        _tls.internal = False


# ---------------------------------------------------------------- socket and urllib guards
def _guarded_getaddrinfo(host, *a, **k):
    orig = RT["orig_getaddrinfo"] or socket.getaddrinfo
    if RT["on"] and not getattr(_tls, "internal", False) and isinstance(host, (str, bytes)):
        h = (host.decode("ascii", "replace") if isinstance(host, bytes) else host).lower().rstrip(".")
        if h and not _is_local(h) and h not in RT["proxy_hosts"]:
            if stopped():
                raise Blocked(f"emergency stop is on: nothing is sent ({h})")
            try:
                literal = ipaddress.ip_address(h.strip("[]"))
            except ValueError:
                literal = None
            if RT["s"]["enforce"] and (literal is not None or not host_allowed(h, RT["allow"])):
                _violation("blocked_socket", h, "a connection outside the allowed list")
                raise Blocked(f"{h} isn't on the bot's allowed list")
    return orig(host, *a, **k)


class _UrllibGuard(urllib.request.BaseHandler):
    handler_order = 100

    def http_request(self, req):
        try:
            gate(req.full_url)
        except Blocked as e:
            raise urllib.error.URLError(str(e)) from None
        return req

    https_request = http_request


def _install_guards():
    if RT["orig_getaddrinfo"] is None:
        RT["orig_getaddrinfo"] = socket.getaddrinfo
        socket.getaddrinfo = _guarded_getaddrinfo
    if not RT["opener"]:
        urllib.request.install_opener(urllib.request.build_opener(_UrllibGuard()))
        RT["opener"] = True


def _remove_guards():
    if RT["orig_getaddrinfo"] is not None:
        socket.getaddrinfo = RT["orig_getaddrinfo"]
        RT["orig_getaddrinfo"] = None
    if RT["opener"]:
        urllib.request.install_opener(None)
        RT["opener"] = False


# ---------------------------------------------------------------- endpoint, verification, rotation
def _set_proxy(url):
    if RT["saved_env"] is None:
        RT["saved_env"] = {k: os.environ.get(k) for k in PROXY_VARS + ("NO_PROXY", "no_proxy")}
    for k in PROXY_VARS:
        os.environ.pop(k, None)
    if url:
        for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
            os.environ[k] = url
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = "localhost,127.0.0.1,::1"
    try:
        RT["tb"].HTTP.close_idle()                  # pooled connections belong to the old route
    except Exception:  # noqa: BLE001
        pass


def _restore_proxy():
    saved, RT["saved_env"] = RT["saved_env"], None
    for k, v in (saved or {}).items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def current_endpoint(s, st):
    """The endpoint in use: your choice on the Security page, else config.json's, else the first."""
    names = sorted(s["endpoints"])
    for want in (st.get("endpoint"), s["endpoint"]):
        if want in s["endpoints"]:
            return want
    return names[0] if names else ""


def parse_ip_reply(body):
    """(ip, is_vpn or None) from an IP-check page: Mullvad's JSON, any {"ip": ...} JSON, or plain text."""
    text = (body or b"").decode("utf-8", "replace").strip()
    try:
        d = json.loads(text)
    except ValueError:
        d = None
    if isinstance(d, dict):
        ip = str(d.get("ip") or d.get("query") or d.get("origin") or "")
        flag = d.get("mullvad_exit_ip")
        return (ip if IP_RE.fullmatch(ip) else ""), (bool(flag) if flag is not None else None)
    m = IP_RE.search(text[:200])
    return (m.group(0) if m else ""), None


def _fetch_ip(tb, s):
    def go():
        status, _, body = tb.HTTP._exchange("GET", s["ip_check_url"])
        if not 200 <= status < 300:
            raise OSError(f"IP check answered HTTP {status}")
        return parse_ip_reply(body)
    return _internal(go)


def verify(tb, s, st, why="check", now=None):
    """Ask what address the world sees and decide connected / disconnected. Returns True if connected."""
    now = now or time.time()
    was = st.get("connected")
    ip, flag, problem = "", None, ""
    try:
        ip, flag = _fetch_ip(tb, s)
        if not ip:
            problem = "the IP check page didn't give an address"
    except Exception as e:  # noqa: BLE001
        problem = f"the IP check failed ({type(e).__name__})"
    if not problem and ip in s["never_ips"]:
        problem = "the address seen is one you said must never be used (never_ips)"
    if not problem and s["mode"] == "proxy" and s["require_vpn_flag"] and flag is not True:
        problem = "the IP check page says this isn't a VPN address"
    st["ip_ts"] = round(now)
    if problem:
        st["connected"] = False if s["mode"] == "proxy" else True
        st["reason"] = problem
        if s["mode"] == "proxy" and was is not False:
            _log("vpn_disconnected", "critical", reason=problem, endpoint=st.get("endpoint_in_use"))
            _notify(tb, f"🔌 **VPN/proxy disconnected** ({problem}). The bot is sending nothing until the connection "
                        f"is verified again. It will not fall back to your normal connection.", "RED")
        return bool(st["connected"])
    st.update(connected=True, reason="", ip=ip, vpn_flag=flag)
    if was is False:
        _log("vpn_reconnected", ip=ip, endpoint=st.get("endpoint_in_use"))
        _notify(tb, "✅ **VPN/proxy connection verified again.** Checks have resumed.", "GREEN")
    elif why != "check":
        _log("ip_verified", ip=ip, endpoint=st.get("endpoint_in_use"), why=why)
    return True


def _notify(tb, text, color):
    cfg = RT["cfg"]
    try:
        _internal(lambda: tb.post_status(cfg, text, getattr(tb, color, None) or tb.GREY))
    except Exception:  # noqa: BLE001
        pass


def _use_endpoint(tb, s, st, name, why, now):
    old_ip = st.get("ip")
    st["endpoint_in_use"] = name
    st["rotated_ts"] = round(now)
    _set_proxy(s["endpoints"][name])
    RT["applied"] = (s["mode"], name, s["endpoints"][name])
    _log("endpoint_selected", endpoint=name, why=why)
    ok = verify(tb, s, st, why=why, now=now)
    if ok and why == "rotation":
        if old_ip and st.get("ip") == old_ip:
            _log("rotation_no_change", "warning", endpoint=name, ip=st.get("ip"))
        else:
            _log("ip_rotated", endpoint=name, before=old_ip, after=st.get("ip"))
    return ok


def apply(tb, cfg, now=None):
    """Called at the start of every check: switch the guard on or off and keep the connection verified."""
    now = now or time.time()
    problems = []
    s = settings(cfg, problems)
    s["captcha"] = captcha_watch.settings(cfg)
    with _lock:
        if RT["tb"] is not tb:
            RT["state"] = None
        was_on = RT["on"]
        RT.update(tb=tb, cfg=cfg, s=s)
        if not s["enabled"]:
            if was_on:
                RT["on"] = False
                _remove_guards()
                _restore_proxy()
                fileguard.disable()
                _log("security_off")
            return s
        st = load_state(tb)
        RT["allow"] = build_allowlist(tb, cfg, s)
        RT["proxy_hosts"] = {_host_of(u) for u in s["endpoints"].values()}
        RT["on"] = True
        _install_guards()
        if s["files"]:
            import sys
            sys.dont_write_bytecode = True
            fileguard.enable(tb.HERE, s["extra_write_dirs"], block_processes=in_container(),
                             report=lambda kind, detail: _log(kind, "warning", detail=detail))
        else:
            fileguard.disable()
        if not was_on:
            _log("security_on", mode=s["mode"], endpoints=sorted(s["endpoints"]), allowed_sites=len(RT["allow"]),
                 container=in_container())
        sig = "; ".join(problems)
        if sig and sig != st.get("warned"):
            _log("config_warning", "warning", problems=problems)
        st["warned"] = sig
        if st.get("stopped"):
            save_state(tb)
            return s
        if s["mode"] == "direct":
            if RT["applied"] != ("direct", "", ""):
                _set_proxy("")
                RT["applied"] = ("direct", "", "")
                st["endpoint_in_use"] = ""
            st["connected"] = True
            if now - float(st.get("ip_ts") or 0) >= s["verify_minutes"] * 60:
                verify(tb, s, st, now=now)
        else:
            name = current_endpoint(s, st)
            rotate = float(st["rotate_minutes"]) if st.get("rotate_minutes") is not None else s["rotate_minutes"]
            rotate = 0.0 if rotate <= 0 else max(float(MIN_ROTATE_MINUTES), rotate)
            names = sorted(s["endpoints"])
            if not name:
                st.update(connected=False, reason="no usable endpoint is set up")
            elif RT["applied"] != ("proxy", name, s["endpoints"][name]):
                _use_endpoint(tb, s, st, name, "start" if not was_on else "selected", now)
            elif rotate and len(names) > 1 and st.get("connected") \
                    and now - float(st.get("rotated_ts") or now) >= rotate * 60:
                nxt = names[(names.index(name) + 1) % len(names)]
                st["endpoint"] = nxt
                _use_endpoint(tb, s, st, nxt, "rotation", now)
            elif now - float(st.get("ip_ts") or 0) >= (VERIFY_RETRY if not st.get("connected") else s["verify_minutes"] * 60):
                verify(tb, s, st, now=now)
        save_state(tb)
    return s


# ---------------------------------------------------------------- controls (the Security page)
def select_endpoint(tb, name):
    s = RT["s"] or {}
    if name not in (s.get("endpoints") or {}):
        raise ValueError("that endpoint isn't set up")
    st = load_state(tb)
    st["endpoint"] = name
    RT["applied"] = None                         # the next check connects through it and verifies
    save_state(tb)


def set_rotation(tb, minutes):
    try:
        m = float(minutes)
    except (TypeError, ValueError):
        raise ValueError("the rotation interval should be a number of minutes (0 = never)") from None
    if 0 < m < MIN_ROTATE_MINUTES:
        raise ValueError(f"the shortest rotation interval is {MIN_ROTATE_MINUTES} minutes")
    load_state(tb)["rotate_minutes"] = max(0.0, m)
    save_state(tb)


def resume_captcha(tb, host):
    st = load_state(tb)
    if not captcha_watch.resume(st, host):
        raise ValueError("that shop isn't paused")
    save_state(tb)
    _log("captcha_resumed", host=host, how="you pressed Resume")


def emergency_stop(tb, reason, by="the bot"):
    """Stop everything. Stays stopped until emergency_resume()."""
    if tb is None:
        return
    st = load_state(tb)
    if st.get("stopped"):
        return
    _log("emergency_stop", "critical", reason=reason, by=by)
    try:                                            # one last notice, then the gate closes
        _notify(tb, f"🛑 **Emergency stop** ({by}): {reason}. The bot is sending nothing and auto-buy is off. "
                    f"Press Resume on the Security page when you've looked into it.", "RED")
    except Exception:  # noqa: BLE001
        pass
    st["stopped"] = {"t": round(time.time()), "reason": str(reason)[:300], "by": by}
    save_state(tb)
    try:
        ab = getattr(tb, "auto_buy", None)
        if ab:
            ab.set_mode(tb, "off")
    except Exception:  # noqa: BLE001
        pass
    try:
        tb.HTTP.close_idle()
    except Exception:  # noqa: BLE001
        pass


def emergency_resume(tb):
    st = load_state(tb)
    if not st.pop("stopped", None):
        raise ValueError("the bot isn't stopped")
    with _lock:
        RT["violations"] = []
        RT["applied"] = None
    save_state(tb)
    _log("emergency_resume")


def snapshot(tb, cfg=None):
    """Everything the Security page shows. Endpoint addresses are never included, only their names."""
    cfg = cfg if cfg is not None else (RT["cfg"] or {})
    s = RT["s"] if RT["on"] and RT["s"] else dict(settings(cfg), captcha=captcha_watch.settings(cfg))
    st = load_state(tb)
    names = sorted(s["endpoints"])
    rotate = float(st["rotate_minutes"]) if st.get("rotate_minutes") is not None else s["rotate_minutes"]
    return {
        "enabled": s["enabled"], "active": RT["on"],
        "environment": {"container": in_container(), "image": os.environ.get("BOT_IMAGE", ""),
                        "data_dir": tb.HERE, "user": _whoami()},
        "network": {"mode": s["mode"], "endpoints": names, "endpoint": st.get("endpoint_in_use") or current_endpoint(s, st),
                    "connected": bool(st.get("connected")) if s["mode"] == "proxy" else True,
                    "reason": st.get("reason") or "", "ip": st.get("ip") or "", "ip_checked": st.get("ip_ts") or 0,
                    "vpn_flag": st.get("vpn_flag"), "rotate_minutes": rotate, "min_rotate_minutes": MIN_ROTATE_MINUTES,
                    "last_rotation": st.get("rotated_ts") or 0},
        "captcha": {"enabled": s["captcha"]["enabled"], "recheck_hours": s["captcha"]["recheck_hours"],
                    "paused": [dict(e, host=h) for h, e in sorted(captcha_watch.paused(st).items())]},
        "monitoring": {"allowlist": s["enforce"], "allowed_sites": len(RT["allow"]) if RT["on"] else 0,
                       "violations_this_hour": len({h for _, h in RT["violations"]}),
                       "max_violations": s["max_violations"], "files": s["files"],
                       "blocked_files": fileguard.STATE["blocked"]},
        "stopped": st.get("stopped") or None,
        "events": security_log.recent(tb, 30),
    }


def _whoami():
    try:
        return "root" if os.geteuid() == 0 else f"uid {os.geteuid()}"
    except AttributeError:
        return "windows user"
