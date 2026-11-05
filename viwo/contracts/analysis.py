"""Static analysis arm (doc 6) and interactive handoffs (doc 8.3a): value types and the two
backend interfaces. An analyzer reads a copy of a binary and writes artifacts; a handoff
prepares the same target and hands it to a GUI tool that runs as a tracked child of ViWo.
Both use the ExtractionContext (`staging` is the output folder): one context type per arm."""

import re
from abc import abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .plugin import ExtractionContext
from .slots import Backend
from .types import Outcome

KINDS = tuple(
    "native_binary dotnet_assembly il2cpp python_bytecode gdscript_bytecode script_vm "
    "memory_image".split()
)
ANALYSIS_DIR = ".analysis"  # <workspace>/.analysis/<analyzer id>/<target key>/


def target_key(path: Path) -> str:
    """A stable, filesystem-safe key from the primary file name."""
    return re.sub(r"[^a-z0-9]+", "-", path.name.lower()).strip("-") or "target"


@dataclass(frozen=True)
class AnalysisTarget:
    """WHAT to analyse (doc 6.1): proposed by an engine plugin or given by the user."""

    key: str  # stable, filesystem-safe (a slug of the primary file)
    kind: str  # one of KINDS
    paths: tuple[Path, ...]  # primary file first, companions after
    owner: str  # plugin id or "user"
    label: str = ""
    hints: Mapping[str, str] = field(default_factory=dict)  # arch, engine_version, ...

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "kind": self.kind,
            "paths": [str(p) for p in self.paths],
            "owner": self.owner,
            "label": self.label or self.paths[0].name,
            "hints": dict(self.hints),
        }


@dataclass(frozen=True)
class LaunchSpec:
    """What a handoff asks the OS layer to start (doc 8.3a): a GUI tool as a tracked child."""

    argv: tuple[str, ...]
    cwd: Path | None = None
    env: Mapping[str, str] = field(default_factory=dict)


class Analyzer(Backend):
    """HOW (doc 6.1): a backend in an `analysis.*` slot. `kinds` lists the target kinds it
    accepts; `analyze` writes its artifacts under `ctx.staging` and never touches the input."""

    families = frozenset({"analysis"})
    kinds: tuple[str, ...] = ()

    @abstractmethod
    def analyze(self, target: AnalysisTarget, ctx: ExtractionContext) -> Outcome:
        """Write the artifacts under ctx.staging; the Outcome counts them or says why not."""


class Handoff(Backend):
    """ "Continue in <tool>" (doc 8.3a): `prepare` does the glue ViWo owns (import a project,
    resolve the artifact) and returns the launch spec; the OS layer starts the tool."""

    families = frozenset({"handoff"})
    label: str = ""  # "Continue in Ghidra"
    accepts: tuple[str, ...] = ()  # target kinds

    @abstractmethod
    def prepare(self, target: AnalysisTarget, ctx: ExtractionContext) -> LaunchSpec | Outcome:
        """A LaunchSpec, or an Outcome saying why the tool cannot open this target."""
