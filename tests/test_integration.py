"""Real libtorrent transfers through a local, recorded SOCKS5 relay."""

from concurrent.futures import Future
import hashlib
import json
import time

import libtorrent as lt
import pytest

from app.config import Config
from app.engine import Engine
from app.policy import parse_source
from app.socks import connect
from tests.support import SocksServer, Tracker, make_torrent, free_port, wait_until


def seeder(root, source, host="127.0.0.1"):
    port = free_port()
    address = f"[{host}]" if ":" in host else host
    session = lt.session(
        {
            "listen_interfaces": f"{address}:{port}",
            "enable_dht": False,
            "enable_lsd": False,
            "enable_upnp": False,
            "enable_natpmp": False,
            "unchoke_slots_limit": -1,
            "allow_multiple_connections_per_ip": True,
        },
        flags=0,
    )
    session.add_extension(lt.create_ut_metadata_plugin)
    p, _, _ = parse_source(source, "direct")
    p.save_path = str(root)
    p.flags &= ~(lt.torrent_flags.paused | lt.torrent_flags.auto_managed)
    handle = session.add_torrent(p)
    wait_until(lambda: handle.status().is_seeding)
    return session, handle, port


def engine_config(root, socks_port):
    c = Config()
    c.storage.state = root / "state"
    c.storage.downloads = root / "downloads"
    c.direct.port = free_port()
    c.direct.upnp = False
    c.proxy.enabled = True
    c.proxy.host = "127.0.0.1"
    c.proxy.port = socks_port
    c.proxy.timeout = 0.5
    c.seeding.save_interval = 1
    return c


def set_health(engine, tcp=True, udp=False):
    engine.health_future = Future()
    engine.health_future.set_result(
        {
            "configured": True,
            "tcp": tcp,
            "udp": udp,
            "checked_at": time.time(),
            "message": "Test TCP actif" if tcp else "Proxy indisponible",
            "audit": "not_verified",
            "bootstrap": [],
        }
    )
    engine.update_health()
    engine.next_health = float("inf")


