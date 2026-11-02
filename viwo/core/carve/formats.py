"""Sizers for embedded files: each walks its format's own structure from a signature hit.

A sizer gets (buffer, start, end) and returns (size, suffix) or None. Validation is strict
(chunk walks, CRCs, back-references) so random bytes that happen to match are rejected.
"""

from __future__ import annotations

import struct
import zlib

U32, U32BE, U16BE = struct.Struct("<I"), struct.Struct(">I"), struct.Struct(">H")


def _ogg_table() -> list[int]:
    table = []
    for i in range(256):
        r = i << 24
        for _ in range(8):
            r = ((r << 1) ^ 0x04C11DB7) if r & 0x80000000 else r << 1
        table.append(r & 0xFFFFFFFF)
    return table


OGG_CRC = _ogg_table()


def png(m, p: int, end: int):
    if (
        m[p + 8 : p + 16] != b"\x00\x00\x00\rIHDR"
        or zlib.crc32(m[p + 12 : p + 29]) != U32BE.unpack_from(m, p + 29)[0]
    ):
        return None
    q = p + 8
    while q + 12 <= end:
        (n,) = U32BE.unpack_from(m, q)
        kind = m[q + 4 : q + 8]
        if not kind.isalpha():
            return None
        q += 12 + n
        if kind == b"IEND":
            return (q - p, ".png") if q <= end else None
    return None


def _scan_entropy(m, q: int, end: int) -> int:
    """Skip entropy-coded data after SOS: stop at the first real marker."""
    while True:
        q = m.find(b"\xff", q, end)
        if q < 0 or q + 1 >= end:
            return -1
        nxt = m[q + 1]
        if nxt == 0 or 0xD0 <= nxt <= 0xD7:
            q += 2
        elif nxt == 0xFF:
            q += 1
        else:
            return q


def jpeg(m, p: int, end: int):
    if m[p + 3] not in (0xE0, 0xE1, 0xE2, 0xDB, 0xC0, 0xC2, 0xC4, 0xEE, 0xFE):
        return None
    q, scans = p + 2, 0
    while q + 4 <= end:
        if m[q] != 0xFF:
            return None
        marker = m[q + 1]
        if marker == 0xD9:
            return (q + 2 - p, ".jpg") if scans and q + 2 - p >= 256 else None
        (n,) = U16BE.unpack_from(m, q + 2)
        if n < 2:
            return None
        q += 2 + n
        if marker == 0xDA:
            scans += 1
            q = _scan_entropy(m, q, end)
            if q < 0:
                return None
    return None


def _sub_blocks(m, q: int, end: int) -> int:
    while q < end and m[q]:
        q += m[q] + 1
    return q + 1


def gif(m, p: int, end: int):
    if m[p + 4 : p + 6] not in (b"7a", b"9a"):
        return None
    flags = m[p + 10]
    q = p + 13 + (3 << ((flags & 7) + 1) if flags & 0x80 else 0)
    while q < end:
        block = m[q]
        if block == 0x3B:
            return q + 1 - p, ".gif"
        if block == 0x21:
            q = _sub_blocks(m, q + 2, end)
        elif block == 0x2C and q + 10 < end:
            local = m[q + 9]
            q += 10 + (3 << ((local & 7) + 1) if local & 0x80 else 0)
            q = _sub_blocks(m, q + 1, end)
        else:
            return None
    return None


RIFF_FORMS = {b"WAVE": ".wav", b"AVI ": ".avi", b"WEBP": ".webp", b"RMID": ".rmi"}
PCM_TAGS = {1, 2, 3, 6, 7, 0x11, 0x55}


def riff(m, p: int, end: int):
    form = m[p + 8 : p + 12]
    size = U32.unpack_from(m, p + 4)[0] + 8
    if form not in RIFF_FORMS or size < 16 or p + size > end:
        return None
    suffix = RIFF_FORMS[form]
    if form == b"WAVE" and m[p + 12 : p + 16] == b"fmt ":
        tag = m[p + 20] | m[p + 21] << 8
        suffix = ".wav" if tag in PCM_TAGS else ".wem"  # Wwise and other codecs
    return size + (size & 1 if p + size < end else 0), suffix


def _ogg_crc_ok(page: bytes) -> bool:
    crc = 0
    for i, byte in enumerate(page):
        byte = 0 if 22 <= i < 26 else byte
        crc = ((crc << 8) & 0xFFFFFFFF) ^ OGG_CRC[((crc >> 24) ^ byte) & 0xFF]
    return crc == U32.unpack_from(page, 22)[0]


def ogg(m, p: int, end: int):
    q, open_streams, first = p, set(), None
    while q + 27 <= end and m[q : q + 4] == b"OggS" and m[q + 4] == 0:
        flags, serial, segs = m[q + 5], U32.unpack_from(m, q + 14)[0], m[q + 26]
        body = sum(m[q + 27 : q + 27 + segs])
        size = 27 + segs + body
        if first is None:
            if not flags & 2 or q + size > end or not _ogg_crc_ok(m[q : q + size]):
                return None
            first = bytes(m[q + 27 + segs : q + 27 + segs + 8])
        open_streams.add(serial) if flags & 2 else None
        q += size
        if flags & 4:
            open_streams.discard(serial)
            if not open_streams:
                break
    if first is None or q > end:
        return None
    return q - p, ".opus" if first.startswith(
        b"OpusHead"
    ) else ".ogv" if b"theora" in first else ".ogg"


def midi(m, p: int, end: int):
    if U32BE.unpack_from(m, p + 4)[0] != 6:
        return None
    tracks, q = U16BE.unpack_from(m, p + 10)[0], p + 14
    for _ in range(tracks):
        if m[q : q + 4] != b"MTrk":
            return None
        q += 8 + U32BE.unpack_from(m, q + 4)[0]
    return (q - p, ".mid") if tracks and q <= end else None


MP4_ATOMS = {b"ftyp", b"moov", b"mdat", b"free", b"skip", b"wide", b"uuid", b"moof", b"mfra"}
MP4_ATOMS |= {b"styp", b"sidx", b"pdin", b"meta", b"udta"}


def mp4(m, p: int, end: int):
    q, seen = p, set()
    while q + 8 <= end and m[q + 4 : q + 8] in MP4_ATOMS:
        size = U32BE.unpack_from(m, q)[0]
        size = (
            struct.unpack_from(">Q", m, q + 8)[0] if size == 1 else (end - q if size == 0 else size)
        )
        if size < 8 or q + size > end:
            break
        seen.add(m[q + 4 : q + 8])
        q += size
    if not {b"moov", b"moof"} & seen:
        return None
    brand = m[p + 8 : p + 12]
    return q - p, ".mov" if brand == b"qt  " else ".m4a" if brand == b"M4A " else ".mp4"
