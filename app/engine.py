"""One process and one libtorrent session per routing mode."""

import concurrent.futures
import json
import os
import signal
import time

import libtorrent as lt

from .config import Config
from .policy import (
    settings,
    parse_source,
    sanitize_params,
    validate_info,
    destination_for,
    tracker_allowed,
    normalize_nodes,
)
from .socks import MISSING_PROXY, check_proxy, ProxyError, resolve_remote
from .storage import atomic_write, write_json
from .folders import StorageUnavailable
from .moves import CompletionMoves
from .error_codes import error_code, proxy_message_code


class Engine:
    def __init__(self, config, mode):
        self.config, self.mode = config, mode
        self.folder = config.storage.state / mode
        self.folder.mkdir(parents=True, exist_ok=True)
        self.manifest = self.folder / "index.json"
        self.records = (
            json.loads(self.manifest.read_text()) if self.manifest.exists() else {}
        )
        for key, record in self.records.items():
            if (
                key != record["id"]
                or record["mode"] != mode
                or not all(c in "0123456789abcdef" for c in key)
                or len(key) not in (40, 64)
            ):
                raise ValueError(
                    "Index de reprise invalide : mode ou infohash incohérent."
                )
        self.handles = {}
        self.session = None
        self.pending_save = set()
        self.proxy = {
            "configured": config.proxy.configured,
            "tcp": False,
            "udp": False,
            "message": "Vérification du proxy…"
            if config.proxy.configured
            else MISSING_PROXY,
            "checked_at": None,
            "audit": "not_verified",
            "bootstrap": [],
        }
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.node_future = None
        self.node_key = None
        self.node_addresses = {}
        self.health_future = None
        self.next_health = 0
        self.next_bootstrap = 0
        self.last_save = time.monotonic()
        self.moves = CompletionMoves(self)
        if mode == "direct":
            self.create_session()

    def persist(self):
        write_json(self.manifest, self.records)

    def allowed(self):
        return self.mode == "direct" or self.proxy["tcp"]

    def create_session(self):
        self.session = lt.session(
            settings(self.config, self.mode, self.proxy["udp"]), flags=0
        )
        self.session.add_extension(lt.create_ut_metadata_plugin)
        self.session.add_extension(lt.create_ut_pex_plugin)
        actual = self.session.get_settings()
        if self.mode == "proxy":
            required = settings(self.config, self.mode, self.proxy["udp"])
            for key in (
                "proxy_type",
                "proxy_hostnames",
                "proxy_peer_connections",
                "proxy_tracker_connections",
                "anonymous_mode",
                "enable_lsd",
                "enable_upnp",
                "enable_natpmp",
                "enable_incoming_tcp",
            ):
                if actual[key] != required[key]:
                    self.session.pause()
                    raise RuntimeError(
                        "Paramètres proxy non appliqués : moteur bloqué."
                    )
        for record in list(self.records.values()):
            try:
                self.restore(record)
            except StorageUnavailable as exc:
                record["storage"].update(error=str(exc), retry_at=time.time() + 30)
            except Exception:
                record["error"] = (
                    "Reprise impossible : métadonnées ou chemins invalides."
                )

    def restore(self, record):
        source_path = self.folder / f"{record['id']}.source"
        source = source_path.read_bytes()
        if record["kind"] == "magnet":
            source = source.decode()
        original, _, hashes = parse_source(source, self.mode)
        if not set(hashes).intersection(record["hashes"]):
            raise ValueError("Infohash incohérent.")
        resume_path = self.folder / f"{record['id']}.resume"
        params = original
        if resume_path.exists():
            try:
                # Sanitize outer resume nodes BEFORE libtorrent parses them.
                raw = lt.bdecode(resume_path.read_bytes())
                if self.mode == "proxy":
                    nodes = (
                        record.get("dht_nodes", [])
                        + list(raw.get(b"nodes", []))
                        + list(raw.get(b"dht_nodes", []))
                    )
                    record["dht_nodes"] = normalize_nodes(nodes)
                raw.pop(b"nodes", None)
                raw.pop(b"dht_nodes", None)
                params = lt.read_resume_data(lt.bencode(raw))
                resumed = params.info_hashes
                actual = {str(resumed.v1), str(resumed.v2)}
                if not set(record["hashes"]).intersection(actual):
                    raise ValueError("Reprise d'un autre torrent.")
                if original.ti:
                    params.ti = original.ti
            except Exception:
                params = original
        if record["storage"]["journal"]:
            # A fast-resume checked alert can precede a requested force_recheck.
            # Recover with fresh params instead, so the only completed check is
            # a full hash check of the files at the journal-selected location.
            if not params.ti:
                raise StorageUnavailable(
                    "Métadonnées manquantes : impossible de vérifier le déplacement interrompu."
                )
            fresh = lt.add_torrent_params()
            fresh.ti = params.ti
            fresh.total_downloaded = params.total_downloaded
            fresh.total_uploaded = params.total_uploaded
            fresh.active_time = params.active_time
            fresh.seeding_time = params.seeding_time
            fresh.url_seeds = params.url_seeds
            fresh.http_seeds = params.http_seeds
            params = fresh
        params.trackers = record["trackers"]
        self.attach(record, params)

    def attach(self, record, params):
        destination = self.moves.prepare_restore(record, params)
        sanitize_params(params, self.mode, self.proxy["udp"], destination)
        if record["storage"]["phase"] == "verifying":
            params.flags |= lt.torrent_flags.upload_mode
        handle = self.session.add_torrent(params)
        self.handles[record["id"]] = handle
        self.moves.after_attach(record, handle)
        if self.allowed() and not record["paused"] and not record.get("error"):
            handle.resume()

    def add(self, payload):
        if not self.allowed():
            raise ProxyError(self.proxy["message"])
        source = payload["source"]
        params, source, hashes = parse_source(source, self.mode)
        key = hashes[0]
        if any(set(hashes).intersection(r["hashes"]) for r in self.records.values()):
            raise ValueError("Ce torrent est déjà présent.")
        record = {
            "id": key,
            "hashes": hashes,
            "mode": self.mode,
            "name": params.ti.name()
            if params.ti
            else (params.name or "Récupération des métadonnées…"),
            "kind": "file" if isinstance(source, bytes) else "magnet",
            "paused": False,
            "added_at": time.time(),
            "error": None,
            "storage": self.moves.new_record(key),
            "dht_nodes": normalize_nodes(params.dht_nodes)
            if self.mode == "proxy"
            else [],
            "trackers": [x for x in params.trackers if tracker_allowed(x, True)],
        }
        # Commit source + index while the handle is still paused. Crash recovery
        # can only replay the saved routing mode, never default to direct.
        destination = self.moves.valid_path(record)
        sanitize_params(params, self.mode, self.proxy["udp"], destination)
        source_path = self.folder / f"{key}.source"
        atomic_write(
            source_path, source if isinstance(source, bytes) else source.encode()
        )
        self.records[key] = record
        try:
            self.persist()
            self.attach(record, params)
        except Exception:
            self.records.pop(key, None)
            self.persist()
            source_path.unlink(missing_ok=True)
            raise
        return record

    def action(self, key, action):
        record = self.records[key]
        handle = self.handles.get(key)
        if action == "retry-move":
            return self.moves.retry(record)
        if action == "resume" and record["storage"]["phase"] == "recovery":
            raise StorageUnavailable(record["storage"]["error"])
        if action == "resume" and not self.allowed():
            raise ProxyError(self.proxy["message"])
        if action == "remove":
            if record["storage"]["phase"] in ("moving", "verifying"):
                raise StorageUnavailable(
                    "Déplacement ou vérification en cours. Attendez la fin avant de retirer le torrent."
                )
            # Remove manifest first; stale resume alerts are discarded below.
            self.records.pop(key)
            self.persist()
            if handle:
                self.session.remove_torrent(handle)  # Never delete payload files.
                self.handles.pop(key)
            self.pending_save.discard(key)
            for suffix in ("source", "resume"):
                (self.folder / f"{key}.{suffix}").unlink(missing_ok=True)
            return {"removed": key}
        record["paused"] = action == "pause"
        self.persist()
        if handle:
            handle.pause() if record["paused"] else handle.resume()
        return {"id": key, "paused": record["paused"]}

    def update_health(self):
        if self.mode != "proxy":
            return
        now = time.monotonic()
        if self.health_future is None and now >= self.next_health:
            self.health_future = self.pool.submit(check_proxy, self.config.proxy)
        if not self.health_future or not self.health_future.done():
            return
        before = self.proxy
        self.proxy = self.health_future.result()
        self.health_future = None
        self.next_health = now + self.config.proxy.check_interval
        if not self.proxy["tcp"]:
            if self.session:
                self.session.pause()
                self.session.apply_settings(
                    {
                        "enable_dht": False,
                        "enable_outgoing_utp": False,
                        "enable_incoming_utp": False,
                    }
                )
            return
        if not self.session:
            self.create_session()
        if not before["tcp"] or before["udp"] != self.proxy["udp"]:
            self.session.pause()
            self.session.apply_settings(
                settings(self.config, "proxy", self.proxy["udp"])
            )
            for key, handle in self.handles.items():
                handle.replace_trackers(
                    [
                        {"url": url, "tier": i}
                        for i, url in enumerate(self.records[key]["trackers"])
                        if tracker_allowed(url, self.proxy["udp"])
                    ]
                )
            self.session.resume()
        if self.proxy["udp"] and (not before["tcp"] or not before["udp"]):
            # The session's own UDP ASSOCIATE is asynchronous. Do not lose the
            # initial DHT pings by sending before that association is ready.
            self.next_bootstrap = time.monotonic() + 2

    def request_saves(self):
        for key, handle in self.handles.items():
            if key not in self.pending_save:
                handle.save_resume_data(
                    lt.save_resume_flags_t.save_info_dict
                    | lt.save_resume_flags_t.flush_disk_cache
                )
                self.pending_save.add(key)

    def key_for_handle(self, handle):
        return next((key for key, h in self.handles.items() if h == handle), None)

    def alerts(self):
        if not self.session:
            return
        for alert in self.session.pop_alerts():
            key = (
                self.key_for_handle(alert.handle) if hasattr(alert, "handle") else None
            )
            if self.moves.alert(alert, key):
                continue
            if isinstance(alert, lt.save_resume_data_alert):
                if key in self.records:
                    atomic_write(
                        self.folder / f"{key}.resume",
                        bytes(lt.write_resume_data_buf(alert.params)),
                    )
                self.pending_save.discard(key)
            elif isinstance(alert, lt.save_resume_data_failed_alert):
                self.pending_save.discard(key)
            elif isinstance(alert, lt.metadata_received_alert) and key:
                handle = self.handles[key]
                try:
                    info = handle.torrent_file()
                    validate_info(info)
                    self.records[key]["name"] = info.name()
                    hashes = info.info_hashes()
                    self.records[key]["hashes"] = (
                        [str(hashes.v1)] if hashes.has_v1() else []
                    ) + ([str(hashes.v2)] if hashes.has_v2() else [])
                    self.persist()
                    handle.set_upload_mode(False)
                    self.request_saves()
                except Exception:
                    handle.pause()
                    self.records[key]["error"] = (
                        "Métadonnées refusées : chemins de fichiers non autorisés."
                    )
            elif isinstance(alert, lt.torrent_error_alert) and key:
                self.records[key]["error"] = (
                    "Erreur torrent ou disque : vérifier l'espace libre et les droits du dossier."
                )
            elif isinstance(alert, lt.socks5_alert) and self.mode == "proxy":
                # No direct fallback in libtorrent; trigger a fresh health probe.
                self.next_health = 0

    def snapshot(self):
        rows = []
        for key, record in self.records.items():
            row = {
                k: v
                for k, v in record.items()
                if k not in ("trackers", "kind", "storage")
            }
            storage = record["storage"]
            row.update(
                save_path=storage["path"],
                move_destination=storage["target"],
                move_state=storage["phase"],
                move_error=storage["error"],
                can_retry_move=storage["phase"] in ("failed", "recovery", "pending")
                or bool(storage["error"]),
            )
            row.update(
                progress=0,
                download_rate=0,
                upload_rate=0,
                downloaded=0,
                uploaded=0,
                total=0,
                peers=0,
                seeds=0,
                ratio=0,
                state="En attente",
                state_code="waiting",
            )
            handle = self.handles.get(key)
            if handle:
                status = handle.status()
                names = {
                    0: ("En attente", "waiting"),
                    1: ("Vérification", "checking"),
                    2: ("Métadonnées", "metadata"),
                    3: ("Téléchargement", "downloading"),
                    4: ("Terminé", "finished"),
                    5: ("Seeding", "seeding"),
                    6: ("Allocation", "allocating"),
                    7: ("Vérification", "checking"),
                }
                state, state_code = names.get(
                    int(status.state), ("En attente", "waiting")
                )
                row.update(
                    progress=status.progress,
                    download_rate=status.download_payload_rate,
                    upload_rate=status.upload_payload_rate,
                    downloaded=status.all_time_download,
                    uploaded=status.all_time_upload,
                    total=status.total_wanted,
                    peers=status.num_peers,
                    seeds=status.num_seeds,
                    ratio=status.all_time_upload / status.all_time_download
                    if status.all_time_download
                    else 0,
                    state=state,
                    state_code=state_code,
                )
            if record.get("error"):
                row["state"] = "Erreur"
                row["state_code"] = "error"
            elif record["paused"]:
                row["state"] = "En pause"
                row["state_code"] = "paused"
            elif not self.allowed():
                row["state"] = "Proxy bloqué"
                row["state_code"] = "proxy_blocked"
            if storage["phase"] == "moving":
                row["state"] = "Déplacement en cours"
                row["state_code"] = "moving"
            elif storage["phase"] == "verifying":
                row["state"] = "Vérification après déplacement"
                row["state_code"] = "move_verifying"
            elif storage["phase"] in ("pending", "failed"):
                row["state"] = "Déplacement en attente"
                row["state_code"] = "move_pending"
            elif storage["error"]:
                row["state"] = "Stockage indisponible"
                row["state_code"] = "storage_unavailable"
            row["error_code"] = (
                error_code(record.get("error")) if record.get("error") else None
            )
            row["move_error_code"] = (
                error_code(storage.get("error")) if storage.get("error") else None
            )
            rows.append(row)
        proxy = (
            {k: v for k, v in self.proxy.items() if k != "bootstrap"}
            if self.mode == "proxy"
            else None
        )
        if proxy:
            proxy["message_code"] = proxy_message_code(proxy)
        return {
            "mode": self.mode,
            "pid": os.getpid(),
            "storage_revision": self.moves.revision,
            "torrents": rows,
            "proxy": proxy,
        }

    def tick(self):
        self.update_health()
        self.alerts()
        self.moves.tick()
        self.resolve_torrent_nodes()
        if (
            self.mode == "proxy"
            and self.session
            and self.proxy["tcp"]
            and self.proxy["udp"]
            and time.monotonic() >= self.next_bootstrap
        ):
            for address, port in self.proxy["bootstrap"]:
                self.session.add_dht_node((address, port))
            for (host, port), addresses in self.node_addresses.items():
                for address in addresses:
                    self.session.add_dht_node((address, port))
            self.next_bootstrap = time.monotonic() + 30
        if time.monotonic() - self.last_save >= self.config.seeding.save_interval:
            self.request_saves()
            self.last_save = time.monotonic()

    def resolve_torrent_nodes(self):
        if self.mode != "proxy":
            return
        if self.node_future and self.node_future.done():
            try:
                self.node_addresses[self.node_key] = self.node_future.result()
            except Exception:
                self.node_addresses[self.node_key] = []
            self.node_future = None
        if self.node_future or not self.proxy["tcp"] or not self.proxy["udp"]:
            return
        # Bound work from untrusted metadata and keep DNS away from the engine
        # event loop. Health checks have their own executor slot.
        nodes = list(
            dict.fromkeys(
                node
                for record in self.records.values()
                for node in normalize_nodes(record.get("dht_nodes", []))
            )
        )[:64]
        self.node_addresses = {
            node: addresses
            for node, addresses in self.node_addresses.items()
            if node in nodes
        }
        for node in nodes:
            if node not in self.node_addresses:
                self.node_key = node
                self.node_future = self.pool.submit(
                    resolve_remote, self.config.proxy, node[0]
                )
                break

    def close(self):
        if self.session:
            self.session.pause()
            self.request_saves()
            deadline = time.monotonic() + 8
            while self.pending_save and time.monotonic() < deadline:
                self.alerts()
                time.sleep(0.05)
        self.persist()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.handles.clear()
        self.session = None
        self.moves.release()


