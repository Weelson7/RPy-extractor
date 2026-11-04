"""Godot PCK identification (standalone and embedded) and unpack backends."""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path

from viwo.contracts.slots import Exporter, Match, Packer, Unarchiver
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind
from viwo.contracts.workspace import count_files, stage_members

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


def pe_sections(head: bytes) -> list[str]:
    """Section names of a PE image from its first bytes (empty when it is not a PE)."""
    if len(head) < 0x40 or head[:2] != b"MZ":
        return []
    pe = struct.unpack_from("<I", head, 0x3C)[0]
    if pe + 24 > len(head) or head[pe : pe + 4] != b"PE\0\0":
        return []
    nsec = struct.unpack_from("<H", head, pe + 6)[0]
    start = pe + 24 + struct.unpack_from("<H", head, pe + 20)[0]
    names = []
    for i in range(nsec):
        if start + 40 * (i + 1) > len(head):
            break
        raw = head[start + 40 * i : start + 40 * i + 8].rstrip(b"\0")
        names.append(raw.decode("ascii", "replace"))
    return names


def godot_executable(head: bytes) -> bool:
    """A Godot export template: its PE carries the "pck" section the embed step fills."""
    return "pck" in pe_sections(head)


def identify_pck(path: Path, head: bytes, tail: bytes) -> Match | None:
    if head.startswith(MAGIC):
        return Match("unarchive.pck", path)
    chunk = embedded_chunk(path, tail)
    return Match("unarchive.pck", path, chunk[0], chunk[1]) if chunk else None


TOOL_NOISE = {"gdre_export.log"}


def _files(dest: Path) -> int:
    """Extracted files, without the tools' own logs."""
    for p in dest.rglob("*"):
        if p.is_file() and p.name in TOOL_NOISE:
            p.unlink()
    return count_files(dest)


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
            [*tool.argv_prefix, *self.argv(archive, dest, key)],
            timeout=3600,
            cancel=ctx.cancel,
            on_line=ctx.tool_output("unpack", mask=key),
        )
        text = (result.stderr or result.stdout).strip()
        if not result.ok:
            kind = OutcomeKind.NEEDS_KEY if "encrypt" in text.lower() else OutcomeKind.FAILED
            return Outcome(kind, error=text[-300:] or f"exit {result.returncode}")
        files = _files(dest)
        if not files:
            return Outcome(OutcomeKind.FAILED, error="the tool reported success but wrote no file")
        return Outcome(OutcomeKind.OK, files)


class GdreTools(_PckCli):
    backend_id, license, isolation, spec = "gdre-tools", "MIT", "subprocess", GDRE
    supports_keys = True

    def argv(self, archive: Path, dest: Path, key: str) -> list[str]:
        args = ["--headless", f"--extract={archive}", f"--output={dest}"]
        return args + ([f"--key={key}"] if key else [])


class GdreRecover(Exporter):
    """export.godot (doc 8.4): GDRE Tools recovers the project (scripts, scenes, resources)
    from the first PCK or the embedded PCK of the executable, into the plugin staging."""

    backend_id, owner, license, isolation = "gdre-recover", "godot", "MIT", "subprocess"

    requires = (GDRE,)

    def export(self, ctx) -> Outcome:
        tool = ctx.os.tools.locate(GDRE)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=GDRE.hint)
        target = _recover_target(ctx.game_root)
        if target is None:
            return Outcome(OutcomeKind.OK, 0, notes=("no PCK to recover",))
        argv = [*tool.argv_prefix, "--headless", f"--recover={target}", f"--output={ctx.staging}"]
        result = ctx.os.process.run(
            argv, timeout=3600, cancel=ctx.cancel, on_line=ctx.tool_output("export")
        )
        files = _files(ctx.staging)
        if not result.ok and not files:
            return Outcome(OutcomeKind.FAILED, error=(result.stderr or result.stdout)[-300:])
        return Outcome(OutcomeKind.OK, files)


def _recover_target(root: Path) -> Path | None:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".pck":
            return path
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 64))
            if embedded_chunk(path, fh.read(64)):
                return path
    return None


class GodotPckTool(_PckCli):
    backend_id, license, isolation, spec = "godotpcktool", "MIT", "subprocess", PCKTOOL

    def argv(self, archive: Path, dest: Path, key: str) -> list[str]:
        return ["--pack", str(archive), "--action", "extract", "--output", str(dest)]


class GodotPckPacker(Packer):
    """Round trip: GodotPckTool adds (replaces) the edited files inside the copied PCK."""

    backend_id, owner, license, isolation = "godotpcktool-pack", "godot", "MIT", "subprocess"

    requires = (PCKTOOL,)

    def pack(self, container, members, ctx) -> Outcome:
        tool = ctx.os.tools.locate(PCKTOOL)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=PCKTOOL.hint)
        ctx.scratch.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix="pck-", dir=ctx.scratch))  # one per pack call
        staged = stage_members(members, root)
        argv = [*tool.argv_prefix, "--pack", str(container), "--action", "add"]
        argv += ["--remove-prefix", str(root), *map(str, staged)]
        result = ctx.os.process.run(
            argv, timeout=3600, cancel=ctx.cancel, on_line=ctx.tool_output("pack")
        )
        if not result.ok:
            return Outcome(OutcomeKind.FAILED, error=(result.stderr or result.stdout)[-300:])
        return Outcome(OutcomeKind.OK, len(staged))
