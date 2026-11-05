"""Bethesda archives: BSA (Oblivion 103, Fallout 3 / Skyrim 104, Skyrim SE 105) and BA2
(Fallout 4 / 76, Starfield: GNRL files and DX10 textures rebuilt as .dds)."""

import struct
import zlib

HAS_DIRS, HAS_NAMES, COMPRESSED, EMBED_NAMES = 0x1, 0x2, 0x4, 0x100
TOGGLE = 0x40000000


def _inflate(data: bytes, size: int, lz4: bool = False) -> bytes | None:
    """Decompress to no more than the declared size (zip-bomb guard); None without lz4."""
    if lz4:
        try:
            import lz4.frame  # optional: Skyrim SE (BSA 105) compresses with LZ4 frames
        except ImportError:
            return None
        out = lz4.frame.LZ4FrameDecompressor().decompress(data, max_length=max(size, 1))
    else:
        out = zlib.decompressobj().decompress(data, max(size, 1))  # 0 would mean "no limit"
    if len(out) != size:
        raise ValueError("entry does not inflate to its declared size")
    return out


def _cstr(blob, pos: int) -> tuple[str, int]:
    end = blob.find(b"\0", pos)
    if end < 0:
        raise ValueError("unterminated name")
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
        path = f"{folder}\\{name}" if folder else name  # archives without folder names
        out.append((path, offset, size & ~(TOGGLE | 0x80000000), compressed))
    return version, flags, out


def bsa_data(blob: bytes, version: int, flags: int, entry) -> bytes | None:
    _, offset, size, compressed = entry
    end = offset + size
    if flags & EMBED_NAMES and version >= 104:
        offset += 1 + blob[offset]
    if not compressed:
        return blob[offset:end]
    (original,) = struct.unpack_from("<I", blob, offset)
    return _inflate(blob[offset + 4 : end], original, lz4=version == 105)


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
            yield names[i], _inflate(raw, size) if packed else raw
            continue
        chunks, _, height, width, mips, dxgi, cube = struct.unpack_from("<BHHHBBB", blob, pos + 13)
        pos, data = pos + 24, b""
        for _ in range(chunks):
            offset, packed, size = struct.unpack_from("<QII", blob, pos)
            raw = blob[offset : offset + (packed or size)]
            data += _inflate(raw, size) if packed else raw
            pos += 24
        yield names[i], dds_header(width, height, mips, dxgi, bool(cube)) + data
