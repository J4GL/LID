"""Regenerate the README screenshots from the real dashboard and demo data.

    .venv/bin/python docs/screenshots/capture.py

Serves the application with a fake manager (no torrent engine, no network)
and drives headless Chrome over the DevTools pipe, so it needs no extra
Python package. Set CHROME to the browser binary if it is not found.
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.config import Config  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.browser import LiveServer  # noqa: E402

OUT = Path(__file__).resolve().parent
WIDTH, HEIGHT, SCALE = 1280, 800, 2
GIB = 1 << 30
MIB = 1 << 20
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "chromium",
    "chromium-browser",
]


def torrent(**row):
    return {
        "move_destination": None,
        "move_error": None,
        "can_retry_move": False,
        "move_state": None,
        "paused": False,
        "error": None,
        "last_upload_at": None,
        **row,
    }


class DemoManager:
    def __init__(self, config):
        now = time.time()
        self.torrents = [
            torrent(
                id="1" * 40,
                mode="direct",
                name="ubuntu-26.04-desktop-amd64.iso",
                save_path="/data/downloads",
                total=6 * GIB,
                downloaded=4 * GIB,
                uploaded=900 * MIB,
                peers=48,
                ratio=0.22,
                progress=0.664,
                state_code="downloading",
                download_rate=38 * MIB,
                upload_rate=2 * MIB,
            ),
            torrent(
                id="2" * 40,
                mode="proxy",
                name="debian-13.1.0-amd64-DVD-1.iso",
                save_path="/data/downloads",
                total=4 * GIB,
                downloaded=int(1.6 * GIB),
                uploaded=200 * MIB,
                peers=17,
                ratio=0.12,
                progress=0.402,
                state_code="downloading",
                download_rate=9 * MIB,
                upload_rate=640 << 10,
            ),
            torrent(
                id="3" * 40,
                mode="direct",
                name="Fedora-Workstation-Live-43-1.6.x86_64.iso",
                save_path="/media/iso/completed",
                total=int(2.4 * GIB),
                downloaded=int(2.4 * GIB),
                uploaded=int(5.9 * GIB),
                peers=6,
                ratio=2.46,
                progress=1,
                state_code="seeding",
                last_upload_at=now - 7 * 60,
                download_rate=0,
                upload_rate=1300 << 10,
            ),
            torrent(
                id="4" * 40,
                mode="proxy",
                name="archlinux-2026.10.01-x86_64.iso",
                save_path="/media/iso/completed",
                total=int(1.3 * GIB),
                downloaded=int(1.3 * GIB),
                uploaded=int(1.1 * GIB),
                peers=2,
                ratio=0.85,
                progress=1,
                state_code="seeding",
                last_upload_at=now - 5 * 3600,
                download_rate=0,
                upload_rate=0,
            ),
        ]

    async def start(self):
        pass

    async def close(self):
        pass

    def state(self):
        def disk(label, path, used, total):
            return {"label": label, "path": path, "used": used * GIB,
                    "total": total * GIB, "free": (total - used) * GIB}

        return {
            "torrents": self.torrents,
            "disks": [
                disk("downloads", "/data/downloads", 182, 465),
                disk("completed", "/media/iso/completed", 1410, 1862),
            ],
            "proxy": {"tcp": True, "udp": True, "checked_at": time.time()},
            "errors": [],
            "seeding": 2,
            "download_rate": 47 * MIB,
            "upload_rate": int(4.2 * MIB),
            "global_ratio": 1.18,
        }


class Chrome:
    """Minimal DevTools client over --remote-debugging-pipe (fds 3 and 4)."""

    def __init__(self, binary):
        to_chrome_r, self.to_chrome = os.pipe()
        self.from_chrome, from_chrome_w = os.pipe()
        self.profile = tempfile.mkdtemp(prefix="lid-shots-")

        # sh puts the pipe ends on fds 3 and 4, where Chrome expects them.
        self.process = subprocess.Popen(
            ["/bin/sh", "-c",
             f'exec "$0" "$@" 3<&{to_chrome_r} 4>&{from_chrome_w}',
             binary, "--headless=new", "--remote-debugging-pipe",
             "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
             f"--user-data-dir={self.profile}", "about:blank"],
            pass_fds=(to_chrome_r, from_chrome_w),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.close(to_chrome_r)
        os.close(from_chrome_w)
        self.next_id = 0
        self.buffer = b""

    def send(self, method, params=None, session=None):
        self.next_id += 1
        message = {"id": self.next_id, "method": method, "params": params or {}}
        if session:
            message["sessionId"] = session
        os.write(self.to_chrome, json.dumps(message).encode() + b"\0")
        while True:
            reply = self.receive()
            if reply.get("id") == self.next_id:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error']}")
                return reply.get("result", {})

    def receive(self):
        while b"\0" not in self.buffer:
            chunk = os.read(self.from_chrome, 1 << 16)
            if not chunk:
                raise RuntimeError("Chrome closed the DevTools pipe")
            self.buffer += chunk
        raw, self.buffer = self.buffer.split(b"\0", 1)
        return json.loads(raw)

    def close(self):
        self.process.terminate()
        self.process.wait(10)
        shutil.rmtree(self.profile, ignore_errors=True)


def capture(chrome, url, name, setup=""):
    target = chrome.send("Target.createTarget", {"url": "about:blank"})["targetId"]
    session = chrome.send(
        "Target.attachToTarget", {"targetId": target, "flatten": True}
    )["sessionId"]
    chrome.send("Emulation.setDeviceMetricsOverride", {
        "width": WIDTH, "height": HEIGHT, "deviceScaleFactor": SCALE,
        "mobile": False}, session)
    chrome.send("Emulation.setEmulatedMedia", {"features": [
        {"name": "prefers-reduced-motion", "value": "reduce"}]}, session)
    chrome.send("Page.navigate", {"url": url}, session)
    time.sleep(2)
    if setup:
        chrome.send("Runtime.evaluate", {"expression": setup}, session)
        time.sleep(0.6)
    shot = chrome.send("Page.captureScreenshot", {"format": "png"}, session)
    (OUT / name).write_bytes(base64.b64decode(shot["data"]))
    chrome.send("Target.closeTarget", {"targetId": target})
    print(f"wrote {OUT / name}")


COMPACT = 'document.getElementById("compact-toggle").click()'
DRAG = """(() => {
  const data = new DataTransfer();
  data.items.add(new File(["d4:infoe"], "ubuntu.torrent"));
  window.dispatchEvent(new DragEvent("dragenter", { dataTransfer: data }));
})()"""


def main():
    binary = os.environ.get("CHROME") or next(
        (c for c in CHROME_CANDIDATES if shutil.which(c) or Path(c).exists()), None
    )
    if not binary:
        sys.exit("Chrome not found: set CHROME=/path/to/chrome")
    with LiveServer(create_app(Config(), DemoManager)) as url:
        chrome = Chrome(binary)
        try:
            capture(chrome, url, "dashboard.png")
            capture(chrome, url, "drop-zones.png", DRAG)
            # Last: the compact choice is remembered by the browser profile.
            capture(chrome, url, "dashboard-compact.png", COMPACT)
        finally:
            chrome.close()


if __name__ == "__main__":
    main()
