"""Delete a torrent together with its files, with an inline confirmation.

Specs: SPEC/storage/delete-with-files.md (DEL-001, DEL-002, DEL-003).
"""

import asyncio
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Config
from app.engine import Engine
from app.folders import StorageUnavailable
from app.main import create_app
from app.manager import Manager


@pytest.fixture
def config(tmp_path):
    config = Config()
    config.storage.state = tmp_path / "state"
    config.storage.downloads = tmp_path / "downloads"
    config.storage.completed = tmp_path / "completed"
    (tmp_path / "completed").mkdir(parents=True, exist_ok=True)
    config.proxy.enabled = False
    return config


def nested_record(engine, key, **overrides):
    record = {
        "id": key,
        "hashes": [key],
        "mode": engine.mode,
        "name": f"torrent-{key[:8]}",
        "paused": False,
        "added_at": 1_000_000.0,
        "error": None,
        "storage": engine.moves.new_record(key),
        "last_upload_at": None,
        "finished_at": None,
    }
    record["storage"].update(overrides.pop("storage", {}))
    record.update(overrides)
    return record


def flat_record(engine, key, folder, root):
    record = nested_record(engine, key)
    record["storage"].update(
        {
            "path": str(root),
            "root": str(root),
            "root_id": engine.moves.registry.roots().get(str(root)),
            "layout": "flat",
            "folder": folder,
            "completion_seen": True,
            "phase": "done",
        }
    )
    return record


class FakeFiles:
    def __init__(self, entries):
        self._entries = entries

    def num_files(self):
        return len(self._entries)

    def file_path(self, i):
        return self._entries[i][0]

    def file_size(self, i):
        return self._entries[i][1]

    def file_flags(self, i):
        return 0


def fake_handle(entries):
    info = SimpleNamespace(files=lambda: FakeFiles(entries))
    return SimpleNamespace(
        torrent_file=lambda: info, save_resume_data=lambda *args: None
    )


class FakeManager:
    """API boundary double: asserts the query flag maps to the engine action."""

    def __init__(self, config):
        self.actions = []

    async def start(self):
        pass

    async def close(self):
        pass

    def state(self):
        return {"torrents": [], "disks": []}

    async def action(self, key, action):
        self.actions.append((key, action))
        if key != "a" * 40:
            raise KeyError(key)
        if action == "remove_with_files":
            return {"removed": key, "files_deleted": True, "file_errors": []}
        return {"removed": key}


def test_del_001_remove_with_files_deletes_staging_folder(config, tmp_path):
    engine = Engine(config, "direct")
    try:
        key = "a" * 40
        engine.records[key] = nested_record(engine, key)
        folder = Path(engine.records[key]["storage"]["path"])
        (folder / "sub").mkdir(parents=True)
        (folder / "sub" / "payload.bin").write_bytes(b"data")
        (engine.folder / f"{key}.source").write_bytes(b"source")
        (engine.folder / f"{key}.resume").write_bytes(b"resume")

        result = engine.action(key, "remove_with_files")

        assert result == {"removed": key, "files_deleted": True, "file_errors": []}
        assert key not in engine.records
        assert not folder.exists()
        assert not (engine.folder / f"{key}.source").exists()
        assert not (engine.folder / f"{key}.resume").exists()

        # The manager drops the id from `known`, like a plain remove.
        manager = Manager(config)
        manager.known[key] = {"mode": "direct", "hashes": [key]}
        calls = []

        async def fake_rpc(mode, action, payload=None):
            calls.append((mode, action))
            return {"removed": key}

        async def scenario():
            manager.rpc = fake_rpc
            await manager.action(key, "remove_with_files")

        asyncio.run(scenario())
        assert calls == [("direct", "remove_with_files")]
        assert key not in manager.known

        # The API flag selects the engine action; unknown ids stay 404.
        with TestClient(create_app(Config(), FakeManager)) as client:
            token = client.get("/api/bootstrap").json()["token"]
            headers = {"X-P2P-Token": token}
            response = client.delete(
                f"/api/torrents/{key}?delete_files=true", headers=headers
            )
            assert response.status_code == 200
            assert response.json()["files_deleted"] is True
            assert client.app.state.manager.actions == [
                (key, "remove_with_files")
            ]
            plain = client.delete(f"/api/torrents/{key}", headers=headers)
            assert plain.json() == {"removed": key}
            assert client.app.state.manager.actions[-1] == (key, "remove")
            missing = client.delete(
                f"/api/torrents/{'b' * 40}?delete_files=true", headers=headers
            )
            assert missing.status_code == 404

        # Without the flag, files stay on disk (unchanged behavior).
        key2 = "c" * 40
        engine.records[key2] = nested_record(engine, key2)
        folder2 = Path(engine.records[key2]["storage"]["path"])
        folder2.mkdir(parents=True)
        survivor = folder2 / "keep.bin"
        survivor.write_bytes(b"data")
        assert engine.action(key2, "remove") == {"removed": key2}
        assert survivor.is_file()
    finally:
        engine.close()


