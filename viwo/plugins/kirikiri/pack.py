"""pack.xp3 (doc 18): edited members of a KiriKiri archive written as the next patch archive the
engine loads after its own (`patch.xp3`, then `patch2.xp3`, ...: a later archive wins), beside
the game's archives. Unencrypted, zlib-compressed segments and index; read back after
writing."""

import struct
import zlib
from pathlib import Path
from types import SimpleNamespace

from viwo.contracts import workspace as ws
from viwo.contracts.slots import Packer, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

SLOT = SlotDefinition("pack.xp3", "pack", "kirikiri", "xp3-writer")


def _chunk(tag: bytes, body: bytes) -> bytes:
    return tag + struct.pack("<Q", len(body)) + body


def write_xp3(members: dict[str, bytes], target: Path) -> None:
    from . import MAGIC

    start = len(MAGIC) + 8
    body, index = bytearray(), bytearray()
    for name, data in sorted(members.items()):
        packed = zlib.compress(data, 9)
        raw = name.replace("\\", "/").encode("utf-16-le")
        info = struct.pack("<IQQH", 0, len(data), len(packed), len(raw) // 2) + raw
        segm = struct.pack("<IQQQ", 1, start + len(body), len(data), len(packed))
        adlr = struct.pack("<I", zlib.adler32(data))
        index += _chunk(
            b"File", _chunk(b"info", info) + _chunk(b"segm", segm) + _chunk(b"adlr", adlr)
        )
        body += packed
    table = zlib.compress(bytes(index), 9)
    tail = b"\x01" + struct.pack("<QQ", len(table), len(index)) + table
    target.write_bytes(MAGIC + struct.pack("<Q", start + len(body)) + bytes(body) + tail)


class Xp3Writer(Packer):
    backend_id, owner, license = "xp3-writer", "kirikiri", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: the read-back parses the written archive
    override = True  # a patch archive holds the edits; the game's archives keep the rest

    def output_for(self, container: Path) -> Path:
        """The first patch archive name the game does not use yet."""
        for n in range(1, 100):
            path = container.with_name("patch.xp3" if n == 1 else f"patch{n}.xp3")
            if not path.exists() or path.stat().st_size == 0 or _ours(path):
                return path
        return container.with_name("patch100.xp3")

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        target = self.output_for(container)
        try:  # edits of another archive already in ViWo's patch stay in it
            merged = {**(_members(target) if target.exists() else {})}
            merged.update({m: p.read_bytes() for m, p in members.items()})
            write_xp3(merged, target)
            (target.parent / f".{target.name}.viwo").write_text("written by ViWo", encoding="utf-8")
        except (OSError, ValueError, zlib.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"patch archive not written: {exc}"[:300])
        return Outcome(OutcomeKind.OK, len(members), notes=(f"edits in {target.name}",))

    def verify(self, output: Path, members: dict[str, Path], ctx) -> list[str]:
        found = _members(output)
        return sorted(m for m, p in members.items() if found.get(m) != p.read_bytes())


def _members(archive: Path) -> dict[str, bytes]:
    """Every member of an XP3 written by ViWo, read back through the engine's reader."""
    import shutil
    import tempfile

    from . import Xp3Builtin

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        Xp3Builtin().extract(archive, out, SimpleNamespace(cancel=SimpleNamespace(cancelled=False)))
        files = [f for f in out.rglob("*") if f.is_file() and not f.name.startswith(".viwo-")]
        names = ws.renamed(out)  # a name Windows cannot hold: its original, from the record
        found = {}
        for f in files:
            rel = f.relative_to(out).as_posix()
            found[names.get(rel, rel)] = f.read_bytes()
        shutil.rmtree(out, ignore_errors=True)
    return found


def _ours(path: Path) -> bool:
    """A patch archive ViWo wrote earlier into this copy is rewritten, never a game's own."""
    return (path.parent / f".{path.name}.viwo").is_file()
