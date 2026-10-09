"""Real-browser helpers for dashboard e2e tests: a live uvicorn server and obscura."""

import json
import os
import shutil
import subprocess
import threading
import time

import pytest
import uvicorn

from tests.support import free_port


class LiveServer:
    def __init__(self, app):
        self.port = free_port()
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="error")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            assert time.monotonic() < deadline, "server did not start"
            time.sleep(0.05)
        return f"http://127.0.0.1:{self.port}/"

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(10)


def obscura(url, script):
    binary = os.environ.get("OBSCURA") or shutil.which("obscura")
    if not binary:
        pytest.fail("obscura is required for dashboard e2e tests (set OBSCURA)")
    result = subprocess.run(
        [
            binary,
            "--allow-private-network",
            "fetch",
            "-q",
            "--wait",
            "2",
            url,
            "-e",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])
