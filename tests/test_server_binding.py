from fastapi.testclient import TestClient

from app.config import Config
from app.main import create_app


def test_lid_server_001_defaults_to_lan_and_accepts_same_origin_requests():
    config = Config()
    origin = "http://192.168.1.29:8000"
    headers = {"Host": "192.168.1.29:8000"}

    with TestClient(create_app(config, setup_only=True), base_url=origin) as client:
        bootstrap = client.get("/api/bootstrap", headers=headers)
        assert bootstrap.status_code == 200
        token = bootstrap.json()["token"]

        settings = client.get(
            "/api/settings",
            headers={**headers, "X-P2P-Token": token},
        )
        assert settings.status_code == 200
        assert settings.json()["values"]["server"]["host"] == "0.0.0.0"

        ready = client.get(
            "/api/ready",
            headers={**headers, "Origin": origin},
        )
        assert ready.status_code == 200
        assert ready.headers["Access-Control-Allow-Origin"] == origin
