import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.config import load_config
from app.folders import (
    FolderSettings,
    RootRegistry,
    StorageUnavailable,
    browse_directories,
    directory,
)
from app.main import create_app
from app.manager import Manager, OperationError
from tests.support import free_port, make_torrent


def configured(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        f"# keep this comment\nserver:\n  port: {free_port()}\ndirect:\n  port: {free_port()}\n  upnp: false\nproxy: null # keep this too\nstorage:\n  downloads: ./incoming # original location\n  state: ./state\n"
    )
    return load_config(path)


def test_folder_api_persists_yaml_and_both_workers(tmp_path):
    config = configured(tmp_path)
    incoming = tmp_path / "new incoming"
    completed = tmp_path / "finished"
    incoming.mkdir()
    completed.mkdir()
    with TestClient(create_app(config)) as client:
        assert client.get("/api/storage").status_code == 403
        assert client.get("/api/storage/directories").status_code == 403
        token = client.get("/api/bootstrap").json()["token"]
        headers = {"X-P2P-Token": token}
        old_source, _ = make_torrent(tmp_path / "seed-old", seed=123)
        old = client.post(
            "/api/torrents/files",
            headers=headers,
            data={"mode": "direct"},
            files={"files": ("old.torrent", old_source)},
        ).json()["results"][0]["id"]
        response = client.put(
            "/api/storage",
            headers=headers,
            json={"downloads": str(incoming), "completed": str(completed)},
        )
        assert response.status_code == 200, response.text
        assert response.json()["completed"] == str(completed)
        yaml = config._path.read_text()
        assert (
            "# keep this comment" in yaml
            and "# keep this too" in yaml
            and "# original location" in yaml
        )
        assert load_config(config._path).storage.completed == completed
        for mode in ("direct", "proxy"):
            # Confirm acknowledgment rather than waiting for the next SSE frame.
            manager = client.app.state.manager
            actual = client.portal.call(
                manager.rpc, mode, "apply_storage", manager.folders.payload()
            )
            assert actual["revision"] == response.json()["revision"]
        old_state = __import__("json").loads(
            (config.storage.state / "direct" / "index.json").read_text()
        )[old]
        assert old_state["storage"]["path"] == str(
            tmp_path / "incoming" / "direct" / old
        )
        source, _ = make_torrent(tmp_path / "seed-new", seed=124)
        new = client.post(
            "/api/torrents/files",
            headers=headers,
            data={"mode": "direct"},
            files={"files": ("new.torrent", source)},
        ).json()["results"][0]["id"]
        new_state = __import__("json").loads(
            (config.storage.state / "direct" / "index.json").read_text()
        )[new]
        assert new_state["storage"]["path"] == str(incoming / "direct" / new)
        listing = client.get(
            "/api/storage/directories", headers=headers, params={"path": str(tmp_path)}
        ).json()
        assert any(d["name"] == "finished" for d in listing["directories"])
        assert not any(d["name"] == "config.yaml" for d in listing["directories"])
        bad = client.put(
            "/api/storage",
            headers=headers,
            json={"downloads": str(incoming), "completed": str(incoming)},
        )
        assert bad.status_code == 409
        assert client.get("/api/storage", headers=headers).json()["completed"] == str(
            completed
        )


def test_folder_roots_identity_and_validation(tmp_path, monkeypatch):
    config = configured(tmp_path)
    service = FolderSettings(config)
    missing = tmp_path / "disconnected" / "complete"
    with pytest.raises(StorageUnavailable):
        service.prepare(config.storage.downloads, missing)
    assert not missing.parent.exists()
    symlink = tmp_path / "link"
    symlink.symlink_to(config.storage.downloads)
    with pytest.raises(StorageUnavailable, match="symbolique"):
        service.prepare(symlink, None)
    with monkeypatch.context() as patch:
        patch.setattr(
            "app.folders.tempfile.TemporaryFile",
            lambda **kw: (_ for _ in ()).throw(PermissionError()),
        )
        with pytest.raises(StorageUnavailable, match="écriture"):
            directory(config.storage.downloads, writable=True)
    marker = config.storage.downloads / ".p2p-storage-id"
    marker.unlink()
    with pytest.raises(StorageUnavailable, match="identité"):
        service.registry.register(config.storage.downloads, initial_downloads=True)
    assert not marker.exists()


def test_settings_prepare_failure_does_not_change_yaml(tmp_path):
    async def scenario():
        config = configured(tmp_path)
        completed = tmp_path / "completed"
        completed.mkdir()
        manager = Manager(config)
        await manager.start()
        original = config._path.read_bytes()
        actual_rpc = manager.rpc

        async def failing_rpc(mode, action, payload=None):
            if mode == "proxy" and action == "prepare_storage":
                raise OperationError("fixture unavailable")
            return await actual_rpc(mode, action, payload)

        manager.rpc = failing_rpc
        try:
            with pytest.raises(OperationError):
                await manager.storage_settings(
                    str(config.storage.downloads), str(completed)
                )
            assert config._path.read_bytes() == original
            assert not manager.storage_pending
            assert manager.folders.payload()["completed"] is None
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_settings_disk_failure_before_commit_keeps_yaml_and_runtime(
    tmp_path, monkeypatch
):
    config = configured(tmp_path)
    service = FolderSettings(config)
    final = tmp_path / "final"
    final.mkdir()
    payload = service.prepare(config.storage.downloads, final)
    before = config._path.read_bytes()
    monkeypatch.setattr(
        "app.folders.write_json",
        lambda *args: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(StorageUnavailable, match="enregistrer"):
        service.commit(payload)
    assert config._path.read_bytes() == before
    assert config.storage.completed is None
