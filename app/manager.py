import asyncio
import multiprocessing
import os
import shutil
import time
import uuid

from .engine import worker
from .policy import parse_source
from .folders import FolderSettings
from .error_codes import error_code, proxy_message_code


class OperationError(Exception):
    pass


class Manager:
    def __init__(self, config):
        self.config = config
        self.workers = {}
        self.snapshots = {}
        self.pending = {}
        self.known = {}
        self.lock = asyncio.Lock()
        self.task = None
        self.folders = FolderSettings(config)
        self.storage_pending = False

    async def start(self):
        context = multiprocessing.get_context("spawn")
        for mode in ("direct", "proxy"):
            parent, child = context.Pipe()
            process = context.Process(
                target=worker,
                args=(self.config.model_dump(mode="json"), mode, child),
                name=f"p2p-{mode}",
            )
            process.start()
            child.close()
            self.workers[mode] = (process, parent)
        self.task = asyncio.create_task(self.collect())
        deadline = time.monotonic() + 15
        while len(self.snapshots) < 2:
            if time.monotonic() > deadline:
                raise OperationError("Les moteurs n'ont pas démarré à temps.")
            await asyncio.sleep(0.05)
        for mode in self.workers:
            await self.rpc(mode, "apply_storage", self.folders.payload())

    async def collect(self):
        while True:
            for mode, (process, pipe) in self.workers.items():
                try:
                    while pipe.poll():
                        message = pipe.recv()
                        if message.get("event") == "snapshot":
                            self.snapshots[mode] = message["data"]
                            for record in message["data"]["torrents"]:
                                self.known[record["id"]] = {
                                    "mode": mode,
                                    "hashes": record["hashes"],
                                }
                            self.reconcile_known(mode)
                        elif message.get("event") == "fatal":
                            self.mark_dead(mode, message["error"])
                        elif message.get("id") in self.pending:
                            future = self.pending.pop(message["id"])
                            if not future.done():
                                if "error" in message:
                                    future.set_exception(
                                        OperationError(message["error"])
                                    )
                                else:
                                    future.set_result(message["result"])
                except (EOFError, OSError):
                    pass
                if not process.is_alive():
                    self.mark_dead(
                        mode, f"Moteur {mode} arrêté. Redémarrez l'application."
                    )
            await asyncio.sleep(0.05)

    def reconcile_known(self, mode):
        """Drop known ids of `mode` missing from its latest snapshot.

        Engines may remove torrents on their own (inactive-seed sweep);
        without this, `known` would keep stale ids pointing at gone
        torrents. Only the snapshotted mode is reconciled.
        """
        ids = {
            record["id"]
            for record in self.snapshots.get(mode, {}).get("torrents", [])
        }
        for key in [
            key
            for key, entry in self.known.items()
            if entry.get("mode") == mode and key not in ids
        ]:
            self.known.pop(key, None)

    def mark_dead(self, mode, error):
        snapshot = self.snapshots.setdefault(
            mode, {"mode": mode, "torrents": [], "proxy": None}
        )
        snapshot["error"] = error
        for row in snapshot["torrents"]:
            row.update(
                state="Moteur arrêté",
                state_code="engine_stopped",
                download_rate=0,
                upload_rate=0,
            )
        if mode == "proxy":
            snapshot["proxy"] = {
                "configured": self.config.proxy.configured,
                "tcp": False,
                "udp": False,
                "message": error,
                "audit": "not_verified",
                "checked_at": None,
                "message_code": "engine_unavailable",
            }

    async def rpc(self, mode, action, payload=None):
        process, pipe = self.workers[mode]
        if not process.is_alive():
            raise OperationError(f"Moteur {mode} arrêté. Redémarrez l'application.")
        key = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self.pending[key] = future
        try:
            pipe.send({"id": key, "action": action, "payload": payload or {}})
            return await asyncio.wait_for(future, timeout=30)
        except (TimeoutError, OSError) as exc:
            raise OperationError(
                "Le moteur ne répond pas. Vérifiez la liste avant de réessayer."
            ) from exc
        finally:
            self.pending.pop(key, None)

    async def add(self, mode, source):
        async with self.lock:
            if self.storage_pending:
                raise OperationError(
                    "Réglages des dossiers en attente d'application. Réenregistrez les réglages ou redémarrez."
                )
            if mode == "proxy":
                proxy = self.state()["proxy"]
                if not proxy["tcp"]:
                    raise OperationError(proxy["message"])
            try:
                _, _, hashes = parse_source(source, mode)
            except Exception as exc:
                raise OperationError(
                    str(exc)
                    if isinstance(exc, ValueError)
                    else "Torrent ou magnet invalide."
                ) from exc
            for existing in self.known.values():
                if set(hashes).intersection(existing["hashes"]):
                    label = "direct" if existing["mode"] == "direct" else "proxy"
                    raise OperationError(
                        f"Ce torrent est déjà présent en mode {label}."
                    )
            record = await self.rpc(mode, "add", {"source": source})
            self.known[record["id"]] = {"mode": mode, "hashes": hashes}
            return record

    async def storage_settings(self, downloads, completed):
        async with self.lock:
            payload = await asyncio.to_thread(
                self.folders.prepare, downloads, completed
            )
            self.storage_pending = True
            committed = False
            try:
                for mode in self.workers:
                    await self.rpc(mode, "prepare_storage", payload)
                await asyncio.to_thread(self.folders.commit, payload)
                committed = True
                for mode in self.workers:
                    result = await self.rpc(mode, "apply_storage", payload)
                    if result.get("revision") != payload["revision"]:
                        raise OperationError("Un moteur n'a pas appliqué les dossiers.")
                self.storage_pending = False
                return payload
            except Exception:
                if not committed:
                    await asyncio.gather(
                        *(self.rpc(mode, "abort_storage") for mode in self.workers),
                        return_exceptions=True,
                    )
                    self.storage_pending = False
                raise

    async def runtime_settings(self, candidate, settings_service):
        async with self.lock:
            storage = await asyncio.to_thread(
                self.folders.prepare,
                candidate.storage.downloads,
                candidate.storage.completed,
            )
            payload = {
                "storage": storage,
                "seeding": candidate.seeding.model_dump(mode="json"),
            }
            self.storage_pending = True
            committed = False
            old_downloads = self.config.storage.downloads
            old_completed = self.config.storage.completed
            try:
                for mode in self.workers:
                    await self.rpc(mode, "prepare_runtime_settings", payload)
                self.folders.commit(storage, write_yaml=False)
                await asyncio.to_thread(settings_service.commit, candidate)
                committed = True
                for mode in self.workers:
                    result = await self.rpc(mode, "apply_runtime_settings", payload)
                    if result.get("revision") != storage["revision"]:
                        raise OperationError("Un moteur n'a pas appliqué les réglages.")
                self.storage_pending = False
                return {**storage, "applied": True, "restart": False}
            except Exception:
                if not committed:
                    self.config.storage.downloads = old_downloads
                    self.config.storage.completed = old_completed
                    await asyncio.gather(
                        *(self.rpc(mode, "abort_storage") for mode in self.workers),
                        return_exceptions=True,
                    )
                    self.storage_pending = False
                raise

    async def action(self, key, action):
        async with self.lock:
            if key not in self.known:
                raise KeyError(key)
            result = await self.rpc(self.known[key]["mode"], action, {"id": key})
            if action in ("remove", "remove_with_files"):
                self.known.pop(key, None)
            return result

    def storage_disks(self):
        """One disk-usage entry per storage root device.

        Downloads and completed folders on the same device collapse into a
        single entry; an unreadable root is omitted without failing the state.
        """
        disks = []
        seen = set()
        for label in ("downloads", "completed"):
            root = getattr(self.config.storage, label, None)
            if not root:
                continue
            try:
                device = os.stat(root).st_dev
            except OSError:
                continue
            if device in seen:
                continue
            seen.add(device)
            try:
                usage = shutil.disk_usage(root)
            except OSError:
                continue
            disks.append(
                {
                    "label": label,
                    "path": str(root),
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                }
            )
        return disks

    def state(self):
        rows = [
            row for snapshot in self.snapshots.values() for row in snapshot["torrents"]
        ]
        proxy = self.snapshots.get("proxy", {}).get("proxy") or {
            "configured": self.config.proxy.configured,
            "tcp": False,
            "udp": False,
            "checked_at": None,
            "message": "Vérification du proxy…",
            "audit": "not_verified",
        }
        proxy.setdefault("message_code", proxy_message_code(proxy))
        total_downloaded = sum(r["downloaded"] for r in rows)
        total_uploaded = sum(r["uploaded"] for r in rows)
        errors = [s["error"] for s in self.snapshots.values() if s.get("error")]
        return {
            "torrents": sorted(rows, key=lambda row: row["added_at"], reverse=True),
            "proxy": proxy,
            "errors": errors,
            "error_details": [
                {"message": message, "code": error_code(message)} for message in errors
            ],
            "download_rate": sum(r["download_rate"] for r in rows),
            "upload_rate": sum(r["upload_rate"] for r in rows),
            "total_downloaded": total_downloaded,
            "total_uploaded": total_uploaded,
            "global_ratio": total_uploaded / total_downloaded
            if total_downloaded
            else 0,
            "seeding": sum(r.get("state_code") == "seeding" for r in rows),
            "storage": {**self.folders.payload(), "pending": self.storage_pending},
            "disks": self.storage_disks(),
        }

    async def close(self):
        for process, pipe in self.workers.values():
            if process.is_alive():
                try:
                    pipe.send({"action": "shutdown"})
                except OSError:
                    pass
        # Collector continues draining pipes while children flush resume data.
        await asyncio.gather(
            *(asyncio.to_thread(p.join, 15) for p, _ in self.workers.values())
        )
        for process, pipe in self.workers.values():
            if process.is_alive():
                process.terminate()
                await asyncio.to_thread(process.join, 3)
            pipe.close()
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
