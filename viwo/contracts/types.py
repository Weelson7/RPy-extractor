"""Shared value types (contract doc 2, 4.4, 8). Stdlib only, no app imports."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


@dataclass(frozen=True)
class ProgressEvent:
    """One progress/log line; rendered for the v1 UI as "[SOURCE:STAGE] message"."""

    message: str
    level: str = "info"
    source: str = "core"
    stage: str = ""

    def legacy_line(self) -> str:
        tag = self.source.split(":", 1)[-1].upper()
        if self.stage:
            tag = f"{tag}:{self.stage.upper()}"
        return f"[{tag}] {self.message}"


ProgressSink = Callable[[ProgressEvent], None]


class CancelToken:
    """Cooperative cancellation shared by a job and everything it runs."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


@dataclass(frozen=True)
class DetectionResult:
    """Engine detection verdict for one plugin (confidence scale: doc 2.4)."""

    engine_type: str
    confidence: float
    evidence: tuple[str, ...] = ()
    plugin_id: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence out of range: {self.confidence}")

    def to_legacy_dict(self) -> dict:
        return {
            "type": self.engine_type,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }


class Requirement(str, Enum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


@dataclass(frozen=True)
class DependencySpec:
    """A tool a backend needs. `executables` are bare names; the OS layer adds suffixes."""

    dep_id: str
    label: str
    kind: str = "executable"  # "executable" | "python"
    requirement: Requirement = Requirement.OPTIONAL
    import_name: str = ""
    executables: tuple[str, ...] = ()
    install_dirs: tuple[str, ...] = ()  # folder names searched under known install roots
    env_var: str = ""
    hint: str = ""


@dataclass(frozen=True)
class ToolLocation:
    """How to invoke a located dependency: argv_prefix + the tool's own arguments."""

    dep_id: str
    argv_prefix: tuple[str, ...]
    path: str = ""
    source: str = "path"  # "config" | "env" | "path" | "known_dir" | "python"


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


class OutcomeKind(str, Enum):
    """Prototype set of backend outcome kinds (doc 8.2, collapsed)."""

    OK = "ok"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    NEEDS_KEY = "needs_key"


@dataclass(frozen=True)
class Outcome:
    kind: OutcomeKind
    files: int = 0
    error: str = ""
    notes: tuple[str, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return self.kind is OutcomeKind.OK

    @property
    def retryable(self) -> bool:
        """Whether the spare backend should be tried after this outcome."""
        return self.kind in (OutcomeKind.UNAVAILABLE, OutcomeKind.FAILED)
