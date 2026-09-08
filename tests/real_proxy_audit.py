"""Bounded real-proxy smoke test using an official Ubuntu torrent (<=45 s).

Stops after at least 1 MiB of verified pieces. Only the disposable container's
network is captured. The torrent payload is never copied to the project.
"""

import http.client
import json
from pathlib import Path
import socket
import ssl
import subprocess
import sys

from app.config import load_config
from app.socks import connect
from tests.network_audit import trace_destinations


def main():
    out = Path("/real-audit")
    out.mkdir(exist_ok=True)
    config = load_config("config.yaml")
    original_host = config.proxy.host
    # Explicitly resolve ONLY the proxy's hostname before tracing the worker.
    proxy_ip = socket.getaddrinfo(
        original_host, config.proxy.port, type=socket.SOCK_STREAM
    )[0][4][0]
    config.proxy.host = proxy_ip
    config.storage.state = out / "state"
    config.storage.downloads = out / "downloads"
    config.seeding.download_limit = 1024 * 1024
    config.seeding.connections = 50
    torrent_path = out / "ubuntu.torrent"
    target = "releases.ubuntu.com"
    torrent_url = (
        "https://releases.ubuntu.com/26.04/ubuntu-26.04.1-live-server-amd64.iso.torrent"
    )
    with connect(config.proxy, target, 443) as (sock, _):
        with ssl.create_default_context().wrap_socket(
            sock, server_hostname=target
        ) as tls:
            tls.sendall(
                b"GET /26.04/ubuntu-26.04.1-live-server-amd64.iso.torrent HTTP/1.1\r\nHost: releases.ubuntu.com\r\nConnection: close\r\n\r\n"
            )
            response = http.client.HTTPResponse(tls)
            response.begin()
            if response.status != 200:
                raise RuntimeError("Official torrent unavailable")
            torrent_path.write_bytes(response.read(1024 * 1024))
    job = {
        "config": config.model_dump(mode="json"),
        "mode": "proxy",
        "torrent": str(torrent_path),
        "real_proxy": True,
        "seconds": 45,
    }
    job_path = out / "job.json"
    job_path.write_text(json.dumps(job))
    capture = subprocess.Popen(
        ["tcpdump", "-U", "-i", "any", "-w", str(out / "traffic.pcap")],
        stdout=subprocess.DEVNULL,
        stderr=(out / "capture.log").open("w"),
    )
    try:
        result = subprocess.run(
            [
                "strace",
                "-f",
                "-s",
                "512",
                "-e",
                "trace=network",
                "-o",
                str(out / "proxy.strace"),
                sys.executable,
                "-m",
                "tests.audit_worker",
                str(job_path),
            ],
            capture_output=True,
            text=True,
            timeout=85,
        )
        (out / "worker.stdout").write_text(result.stdout)
        (out / "worker.stderr").write_text(result.stderr)
    finally:
        capture.terminate()
        capture.wait(timeout=5)
    destinations = trace_destinations(out / "proxy.strace")
    unexpected = [ep for ep in destinations if ep[0] != proxy_ip]
    events = [
        json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")
    ]
    final = next((e for e in reversed(events) if "downloaded" in e), {})
    health = next((e["health"] for e in events if "health" in e), {})
    report = {
        "proxy_host": original_host,
        "proxy_ip": proxy_ip,
        "torrent_source": torrent_url,
        "destinations": destinations,
        "unexpected_destinations": unexpected,
        "tcp": health.get("tcp", False),
        "udp": health.get("udp", False),
        "verified_downloaded_bytes": final.get("downloaded", 0),
        "worker_exit_code": result.returncode,
        "passed": not unexpected
        and final.get("downloaded", 0) >= 1024 * 1024
        and result.returncode == 0,
        "scope": "Linux container; proxy hostname resolved before trace; all worker threads traced from startup to exit; bounded download.",
    }
    (out / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
