"""Patcher / isolation backends (doc 11.8): one interface for cold and live patching that holds
even when the target defends itself (self-checksums, anti-debug) or guards fragile state, and
that can satisfy TPM-gated local logic with a virtual TPM. A backend runs the target behind an
isolation boundary (a VM, an emulator, a VMI host) and drives the edit; the boundary is a pinned
third-party tool run as a separate process (CLAUDE.md: ViWo authors no hypervisor, driver or
evasion code). Three tiers (doc 16.2b T4): VirtualBox (1), QEMU (2), DRAKVUF/LibVMI (3). When a
patch cannot land the backend says WHICH wall it hit instead of failing blind (owner: never
silent)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from .slots import Backend
from .types import Outcome, OutcomeKind

if TYPE_CHECKING:
    from .os import OS


class Wall(str, Enum):
    """Why an edit could not land. NONE = it did; the rest are reported, never swallowed."""

    NONE = "none"
    SERVER_SIDE = "server_side"  # the logic the edit targets runs on a remote server, not here
    VM_DETECTED = "vm_detected"  # the target refuses to run under virtualization
    REMOTE_ATTESTATION = "remote_attestation"  # a remote party must attest the state (TPM/HW)
    INTEGRITY_CHECK = "integrity_check"  # a self-checksum reverted or rejected the edit
    NOT_READY = "not_ready"  # the backend's own requirement is not met here


class MemoryFault(Exception):
    """Guest memory could not be reached: the tier's channel refused, or the page is not in
    guest RAM (core.isolation.paging.NotResident)."""


@dataclass(frozen=True)
class WallReport:
    """The wall an action hit; the default is "no wall" (it landed)."""

    wall: Wall = Wall.NONE
    detail: str = ""

    @property
    def blocked(self) -> bool:
        return self.wall is not Wall.NONE


@dataclass(frozen=True)
class PatchTarget:
    """WHAT to patch under isolation: the program and its workspace, plus either a running `pid`
    or a guest `image` the backend boots: a disk (never written: the session runs on its own
    overlay or copy) or an installer .iso (booted with a new empty disk). `args` are extra
    launch arguments; the rest shape the guest."""

    exe: Path
    workspace: Path
    pid: int = 0
    image: Path | None = None
    args: tuple[str, ...] = ()
    memory_mb: int = 4096
    cpus: int = 2
    network: bool = False  # the boundary is closed unless the user opens it
    headless: bool = False
    halted: bool = False  # start stopped at the first instruction, to be resumed by the caller
    accel: str = ""  # "" = the backend picks one and says which
    fresh: bool = False  # discard the overlay disk an earlier session left
    efi: bool = False  # UEFI firmware (with a virtual TPM 2.0 where the tier has one)
    share: Path | None = None  # a host folder handed to the guest read-only (as a CD)
    gpu: bool = False  # 3D acceleration where the tier has it


class PatchSession(ABC):
    """A live handle on one isolated target. A live edit is atomic: suspend -> write_mem ->
    read_mem (verify) -> resume (see core.isolation.atomic_write). Each call that can be blocked
    returns a WallReport, so the caller is never left guessing; close() tears the session down."""

    @abstractmethod
    def suspend(self) -> None: ...

    @abstractmethod
    def resume(self) -> None: ...

    @abstractmethod
    def read_mem(self, addr: int, size: int) -> bytes:
        """`size` bytes at `addr`; b"" when the boundary cannot read it host-side (said by wall)."""

    @abstractmethod
    def write_mem(self, addr: int, data: bytes) -> WallReport:
        """Write `data` at `addr`; WallReport() on success, else which wall stopped it."""

    @abstractmethod
    def snapshot(self, name: str) -> Outcome:
        """Save the whole isolated state under `name` (for an iterative patch retry)."""

    @abstractmethod
    def rollback(self, name: str) -> Outcome:
        """Restore the state saved under `name`."""

    @abstractmethod
    def dump(self, out: Path) -> Outcome:
        """Write the target's in-memory image to `out` as a patchable file (feeds the cold arm)."""

    @abstractmethod
    def wall(self) -> WallReport:
        """The last wall this session hit (WallReport() when the last action landed)."""

    def physical(self):
        """A context manager over guest PHYSICAL memory with the guest stopped: it yields an
        object with read(pa, n) and write(pa, data), raising MemoryFault. None when this tier
        cannot reach physical memory (then no guest process can be addressed by itself)."""
        return None

    def cpu_paging(self) -> dict | None:
        """{"dtb", "mode"} of vCPU 0 now (its CR3 and paging mode), or None when unknown."""
        return None

    def record(self) -> dict:
        """What a later call needs to reach this session again; {} when it cannot be rejoined."""
        return {}

    def alive(self) -> bool:
        """Whether the isolated target still runs."""
        return True

    def release(self) -> None:
        """Let go of this handle's connections; the target keeps running."""

    def close(self) -> None:
        """Stop the target and release the boundary; safe to call more than once."""


class PatcherBackend(Backend):
    """A backend in an `isolation.<tier>` slot. It orchestrates a pinned VM / emulator / VMI tool
    as a separate process; `ready` says whether it can run here and, when not, which wall (its
    requirement); `start` boots the target and returns a live PatchSession."""

    families = frozenset({"isolation"})
    isolation = "subprocess"
    tier: int = 0
    requirement: str = ""  # the one-line requirement shown when the backend is not ready

    @abstractmethod
    def ready(self, os: "OS") -> WallReport:
        """WallReport() when this backend can run here, else Wall.NOT_READY + its requirement."""

    @abstractmethod
    def start(self, target: PatchTarget, ctx, *, snapshot: bool = False):
        """Boot `target` behind the boundary (take a base snapshot first when `snapshot`);
        returns a PatchSession, or an Outcome saying why it could not start."""

    def reattach(self, record: dict, ctx):
        """The PatchSession a `record()` describes, or an Outcome saying why it is gone."""
        return Outcome(OutcomeKind.UNAVAILABLE, error=f"{self.backend_id} cannot rejoin a session")

    def available(self, os: "OS") -> tuple[bool, str]:
        report = self.ready(os)
        return (not report.blocked, report.detail)
