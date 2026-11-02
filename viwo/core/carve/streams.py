"""Compressed streams inside unknown blobs: zlib and gzip, inflated with bounded memory.

Custom archives often store each entry zlib-compressed. A stream counts only when it
inflates to its end without error; its output is then carved like any other buffer.
"""

from __future__ import annotations

import bisect
import zlib
from dataclasses import dataclass

HEADS = ((b"\x78\x01", 15), (b"\x78\x5e", 15), (b"\x78\x9c", 15), (b"\x78\xda", 15))
HEADS += ((b"\x1f\x8b\x08", 31),)
CHUNK = 1 << 16
LIMIT = 64 << 20  # inflated bytes kept in memory per stream
MIN_OUT = 64
MAX_STREAMS = 50_000
TEXT_BYTES = frozenset(range(32, 127)) | {9, 10, 13}


def is_text(data: bytes) -> bool:
    return bool(data) and all(b in TEXT_BYTES for b in data[:4096])


@dataclass(frozen=True)
class Stream:
    offset: int
    consumed: int
    data: bytes


def inflate(m, start: int, end: int, wbits: int) -> Stream | None:
    d, pos, parts, total = zlib.decompressobj(wbits), start, [], 0
    try:
        while not d.eof and pos < end and total <= LIMIT:
            piece = d.decompress(m[pos : pos + CHUNK])
            pos += CHUNK
            parts.append(piece)
            total += len(piece)
    except zlib.error:
        return None
    if not d.eof or total < MIN_OUT or total > LIMIT:
        return None
    consumed = min(pos, end) - start - len(d.unused_data)
    return Stream(start, consumed, b"".join(parts))


def find_streams(m, size: int, taken: list[tuple[int, int]], cancel) -> list[Stream]:
    """Streams outside the taken (offset, size) ranges, earliest first, non-overlapping."""
    taken = sorted(taken)
    edges = [o for o, _ in taken]

    def free(pos: int) -> bool:
        i = bisect.bisect_right(edges, pos) - 1
        return i < 0 or pos >= taken[i][0] + taken[i][1]

    starts = sorted(
        (pos, wbits) for head, wbits in HEADS for pos in _positions(m, head, cancel) if free(pos)
    )
    found, covered = [], 0
    for pos, wbits in starts:
        if pos < covered or cancel.cancelled or len(found) >= MAX_STREAMS:
            continue
        stream = inflate(m, pos, size, wbits)
        if stream is not None:
            found.append(stream)
            covered = pos + stream.consumed
    return found


def _positions(m, head: bytes, cancel) -> list[int]:
    out, pos = [], m.find(head)
    while pos >= 0 and len(out) < 4 * MAX_STREAMS and not cancel.cancelled:
        out.append(pos)
        pos = m.find(head, pos + 1)
    return out
