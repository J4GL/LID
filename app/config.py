from pathlib import Path
import copy
import ipaddress
import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Server(StrictModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1024, le=65535)

    @field_validator("host")
    @classmethod
    def local_only(cls, value):
        if value not in ("127.0.0.1", "::1"):
            raise ValueError("Cette version est locale : utiliser 127.0.0.1 ou ::1.")
        return value


class Storage(StrictModel):
    downloads: Path = Path("downloads")
    completed: Path | None = None
    state: Path = Path("data")


class Direct(StrictModel):
    port: int = Field(default=51413, ge=1024, le=65535)
    upnp: bool = True


class Proxy(StrictModel):
    enabled: bool = True
    host: str = ""
    port: int = Field(default=1080, ge=1, le=65535)
    username: str = ""
    password: str = ""
    udp: str = "auto"
    timeout: float = Field(default=5, ge=0.2, le=60)
    check_interval: float = Field(default=30, ge=2, le=600)
    dns_server: str = "1.1.1.1"
    dht_bootstrap: list[str] = [
        "dht.libtorrent.org:25401",
        "router.bittorrent.com:6881",
    ]

    @field_validator("host")
    @classmethod
    def clean_host(cls, value):
        value = value.strip()
        if any(c in value for c in "/@\n\r "):
            raise ValueError("Le proxy attend un nom d'hôte, sans URL ni identifiants.")
        return value

    @field_validator("udp")
    @classmethod
    def udp_policy(cls, value):
        if value not in ("auto", "off"):
            raise ValueError("udp doit être auto ou off")
        return value

    @field_validator("dns_server")
    @classmethod
    def numeric_dns(cls, value):
        ipaddress.ip_address(value)
        return value

    @field_validator("dht_bootstrap")
    @classmethod
    def valid_bootstrap_nodes(cls, values):
        if len(values) > 32:
            raise ValueError("32 nœuds DHT maximum")
        cleaned = []
        for value in values:
            try:
                host, port = value.rsplit(":", 1)
                host = host.strip().strip("[]")
                port = int(port)
            except (AttributeError, ValueError) as exc:
                raise ValueError("Chaque nœud DHT doit utiliser hôte:port") from exc
            if not host or not 1 <= port <= 65535 or any(c in host for c in "/@ "):
                raise ValueError("Nœud DHT invalide")
            cleaned.append(f"{host}:{port}")
        return list(dict.fromkeys(cleaned))

    @property
    def configured(self):
        return self.enabled and bool(self.host)


class Seeding(StrictModel):
    upload_limit: int = Field(default=0, ge=0)
    download_limit: int = Field(default=0, ge=0)
    connections: int = Field(default=500, ge=10, le=10000)
    file_pool_size: int = Field(default=100, ge=10, le=10000)
    save_interval: float = Field(default=30, ge=1, le=600)


class Config(StrictModel):
    _path: Path | None = PrivateAttr(default=None)
    server: Server = Field(default_factory=Server)
    storage: Storage = Field(default_factory=Storage)
    direct: Direct = Field(default_factory=Direct)
    proxy: Proxy = Field(default_factory=lambda: Proxy(enabled=False, host=""))
    seeding: Seeding = Field(default_factory=Seeding)


def config_from_mapping(raw, path: str | Path) -> Config:
    path = Path(path).resolve()
    raw = copy.deepcopy(raw)
    if not isinstance(raw, dict):
        raise ValueError("Le fichier YAML doit contenir une configuration.")
    # An omitted/null proxy explicitly means NO proxy; never insert our default.
    if not raw.get("proxy"):
        raw["proxy"] = {"enabled": False, "host": ""}
    elif not isinstance(raw["proxy"], dict):
        raise ValueError(
            "La section proxy doit contenir des paramètres YAML ou être nulle."
        )
    elif "host" not in raw["proxy"]:
        raw["proxy"]["host"] = ""
    config = Config.model_validate(raw)
    config._path = path
    for field in ("downloads", "completed", "state"):
        if getattr(config.storage, field) is None:
            continue
        p = getattr(config.storage, field).expanduser()
        setattr(config.storage, field, (path.parent / p).resolve())
    if config.storage.downloads == config.storage.state:
        raise ValueError(
            "Les dossiers de données et de téléchargements doivent être distincts."
        )
    folders = [config.storage.downloads, config.storage.state, config.storage.completed]
    for i, first in enumerate(folders):
        for second in folders[i + 1 :]:
            if (
                first
                and second
                and (
                    first == second
                    or first in second.parents
                    or second in first.parents
                )
            ):
                raise ValueError(
                    "Les dossiers de stockage doivent être distincts et non imbriqués."
                )
    if config.server.port == config.direct.port:
        raise ValueError(
            "Le port web et le port torrent direct doivent être distincts."
        )
    return config


def load_config(path: str | Path) -> Config:
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f"Configuration introuvable : {path}")
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f" à la ligne {mark.line + 1}" if mark else ""
        raise ValueError(
            f"YAML invalide{location}. Vérifiez l'indentation et les valeurs."
        ) from exc
    return config_from_mapping(raw, path)
