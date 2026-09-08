import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import load_config
from app.main import create_app
from app.settings import SettingsService, SettingsValidation


def write_config(root: Path, *, password="secret"):
    path = root / "config.yaml"
    path.write_text(
        "# preserved header\n"
        "server:\n  host: 127.0.0.1\n  port: 8000\n"
        "storage:\n  downloads: ./downloads # preserved folder\n  completed: null\n  state: ./state\n"
        "direct:\n  port: 51413\n  upnp: false\n"
        "proxy:\n  enabled: true\n  host: proxy.test\n  port: 1080\n"
        f'  username: user\n  password: "{password}"\n'
        "  udp: auto\n  timeout: 5\n  check_interval: 30\n"
        "  dns_server: 1.1.1.1\n  dht_bootstrap: [router.test:6881]\n"
        "seeding:\n  upload_limit: 0\n  download_limit: 0\n"
        "  connections: 500\n  file_pool_size: 100\n  save_interval: 30\n"
    )
    return path


def complete_payload(service):
    value = service.config.model_dump(mode="json")
    value["proxy"]["password"] = ""
    return value


def test_first_launch_and_existing_install_detection(tmp_path):
    path = write_config(tmp_path)
    service = SettingsService.load(path)
    assert service.setup_required

    (tmp_path / "state" / "direct").mkdir(parents=True)
    (tmp_path / "state" / "direct" / "index.json").write_text("{}")
    service = SettingsService.load(path)
    assert not service.setup_required
    assert service.marker.exists()


def test_settings_redact_password_preserve_comments_and_blank_secret(tmp_path):
    path = write_config(tmp_path)
    (tmp_path / "downloads").mkdir()
    (tmp_path / "state").mkdir()
    service = SettingsService.load(path)
    public = service.public()
    assert "password" not in public["values"]["proxy"]
    assert public["values"]["proxy"]["password_configured"] is True

    payload = complete_payload(service)
    payload["seeding"]["connections"] = 750
    candidate = service.candidate(payload)
    assert candidate.proxy.password == "secret"
    service.validate(candidate, check_ports=False)
    service.commit(candidate)
    text = path.read_text()
    assert "# preserved header" in text
    assert "# preserved folder" in text
    assert load_config(path).seeding.connections == 750
    assert load_config(path).proxy.password == "secret"

    payload = complete_payload(service)
    payload["proxy"]["clear_password"] = True
    service.commit(service.candidate(payload))
    assert load_config(path).proxy.password == ""


def test_settings_validate_paths_and_full_bounds(tmp_path):
    path = write_config(tmp_path)
    service = SettingsService.load(path)
    payload = complete_payload(service)
    payload["storage"]["completed"] = payload["storage"]["downloads"]
    with pytest.raises(SettingsValidation) as caught:
        service.candidate(payload)
    assert "stockage" in str(caught.value).lower() or caught.value.fields

    payload = complete_payload(service)
    payload["proxy"]["dns_server"] = "not-an-ip"
    with pytest.raises(SettingsValidation) as caught:
        service.candidate(payload)
    assert "proxy.dns_server" in caught.value.fields


def test_setup_api_never_starts_manager_and_requires_token(tmp_path):
    path = write_config(tmp_path)
    service = SettingsService.load(path)

    class ForbiddenManager:
        def __init__(self, config):
            raise AssertionError("torrent manager started during setup")

    with TestClient(
        create_app(
            service.config,
            ForbiddenManager,
            settings_service=service,
            setup_only=True,
            restart_callback=lambda: None,
            active_endpoint=("127.0.0.1", 8000),
        )
    ) as client:
        bootstrap = client.get("/api/bootstrap").json()
        assert bootstrap["setup_required"] is True
        assert client.get("/api/settings").status_code == 403
        response = client.get(
            "/api/settings", headers={"X-P2P-Token": bootstrap["token"]}
        )
        assert response.status_code == 200
        assert "password" not in response.json()["values"]["proxy"]
        assert client.get("/api/torrents").json()["torrents"] == []


def test_state_migration_is_verified_and_source_removed_after_restore(tmp_path):
    path = write_config(tmp_path)
    source = tmp_path / "state"
    (tmp_path / "downloads").mkdir()
    source.mkdir()
    (source / "direct").mkdir()
    (source / "direct" / "resume.fastresume").write_bytes(b"resume data")
    service = SettingsService.load(path)
    service.complete_setup()
    payload = complete_payload(service)
    target = tmp_path / "new-state"
    target.mkdir()
    payload["storage"]["state"] = str(target)
    candidate = service.candidate(payload)
    service.validate(candidate, check_ports=False)
    service.stage_restart(candidate)
    service.commit_staged()

    assert source.exists()
    assert (target / "direct" / "resume.fastresume").read_bytes() == b"resume data"
    restarted = SettingsService.load(path)
    restarted.finalize_migration()
    assert not source.exists()
    assert not (target / ".lid-state-migration-target").exists()
    assert json.loads(restarted.marker.read_text()) == {"complete": True}
