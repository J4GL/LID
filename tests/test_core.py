import socket
from pathlib import Path
from concurrent.futures import Future

import libtorrent as lt
import pytest
import yaml

from app.config import Config, Proxy, load_config
from app.engine import Engine
from app.policy import parse_source, sanitize_params, settings
from app.socks import MISSING_PROXY, ProxyError, connect, probe_udp, resolve_remote
from tests.support import SocksServer, make_torrent
from app.socks import check_proxy


@pytest.fixture
def config(tmp_path):
    c = Config()
    c.storage.state = tmp_path / "state"
    c.storage.downloads = tmp_path / "downloads"
    c.proxy.enabled = False
    return c


@pytest.mark.parametrize("proxy", [None, {}, {"enabled": True}])
def test_missing_proxy_never_defaults_to_direct(tmp_path, proxy):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump({"proxy": proxy}))
    c = load_config(p)
    assert not c.proxy.configured
    with pytest.raises(ProxyError, match="Aucun proxy"):
        settings(c, "proxy")


def test_red_refusal_no_session_no_record(config):
    engine = Engine(config, "proxy")
    try:
        with pytest.raises(ProxyError, match="Aucun proxy"):
            engine.add({"source": "magnet:?xt=urn:btih:" + "1" * 40})
        assert engine.session is None and engine.records == {} and engine.handles == {}
        assert not list(engine.folder.glob("*.source"))
    finally:
        engine.close()


def test_invalid_proxy_yaml_is_readable(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("proxy: socks://invalid")
    with pytest.raises(ValueError, match="section proxy"):
        load_config(path)


def test_password_authentication_rejected_without_admission(config):
    with SocksServer(password_rejected=True) as proxy:
        config.proxy = Proxy(
            host="127.0.0.1",
            port=proxy.port,
            username="fixture",
            password="invalid",
            timeout=1,
        )
        health = check_proxy(config.proxy)
        assert (
            not health["tcp"] and "Authentification SOCKS5 refusée" in health["message"]
        )
        engine = Engine(config, "proxy")
        try:
            engine.health_future = Future()
            engine.health_future.set_result(health)
            engine.update_health()
            with pytest.raises(ProxyError, match="Authentification SOCKS5 refusée"):
                engine.add({"source": "magnet:?xt=urn:btih:" + "1" * 40})
            assert engine.session is None and not engine.handles and not engine.records
            assert not list(engine.folder.glob("*.source"))
        finally:
            engine.close()


def test_policy_and_resume_cannot_override_route(config, tmp_path):
    config.proxy.enabled = True
    config.proxy.host = "proxy.test"
    values = settings(config, "proxy", False)
    assert values["proxy_type"] == 2 and values["proxy_port"] == 1080
    assert all(
        values[k]
        for k in (
            "force_proxy",
            "proxy_hostnames",
            "proxy_peer_connections",
            "proxy_tracker_connections",
            "anonymous_mode",
        )
    )
    assert all(
        not values[k]
        for k in (
            "enable_dht",
            "enable_lsd",
            "enable_upnp",
            "enable_natpmp",
            "enable_incoming_tcp",
            "enable_incoming_utp",
            "enable_outgoing_utp",
        )
    )
    assert values["unchoke_slots_limit"] == -1
    p = lt.add_torrent_params()
    p.save_path = "/etc"
    p.renamed_files = {0: "/etc/passwd"}
    p.dht_nodes = [("leak.test", 6881)]
    p.trackers = [
        "udp://tracker.test:80",
        "http://tracker.test/announce",
        "wss://tracker.test",
    ]
    p.flags = lt.torrent_flags.auto_managed
    sanitize_params(p, "proxy", False, tmp_path)
    assert p.save_path == str(tmp_path) and not p.renamed_files and not p.dht_nodes
    assert list(p.trackers) == ["http://tracker.test/announce"]
    assert p.flags & lt.torrent_flags.paused
    assert not p.flags & lt.torrent_flags.auto_managed


def test_torrent_validation_removes_nodes_before_parsing(tmp_path):
    source, _ = make_torrent(tmp_path / "seed")
    raw = lt.bdecode(source)
    raw[b"nodes"] = [[b"never-resolve.test", 6881]]
    p, clean, hashes = parse_source(bytes(lt.bencode(raw)), "proxy")
    assert b"nodes" not in lt.bdecode(clean)
    assert hashes
    raw[b"info"][b"name"] = b"../escape"
    with pytest.raises(ValueError):
        parse_source(bytes(lt.bencode(raw)), "proxy")


def test_socks_noauth_remote_dns_and_real_udp(monkeypatch):
    with SocksServer() as proxy:
        conf = Proxy(host="127.0.0.1", port=proxy.port, timeout=1)
        original = socket.getaddrinfo
        looked_up = []

        def guarded(host, *args, **kwargs):
            looked_up.append(host)
            assert host == "127.0.0.1", "DNS destination leaked locally"
            return original(host, *args, **kwargs)

        monkeypatch.setattr(socket, "getaddrinfo", guarded)
        assert resolve_remote(conf, "dht.test") == ["127.0.0.1", "::1"]
        probe_udp(conf)
        assert looked_up and all(h == "127.0.0.1" for h in looked_up)


def test_udp_associate_without_reply_is_failure():
    with SocksServer(udp=False) as proxy:
        conf = Proxy(host="127.0.0.1", port=proxy.port, timeout=0.2)
        with pytest.raises(TimeoutError):
            probe_udp(conf)


def test_whitelist_rejected():
    with SocksServer(reject=True) as proxy:
        with pytest.raises(ProxyError, match="liste blanche"):
            with connect(Proxy(host="127.0.0.1", port=proxy.port, timeout=1)):
                pass


def test_health_transition_never_changes_proxy_settings(config):
    config.proxy.enabled = True
    engine = Engine(config, "proxy")
    calls = []

    class Session:
        def pause(self):
            calls.append("pause")

        def resume(self):
            calls.append("resume")

        def apply_settings(self, values):
            calls.append(values)

    engine.session = Session()
    engine.proxy.update(tcp=True, udp=True)
    engine.health_future = Future()
    engine.health_future.set_result({**engine.proxy, "tcp": False, "udp": False})
    engine.update_health()
    assert calls[0] == "pause"
    assert not any(isinstance(c, dict) and c.get("proxy_type") == 0 for c in calls)
    engine.session = None
    engine.close()
