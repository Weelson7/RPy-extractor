"""RPG Maker XP / VX (.rgssad, .rgss2a: RGSSAD v1) and VX Ace (.rgss3a: v3) archives."""

from __future__ import annotations

import mmap
import struct
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.slots import Unarchiver
from viwo.contracts.types import Outcome, OutcomeKind

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


class RgssadBuiltin(Unarchiver):
    backend_id, owner, license = "rgssad-builtin", "rpgmaker", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        try:  # memory-mapped: game archives can be large
            with (
                open(archive, "rb") as fh,
                mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as blob,
            ):
                written, notes = _write_all(blob, dest, ctx)
                return Outcome(OutcomeKind.OK, written, notes=tuple(notes))
        except (OSError, ValueError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=str(exc))


def _write_all(blob, dest: Path, ctx) -> tuple[int, list[str]]:
    """(written, what was skipped or altered and why: names, entries past a cut archive's end)."""
    names, written, cut = ws.Names(dest), 0, 0
    for name, offset, size, key in entries(blob):
        if ctx.cancel.cancelled:
            break
        if offset + size > len(blob):
            cut += 1
            continue
        target = names.target(name.decode("utf-8", "replace"))
        if target is None:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(decrypt(blob[offset : offset + size], key))
        written += 1
    notes = [f"{cut} entr(ies) past the end of the archive (cut short)"] if cut else []
    return written, [*names.save(), *notes]
