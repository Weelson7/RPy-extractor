"""Signature carver: the last-resort extractor for files no plugin or unpacker recognizes.

It finds complete files embedded in any blob (custom archives, packed data files, saves,
executables in "all" mode) and writes each one out with its real suffix. Nothing is
decrypted or decompressed here: carved archives go back through the unpack loop.
"""

from __future__ import annotations

import mmap
import struct
from dataclasses import dataclass
from pathlib import Path

from viwo.contracts.slots import Carver
from viwo.contracts.types import Outcome, OutcomeKind

from . import formats as f
from . import formats2 as g

SIGNATURES = (  # (needle, offset of the file start relative to the needle, sizer)
    (b"\x89PNG\r\n\x1a\n", 0, f.png),
    (b"\xff\xd8\xff", 0, f.jpeg),
    (b"GIF8", 0, f.gif),
    (b"RIFF", 0, f.riff),
    (b"OggS", 0, f.ogg),
    (b"MThd", 0, f.midi),
    (b"ftyp", -4, f.mp4),
    (b"BIK", 0, g.bink),
    (b"KB2", 0, g.bink),
    (b"FSB5", 0, g.fsb5),
    (b"BKHD", 0, g.bnk),
    (b"DDS |", 0, g.dds),
    (b"glTF", 0, g.glb),
    (b"PK\x03\x04", 0, g.zip_file),
    (b"7z\xbc\xaf\x27\x1c", 0, g.seven_zip),
)
MIN_SIZE = 24
MAX_HITS = 200_000  # per needle: bounds the work on pathological inputs


@dataclass(frozen=True)
class Hit:
    offset: int
    size: int
    suffix: str


def _starts(m, end: int, cancel) -> list[tuple[int, object]]:
    starts = []
    for needle, delta, sizer in SIGNATURES:
        pos, count = m.find(needle), 0
        while pos >= 0 and count < MAX_HITS and not cancel.cancelled:
            if pos + delta >= 0:
                starts.append((pos + delta, sizer))
            pos, count = m.find(needle, pos + 1), count + 1
    starts.sort(key=lambda s: s[0])
    return starts


def scan(path: Path, cancel) -> list[Hit]:
    """Non-overlapping embedded files, outermost first (a PNG inside a zip stays in the zip)."""
    size = path.stat().st_size
    if size < MIN_SIZE:
        return []
    hits: list[Hit] = []
    with open(path, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as m:
        covered, cache = 0, {}
        for start, sizer in _starts(m, size, cancel):
            if start < covered or cancel.cancelled:
                continue
            try:
                found = (
                    sizer(m, start, size, cache) if sizer is g.zip_file else sizer(m, start, size)
                )
            except (
                IndexError,
                ValueError,
                OverflowError,
                struct.error,
            ):  # truncated structure: not a file
                found = None
            if found and found[0] >= MIN_SIZE and start + found[0] <= size:
                hits.append(Hit(start, found[0], found[1]))
                covered = start + found[0]
    return hits


def write_hits(path: Path, hits: list[Hit], dest: Path) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    with open(path, "rb") as src:
        for hit in hits:
            src.seek(hit.offset)
            with open(dest / f"{path.name}@{hit.offset:08x}{hit.suffix}", "wb") as out:
                remaining = hit.size
                while remaining:
                    chunk = src.read(min(1 << 20, remaining))
                    if not chunk:
                        break
                    out.write(chunk)
                    remaining -= len(chunk)
    return len(hits)


class SignatureCarver(Carver):
    """In-process carver (MIT, ours): PNG, JPEG, GIF, RIFF (WAV/WEM/AVI/WebP), Ogg/Opus,
    MIDI, MP4/MOV, Bink, FMOD FSB5, Wwise BNK, DDS, glTF binary, zip and 7z."""

    backend_id, license = "signature-carver", "MIT"

    def carve(self, path: Path, dest: Path, ctx) -> Outcome:
        try:
            hits = scan(path, ctx.cancel)
            return Outcome(OutcomeKind.OK, write_hits(path, hits, dest) if hits else 0)
        except (OSError, ValueError) as exc:
            return Outcome(OutcomeKind.FAILED, error=str(exc))
