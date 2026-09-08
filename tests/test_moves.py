"""Completion moves use real libtorrent, including actual cross-volume IO."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace

import libtorrent as lt
import pytest

from app.engine import Engine
from app.folders import MARKER, StorageUnavailable
from app.policy import parse_source
from tests.support import SocksServer, make_torrent, wait_until
from tests.test_integration import engine_config, seeder, set_health


def multi_torrent(root):
    root.mkdir(parents=True)
    storage = lt.file_storage()
    files = {"album/a.bin": b"a" * 80000, "album/nested/b.bin": b"b" * 120000}
    for name, body in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        storage.add_file(name, len(body))
    torrent = lt.create_torrent(storage, 16384, lt.create_torrent.v1_only)
    torrent.set_priv(False)
    lt.set_piece_hashes(torrent, str(root))
    return bytes(lt.bencode(torrent.generate())), files


@contextmanager
def transfer(tmp_path, mode="proxy", *, multi=False, magnet=False, completed=None):
    with SocksServer() as proxy:
        if multi:
            source, files = multi_torrent(tmp_path / "seed")
        else:
            source, body = make_torrent(tmp_path / "seed", private=not magnet)
            files = {"payload.bin": body}
        seed, seed_handle, port = seeder(tmp_path / "seed", source)
        config = engine_config(tmp_path, proxy.port)
        config.storage.completed = completed or tmp_path / "completed"
        config.storage.completed.mkdir(parents=True, exist_ok=True)
        engine = Engine(config, mode)
        if mode == "proxy":
            set_health(engine)
        engine.session.apply_settings(
            {"enable_dht": False, "allow_multiple_connections_per_ip": True}
        )
        offered = (
            lt.make_magnet_uri(lt.torrent_info(lt.bdecode(source)))
            if magnet
            else source
        )
        record = engine.add({"source": offered})
        engine.handles[record["id"]].connect_peer(("127.0.0.1", port))
        try:
            yield engine, record, source, files
        finally:
            engine.close()
            seed.pause()


def wait_moved(engine, record):
    wait_until(lambda: engine.tick() or record["storage"]["phase"] == "done", 25)


@pytest.mark.parametrize(
    "mode,multi,magnet",
    [("direct", False, False), ("proxy", True, False), ("proxy", True, True)],
)
def test_move_seed_and_restore_real_torrents(tmp_path, mode, multi, magnet):
    with transfer(tmp_path, mode, multi=multi, magnet=magnet) as (
        engine,
        record,
        source,
        files,
    ):
        original = Path(record["storage"]["path"])
        wait_moved(engine, record)
        destination = Path(record["storage"]["path"])
        assert destination == engine.config.storage.completed / mode / record["id"]
        assert all(
            (destination / name).read_bytes() == body for name, body in files.items()
        )
        assert all(not (original / name).exists() for name in files)
        assert engine.handles[record["id"]].status().is_seeding
        assert engine.session.get_settings()["proxy_type"] == (
            2 if mode == "proxy" else 0
        )

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
        params, _, _ = parse_source(source, "direct")
        params.save_path = str(tmp_path / "receiver")
        params.flags &= ~(lt.torrent_flags.paused | lt.torrent_flags.auto_managed)
        receiving = receiver.add_torrent(params)
        try:
            wait_until(lambda: receiver.listen_port() > 0)
            engine.handles[record["id"]].connect_peer(
                ("127.0.0.1", receiver.listen_port())
            )
            wait_until(lambda: engine.tick() or receiving.status().is_seeding, 20)
            assert all(
                (tmp_path / "receiver" / name).read_bytes() == body
                for name, body in files.items()
            )
        finally:
            receiver.pause()
        engine.action(record["id"], "pause")
        engine.close()
        engine.config.storage.downloads = tmp_path / "another-download-folder"
        restored = Engine(engine.config, mode)
        try:
            if mode == "proxy":
                set_health(restored)
            handle = restored.handles[record["id"]]
            assert Path(handle.status().save_path) == destination
            assert restored.records[record["id"]]["paused"]
            assert handle.status().paused
        finally:
            restored.close()


def test_missing_disk_and_collision_preserve_source(tmp_path):
    with transfer(tmp_path, "direct") as (engine, record, _, files):
        engine.moves.next_scan = float("inf")
        wait_until(
            lambda: engine.tick() or engine.handles[record["id"]].status().is_seeding
        )
        source = Path(record["storage"]["path"])
        marker = engine.config.storage.completed / MARKER
        identity = marker.read_text()
        marker.unlink()
        engine.moves.next_scan = 0
        engine.tick()
        assert record["storage"]["phase"] == "failed"
        assert not marker.exists()
        assert engine.handles[record["id"]].status().is_seeding
        assert all((source / name).read_bytes() == body for name, body in files.items())
        marker.write_text(identity)
        occupied = engine.config.storage.completed / "direct" / record["id"]
        occupied.mkdir(parents=True)
        (occupied / "important.txt").write_text("keep")
        engine.action(record["id"], "retry-move")
        engine.moves.next_scan = 0
        engine.tick()
        assert record["storage"]["manual_retry"]
        assert (occupied / "important.txt").read_text() == "keep"
        (occupied / "important.txt").unlink()
        engine.action(record["id"], "retry-move")
        wait_moved(engine, record)


def test_insufficient_space_and_manual_pause(tmp_path, monkeypatch):
    with transfer(tmp_path, "direct") as (engine, record, _, _):
        engine.moves.next_scan = float("inf")
        wait_until(
            lambda: engine.tick() or engine.handles[record["id"]].status().is_seeding
        )
        engine.action(record["id"], "pause")
        with monkeypatch.context() as patch:
            patch.setattr("app.moves.cross_device", lambda *args: True)
            patch.setattr(
                "app.moves.shutil.disk_usage", lambda *args: SimpleNamespace(free=0)
            )
            engine.moves.next_scan = 0
            engine.tick()
            assert "Espace insuffisant" in record["storage"]["error"]
            assert record["storage"]["journal"] is None
        engine.action(record["id"], "retry-move")
        wait_moved(engine, record)
        assert record["paused"] and engine.handles[record["id"]].status().paused


def test_existing_completed_torrent_is_not_migrated(tmp_path):
    with transfer(tmp_path, "direct") as (engine, record, _, _):
        engine.config.storage.completed = None
        wait_until(
            lambda: engine.tick() or engine.handles[record["id"]].status().is_seeding
        )
        engine.moves.scan_completions()
        original = record["storage"]["path"]
        engine.close()
        manifest = json.loads(engine.manifest.read_text())
        manifest[record["id"]].pop("storage")
        engine.manifest.write_text(json.dumps(manifest))
        engine.config.storage.completed = tmp_path / "completed"
        restored = Engine(engine.config, "direct")
        try:
            wait_until(
                lambda: (
                    restored.tick()
                    or restored.handles[record["id"]].status().is_seeding
                )
            )
            restored.moves.scan_completions()
            assert restored.records[record["id"]]["storage"]["completion_seen"] is True
            assert restored.records[record["id"]]["storage"]["phase"] == "idle"
            assert restored.records[record["id"]]["storage"]["path"] == original
        finally:
            restored.close()


def test_actual_cross_filesystem_move(tmp_path):
    other = os.environ.get("P2P_CROSS_DEVICE_ROOT") or (
        "/dev/shm" if Path("/dev/shm").is_dir() else None
    )
    if not other:
        pytest.skip("Provide P2P_CROSS_DEVICE_ROOT on a different filesystem")
    Path(other).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="p2p-move-", dir=other) as folder:
        target = Path(folder)
        if target.stat().st_dev == tmp_path.stat().st_dev:
            pytest.skip("The configured destination is on the same filesystem")
        with transfer(tmp_path, "proxy", multi=True, completed=target) as (
            engine,
            record,
            _,
            files,
        ):
            wait_moved(engine, record)
            destination = Path(record["storage"]["path"])
            assert all(
                (destination / name).read_bytes() == body
                for name, body in files.items()
            )


@pytest.mark.parametrize("layout", ["source", "destination", "split", "corrupt"])
def test_interrupted_move_recovery_never_downloads_missing_data(tmp_path, layout):
    with transfer(tmp_path, "direct", multi=True) as (engine, record, _, files):
        engine.moves.next_scan = float("inf")
        wait_until(
            lambda: engine.tick() or engine.handles[record["id"]].status().is_seeding
        )
        state = record["storage"]
        source = Path(state["path"])
        target = engine.config.storage.completed / "direct" / record["id"]
        engine.close()
        manifest = json.loads(engine.manifest.read_text())
        saved = manifest[record["id"]]["storage"]
        saved.update(
            completion_seen=True,
            phase="moving",
            target=str(target),
            target_root=str(engine.config.storage.completed),
            target_id=engine.moves.registry.roots()[
                str(engine.config.storage.completed)
            ],
            journal={
                "source_root": saved["root"],
                "source_id": saved["root_id"],
                "target_root": str(engine.config.storage.completed),
                "target_id": engine.moves.registry.roots()[
                    str(engine.config.storage.completed)
                ],
                "files": [
                    {"path": name, "size": len(body)} for name, body in files.items()
                ],
            },
        )
        engine.manifest.write_text(json.dumps(manifest))
        if layout in ("destination", "corrupt"):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
        elif layout == "split":
            first = next(iter(files))
            (target / first).parent.mkdir(parents=True)
            shutil.move(str(source / first), str(target / first))
        if layout == "corrupt":
            first = next(iter(files))
            (target / first).write_bytes(b"X" * len(files[first]))
        restored = Engine(engine.config, "direct")
        try:
            entry = restored.records[record["id"]]
            if layout == "split":
                assert not restored.handles
                assert entry["storage"]["phase"] == "recovery"
                assert "répartis" in entry["storage"]["error"]
            elif layout == "corrupt":
                try:
                    wait_until(
                        lambda: (
                            restored.tick() or entry["storage"]["phase"] == "recovery"
                        ),
                        8,
                    )
                except AssertionError:
                    print("RECOVERY", entry["storage"], restored.snapshot())
                    raise
                handle = restored.handles[record["id"]]
                assert handle.status().paused
                assert handle.status().download_payload_rate == 0
                assert (target / next(iter(files))).read_bytes().startswith(b"X")
            else:
                wait_moved(restored, entry)
                assert all(
                    (target / name).read_bytes() == body for name, body in files.items()
                )
                assert restored.handles[record["id"]].status().is_seeding
        finally:
            restored.close()


def test_moves_are_serialized_and_active_destination_is_frozen(tmp_path):
    with transfer(tmp_path, "proxy") as (engine, record, source, files):
        engine.moves.next_scan = float("inf")
        wait_until(
            lambda: engine.tick() or engine.handles[record["id"]].status().is_seeding
        )
        other = Engine(engine.config.model_copy(deep=True), "direct")
        try:
            folder = other.config.storage.downloads / "direct" / record["id"]
            folder.mkdir(parents=True)
            for name, body in files.items():
                (folder / name).write_bytes(body)
            other_record = other.add({"source": source})
            other.moves.next_scan = float("inf")
            wait_until(lambda: other.handles[record["id"]].status().is_seeding)
            engine.moves.scan_completions()
            other.moves.scan_completions()
            engine.moves.begin(record)
            assert engine.moves.active == record["id"]
            frozen = record["storage"]["target"]
            other.moves.begin(other_record)
            assert other.moves.active is None
            assert other_record["storage"]["phase"] == "pending"
            another = tmp_path / "another-finished"
            another.mkdir()
            engine.moves.registry.register(another)
            payload = {
                "downloads": str(engine.config.storage.downloads),
                "completed": str(another),
                "revision": 1,
            }
            engine.moves.prepare_settings(payload)
            engine.moves.apply_settings(payload)
            engine.moves.next_scan = 0
            wait_moved(engine, record)
            assert record["storage"]["path"] == frozen
            other.moves.next_scan = 0
            wait_moved(other, other_record)
            assert other_record["storage"]["phase"] == "done"
        finally:
            other.close()
