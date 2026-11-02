"""Bethesda (Gamebryo / Creation Engine): BSA and BA2 archives."""

from __future__ import annotations

import mmap
import struct
import zlib
from pathlib import Path

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind
from viwo.contracts.workspace import safe_member

from .archives import ba2_files, bsa_data, bsa_entries

MANIFEST = PluginManifest(
    "bethesda", "Bethesda (BSA/BA2)", "0.1.0", engine_type="bethesda", priority=12
)
BSA, BA2 = b"BSA\0", b"BTDX"


def _write(dest: Path, name: str, data: bytes) -> int:
    rel = safe_member(name)
    if rel is None:
        return 0
    target = dest.joinpath(*rel.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return 1


def _mapped(archive: Path, read):
    """Run read(blob) over a read-only memory map (multi-GB archives are never loaded)."""
    with open(archive, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as blob:
        return read(blob)


class BsaBuiltin(Unarchiver):
    backend_id, owner, license = "bsa-builtin", "bethesda", "MIT"

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        def read(blob) -> tuple[int, int]:
            version, flags, entries = bsa_entries(blob)
            written, skipped = 0, 0
            for entry in entries:
                if ctx.cancel.cancelled:
                    break
                data = bsa_data(blob, version, flags, entry)
                if data is None:
                    skipped += 1
                else:
                    written += _write(dest, entry[0], data)
            return written, skipped

        try:
            written, skipped = _mapped(archive, read)
        except (OSError, ValueError, struct.error, zlib.error, IndexError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad BSA: {exc}")
        notes = (f"{skipped} LZ4 entries need the 'lz4' Python package",) if skipped else ()
        return Outcome(OutcomeKind.OK, written, notes=notes)


class Ba2Builtin(Unarchiver):
    backend_id, owner, license = "ba2-builtin", "bethesda", "MIT"

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        def read(blob) -> int:
            written = 0
            for name, data in ba2_files(blob):
                if ctx.cancel.cancelled:
                    break
                written += _write(dest, name, data)
            return written

        try:
            return Outcome(OutcomeKind.OK, _mapped(archive, read))
        except (OSError, ValueError, struct.error, zlib.error, IndexError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad BA2: {exc}")


SLOTS = (
    SlotDefinition(
        "unarchive.bsa", "unarchive", "bethesda", "bsa-builtin", suffixes=(".bsa",), magic=(BSA,)
    ),
    SlotDefinition(
        "unarchive.ba2", "unarchive", "bethesda", "ba2-builtin", suffixes=(".ba2",), magic=(BA2,)
    ),
)


class BethesdaPlugin(EnginePlugin):
    @property
    def manifest(self) -> PluginManifest:
        return MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        found = [
            p for p in probe.with_suffix(".bsa", ".ba2")[:40] if probe.head(p, 4) in (BSA, BA2)
        ]
        evidence = ("BSA/BA2 archives",) if found else ()
        if probe.with_suffix(".esm")[:1]:
            evidence += ("master plugin files (.esm)",)
        score = 0.9 if found else (0.5 if evidence else 0.0)
        return DetectionResult("bethesda", score, evidence, "bethesda")

    def slot_definitions(self):
        return SLOTS

    def backends(self):
        return (BsaBuiltin(), Ba2Builtin())
