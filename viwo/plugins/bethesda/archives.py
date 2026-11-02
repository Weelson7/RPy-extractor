"""Bethesda archives: BSA (Oblivion 103, Fallout 3 / Skyrim 104, Skyrim SE 105) and BA2
(Fallout 4 / 76, Starfield: GNRL files and DX10 textures rebuilt as .dds)."""

from __future__ import annotations

import struct
import zlib

HAS_DIRS, HAS_NAMES, COMPRESSED, EMBED_NAMES = 0x1, 0x2, 0x4, 0x100
TOGGLE = 0x40000000


def _lz4(data: bytes) -> bytes | None:
    try:
        import lz4.frame  # optional: Skyrim SE (BSA 105) compresses with LZ4 frames
    except ImportError:
        return None
    return lz4.frame.decompress(data)


def _cstr(blob: bytes, pos: int) -> tuple[str, int]:
    end = blob.index(b"\0", pos)
    return blob[pos:end].decode("cp1252", "replace"), end + 1


def bsa_entries(blob: bytes):
    """(path, offset, size, compressed) for every file of a BSA."""
    version, _, flags, folders, files, _, _, _ = struct.unpack_from("<8I", blob, 4)
    record = 24 if version == 105 else 16
    counts = [struct.unpack_from("<Q I", blob, 36 + i * record)[1] for i in range(folders)]
    pos, records = 36 + folders * record, []
    for count in counts:
        folder = ""
        if flags & HAS_DIRS:
            length = blob[pos]
            folder = blob[pos + 1 : pos + length].decode("cp1252", "replace")
            pos += 1 + length
        for _ in range(count):
            _, size, offset = struct.unpack_from("<QII", blob, pos)
            records.append((folder, size, offset))
            pos += 16
    out = []
    for folder, size, offset in records:
        name, pos = _cstr(blob, pos) if flags & HAS_NAMES else (f"{offset:08x}", pos)
        compressed = bool(flags & COMPRESSED) != bool(size & TOGGLE)
        out.append((f"{folder}\\{name}", offset, size & ~(TOGGLE | 0x80000000), compressed))
    return version, flags, out


def bsa_data(blob: bytes, version: int, flags: int, entry) -> bytes | None:
    _, offset, size, compressed = entry
    end = offset + size
    if flags & EMBED_NAMES and version >= 104:
        offset += 1 + blob[offset]
    if not compressed:
        return blob[offset:end]
    body = blob[offset + 4 : end]
    return _lz4(body) if version == 105 else zlib.decompress(body)


def _names(blob: bytes, at: int, count: int) -> list[str]:
    names = []
    for _ in range(count):
        (length,) = struct.unpack_from("<H", blob, at)
        names.append(blob[at + 2 : at + 2 + length].decode("utf-8", "replace"))
        at += 2 + length
    return names


def dds_header(width: int, height: int, mips: int, dxgi: int, cube: bool) -> bytes:
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000
    caps = 0x1000 | (0x400008 if mips > 1 else 0) | (0x8 if cube else 0)
    head = struct.pack("<7I", 124, flags, height, width, 0, 0, mips) + b"\0" * 44
    head += struct.pack("<2I4s5I", 32, 0x4, b"DX10", 0, 0, 0, 0, 0)
    head += struct.pack("<5I", caps, 0xFE00 if cube else 0, 0, 0, 0)
    return b"DDS " + head + struct.pack("<5I", dxgi, 3, 0x4 if cube else 0, 1, 0)


def ba2_files(blob: bytes):
    """(path, bytes) for every file of a BA2 (version 1, 7 or 8; zlib)."""
    version, kind, count, table = struct.unpack_from("<I4sIQ", blob, 4)
    names, pos = _names(blob, table, count), 24 + (8 if version in (2, 3) else 0)
    pos += 4 if version == 3 else 0
    for i in range(count):
        if kind == b"GNRL":
            offset, packed, size = struct.unpack_from("<QII", blob, pos + 16)
            pos += 36
            raw = blob[offset : offset + (packed or size)]
            yield names[i], zlib.decompress(raw) if packed else raw
            continue
        chunks, _, height, width, mips, dxgi, cube = struct.unpack_from("<BHHHBBB", blob, pos + 13)
        pos, data = pos + 24, b""
        for _ in range(chunks):
            offset, packed, size = struct.unpack_from("<QII", blob, pos)
            raw = blob[offset : offset + (packed or size)]
            data += zlib.decompress(raw) if packed else raw
            pos += 24
        yield names[i], dds_header(width, height, mips, dxgi, bool(cube)) + data
