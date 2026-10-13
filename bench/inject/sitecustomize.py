# Loaded automatically by Python when bench/inject is on PYTHONPATH (benchmarks and tests only).
# Points the mocked shop hostnames at the local mock server, so the bot under test runs unmodified:
# same URLs, same TLS hostname checks, just a different IP and port.
import os
import socket

_hosts = {h.strip().lower() for h in os.environ.get("BENCH_HOSTS", "").split(",") if h.strip()}
_port = int(os.environ.get("BENCH_PORT", "0") or 0)

if _hosts and _port:
    _real_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):  # noqa: A002
        if isinstance(host, str) and host.lower().rstrip(".") in _hosts:
            return _real_getaddrinfo("127.0.0.1", _port, family, type, proto, flags)
        return _real_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = getaddrinfo
