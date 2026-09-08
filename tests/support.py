import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import select
import socket
import struct
import threading
import time
from pathlib import Path

import dns.message
import dns.rrset
import libtorrent as lt

from app.socks import read_exact, read_address, address_bytes


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_torrent(
    root, name="payload.bin", tracker=None, seed=1, size=512 * 1024, private=True
):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    payload = bytes((i + seed) % 251 for i in range(size))
    (root / name).write_bytes(payload)
    storage = lt.file_storage()
    storage.add_file(name, len(payload))
    creator = lt.create_torrent(storage, 16384, lt.create_torrent.v1_only)
    creator.set_priv(private)
    if tracker:
        creator.add_tracker(tracker)
    lt.set_piece_hashes(creator, str(root))
    return bytes(lt.bencode(creator.generate())), payload


class SocksServer:
    """Test-only relay: no outgoing Internet is required for the integration suite."""

    def __init__(self, udp=True, reject=False, mappings=None, password_rejected=False):
        self.allow_udp, self.reject = udp, reject
        self.password_rejected = password_rejected
        self.mappings = mappings or {}
        self.requests = []
        self.relays = []
        self.sockets = set()
        self.closed = threading.Event()
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.listener.settimeout(0.2)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self.accept, daemon=True)
        self.thread.start()

    def accept(self):
        while not self.closed.is_set():
            try:
                client, _ = self.listener.accept()
                self.sockets.add(client)
                threading.Thread(
                    target=self.handle, args=(client,), daemon=True
                ).start()
            except (TimeoutError, OSError):
                continue

    def handle(self, client):
        try:
            client.settimeout(3)
            version, count = read_exact(client, 2)
            methods = read_exact(client, count)
            if self.password_rejected and 2 in methods:
                client.sendall(b"\x05\x02")
                auth_version, user_size = read_exact(client, 2)
                read_exact(client, user_size)
                read_exact(client, read_exact(client, 1)[0])
                client.sendall(b"\x01\x01")
                return
            client.sendall(bytes([5, 255 if self.reject or 0 not in methods else 0]))
            if self.reject or 0 not in methods:
                return
            header = read_exact(client, 3)
            host, port = read_address(client)
            self.requests.append((header[1], host, port))
            if header[1] == 3:
                self.relay_udp(client)
                return
            if port == 53 and host == "1.1.1.1":
                client.sendall(b"\x05\x00\x00" + address_bytes("127.0.0.1", 0))
                n = struct.unpack("!H", read_exact(client, 2))[0]
                query = dns.message.from_wire(read_exact(client, n))
                response = dns.message.make_response(query)
                q = query.question[0]
                response.answer.append(
                    dns.rrset.from_text(
                        q.name,
                        60,
                        "IN",
                        q.rdtype,
                        "127.0.0.1" if q.rdtype == 1 else "::1",
                    )
                )
                data = response.to_wire()
                client.sendall(struct.pack("!H", len(data)) + data)
                return
            target = self.mappings.get(host, host)
            remote = socket.create_connection((target, port), timeout=3)
            self.sockets.add(remote)
            with remote:
                client.sendall(b"\x05\x00\x00" + address_bytes("127.0.0.1", 0))
                client.setblocking(False)
                remote.setblocking(False)
                while not self.closed.is_set():
                    ready, _, _ = select.select([client, remote], [], [], 0.2)
                    for source in ready:
                        data = source.recv(65536)
                        if not data:
                            return
                        (remote if source is client else client).sendall(data)
        except Exception:
            pass
        finally:
            client.close()

    def relay_udp(self, control):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as relay:
            relay.bind(("127.0.0.1", 0))
            self.relays.append(relay.getsockname())
            control.sendall(
                b"\x05\x00\x00" + address_bytes("127.0.0.1", relay.getsockname()[1])
            )
            remotes, clients = {}, {}
            try:
                while not self.closed.is_set():
                    ready, _, _ = select.select(
                        [relay, control, *remotes.values()], [], [], 0.1
                    )
                    for source in ready:
                        if source is control:
                            if not control.recv(1024):
                                return
                        elif source is relay:
                            packet, client = relay.recvfrom(65535)
                            if not self.allow_udp:
                                continue
                            import io

                            class Reader:
                                def __init__(self, data):
                                    self.buf = io.BytesIO(data)

                                def recv(self, n):
                                    return self.buf.read(n)

                            reader = Reader(packet[3:])
                            host, port = read_address(reader)
                            body = reader.buf.read()
                            self.requests.append((3, host, port))
                            if port == 53 and host == "1.1.1.1":
                                query = dns.message.from_wire(body)
                                response = dns.message.make_response(query)
                                response.answer.append(
                                    dns.rrset.from_text(
                                        query.question[0].name,
                                        60,
                                        "IN",
                                        "A",
                                        "192.0.2.1",
                                    )
                                )
                                relay.sendto(
                                    b"\x00\x00\x00"
                                    + address_bytes(host, port)
                                    + response.to_wire(),
                                    client,
                                )
                                continue
                            key = (self.mappings.get(host, host), port)
                            if key not in remotes:
                                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                                sock.connect(key)
                                remotes[key] = sock
                            clients[remotes[key]] = (client, host, port)
                            remotes[key].send(body)
                        else:
                            client, host, port = clients[source]
                            try:
                                response = source.recv(65535)
                                relay.sendto(
                                    b"\x00\x00\x00"
                                    + address_bytes(host, port)
                                    + response,
                                    client,
                                )
                            except OSError:
                                continue
            finally:
                for sock in remotes.values():
                    sock.close()

    def close(self):
        self.closed.set()
        self.listener.close()
        for sock in list(self.sockets):
            try:
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
            except OSError:
                pass
        self.thread.join(timeout=1)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Tracker:
    def __init__(self, peer_port=0):
        self.peer_port = peer_port
        self.announces = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_HEAD(self):
                self.send_response(200)
                self.end_headers()

            def do_GET(self):
                owner.announces.append((self.client_address, self.path))
                peers = (
                    socket.inet_aton("127.0.0.1") + struct.pack("!H", owner.peer_port)
                    if owner.peer_port
                    else b""
                )
                body = lt.bencode({b"interval": 2, b"min interval": 1, b"peers": peers})
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def wait_until(fn, timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = fn()
        if result:
            return result
        time.sleep(0.05)
    raise AssertionError("Condition non atteinte avant expiration")
