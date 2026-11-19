"""Wolf RPG archives (`Data.wolf`, `*.wolf`): the DXArchive-derived container Wolf RPG Editor and
DxLib share, read first-party. Implemented from the public DXArchive version 6 description:

- Header (little-endian, 28 bytes): u16 magic `0x5844` ("DX"), u16 version, u32 head_size (the
  three tables together), u32 data_start, u32 name_off, u32 file_off, u32 dir_off, u32 code_page.
  The tables sit at offset 28 for `head_size` bytes; file data follows at `data_start`.
- FileNameTable: per name a u16 of 4-byte units, a u16 parity, then an upper-case copy and the
  real name, each NUL-terminated and padded to four bytes.
- FileTable: 56-byte entries (name offset, attributes, three 64-bit times, 64-bit data offset,
  64-bit size, 64-bit pressed size or `NONE` when stored raw). Attribute 0x10 is a directory,
  whose data offset points into the DirectoryTable.
- DirectoryTable: 32-byte entries (this directory's file header, its parent, the file count, the
  first file header). Entry 0 is the root.

A key (from the user, verified: the decrypted header must read as `DX` version 6) XORs the file
by a 7-byte stream, `byte[i] ^= key[i % 7]`. Only version 6 is read; any other is refused by
name. DXA-compressed members (`pressed != NONE`) are refused by name: ViWo's DXA decompressor is
not verified against DxLib, so it never writes a member it cannot trust. NOT verified against a
real Wolf RPG game: no install was available."""

import struct

MAGIC = 0x5844
VERSION = 6
NONE = 0xFFFFFFFFFFFFFFFF  # a file's pressed size when it is stored raw (not DXA-compressed)
HEADER = 28
DIRECTORY = 0x10  # the attribute bit of a directory entry


def key_bytes(key: str) -> bytes:
    """The 7-byte XOR stream of a key string (its UTF-8 bytes folded into seven), or b"" for
    none; a key the archive was not made with fails the header check and is refused."""
    raw = key.encode("utf-8")
    if not raw:
        return b""
    return bytes(raw[i] if i < len(raw) else raw[i % len(raw)] for i in range(7))


def unkey(data: bytes, key: bytes) -> bytes:
    """`data` with the key stream removed (XOR is its own inverse); `data` unchanged for no key."""
    if not key:
        return data
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


class Entry:
    __slots__ = ("path", "offset", "size", "pressed")

    def __init__(self, path: str, offset: int, size: int, pressed: int) -> None:
        self.path, self.offset, self.size, self.pressed = path, offset, size, pressed


def _header(blob: bytes) -> tuple[int, int, int, int, int]:
    """(data_start, name_off, file_off, dir_off) within the tables block; ValueError otherwise."""
    if len(blob) < HEADER:
        raise ValueError("not a Wolf RPG archive (too short)")
    magic, version, head_size, data_start, name_off, file_off, dir_off, _ = struct.unpack_from(
        "<HHIIIIII", blob, 0
    )
    if magic != MAGIC:
        raise ValueError("not a Wolf RPG / DXArchive file (no DX signature)")
    if version != VERSION:
        raise ValueError(f"DXArchive version {version}: only version 6 is read")
    if HEADER + head_size > len(blob) or data_start > len(blob):
        raise ValueError("Wolf RPG archive header points past the end")
    return data_start, HEADER + name_off, HEADER + file_off, HEADER + dir_off, head_size


def _name(blob: bytes, at: int) -> str:
    """The real (second) name of a FileNameTable packet at `at`: after the upper-case copy, which
    is NUL-terminated and padded to a 4-byte boundary."""
    (units,) = struct.unpack_from("<H", blob, at)
    packet = blob[at + 4 : at + units * 4]
    real_start = (packet.index(b"\x00") + 1 + 3) & ~3  # 4-align past the upper copy's NUL
    return packet[real_start:].split(b"\x00", 1)[0].decode("utf-8", "replace")


def _entries(blob: bytes, data_start: int, name_off: int, file_off: int, dir_off: int) -> list:
    """Every file, by its full path; directories walked from the root, ValueError on a bad link."""
    out: list[Entry] = []

    def walk(dir_index: int, prefix: str) -> None:
        base = dir_off + dir_index * 32
        if base + 32 > len(blob):
            raise ValueError("directory table entry past the end")
        _, _, count, first = struct.unpack_from("<4Q", blob, base)
        for n in range(count):
            fh = file_off + (first + n * 56)
            if fh + 56 > len(blob):
                raise ValueError("file table entry past the end")
            nm, attr, _, _, _, offset, size, pressed = struct.unpack_from("<IIQQQQQQ", blob, fh)
            name = _name(blob, name_off + nm)
            if attr & DIRECTORY:
                walk(offset // 32, f"{prefix}{name}/")
            else:
                out.append(Entry(prefix + name, data_start + offset, size, pressed))

    walk(0, "")
    return out


def read_archive(blob: bytes, key: bytes = b"") -> tuple[bytes, list]:
    """(the decrypted bytes, every file entry whose offset is into them); ValueError when the
    archive, or the key, does not read as a version 6 DXArchive."""
    body = unkey(blob, key) if key else blob
    data_start, name_off, file_off, dir_off, _ = _header(body)
    return body, _entries(body, data_start, name_off, file_off, dir_off)
