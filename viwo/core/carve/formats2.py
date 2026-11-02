"""Sizers for game-specific media (Bink, FMOD, Wwise, DDS, glTF) and archives (zip, 7z)."""

from __future__ import annotations

import struct
import zlib

from .formats import U32

BLOCK8 = {b"DXT1", b"ATI1", b"BC4U", b"BC4S"}
BLOCK16 = {b"DXT2", b"DXT3", b"DXT4", b"DXT5", b"ATI2", b"BC5U", b"BC5S"}
DXGI = {n: 8 for n in (*range(70, 73), *range(79, 82))}  # BC1, BC4
DXGI |= {n: 16 for n in (*range(73, 79), *range(82, 85), *range(94, 100))}  # BC2/3/5/6/7
DXGI |= {
    n: -bpp
    for bpp, ids in (
        (4, (*range(27, 33), *range(87, 94))),
        (16, (2,)),
        (8, (10,)),
        (1, (61,)),
        (2, (49,)),
    )
    for n in ids
}
BNK_CHUNKS = {
    b"BKHD",
    b"DIDX",
    b"DATA",
    b"HIRC",
    b"STID",
    b"STMG",
    b"ENVS",
    b"PLAT",
    b"INIT",
    b"FXPR",
}


def bink(m, p: int, end: int):
    rev = m[p + 3 : p + 4]
    if rev not in (b"b", b"d", b"f", b"g", b"h", b"i", b"k", b"a", b"j"):
        return None
    size, frames = U32.unpack_from(m, p + 4)[0] + 8, U32.unpack_from(m, p + 8)[0]
    width, height = U32.unpack_from(m, p + 20)[0], U32.unpack_from(m, p + 24)[0]
    if not (0 < frames < 1_000_000 and 0 < width <= 8192 and 0 < height <= 8192) or p + size > end:
        return None
    return size, ".bk2" if m[p : p + 3] == b"KB2" else ".bik"


def fsb5(m, p: int, end: int):
    version, samples, headers, names, data = struct.unpack_from("<5I", m, p + 4)
    size = (64 if version == 0 else 60) + headers + names + data
    if version > 1 or not 0 < samples < 100_000 or p + size > end:
        return None
    return size, ".fsb"


def bnk(m, p: int, end: int):
    q, kinds = p, set()
    while q + 8 <= end and m[q : q + 4] in BNK_CHUNKS:
        kinds.add(bytes(m[q : q + 4]))
        q += 8 + U32.unpack_from(m, q + 4)[0]
    return (q - p, ".bnk") if len(kinds) >= 2 and q <= end else None


def _dds_layout(m, p: int) -> tuple[int, int]:
    """(bytes per 4x4 block, or minus bytes per pixel; header size). 0 when unknown."""
    fourcc = m[p + 84 : p + 88]
    if fourcc == b"DX10":
        return DXGI.get(U32.unpack_from(m, p + 128)[0], 0), 148
    if fourcc in BLOCK8 or fourcc in BLOCK16:
        return (8 if fourcc in BLOCK8 else 16), 128
    bits = U32.unpack_from(m, p + 88)[0]
    return (
        -(bits // 8) if not U32.unpack_from(m, p + 80)[0] & 4 and bits in (8, 16, 24, 32) else 0
    ), 128


def dds(m, p: int, end: int):
    if U32.unpack_from(m, p + 76)[0] != 32 or p + 128 > end:
        return None
    height, width, _, depth, mips = struct.unpack_from("<5I", m, p + 12)
    caps2 = U32.unpack_from(m, p + 112)[0]
    unit, header = _dds_layout(m, p)
    if not unit or not (0 < width <= 32768 and 0 < height <= 32768):
        return None
    faces = 6 if caps2 & 0x200 else 1
    depth = depth if caps2 & 0x200000 and depth else 1
    size = 0
    for level in range(max(1, min(mips, 16))):
        w, h, d = max(1, width >> level), max(1, height >> level), max(1, depth >> level)
        size += ((w + 3) // 4) * ((h + 3) // 4) * unit * d if unit > 0 else w * h * -unit * d
    size = header + size * faces
    return (size, ".dds") if p + size <= end else None


def glb(m, p: int, end: int):
    version, length = struct.unpack_from("<II", m, p + 4)
    if version != 2 or m[p + 16 : p + 20] != b"JSON" or p + length > end:
        return None
    return length, ".glb"


def zip_file(m, p: int, end: int, cache: dict):
    """A zip whose end-of-central-directory points back exactly at this local header."""
    if "eocd" not in cache:
        found, q = [], m.find(b"PK\x05\x06")
        while q >= 0 and len(found) < 4096:
            found.append(q)
            q = m.find(b"PK\x05\x06", q + 4)
        cache["eocd"] = found
    for e in cache["eocd"]:
        if e < p or e + 22 > end:
            continue
        cd_size, cd_offset = struct.unpack_from("<II", m, e + 12)
        if e - cd_size - cd_offset == p:
            return e + 22 + (m[e + 20] | m[e + 21] << 8) - p, ".zip"
    return None


def seven_zip(m, p: int, end: int):
    if zlib.crc32(m[p + 12 : p + 32]) != U32.unpack_from(m, p + 8)[0]:
        return None
    offset, size = struct.unpack_from("<QQ", m, p + 12)
    total = 32 + offset + size
    return (total, ".7z") if size and p + total <= end else None
