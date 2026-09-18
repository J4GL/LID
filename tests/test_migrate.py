"""The one-off relocation of a nested completed library into a flat final folder."""

import fcntl
import json
import os
from pathlib import Path

import pytest

from app import migrate
from app.folders import MARKER, RootRegistry
from app.storage import write_json
from tests.test_moves import multi_torrent


def torrent(root, name, seed):
    """A real multi-file torrent, so the migration can read back its file list."""
    source, files = multi_torrent(root / name, name, seed)
    return source, files


def place(folder, files):
    for name, body in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(body)


def record(key, mode, root, path, *, phase, **overrides):
    base = {
        "id": key,
        "hashes": [key],
        "mode": mode,
        "name": f"torrent-{key[:6]}",
        "kind": "file",
        "paused": False,
        "added_at": 1_700_000_000.0,
        "error": None,
        "dht_nodes": [],
        "trackers": [],
        "last_upload_at": None,
        "finished_at": None,
        "storage": {
            "path": str(path),
            "root": str(root),
            "root_id": None,
            "layout": "nested",
            "folder": None,
            "completion_seen": True,
            "phase": phase,
            "target": None,
            "target_root": None,
            "target_id": None,
            "target_layout": None,
            "error": None,
            "retry_at": 0,
            "manual_retry": False,
            "journal": None,
        },
    }
    base["storage"].update(overrides)
    return base


@pytest.fixture
def library(tmp_path):
    """One library shaped like the server's: nested, mixed, with Finder debris."""
    tmp_path = tmp_path.resolve()
    state = tmp_path / "state"
    downloads = tmp_path / "downloads"
    final = tmp_path / "final"
    for folder in (state, downloads, final, tmp_path / "seed"):
        folder.mkdir(parents=True)
    registry = RootRegistry(state)
    identities = {
        str(downloads): registry.register(downloads),
        str(final): registry.register(final),
    }

    indexes = {"direct": {}, "proxy": {}}
    payloads = {}
    plan = [
        ("direct", "free", 1, "done", final),
        ("proxy", "same", 2, "done", final),
        ("proxy", "other", 3, "done", final),
        ("proxy", "staging", 4, "idle", downloads),
    ]
    for index, (mode, label, seed, phase, root) in enumerate(plan):
        key = f"{index + 10:x}" * 40
        source, files = torrent(tmp_path / "seed", label, seed)
        (state / mode).mkdir(parents=True, exist_ok=True)
        (state / mode / f"{key}.source").write_bytes(source)
        nested = root / mode / key
        nested.mkdir(parents=True)
        place(nested, files)
        indexes[mode][key] = record(
            key,
            mode,
            root,
            nested,
            phase=phase,
            root_id=identities[str(root)],
        )
        payloads[label] = (key, mode, files, nested)

    # `same`: the very same bytes are already sitting in the flat final folder.
    place(final, payloads["same"][2])
    # `other`: a stranger holds that name with different bytes.
    (final / "other").mkdir()
    (final / "other" / "a.bin").write_bytes(b"z" * 4096)
    # Finder debris in one shell, something real in another.
    (final / "direct" / payloads["free"][0] / ".DS_Store").write_bytes(b"junk")
    (final / "direct" / payloads["free"][0] / "._.DS_Store").write_bytes(b"j")
    (final / "proxy" / payloads["other"][0] / "keepme.txt").write_text("mine")

    for mode, records in indexes.items():
        write_json(state / mode / "index.json", records)
    return {
        "root": tmp_path,
        "state": state,
        "downloads": downloads,
        "final": final,
        "payloads": payloads,
        "config": tmp_path / "config.yaml",
    }


def write_config(library):
    library["config"].write_text(
        "server:\n  host: 127.0.0.1\n  port: 8000\n"
        f"storage:\n  downloads: {library['downloads']}\n"
        f"  completed: {library['final']}\n  state: {library['state']}\n"
    )
    return str(library["config"])


def snapshot(root):
    return {
        str(item.relative_to(root)): item.stat().st_size
        for item in sorted(root.rglob("*"))
        if item.is_file() and item.name != "app.lock"
    }


