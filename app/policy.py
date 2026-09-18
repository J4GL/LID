"""Network policy is code, not an overridable bag of libtorrent options."""

from pathlib import Path
from urllib.parse import urlsplit
import ipaddress
import libtorrent as lt

from .socks import MISSING_PROXY, ProxyError


def settings(config, mode, udp=False):
    seed = config.seeding
    result = {
        "user_agent": "LID/1.0 libtorrent/2.1.1",
        "choking_algorithm": int(lt.choking_algorithm_t.fixed_slots_choker),
        "unchoke_slots_limit": -1,
        "upload_rate_limit": seed.upload_limit,
        "download_rate_limit": seed.download_limit,
        "connections_limit": seed.connections,
        "file_pool_size": seed.file_pool_size,
        "active_downloads": -1,
        "active_seeds": -1,
        "active_limit": -1,
        "seeding_outgoing_connections": True,
        "enable_lsd": False,
        "listen_system_port_fallback": False,
        "max_retry_port_bind": 0,
        "validate_https_trackers": True,
        "ssrf_mitigation": True,
        "max_webtorrent_offers": 0,
        "webtorrent_stun_server": "",
        "alert_mask": int(
            lt.alert.category_t.error_notification
            | lt.alert.category_t.status_notification
            | lt.alert.category_t.storage_notification
        ),
    }
    if mode == "direct":
        result.update(
            proxy_type=0,
            force_proxy=False,
            listen_interfaces=f"0.0.0.0:{config.direct.port},[::]:{config.direct.port}",
            enable_upnp=config.direct.upnp,
            enable_natpmp=config.direct.upnp,
            enable_dht=True,
            enable_incoming_tcp=True,
            enable_outgoing_utp=True,
            enable_incoming_utp=True,
        )
        return result
    if mode != "proxy" or not config.proxy.configured:
        raise ProxyError(MISSING_PROXY)
    proxy = config.proxy
    result.update(
        proxy_type=3 if proxy.username or proxy.password else 2,
        proxy_hostname=proxy.host,
        proxy_port=proxy.port,
        proxy_username=proxy.username,
        proxy_password=proxy.password,
        proxy_hostnames=True,
        proxy_peer_connections=True,
        proxy_tracker_connections=True,
        force_proxy=True,
        anonymous_mode=True,
        listen_interfaces="",
        enable_incoming_tcp=False,
        enable_upnp=False,
        enable_natpmp=False,
        enable_lsd=False,
        enable_outgoing_utp=udp,
        enable_incoming_utp=udp,
        enable_dht=udp,
        dht_bootstrap_nodes="",
        socks5_udp_send_local_ep=False,
        announce_ip="",
        announce_port=0,
    )
    return result


def tracker_allowed(url, udp):
    try:
        parsed = urlsplit(url)
        return bool(parsed.hostname) and parsed.scheme.lower() in (
            ("http", "https", "udp") if udp else ("http", "https")
        )
    except ValueError:
        return False


def safe_path(path):
    return (
        bool(path)
        and not path.startswith(("/", "\\"))
        and all(
            part not in ("", ".", "..")
            and "\\" not in part
            and ":" not in part
            and "\x00" not in part
            for part in path.split("/")
        )
    )


def validate_info(info):
    files = info.files()
    if files.num_files() > 100000:
        raise ValueError("Le torrent contient trop de fichiers.")
    for i in range(files.num_files()):
        if not safe_path(files.file_path(i)):
            raise ValueError("Le torrent contient un chemin de fichier non autorisé.")
        if files.file_flags(i) & lt.file_storage.flag_symlink:
            raise ValueError(
                "Les liens symboliques dans les torrents ne sont pas autorisés."
            )


