"""Warscape (Total War: Empire through Rome II / Attila / Warhammer): PFH pack archives.

Header: magic PFH4/PFH5/PFH6, pack type, dependency count and index size, file count and
index size, timestamp. Index entries: u32 size (+ u32 timestamp when the type carries the
0x40 bit, as boot.pack does), zero-terminated path; the file data follows the index in entry
order, uncompressed. An encrypted index (0x80) is reported, not guessed.
"""

import struct
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind
from viwo.contracts.workspace import count_files

from .db import GAMES, DbBuiltin
from .db import SLOT as DB_SLOT
from .loc import SLOT as LOC_SLOT
from .loc import LocBuiltin
from .pack import SLOT as PACK_SLOT
from .pack import MoviePack

MAGICS = (b"PFH4", b"PFH5", b"PFH6")
HEADER = 28
TIMESTAMPS, ENCRYPTED_INDEX = 0x40, 0x80  # pack type bits (RPFM's names)
LIMIT = 1 << 31
MANIFEST = PluginManifest(
    "warscape", "Warscape (Total War)", "0.1.0", engine_type="warscape", priority=10
)
MARKERS = tuple(f"{exe}.exe" for exe in GAMES)  # every Warscape game ViWo has a schema for


def entries(fh):
    """(path, offset, size) per member: the index, then sequential data."""
    head = fh.read(HEADER)
    if head[:4] not in MAGICS:
        raise ValueError("not a PFH pack")
    kind, deps, deps_size, count, index_size, _stamp = struct.unpack_from("<6I", head, 4)
    if kind & ENCRYPTED_INDEX:
        raise ValueError("encrypted index")
    if count > 1 << 22 or index_size > 1 << 28:
        raise ValueError("index out of range")
    fh.seek(HEADER + deps_size)
    index = fh.read(index_size)
    pos, data_at, out = 0, HEADER + deps_size + index_size, []
    for _ in range(count):
        (size,) = struct.unpack_from("<I", index, pos)
        pos += 8 if kind & TIMESTAMPS else 4
        end = index.index(b"\0", pos)
        name = index[pos:end].decode("utf-8", "replace").replace("\\", "/")
        pos = end + 1
        if size > LIMIT:
            raise ValueError("member size out of range")
        out.append((name, data_at, size))
        data_at += size
    return out


class PackBuiltin(Unarchiver):
    backend_id, owner, license = "pack-builtin", "warscape", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        names, cut = ws.Names(dest), 0
        try:
            with open(archive, "rb") as fh:
                for name, offset, size in entries(fh):
                    if ctx.cancel.cancelled:
                        break
                    target = names.target(name)
                    if target is None:
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    fh.seek(offset)
                    with open(target, "wb") as out:
                        for left in range(size, 0, -(1 << 20)):
                            out.write(block := fh.read(min(left, 1 << 20)))
                            if len(block) < min(left, 1 << 20):
                                cut += 1  # the pack ends inside this member
                                break
        except (OSError, ValueError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad pack: {exc}")
        files = count_files(dest)
        notes = (f"{cut} member(s) cut short (the pack ends early)",) if cut else ()
        return Outcome(OutcomeKind.OK, files, notes=names.save() + notes)


class WarscapePlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        if any(probe.head(p, 4) in MAGICS for p in probe.with_suffix(".pack")[:10]):
            evidence.append("PFH pack archives")
        if probe.has_name(*MARKERS):
            evidence.append("Total War executable")
        score = 0.9 if len(evidence) == 2 else 0.7 if evidence else 0.0
        return DetectionResult("warscape", score, tuple(evidence), "warscape")

    def slot_definitions(self):
        return (
            SlotDefinition(
                "unarchive.pack",
                "unarchive",
                "warscape",
                "pack-builtin",
                suffixes=(".pack",),
                magic=MAGICS,
            ),
            LOC_SLOT,
            DB_SLOT,
            PACK_SLOT,
        )

    def export_slot(self) -> str:
        return "export.warscape"

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.pack" if unarchive_slot == "unarchive.pack" else ""

    def backends(self):
        return (PackBuiltin(), LocBuiltin(), DbBuiltin(), MoviePack())
