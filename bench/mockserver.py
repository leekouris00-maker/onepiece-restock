"""
A local HTTPS "internet" for benchmarks and tests: every shop, Discord, ntfy and GitHub raw on one
port, routed by Host header, with a network model so timings mean something:

  * conn_setup   - delay before the TLS handshake, standing in for TCP + TLS round trips
  * ttfb         - server think time per request type (Shopify renders products.json slowly)
  * bandwidth    - bytes per second per connection while sending the body
  * jitter       - log-normal noise on think time, so p95/p99 aren't flat

It speaks real HTTP/1.1 over real TLS (certificate for every shop hostname), honours keep-alive
exactly like a normal server (urllib's "Connection: close" really closes), gzip-compresses when asked,
and can optionally send ETags and answer If-None-Match with 304.
"""
import gzip
import hashlib
import json
import math
import random
import re
import socket
import ssl
import threading
import time
import urllib.parse
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler

from fixtures import POKEBOX_EB05, product_js, suggest_result  # noqa: F401  (EB05 used by callers)


class Profile:
    def __init__(self, conn_setup=0.060, bandwidth=4_000_000, jitter=0.30, etag=False, scale=1.0,
                 ttfb=None, seed=7):
        self.conn_setup = conn_setup
        self.bandwidth = bandwidth
        self.jitter = jitter
        self.etag = etag
        self.scale = scale
        self.ttfb = {"collection": 0.65, "collection_per_product": 0.0016, "product_js": 0.16,
                     "suggest": 0.24, "woo": 0.85, "robots": 0.05, "raw": 0.08, "discord": 0.14,
                     "ntfy": 0.09, "other": 0.10}
        self.ttfb.update(ttfb or {})
        self.slow_hosts = {}           # host -> extra seconds of think time
        self.flaky_hosts = {}          # host -> probability of a 503
        self.discord_429 = 0           # first N webhook posts get a 429
        self.rng = random.Random(seed)
        self.lock = threading.Lock()

    def think(self, kind, n_products=0, host=""):
        base = self.ttfb.get(kind, self.ttfb["other"])
        if kind == "collection":
            base += n_products * self.ttfb["collection_per_product"]
        with self.lock:
            noise = math.exp(self.rng.gauss(0, self.jitter)) if self.jitter else 1.0
        return (base * noise + self.slow_hosts.get(host, 0.0)) * self.scale

    def flaky(self, host):
        p = self.flaky_hosts.get(host, 0)
        if not p:
            return False
        with self.lock:
            return self.rng.random() < p


class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        with getattr(self, "lock", threading.Lock()):
            self.connections = 0
            self.requests = 0
            self.bytes_out = 0
            self.by_host = defaultdict(Counter)
            self.statuses = Counter()
            self.discord = []          # posted payloads
            self.ntfy = []
            self.paths = Counter()

    def snapshot(self):
        with self.lock:
            return {"connections": self.connections, "requests": self.requests, "bytes_out": self.bytes_out,
                    "statuses": dict(self.statuses), "discord_posts": len(self.discord),
                    "by_host": {h: dict(c) for h, c in self.by_host.items()}}


ROBOTS_SHOPIFY = """# Shopify-style robots.txt (trimmed)
User-agent: *
Disallow: /admin
Disallow: /cart
Disallow: /orders
Disallow: /checkouts/
Disallow: /checkout
Disallow: /account
Disallow: /collections/*sort_by*
Disallow: /*/collections/*sort_by*
Disallow: /collections/*+*
Disallow: /recommendations/products
Disallow: /cart.js
Disallow: /cdn/wpm/*.js
Allow: /

User-agent: Nutch
Disallow: /
"""


