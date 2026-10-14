"""The bot's TLS handshake must look like urllib's (what v1 sent). On 14 Oct 2026 v2's bare
ssl.create_default_context() left out ALPN and post-handshake auth, and every shop answered 403."""
import os
import socket
import struct
import sys
import threading
import unittest
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tcg_bot as tb  # noqa: E402


def _extensions(hello):
    """Extension types and ALPN names from a raw TLS ClientHello record."""
    p = 5 + 4 + 2 + 32                       # record header, handshake header, version, random
    p += 1 + hello[p]                        # session id
    p += 2 + struct.unpack(">H", hello[p:p + 2])[0]   # cipher suites
    p += 1 + hello[p]                        # compression methods
    end = p + 2 + struct.unpack(">H", hello[p:p + 2])[0]
    p += 2
    types, alpn = [], []
    while p < end:
        t, n = struct.unpack(">HH", hello[p:p + 4])
        types.append(t)
        if t == 16:                          # ALPN: 2-byte list length, then length-prefixed names
            d = hello[p + 6:p + 4 + n]
            while d:
                alpn.append(d[1:1 + d[0]].decode())
                d = d[1 + d[0]:]
        p += 4 + n
    return sorted(types), alpn


def _client_hello(connect):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    got = {}

    def serve():
        conn, _ = srv.accept()
        got["hello"] = conn.recv(65536)
        conn.close()

    t = threading.Thread(target=serve)
    t.start()
    try:
        connect(srv.getsockname()[1])
    except Exception:  # noqa: BLE001  (the fake server hangs up; only the hello matters)
        pass
    t.join(5)
    srv.close()
    return _extensions(got["hello"])


class Handshake(unittest.TestCase):
    def test_bot_offers_alpn_http11(self):
        _, alpn = _client_hello(lambda port: tb.tls_context().wrap_socket(
            socket.create_connection(("127.0.0.1", port), timeout=5), server_hostname="localhost"))
        self.assertEqual(alpn, ["http/1.1"])

    def test_bot_handshake_matches_urllib(self):
        bot = _client_hello(lambda port: tb.tls_context().wrap_socket(
            socket.create_connection(("127.0.0.1", port), timeout=5), server_hostname="localhost"))
        lib = _client_hello(lambda port: urllib.request.urlopen(f"https://localhost:{port}/", timeout=5))
        self.assertEqual(bot, lib)


if __name__ == "__main__":
    unittest.main()
