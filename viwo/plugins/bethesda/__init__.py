"""Bethesda (Gamebryo / Creation Engine): BSA and BA2 archives; NIF models decoded
(decode.nif, nifmodels.py over nif.py)."""

import mmap
import struct
import zlib
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import SlotDefinition, Unarchiver
from viwo.contracts.types import DependencySpec, DetectionResult, Outcome, OutcomeKind

from .archives import ba2_files, bsa_data, bsa_entries

MANIFEST = PluginManifest(
    "bethesda", "Bethesda (BSA/BA2)", "0.1.0", engine_type="bethesda", priority=12
)
BSA, BA2 = b"BSA\0", b"BTDX"
LZ4 = DependencySpec(
    "lz4", "lz4 (Skyrim SE BSA)", kind="python", import_name="lz4", hint="pip install lz4"
)


def _write(names: ws.Names, name: str, data: bytes) -> int:
    target = names.target(name)
    if target is None:
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return 1


BAD = (OSError, ValueError, OverflowError, struct.error, zlib.error, IndexError)


def _bsa(blob, ctx):
    """(path, bytes or None without lz4) per file; a cancelled run reads no further entry."""
    version, flags, entries = bsa_entries(blob)
    for entry in entries:
        if ctx.cancel.cancelled:
            return
        yield entry[0], bsa_data(blob, version, flags, entry)


def _extract(archive: Path, dest: Path, ctx, what: str, members) -> Outcome:
    """Write what members(blob) yields over a read-only memory map (multi-GB archives are
    never loaded); an entry without data (LZ4 without the package) is counted and said."""
    names, written, skipped = ws.Names(dest), 0, 0
    try:
        with open(archive, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as blob:
            for name, data in members(blob):
                if ctx.cancel.cancelled:
                    break
                skipped += data is None
                written += _write(names, name, data) if data is not None else 0
    except BAD as exc:
        return Outcome(OutcomeKind.FAILED, error=f"bad {what}: {exc}")
    notes = (f"{skipped} LZ4 entries need the 'lz4' Python package",) if skipped else ()
    return Outcome(OutcomeKind.OK, written, notes=notes + names.save())


class BsaBuiltin(Unarchiver):
    backend_id, owner, license = "bsa-builtin", "bethesda", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    requires = (LZ4,)

    def available(self, os) -> tuple[bool, str]:
        return True, ""  # lz4 only unlocks version-105 entries; everything else works without it

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        return _extract(archive, dest, ctx, "BSA", lambda blob: _bsa(blob, ctx))


class Ba2Builtin(Unarchiver):
    backend_id, owner, license = "ba2-builtin", "bethesda", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        return _extract(archive, dest, ctx, "BA2", ba2_files)


SLOTS = (
    SlotDefinition(
        "unarchive.bsa", "unarchive", "bethesda", "bsa-builtin", suffixes=(".bsa",), magic=(BSA,)
    ),
    SlotDefinition(
        "unarchive.ba2", "unarchive", "bethesda", "ba2-builtin", suffixes=(".ba2",), magic=(BA2,)
    ),
)


class BethesdaPlugin(EnginePlugin):
    manifest = MANIFEST

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
        from .nifmodels import SLOT as NIF_SLOT
        from .pack import SLOTS as PACK_SLOTS

        return SLOTS + PACK_SLOTS + (NIF_SLOT,)

    def pack_slot(self, unarchive_slot: str) -> str:
        return {"unarchive.bsa": "pack.bsa", "unarchive.ba2": "pack.ba2"}.get(unarchive_slot, "")

    def backends(self):
        from .nifmodels import NifDecoder
        from .pack import LooseOverride

        return (BsaBuiltin(), Ba2Builtin(), LooseOverride(), NifDecoder())
