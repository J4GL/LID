"""Linux audit: trace only the proxy worker while a direct worker runs too.

Run inside tests/Dockerfile. Captures only this disposable container's traffic.
The report is empirical evidence for these scenarios, not a universal guarantee.
"""

import argparse
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import libtorrent as lt

from tests.support import SocksServer, Tracker, make_torrent
from tests.test_integration import engine_config, seeder
from tests.test_udp_webseed import UDPTracker


def trace_destinations(path):
    destinations = set()
    for line in path.read_text().splitlines():
        # Only outgoing destination sockaddrs, not getsockname or received peers.
        if not re.search(r"\b(connect|sendto|sendmsg|sendmmsg)\(", line):
            continue
        port = re.search(r"sin6?_port=htons\((\d+)\)", line)
        addr = re.search(r'inet_addr\("([^"]+)"\)', line)
        if not addr:
            addr = re.search(r'inet_pton\(AF_INET6, "([^"]+)"', line)
        if addr and port:
            destinations.add((addr[1], int(port[1])))
    return sorted(destinations)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/audit")
    parser.add_argument("--udp", action="store_true")
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    capture = subprocess.Popen(
        ["tcpdump", "-U", "-i", "any", "-w", str(out / "traffic.pcap")],
        stdout=subprocess.DEVNULL,
        stderr=(out / "capture.log").open("w"),
    )
    try:
        with (
            SocksServer(
                mappings={"tracker.test": "127.0.0.1", "udp-tracker.test": "127.0.0.1"}
            ) as proxy,
            Tracker() as tracker,
        ):
            udp_tracker = UDPTracker()
            dht = UDPTracker()
            source_a, body_a = make_torrent(
                out / "seed-direct",
                "direct.bin",
                f"http://127.0.0.1:{tracker.port}/announce",
                seed=13,
            )
            red_tracker = (
                f"udp://udp-tracker.test:{udp_tracker.port}/announce"
                if args.udp
                else f"http://tracker.test:{tracker.port}/announce"
            )
            source_b, body_b = make_torrent(
                out / "seed-proxy", "proxy.bin", red_tracker, seed=31
            )
            if args.udp:
                raw = lt.bdecode(source_b)
                raw[b"nodes"] = [[b"dht-source.test", dht.port]]
                source_b = bytes(lt.bencode(raw))
            sa, ha, pa = seeder(out / "seed-direct", source_a)
            sb, hb, pb = seeder(out / "seed-proxy", source_b)
            udp_tracker.peer_port = pb
            processes = []
            for mode, source, peer in [
                ("direct", source_a, pa),
                ("proxy", source_b, pb),
            ]:
                torrent = out / f"{mode}.torrent"
                torrent.write_bytes(source)
                cfg = engine_config(out / mode, proxy.port)
                job = {
                    "config": cfg.model_dump(mode="json"),
                    "mode": mode,
                    "torrent": str(torrent),
                    "tracker_port": tracker.port,
                    "peer_port": peer,
                    "seconds": 8,
                    "udp": args.udp,
                    "dht_port": dht.port,
                }
                job_path = out / f"{mode}.json"
                job_path.write_text(json.dumps(job))
                command = [sys.executable, "-m", "tests.audit_worker", str(job_path)]
                if mode == "proxy":
                    command = [
                        "strace",
                        "-f",
                        "-s",
                        "512",
                        "-e",
                        "trace=network",
                        "-o",
                        str(out / "proxy.strace"),
                        *command,
                    ]
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=(out / f"{mode}.stderr").open("w"),
                    text=True,
                )
                processes.append((mode, process))
            proxy_process = processes[1][1]
            lines = []
            for line in proxy_process.stdout:
                lines.append(line)
                if '"event": "completed"' in line:
                    proxy.close()
            proxy_process.wait(timeout=20)
            direct_output = processes[0][1].communicate(timeout=20)[0]
            (out / "proxy.stdout").write_text("".join(lines))
            (out / "direct.stdout").write_text(direct_output)
            destinations = trace_destinations(out / "proxy.strace")
            allowed = {("127.0.0.1", proxy.port), *proxy.relays}
            unexpected = [ep for ep in destinations if ep not in allowed]
            completed = any('"event": "completed"' in line for line in lines)
            direct_completed = '"event": "completed"' in direct_output
            report = {
                "scenario": f"simultaneous_direct_and_proxy_{'UDP' if args.udp else 'TCP'}_with_proxy_cutoff",
                "proxy_port": proxy.port,
                "proxy_destinations": destinations,
                "allowed_proxy_endpoints": sorted(allowed),
                "udp_tracker_observed": any(
                    r[1] == "udp-tracker.test" for r in proxy.requests
                ),
                "dht_observed": any(
                    r[0] == 3 and r[2] == dht.port for r in proxy.requests
                ),
                "unexpected_destinations": unexpected,
                "proxy_download_completed": completed,
                "direct_download_completed": direct_completed,
                "proxy_exit_code": proxy_process.returncode,
                "passed": completed
                and direct_completed
                and not unexpected
                and proxy_process.returncode == 0,
                "scope": "Linux container, controlled fixtures, proxy worker and all its threads traced from startup to exit.",
            }
            (out / "report.json").write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2), flush=True)
            sa.pause()
            sb.pause()
            udp_tracker.close()
            dht.close()
    finally:
        capture.terminate()
        capture.wait(timeout=5)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
