"""Seeding activity display and inactive-seed auto-removal.

Specs: SPEC/seeding/last-upload.md (SEED-LASTUP-001),
       SPEC/seeding/auto-remove.md (SEED-AUTORM-001).
"""

import time
from types import SimpleNamespace

import pytest

from app.config import Config
from app.engine import Engine, INACTIVE_TTL
from app.manager import Manager

DAY = 24 * 3600


@pytest.fixture
def config(tmp_path):
    c = Config()
    c.storage.state = tmp_path / "state"
    c.storage.downloads = tmp_path / "downloads"
    c.proxy.enabled = False
    return c


def record(key, mode="proxy", now=1_000_000.0, **overrides):
    base = {
        "id": key,
        "hashes": [key],
        "mode": mode,
        "name": f"torrent-{key[:8]}",
        "paused": False,
        "added_at": now - 10 * DAY,
        "error": None,
        "storage": {
            "path": f"/tmp/downloads/{mode}/{key}",
            "root": "/tmp/downloads",
            "root_id": None,
            "completion_seen": True,
            "phase": "idle",
            "target": None,
            "target_root": None,
            "target_id": None,
            "error": None,
            "retry_at": 0,
            "manual_retry": False,
            "journal": None,
        },
        "last_upload_at": None,
        "finished_at": now - 10 * DAY,
    }
    base.update(overrides)
    return base


