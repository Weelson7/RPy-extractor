"""Genie engine (Age of Empires I/II, HD editions): DRS resource archives.

A DRS is a flat container: tables per extension (the extension is stored reversed, " pls"),
then (id, offset, size) per file. Members come out as `<id>.<ext>` (slp, wav, bina, shp).
"""

import struct
from pathlib import Path

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind
from viwo.contracts.workspace import count_files

from .pack import SLOT as PACK_SLOT
from .pack import DrsWriter
from .slp import SLP_SLOT, SlpDecoder

MAGIC = b"Copyright (c) 1997 Ensemble Studios."
HEADER = 56  # copyright 40 + version 4 + file type 12; then table count + first file offset
LIMIT = 1 << 31
MANIFEST = PluginManifest(
    "genie", "Genie (Age of Empires)", "0.1.0", engine_type="genie", priority=10
)


def entries(fh):
    """(name, offset, size) for every member of a DRS file."""
    head = fh.read(HEADER + 8)
    if not head.startswith(MAGIC):
        raise ValueError("not a DRS file")
    tables, _first = struct.unpack_from("<II", head, HEADER)
    if not 0 < tables < 64:
        raise ValueError("table count out of range")
    specs = [struct.unpack("<4sII", fh.read(12)) for _ in range(tables)]
    for kind, offset, count in specs:
        raw = kind[::-1].decode("ascii", "replace")  # " pls" -> slp, "anib" -> bina
        ext = "".join(c for c in raw if c.isascii() and c.isalnum()) or "bin"
        if count > 1 << 20:
            raise ValueError("file count out of range")
        fh.seek(offset)
        for _ in range(count):
            file_id, at, size = struct.unpack("<III", fh.read(12))
            if not 0 <= size < LIMIT:
                raise ValueError("member size out of range")
            yield f"{file_id}.{ext}", at, size


class DrsBuiltin(Unarchiver):
    backend_id, owner, license = "drs-builtin", "genie", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        try:
            with open(archive, "rb") as fh:
                for name, offset, size in list(entries(fh)):
                    if ctx.cancel.cancelled:
                        break
                    fh.seek(offset)
                    (dest / name).write_bytes(fh.read(size))
        except (OSError, ValueError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad DRS: {exc}")
        return Outcome(OutcomeKind.OK, count_files(dest))


class GeniePlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        """The engine's own signature (doc 2.10): DRS archives, never a title's executable."""
        drs = any(probe.head(p, len(MAGIC)) == MAGIC for p in probe.with_suffix(".drs")[:10])
        evidence = ("DRS resource archives",) if drs else ()
        return DetectionResult("genie", 0.85 if drs else 0.0, evidence, "genie")

    def slot_definitions(self):
        return (
            SlotDefinition(
                "unarchive.drs",
                "unarchive",
                "genie",
                "drs-builtin",
                suffixes=(".drs",),
                magic=(MAGIC,),
            ),
            SLP_SLOT,
            PACK_SLOT,
        )

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.drs" if unarchive_slot == "unarchive.drs" else ""

    def backends(self):
        return (DrsBuiltin(), SlpDecoder(), DrsWriter())
