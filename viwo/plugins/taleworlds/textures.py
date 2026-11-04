"""Bannerlord TPAC textures to DDS. A texture item's metadata ends with the full-size shape,
then the pixel format as a length-prefixed name: u32 width, u32 height, u32 depth, u8 mip count,
u16, u32 name length, the name (DXT1, BC7, R8_UNORM...). Its largest data segment is that chain
from some mip level down (the top levels can stream from elsewhere): the level whose chain is
exactly the segment's size gives the stored width, height and mips, so the segment becomes a
standard DDS (DX10 header when no FourCC or legacy format names it).
Layout and formats measured on the Native module's 150 packages (2026-11-04)."""

from __future__ import annotations

import re
import struct

TEXTURE = bytes.fromhex("cbcb74c91c5ff6499a322b5b6c92c2e8")  # the texture asset type GUID
# name -> (DXGI format, bytes per block or pixel, block edge, legacy FourCC); R8 and RGBA8 use
# the legacy uncompressed header (LEGACY) that every DDS reader takes
FORMATS = {
    "DXT1": (71, 8, 4, b"DXT1"),
    "DXT3": (74, 16, 4, b"DXT3"),
    "DXT5": (77, 16, 4, b"DXT5"),
    "BC4": (80, 8, 4, None),
    "BC5": (83, 16, 4, None),
    "BC6H_UF16": (95, 16, 4, None),
    "BC7": (98, 16, 4, None),
    "R8_UNORM": (61, 1, 1, None),
    "R16_UNORM": (56, 2, 1, None),
    "R16G16F": (34, 4, 1, None),
    "R8G8B8A8_UNORM": (28, 4, 1, None),
    "R16G16B16A16F": (10, 8, 1, None),
}
LEGACY = {  # name -> (pixel format flags, bit count, R, G, B, A masks)
    "R8_UNORM": (0x20000, 8, 0xFF, 0, 0, 0),
    "R8G8B8A8_UNORM": (0x41, 32, 0xFF, 0xFF00, 0xFF0000, 0xFF000000),
}
CUBE_TAG = b"is_cubemap"  # a cubemap's chain is six faces, each a full chain, face after face
NAME = re.compile(rb"([\x02-\x14])\x00\x00\x00([A-Z0-9_]{2,20})")


def pixel_format(meta: bytes) -> tuple[str, int]:
    """(the known format name, where its length prefix starts) or ("", -1)."""
    for match in NAME.finditer(meta):
        name = match.group(2).decode()
        if match.group(1)[0] == len(name) and name in FORMATS:
            return name, match.start()
    return "", -1


def chain(width: int, height: int, fmt: str, levels: int) -> int:
    """Bytes of `levels` mip levels from width x height down (each edge halved, at least 1)."""
    _, size, block, _ = FORMATS[fmt]
    total = 0
    for _ in range(levels):
        total += -(-width // block) * -(-height // block) * size
        width, height = max(1, width // 2), max(1, height // 2)
    return total


def shape(meta: bytes, length: int, faces: int = 1) -> tuple[str, tuple[int, int, int]] | None:
    """(format, (width, height, mips)) of the chain stored in a segment of `length` bytes:
    the metadata's full size, from the first mip level whose chain is exactly that long."""
    fmt, at = pixel_format(meta)
    if not fmt or at < 15 or length % faces:
        return None
    width, height, _depth, mips = struct.unpack_from("<IIIB", meta, at - 15)
    for level in range(max(mips, 1)):
        w, h = max(1, width >> level), max(1, height >> level)
        for levels in (mips - level, max(w, h).bit_length()):  # some hold the full chain anyway
            if levels > 0 and chain(w, h, fmt, levels) * faces == length:
                return fmt, (w, h, levels)
    return None


def dds(data: bytes, fmt: str, size: tuple[int, int, int], faces: int = 1) -> bytes:
    """The DDS file: FourCC or legacy pixel format when one names the format, else DX10."""
    width, height, mips = size
    dxgi, unit, block, fourcc = FORMATS[fmt]
    top = -(-width // block) * -(-height // block) * unit
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | (0x80000 if block > 1 else 0x8) | (0x20000 * (mips > 1))
    caps = 0x1000 | (0x400000 | 0x8 if mips > 1 else 0) | (0x8 if faces == 6 else 0)
    if fmt in LEGACY:
        pf_flags, bits, *masks = LEGACY[fmt]
        pf = struct.pack("<II4s5I", 32, pf_flags, b"\0\0\0\0", bits, *masks)
        top = width * unit  # the pitch of an uncompressed row
    else:
        pf = struct.pack("<II4s5I", 32, 0x4, fourcc or b"DX10", 0, 0, 0, 0, 0)
    head = struct.pack("<7I44x", 124, flags, height, width, top, 0, mips) + pf
    head += struct.pack("<5I", caps, 0xFE00 if faces == 6 else 0, 0, 0, 0)  # cubemap: 6 faces
    dx10 = not fourcc and fmt not in LEGACY
    extra = struct.pack("<5I", dxgi, 3, 0x4 if faces == 6 else 0, 1, 0) if dx10 else b""
    return b"DDS " + head + extra + data
