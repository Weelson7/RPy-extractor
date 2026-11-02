"""Engine plugin contract (doc 2). A plugin knows one game engine.

Rules: detect() is fast and pure (probe only); plugins write only into
ctx.staging / ctx.scratch; tools run through ctx.os; no print().
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .os import OS
from .slots import Backend, SlotDefinition
from .types import CancelToken, DetectionResult, ProgressEvent, ProgressSink


@dataclass(frozen=True)
class PluginOption:
    key: str
    label: str
    kind: str = "string"  # string | secret | bool | int | choice | path
    default: Any = None
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    name: str
    version: str
    engine_type: str
    contract: str = "1.0"
    priority: int = 0
    options: tuple[PluginOption, ...] = ()
    tos_sensitive: bool = False
    builtin: bool = True


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

    def log(self, message: str, level: str = "info", stage: str = "") -> None:
        if self.progress:
            self.progress(ProgressEvent(message, level, self.source, stage))


class EnginePlugin(ABC):
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

    def verify(self, ctx: ExtractionContext, collected: int) -> Sequence[str]:
        """Return warnings."""
        return ()