def test_storage_migrate_001_the_dry_run_reports_everything_and_writes_nothing(
    library, capsys
):
    config = write_config(library)
    before = snapshot(library["root"])
    assert migrate.main(["--config", config]) == 0
    report = capsys.readouterr().out
    free, same, other, staging = (
        library["payloads"][k][0] for k in ("free", "same", "other", "staging")
    )

    assert "free" in report and str(library["final"] / "free") in report
    assert "same" in report and "adopt" in report.lower()
    assert "other (2)" in report
    assert ".DS_Store" in report and "keepme.txt" in report
    assert staging not in report
    assert snapshot(library["root"]) == before

    lock = (library["state"] / "app.lock").open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert migrate.main(["--config", config]) == 1
        assert "LID" in capsys.readouterr().err
        assert snapshot(library["root"]) == before
    finally:
        lock.close()

    records = json.loads((library["state"] / "direct" / "index.json").read_text())
    records[free]["storage"]["phase"] = "moving"
    records[free]["storage"]["journal"] = {"files": []}
    write_json(library["state"] / "direct" / "index.json", records)
    mid_move = snapshot(library["root"])
    assert migrate.main(["--config", config]) == 1
    assert free in capsys.readouterr().err
    assert snapshot(library["root"]) == mid_move


def test_storage_migrate_002_apply_relocates_verifies_and_resumes(library, capsys):
    config = write_config(library)
    final = library["final"]
    free, same, other, staging = (
        library["payloads"][k] for k in ("free", "same", "other", "staging")
    )
    stamps = {name: (free[3] / name).stat().st_mtime_ns for name in free[2]}
    kept = snapshot(final / "other")

    assert migrate.main(["--config", config, "--apply"]) == 0
    capsys.readouterr()

    assert all((final / name).read_bytes() == body for name, body in free[2].items())
    assert {name: (final / name).stat().st_mtime_ns for name in free[2]} == stamps
    assert all(
        (final / name.replace("other/", "other (2)/", 1)).read_bytes() == body
        for name, body in other[2].items()
    )
    assert snapshot(final / "other") == kept
    assert all((final / name).read_bytes() == body for name, body in same[2].items())

    direct = json.loads((library["state"] / "direct" / "index.json").read_text())
    proxy = json.loads((library["state"] / "proxy" / "index.json").read_text())
    for key, records in ((free[0], direct), (same[0], proxy), (other[0], proxy)):
        assert records[key]["storage"]["layout"] == "flat"
        assert records[key]["storage"]["path"] == str(final)
    assert proxy[other[0]]["storage"]["folder"] == "other (2)"
    assert proxy[staging[0]]["storage"]["layout"] == "nested"
    assert proxy[staging[0]]["storage"]["path"] == str(staging[3])

    # Nothing left holding `direct`; `proxy` still holds what must not be deleted.
    assert not (final / "direct").exists()
    assert (final / "proxy" / other[0] / "keepme.txt").read_text() == "mine"
    assert (final / "proxy" / same[0] / "same" / "a.bin").is_file()
    assert (final / MARKER).is_file()
    for mode in ("direct", "proxy"):
        backup = library["state"] / mode / "index.before-flat.json"
        assert backup.exists()
    assert json.loads((library["state"] / migrate.JOURNAL).read_text()) == {}

    assert migrate.main(["--config", config, "--apply"]) == 0
    assert "Rien" in capsys.readouterr().out


def test_storage_migrate_002_an_interrupted_apply_is_finished_by_the_next_run(
    library, capsys, monkeypatch
):
    config = write_config(library)
    final = library["final"]
    free = library["payloads"]["free"]
    real = migrate.write_json
    calls = []

    def once(path, payload):
        # Break between the rename and the index write — the one window where
        # the disk and the index disagree.
        if Path(path).name == "index.json" and not calls:
            calls.append(path)
            raise OSError("disque plein")
        return real(path, payload)

    with monkeypatch.context() as patch:
        patch.setattr(migrate, "write_json", once)
        assert migrate.main(["--config", config, "--apply"]) == 1
    capsys.readouterr()
    assert json.loads((library["state"] / migrate.JOURNAL).read_text())

    assert migrate.main(["--config", config, "--apply"]) == 0
    records = json.loads((library["state"] / "direct" / "index.json").read_text())
    assert records[free[0]]["storage"]["layout"] == "flat"
    assert all((final / name).read_bytes() == body for name, body in free[2].items())
    assert json.loads((library["state"] / migrate.JOURNAL).read_text()) == {}