def test_simultaneous_transfer_seeding_resume_and_proxy_failure(tmp_path):
    with (
        SocksServer(mappings={"tracker.test": "127.0.0.1"}) as proxy,
        Tracker() as tracker,
    ):
        source_a, body_a = make_torrent(
            tmp_path / "seed-a",
            "direct.bin",
            f"http://127.0.0.1:{tracker.port}/announce",
            seed=17,
        )
        source_b, body_b = make_torrent(
            tmp_path / "seed-b",
            "proxy.bin",
            f"http://tracker.test:{tracker.port}/announce",
            seed=39,
        )
        seed_a, ha, port_a = seeder(tmp_path / "seed-a", source_a)
        seed_b, hb, port_b = seeder(tmp_path / "seed-b", source_b)
        config = engine_config(tmp_path, proxy.port)
        direct = Engine(config, "direct")
        direct.session.apply_settings({"enable_dht": False})
        proxied = Engine(config, "proxy")
        try:
            # Validate actual CONNECT before promoting proxy readiness.
            with connect(config.proxy, "tracker.test", tracker.port) as (sock, _):
                sock.sendall(b"HEAD /announce HTTP/1.0\r\n\r\n")
                assert sock.recv(200).startswith(b"HTTP/")
            set_health(proxied)
            # Multiple loopback fixtures share an IP; real peers normally do not.
            proxied.session.apply_settings({"allow_multiple_connections_per_ip": True})
            a = direct.add({"source": source_a})
            b = proxied.add({"source": source_b})
            direct.handles[a["id"]].connect_peer(("127.0.0.1", port_a))
            proxied.handles[b["id"]].connect_peer(("127.0.0.1", port_b))

            def finished():
                direct.tick()
                proxied.tick()
                return (
                    direct.handles[a["id"]].status().is_seeding
                    and proxied.handles[b["id"]].status().is_seeding
                )

            wait_until(finished, 30)
            for record, body, name in (
                (a, body_a, "direct.bin"),
                (b, body_b, "proxy.bin"),
            ):
                path = config.storage.downloads / record["mode"] / record["id"] / name
                assert path.read_bytes() == body
            assert (1, "127.0.0.1", port_b) in proxy.requests
            wait_until(
                lambda: (
                    proxied.tick()
                    or any(r[1] == "tracker.test" for r in proxy.requests)
                )
            )
            assert proxied.snapshot()["torrents"][0]["state"] == "Seeding"

            # A third client fetches from our red engine: seeding is actual payload.
            receiver = lt.session(
                {
                    "listen_interfaces": "127.0.0.1:0",
                    "enable_dht": False,
                    "enable_lsd": False,
                    "enable_upnp": False,
                    "enable_natpmp": False,
                },
                flags=0,
            )
            p, _, _ = parse_source(source_b, "direct")
            p.save_path = str(tmp_path / "receiver")
            p.flags &= ~(lt.torrent_flags.paused | lt.torrent_flags.auto_managed)
            recv_handle = receiver.add_torrent(p)
            wait_until(lambda: receiver.listen_port() > 0)
            proxied.handles[b["id"]].connect_peer(("127.0.0.1", receiver.listen_port()))
            try:
                wait_until(
                    lambda: proxied.tick() or recv_handle.status().is_seeding, 10
                )
            except AssertionError:
                print("PROXY REQUESTS", proxy.requests)
                print("ENGINE", proxied.snapshot())
                print(
                    "RECEIVER",
                    recv_handle.status().state,
                    recv_handle.status().errc.message(),
                )
                print(
                    "PEERS",
                    [
                        (p.ip, p.flags, p.up_speed, p.down_speed)
                        for p in proxied.handles[b["id"]].get_peer_info()
                    ],
                )
                print("RECEIVER ALERTS", [str(a) for a in receiver.pop_alerts()])
                raise
            assert (tmp_path / "receiver" / "proxy.bin").read_bytes() == body_b
            wait_until(lambda: proxied.handles[b["id"]].status().all_time_upload > 0)
            receiver.pause()
            del recv_handle
            del receiver

            direct.action(a["id"], "pause")
            proxied.action(b["id"], "pause")
            set_health(proxied, tcp=False)
            assert proxied.snapshot()["proxy"]["tcp"] is False
            assert direct.session.get_settings()["proxy_type"] == 0
            with pytest.raises(Exception, match="indisponible"):
                proxied.add({"source": "magnet:?xt=urn:btih:" + "c" * 40})
            assert len(proxied.records) == 1
            set_health(proxied, tcp=True)
            assert proxied.records[b["id"]]["paused"] is True
            assert proxied.handles[b["id"]].status().paused
            proxied.close()
            direct.close()
            assert (config.storage.state / "proxy" / f"{b['id']}.resume").exists()
            # Proxy unavailable at restart: zero red session, records retained.
            proxied = Engine(config, "proxy")
            assert proxied.session is None
            assert proxied.records[b["id"]]["mode"] == "proxy"
            set_health(proxied)
            assert proxied.handles[b["id"]].status().paused
            proxied.action(b["id"], "resume")
            wait_until(
                lambda: proxied.tick() or proxied.handles[b["id"]].status().is_seeding
            )
            assert proxied.session.get_settings()["proxy_type"] == 2
            proxied.action(b["id"], "remove")
            assert (
                config.storage.downloads / "proxy" / b["id"] / "proxy.bin"
            ).read_bytes() == body_b
        finally:
            proxied.close()
            direct.close()
            seed_a.pause()
            seed_b.pause()


def test_magnet_metadata_through_proxy(tmp_path):
    with SocksServer() as proxy:
        source, body = make_torrent(tmp_path / "seed", seed=57, private=False)
        seed, handle, port = seeder(tmp_path / "seed", source)
        magnet = lt.make_magnet_uri(lt.torrent_info(lt.bdecode(source)))
        config = engine_config(tmp_path, proxy.port)
        engine = Engine(config, "proxy")
        try:
            set_health(engine)
            record = engine.add({"source": magnet})
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
            assert any(
                host == "127.0.0.1" and dest == port for _, host, dest in proxy.requests
            )
        finally:
            engine.close()
            seed.pause()
