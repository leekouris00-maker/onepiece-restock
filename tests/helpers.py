"""Shared test plumbing: the mock shops from bench/, pointed at by both in-process and subprocess bots."""
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
BENCH = os.path.join(REPO, "bench")
for p in (REPO, BENCH):
    if p not in sys.path:
        sys.path.insert(0, p)

import fixtures  # noqa: E402
from mockserver import MockInternet, Profile  # noqa: E402

V1_BOT = os.environ.get("V1_BOT") or os.path.join(BENCH, "baseline", "tcg_bot_v1.py")
WEBHOOKS = {"DISCORD_WEBHOOK_BOXES": "https://discord.com/api/webhooks/1001/boxes-token",
            "DISCORD_WEBHOOK_SINGLES": "https://discord.com/api/webhooks/1002/singles-token",
            "DISCORD_WEBHOOK_SEALED": "https://discord.com/api/webhooks/1003/sealed-token",
            "DISCORD_PING": "<@&123456789012345678>"}


def have_crypto():
    try:
        import cryptography  # noqa: F401
        return True
    except ImportError:
        return False


class Net:
    """Mock internet + certificate, started once per test module."""

    def __init__(self, scenario="baseline", profile=None):
        import certs
        self.dir = tempfile.mkdtemp(prefix="restock-test-")
        self.hosts = fixtures.all_hosts() + ["redirect.example.com"]
        self.ca, cert, key = certs.make(os.path.join(self.dir, "tls"), self.hosts)
        self.inet = MockInternet(fixtures.build(scenario), profile or Profile(conn_setup=0, jitter=0, scale=0.01),
                                 cert, key).start()
        self._real = None

    # in-process: point this Python's DNS at the mock and trust its certificate
    def patch_process(self, tb):
        hosts, port = set(self.hosts), self.inet.port
        real = socket.getaddrinfo
        self._real = real

        def getaddrinfo(host, p, *a, **k):
            if isinstance(host, str) and host.lower() in hosts:
                return real("127.0.0.1", port, *a, **k)
            return real(host, p, *a, **k)
        socket.getaddrinfo = getaddrinfo
        tb.HTTP._ctx = tb.tls_context(cafile=self.ca)   # the real handshake settings, trusting the mock's CA
        os.environ["no_proxy"] = os.environ["NO_PROXY"] = "*"

    def unpatch_process(self):
        if self._real:
            socket.getaddrinfo = self._real

    def env(self, extra=None):
        env = dict(os.environ)
        env.update({"PYTHONPATH": os.path.join(BENCH, "inject"), "BENCH_HOSTS": ",".join(self.hosts),
                    "BENCH_PORT": str(self.inet.port), "SSL_CERT_FILE": self.ca, "no_proxy": "*", "NO_PROXY": "*",
                    "TZ": "Australia/Melbourne", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
        for k in ("DISCORD_WEBHOOK", "NTFY_TOPIC", "HEARTBEAT_TOPIC", "HEARTBEAT_ROLE", "GITHUB_ACTIONS"):
            env.pop(k, None)
        env.update(extra or {})
        return env

    def stop(self):
        self.inet.stop()
        shutil.rmtree(self.dir, ignore_errors=True)


def bot_dir(bot_path, cfg=None, base=None):
    d = tempfile.mkdtemp(prefix="bot-", dir=base)
    shutil.copy(bot_path, os.path.join(d, "tcg_bot.py"))
    if cfg is None:
        with open(os.path.join(REPO, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
    return d


def run_bot(net, d, args=(), extra_env=None, timeout=180):
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, "-u", "tcg_bot.py", *args], cwd=d, env=net.env(extra_env),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    p.secs = time.perf_counter() - t0
    return p


def load(d, name, default=None):
    try:
        with open(os.path.join(d, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default
