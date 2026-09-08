import socket
import subprocess
import sys
from pathlib import Path
import pytest
import yaml
import signal
import time
import httpx
from app.launch import check_port
from tests.support import free_port


@pytest.mark.parametrize("kind", [socket.SOCK_STREAM, socket.SOCK_DGRAM])
def test_busy_port_does_not_kill_or_fallback(kind):
    with socket.socket(socket.AF_INET, kind) as listener:
        listener.bind(("127.0.0.1", 0))
        if kind == socket.SOCK_STREAM:
            listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(ValueError, match=str(port)):
            check_port("127.0.0.1", port, kind)
        assert listener.fileno() > 0


def test_launcher_config_and_ports(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "server": {"port": free_port()},
                "direct": {"port": free_port(), "upnp": False},
                "proxy": None,
            }
        )
    )
    result = subprocess.run(
        [sys.executable, "-m", "app.launch", "--config", str(config), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    config.write_text("server: [invalid")
    result = subprocess.run(
        [sys.executable, "-m", "app.launch", "--config", str(config), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_shutdown_with_open_sse_releases_lock_and_ports(tmp_path):
    config = tmp_path / "config.yaml"
    port = free_port()
    config.write_text(
        yaml.safe_dump(
            {
                "server": {"port": port},
                "direct": {"port": free_port(), "upnp": False},
                "proxy": None,
            }
        )
    )
    # Existing installations bypass the new first-run wizard and bind their
    # configured web port immediately.
    (tmp_path / "data" / "direct").mkdir(parents=True)
    (tmp_path / "data" / "direct" / "index.json").write_text("{}")
    command = [sys.executable, "-m", "app.launch", "--config", str(config)]
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=2) as client:
            deadline = time.monotonic() + 10
            while True:
                try:
                    client.get("/api/bootstrap").raise_for_status()
                    break
                except httpx.TransportError:
                    if time.monotonic() > deadline:
                        raise AssertionError("Server failed to start")
                    time.sleep(0.1)
            with client.stream("GET", "/api/events") as response:
                lines = response.iter_lines()
                assert next(lines).startswith("data: ")
                process.send_signal(signal.SIGINT)
                output, _ = process.communicate(timeout=15)
                assert process.returncode == 0, output
                assert "Application shutdown complete" in output
        checked = subprocess.run([*command, "--check"], capture_output=True, text=True)
        assert checked.returncode == 0, checked.stderr
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
