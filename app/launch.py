import argparse
import errno
import fcntl
import os
from pathlib import Path
import socket
import sys
import tempfile

from .config import load_config
from .settings import SettingsService


def check_port(host, port, kind):
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, kind) as sock:
        if kind == socket.SOCK_STREAM:
            # Match Uvicorn/libtorrent: closed connections in TIME_WAIT must
            # not prevent a restart. Active listeners still fail the bind.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if family == socket.AF_INET6:
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        try:
            sock.bind((host, port))
        except OSError as exc:
            protocol = "TCP" if kind == socket.SOCK_STREAM else "UDP"
            if exc.errno in (errno.EACCES, errno.EPERM):
                raise ValueError(
                    f"Permission réseau refusée pour {host}:{port}/{protocol}. Vérification du port impossible."
                ) from exc
            raise ValueError(
                f"Port {port}/{protocol} indisponible sur {host}. Libérez ce port ou modifiez config.yaml."
            ) from exc


def check_storage(config):
    for folder in (config.storage.state, config.storage.downloads):
        if folder == config.storage.downloads:
            from .folders import RootRegistry

            registry = RootRegistry(config.storage.state)
            if str(folder) in registry.roots():
                registry.check(folder)
        folder.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryFile(dir=folder) as out:
                out.write(b"p2p-check")
                out.flush()
        except OSError as exc:
            raise ValueError(f"Dossier non accessible en écriture : {folder}") from exc


def main():
    parser = argparse.ArgumentParser(
        description="LID — Linux ISO Downloader, téléchargements directs et SOCKS5"
    )
    parser.add_argument(
        "--config", default=str(Path(__file__).resolve().parent.parent / "config.yaml")
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Vérifier les dépendances, dossiers et ports sans démarrer",
    )
    args = parser.parse_args()
    lock = None
    try:
        import libtorrent as lt

        if not lt.__version__.startswith("2.1.1."):
            raise ValueError(
                "Version libtorrent non validée : installer libtorrent==2.1.1."
            )
        if args.check:
            config = load_config(args.config)
            check_storage(config)
            check_port(config.server.host, config.server.port, socket.SOCK_STREAM)
            for host in ("0.0.0.0", "::"):
                if host == "::" and not socket.has_ipv6:
                    continue
                for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
                    check_port(host, config.direct.port, kind)
            print(
                f"✓ Configuration, dépendances et ports vérifiés · libtorrent {lt.__version__}",
                flush=True,
            )
            return
        from .main import create_app
        import uvicorn

        while True:
            service = SettingsService.load(args.config)
            # Resume a supervised restart interrupted before the new process
            # could start. State migration targets carry an identity marker,
            # so only LID's own private target can be rebuilt.
            if service.pending.exists() and service.restart_journal.exists():
                service.commit_staged()
                service = SettingsService.load(args.config)
            config = service.config
            setup_only = service.setup_required
            if setup_only:
                bind_host, bind_port = "127.0.0.1", 8000
                check_port(bind_host, bind_port, socket.SOCK_STREAM)
            else:
                bind_host, bind_port = config.server.host, config.server.port
                check_storage(config)
                lock = (config.storage.state / "app.lock").open("a+")
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ValueError(
                        "Une instance LID utilise déjà ce dossier de données."
                    )
                check_port(config.server.host, config.server.port, socket.SOCK_STREAM)
                for host in ("0.0.0.0", "::"):
                    if host == "::" and not socket.has_ipv6:
                        continue
                    for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
                        check_port(host, config.direct.port, kind)
            print(
                f"✓ Configuration et dépendances vérifiées · libtorrent {lt.__version__}",
                flush=True,
            )
            host = (
                f"[{bind_host}]"
                if ":" in bind_host
                else bind_host
            )
            label = "configuration initiale" if setup_only else "transferts actifs"
            print(
                f"LID → http://{host}:{bind_port} · {label}", flush=True
            )
            requested = False
            server = None

            def request_restart():
                nonlocal requested
                requested = True
                if server:
                    server.should_exit = True

            uvicorn_config = uvicorn.Config(
                create_app(
                    config,
                    settings_service=service,
                    setup_only=setup_only,
                    restart_callback=request_restart,
                    active_endpoint=(bind_host, bind_port),
                ),
                host=bind_host,
                port=bind_port,
                workers=1,
                access_log=False,
                timeout_graceful_shutdown=3,
            )
            server = uvicorn.Server(uvicorn_config)
            try:
                server.run()
            except KeyboardInterrupt:
                # Programmatic Uvicorn may re-raise SIGINT after completing its
                # lifespan when an SSE client was still connected.
                pass
            if lock:
                lock.close()
                lock = None
            if requested:
                try:
                    service.commit_staged()
                except Exception as exc:
                    service.rollback_staged()
                    print(f"ERREUR : redémarrage annulé : {exc}", file=sys.stderr)
                continue
            if service.migration_journal.exists() and not server.started:
                service.rollback_staged()
                continue
            break
    except (ValueError, OSError) as exc:
        print(f"\nERREUR : {exc}\n", file=sys.stderr)
        sys.exit(1)
    finally:
        if lock:
            lock.close()


if __name__ == "__main__":
    main()