def fake_status(**overrides):
    base = {
        "state": 5,
        "progress": 1.0,
        "download_payload_rate": 0,
        "upload_payload_rate": 0,
        "all_time_download": 1000,
        "all_time_upload": 500,
        "total_wanted": 1000,
        "num_peers": 1,
        "num_seeds": 0,
        "time_since_upload": -1,
        "is_seeding": True,
        "is_finished": True,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_seed_lastup_001_snapshot_exposes_last_upload_and_finished_anchors(
    config,
):
    engine = Engine(config, "proxy")
    try:
        now = 1_700_000_000.0
        key = "a" * 40
        engine.records[key] = record(
            key, now=now, last_upload_at=now - 3600, finished_at=now - 7200
        )
        rows = {row["id"]: row for row in engine.snapshot()["torrents"]}
        assert rows[key]["last_upload_at"] == now - 3600
        assert rows[key]["finished_at"] == now - 7200

        # Legacy index.json entries without the new keys normalize to None.
        old = "b" * 40
        legacy = record(old, now=now)
        del legacy["last_upload_at"]
        del legacy["finished_at"]
        engine.records[old] = legacy
        rows = {row["id"]: row for row in engine.snapshot()["torrents"]}
        assert rows[old]["last_upload_at"] is None
        assert rows[old]["finished_at"] is None
    finally:
        engine.close()


def test_seed_lastup_001_snapshot_tracks_upload_activity(config):
    engine = Engine(config, "proxy")
    try:
        now = 1_700_000_000.0
        key = "c" * 40
        engine.records[key] = record(key, now=now, last_upload_at=None)
        engine.handles[key] = SimpleNamespace(
            status=lambda: fake_status(upload_payload_rate=1024)
        )
        rows = {row["id"]: row for row in engine.snapshot()["torrents"]}
        assert rows[key]["last_upload_at"] is not None
        assert abs(rows[key]["last_upload_at"] - time.time()) < 60

        # A libtorrent-reported upload 6h ago backfills the anchor.
        key2 = "d" * 40
        engine.records[key2] = record(key2, now=now, last_upload_at=None)
        engine.handles[key2] = SimpleNamespace(
            status=lambda: fake_status(time_since_upload=6 * 3600)
        )
        rows = {row["id"]: row for row in engine.snapshot()["torrents"]}
        assert rows[key2]["last_upload_at"] == pytest.approx(
            time.time() - 6 * 3600, abs=60
        )

        # finished_at is set on first observed seeding.
        key3 = "e" * 40
        fresh = record(key3, now=now, finished_at=None)
        engine.records[key3] = fresh
        engine.handles[key3] = SimpleNamespace(status=lambda: fake_status())
        engine.snapshot()
        assert engine.records[key3]["finished_at"] is not None
    finally:
        engine.close()


def test_seed_autorm_001_sweep_removes_only_stale_finished_seeds(config, tmp_path):
    engine = Engine(config, "proxy")
    try:
        engine.proxy["tcp"] = True
        now = 1_700_000_000.0
        stale = "1" * 40
        recent = "2" * 40
        never_stale = "3" * 40
        never_recent = "4" * 40
        downloading = "5" * 40
        paused = "6" * 40
        boundary = "7" * 40
        engine.records[stale] = record(stale, now=now, last_upload_at=now - 8 * DAY)
        engine.records[recent] = record(recent, now=now, last_upload_at=now - 3600)
        engine.records[never_stale] = record(
            never_stale, now=now, last_upload_at=None, finished_at=now - 8 * DAY
        )
        engine.records[never_recent] = record(
            never_recent, now=now, last_upload_at=None, finished_at=now - 3600
        )
        engine.records[downloading] = record(
            downloading, now=now, last_upload_at=now - 30 * DAY
        )
        engine.handles[downloading] = SimpleNamespace(
            status=lambda: fake_status(
                state=3, progress=0.5, is_seeding=False, is_finished=False
            )
        )
        engine.records[paused] = record(
            paused, now=now, last_upload_at=now - 30 * DAY, paused=True
        )
        engine.records[boundary] = record(
            boundary, now=now, last_upload_at=now - INACTIVE_TTL
        )
        for key in (stale, recent, never_stale, never_recent, paused, boundary):
            engine.handles[key] = SimpleNamespace(status=lambda: fake_status())
        for key in (stale, recent, never_stale, never_recent, paused, boundary):
            (engine.folder / f"{key}.source").write_bytes(b"source")
            (engine.folder / f"{key}.resume").write_bytes(b"resume")

        removed = engine._sweep_inactive(now)

        assert set(removed) == {stale, never_stale}
        assert set(engine.records) == {
            recent,
            never_recent,
            downloading,
            paused,
            boundary,
        }
        # Payload files are kept; only manifest sidecars go away.
        for key in (stale, never_stale):
            assert not (engine.folder / f"{key}.source").exists()
            assert not (engine.folder / f"{key}.resume").exists()
    finally:
        engine.close()


def test_seed_autorm_002_sweep_refreshes_anchors_before_removing(config):
    # Direct mode: tick() refreshes the proxy health, which would block a sweep.
    engine = Engine(config, "direct")
    try:
        now = time.time()
        key = "8" * 40
        legacy = record(key, mode="direct", now=now)
        # An index written before activity tracking: no anchors at all.
        del legacy["last_upload_at"]
        del legacy["finished_at"]
        engine.records[key] = legacy
        engine.handles[key] = SimpleNamespace(
            status=lambda: fake_status(has_metadata=True),
            save_resume_data=lambda *args: None,
        )
        (engine.folder / f"{key}.source").write_bytes(b"source")
        (engine.folder / f"{key}.resume").write_bytes(b"resume")

        engine.tick()

        assert key in engine.records
        assert engine.records[key]["finished_at"] == pytest.approx(now, abs=60)

        engine.records[key]["finished_at"] = now - INACTIVE_TTL - DAY
        engine.next_sweep = 0
        engine.tick()

        assert key not in engine.records
    finally:
        engine.close()


def test_seed_autorm_001_sweep_skips_proxy_blocked_and_unallowed(config):
    engine = Engine(config, "proxy")
    try:
        now = 1_700_000_000.0
        key = "8" * 40
        engine.records[key] = record(key, now=now, last_upload_at=now - 30 * DAY)
        assert not engine.allowed()
        removed = engine._sweep_inactive(now)
        assert removed == []
        assert key in engine.records
    finally:
        engine.close()


def test_seed_autorm_001_manager_prunes_known_after_engine_removal(config):
    manager = Manager(config)
    manager.snapshots = {
        "direct": {"torrents": [{"id": "a" * 40}], "error": None},
        "proxy": {"torrents": [], "error": None, "proxy": None},
    }
    manager.known = {
        "a" * 40: {"mode": "direct", "hashes": ["a" * 40]},
        "b" * 40: {"mode": "direct", "hashes": ["b" * 40]},
        "c" * 40: {"mode": "proxy", "hashes": ["c" * 40]},
    }
    manager.reconcile_known("direct")
    assert set(manager.known) == {"a" * 40, "c" * 40}
