"""Slots and backends (doc 8): every pipeline engine sits behind an interface.

A slot is one job ("unarchive .7z") with a main and an optional spare backend.
The core identifies files for unarchive slots (head/tail bytes, carving) and
falls back to the spare when the main's outcome is retryable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Sequence

from .types import DependencySpec, Outcome

if TYPE_CHECKING:
    from .os import OS
    from .plugin import ExtractionContext

SNIFF_BYTES = 64


@dataclass(frozen=True)
class Match:
    """An identified container. offset/size describe an embedded chunk to carve."""

    slot_id: str
    path: Path
    offset: int = 0
    size: int | None = None

    @property
    def embedded(self) -> bool:
        return self.offset > 0 or self.size is not None


Identifier = Callable[[Path, bytes, bytes], "Match | None"]


@dataclass(frozen=True)
class SlotDefinition:
    slot_id: str  # "<family>.<name>", e.g. "unarchive.7z"
    family: str  # "unarchive" | "export"
    owner: str  # "core" or plugin id
    default_main: str
    default_spare: str = ""
    suffixes: tuple[str, ...] = ()  # lowercase, dotted, multi-part allowed
    magic: tuple[bytes, ...] = ()  # accepted head signatures (any)
    identify: Identifier | None = None  # custom identification (e.g. exe trailers)


class Backend(ABC):
    backend_id: str = ""
    owner: str = "core"
    families: frozenset[str] = frozenset()
    license: str = ""  # SPDX
    isolation: str = "inprocess"  # "inprocess" | "subprocess" (GPL/AGPL must be subprocess)

    def dependencies(self) -> Sequence[DependencySpec]:
        return ()

    def available(self, os: "OS") -> tuple[bool, str]:
        """Side-effect free check: (usable, reason when not)."""
        for spec in self.dependencies():
            if os.tools.locate(spec) is None:
                return False, spec.hint or f"{spec.label} not found"
        return True, ""


class Unarchiver(Backend):
    families = frozenset({"unarchive"})
    supports_keys = False

    @abstractmethod
    def extract(self, archive: Path, dest: Path, ctx: "ExtractionContext") -> Outcome:
        """Unpack one archive into the empty folder dest. Must not write outside dest
        (reject traversal, links, absolute paths)."""


class Exporter(Backend):
    families = frozenset({"export"})

    @abstractmethod
    def export(self, ctx: "ExtractionContext") -> Outcome:
        """Engine-native decoding of ctx.game_root into ctx.staging only."""


class Carver(Backend):
    families = frozenset({"carve"})

    @abstractmethod
    def carve(self, path: Path, dest: Path, ctx: "ExtractionContext") -> Outcome:
        """Write every complete file embedded in path into dest (never decrypts)."""


class Decoder(Backend):
    families = frozenset({"decode"})

    @abstractmethod
    def decode(self, path: Path, dest: Path, ctx: "ExtractionContext") -> Outcome:
        """Write viewable/playable versions of path (WAV, PNG, MP4) into the empty dest."""


class Packer(Backend):
    """Round trip (doc 18): write edited members into the patched copy, never the game."""

    families = frozenset({"pack"})

    def output_for(self, container: Path) -> Path:
        """The file this packer writes for a container (itself when rebuilt in place)."""
        return container

    @abstractmethod
    def pack(self, container: Path, members: dict[str, Path], ctx: "ExtractionContext") -> Outcome:
        """container lies inside the patched copy; members map member path -> edited file."""


@dataclass(frozen=True)
class SlotBinding:
    slot_id: str
    main: str  # backend id, "" when unbound
    spare: str = ""
    promoted: bool = False  # main was unavailable, spare acts as main
    source: str = "default"  # "default" | "ini"
    reasons: tuple[str, ...] = ()

    @property
    def bound(self) -> bool:
        return bool(self.main)
