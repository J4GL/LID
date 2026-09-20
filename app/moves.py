"""Completion moves stay in the torrent's original libtorrent session.

The flock is shared by both engine processes. The per-torrent journal is
persisted before libtorrent starts moving files, including across filesystems.
"""

import fcntl
import itertools
import os
from pathlib import Path
import shutil
import time

import libtorrent as lt

from .folders import MARKER, RootRegistry, StorageUnavailable, directory, separate
from .policy import destination_for
from .storage import atomic_write

MISSING_PAYLOAD = (
    "Fichiers introuvables à l'emplacement enregistré : reprise bloquée, "
    "aucun téléchargement automatique."
)


def cross_device(source, target):
    return source.stat().st_dev != target.stat().st_dev


def rename_entry(files, folder):
    """Put a recorded top-level name back on a torrent's file list.

    A rename is applied by the session, not by the metadata we hold, so the name
    the index owns has to be put back by hand. Doing it twice changes nothing,
    which keeps this safe wherever the paths come from.
    """
    if not folder:
        return files
    return [
        {"path": str(Path(folder, *Path(f["path"]).parts[1:])), "size": f["size"]}
        for f in files
    ]


class CompletionMoves:
    def __init__(self, engine):
        self.engine = engine
        self.registry = RootRegistry(engine.config.storage.state)
        self.revision = 0
        self.prepared = None
        self.lock = None
        self.active = None
        self.next_scan = 0
        if any("storage" not in record for record in engine.records.values()):
            backup = engine.folder / "index.before-storage.json"
            if not backup.exists():
                atomic_write(backup, engine.manifest.read_bytes())
        # An index written before the final folder was flattened records no shape
        # at all, and everything it points at is nested.
        if any(
            "layout" not in record.get("storage", {})
            for record in engine.records.values()
            if "storage" in record
        ):
            backup = engine.folder / "index.before-flat.json"
            if not backup.exists():
                atomic_write(backup, engine.manifest.read_bytes())
        for name in ("downloads", "completed"):
            root = getattr(engine.config.storage, name)
            if root:
                try:
                    self.registry.register(root, initial_downloads=name == "downloads")
                except (OSError, ValueError):
                    pass
        for record in engine.records.values():
            if "storage" not in record:
                record["storage"] = self.new_record(record["id"], legacy=True)
            state = record["storage"]
            state.setdefault("layout", "nested")
            state.setdefault("target_layout", None)
            state.setdefault("folder", None)
            if state.get("journal"):
                state["journal"].setdefault("source_layout", "nested")
                state["journal"].setdefault("target_layout", "nested")
                state["journal"].setdefault("target_claimed", False)
        if engine.records:
            engine.persist()

    def new_record(self, key, legacy=False):
        root = str(self.engine.config.storage.downloads)
        return {
            "path": str(Path(root) / self.engine.mode / key),
            "root": root,
            "root_id": self.registry.roots().get(root),
            # A torrent is always born in the staging folder, one folder per
            # infohash; only the final folder is flat.
            "layout": "nested",
            "folder": None,
            "completion_seen": None if legacy else False,
            "phase": "idle",
            "target": None,
            "target_root": None,
            "target_id": None,
            "target_layout": None,
            "error": None,
            "retry_at": 0,
            "manual_retry": False,
            "journal": None,
        }

    def valid_path(self, record, root=None, identity=None, layout=None):
        state = record["storage"]
        root = root or state["root"]
        identity = identity or state["root_id"]
        layout = layout or state["layout"]
        path = destination_for(
            self.registry.check(root, identity), self.engine.mode, record["id"], layout
        )
        if root == state["root"] and str(path) != state["path"]:
            raise StorageUnavailable(
                "Chemin de reprise incohérent : restauration bloquée."
            )
        return path

    def prepare_settings(self, payload):
        separate(
            payload["downloads"], payload["completed"], self.engine.config.storage.state
        )
        for name in ("downloads", "completed"):
            if payload[name]:
                self.registry.check(payload[name])
        self.prepared = dict(payload)
        return {"revision": payload["revision"], "prepared": True}

    def apply_settings(self, payload):
        if payload["revision"] < self.revision:
            raise StorageUnavailable("Révision de dossiers périmée.")
        # Classify current completions using the old settings before enabling
        # moves. Already-complete downloads never migrate retroactively.
        self.scan_completions()
        self.engine.config.storage.downloads = Path(payload["downloads"])
        self.engine.config.storage.completed = (
            Path(payload["completed"]) if payload["completed"] else None
        )
        self.revision = payload["revision"]
        self.prepared = None
        for record in self.engine.records.values():
            state = record["storage"]
            if state["phase"] in ("pending", "failed") and not state["journal"]:
                state.update(
                    retry_at=0, manual_retry=False, error=None, phase="pending"
                )
        self.engine.persist()
        return {"revision": self.revision}

    @staticmethod
    def complete_files(path, files):
        try:
            return bool(files) and all(
                (path / f["path"]).is_file()
                and (path / f["path"]).stat().st_size == f["size"]
                for f in files
            )
        except OSError:
            return False

    @staticmethod
    def file_list(info, folder=None):
        files = info.files()
        listed = [
            {"path": files.file_path(i), "size": files.file_size(i)}
            for i in range(files.num_files())
            if not files.file_flags(i) & lt.file_storage.flag_pad_file
        ]
        return rename_entry(listed, folder)

    @staticmethod
    def entries_of(files):
        """The torrent's own top-level names — what it claims in a shared folder."""
        return sorted({Path(f["path"]).parts[0] for f in files})

    @staticmethod
    def reserved(name):
        return name == MARKER or name.startswith(".lid-") or name.endswith(".parts")

    def require_payload(self, record, params, destination):
        """A torrent that once completed must find its files before it may run.

        Every path used to carry an infohash, so a wrong one was barely reachable.
        A shared final folder makes it reachable — a migration cut short, a stale
        recorded shape — and libtorrent answers an empty save path by checking to
        zero and downloading the whole library again.
        """
        state = record["storage"]
        if (
            not params.ti
            or not state["completion_seen"]
            or state["phase"] in ("verifying", "recovery")
        ):
            return
        if self.complete_files(destination, self.file_list(params.ti, state["folder"])):
            if state["manual_retry"] and state["error"] == MISSING_PAYLOAD:
                state.update(error=None, manual_retry=False)
            return
        state.update(error=MISSING_PAYLOAD, manual_retry=True, retry_at=0)
        self.engine.persist()
        raise StorageUnavailable(MISSING_PAYLOAD)

    @staticmethod
    def discard_stale(path, files, *, prune_root=True, errors=None):
        # Only the interrupted move's own files, and only the directories they
        # leave empty: rmdir refuses anything that still holds other data.
        # With `errors`, each skipped or failed entry is reported instead of
        # silently ignored; already-gone files are never an error.
        root = Path(path)
        base = root.resolve()
        parents = set()
        for entry in files:
            item = root / entry["path"]
            if not item.resolve().is_relative_to(base):
                if errors is not None:
                    errors.append(str(item))
                continue
            try:
                item.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                if errors is not None:
                    errors.append(str(item))
            for parent in item.parents:
                if parent == root:
                    break
                parents.add(parent)
        for folder in sorted(parents, key=lambda p: len(p.parts), reverse=True):
            try:
                folder.rmdir()
            except OSError:
                pass
        # A flat root belongs to the whole library, never to one torrent.
        if not prune_root:
            return
        try:
            root.rmdir()
        except OSError:
            pass

    def prepare_restore(self, record, params):
        state = record["storage"]
        journal = state["journal"]
        if journal:
            # Never trust resume.save_path after a crash during move_storage.
            source = self.valid_path(
                record,
                journal["source_root"],
                journal["source_id"],
                journal["source_layout"],
            )
            target = self.valid_path(
                record,
                journal["target_root"],
                journal["target_id"],
                journal["target_layout"],
            )
            # A move copies before it unlinks, so an interruption normally leaves
            # a complete copy on one side and a partial one on the other. The
            # partial side holds no unique data, so it is dropped once the kept
            # side passes its hash check.
            if self.complete_files(target, journal["files"]):
                state.update(
                    path=str(target),
                    root=journal["target_root"],
                    root_id=journal["target_id"],
                    layout=journal["target_layout"],
                    recovery_destination=True,
                    stale_copy=str(source),
                    stale_layout=journal["source_layout"],
                )
            elif self.complete_files(source, journal["files"]):
                state.update(
                    path=str(source),
                    root=journal["source_root"],
                    root_id=journal["source_id"],
                    layout=journal["source_layout"],
                    recovery_destination=False,
                    stale_copy=str(target),
                    stale_layout=journal["target_layout"],
                )
            else:
                state.update(
                    phase="recovery",
                    error="Déplacement interrompu : fichiers répartis ou ambigus. Récupérez les fichiers dans un seul emplacement puis réessayez.",
                    manual_retry=True,
                )
                self.engine.persist()
                raise StorageUnavailable(state["error"])
            state.update(phase="verifying", error=None)
            params.flags |= lt.torrent_flags.upload_mode
            params.flags &= ~lt.torrent_flags.seed_mode
            self.engine.persist()
        return self.valid_path(record)

    def after_attach(self, record, handle):
        state = record["storage"]
        if state["phase"] == "verifying":
            # Fresh add_torrent_params triggers a full check, with no cached
            # pieces and no earlier fast-resume checked alert to confuse it.
            handle.set_upload_mode(True)

    def scan_completions(self):
        changed = False
        for key, handle in list(self.engine.handles.items()):
            record = self.engine.records[key]
            state = record["storage"]
            status = handle.status()
            if state["phase"] in ("moving", "verifying", "recovery"):
                continue
            if not status.has_metadata or int(status.state) not in (3, 4, 5):
                continue
            if state["completion_seen"] is None:
                state["completion_seen"] = bool(status.is_seeding)
                changed = True
            elif not state["completion_seen"] and status.is_seeding:
                state["completion_seen"] = True
                if self.engine.config.storage.completed:
                    state.update(phase="pending", retry_at=0)
                changed = True
        if changed:
            self.engine.persist()

    def target_for(self, record):
        root = self.engine.config.storage.completed
        state = record["storage"]
        if not root:
            state.update(phase="idle", target=None, error=None)
            return None
        # The final folder is browsed by people: no mode, no infohash, the
        # torrent's own entry sits at its root. Normalise it the way valid_path
        # does, so the two never disagree over a trailing slash.
        root = directory(root)
        state.update(
            target=str(root),
            target_root=str(root),
            target_id=self.registry.roots().get(str(root)),
            target_layout="flat",
        )
        if state["target"] == state["path"] and state["layout"] == "flat":
            state.update(phase="done", error=None)
            return None
        return self.valid_path(record, state["target_root"], state["target_id"], "flat")

    def acquire(self):
        lock = (self.engine.config.storage.state / "storage-move.lock").open("a+")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            return False
        self.lock = lock
        return True

    def release(self):
        if self.lock:
            self.lock.close()
        self.lock, self.active = None, None

    def occupancy(self, target, files):
        """What this torrent's own names already hold in the shared final folder.

        Three answers: nothing there, the very same data, or someone else's.
        """
        entries = self.entries_of(files)
        present = [name for name in entries if os.path.lexists(target / name)]
        for name in present:
            if (target / name).is_symlink():
                raise StorageUnavailable(
                    f"« {name} » est un lien symbolique dans le dossier final : "
                    "rien ne sera écrit à travers."
                )
        if not present:
            return "free"
        if len(present) == len(entries) and self.same_content(target, files, entries):
            return "same"
        return "other"

    @staticmethod
    def same_content(root, files, entries):
        # Same names, same sizes, same count and nothing extra: the same data.
        found = {}
        for name in entries:
            item = root / name
            if item.is_file():
                found[name] = item.stat().st_size
                continue
            for child in item.rglob("*"):
                if child.is_symlink():
                    return False
                if child.is_file():
                    found[str(child.relative_to(root))] = child.stat().st_size
        return found == {f["path"]: f["size"] for f in files}

    def free_name(self, target, files, source):
        """The first `Nom (2)`, `Nom (3)`… nobody is using, extension kept last."""
        current = self.entries_of(files)[0]
        stem, suffix = current, ""
        if len(files) == 1 and Path(files[0]["path"]).parent == Path("."):
            stem, suffix = os.path.splitext(current)
        for number in itertools.count(2):
            candidate = f"{stem} ({number}){suffix}"
            if (
                not self.reserved(candidate)
                and not os.path.lexists(target / candidate)
                and not os.path.lexists(source / candidate)
            ):
                return current, candidate

    def rename_aside(self, record, source, target, files):
        """Take a free name rather than touch what is already in the final folder."""
        current, candidate = self.free_name(target, files, source)
        record["storage"]["folder"] = candidate
        # Recorded before the disk moves: a crash here leaves the payload check
        # in Engine.attach to refuse the torrent instead of re-downloading it.
        self.engine.persist()
        os.rename(source / current, source / candidate)
        self.reattach(record)
        record["storage"].update(phase="pending", retry_at=0, error=None)
        self.engine.persist()

    def reattach(self, record):
        """Re-add the torrent so libtorrent reads the new layout from scratch."""
        key = record["id"]
        if key in self.engine.handles:
            handle = self.engine.handles.pop(key)
            self.engine.session.remove_torrent(handle)
        self.engine.restore(record)

    def begin(self, record):
        key = record["id"]
        state = record["storage"]
        if not self.acquire():
            return
        try:
            handle = self.engine.handles.get(key)
            if not handle or not handle.status().is_seeding:
                self.release()
                return
            source = self.valid_path(record)
            target = self.target_for(record)
            if target is None:
                self.release()
                self.engine.persist()
                return
            directory(state["target_root"], writable=True)
            files = self.file_list(handle.torrent_file(), state["folder"])
            occupied = self.occupancy(target, files)
            if occupied == "other":
                self.rename_aside(record, source, target, files)
                self.release()
                return
            if occupied == "free" and cross_device(source, Path(state["target_root"])):
                if shutil.disk_usage(state["target_root"]).free < sum(
                    f["size"] for f in files
                ):
                    raise StorageUnavailable(
                        "Espace insuffisant sur le disque de destination. Les fichiers restent dans le dossier actuel."
                    )
            state.update(
                phase="moving",
                error=None,
                journal={
                    "source_root": state["root"],
                    "source_id": state["root_id"],
                    "source_layout": state["layout"],
                    "target_root": state["target_root"],
                    "target_id": state["target_id"],
                    "target_layout": state["target_layout"],
                    # Whether this move is what put the files there, and so the
                    # only thing allowed to take them away again.
                    "target_claimed": occupied == "free",
                    "files": files,
                },
            )
            self.engine.persist()
            if occupied == "same":
                # The same data is already in place: adopt it rather than copy it
                # over itself. The interrupted-move recovery does exactly this —
                # hash-check the destination, then drop the staging copy.
                self.release()
                self.reattach(record)
                return
            self.active = key
            handle.move_storage(str(target), lt.move_flags_t.fail_if_exist)
        except (ValueError, OSError, RuntimeError) as exc:
            state.update(phase="failed", error=str(exc), retry_at=time.time() + 30)
            self.release()
            self.engine.persist()

    def alert(self, alert, key):
        if key not in self.engine.records:
            return False
        record = self.engine.records[key]
        state = record["storage"]
        if isinstance(alert, lt.storage_moved_alert):
            if state["phase"] != "moving":
                return False
            state.update(
                path=state["target"],
                root=state["target_root"],
                root_id=state["target_id"],
                layout=state["target_layout"],
                phase="done",
                journal=None,
                error=None,
                manual_retry=False,
            )
            self.engine.persist()
            # An older save may still be in flight. Queue a fresh save after it.
            self.engine.handles[key].save_resume_data(
                lt.save_resume_flags_t.save_info_dict
                | lt.save_resume_flags_t.flush_disk_cache
            )
            self.engine.pending_save.add(key)
            self.release()
            return True
        if isinstance(alert, lt.storage_moved_failed_alert):
            # File existence errors occur before libtorrent modifies the source.
            # Other failures may have partially moved data; inspect on retry.
            state.update(
                phase="recovery",
                error="Déplacement échoué : vérifier le disque et les fichiers avant de réessayer.",
                manual_retry=True,
            )
            self.engine.handles[key].pause()
            self.engine.persist()
            self.release()
            return True
        if (
            isinstance(alert, lt.torrent_checked_alert)
            and state["phase"] == "verifying"
        ):
            handle = self.engine.handles[key]
            if handle.status().is_seeding:
                stale = state.pop("stale_copy", None)
                flat = state.pop("stale_layout", "nested") == "flat"
                journal = state["journal"]
                # A nested side is the torrent's own folder and goes whole. A flat
                # side is shared, so only a copy this move wrote may be removed.
                if stale and journal and (not flat or journal["target_claimed"]):
                    self.discard_stale(stale, journal["files"], prune_root=not flat)
                state.update(
                    phase="done"
                    if state.pop("recovery_destination", False)
                    else "pending",
                    journal=None,
                    error=None,
                    manual_retry=False,
                    retry_at=0,
                )
                handle.set_upload_mode(False)
                if not record["paused"] and self.engine.allowed():
                    handle.resume()
                else:
                    handle.pause()
                self.engine.request_saves()
            else:
                handle.pause()
                state.update(
                    phase="recovery",
                    error="Pièces manquantes ou corrompues après déplacement : reprise bloquée, aucun téléchargement automatique.",
                    manual_retry=True,
                )
            self.engine.persist()
            return True
        return False

    def retry(self, record):
        state = record["storage"]
        if (
            state["phase"] not in ("pending", "failed", "recovery")
            and not state["error"]
        ):
            raise StorageUnavailable("Aucun déplacement à réessayer pour ce torrent.")
        if state["phase"] == "moving":
            raise StorageUnavailable("Déplacement en cours. Attendez sa fin.")
        if state["journal"] or record["id"] not in self.engine.handles:
            if not self.engine.session:
                raise StorageUnavailable(
                    "Moteur indisponible : attendez la validation du proxy."
                )
            # Rechecking an ambiguous disk layout requires a fresh paused handle;
            # the network policy is reapplied by Engine.restore.
            self.reattach(record)
            state["error"] = None
        else:
            state.update(phase="pending", error=None, manual_retry=False, retry_at=0)
        self.engine.persist()
        return {"retrying": record["id"]}

    def tick(self):
        now = time.time()
        if now < self.next_scan:
            return
        self.next_scan = now + 1
        self.scan_completions()
        for record in list(self.engine.records.values()):
            state = record["storage"]
            if (
                record["id"] not in self.engine.handles
                and self.engine.session
                and not state["manual_retry"]
                and now >= state["retry_at"]
            ):
                try:
                    self.engine.restore(record)
                    state["error"] = None
                except (OSError, ValueError, RuntimeError) as exc:
                    state.update(error=str(exc), retry_at=now + 30)
            if (
                not self.active
                and not self.prepared
                and record["id"] in self.engine.handles
                and state["phase"] in ("pending", "failed")
                and not state["manual_retry"]
                and now >= state["retry_at"]
            ):
                self.begin(record)

    def close(self):
        # Engine.close processes disk alerts before releasing this lock. If a
        # worker must be terminated, its OS lock is released on process exit.
        if not self.active:
            self.release()