def test_del_002_flat_deletes_only_own_entries(config, tmp_path):
    engine = Engine(config, "direct")
    try:
        detached = []
        engine.session = SimpleNamespace(
            remove_torrent=detached.append, pause=lambda: None
        )
        root = Path(config.storage.completed)
        engine.moves.registry.register(root)
        key = "d" * 40
        engine.records[key] = flat_record(engine, key, "MyShow", root)
        (root / "MyShow").mkdir()
        (root / "MyShow" / "a.bin").write_bytes(b"a")
        (root / "MyShow" / "b.bin").write_bytes(b"bb")
        (root / "MyShow.parts").write_bytes(b"parts")
        neighbor = root / "Other"
        neighbor.mkdir()
        (neighbor / "c.bin").write_bytes(b"c")
        handle = fake_handle([("MyShow/a.bin", 1), ("MyShow/b.bin", 2)])
        engine.handles[key] = handle
        (engine.folder / f"{key}.source").write_bytes(b"source")

        result = engine.action(key, "remove_with_files")

        assert detached == [handle]
        assert result["removed"] == key
        assert result["file_errors"] == []
        assert not (root / "MyShow").exists()
        assert not (root / "MyShow.parts").exists()
        assert (neighbor / "c.bin").is_file()
        assert root.is_dir()
        assert not (engine.folder / f"{key}.source").exists()

        # A symlink is neither followed nor deleted.
        key2 = "e" * 40
        engine.records[key2] = flat_record(engine, key2, "Linked", root)
        secret = tmp_path / "secret.bin"
        secret.write_bytes(b"secret")
        link = root / "Linked"
        link.symlink_to(secret)
        engine.handles[key2] = fake_handle([("Linked", 6)])

        engine.action(key2, "remove_with_files")

        assert link.is_symlink()
        assert secret.is_file()
    finally:
        engine.close()


def test_del_003_remove_with_files_guards_and_edge_cases(
    config, tmp_path, monkeypatch
):
    engine = Engine(config, "direct")
    try:
        # A move in progress blocks the deletion; the torrent stays.
        for phase in ("moving", "verifying"):
            key = f"{phase[0]}" * 40
            engine.records[key] = nested_record(
                engine, key, storage={"phase": phase}
            )
            with pytest.raises(StorageUnavailable):
                engine.action(key, "remove_with_files")
            assert key in engine.records

        # A magnet without metadata removes like a plain remove.
        key = "f" * 40
        engine.records[key] = nested_record(engine, key)
        assert not Path(engine.records[key]["storage"]["path"]).exists()
        result = engine.action(key, "remove_with_files")
        assert result == {"removed": key, "files_deleted": True, "file_errors": []}

        # A path outside the validated root: nothing is deleted, torrent kept.
        key = "1" * 40
        engine.records[key] = nested_record(engine, key)
        evil = tmp_path / "evil"
        evil.mkdir()
        sentinel = evil / "sentinel.bin"
        sentinel.write_bytes(b"sentinel")
        engine.records[key]["storage"]["path"] = str(evil)
        with pytest.raises(StorageUnavailable):
            engine.action(key, "remove_with_files")
        assert key in engine.records
        assert sentinel.is_file()

        # An undeletable file removes the torrent but reports the failure.
        key = "2" * 40
        engine.records[key] = nested_record(engine, key)
        folder = Path(engine.records[key]["storage"]["path"])
        folder.mkdir(parents=True)
        (folder / "stuck.bin").write_bytes(b"data")

        def boom(path, **kwargs):
            raise OSError("disque en lecture seule")

        monkeypatch.setattr(shutil, "rmtree", boom)
        result = engine.action(key, "remove_with_files")
        assert key not in engine.records
        assert result["files_deleted"] is False
        assert result["file_errors"] and key in result["file_errors"][0]
    finally:
        engine.close()
