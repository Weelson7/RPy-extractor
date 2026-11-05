"""pack.rgssad (doc 18): an RPG Maker XP / VX (RGSSAD v1) or VX Ace (v3) archive rebuilt in the
patched copy with the edited members, every entry in its place and under its own key (v1 keys
come from the header stream, v3 keys are stored per entry, so neither depends on a member's
size); RPG Maker loads nothing over its archive, so the archive itself is rewritten."""

from __future__ import annotations

import os
import struct
from pathlib import Path

from viwo.contracts.slots import Packer, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

from .rgss import MASK, _advance, decrypt, entries

SLOT = SlotDefinition("pack.rgssad", "pack", "rpgmaker", "rgssad-writer")


def _plain(blob: bytes, members: dict[str, Path]) -> list[tuple[bytes, int, bytes]]:
    """(name, data key, plain bytes) per entry: the edit when there is one, else the original."""
    out = []
    for name, offset, size, key in entries(blob):
        edited = members.get(name.decode("utf-8", "replace").replace("\\", "/"))
        data = edited.read_bytes() if edited else decrypt(blob[offset : offset + size], key)
        out.append((name, key, data))
    return out


def _v1(items: list[tuple[bytes, int, bytes]]) -> bytes:
    out, key = bytearray(b"RGSSAD\x00\x01"), 0xDEADCAFE
    for name, _, data in items:
        out += struct.pack("<I", len(name) ^ key)
        key = _advance(key)
        for byte in name:
            out.append(byte ^ (key & 0xFF))
            key = _advance(key)
        out += struct.pack("<I", len(data) ^ key)
        key = _advance(key)
        out += decrypt(data, key)  # the data key is the stream's key here: XOR undoes itself
    return bytes(out)


def _v3(seed: int, items: list[tuple[bytes, int, bytes]]) -> bytes:
    key = (seed * 9 + 3) & MASK
    table_size = sum(16 + len(name) for name, _, _ in items) + 16
    table, body, offset = bytearray(), bytearray(), 12 + table_size
    for name, file_key, data in items:
        table += struct.pack("<4I", offset ^ key, len(data) ^ key, file_key ^ key, len(name) ^ key)
        table += bytes(b ^ ((key >> (8 * (i % 4))) & 0xFF) for i, b in enumerate(name))
        body += decrypt(data, file_key)
        offset += len(data)
    table += struct.pack("<4I", key, 0, 0, 0)  # offset 0 after the XOR: the end of the table
    return b"RGSSAD\x00\x03" + struct.pack("<I", seed) + bytes(table) + bytes(body)


class RgssadWriter(Packer):
    backend_id, owner, license = "rgssad-writer", "rpgmaker", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        temp = container.with_name(container.name + ".viwo-tmp")
        try:
            blob = container.read_bytes()
            items = _plain(blob, members)
            rebuilt = (
                _v3(struct.unpack_from("<I", blob, 8)[0], items) if blob[7] == 3 else _v1(items)
            )
            temp.write_bytes(rebuilt)
            os.replace(temp, container)
        except (OSError, ValueError, struct.error) as exc:
            temp.unlink(missing_ok=True)
            return Outcome(OutcomeKind.FAILED, error=f"archive not rebuilt: {exc}"[:300])
        known = {n.decode("utf-8", "replace").replace("\\", "/") for n, _, _ in items}
        new = sorted(set(members) - known)
        notes = (f"{len(new)} new member(s) not in the archive: not added",) if new else ()
        return Outcome(OutcomeKind.OK, len(items), notes=notes)
