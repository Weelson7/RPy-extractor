"""Startup ini parsing (doc 9): one flat file, one optional `base =` layer, strict checks."""

from __future__ import annotations

import configparser
from dataclasses import dataclass, field
from pathlib import Path

from viwo import CONTRACT_VERSION
from viwo.contracts.errors import ViwoError

KNOWN_SECTIONS = {"startup", "plugins", "slots", "tools", "server"}
FORM_KEYS = ("os", "profile", "features", "auto_install", "strict_preflight", "av_exclusions")
STARTUP_KEYS = {*FORM_KEYS, "base", "contract"}
SERVER_KEYS = {"host", "port", "workspace", "merged", "logs", "temp"}
MAX_LAYERS = 2  # doc 9.1: the ini and at most one base file
SECRET_WORDS = ("key", "secret", "password", "token")


@dataclass
class StartupConfig:
    os_id: str = "auto"
    profile: str = "mixed"
    features: tuple[str, ...] = ("extraction", "sorting", "merger")
    auto_install: bool = True  # install missing pinned tools into third_party/ at startup
    strict_preflight: bool = False
    av_exclusions: bool = True  # workspace, source and temp skip the antivirus during a job
    plugins: dict[str, bool] = field(default_factory=dict)
    custom_dirs: tuple[Path, ...] = ()
    slots: dict[str, tuple[str, str]] = field(default_factory=dict)
    tools: dict[str, str] = field(default_factory=dict)
    options: dict[str, dict[str, str]] = field(default_factory=dict)
    source: str = "defaults"
    path: Path | None = None  # the ini file itself (None = built-in defaults)
    contract: str = CONTRACT_VERSION
    sources: dict[str, str] = field(default_factory=dict)  # "section.key" -> default|base|ini|cli
    problems: list[str] = field(default_factory=list)
    server: "ServerConfig" = field(default_factory=lambda: ServerConfig.under(Path.cwd()))


@dataclass
class ServerConfig:
    """[server] section: where the web server listens and keeps its data."""

    host: str = "127.0.0.1"
    port: int = 8081
    workspace: Path = Path("viwo-data/workspace")  # default extraction workspace
    merged: Path = Path("viwo-data/merged")  # media merger outputs
    logs: Path = Path("viwo-data/logs")
    temp: Path = Path("viwo-data/tmp")

    @classmethod
    def under(cls, base: Path) -> "ServerConfig":
        d = cls()
        return cls(
            d.host, d.port, base / d.workspace, base / d.merged, base / d.logs, base / d.temp
        )


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _read_startup(cfg: configparser.ConfigParser, out: StartupConfig) -> None:
    sec = cfg["startup"] if cfg.has_section("startup") else {}
    out.contract = str(sec.get("contract", CONTRACT_VERSION)).strip()
    if out.contract.split(".")[0] != CONTRACT_VERSION.split(".")[0]:
        raise ViwoError(
            "invalid_request",
            f"[startup] contract = {out.contract}: this ViWo implements contract "
            f"{CONTRACT_VERSION} (major versions must match)",
        )
    out.os_id = str(sec.get("os", out.os_id)).lower()
    out.profile = str(sec.get("profile", out.profile)).lower()
    if "features" in sec:
        out.features = tuple(_split(sec["features"]))
    for name in ("auto_install", "strict_preflight", "av_exclusions"):
        if name in sec:
            setattr(out, name, cfg.getboolean("startup", name))


def _read_tables(cfg: configparser.ConfigParser, out: StartupConfig, base: Path) -> None:
    if cfg.has_section("plugins"):
        for key, value in cfg["plugins"].items():
            if key == "custom_dirs":
                out.custom_dirs = tuple((base / p).resolve() for p in _split(value))
            else:
                out.plugins[key.lower()] = cfg.getboolean("plugins", key)
    if cfg.has_section("slots"):
        for slot, value in cfg["slots"].items():
            parts = [p if p != "none" else "" for p in _split(value)] + ["", ""]
            out.slots[slot.lower()] = (parts[0], parts[1])
    if cfg.has_section("tools"):
        out.tools = {k.lower(): str((base / v).resolve()) for k, v in cfg["tools"].items()}


