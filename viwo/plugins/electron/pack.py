"""pack.asar (doc 18): an edited app.asar rebuilt in the patched copy. Every member keeps its
place in the header tree; edited ones get their new bytes and size, the rest are streamed from
the original; offsets are laid out again; a member's `integrity` (Electron's per-file SHA-256
and 4 MB block hashes) is recomputed when the original carries one. A file marked `unpacked`
lives in `app.asar.unpacked/` and is written there."""

import hashlib
import json
import os
import struct
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.slots import Packer, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

BLOCK = 4 << 20
SLOT = SlotDefinition("pack.asar", "pack", "electron", "asar-writer")


def _header(fh) -> tuple[dict, int]:
    from . import asar_header

    found = asar_header(fh.read(16))
    if found is None:
        raise ValueError("not an asar archive")
    return json.loads(fh.read(found[0]).decode("utf-8")), found[1]


def _files(tree: dict, prefix: str = ""):
    """(path, node) of every file node, in header order."""
    for name, node in (tree.get("files") or {}).items():
        path = f"{prefix}/{name}" if prefix else name
        if "files" in node:
            yield from _files(node, path)
        else:
            yield path, node


def _integrity(data: bytes) -> dict:
    blocks = [hashlib.sha256(data[i : i + BLOCK]).hexdigest() for i in range(0, len(data), BLOCK)]
    whole = hashlib.sha256(data).hexdigest()
    return {"algorithm": "SHA256", "hash": whole, "blockSize": BLOCK, "blocks": blocks or [whole]}


def write_asar(original: Path, members: dict[str, Path], target: Path) -> int:
    """Rebuild original into target with members (path -> edited file); returns the count."""
    with open(original, "rb") as src:
        tree, base = _header(src)
        bodies, at = [], 0
        for path, node in _files(tree):
            if node.get("unpacked") or "offset" not in node:
                continue
            if path in members:
                data = members[path].read_bytes()
            else:
                src.seek(base + int(node["offset"]))
                data = src.read(int(node.get("size", 0)))
            node["offset"], node["size"] = str(at), len(data)
            if "integrity" in node:
                node["integrity"] = _integrity(data)
            bodies.append(data)
            at += len(data)
    raw = json.dumps(tree, separators=(",", ":")).encode("utf-8")
    pickle = struct.pack("<I", len(raw)) + raw
    pickle += b"\0" * (-len(pickle) % 4)
    with open(target, "wb") as out:
        out.write(struct.pack("<III", 4, len(pickle) + 4, len(pickle)) + pickle)
        for data in bodies:
            out.write(data)
    return len(bodies)


class AsarWriter(Packer):
    backend_id, owner, license = "asar-writer", "electron", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        temp = container.with_name(container.name + ".viwo-tmp")
        try:
            unpacked = _unpacked(container, members)
            inside = {m: p for m, p in members.items() if m not in unpacked}
            count = write_asar(container, inside, temp)
            os.replace(temp, container)
            for member, source in unpacked.items():
                target = ws.member_path(container.with_name(container.name + ".unpacked"), member)
                if target is not None:
                    target.write_bytes(source.read_bytes())
        except (OSError, ValueError, struct.error, UnicodeDecodeError) as exc:
            temp.unlink(missing_ok=True)
            return Outcome(OutcomeKind.FAILED, error=f"asar not rebuilt: {exc}"[:300])
        missing = sorted(set(inside) - _names(container))
        notes = (f"{len(missing)} new member(s) not in the archive: not added",) if missing else ()
        return Outcome(OutcomeKind.OK, count + len(unpacked), notes=notes)


def _unpacked(container: Path, members: dict[str, Path]) -> dict[str, Path]:
    with open(container, "rb") as fh:
        tree, _ = _header(fh)
    marked = {path for path, node in _files(tree) if node.get("unpacked")}
    return {m: p for m, p in members.items() if m in marked}


def _names(container: Path) -> set[str]:
    with open(container, "rb") as fh:
        tree, _ = _header(fh)
    return {path for path, _ in _files(tree)}
