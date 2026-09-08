from app.config import Config
from app.manager import Manager


def row(key, downloaded, uploaded, state_code):
    return {
        "id": key,
        "hashes": [key],
        "mode": "direct",
        "added_at": 1,
        "download_rate": 10,
        "upload_rate": 20,
        "downloaded": downloaded,
        "uploaded": uploaded,
        "state": "legacy text is not used for aggregation",
        "state_code": state_code,
    }


def manager_with_state(tmp_path, rows):
    config = Config()
    config.storage.downloads = tmp_path / "downloads"
    config.storage.state = tmp_path / "state"
    manager = Manager(config)
    manager.snapshots = {
        "direct": {"torrents": rows, "error": None},
        "proxy": {"torrents": [], "error": None, "proxy": None},
    }
    return manager


def test_global_ratio_aggregates_present_torrents_and_stable_state_codes(tmp_path):
    manager = manager_with_state(
        tmp_path,
        [
            row("a" * 40, 100, 50, "seeding"),
            row("b" * 40, 300, 150, "paused"),
        ],
    )

    state = manager.state()

    assert state["total_downloaded"] == 400
    assert state["total_uploaded"] == 200
    assert state["global_ratio"] == 0.5
    assert state["seeding"] == 1
    assert state["download_rate"] == 20
    assert state["upload_rate"] == 40


def test_global_ratio_is_zero_without_downloaded_bytes(tmp_path):
    manager = manager_with_state(tmp_path, [row("c" * 40, 0, 500, "downloading")])

    state = manager.state()

    assert state["total_downloaded"] == 0
    assert state["total_uploaded"] == 500
    assert state["global_ratio"] == 0
