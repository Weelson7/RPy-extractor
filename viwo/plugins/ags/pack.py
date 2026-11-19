"""pack.clib (doc 18): an AGS library rebuilt in the patched copy, in its own version (the
engine loads nothing over its library). Its table of contents is kept byte for byte but for each
asset's offset and size, rewritten in place (re-encrypted through the generator in version 21);
the assets follow it in the table's order, an edited one with its new data, so an unchanged
library comes back as it was. An edited asset another part holds (`game.001`) moves into this
one; the part is left as it is. A library behind the game's executable stays behind it, with its
tail signature. Read back by unpacking it again."""

import os
import shutil
from pathlib import Path

from viwo.contracts.slots import Packer, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

from .clib import TAIL, Field, next_rand, read_lib

SLOT = SlotDefinition("pack.clib", "pack", "ags", "clib-writer")


def _put(toc: bytearray, where: Field, value: int) -> None:
    raw = value.to_bytes(where.width, "little")
    if where.rand is not None:
        state, out = where.rand, bytearray()
        for b in raw:
            state, r = next_rand(state)
            out.append((b + r) & 0xFF)
        raw = bytes(out)
    toc[where.at : where.at + where.width] = raw


def copy(src, out, offset: int, size: int) -> None:
    src.seek(offset)
    while size > 0:
        chunk = src.read(min(size, 1 << 20))
        if not chunk:
            raise ValueError("an asset runs past the end of its library")
        out.write(chunk)
        size -= len(chunk)


def _check(lib, edits: dict) -> None:
    if lib.index:
        raise ValueError(f"part {lib.index} of a library: its table is in the first part")
    unknown = sorted(set(edits) - {a.name for a in lib.assets})
    if unknown:
        raise ValueError(f"not in the library (AGS reads its assets from it): {unknown[:3]}")


def rebuild(path: Path, edits: dict[str, Path], temp: Path) -> int:
    """Write the library with the edits into temp; returns how many moved out of other parts."""
    lib = read_lib(path)
    _check(lib, edits)
    limit, moved = 1 << (32 if lib.version < 30 else 62), 0
    with open(path, "rb") as src, open(temp, "wb") as out:
        copy(src, out, 0, lib.base)  # the executable before it, when there is one
        src.seek(lib.base)
        toc = bytearray(src.read(lib.end))
        out.write(toc)
        at = lib.end
        for asset in lib.assets:
            edited = edits.get(asset.name)
            if asset.uid and edited is None:
                continue  # stays in its part
            size = edited.stat().st_size if edited is not None else asset.size
            if at + size >= limit:
                raise ValueError(f"version {lib.version} holds no offset past 4 GiB")
            if "offset" in asset.fields:  # version 6 stores none: its data is in sequence
                _put(toc, asset.fields["offset"], at)
            _put(toc, asset.fields["size"], size)
            if asset.uid:
                _put(toc, asset.fields["uid"], 0)
                moved += 1
            if edited is not None:
                with open(edited, "rb") as fh:
                    shutil.copyfileobj(fh, out)
            else:
                copy(src, out, lib.base + asset.offset, size)
            at += size
        if lib.ender:
            out.write(lib.base.to_bytes(lib.ender, "little") + TAIL)
        out.seek(lib.base)
        out.write(toc)
    return moved


class ClibWriter(Packer):
    backend_id, owner, license = "clib-writer", "ags", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: reads the game's library

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        temp = container.with_name(container.name + ".viwo-tmp")
        try:
            moved = rebuild(container, members, temp)
            os.replace(temp, container)
        except (OSError, ValueError) as exc:
            temp.unlink(missing_ok=True)
            return Outcome(OutcomeKind.FAILED, error=f"{container.name}: {exc}"[:300])
        notes = (f"{moved} edited asset(s) moved from another part into this one",) if moved else ()
        return Outcome(OutcomeKind.OK, len(members), notes=notes)
