"""Minimal SOCKS5 transport. Only the proxy host is resolved by the OS."""

import ipaddress
import socket
import ssl
import struct
import time
from contextlib import contextmanager

import dns.message
import dns.rdatatype

from .config import Proxy


class ProxyError(Exception):
    pass


MISSING_PROXY = "Aucun proxy configuré : téléchargement bloqué. Configurez le proxy dans config.yaml."


def read_exact(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ProxyError("Le proxy a fermé la connexion.")
        data += chunk
    return data


def address_bytes(host, port):
    try:
        address = ipaddress.ip_address(host)
        prefix = bytes([1 if address.version == 4 else 4]) + address.packed
    except ValueError:
        name = host.encode("idna")
        if not name or len(name) > 255:
            raise ProxyError("Nom de destination invalide.")
        prefix = bytes([3, len(name)]) + name
    return prefix + struct.pack("!H", port)


def read_address(sock):
    kind = read_exact(sock, 1)[0]
    if kind == 1:
        host = socket.inet_ntop(socket.AF_INET, read_exact(sock, 4))
    elif kind == 4:
        host = socket.inet_ntop(socket.AF_INET6, read_exact(sock, 16))
    elif kind == 3:
        host = read_exact(sock, read_exact(sock, 1)[0]).decode("ascii")
    else:
        raise ProxyError("Réponse SOCKS5 invalide.")
    return host, struct.unpack("!H", read_exact(sock, 2))[0]


@contextmanager
def connect(proxy: Proxy, target="example.com", port=443, command=1):
    if not proxy.configured:
        raise ProxyError(MISSING_PROXY)
    # Deliberately do not read HTTP_PROXY / ALL_PROXY environment variables.
    sock = socket.create_connection((proxy.host, proxy.port), timeout=proxy.timeout)
    try:
        auth = bool(proxy.username or proxy.password)
        sock.sendall(b"\x05\x01" + (b"\x02" if auth else b"\x00"))
        response = read_exact(sock, 2)
        if response != bytes([5, 2 if auth else 0]):
            raise ProxyError(
                "Accès SOCKS5 refusé : vérifier la liste blanche d’IP ou les identifiants YAML."
            )
        if auth:
            user, password = proxy.username.encode(), proxy.password.encode()
            if len(user) > 255 or len(password) > 255:
                raise ProxyError("Identifiants SOCKS5 trop longs.")
            sock.sendall(
                bytes([1, len(user)]) + user + bytes([len(password)]) + password
            )
            if read_exact(sock, 2) != b"\x01\x00":
                raise ProxyError("Authentification SOCKS5 refusée.")
        sock.sendall(bytes([5, command, 0]) + address_bytes(target, port))
        header = read_exact(sock, 3)
        if header[0] != 5 or header[2] != 0 or header[1] != 0:
            raise ProxyError(
                f"Le proxy a refusé la connexion (code SOCKS5 {header[1]})."
            )
        bound = read_address(sock)
        yield sock, bound
    finally:
        sock.close()


def resolve_remote(proxy, hostname):
    """DNS over TCP inside SOCKS, including IPv6; never socket.getaddrinfo(target)."""
    try:
        return [str(ipaddress.ip_address(hostname))]
    except ValueError:
        pass
    result = []
    for kind in (dns.rdatatype.A, dns.rdatatype.AAAA):
        query = dns.message.make_query(hostname, kind)
        wire = query.to_wire()
        with connect(proxy, proxy.dns_server, 53) as (sock, _):
            sock.sendall(struct.pack("!H", len(wire)) + wire)
            size = struct.unpack("!H", read_exact(sock, 2))[0]
            response = dns.message.from_wire(read_exact(sock, size))
        if not query.is_response(response):
            raise ProxyError("Réponse DNS via proxy invalide.")
        for answer in response.answer:
            if answer.rdtype == kind:
                result.extend(str(record.address) for record in answer)
    if not result:
        raise ProxyError("Résolution DNS via proxy impossible.")
    return result


def probe_tcp(proxy):
    with connect(proxy) as (sock, _):
        with ssl.create_default_context().wrap_socket(
            sock, server_hostname="example.com"
        ) as tls:
            tls.sendall(
                b"HEAD / HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n"
            )
            response = tls.recv(512)
            if not response.startswith(b"HTTP/"):
                raise ProxyError("Le proxy ne transmet pas les requêtes TCP.")


def unwrap_udp(packet):
    if len(packet) < 7 or packet[:3] != b"\x00\x00\x00":
        raise ProxyError("Datagramme SOCKS5 invalide.")
    kind = packet[3]
    if kind == 1:
        offset = 10
    elif kind == 4:
        offset = 22
    elif kind == 3:
        offset = 7 + packet[4]
    else:
        raise ProxyError("Adresse UDP SOCKS5 invalide.")
    if len(packet) < offset:
        raise ProxyError("Datagramme SOCKS5 incomplet.")
    return packet[offset:]


def probe_udp(proxy):
    # An ASSOCIATE success alone is NOT a successful UDP test.
    with connect(proxy, "0.0.0.0", 0, command=3) as (control, relay):
        host, port = relay
        if host in ("0.0.0.0", "::"):
            host = control.getpeername()[0]
        # Never resolve a relay name using the local DNS resolver.
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = ipaddress.ip_address(resolve_remote(proxy, host)[0])
        query = dns.message.make_query("example.com", "A")
        with socket.socket(
            socket.AF_INET if address.version == 4 else socket.AF_INET6,
            socket.SOCK_DGRAM,
        ) as udp:
            udp.settimeout(proxy.timeout)
            udp.connect((str(address), port))
            udp.send(
                b"\x00\x00\x00" + address_bytes(proxy.dns_server, 53) + query.to_wire()
            )
            response = dns.message.from_wire(unwrap_udp(udp.recv(65535)))
            if (
                not query.is_response(response)
                or response.rcode() != 0
                or not response.answer
            ):
                raise ProxyError("Aucun aller-retour UDP valide via le proxy.")


def check_proxy(proxy):
    result = {
        "configured": proxy.configured,
        "tcp": False,
        "udp": False,
        "checked_at": time.time(),
        "message": MISSING_PROXY,
        "bootstrap": [],
        "audit": "not_verified",
    }
    if not proxy.configured:
        return result
    try:
        probe_tcp(proxy)
        result.update(tcp=True, message="Proxy actif — TCP")
    except Exception as exc:
        result["message"] = (
            f"Proxy indisponible : téléchargements proxy bloqués. {safe_error(exc)}"
        )
        return result
    if proxy.udp == "off":
        return result
    try:
        probe_udp(proxy)
        result.update(udp=True, message="Proxy actif — TCP + UDP")
        for node in proxy.dht_bootstrap:
            try:
                host, port = node.rsplit(":", 1)
                for address in resolve_remote(proxy, host.strip("[]")):
                    result["bootstrap"].append((address, int(port)))
            except Exception:
                continue
        if not result["bootstrap"]:
            result["message"] = (
                "Proxy actif — UDP disponible, amorçage DHT indisponible"
            )
    except Exception:
        result["message"] = "Proxy actif — UDP indisponible"
    return result


def safe_error(exc):
    # Exception messages from sockets are safe; no tracker URLs or credentials.
    if isinstance(exc, ProxyError):
        return str(exc)
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "Délai de connexion dépassé."
    if isinstance(exc, socket.gaierror):
        return "Nom du proxy introuvable."
    return "Connexion impossible."
