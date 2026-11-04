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
    for system in ws.files(game, "System.json"):
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


def game_images(game: Path) -> list[Path]:
    """The game's encrypted images: what any key is checked on (an audio file says nothing)."""
    return [p for p in ws.files(game) if SUFFIXES.get(p.suffix.lower()) == ".png"][:20]


def opens(key: bytes, images: list[Path]) -> bool:
    """D18: a key is used only once it turns an encrypted image back into a PNG."""
    for image in images[:5]:
        with open(image, "rb") as fh:
            head = fh.read(32)
        if head[:16] == HEADER and len(head) == 32:
            return bytes(a ^ b for a, b in zip(head[16:], key)) == PNG_HEAD
    return True  # no image to check it on (audio only): the game's own key is taken


def verified_key(game: Path, images: list[Path]) -> tuple[bytes | None, str]:
    """(key, note): System.json's key when it opens the images, else the one the PNG
    signature gives (a decoy or a stale System.json is said), else None."""
    key = system_key(game)
    if key is not None and opens(key, images):
        return key, ""
    found = png_key(images)
    if key is not None and found is not None:
        return found, "System.json's key does not open the images: the PNG signature's key is used"
    return found, ""


def decrypt(data: bytes, key: bytes) -> bytes | None:
    if not data.startswith(HEADER):
        return None
    body = bytearray(data[16:])
    for i in range(min(16, len(body))):
        body[i] ^= key[i]
    return bytes(body)


class RpgMvExporter(Exporter):
    backend_id, owner, license = "rpgmv-builtin", "rpgmaker", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def export(self, ctx) -> Outcome:
        files = [p for p in ws.files(ctx.game_root) if p.suffix.lower() in SUFFIXES]
        if not files:
            return Outcome(OutcomeKind.OK, 0)
        images = [p for p in files if SUFFIXES[p.suffix.lower()] == ".png"]
        key, note = verified_key(ctx.game_root, images)
        if key is None:
            return Outcome(OutcomeKind.NEEDS_KEY, error="no key in System.json opens the images")
        written, raw, mapping = 0, 0, {}
        for path in files:
            if ctx.cancel.cancelled:
                break
            data = path.read_bytes()
            plain = decrypt(data, key)
            if plain is None:  # no RPGMV header (a placeholder, a custom header): kept as it is
                target = ctx.staging / path.relative_to(ctx.game_root)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                raw += 1
                continue
            rel = path.relative_to(ctx.game_root).with_suffix(SUFFIXES[path.suffix.lower()])
            target = ctx.staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(plain)
            mapping[rel.as_posix()] = [path.relative_to(ctx.game_root).as_posix(), "file"]
            written += 1
        (ctx.staging / ws.EXPORT_MAP).write_text(json.dumps(mapping), encoding="utf-8")
        notes = [note] if note else []
        if raw:
            notes.append(f"{raw} file(s) without the RPGMV header kept as they are (not decrypted)")
        return Outcome(OutcomeKind.OK, written + raw, notes=tuple(notes))


class RpgMvPacker(Packer):
    """Round trip: re-encrypt the edited image/audio over its encrypted original."""

    backend_id, owner, license = "rpgmv-pack", "rpgmaker", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def pack(self, container, members, ctx) -> Outcome:
        key = verified_key(ctx.game_root, game_images(ctx.game_root))[0]
        if key is None:
            return Outcome(OutcomeKind.NEEDS_KEY, error="no key in System.json opens the images")
        container.write_bytes(HEADER + decrypt(HEADER + members["file"].read_bytes(), key))
        return Outcome(OutcomeKind.OK, 1)

    def verify(self, output, members, ctx) -> list[str]:
        key = verified_key(ctx.game_root, game_images(ctx.game_root))[0]
        ok = key is not None and decrypt(output.read_bytes(), key) == members["file"].read_bytes()
        return [] if ok else ["file"]
