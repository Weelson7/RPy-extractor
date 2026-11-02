"""Godot PCK identification (standalone and embedded) and unpack backends."""

from __future__ import annotations

import struct
from pathlib import Path

from viwo.contracts.slots import Match, Unarchiver
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

MAGIC = b"GDPC"
GDRE = DependencySpec(
    "gdre",
    "GDRE Tools",
    env_var="VIWO_GDRE",
    executables=("gdre_tools", "gdre_tools.x86_64"),
    install_dirs=("GDRE Tools", "gdre_tools"),
    hint="install GDRE Tools (MIT) from GDRETools/gdsdecomp",
)
PCKTOOL = DependencySpec(
    "godotpcktool",
    "GodotPckTool",
    env_var="VIWO_GODOTPCKTOOL",
    executables=("godotpcktool",),
    hint="install GodotPckTool (MIT); unencrypted PCKs only",
)


def embedded_chunk(path: Path, tail: bytes) -> tuple[int, int] | None:
    """(offset, size) of a PCK appended to an executable, from the GDPC trailer."""
    if len(tail) < 12 or tail[-4:] != MAGIC:
        return None
    (size,) = struct.unpack("<Q", tail[-12:-4])
    offset = path.stat().st_size - 12 - size
    if size <= 0 or offset < 0:
        return None
    with open(path, "rb") as fh:
        fh.seek(offset)
        return (offset, size) if fh.read(4) == MAGIC else None


def identify_pck(path: Path, head: bytes, tail: bytes) -> Match | None:
    if head.startswith(MAGIC):
        return Match("unarchive.pck", path)
    chunk = embedded_chunk(path, tail)
    return Match("unarchive.pck", path, chunk[0], chunk[1]) if chunk else None


def _files(dest: Path) -> int:
    return sum(1 for p in dest.rglob("*") if p.is_file())


class _PckCli(Unarchiver):
    spec: DependencySpec
    owner = "godot"

    def dependencies(self):
        return (self.spec,)

    def argv(self, archive: Path, dest: Path, key: str) -> list[str]:
        raise NotImplementedError

    def extract(self, archive, dest, ctx) -> Outcome:
        tool = ctx.os.tools.locate(self.spec)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=self.spec.hint)
        key = str(ctx.options.get("encryption_key", "") or "")
        result = ctx.os.process.run(
            [*tool.argv_prefix, *self.argv(archive, dest, key)], timeout=3600, cancel=ctx.cancel
        )
        text = (result.stderr or result.stdout).strip()
        if not result.ok:
            kind = OutcomeKind.NEEDS_KEY if "encrypt" in text.lower() else OutcomeKind.FAILED
            return Outcome(kind, error=text[-300:] or f"exit {result.returncode}")
        return Outcome(OutcomeKind.OK, _files(dest))


class GdreTools(_PckCli):
    backend_id, license, isolation, spec = "gdre-tools", "MIT", "subprocess", GDRE
    supports_keys = True

    def argv(self, archive: Path, dest: Path, key: str) -> list[str]:
        args = ["--headless", f"--extract={archive}", f"--output={dest}"]
        return args + ([f"--key={key}"] if key else [])


class GodotPckTool(_PckCli):
    backend_id, license, isolation, spec = "godotpcktool", "MIT", "subprocess", PCKTOOL

    def argv(self, archive: Path, dest: Path, key: str) -> list[str]:
        return ["--pack", str(archive), "--action", "extract", "--output", str(dest)]
