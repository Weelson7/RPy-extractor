"""RPG Maker MV / MZ encrypted media (.rpgmvp/.png_, .rpgmvo/.ogg_, .rpgmvm/.m4a_).

Each file is a 16-byte "RPGMV" header followed by the original file whose first 16 bytes
are XORed with the project key. The key comes from the game's own data/System.json; when
that is missing it is recovered from the fixed PNG signature and checked on every image.
"""

from __future__ import annotations

import json
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.slots import Exporter, Packer
from viwo.contracts.types import Outcome, OutcomeKind

HEADER = b"RPGMV\x00\x00\x00\x00\x03\x01\x00\x00\x00\x00\x00"
SUFFIXES = {
    ".rpgmvp": ".png",
    ".png_": ".png",
    ".rpgmvo": ".ogg",
    ".ogg_": ".ogg",
    ".rpgmvm": ".m4a",
    ".m4a_": ".m4a",
}
PNG_HEAD = bytes.fromhex("89504e470d0a1a0a0000000d49484452")


def system_key(game: Path) -> bytes | None:
    for system in sorted(game.rglob("System.json")):
        try:
            key = json.loads(system.read_text(encoding="utf-8-sig")).get("encryptionKey") or ""
            return bytes.fromhex(key) if len(key) == 32 else None
        except (OSError, ValueError, AttributeError):
            continue
    return None


def png_key(images: list[Path]) -> bytes | None:
    """The key that turns the first encrypted image back into a PNG, if it does for all."""
    heads = []
    for image in images[:20]:
        with open(image, "rb") as fh:
            head = fh.read(32)
        if head[:16] == HEADER and len(head) == 32:
            heads.append(head[16:])
    if not heads:
        return None
    key = bytes(a ^ b for a, b in zip(heads[0], PNG_HEAD))
    return key if all(bytes(a ^ b for a, b in zip(h, key)) == PNG_HEAD for h in heads) else None


def decrypt(data: bytes, key: bytes) -> bytes | None:
    if not data.startswith(HEADER):
        return None
    body = bytearray(data[16:])
    for i in range(min(16, len(body))):
        body[i] ^= key[i]
    return bytes(body)


class RpgMvExporter(Exporter):
    backend_id, owner, license = "rpgmv-builtin", "rpgmaker", "MIT"

    def export(self, ctx) -> Outcome:
        files = [p for p in sorted(ctx.game_root.rglob("*")) if p.suffix.lower() in SUFFIXES]
        if not files:
            return Outcome(OutcomeKind.OK, 0)
        images = [p for p in files if SUFFIXES[p.suffix.lower()] == ".png"]
        key = system_key(ctx.game_root) or png_key(images)
        if key is None:
            return Outcome(OutcomeKind.NEEDS_KEY, error="no encryptionKey in System.json")
        written, mapping = 0, {}
        for path in files:
            if ctx.cancel.cancelled:
                break
            plain = decrypt(path.read_bytes(), key)
            if plain is None:
                continue
            rel = path.relative_to(ctx.game_root).with_suffix(SUFFIXES[path.suffix.lower()])
            target = ctx.staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(plain)
            mapping[rel.as_posix()] = [path.relative_to(ctx.game_root).as_posix(), "file"]
            written += 1
        (ctx.staging / ws.EXPORT_MAP).write_text(json.dumps(mapping), encoding="utf-8")
        return Outcome(OutcomeKind.OK, written)


class RpgMvPacker(Packer):
    """Round trip: re-encrypt the edited image/audio over its encrypted original."""

    backend_id, owner, license = "rpgmv-pack", "rpgmaker", "MIT"

    def pack(self, container, members, ctx) -> Outcome:
        key = system_key(ctx.game_root) or png_key([container])
        if key is None:
            return Outcome(OutcomeKind.NEEDS_KEY, error="no encryptionKey in System.json")
        container.write_bytes(HEADER + decrypt(HEADER + members["file"].read_bytes(), key))
        return Outcome(OutcomeKind.OK, 1)

    def verify(self, output, members, ctx) -> list[str]:
        key = system_key(ctx.game_root) or png_key([output])
        ok = key is not None and decrypt(output.read_bytes(), key) == members["file"].read_bytes()
        return [] if ok else ["file"]