def parse_source(source, mode):
    """Drop outer DHT names before libtorrent ever sees torrent_info."""
    if isinstance(source, bytes):
        if len(source) > 10 * 1024 * 1024:
            raise ValueError("Fichier .torrent trop volumineux (maximum 10 Mio).")
        raw = lt.bdecode(source)
        if not isinstance(raw, dict) or not isinstance(raw.get(b"info"), dict):
            raise ValueError("Fichier .torrent invalide.")
        info = raw[b"info"]

        # Validate original names too, before libtorrent sanitizes them.
        def inspect_tree(tree):
            for name, value in tree.items():
                if name and not safe_path(name.decode("utf-8", "replace")):
                    raise ValueError("Chemin non autorisé dans le torrent.")
                if isinstance(value, dict):
                    inspect_tree(value) if name else None

        name = info.get(b"name.utf-8", info.get(b"name", b""))
        if not safe_path(name.decode("utf-8", "replace")):
            raise ValueError("Nom de torrent non autorisé.")
        for item in info.get(b"files", []):
            if not all(
                safe_path(p.decode("utf-8", "replace"))
                for p in item.get(b"path.utf-8", item.get(b"path", []))
            ):
                raise ValueError("Chemin non autorisé dans le torrent.")
        if b"file tree" in info:
            inspect_tree(info[b"file tree"])
        nodes = normalize_nodes(raw.pop(b"nodes", [])) if mode == "proxy" else []
        params = lt.add_torrent_params()
        params.ti = lt.torrent_info(raw)
        # These names are retained for our SOCKS resolver, then removed from
        # add_torrent_params before handing the torrent to a session.
        if mode == "proxy":
            params.dht_nodes = nodes
        validate_info(params.ti)
        params.trackers = [x.url for x in params.ti.trackers()]
        for seed in params.ti.web_seeds():
            if seed.get("type", 0) == 0:
                params.url_seeds = [*params.url_seeds, seed["url"]]
            else:
                params.http_seeds = [*params.http_seeds, seed["url"]]
        source = bytes(lt.bencode(raw))
    else:
        if len(source) > 32768 or not source.startswith("magnet:?"):
            raise ValueError("Lien magnet invalide.")
        params = lt.parse_magnet_uri(source)
    hashes = []
    if params.ti:
        ih = params.ti.info_hashes()
    else:
        ih = params.info_hashes
    if ih.has_v1():
        hashes.append(str(ih.v1))
    if ih.has_v2():
        hashes.append(str(ih.v2))
    if not hashes:
        raise ValueError("Infohash manquant dans le torrent.")
    return params, source, hashes


def normalize_nodes(nodes):
    result = []
    if not isinstance(nodes, (list, tuple)):
        return result
    for node in nodes[:32]:
        try:
            host, port = node
            if isinstance(host, bytes):
                host = host.decode("utf-8")
            if not isinstance(host, str) or not host or len(host.encode("idna")) > 255:
                continue
            if any(c in host for c in "/@\\ \r\n\x00"):
                continue
            if not isinstance(port, int) or not 1 <= port <= 65535:
                continue
            result.append((host, port))
        except (ValueError, TypeError, UnicodeError):
            continue
    return list(dict.fromkeys(result))


def sanitize_params(params, mode, udp, destination):
    # Never trust paths or traffic-related flags from resume data.
    params.save_path = str(destination)
    params.renamed_files = {}
    params.part_file_dir = ""
    params.max_uploads = -1
    params.url = ""
    params.trackers = [
        x
        for x in params.trackers
        if tracker_allowed(x, udp if mode == "proxy" else True)
    ]
    params.tracker_tiers = list(range(len(params.trackers)))
    params.url_seeds = [x for x in params.url_seeds if tracker_allowed(x, False)]
    params.http_seeds = [x for x in params.http_seeds if tracker_allowed(x, False)]
    if mode == "proxy":
        # Discard untrusted nodes; bootstrap is supplied via our remote resolver.
        params.dht_nodes = []
        params.peers = [(host, port) for host, port in params.peers if is_ip(host)]
    flags = lt.torrent_flags
    params.flags = (
        params.flags | flags.paused | flags.override_trackers | flags.override_web_seeds
    ) & ~flags.auto_managed
    # Metadata must be inspected before downloading any payload from a magnet.
    if not params.ti:
        params.flags |= flags.upload_mode
    else:
        params.flags &= ~flags.upload_mode
        validate_info(params.ti)
    return params


def is_ip(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def destination_for(root: Path, mode, key, layout="nested"):
    # A flat root is the whole library, shared by every completed torrent: it is
    # never walked, and the per-torrent symlink check is done on the torrent's own
    # top-level entries at move time instead.
    destination = root if layout == "flat" else root / mode / key
    if destination.resolve() != destination or any(
        p.is_symlink() for p in [destination, *destination.parents] if p != root.parent
    ):
        raise ValueError("Le dossier de destination contient un lien symbolique.")
    if layout != "flat" and destination.exists():
        for item in destination.rglob("*"):
            if item.is_symlink():
                raise ValueError(
                    "Un lien symbolique existe dans le dossier du torrent."
                )
    return destination


def apply_folder(params, folder):
    """Rename the torrent's top-level entry, when the recorded one differs.

    `sanitize_params` drops every rename carried by resume data; this puts back the
    one the index owns, so a name taken to avoid overwriting something in the final
    folder survives each restart.
    """
    if not folder or not params.ti:
        return params
    files = params.ti.files()
    params.renamed_files = {
        i: str(Path(folder, *Path(files.file_path(i)).parts[1:]))
        for i in range(files.num_files())
    }
    return params
