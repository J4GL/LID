from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import struct
import threading
import time
import libtorrent as lt

from app.engine import Engine
from tests.support import SocksServer, make_torrent, wait_until
from tests.test_integration import engine_config, set_health, seeder


class UDPTracker:
    def __init__(self, peer_port=0):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.settimeout(0.2)
        self.port = self.socket.getsockname()[1]
        self.peer_port = peer_port
        self.requests = []
        self.stopped = False
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while not self.stopped:
            try:
                data, addr = self.socket.recvfrom(65535)
                self.requests.append(data)
                if data.startswith(b"d"):
                    msg = lt.bdecode(data)
                    reply = lt.bencode(
                        {
                            b"t": msg[b"t"],
                            b"y": b"r",
                            b"r": {b"id": b"a" * 20, b"nodes": b"", b"token": b"ok"},
                        }
                    )
                else:
                    action, tx = struct.unpack("!II", data[8:16])
                    if action == 0:
                        reply = struct.pack("!IIQ", 0, tx, 0x11223344)
                    elif action == 1:
                        peers = (
                            socket.inet_aton("127.0.0.1")
                            + struct.pack("!H", self.peer_port)
                            if self.peer_port
                            else b""
                        )
                        reply = struct.pack("!IIIII", 1, tx, 2, 0, 1) + peers
                    else:
                        continue
                self.socket.sendto(reply, addr)
            except (TimeoutError, OSError):
                pass

    def close(self):
        self.stopped = True
        self.socket.close()
        self.thread.join(timeout=1)


def test_libtorrent_udp_tracker_dht_and_utp_via_socks(tmp_path):
    with SocksServer(mappings={"udp-tracker.test": "127.0.0.1"}) as proxy:
        tracker = UDPTracker()
        dht = UDPTracker()
        source, body = make_torrent(
            tmp_path / "seed",
            tracker=f"udp://udp-tracker.test:{tracker.port}/announce",
            seed=77,
        )
        raw = lt.bdecode(source)
        raw[b"nodes"] = [[b"dht-source.test", dht.port]]
        source = bytes(lt.bencode(raw))
        seed, handle, port = seeder(tmp_path / "seed", source)
        # Force both sides to use uTP; successful payload proves UDP transport.
        seed.apply_settings(
            {"enable_incoming_tcp": False, "enable_outgoing_tcp": False}
        )
        tracker.peer_port = port
        config = engine_config(tmp_path, proxy.port)
        engine = Engine(config, "proxy")
        try:
            set_health(engine, udp=True)
            engine.proxy["bootstrap"] = []
            engine.session.apply_settings({"enable_outgoing_tcp": False})
            record = engine.add({"source": source})
            engine.handles[record["id"]].connect_peer(("127.0.0.1", port))
            wait_until(
                lambda: (
                    engine.tick() or engine.handles[record["id"]].status().is_seeding
                ),
                30,
            )
            assert (
                config.storage.downloads / "proxy" / record["id"] / "payload.bin"
            ).read_bytes() == body
            wait_until(
                lambda: (
                    engine.tick()
                    or any(p[1] == "udp-tracker.test" for p in proxy.requests)
                ),
                10,
            )
            assert any(p[0] == 3 and p[2] == port for p in proxy.requests)
            wait_until(
                lambda: (
                    engine.tick()
                    or any(p[0] == 3 and p[2] == dht.port for p in proxy.requests)
                ),
                10,
            )
            assert engine.node_addresses[("dht-source.test", dht.port)] == [
                "127.0.0.1",
                "::1",
            ]
            announces = [
                r
                for r in tracker.requests
                if len(r) >= 98 and struct.unpack("!I", r[8:12])[0] == 1
            ]
            assert announces and all(r[84:88] == b"\x00" * 4 for r in announces)
            # Turning UDP off removes UDP trackers and transports, keeping SOCKS TCP.
            set_health(engine, udp=False)
            effective = engine.session.get_settings()
            assert (
                effective["proxy_type"] == 2
                and not effective["enable_dht"]
                and not effective["enable_outgoing_utp"]
            )
            assert all(
                not t["url"].startswith("udp:")
                for t in engine.handles[record["id"]].trackers()
            )
            engine.close()
            engine = Engine(config, "proxy")
            set_health(engine, udp=True)
            wait_until(lambda: engine.tick() or bool(engine.node_addresses), 10)
            assert engine.node_addresses[("dht-source.test", dht.port)] == [
                "127.0.0.1",
                "::1",
            ]
        finally:
            engine.close()
            seed.pause()
            tracker.close()
            dht.close()


def test_webseed_uses_proxy_and_remote_hostname(tmp_path):
    source, body = make_torrent(tmp_path / "seed", seed=88)
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            start, end = 0, len(body) - 1
            if self.headers.get("Range"):
                left, right = self.headers["Range"].removeprefix("bytes=").split("-")
                start = int(left)
                end = int(right) if right else end
            payload = body[start : end + 1]
            self.send_response(206 if self.headers.get("Range") else 200)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(body)}")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    web = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=web.serve_forever, daemon=True)
    thread.start()
    with SocksServer(mappings={"webseed.test": "127.0.0.1"}) as proxy:
        raw = lt.bdecode(source)
        raw[b"url-list"] = [
            f"http://webseed.test:{web.server_address[1]}/payload.bin".encode()
        ]
        config = engine_config(tmp_path, proxy.port)
        engine = Engine(config, "proxy")
        try:
            set_health(engine)
            record = engine.add({"source": bytes(lt.bencode(raw))})
            wait_until(
                lambda: (
                    engine.tick() or engine.handles[record["id"]].status().is_seeding
                ),
                30,
            )
            assert (
                config.storage.downloads / "proxy" / record["id"] / "payload.bin"
            ).read_bytes() == body
            assert requests and any(h == "webseed.test" for _, h, _ in proxy.requests)
        finally:
            engine.close()
            web.shutdown()
            web.server_close()


def test_ipv6_peer_over_ipv4_proxy(tmp_path):
    with SocksServer() as proxy:
        source, body = make_torrent(tmp_path / "seed", seed=99)
        seed, handle, port = seeder(tmp_path / "seed", source, host="::1")
        config = engine_config(tmp_path, proxy.port)
        engine = Engine(config, "proxy")
        try:
            set_health(engine)
            record = engine.add({"source": source})
            engine.handles[record["id"]].connect_peer(("::1", port))
            wait_until(
                lambda: (
                    engine.tick() or engine.handles[record["id"]].status().is_seeding
                ),
                20,
            )
            assert (
                config.storage.downloads / "proxy" / record["id"] / "payload.bin"
            ).read_bytes() == body
            assert (1, "::1", port) in proxy.requests
        finally:
            engine.close()
            seed.pause()
