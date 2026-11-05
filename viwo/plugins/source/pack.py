"""pack.vpk (doc 18): edited members of a VPK set written as an override VPK the Source engine
loads first, `<mod folder>/custom/!viwo_<set>.vpk` (version 1, a single file: every member
inline, no parts), so a
30 GB set is never rebuilt for one edit and the original parts stay as they are. The override
holds the edits only; it is read back after writing."""

from __future__ import annotations

import binascii
import struct
from collections import defaultdict
from pathlib import Path

from viwo.contracts.slots import Packer, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

SLOT = SlotDefinition("pack.vpk", "pack", "source", "vpk-writer")
PREFIX = "!viwo_"  # sorts before the names a user drops into custom/


def _split(member: str) -> tuple[str, str, str]:
    """(extension, folder, name) as the VPK tree stores them (" " for an empty part)."""
    folder, _, leaf = member.replace("\\", "/").rpartition("/")
    name, dot, ext = leaf.rpartition(".")
    if not dot:
        name, ext = leaf, ""
    return ext.lower() or " ", folder.lower() or " ", name.lower()


def write_vpk(members: dict[str, bytes], target: Path) -> None:
    """A version-1 VPK directory with every member inline (archive index 0x7FFF)."""
    grouped: dict[str, dict[str, list[tuple[str, bytes]]]] = defaultdict(lambda: defaultdict(list))
    for member, data in sorted(members.items()):
        ext, folder, name = _split(member)
        grouped[ext][folder].append((name, data))
    tree, body = bytearray(), bytearray()
    for ext, folders in grouped.items():
        tree += ext.encode() + b"\0"
        for folder, files in folders.items():
            tree += folder.encode() + b"\0"
            for name, data in files:
                crc = binascii.crc32(data) & 0xFFFFFFFF
                tree += name.encode() + b"\0"
                tree += struct.pack("<IHHIIH", crc, 0, 0x7FFF, len(body), len(data), 0xFFFF)
                body += data
            tree += b"\0"
        tree += b"\0"
    tree += b"\0"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(struct.pack("<III", 0x55AA1234, 1, len(tree)) + bytes(tree) + bytes(body))


class VpkWriter(Packer):
    backend_id, owner, license = "vpk-writer", "source", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: the read-back parses the written VPK
    override = True  # the override holds the edits; the set it loads over keeps the rest

    def output_for(self, container: Path) -> Path:
        stem = container.name[: -len("_dir.vpk")] if container.name.endswith("_dir.vpk") else ""
        return container.parent / "custom" / f"{PREFIX}{stem or container.stem}.vpk"  # one file

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        target = self.output_for(container)
        try:
            write_vpk({m: p.read_bytes() for m, p in members.items()}, target)
        except (OSError, ValueError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"override VPK not written: {exc}"[:300])
        note = f"edits in {target.parent.name}/{target.name}, loaded before the game's own VPKs"
        return Outcome(OutcomeKind.OK, len(members), notes=(note,))

    def verify(self, output: Path, members: dict[str, Path], ctx) -> list[str]:
        """Every edit read back from the override, byte for byte (paths as the engine sees
        them: lower case)."""
        from . import tree

        blob = output.read_bytes()
        entries, base = tree(blob)
        found = {path: blob[base + off : base + off + size] for path, _, _, off, size in entries}
        return sorted(
            m
            for m, p in members.items()
            if found.get(m.lower().replace("\\", "/")) != p.read_bytes()
        )
