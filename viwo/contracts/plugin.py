"""Engine plugin contract (doc 2). A plugin knows one game engine.

Rules: detect() is fast and pure (probe only); plugins write only into
ctx.staging / ctx.scratch; tools run through ctx.os; no print().
"""

from __future__ import annotations

import inspect
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from .os import OS
from .slots import Backend, SlotDefinition
from .types import CancelToken, DetectionResult, ProgressEvent, ProgressSink

OPTION_KINDS = ("string", "secret", "bool", "int", "float", "choice", "path")


@dataclass(frozen=True)
class PluginOption:
    key: str
    label: str
    kind: str = "string"  # one of OPTION_KINDS (doc 2.1)
    default: Any = None
    choices: tuple[str, ...] = ()
    help: str = ""


@dataclass(frozen=True)
class PluginManifest:
    """Doc 2.1. `capabilities` names what the plugin can do ("detect", "unpack", "export",
    "pack", "decode"); `dependencies` lists dependency ids for people (backends declare the
    real specs); `os_layers` restricts the plugin to hosts (empty = every OS layer)."""

    plugin_id: str
    name: str
    version: str
    engine_type: str
    contract: str = "1.0"
    priority: int = 0
    options: tuple[PluginOption, ...] = ()
    tos_sensitive: bool = False
    builtin: bool = True
    description: str = ""
    capabilities: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    os_layers: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerifyReport:
    """Doc 2.2: the plugin's own verdict after COLLECT. `expected`/`found` count inventory
    items when the plugin keeps one (0 = no completeness claim, doc 0.4)."""

    ok: bool = True
    warnings: tuple[str, ...] = ()
    expected: int = 0
    found: int = 0


@dataclass(frozen=True)
class CliCommand:
    """A `viwo <name>` subcommand contributed by a plugin (add-ons, 1.1)."""

    name: str
    help: str
    build: Callable[[Any], None]  # receives the argparse subparser: add arguments
    run: Callable[[Any, Any], Any]  # (runtime, parsed args) -> envelope data (a dict)
    override: bool = False  # replace a core command (or another plugin's) with this name
    formatter: Callable[[dict], str] | None = None  # human output; default: readable JSON


class GameProbe(Protocol):
    """Bounded, cached index of the game folder, shared by all plugins."""

    @property
    def root(self) -> Path: ...

    def has_name(self, *names: str) -> bool: ...

    def find(self, pattern: str, limit: int = 100) -> list[Path]: ...

    def with_suffix(self, *suffixes: str) -> list[Path]: ...

    def head(self, path: Path, size: int = 64) -> bytes: ...

    def tail(self, path: Path, size: int = 64) -> bytes: ...


@dataclass
class ExtractionContext:
    """Per request, per plugin view handed to hooks and backends."""

    request_id: str
    game_root: Path
    staging: Path
    scratch: Path
    os: OS
    detection: DetectionResult
    selected_exts: frozenset[str] | None = None
    options: Mapping[str, Any] = field(default_factory=dict)
    progress: ProgressSink | None = None
    cancel: CancelToken = field(default_factory=CancelToken)
    source: str = "core"
    probe: GameProbe | None = None  # the shared folder index (doc 2.3); None in tool contexts

    def log(self, message: str, level: str = "info", stage: str = "") -> None:
        if self.progress:
            self.progress(ProgressEvent(message, level, self.source, stage))

    def tool_output(self, stage: str, every: float = 0.5, mask: str = ""):
        """on_line callback for ProcessRunner.run: a tool's own output lines become events,
        at most one per `every` seconds; `mask` (a secret) is never shown."""
        last = [0.0]

        def relay(line: str) -> None:
            now = time.monotonic()
            if now - last[0] < every or not line.strip():
                return
            last[0] = now
            text = line.strip()[:200]
            if mask:
                text = text.replace(mask, "<secret>").replace(mask.upper(), "<secret>")
            self.log(text, "info", stage)

        return relay


class EnginePlugin(ABC):
    cli_enabled: bool = True  # drop-ins: only with "cli": true in plugin.json
    ui_path: Path | None = None  # drop-ins: "ui" in plugin.json; default: ui.js next to the code

    @property
    @abstractmethod
    def manifest(self) -> PluginManifest: ...

    @abstractmethod
    def detect(self, probe: GameProbe) -> DetectionResult: ...

    def configure(self, options: Mapping[str, Any]) -> None:
        """Startup options from [options.<plugin id>] in the ini (before slots are read)."""

    def slot_definitions(self) -> Sequence[SlotDefinition]:
        return ()

    def backends(self) -> Sequence[Backend]:
        return ()

    def source_roots(self, game_root: Path, probe: GameProbe) -> Sequence[Path]:
        """Loose-file roots that COLLECT copies from (never moves)."""
        return (game_root,)

    def skip_dirs(self) -> Iterable[str]:
        return ()

    def claimed_suffixes(self) -> Iterable[str]:
        """Suffixes (or exact lowercase names) the exporter decodes: not carved by default."""
        return ()

    def pack_slot(self, unarchive_slot: str) -> str:
        """Round trip: the pack.* slot that writes back into this kind of container."""
        return ""

    def export_slot(self) -> str:
        """Slot id run in the EXPORT stage, "" for none."""
        return ""

    def inventory(self, ctx: ExtractionContext) -> Sequence[str]:
        """Doc 2.2: what the plugin expects to produce (relative paths or names); empty = no
        completeness claim is ever made for this plugin (doc 0.4)."""
        return ()

    def verify_report(
        self, ctx: ExtractionContext, inventory: Sequence[str], export: Any, collected: int
    ) -> VerifyReport:
        """Doc 2.2 `verify(ctx, inventory, export, collected) -> VerifyReport`. `export` is the
        EXPORT stage outcome when the core has one, else None."""
        return VerifyReport(True, (), len(inventory), collected if inventory else 0)

    def verify(self, ctx: ExtractionContext, collected: int) -> Sequence[str]:
        """The core's call (1.0 signature). Adapts to verify_report(); a plugin written against
        1.0 may still override this method directly."""
        report = self.verify_report(ctx, self.inventory(ctx), None, collected)
        if report.ok:
            return tuple(report.warnings)
        return tuple(report.warnings) or (f"{self.manifest.name}: verification failed",)

    def sanitizer_rules(self) -> Sequence[object]:
        """Sanitizer rule providers (doc 5.2); ids must start with "<plugin id>."."""
        return ()

    def cli_commands(self) -> Sequence[CliCommand]:
        """Subcommands this plugin adds to `viwo` (add-ons; overrides by name)."""
        return ()

    def ui_module(self) -> Path | None:
        """ES module served as /plugins/<id>/ui.js (registers views and panels), or None."""
        if self.ui_path is not None:
            return self.ui_path if self.ui_path.is_file() else None
        try:
            folder = Path(inspect.getfile(type(self))).resolve().parent
        except (TypeError, OSError):  # frozen build or a class without a file
            return None
        return folder / "ui.js" if (folder / "ui.js").is_file() else None
