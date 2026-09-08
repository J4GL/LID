"""Complete UI-managed configuration and supervised restart transactions."""

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import uuid

from pydantic import ValidationError
from ruamel.yaml import YAML

from .config import Config, config_from_mapping, load_config
from .folders import directory, separate, StorageUnavailable
from .storage import atomic_write, write_json


class SettingsValidation(ValueError):
    def __init__(self, message, fields=None, warnings=None):
        super().__init__(message)
        self.fields = fields or {}
        self.warnings = warnings or []


def _config_dict(config, *, redact=False):
    data = config.model_dump(mode="json")
    if redact:
        password = data["proxy"].pop("password", "")
        data["proxy"]["password_configured"] = bool(password)
    return data


def _set_config(target, source):
    for section in ("server", "storage", "direct", "proxy", "seeding"):
        setattr(target, section, getattr(source, section))
    target._path = source._path


def _merge(document, values):
    for key, value in values.items():
        if isinstance(value, dict):
            section = document.get(key)
            if not isinstance(section, dict):
                section = {}
                document[key] = section
            _merge(section, value)
        else:
            document[key] = value


def _nearest_existing(path):
    candidate = Path(path)
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _planned_directory(value, *, may_create=False, empty=False):
    path = Path(os.path.abspath(Path(value).expanduser()))
    existing = _nearest_existing(path)
    if existing.resolve() != existing or any(
        parent.is_symlink() for parent in (existing, *existing.parents)
    ):
        raise StorageUnavailable("Les liens symboliques ne sont pas autorisés.")
    if path.exists():
        directory(path, writable=True)
        if empty and any(path.iterdir()):
            raise StorageUnavailable("Le nouveau dossier de données doit être vide.")
    elif not may_create:
        raise StorageUnavailable(f"Dossier indisponible : {path}.")
    else:
        directory(existing, writable=True)
    return path


