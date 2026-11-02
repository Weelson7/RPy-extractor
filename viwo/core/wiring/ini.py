"""Startup ini parsing (doc 9, flat prototype form)."""

from __future__ import annotations

import configparser
from dataclasses import dataclass, field
from pathlib import Path

from viwo.contracts.errors import ViwoError

KNOWN_SECTIONS = {"startup", "plugins", "slots", "tools", "server"}
SECRET_WORDS = ("key", "secret", "password", "token")


@dataclass
class StartupConfig:
    os_id: str = "auto"
    profile: str = "mixed"
    features: tuple[str, ...] = ("extraction", "sorting", "merger")
    auto_install: bool = False
    strict_preflight: bool = False
    plugins: dict[str, bool] = field(default_factory=dict)
    custom_dirs: tuple[Path, ...] = ()
    slots: dict[str, tuple[str, str]] = field(default_factory=dict)
    tools: dict[str, str] = field(default_factory=dict)
    options: dict[str, dict[str, str]] = field(default_factory=dict)
    source: str = "defaults"
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
    out.os_id = str(sec.get("os", out.os_id)).lower()
    out.profile = str(sec.get("profile", out.profile)).lower()
    if "features" in sec:
        out.features = tuple(_split(sec["features"]))
    for name in ("auto_install", "strict_preflight"):
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


def load_ini(path: Path | None) -> StartupConfig:
    """Parse the startup ini; missing file = built-in defaults."""
    out = StartupConfig()
    if path is None or not path.exists():
        return out
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    try:
        cfg.read(path, encoding="utf-8-sig")
        _read_startup(cfg, out)
        _read_tables(cfg, out, path.parent)
        _read_options(cfg, out)
        _read_server(cfg, out, path.parent)
    except (configparser.Error, ValueError) as exc:
        raise ViwoError("invalid_request", f"{path}: {exc}") from exc
    out.source = str(path)
    return out
