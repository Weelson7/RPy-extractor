"""Compressed streams inside unknown blobs, inflated with bounded memory: zlib and gzip always,
zstd and LZ4 frames when their modules are importable (doc 16.0b, ladder rung 4).

Custom archives often store each entry compressed. A stream counts only when it inflates to its
end without error; its output is then carved like any other buffer.
"""

from __future__ import annotations

import bisect
import zlib
from dataclasses import dataclass

ZLIB = ((b"\x78\x01", 15), (b"\x78\x5e", 15), (b"\x78\x9c", 15), (b"\x78\xda", 15))
GZIP = ((b"\x1f\x8b\x08", 31),)
ZSTD = ((b"\x28\xb5\x2f\xfd", "zstd"),)
LZ4 = ((b"\x04\x22\x4d\x18", "lz4"),)
CHUNK = 1 << 16
LIMIT = 64 << 20  # inflated bytes kept in memory per stream
MIN_OUT = 64
MAX_STREAMS = 50_000
TOTAL = 1 << 30  # inflated bytes per input file (zip-bomb guard)
TEXT_BYTES = frozenset(range(32, 127)) | {9, 10, 13}


def is_text(data: bytes) -> bool:
    return bool(data) and all(b in TEXT_BYTES for b in data[:4096])


@dataclass(frozen=True)
class Stream:
    offset: int
    consumed: int
    data: bytes


def decoder(kind):
    """A streaming decompressor with decompress(), eof and unused_data, or None when the
    optional module (zstandard, lz4) is not installed."""
    if isinstance(kind, int):
        return zlib.decompressobj(kind)
    try:
        if kind == "zstd":
            import zstandard  # optional

            return zstandard.ZstdDecompressor().decompressobj()
        import lz4.frame  # optional

        return lz4.frame.LZ4FrameDecompressor()
    except ImportError:
        return None


def heads() -> tuple[tuple[bytes, int | str], ...]:
    """The signatures worth scanning: optional kinds only when their decoder exists."""
    extra = tuple(h for h in ZSTD + LZ4 if decoder(h[1]) is not None)
    return ZLIB + GZIP + extra


def inflate(m, start: int, end: int, kind) -> Stream | None:
    d = decoder(kind)
    if d is None:
        return None
    pos, parts, total = start, [], 0
    try:
        while not d.eof and pos < end and total <= LIMIT:
            piece = d.decompress(m[pos : pos + CHUNK])
            pos += CHUNK
            parts.append(piece)
            total += len(piece)
    except Exception:  # zlib.error, zstd.ZstdError, lz4 RuntimeError: not a stream after all
        return None
    if not d.eof or total < MIN_OUT or total > LIMIT:
        return None
    consumed = min(pos, end) - start - len(d.unused_data or b"")
    return Stream(start, consumed, b"".join(parts))


def find_streams(m, size: int, taken: list[tuple[int, int]], cancel):
    """Yield streams outside the taken (offset, size) ranges, earliest first, one at a time
    (callers write and drop each), up to TOTAL inflated bytes per input file."""
    taken = sorted(taken)
    edges = [o for o, _ in taken]

    def free(pos: int) -> bool:
        i = bisect.bisect_right(edges, pos) - 1
        return i < 0 or pos >= taken[i][0] + taken[i][1]

    starts = sorted(
        (pos, kind) for head, kind in heads() for pos in _positions(m, head, cancel) if free(pos)
    )
    found, covered, total = 0, 0, 0
    for pos, kind in starts:
        if cancel.cancelled or found >= MAX_STREAMS or total > TOTAL:
            return
        if pos < covered:
            continue
        stream = inflate(m, pos, size, kind)
        if stream is not None:
            found, covered, total = found + 1, pos + stream.consumed, total + len(stream.data)
            yield stream


def _positions(m, head: bytes, cancel) -> list[int]:
    out, pos = [], m.find(head)
    while pos >= 0 and len(out) < 4 * MAX_STREAMS and not cancel.cancelled:
        out.append(pos)
        pos = m.find(head, pos + 1)
    return out