def _read_options(cfg: configparser.ConfigParser, out: StartupConfig) -> None:
    for section in cfg.sections():
        if section.startswith("options."):
            plugin = section.split(".", 1)[1].lower()
            for key, value in cfg[section].items():
                if any(word in key.lower() for word in SECRET_WORDS):
                    out.problems.append(f"[{section}] {key}: secrets are not allowed in the ini")
                    continue
                out.options.setdefault(plugin, {})[key] = value
        elif section not in KNOWN_SECTIONS:
            out.problems.append(f"unknown section [{section}] ignored")


def _read_server(cfg: configparser.ConfigParser, out: StartupConfig, base: Path) -> None:
    server = ServerConfig.under(base)
    sec = cfg["server"] if cfg.has_section("server") else {}
    server.host = str(sec.get("host", server.host))
    server.port = int(sec.get("port", server.port))
    for key in ("workspace", "merged", "logs", "temp"):
        if key in sec:
            setattr(server, key, (base / sec[key]).resolve())
    out.server = server


def _parser() -> configparser.ConfigParser:
    return configparser.ConfigParser(inline_comment_prefixes=(";", "#"))


def layers(path: Path) -> list[Path]:
    """The file and the files it names with [startup] base = (relative to the naming file),
    base first. At most MAX_LAYERS files; cycles and missing bases are errors."""
    chain, current = [], path.resolve()
    while current is not None:
        if current in chain or len(chain) >= MAX_LAYERS:
            raise ViwoError(
                "invalid_request", f"{path}: base chain loops or has more than one level"
            )
        chain.append(current)
        cfg = _parser()
        cfg.read(current, encoding="utf-8-sig")
        base = cfg.get("startup", "base", fallback="").strip()
        current = (current.parent / base).resolve() if base else None
        if current is not None and not current.is_file():
            raise ViwoError("invalid_request", f"{chain[-1]}: base file not found: {base}")
    return list(reversed(chain))


def _unknown_keys(cfg: configparser.ConfigParser, out: StartupConfig) -> None:
    for section, known in (("startup", STARTUP_KEYS), ("server", SERVER_KEYS)):
        if cfg.has_section(section):
            for key in cfg[section]:
                if key not in known:
                    out.problems.append(f"[{section}] {key}: unknown key ignored")


def _sources(files: list[Path], out: StartupConfig) -> None:
    """Doc 9.1: where every effective value comes from (default, base, ini); cli is added by
    boot. Keys are "section.key"; [startup] fields absent from every file read "default"."""
    for name in (*FORM_KEYS, "contract"):
        out.sources[f"startup.{name}"] = "default"
    for index, file in enumerate(files):
        origin = "ini" if index == len(files) - 1 else "base"
        cfg = _parser()
        cfg.read(file, encoding="utf-8-sig")
        for section in cfg.sections():
            for key in cfg[section]:
                out.sources[f"{section}.{key}"] = origin


def load_ini(path: Path | None) -> StartupConfig:
    """Parse the startup ini (and its base layers); missing file = built-in defaults."""
    out = StartupConfig()
    if path is None or not path.exists():
        return out
    cfg = _parser()
    try:
        files = layers(path)
        cfg.read(files, encoding="utf-8-sig")  # later files override earlier ones
        _unknown_keys(cfg, out)
        _sources(files, out)
        _read_startup(cfg, out)
        _read_tables(cfg, out, path.parent)
        _read_options(cfg, out)
        _read_server(cfg, out, path.parent)
    except (configparser.Error, ValueError) as exc:
        raise ViwoError("invalid_request", f"{path}: {exc}") from exc
    out.source = " <- ".join(str(f) for f in reversed(files))
    out.path = path
    return out
