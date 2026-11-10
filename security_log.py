#!/usr/bin/env python3
"""
Security event log for the restock bot (v2.15)
==============================================
Every security-relevant thing the bot does or refuses goes to security_events.jsonl (one JSON object a
line, newest last) in the bot's data folder, and is printed to the bot's normal log. Before anything is
written, secrets are removed: proxy usernames and passwords, Discord webhook and bot tokens, anything that
looks like a key or token, and all but the first half of public IP addresses (203.0.x.x).

Events: security_on, security_off, endpoint_selected, ip_verified, ip_rotated, rotation_no_change,
vpn_disconnected, vpn_reconnected, blocked_host, blocked_socket, blocked_file, blocked_process,
captcha_detected, captcha_resumed, emergency_stop, emergency_resume, config_warning.

The file is cut over to security_events.jsonl.1 when it reaches 2 MB. Never raises.
"""
import ipaddress
import json
import os
import re
import threading
import time

NAME = "security_events.jsonl"
MAX_BYTES = 2_000_000
_lock = threading.Lock()

_SECRETS = [
    (re.compile(r"(://)[^/\s:@]+:[^/\s@]+@"), r"\1***:***@"),                           # user:pass@ in a proxy address
    (re.compile(r"(discord(?:app)?\.com/api/webhooks/\d+/)[\w-]+"), r"\1***"),
    (re.compile(r"\b[MN][\w-]{23,25}\.[\w-]{6}\.[\w-]{27,40}\b"), "***bot-token***"),
    (re.compile(r"(?i)\b(proxy-authorization|authorization|x-token|token|password|passwd|secret|private[_-]?key|"
                r"api[_-]?key|client[_-]?secret)\b(\"?\s*[:=]\s*\"?)[^\s\",}]+"), r"\1\2***"),
    (re.compile(r"\b[A-Za-z0-9+/]{43}=(?![A-Za-z0-9+/=])"), "***key***"),                # a WireGuard key
]
_HOME_NETS = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "fc00::/7")]
_IP4 = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.\d{1,3}\.\d{1,3}\b")


def mask_ip(ip):
    """203.0.113.7 -> 203.0.x.x; home-network and loopback addresses are left as they are; IPv6 keeps its first two groups."""
    s = str(ip or "")
    try:
        a = ipaddress.ip_address(s)
    except ValueError:
        return s
    if a.is_loopback or a.is_link_local or any(a in n for n in _HOME_NETS if n.version == a.version):
        return s
    if a.version == 4:
        p = s.split(".")
        return f"{p[0]}.{p[1]}.x.x"
    return ":".join(s.split(":")[:2]) + ":x"


def scrub(text):
    """Text with secrets and the second half of public IP addresses removed."""
    text = str(text)
    for rx, rep in _SECRETS:
        text = rx.sub(rep, text)
    return _IP4.sub(lambda m: mask_ip(m.group(0)), text)


def _clean(v):
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in list(v.items())[:40]}
    if isinstance(v, (list, tuple, set)):
        return [_clean(x) for x in list(v)[:40]]
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    return scrub(v)[:400]


def path(tb):
    return os.path.join(tb.HERE, NAME)


def log(tb, event, level="info", **fields):
    """Write one event. level: info, warning or critical."""
    entry = {"t": round(time.time()), "event": str(event), "level": level}
    entry.update(_clean(fields))
    line = json.dumps(entry, ensure_ascii=True, sort_keys=True)
    mark = {"critical": "!!!", "warning": "!"}.get(level, "·")
    try:
        print(f"   {mark} security: {event}" + (" " + json.dumps({k: v for k, v in entry.items()
                                                                  if k not in ("t", "event", "level")}) if fields else ""))
    except Exception:  # noqa: BLE001
        pass
    if getattr(tb, "DRY_RUN", [False])[0]:
        return entry
    p = path(tb)
    try:
        with _lock:
            try:
                if os.path.getsize(p) > MAX_BYTES:
                    os.replace(p, p + ".1")
            except OSError:
                pass
            with open(p, "a", encoding="utf-8", newline="\n") as f:
                f.write(line + "\n")
    except OSError:
        pass
    return entry


def recent(tb, n=50):
    """The newest n events, newest first."""
    try:
        with open(path(tb), "r", encoding="utf-8") as f:
            lines = f.readlines()[-n:]
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out
