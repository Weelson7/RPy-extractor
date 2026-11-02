"""KiriKiri / KAG (Japanese visual novels): XP3 archives, versions 1 and 2.

Unencrypted archives unpack fully. Many commercial games add a per-title cipher on top
(flagged in the index): those entries are reported, not guessed at.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind
from viwo.contracts.workspace import safe_member

MAGIC = b"XP3\r\n \n\x1a\x8b\x67\x01"
ENCRYPTED = 0x80000000
MANIFEST = PluginManifest(
    "kirikiri", "KiriKiri (XP3)", "0.1.0", engine_type="kirikiri", priority=12
)


def _index(fh) -> bytes:
    fh.seek(11)
    (offset,) = struct.unpack("<Q", fh.read(8))
    if offset == 0x17:  # version 2: a small header points at the real index
        fh.seek(0x17 + 1 + 8)
        (offset,) = struct.unpack("<Q", fh.read(8))
    fh.seek(offset)
    flag = fh.read(1)[0]
    if flag & 7 == 1:
        packed, _ = struct.unpack("<QQ", fh.read(16))
        return zlib.decompress(fh.read(packed))
    (size,) = struct.unpack("<Q", fh.read(8))
    return fh.read(size)


def _chunks(blob: bytes, pos: int, end: int):
    while pos + 12 <= end:
        tag, size = blob[pos : pos + 4], struct.unpack_from("<Q", blob, pos + 4)[0]
        yield tag, pos + 12, size
        pos += 12 + size


def entries(index: bytes):
    """(name, encrypted, [(compressed, offset, original size, packed size)]) per file."""
    for tag, start, size in _chunks(index, 0, len(index)):
        if tag != b"File":
            continue
        name, encrypted, segments = "", False, []
        for sub, at, length in _chunks(index, start, start + size):
            if sub == b"info":
                flags, _, _, chars = struct.unpack_from("<IQQH", index, at)
                name = index[at + 22 : at + 22 + 2 * chars].decode("utf-16-le", "replace")
                encrypted = bool(flags & ENCRYPTED)
            elif sub == b"segm":
                segments = [
                    struct.unpack_from("<IQQQ", index, at + i) for i in range(0, length, 28)
                ]
        yield name, encrypted, [(f & 7 == 1, o, n, p) for f, o, n, p in segments]


class Xp3Builtin(Unarchiver):
    backend_id, owner, license = "xp3-builtin", "kirikiri", "MIT"

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        written, locked = 0, 0
        try:
            with open(archive, "rb") as fh:
                for name, encrypted, segments in list(entries(_index(fh))):
                    rel = safe_member(name)
                    if rel is None or ctx.cancel.cancelled:
                        continue
                    if encrypted:
                        locked += 1
                        continue
                    data = b""
                    for compressed, offset, _, packed in segments:
                        fh.seek(offset)
                        chunk = fh.read(packed)
                        data += zlib.decompress(chunk) if compressed else chunk
                    target = dest.joinpath(*rel.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    written += 1
        except (OSError, ValueError, struct.error, zlib.error, IndexError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad XP3: {exc}")
        if locked and not written:
            return Outcome(
                OutcomeKind.NEEDS_KEY, error=f"{locked} entries use a game-specific cipher"
            )
        notes = (f"{locked} encrypted entries skipped (game-specific cipher)",) if locked else ()
        return Outcome(OutcomeKind.OK, written, notes=notes)


SLOT = SlotDefinition(
    "unarchive.xp3", "unarchive", "kirikiri", "xp3-builtin", suffixes=(".xp3",), magic=(MAGIC,)
)


class KiriKiriPlugin(EnginePlugin):
    @property
    def manifest(self) -> PluginManifest:
        return MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        found = any(probe.head(p, 11) == MAGIC for p in probe.with_suffix(".xp3")[:20])
        evidence = ("XP3 archives",) if found else ()
        if probe.has_name("krkr.eXe".lower(), "tvpwin32.exe", "krkrz.exe"):
            evidence += ("KiriKiri runtime",)
        score = 0.9 if found else (0.6 if evidence else 0.0)
        return DetectionResult("kirikiri", score, evidence, "kirikiri")

    def slot_definitions(self):
        return (SLOT,)

    def backends(self):
        return (Xp3Builtin(),)
