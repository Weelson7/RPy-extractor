"""Defold's bundled archive, read as the engine reads it (`engine/resource/src/
resource_archive.cpp`): `game.arci` holds a 48-byte header (version, entry count, where the hashes
and entries sit, the hash length, an MD5 of what follows), the resources' content hashes in 64-byte
slots, sorted, and one 16-byte entry each (big-endian: offset, size, compressed size, flags in
versions 4 and 5; in 6 the flags in the offset's top four bits); `game.arcd` holds the data, LZ4
blocks where compressed. Names come from `game.dmanifest` (protobuf: each resource's URL and its
hash). The engine finds a resource by its manifest hash and reads its sizes from the index, so the
way back rewrites the data and the entries and keeps every hash and the manifest as they are."""

import hashlib
import struct
from dataclasses import dataclass, replace

VERSIONS = (4, 5, 6)
HEADER, SLOT_BYTES, ENTRY = 48, 64, 16
ENCRYPTED, COMPRESSED = 1, 2
RAW = 0xFFFFFFFF  # the compressed size of an entry stored as it is
V6_MASK = (1 << 60) - 1


@dataclass(frozen=True)
class Entry:
    digest: bytes
    offset: int
    size: int
    packed: int  # RAW when stored uncompressed
    flags: int

    @property
    def stored(self) -> int:
        return self.packed if self.flags & COMPRESSED else self.size


@dataclass
class Index:
    version: int
    blob: bytes  # the whole .arci as read
    entry_at: int
    entries: list


def read_index(blob: bytes) -> Index:
    """The index; ValueError for another version or a damaged one."""
    if len(blob) < HEADER:
        raise ValueError("index cut short")
    version, _, _, count, entry_at, hash_at, hash_len = struct.unpack_from(">IIQIIII", blob)
    if version not in VERSIONS:
        raise ValueError(f"Defold archive version {version} is not one ViWo reads (4, 5, 6)")
    if not 0 < hash_len <= SLOT_BYTES:
        raise ValueError(f"hash length {hash_len}")
    if hash_at + SLOT_BYTES * count > len(blob) or entry_at + ENTRY * count > len(blob):
        raise ValueError("index cut short")
    entries = []
    for i in range(count):
        digest = blob[hash_at + SLOT_BYTES * i : hash_at + SLOT_BYTES * i + hash_len]
        at = entry_at + ENTRY * i
        if version >= 6:
            packed_at, size, packed = struct.unpack_from(">QII", blob, at)
            offset, flags = packed_at & V6_MASK, packed_at >> 60
        else:
            offset, size, packed, flags = struct.unpack_from(">IIII", blob, at)
        entries.append(Entry(digest, offset, size, packed, flags))
    return Index(version, blob, entry_at, entries)


def _varint(blob: bytes, at: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = blob[at]
        value, at, shift = value | (byte & 0x7F) << shift, at + 1, shift + 7
        if byte < 0x80:
            return value, at
        if shift > 63:
            raise ValueError("varint too long")


def fields(blob: bytes):
    """(field number, value) of each protobuf field: ints for varints and fixed, bytes else."""
    at = 0
    while at < len(blob):
        key, at = _varint(blob, at)
        kind = key & 7
        if kind == 0:
            value, at = _varint(blob, at)
        elif kind in (1, 5):
            width = 8 if kind == 1 else 4
            value, at = int.from_bytes(blob[at : at + width], "little"), at + width
        elif kind == 2:
            size, at = _varint(blob, at)
            value, at = blob[at : at + size], at + size
            if at > len(blob):
                raise ValueError("a field runs past the end")
        else:
            raise ValueError(f"protobuf wire type {kind}")
        yield key >> 3, value


def manifest_names(blob: bytes) -> dict[bytes, list[str]]:
    """Content hash -> the URLs of the resources holding it, from `game.dmanifest`."""
    try:
        data = next(v for n, v in fields(blob) if n == 1 and isinstance(v, bytes))
        names: dict[bytes, list[str]] = {}
        for number, entry in fields(data):
            if number != 3 or not isinstance(entry, bytes):
                continue
            parts = dict(fields(entry))
            digest = dict(fields(parts[1]))[1]
            names.setdefault(digest, []).append(parts[2].decode("utf-8"))
        return names
    except (StopIteration, KeyError, IndexError, UnicodeDecodeError, TypeError) as exc:
        raise ValueError(f"damaged manifest: {exc!r}") from None


def pack_entry(version: int, entry: Entry) -> bytes:
    if version >= 6:
        return struct.pack(">QII", entry.flags << 60 | entry.offset, entry.size, entry.packed)
    return struct.pack(">IIII", entry.offset, entry.size, entry.packed, entry.flags)


def _encrypt(body: bytes, entry: Entry, key: bytes | None) -> bytes:
    """`body` encrypted when the entry is an encrypted one and a key is at hand (the compress-
    then-encrypt order the bundler uses), else `body` unchanged."""
    if entry.flags & ENCRYPTED and key:
        from .crypt import crypt

        return crypt(body, key)
    return body


def stored_form(entry: Entry, data: bytes, lz4, key: bytes | None = None) -> tuple[Entry, bytes]:
    """An edited resource as the archive holds it: LZ4 when the original was and it saves at
    least 5 % (Defold's own rule), then encrypted when the original was, else as it is."""
    if entry.flags & COMPRESSED and lz4 is not None:
        packed = lz4.block.compress(data, mode="high_compression", store_size=False)
        if len(packed) <= 0.95 * len(data):
            return replace(entry, size=len(data), packed=len(packed)), _encrypt(packed, entry, key)
    flags = entry.flags & ~COMPRESSED
    return replace(entry, size=len(data), packed=RAW, flags=flags), _encrypt(data, entry, key)


def write_archive(index: Index, data_src, edits: dict[bytes, bytes], out, lz4, key=None) -> bytes:
    """Write the data file into `out` (stored data in the original order, each start aligned to
    4 as Defold writes it) and return the new index."""
    entries, at = list(index.entries), 0
    for i in sorted(range(len(entries)), key=lambda n: (entries[n].offset, entries[n].stored)):
        out.write(b"\0" * (-at % 4))
        at += -at % 4
        entry = entries[i]
        if entry.digest in edits:
            entry, stored = stored_form(entry, edits[entry.digest], lz4, key)
        else:
            data_src.seek(entry.offset)
            stored = data_src.read(entry.stored)
            if len(stored) != entry.stored:
                raise ValueError("a resource runs past the end of the data file")
        entries[i] = replace(entry, offset=at)
        out.write(stored)
        at += len(stored)
    table = b"".join(pack_entry(index.version, e) for e in entries)
    blob = bytearray(index.blob)
    blob[index.entry_at : index.entry_at + len(table)] = table
    if blob != index.blob:  # Defold's archive identifier: the MD5 of all after the header
        blob[32:48] = hashlib.md5(bytes(blob[HEADER:])).digest()
    return bytes(blob)
