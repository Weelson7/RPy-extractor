"""RPG Maker XP / VX (.rgssad, .rgss2a: RGSSAD v1) and VX Ace (.rgss3a: v3) archives."""

from __future__ import annotations

import mmap
import struct
from pathlib import Path, PurePosixPath

from viwo.contracts.slots import Unarchiver
from viwo.contracts.types import Outcome, OutcomeKind
from viwo.contracts.workspace import safe_member

MAGIC = b"RGSSAD\x00"
MASK = 0xFFFFFFFF


def _advance(key: int) -> int:
    return (key * 7 + 3) & MASK


def decrypt(data: bytes, key: int) -> bytes:
    """Data stream: each 4-byte word is XORed with the key, which advances per word."""
    words = (len(data) + 3) // 4
    stream = bytearray(words * 4)
    for i in range(words):
        struct.pack_into("<I", stream, i * 4, key)
        key = _advance(key)
    width = len(data)
    return (int.from_bytes(data, "little") ^ int.from_bytes(stream[:width], "little")).to_bytes(
        width, "little"
    )


def _entries_v1(blob: bytes):
    pos, key = 8, 0xDEADCAFE
    while pos + 4 <= len(blob):
        (length,) = struct.unpack_from("<I", blob, pos)
        length, key, pos = length ^ key, _advance(key), pos + 4
        if length > 4096 or pos + length > len(blob):
            raise ValueError("corrupt RGSSAD v1 entry")
        name = bytearray()
        for byte in blob[pos : pos + length]:
            name.append(byte ^ (key & 0xFF))
            key = _advance(key)
        pos += length
        (size,) = struct.unpack_from("<I", blob, pos)
        size, key, pos = size ^ key, _advance(key), pos + 4
        yield bytes(name), pos, size, key
        pos += size


def _entries_v3(blob: bytes):
    key = (struct.unpack_from("<I", blob, 8)[0] * 9 + 3) & MASK
    pos = 12
    while pos + 16 <= len(blob):
        offset, size, file_key, length = (v ^ key for v in struct.unpack_from("<4I", blob, pos))
        if offset == 0:
            return
        pos += 16
        raw = blob[pos : pos + length]
        name = bytes(b ^ ((key >> (8 * (i % 4))) & 0xFF) for i, b in enumerate(raw))
        pos += length
        yield name, offset, size, file_key


def entries(blob: bytes):
    """(name, offset, size, data key) for every entry."""
    if blob[: len(MAGIC)] != MAGIC or len(blob) < 12:
        raise ValueError("not an RGSSAD archive")
    return list(_entries_v3(blob) if blob[7] == 3 else _entries_v1(blob))


def safe_path(name: bytes) -> PurePosixPath | None:
    return safe_member(name.decode("utf-8", "replace"))


class RgssadBuiltin(Unarchiver):
    backend_id, owner, license = "rgssad-builtin", "rpgmaker", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        try:  # memory-mapped: game archives can be large
            with (
                open(archive, "rb") as fh,
                mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as blob,
            ):
                return Outcome(OutcomeKind.OK, _write_all(blob, dest, ctx))
        except (OSError, ValueError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=str(exc))


def _write_all(blob, dest: Path, ctx) -> int:
    written = 0
    for name, offset, size, key in entries(blob):
        rel = safe_path(name)
        if ctx.cancel.cancelled or rel is None or offset + size > len(blob):
            continue
        target = dest.joinpath(*rel.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(decrypt(blob[offset : offset + size], key))
        written += 1
    return written
