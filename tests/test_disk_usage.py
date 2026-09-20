"""Storage disk usage exposed in the dashboard state.

Specs: SPEC/storage/disk-usage.md (DISK-001, DISK-002).
"""

import os
import shutil
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import Config
from app.main import create_app
from app.manager import Manager


def make_config(tmp_path, completed=True):
    config = Config()
    config.storage.state = tmp_path / "state"
    config.storage.downloads = tmp_path / "downloads"
    config.storage.completed = tmp_path / "completed" if completed else None
    if completed:
        (tmp_path / "completed").mkdir(parents=True, exist_ok=True)
    config.proxy.enabled = False
    return config


def test_disk_001_state_exposes_storage_disk_usage(tmp_path):
    manager = Manager(make_config(tmp_path, completed=False))
    (entry,) = manager.state()["disks"]
    assert entry["label"] == "downloads"
    assert entry["path"] == str(tmp_path / "downloads")
    assert entry["total"] > 0
    assert entry["total"] == entry["used"] + entry["free"]
    assert entry["used"] >= 0 and entry["free"] >= 0


def test_disk_002_disks_deduped_and_setup_empty(tmp_path, monkeypatch):
    # No completed folder: downloads only.
    manager = Manager(make_config(tmp_path, completed=False))
    assert [d["label"] for d in manager.state()["disks"]] == ["downloads"]

    # Both roots on the same device: a single entry.
    manager = Manager(make_config(tmp_path, completed=True))
    assert len(manager.state()["disks"]) == 1

    # Distinct devices: one entry per root.
    def fake_stat(path):
        return SimpleNamespace(st_dev=1 if str(path).endswith("downloads") else 2)

    def fake_usage(path):
        total = 1000 if str(path).endswith("downloads") else 2000
        return SimpleNamespace(total=total, used=100, free=total - 100)

    with monkeypatch.context() as patched:
        patched.setattr(os, "stat", fake_stat)
        patched.setattr(shutil, "disk_usage", fake_usage)
        disks = manager.state()["disks"]
    assert [(d["label"], d["total"]) for d in disks] == [
        ("downloads", 1000),
        ("completed", 2000),
    ]

    # An unreadable root is omitted without failing the state.
    broken = make_config(tmp_path, completed=False)
    broken.storage.completed = tmp_path / "missing-disk"
    manager = Manager(broken)
    assert [d["label"] for d in manager.state()["disks"]] == ["downloads"]

    # Setup mode has no manager: empty disk list.
    with TestClient(create_app(Config(), setup_only=True)) as client:
        assert client.get("/api/torrents").json()["disks"] == []
