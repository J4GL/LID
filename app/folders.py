"""Validated storage roots, removable-volume identity and local folder settings."""

import fcntl
import io
import json
import os
from pathlib import Path
import tempfile
import uuid

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from .storage import atomic_write, write_json

MARKER = ".p2p-storage-id"


class StorageUnavailable(ValueError):
    pass


def directory(value, *, writable=False):
    if not value or "\x00" in str(value):
        raise StorageUnavailable("Chemin de dossier invalide.")
    path = Path(os.path.abspath(Path(value).expanduser()))
    if path.resolve() != path or any(p.is_symlink() for p in (path, *path.parents)):
        raise StorageUnavailable(
            "Les dossiers contenant un lien symbolique ne sont pas autorisés."
        )
    if not path.is_dir():
        raise StorageUnavailable(
            f"Dossier indisponible : {path}. Vérifiez que le disque est connecté."
        )
    if writable:
        try:
            with tempfile.TemporaryFile(dir=path) as probe:
                probe.write(b"p2p")
                probe.flush()
        except OSError as exc:
            raise StorageUnavailable(
                f"Dossier non accessible en écriture : {path}."
            ) from exc
    return path


def separate(*paths):
    paths = [Path(p) for p in paths if p]
    for i, first in enumerate(paths):
        for second in paths[i + 1 :]:
            if first == second or first in second.parents or second in first.parents:
                raise StorageUnavailable(
                    "Les dossiers de stockage doivent être distincts et non imbriqués."
                )


class RootRegistry:
    def __init__(self, state):
        self.state = Path(state)
        self.state.mkdir(parents=True, exist_ok=True)
        self.file = self.state / "storage-roots.json"

    def roots(self):
        return json.loads(self.file.read_text()) if self.file.exists() else {}

    def register(self, value, *, initial_downloads=False):
        path = Path(value).absolute()
        with (self.state / "storage-roots.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            roots = self.roots()
            expected = roots.get(str(path))
            if expected:
                self.check(path, expected)
                directory(path, writable=True)
                return expected
            # Older torrents can still live under previous roots after a
            # settings change. Never register a root inside their payloads.
            separate(path, self.state)
            for old_root in roots:
                separate(path, old_root)
            if initial_downloads:
                path.mkdir(parents=True, exist_ok=True)
            path = directory(path, writable=True)
            marker = path / MARKER
            if marker.is_symlink():
                raise StorageUnavailable("Marqueur de stockage invalide.")
            if not marker.exists():
                identity = str(uuid.uuid4())
                # Only explicit registration can create an identity marker.
                with marker.open("x") as out:
                    out.write(identity)
                    out.flush()
                    os.fsync(out.fileno())
            try:
                identity = str(uuid.UUID(marker.read_text().strip()))
            except (OSError, ValueError) as exc:
                raise StorageUnavailable(
                    "Marqueur de stockage illisible ou invalide."
                ) from exc
            roots[str(path)] = identity
            write_json(self.file, roots)
            return identity

    def check(self, value, expected=None):
        path = directory(value)
        identity = self.roots().get(str(path))
        marker = path / MARKER
        try:
            if (
                not identity
                or (expected and identity != expected)
                or marker.is_symlink()
                or marker.read_text().strip() != identity
            ):
                raise ValueError
        except (OSError, ValueError) as exc:
            raise StorageUnavailable(
                f"Disque indisponible ou identité différente : {path}. Aucun dossier ne sera recréé."
            ) from exc
        return path


class FolderSettings:
    def __init__(self, config):
        self.config = config
        self.registry = RootRegistry(config.storage.state)
        self.file = config.storage.state / "storage-settings.json"
        previous = json.loads(self.file.read_text()) if self.file.exists() else {}
        self.revision = previous.get("revision", 0) + 1
        for name in ("downloads", "completed"):
            root = getattr(config.storage, name)
            if root:
                try:
                    self.registry.register(root, initial_downloads=name == "downloads")
                except (OSError, ValueError):
                    # An absent completed disk must not prevent the web app or
                    # torrents still on their original disk from starting.
                    pass

    def payload(self):
        return {
            "downloads": str(self.config.storage.downloads),
            "completed": str(self.config.storage.completed)
            if self.config.storage.completed
            else None,
            "revision": self.revision,
        }

    def prepare(self, downloads, completed):
        if not self.config._path:
            raise StorageUnavailable(
                "Le chemin du fichier YAML est inconnu. Démarrez avec ./run.sh."
            )
        downloads = directory(downloads, writable=True)
        completed = directory(completed, writable=True) if completed else None
        separate(downloads, completed, self.config.storage.state)
        self.registry.register(downloads)
        if completed:
            self.registry.register(completed)
        return {
            "downloads": str(downloads),
            "completed": str(completed) if completed else None,
            "revision": self.revision + 1,
        }

    def commit(self, payload, *, write_yaml=True):
        yaml = YAML()
        yaml.preserve_quotes = True
        path = self.config._path
        try:
            if write_yaml:
                document = yaml.load(path.read_text())
                section = document.setdefault("storage", {})
                section["downloads"] = payload["downloads"]
                section["completed"] = payload["completed"]
                output = io.StringIO()
                yaml.dump(document, output)
            # YAML is the commit point. The revision sidecar is advisory; if
            # either write fails before the YAML replacement, workers can
            # safely abort the prepared update and retain the old directories.
            write_json(self.file, payload)
            if write_yaml:
                atomic_write(path, output.getvalue().encode())
        except (OSError, YAMLError, AttributeError, TypeError) as exc:
            raise StorageUnavailable(
                "Impossible d'enregistrer les dossiers : vérifiez le YAML, l'espace libre et les droits du dossier de configuration."
            ) from exc
        self.config.storage.downloads = Path(payload["downloads"])
        self.config.storage.completed = (
            Path(payload["completed"]) if payload["completed"] else None
        )
        self.revision = payload["revision"]


def browse_directories(value=None, offset=0):
    path = directory(value or Path.home().resolve())
    try:
        entries = sorted(
            (
                p
                for p in path.iterdir()
                if not p.name.startswith(".")
                and not p.is_symlink()
                and p.is_dir()
                and os.access(p, os.R_OK | os.X_OK)
            ),
            key=lambda p: p.name.casefold(),
        )
    except OSError as exc:
        raise StorageUnavailable(f"Impossible de parcourir {path}.") from exc
    shortcuts = [
        ("home", "Dossier personnel", Path.home().resolve()),
        ("root", "Racine", Path("/")),
    ]
    for key, label, root in (
        ("drives", "Disques", "/Volumes"),
        ("media", "Médias", "/media"),
        ("mounts", "Montages", "/mnt"),
        ("user_drives", "Disques utilisateur", "/run/media"),
    ):
        if Path(root).is_dir():
            shortcuts.append((key, label, Path(root)))
    return {
        "path": str(path),
        "parent": str(path.parent),
        "directories": [
            {"name": p.name, "path": str(p)} for p in entries[offset : offset + 200]
        ],
        "next_offset": offset + 200 if len(entries) > offset + 200 else None,
        "shortcuts": [
            {"key": key, "name": name, "path": str(p)} for key, name, p in shortcuts
        ],
    }
