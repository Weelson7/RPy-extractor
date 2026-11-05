"""Shared value types (contract doc 2, 4.4, 8). Stdlib only, no app imports."""

import functools
import json
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping


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
    """A tool a backend needs (doc 2.6). `executables` are bare names (the OS layer adds the
    suffixes), either one tuple for every OS layer or a mapping `{os_id: names}`."""

    dep_id: str
    label: str
    kind: str = "executable"  # "executable" | "python" | "runtime"
    requirement: Requirement = Requirement.OPTIONAL
    import_name: str = ""
    executables: tuple[str, ...] | Mapping[str, tuple[str, ...]] = ()
    install_dirs: tuple[str, ...] = ()  # folder names searched under known install roots
    env_var: str = ""
    hint: str = ""

    def executables_for(self, os_id: str) -> tuple[str, ...]:
        if isinstance(self.executables, Mapping):
            return tuple(self.executables.get(os_id, ()))
        return tuple(self.executables)

    @classmethod
    def of(cls, dep_id: str) -> "DependencySpec":
        """A tool, package or runtime ViWo's own backends need, as `viwo/data/dependencies.json`
        describes it (plugins of others may still build their own)."""
        fields = dict(_known()[dep_id])
        names = fields.get("executables", ())
        fields["executables"] = (
            {os_id: tuple(v) for os_id, v in names.items()}
            if isinstance(names, dict)
            else tuple(names)
        )
        fields["install_dirs"] = tuple(fields.get("install_dirs", ()))
        fields["requirement"] = Requirement(fields.get("requirement", "optional"))
        return cls(dep_id, **fields)


@functools.lru_cache(maxsize=1)
def _known() -> dict:
    path = Path(__file__).resolve().parent.parent / "data" / "dependencies.json"
    return json.loads(path.read_text(encoding="utf-8"))


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
    fallback: str = ""  # set by the failover: why the main backend was not the one used

    @property
    def ok(self) -> bool:
        return self.kind is OutcomeKind.OK

    @property
    def retryable(self) -> bool:
        """Whether the spare backend should be tried after this outcome."""
        return self.kind in (OutcomeKind.UNAVAILABLE, OutcomeKind.FAILED)
