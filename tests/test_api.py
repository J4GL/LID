from fastapi.testclient import TestClient
from app.config import Config
from app.main import create_app
from app.manager import OperationError
from app.socks import MISSING_PROXY


class FakeManager:
    def __init__(self, config):
        self.calls = []

    async def start(self):
        pass

    async def close(self):
        pass

    def state(self):
        return {
            "torrents": [],
            "proxy": {"tcp": False, "udp": False, "message": MISSING_PROXY},
            "errors": [],
            "seeding": 0,
            "download_rate": 0,
            "upload_rate": 0,
            "total_downloaded": 0,
            "total_uploaded": 0,
            "global_ratio": 0,
        }

    async def add(self, mode, source):
        if mode == "proxy":
            raise OperationError(MISSING_PROXY)
        self.calls.append((mode, source))
        return {"id": "a" * 40, "mode": mode}


def test_api_requires_explicit_mode_and_session_token():
    with TestClient(create_app(Config(), FakeManager)) as client:
        payload = {"magnet": "magnet:?xt=urn:btih:" + "a" * 40, "mode": "direct"}
        assert client.post("/api/torrents/magnet", json=payload).status_code == 403
        token = client.get("/api/bootstrap").json()["token"]
        headers = {"X-P2P-Token": token}
        payload.pop("mode")
        assert (
            client.post(
                "/api/torrents/magnet", json=payload, headers=headers
            ).status_code
            == 422
        )
        payload["mode"] = "proxy"
        response = client.post("/api/torrents/magnet", json=payload, headers=headers)
        assert (
            response.status_code == 409 and response.json()["detail"] == MISSING_PROXY
        )
        assert not client.app.state.manager.calls


def test_red_drop_error_is_clear_and_has_no_addition():
    with TestClient(create_app(Config(), FakeManager)) as client:
        token = client.get("/api/bootstrap").json()["token"]
        response = client.post(
            "/api/torrents/files",
            data={"mode": "proxy"},
            files=[
                ("files", ("demo.torrent", b"d4:infodee", "application/x-bittorrent"))
            ],
            headers={"X-P2P-Token": token},
        )
        assert response.status_code == 409
        assert response.json()["results"][0]["error"] == MISSING_PROXY
        assert response.json()["results"][0]["error_code"] == "proxy_not_configured"
        assert not client.app.state.manager.calls


def test_host_rebinding_and_static_content():
    with TestClient(create_app(Config(), FakeManager)) as client:
        assert (
            client.get("/api/bootstrap", headers={"Host": "attacker.test"}).status_code
            == 400
        )
        response = client.get("/")
        assert response.status_code == 200
        assert "frame-ancestors" in response.headers["Content-Security-Policy"]
        assert (
            'data-drop-mode="direct"' in response.text
            and 'data-drop-mode="proxy"' in response.text
        )
        assert '<html lang="en">' in response.text
        assert 'id="language-toggle"' in response.text
        assert 'id="global-ratio"' in response.text
        ready = client.get("/api/ready").json()
        assert ready["ready"] is True and ready["instance_id"]
        cross_port = client.get(
            "/api/ready", headers={"Origin": "http://127.0.0.1:9000"}
        )
        assert cross_port.headers["Access-Control-Allow-Origin"] == (
            "http://127.0.0.1:9000"
        )
        state = client.get("/api/torrents").json()
        assert state["total_downloaded"] == 0
        assert state["total_uploaded"] == 0
        assert state["global_ratio"] == 0


def test_server_static_001_static_files_must_be_revalidated():
    with TestClient(create_app(Config(), FakeManager)) as client:
        response = client.get("/static/app.js")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"
        etag = response.headers["etag"]

        cached = client.get("/static/app.js", headers={"If-None-Match": etag})
        assert cached.status_code == 304
        assert not cached.content