def worker(config_data, mode, pipe):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    engine = None
    try:
        engine = Engine(Config.model_validate(config_data), mode)
        pipe.send({"event": "snapshot", "data": engine.snapshot()})
        last_snapshot = 0
        while True:
            if pipe.poll(0.1):
                request = pipe.recv()
                if request["action"] == "shutdown":
                    break
                try:
                    if request["action"] == "add":
                        result = engine.add(request["payload"])
                    elif request["action"] == "check_proxy":
                        engine.next_health = 0
                        result = {"checking": True}
                    elif request["action"] == "prepare_storage":
                        result = engine.moves.prepare_settings(request["payload"])
                    elif request["action"] == "apply_storage":
                        result = engine.moves.apply_settings(request["payload"])
                    elif request["action"] == "abort_storage":
                        engine.moves.prepared = None
                        result = {"aborted": True}
                    elif request["action"] == "prepare_runtime_settings":
                        result = engine.moves.prepare_settings(
                            request["payload"]["storage"]
                        )
                    elif request["action"] == "apply_runtime_settings":
                        payload = request["payload"]
                        result = engine.moves.apply_settings(payload["storage"])
                        engine.config.seeding = type(engine.config.seeding).model_validate(
                            payload["seeding"]
                        )
                        if engine.session:
                            engine.session.apply_settings(
                                {
                                    "upload_rate_limit": engine.config.seeding.upload_limit,
                                    "download_rate_limit": engine.config.seeding.download_limit,
                                    "connections_limit": engine.config.seeding.connections,
                                    "file_pool_size": engine.config.seeding.file_pool_size,
                                }
                            )
                    else:
                        result = engine.action(
                            request["payload"]["id"], request["action"]
                        )
                    pipe.send({"id": request["id"], "result": result})
                    last_snapshot = 0
                except Exception as exc:
                    message = (
                        str(exc)
                        if isinstance(exc, (ValueError, ProxyError))
                        else "L'opération a échoué dans le moteur torrent."
                    )
                    pipe.send({"id": request["id"], "error": message})
            engine.tick()
            if time.monotonic() - last_snapshot >= 1:
                pipe.send({"event": "snapshot", "data": engine.snapshot()})
                last_snapshot = time.monotonic()
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        try:
            pipe.send(
                {
                    "event": "fatal",
                    "error": f"Moteur {mode} arrêté ({type(exc).__name__}).",
                }
            )
        except (BrokenPipeError, OSError):
            pass
        import traceback

        traceback.print_exc()
    finally:
        if engine:
            engine.close()
        pipe.close()