def _hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class SettingsService:
    restart_fields = {
        "server",
        "storage.state",
        "direct",
        "proxy",
    }

    def __init__(self, config, path, *, load_error=None, setup_required=False):
        self.config = config
        self.path = Path(path).resolve()
        self.config._path = self.path
        self.load_error = load_error
        self.setup_required = setup_required
        self.marker = self.path.with_name(f".{self.path.name}.lid-setup")
        self.pending = self.path.with_name(f".{self.path.name}.lid-pending.yaml")
        self.restart_journal = self.path.with_name(f".{self.path.name}.lid-restart.json")
        self.migration_journal = self.path.with_name(
            f".{self.path.name}.lid-state-migration.json"
        )

    @classmethod
    def load(cls, path):
        path = Path(path).resolve()
        error = None
        try:
            config = load_config(path)
        except ValueError as exc:
            error = str(exc)
            config = Config()
            config._path = path
            for name in ("downloads", "completed", "state"):
                value = getattr(config.storage, name)
                if value is not None:
                    setattr(config.storage, name, (path.parent / value).resolve())
        marker = path.with_name(f".{path.name}.lid-setup")
        existing = cls.existing_installation(config)
        setup_required = bool(error) or (not marker.exists() and not existing)
        service = cls(
            config,
            path,
            load_error=error,
            setup_required=setup_required,
        )
        if existing and not marker.exists() and not error:
            service.complete_setup()
        return service

    @staticmethod
    def existing_installation(config):
        state = config.storage.state
        return any(
            (state / relative).exists()
            for relative in (
                "storage-roots.json",
                "storage-settings.json",
                "direct/index.json",
                "proxy/index.json",
            )
        )

    def complete_setup(self):
        atomic_write(self.marker, b'{"complete":true}\n')
        try:
            os.chmod(self.marker, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        self.setup_required = False
        self.load_error = None

    def public(self):
        return {
            "values": _config_dict(self.config, redact=True),
            "defaults": _config_dict(Config(), redact=True),
            "setup_required": self.setup_required,
            "load_error": self.load_error,
            "restart_required": False,
        }

    def candidate(self, payload):
        raw = json.loads(json.dumps(payload))
        proxy = raw.setdefault("proxy", {})
        clear = bool(proxy.pop("clear_password", False))
        supplied = proxy.pop("password", None)
        proxy.pop("password_configured", None)
        if clear:
            proxy["password"] = ""
        elif supplied:
            proxy["password"] = supplied
        else:
            proxy["password"] = self.config.proxy.password
        try:
            return config_from_mapping(raw, self.path)
        except (ValidationError, ValueError) as exc:
            fields = {}
            if isinstance(exc, ValidationError):
                for error in exc.errors(include_url=False, include_input=False):
                    fields[".".join(str(item) for item in error["loc"])] = error["msg"]
            else:
                fields["configuration"] = str(exc)
            raise SettingsValidation("Configuration invalide.", fields) from exc

    def validate(self, candidate, *, setup_endpoint=None, check_ports=True):
        fields = {}
        old_state = self.config.storage.state
        default_downloads = (self.path.parent / "downloads").resolve()
        default_state = (self.path.parent / "data").resolve()
        try:
            _planned_directory(
                candidate.storage.downloads,
                may_create=self.setup_required
                and candidate.storage.downloads == default_downloads,
            )
        except ValueError as exc:
            fields["storage.downloads"] = str(exc)
        if candidate.storage.completed:
            try:
                _planned_directory(candidate.storage.completed)
            except ValueError as exc:
                fields["storage.completed"] = str(exc)
        try:
            _planned_directory(
                candidate.storage.state,
                may_create=self.setup_required and candidate.storage.state == default_state,
                empty=candidate.storage.state != old_state,
            )
        except ValueError as exc:
            fields["storage.state"] = str(exc)
        try:
            separate(
                candidate.storage.downloads,
                candidate.storage.completed,
                candidate.storage.state,
            )
        except ValueError as exc:
            fields["storage"] = str(exc)
        if candidate.proxy.enabled and not candidate.proxy.host:
            fields["proxy.host"] = "Un hôte est requis lorsque le proxy est activé."
        if check_ports:
            from .launch import check_port
            import socket

            endpoint = (candidate.server.host, candidate.server.port)
            if endpoint != setup_endpoint and endpoint != (
                self.config.server.host,
                self.config.server.port,
            ):
                try:
                    check_port(*endpoint, socket.SOCK_STREAM)
                except ValueError as exc:
                    fields["server.port"] = str(exc)
            if candidate.direct.port != self.config.direct.port or self.setup_required:
                for host in ("0.0.0.0", "::"):
                    if host == "::" and not socket.has_ipv6:
                        continue
                    for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
                        try:
                            check_port(host, candidate.direct.port, kind)
                        except ValueError as exc:
                            fields["direct.port"] = str(exc)
        if fields:
            raise SettingsValidation("Certains réglages sont invalides.", fields)
        return {"valid": True, "fields": {}, "warnings": []}

    def changed(self, candidate):
        before = _config_dict(self.config)
        after = _config_dict(candidate)
        changes = set()
        for section in before:
            if before[section] == after[section]:
                continue
            if section == "storage":
                for key in before[section]:
                    if before[section][key] != after[section][key]:
                        changes.add(f"storage.{key}")
            else:
                changes.add(section)
        return changes

    def needs_restart(self, candidate):
        changes = self.changed(candidate)
        return self.setup_required or bool(changes & self.restart_fields)

    def render(self, candidate):
        yaml = YAML()
        yaml.preserve_quotes = True
        try:
            document = yaml.load(self.path.read_text()) if self.path.exists() else {}
        except Exception:
            document = {}
        if not isinstance(document, dict):
            document = {}
        values = _config_dict(candidate)
        _merge(document, values)
        output = io.StringIO()
        yaml.dump(document, output)
        return output.getvalue().encode()

    def commit(self, candidate):
        for folder in (candidate.storage.downloads, candidate.storage.state):
            folder.mkdir(parents=True, exist_ok=True)
        atomic_write(self.path, self.render(candidate))
        _set_config(self.config, candidate)
        self.complete_setup()

    def stage_restart(self, candidate):
        atomic_write(self.pending, self.render(candidate))
        write_json(
            self.restart_journal,
            {
                "old_state": str(self.config.storage.state),
                "new_state": str(candidate.storage.state),
                "old_config": self.path.read_text() if self.path.exists() else None,
            },
        )
        for protected in (self.pending, self.restart_journal):
            try:
                os.chmod(protected, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
        return self.url(candidate)

    @staticmethod
    def url(config):
        host = f"[{config.server.host}]" if ":" in config.server.host else config.server.host
        return f"http://{host}:{config.server.port}/"

    def commit_staged(self):
        if not self.pending.exists():
            return
        candidate = load_config(self.pending)
        candidate._path = self.path
        old_state = self.config.storage.state
        if candidate.storage.state != old_state:
            self._copy_state(old_state, candidate.storage.state)
        atomic_write(self.path, self.pending.read_bytes())
        self.pending.unlink()
        self.complete_setup()

    def _copy_state(self, source, target):
        source, target = Path(source), Path(target)
        target_created = not target.exists()
        target.mkdir(parents=True, exist_ok=True)
        previous = None
        if self.migration_journal.exists():
            previous = json.loads(self.migration_journal.read_text())
        marker = target / ".lid-state-migration-target"
        if previous and previous.get("source") == str(source) and previous.get(
            "target"
        ) == str(target):
            migration_id = previous["id"]
            target_created = previous.get("target_created", False)
            if marker.is_symlink() or marker.read_text().strip() != migration_id:
                raise SettingsValidation(
                    "Reprise de migration refusée : l'identité de la destination a changé."
                )
            # The source is retained until the new engines restore successfully,
            # so a private, identified target can be rebuilt after interruption.
            known = (
                {
                    item.name
                    for item in source.iterdir()
                    if item.name not in {"app.lock", "storage-move.lock"}
                }
                if source.exists()
                else set()
            )
            for item in target.iterdir():
                if item == marker:
                    continue
                if item.name not in known and not item.name.startswith(
                    ".lid-migration-"
                ):
                    raise SettingsValidation(
                        "Reprise de migration ambiguë : la destination contient de nouvelles données."
                    )
                if item.is_dir() and not item.is_symlink():
                    shutil.rmtree(item)
                elif item.is_file() and not item.is_symlink():
                    item.unlink()
                else:
                    raise SettingsValidation(
                        "Reprise de migration ambiguë : intervention requise."
                    )
        else:
            if any(target.iterdir()):
                raise SettingsValidation("Le nouveau dossier de données doit être vide.")
            migration_id = uuid.uuid4().hex
            atomic_write(marker, f"{migration_id}\n".encode())
        stage = target / f".lid-migration-{migration_id}"
        stage.mkdir()
        source_stat = source.stat() if source.exists() else None
        journal = {
            "id": migration_id,
            "source": str(source),
            "target": str(target),
            "stage": str(stage),
            "phase": "copying",
            "source_device": source_stat.st_dev if source_stat else None,
            "source_inode": source_stat.st_ino if source_stat else None,
            "target_created": target_created,
        }
        write_json(self.migration_journal, journal)
        if source.exists():
            for item in source.iterdir():
                if item.name in {"app.lock", "storage-move.lock"}:
                    continue
                destination = stage / item.name
                if item.is_dir():
                    shutil.copytree(item, destination)
                elif item.is_file() and not item.is_symlink():
                    shutil.copy2(item, destination)
            for copied in stage.rglob("*"):
                if copied.is_file():
                    original = source / copied.relative_to(stage)
                    if not original.is_file() or _hash_file(copied) != _hash_file(original):
                        raise SettingsValidation("Échec de vérification de la migration.")
        for item in list(stage.iterdir()):
            item.replace(target / item.name)
        stage.rmdir()
        journal["phase"] = "copied"
        write_json(self.migration_journal, journal)

    def finalize_migration(self):
        if not self.migration_journal.exists():
            return
        journal = json.loads(self.migration_journal.read_text())
        if journal.get("phase") != "copied":
            return
        source = Path(journal["source"])
        target = Path(journal["target"])
        marker = target / ".lid-state-migration-target"
        protected = {Path("/"), Path.home().resolve(), self.path.parent.resolve()}
        try:
            source_stat = source.stat() if source.exists() else None
            source_matches = not source_stat or (
                source_stat.st_dev == journal.get("source_device")
                and source_stat.st_ino == journal.get("source_inode")
            )
            target_matches = (
                not marker.is_symlink()
                and marker.read_text().strip() == journal.get("id")
            )
        except OSError:
            source_matches = target_matches = False
        if (
            source.resolve() in protected
            or source.is_symlink()
            or self.config.storage.state.resolve() != target.resolve()
            or not source_matches
            or not target_matches
        ):
            raise SettingsValidation("Suppression de l'ancien dossier refusée.")
        if source.exists():
            shutil.rmtree(source)
        marker.unlink()
        self.migration_journal.unlink()
        if self.restart_journal.exists():
            self.restart_journal.unlink()

    def rollback_staged(self):
        if not self.restart_journal.exists():
            return
        journal = json.loads(self.restart_journal.read_text())
        if journal.get("old_config") is not None:
            atomic_write(self.path, journal["old_config"].encode())
        if self.pending.exists():
            self.pending.unlink()
        if self.migration_journal.exists():
            migration = json.loads(self.migration_journal.read_text())
            target = Path(migration["target"])
            marker = target / ".lid-state-migration-target"
            try:
                identified = (
                    not marker.is_symlink()
                    and marker.read_text().strip() == migration.get("id")
                )
            except OSError:
                identified = False
            if identified and target.exists():
                known = {
                    item.name
                    for item in Path(migration["source"]).iterdir()
                    if item.name not in {"app.lock", "storage-move.lock"}
                } if Path(migration["source"]).exists() else set()
                removable = all(
                    item.name in known
                    or item.name.startswith(".lid-migration-")
                    or item == marker
                    for item in target.iterdir()
                )
                if removable:
                    for item in list(target.iterdir()):
                        if item.is_dir() and not item.is_symlink():
                            shutil.rmtree(item)
                        elif item.is_file() and not item.is_symlink():
                            item.unlink()
                    if migration.get("target_created"):
                        target.rmdir()
                    self.migration_journal.unlink()
        self.restart_journal.unlink()
