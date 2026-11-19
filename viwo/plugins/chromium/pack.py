"""pack.pak (doc 18): a Chromium DataPack rebuilt in the patched copy with the edited resources.
The header (version, encoding), the id order and every version-5 alias are kept; each resource's
bytes are the edit when its id was edited, else the original. Offsets are laid out again in id
order, so an unchanged pack comes back byte for byte. The engine loads nothing over a `.pak`:
the container is rewritten (doc 18.3). Read back after writing."""

import struct
from pathlib import Path

from viwo.contracts.slots import Packer, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

from . import read_pak

SLOT = SlotDefinition("pack.pak", "pack", "chromium", "pak-writer")


def _edited_id(member: str) -> int | None:
    stem = member.replace("\\", "/").rsplit("/", 1)[-1].split(".", 1)[0]
    return int(stem) if stem.isdigit() else None


def build_pak(raw: bytes, edits: dict[int, bytes]) -> bytes:
    """`raw` rebuilt with edits (resource id -> new bytes); byte-identical when edits is empty."""
    version, encoding, resources, aliases = read_pak(raw)
    bodies = [(rid, edits.get(rid, raw[start:end])) for rid, start, end in resources]
    if version == 4:
        head = struct.pack("<II", 4, len(bodies)) + bytes([encoding])
        alias_bytes = b""
    else:
        head = (
            struct.pack("<IB", 5, encoding)
            + b"\0\0\0"
            + struct.pack("<HH", len(bodies), len(aliases))
        )
        alias_bytes = b"".join(struct.pack("<HH", a, b) for a, b in aliases)
    data_start = len(head) + (len(bodies) + 1) * 6 + len(alias_bytes)
    index, at = bytearray(), data_start
    for rid, data in bodies:
        index += struct.pack("<HI", rid, at)
        at += len(data)
    index += struct.pack("<HI", 0, at)  # the sentinel: id 0, the end offset
    return head + bytes(index) + alias_bytes + b"".join(data for _, data in bodies)


class PakWriter(Packer):
    backend_id, owner, license = "pak-writer", "chromium", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: the read-back parses the written pack

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        try:
            raw = container.read_bytes()
            _, _, resources, _ = read_pak(raw)
            ids = {rid for rid, _, _ in resources}
            edits, unknown = {}, []
            for member, source in members.items():
                rid = _edited_id(member)
                if rid is None or rid not in ids:
                    unknown.append(member)
                else:
                    edits[rid] = source.read_bytes()
            container.write_bytes(build_pak(raw, edits))
        except (OSError, ValueError, struct.error, IndexError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"pak not rebuilt: {exc}"[:300])
        notes = [f"{len(unknown)} member(s) with no resource id in the pack: not added"] * bool(
            unknown
        )
        return Outcome(OutcomeKind.OK, len(edits), notes=tuple(notes))

    def verify(self, output: Path, members: dict[str, Path], ctx) -> list[str]:
        _, _, resources, _ = read_pak(output.read_bytes())
        raw = output.read_bytes()
        found = {rid: raw[s:e] for rid, s, e in resources}
        bad = []
        for member, source in members.items():
            rid = _edited_id(member)
            if rid is not None and found.get(rid) != source.read_bytes():
                bad.append(member)
        return bad
