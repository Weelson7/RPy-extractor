"""pack.archive (doc 18, 16.0c): edited Cyberpunk 2077 members packed into an override archive in
the patched copy's `archive/pc/mod/`, which the game loads over its own archives, through
WolvenKit's console (GPL-3.0, its own process). A member known by name is packed under its path
(the game hashes it with backslashes); one known only by its hash is staged as `<decimal>.<ext>`,
the name WolvenKit keeps the hash of. The archive is read back and every edited member compared."""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from viwo.contracts.slots import Packer, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind
from viwo.contracts.workspace import safe_member

from .export import WOLVENKIT
from .names import fnv1a64
from .rdar import Archive, Oodle

SLOT = SlotDefinition("pack.archive", "pack", "redengine", "wolvenkit-pack")
HASHED = re.compile(r"^([0-9a-f]{16})(\.[^/]+)$")
PREFIX = "!viwo_"  # mods load in name order and the first one wins: ViWo's edits come first


def member_hash(member: str) -> int:
    hashed = HASHED.match(member)
    if hashed:
        return int(hashed.group(1), 16)
    return fnv1a64(member.replace("/", "\\").encode("utf-8"))


def stage(members: dict[str, Path], root: Path) -> int:
    """Copy the edited members where WolvenKit packs them from; unsafe names are skipped."""
    staged = 0
    for member, source in members.items():
        hashed = HASHED.match(member)
        rel = Path(f"{int(hashed.group(1), 16)}{hashed.group(2)}") if hashed else None
        rel = rel or safe_member(member)
        if rel is not None:
            target = root.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            staged += 1
    return staged


class WolvenKitPack(Packer):
    backend_id, owner, license, isolation = "wolvenkit-pack", "redengine", "GPL-3.0", "subprocess"
    requires = (WOLVENKIT,)
    override = True

    def output_for(self, container: Path) -> Path:
        mods = container.parent.parent / "mod"  # archive/pc/content -> archive/pc/mod
        return mods / f"{PREFIX}{container.stem}.archive"

    def pack(self, container, members, ctx) -> Outcome:
        tool = ctx.os.tools.locate(WOLVENKIT)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=WOLVENKIT.hint)
        ctx.scratch.mkdir(parents=True, exist_ok=True)
        out = self.output_for(container)
        root = Path(tempfile.mkdtemp(prefix="rdar-", dir=ctx.scratch)) / out.stem  # its name
        staged = stage(members, root)
        out.parent.mkdir(parents=True, exist_ok=True)
        result = ctx.os.process.run(
            [*tool.argv_prefix, "pack", str(root), "-o", str(out.parent), "-v", "Minimal"],
            cwd=str(root.parent),
            timeout=3600,
            cancel=ctx.cancel,
        )
        if not result.ok or not out.is_file():
            said = (result.stderr or result.stdout).strip()[-300:]
            return Outcome(OutcomeKind.FAILED, error=said or "WolvenKit wrote no archive")
        note = f"{out.name}: loaded over {container.name} (archive/pc/mod)"
        return Outcome(OutcomeKind.OK, staged, notes=(note,))

    def verify(self, output: Path, members: dict[str, Path], ctx):
        """The edited members whose packed bytes, read back, differ from the edit."""
        oodle = Oodle.beside(output, ctx.os)
        scratch = Path(tempfile.mkdtemp(prefix="rdar-check-", dir=ctx.scratch))
        bad = []
        with open(output, "rb") as fh:
            archive = Archive(fh)
            entries = {e.name_hash: e for e in archive.entries()}
            for i, (member, source) in enumerate(members.items()):
                entry, target = entries.get(member_hash(member)), scratch / f"{i}.member"
                if entry is None or not archive.write(entry, scratch, oodle, target.name):
                    bad.append(member)
                elif not target.is_file() or target.read_bytes() != source.read_bytes():
                    bad.append(member)
        shutil.rmtree(scratch, ignore_errors=True)
        return bad