class MockInternet:
    def __init__(self, data, profile=None, certfile=None, keyfile=None, port=0):
        self.data = data
        self.profile = profile or Profile()
        self.stats = Stats()
        self.ntfy_pc_on = False
        self.ntfy_last = 0.0
        self.robots = {}                     # host -> text override (or a status code)
        self.script = {}                     # (host, path) -> [(status, headers, body), ...] served first, in order
        self.idle_timeout = 20               # seconds the server keeps an idle keep-alive connection open
        self.discord_fail = 0                # webhook posts answer 500 while this is > 0 (counts down)
        self._gz = {}
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile, keyfile)
        self.ctx = ctx
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(1024)
        self.port = self.sock.getsockname()[1]
        self._stop = False
        self.thread = threading.Thread(target=self._accept, daemon=True)

    # ------------------------------------------------------------------ plumbing
    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self._stop = True
        try:
            self.sock.close()
        except OSError:
            pass

    def _accept(self):
        while not self._stop:
            try:
                raw, addr = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._conn, args=(raw, addr), daemon=True).start()

    def _conn(self, raw, addr):
        with self.stats.lock:
            self.stats.connections += 1
        try:
            time.sleep(self.profile.conn_setup * self.profile.scale)   # TCP + TLS round trips
            ssock = self.ctx.wrap_socket(raw, server_side=True)
        except (OSError, ssl.SSLError):
            raw.close()
            return
        try:
            _Handler(ssock, addr, self)
        except Exception:  # noqa: BLE001
            pass
        finally:
            try:
                ssock.close()
            except OSError:
                pass

    def gz(self, key, body):
        hit = self._gz.get(key)
        if hit is None or hit[0] != len(body):
            hit = (len(body), gzip.compress(body, 6))
            self._gz[key] = hit
        return hit[1]

    # ------------------------------------------------------------------ routing
    def route(self, method, host, path, query, body):
        """-> (status, content_type, body_bytes, kind, n_products, extra_headers)"""
        host = host.lower().split(":")[0]
        d = self.data
        queue = self.script.get((host, path))
        if queue:
            status, hdrs, blob = queue.pop(0)
            return status, "application/json", blob, "other", 0, dict(hdrs)
        if path == "/robots.txt":
            txt = self.robots.get(host)
            if txt is None:
                txt = ROBOTS_SHOPIFY if host in d["shopify"] else "User-agent: *\nDisallow: /wp-admin/\n"
            if isinstance(txt, int):
                return txt, "text/plain", b"", "robots", 0, {}
            return 200, "text/plain", txt.encode(), "robots", 0, {}
        if host == "discord.com":
            return self._discord(path, query, body)
        if host == "ntfy.sh":
            return self._ntfy(method, path, query, body)
        if host == "raw.githubusercontent.com":
            blob = d["raw"].get(path)
            return (200, "text/plain", blob, "raw", 0, {}) if blob is not None else (404, "text/plain", b"404: Not Found", "raw", 0, {})
        if host in d["refuse"]:
            return d["refuse"][host], "text/html", b"<html><body>Forbidden</body></html>", "other", 0, {}
        if self.profile.flaky(host):
            return 503, "text/html", b"<html>Service Unavailable</html>", "other", 0, {}
        if host in d["woo"] and path.startswith("/wp-json/wc/store/v1/products"):
            return 200, "application/json", json.dumps(d["woo"][host]).encode(), "woo", 0, {}
        shop = d["shopify"].get(host)
        if not shop:
            return 404, "text/html", b"not found", "other", 0, {}
        m = re.fullmatch(r"/collections/([^/]+)/products\.json", path)
        if m:
            items = shop["collections"].get(m.group(1))
            if items is None:
                return 404, "application/json", b'{"errors":"Not Found"}', "collection", 0, {}
            limit = max(1, min(250, int(query.get("limit", ["30"])[0] or 30)))
            page = max(1, int(query.get("page", ["1"])[0] or 1))
            chunk = items[(page - 1) * limit: page * limit]
            return 200, "application/json", json.dumps({"products": chunk}).encode(), "collection", len(chunk), {}
        m = re.fullmatch(r"/products/([^/]+)\.js", path)
        if m:
            p = shop["products"].get(m.group(1))
            if not p:
                return 404, "application/json", b'{"status":404,"message":"Not Found"}', "product_js", 0, {}
            return 200, "application/json", json.dumps(product_js(p)).encode(), "product_js", 0, {}
        if path == "/search/suggest.json":
            q = query.get("q", [""])[0]
            limit = max(1, min(10, int(query.get("resources[limit]", ["10"])[0] or 10)))
            toks = [t for t in re.split(r"[^a-z0-9]+", q.lower()) if t]
            hits = []
            for p in shop["index"]:
                hay = " ".join(re.split(r"[^a-z0-9]+", (p["title"] + " " + " ".join(p["tags"]) + " " +
                                                         p["body_html"][:300]).lower()))
                if toks and all(t in hay for t in toks):
                    hits.append(p)
            hits.sort(key=lambda p: not any(v["available"] for v in p["variants"]))   # unavailable last
            res = {"resources": {"results": {"products": [suggest_result(p) for p in hits[:limit]]}}}
            return 200, "application/json", json.dumps(res).encode(), "suggest", 0, {}
        return 404, "text/html", b"not found", "other", 0, {}

    def _discord(self, path, query, body):
        if not re.fullmatch(r"/api/webhooks/[^/]+/[^/]+", path):
            return 404, "application/json", b'{"message":"Unknown Webhook","code":10015}', "discord", 0, {}
        with self.stats.lock:
            n_before = len(self.stats.discord) + self.stats.statuses.get(429, 0)
            limited = self.profile.discord_429 and n_before < self.profile.discord_429
            failing = self.discord_fail > 0
            if failing:
                self.discord_fail -= 1
        if failing:
            return 500, "application/json", b'{"message":"500: Internal Server Error","code":0}', "discord", 0, {}
        if limited:
            ra = 0.35
            return 429, "application/json", json.dumps({"message": "You are being rate limited.", "retry_after": ra,
                                                         "global": False}).encode(), "discord", 0, {"Retry-After": "1"}
        try:
            payload = json.loads(body or b"{}")
        except ValueError:
            return 400, "application/json", b'{"message":"Cannot send an empty message","code":50006}', "discord", 0, {}
        embeds = payload.get("embeds") or []
        chars = sum(len(json.dumps(e)) for e in embeds)
        if len(embeds) > 10 or len(payload.get("content") or "") > 2000:
            return 400, "application/json", b'{"message":"Invalid Form Body","code":50035}', "discord", 0, {}
        if payload.get("components") and query.get("with_components", ["false"])[0] != "true":
            payload["components_ignored"] = True
        with self.stats.lock:
            self.stats.discord.append(payload)
        if query.get("wait", ["false"])[0] == "true":
            return 200, "application/json", json.dumps({"id": "1", "embeds": embeds, "chars": chars}).encode(), "discord", 0, {}
        return 204, "application/json", b"", "discord", 0, {}

    def _ntfy(self, method, path, query, body):
        if method == "POST":
            with self.stats.lock:
                self.stats.ntfy.append((path, body))
            self.ntfy_last = time.time()
            return 200, "application/json", b'{"id":"x","event":"message"}', "ntfy", 0, {}
        if path.endswith("/json"):
            lines = ""
            if self.ntfy_pc_on:
                lines = json.dumps({"id": "hb", "time": int(self.ntfy_last or time.time()), "event": "message",
                                    "topic": path.strip("/").split("/")[0], "message": "pc-on"}) + "\n"
            return 200, "application/x-ndjson", lines.encode(), "ntfy", 0, {}
        return 404, "text/plain", b"", "ntfy", 0, {}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 20                      # idle keep-alive timeout

    def __init__(self, request, client_address, server):
        self.inet = server
        self.timeout = getattr(server, "idle_timeout", 20)
        super().__init__(request, client_address, server)

    def log_message(self, *a):        # quiet
        pass

    def _do(self, method):
        inet = self.inet
        url = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(url.query, keep_blank_values=True)
        host = (self.headers.get("Host") or "").lower().split(":")[0]
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        status, ctype, payload, kind, n_products, extra = inet.route(method, host, url.path, query, body)
        prof = inet.profile
        headers = {"Content-Type": ctype}
        headers.update(extra)
        if prof.etag and status == 200 and kind in ("collection", "product_js", "suggest", "woo"):
            tag = 'W/"' + hashlib.md5(payload).hexdigest()[:16] + '"'
            headers["ETag"] = tag
            if tag in (self.headers.get("If-None-Match") or ""):
                status, payload = 304, b""
        if payload and "gzip" in (self.headers.get("Accept-Encoding") or "") and len(payload) > 512:
            payload = inet.gz((host, url.path, url.query, len(payload)), payload)
            headers["Content-Encoding"] = "gzip"
            headers["Vary"] = "Accept-Encoding"
        time.sleep(prof.think(kind, n_products, host))
        with inet.stats.lock:
            inet.stats.requests += 1
            inet.stats.statuses[status] += 1
            inet.stats.by_host[host]["requests"] += 1
            inet.stats.by_host[host][f"s{status}"] += 1
            inet.stats.paths[(host, kind)] += 1
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(payload)))
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        if payload and method != "HEAD":
            step = 32 * 1024
            per = step / max(1.0, prof.bandwidth / prof.scale if prof.scale else prof.bandwidth)
            for i in range(0, len(payload), step):
                self.wfile.write(payload[i:i + step])
                if len(payload) > step:
                    time.sleep(per)
            with inet.stats.lock:
                inet.stats.bytes_out += len(payload)

    def do_GET(self):
        self._do("GET")

    def do_POST(self):
        self._do("POST")

    def do_HEAD(self):
        self._do("HEAD")
