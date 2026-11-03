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
from .streams import Stream, find_streams, is_text

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


def scan_buffer(m, size: int, cancel) -> list[Hit]:
    """Non-overlapping embedded files, outermost first (a PNG inside a zip stays in the zip)."""
    hits: list[Hit] = []
    covered, cache = 0, {}
    for start, sizer in _starts(m, size, cancel):
        if start < covered or cancel.cancelled:
            continue
        try:
            found = sizer(m, start, size, cache) if sizer is g.zip_file else sizer(m, start, size)
        except (IndexError, ValueError, OverflowError, struct.error):  # truncated: not a file
            found = None
        if found and found[0] >= MIN_SIZE and start + found[0] <= size:
            hits.append(Hit(start, found[0], found[1]))
            covered = start + found[0]
    return hits


def scan(path: Path, cancel) -> list[Hit]:
    size = path.stat().st_size
    if size < MIN_SIZE:
        return []
    with open(path, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as m:
        return scan_buffer(m, size, cancel)


def _copy(src, hit: Hit, target: Path) -> None:
    src.seek(hit.offset)
    with open(target, "wb") as out:
        remaining = hit.size
        while remaining:
            chunk = src.read(min(1 << 20, remaining))
            if not chunk:
                break
            out.write(chunk)
            remaining -= len(chunk)


def _write_stream(stream: Stream, stem: str, dest: Path, cancel) -> int:
    """An inflated stream: one known file, the files inside it, or raw data (.txt/.bin)."""
    data, at = stream.data, f"{stem}@{stream.offset:08x}"
    inner = scan_buffer(data, len(data), cancel)
    if len(inner) == 1 and inner[0].offset == 0 and inner[0].size == len(data):
        (dest / f"{at}{inner[0].suffix}").write_bytes(data)
        return 1
    for hit in inner:
        part = data[hit.offset : hit.offset + hit.size]
        (dest / f"{at}+{hit.offset:08x}{hit.suffix}").write_bytes(part)
    if not inner:
        (dest / f"{at}{'.txt' if is_text(data) else '.bin'}").write_bytes(data)
    return max(1, len(inner))


def count_embedded(path: Path, cancel) -> int:
    """How many embedded files and compressed streams a file holds (nothing is written)."""
    size = path.stat().st_size
    if size < MIN_SIZE:
        return 0
    with open(path, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as m:
        hits = scan_buffer(m, size, cancel)
        streams = find_streams(m, size, [(h.offset, h.size) for h in hits], cancel)
        return len(hits) + sum(1 for _ in streams)


def carve_file(path: Path, dest: Path, cancel) -> int:
    """Embedded files, then compressed streams in the gaps; returns files written."""
    size = path.stat().st_size
    if size < MIN_SIZE:
        return 0
    with open(path, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as m:
        hits = scan_buffer(m, size, cancel)
        dest.mkdir(parents=True, exist_ok=True)
        for hit in hits:
            _copy(fh, hit, dest / f"{path.name}@{hit.offset:08x}{hit.suffix}")
        streams = find_streams(m, size, [(h.offset, h.size) for h in hits], cancel)
        written = len(hits) + sum(_write_stream(s, path.name, dest, cancel) for s in streams)
    if not written:
        dest.rmdir()
    return written


class SignatureCarver(Carver):
    """In-process carver (MIT, ours): PNG, JPEG, GIF, RIFF (WAV/WEM/AVI/WebP), Ogg/Opus,
    MIDI, MP4/MOV, Bink, FMOD FSB5, Wwise BNK, DDS, glTF binary, zip and 7z; plus zlib and
    gzip streams, inflated and carved in turn."""

    backend_id, license = "signature-carver", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def carve(self, path: Path, dest: Path, ctx) -> Outcome:
        try:
            return Outcome(OutcomeKind.OK, carve_file(path, dest, ctx.cancel))
        except (OSError, ValueError) as exc:
            return Outcome(OutcomeKind.FAILED, error=str(exc))
