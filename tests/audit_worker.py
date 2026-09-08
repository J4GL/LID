"""A standalone Engine process for syscall/packet audits; not a server API."""

import argparse
import json
from pathlib import Path
import time

from app.config import Config
from app.engine import Engine
from app.socks import check_proxy, connect
from tests.test_integration import set_health


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("job")
    args = parser.parse_args()
    job = json.loads(Path(args.job).read_text())
    config = Config.model_validate(job["config"])
    engine = Engine(config, job["mode"])
    record = None
    downloaded = 0
    phases = []
    try:
        if job["mode"] == "proxy":
            if job.get("real_proxy"):
                health = check_proxy(config.proxy)
                print(json.dumps({"health": health}), flush=True)
                engine.proxy = health
                if not health["tcp"]:
                    raise RuntimeError("Proxy réel inaccessible")
                engine.create_session()
                engine.next_health = float("inf")
            else:
                # Health validation uses the controlled HTTP tracker fixture.
                with connect(config.proxy, "tracker.test", job["tracker_port"]) as (
                    sock,
                    _,
                ):
                    sock.sendall(b"HEAD /announce HTTP/1.0\r\n\r\n")
                    assert sock.recv(128).startswith(b"HTTP/")
                set_health(engine, udp=job.get("udp", False))
                if job.get("udp"):
                    engine.session.apply_settings({"enable_outgoing_tcp": False})
                    engine.proxy["bootstrap"] = [("127.0.0.1", job["dht_port"])]
        else:
            engine.session.apply_settings({"enable_dht": False})
        record = engine.add({"source": Path(job["torrent"]).read_bytes()})
        handle = engine.handles[record["id"]]
        if job.get("peer_port"):
            handle.connect_peer(("127.0.0.1", job["peer_port"]))
        phases.append("startup")
        started = time.monotonic()
        end = started + job.get("seconds", 15)
        failed = False
        while time.monotonic() < end:
            engine.tick()
            status = handle.status()
            downloaded = max(downloaded, status.total_done)
            if (
                status.is_seeding
                and not failed
                and not job.get("real_proxy")
                and time.monotonic() - started >= 3
            ):
                phases.append("completed")
                # The parent kills the proxy relay on observing this signal.
                print(
                    json.dumps({"event": "completed", "mode": job["mode"]}), flush=True
                )
                if job["mode"] == "proxy":
                    failed = True
                    time.sleep(1)
                    handle.force_reannounce()
                    handle.connect_peer(("127.0.0.1", job["peer_port"]))
                    engine.next_health = 0
                    phases.append("proxy_failure")
            if job.get("real_proxy") and downloaded >= 1024 * 1024:
                break
            time.sleep(0.1)
        phases.append("shutdown")
        print(
            json.dumps(
                {
                    "mode": job["mode"],
                    "downloaded": downloaded,
                    "phases": phases,
                    "proxy": engine.proxy,
                }
            ),
            flush=True,
        )
    finally:
        engine.close()


if __name__ == "__main__":
    main()
