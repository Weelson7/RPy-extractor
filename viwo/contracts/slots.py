"""Slots and backends (doc 8): every pipeline engine sits behind an interface.

A slot is one job ("unarchive .7z") with a main and an optional spare backend.
The core identifies files for unarchive slots (head/tail bytes, carving) and
falls back to the spare when the main's outcome is retryable.
"""

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
    fallback: bool = False  # identify only what no suffix or signature of another slot claims


class Backend(ABC):
    backend_id: str = ""
    owner: str = "core"
    families: frozenset[str] = frozenset()
    license: str = ""  # SPDX
    isolation: str = "inprocess"  # "inprocess" | "subprocess" (GPL/AGPL must be subprocess)
    network: str = "none"  # "none" | "download" | "any": what the backend may reach (doc 8.4)
    parses_untrusted_in_process: bool = False  # reads game/archive bytes in the ViWo process
    self_check_args: tuple[str, ...] = ("--version",)  # how self_check() pokes a CLI tool
    requires: tuple[DependencySpec, ...] = ()  # the tools it needs; or override dependencies()

    def dependencies(self) -> Sequence[DependencySpec]:
        return self.requires

    def available(self, os: "OS") -> tuple[bool, str]:
        """Side-effect free check: (usable, reason when not)."""
        for spec in self.dependencies():
            if os.tools.locate(spec) is None:
                return False, spec.hint or f"{spec.label} not found"
        return True, ""

    def self_check(self, os: "OS") -> tuple[bool, str]:
        """`viwo slots --check`: available(), plus a real run of every CLI tool (doc 8.6).
        A tool passes when it starts and answers within 8 s; its exit code does not matter."""
        ok, reason = self.available(os)
        if not ok or self.isolation != "subprocess":
            return ok, reason
        for spec in self.dependencies():
            tool = os.tools.locate(spec)
            if tool is None or spec.kind != "executable":
                continue
            result = os.process.run([*tool.argv_prefix, *self.self_check_args], timeout=8)
            if result.timed_out or not (result.stdout or result.stderr):
                return False, f"{spec.label}: did not answer {' '.join(self.self_check_args)}"
        return True, ""


class Unarchiver(Backend):
    families = frozenset({"unarchive"})

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


class Prober(Backend):
    """media.probe (doc 8.3): what a media file is (format, duration, size), never rewritten."""

    families = frozenset({"probe"})

    @abstractmethod
    def probe(self, path: Path, ctx: "ExtractionContext") -> Outcome:
        """Outcome.notes carry the facts ("format=png", "width=640", "duration=1.5")."""


class Packer(Backend):
    """Round trip (doc 18): write edited members into the patched copy, never the game."""

    families = frozenset({"pack"})
    override = False  # True: a separate file loaded over the container, which keeps the rest

    def output_for(self, container: Path) -> Path:
        """The file this packer writes for a container (itself when rebuilt in place)."""
        return container

    def verify(self, output: Path, members: dict[str, Path], ctx: "ExtractionContext"):
        """Members not written back correctly, or None to verify by re-extraction."""
        return None

    @abstractmethod
    def pack(self, container: Path, members: dict[str, Path], ctx: "ExtractionContext") -> Outcome:
        """container lies inside the patched copy; members map member path -> edited file."""


@dataclass(frozen=True)
class SlotBinding:
    slot_id: str
    main: str  # backend id, "" when unbound
    spare: str = ""
    promoted: bool = False  # main was unavailable, spare acts as main
    source: str = "default"  # "default" | "ini" | "cli"
    reasons: tuple[str, ...] = ()

    @property
    def bound(self) -> bool:
        return bool(self.main)
