"""pack.tpac (doc 18.4): a TaleWorlds TPAC package rewritten in the patched copy with its edited
members, every other byte kept (layout in __init__.py, measured on Bannerlord's packages).

- `<item>.<n>.bin`: segment n's data replaced, any size.
- `<item>.dds`: the texture's largest segment. Its width, height, mip count and pixel format
  stay as extracted (the item's metadata holds them and is not rewritten): an edited DDS whose
  header differs is refused with what changed. A segment of that texture holding the tail of
  the old chain (Bannerlord keeps the chain from mip 1 as a segment of its own) gets the tail of
  the new one; a segment that is not is left as it was, and said.
- A segment stored as LZ4 is compressed again as the game's packages are (LZ4 HC, level 12: the
  same data gives the same bytes); without the lz4 package it is stored raw (format 0), said.
- New data goes where the old was when it fits and no other entry reads those bytes, the rest
  zeroed; else at the end of the file (the old bytes stay, unread). The entry's offset, sizes,
  format and xxHash64 are updated; the index keeps its size, every other byte is unchanged.
- An item's 8-byte checksum is kept: what it hashes is not known (not the metadata, not the
  data); packages whose checksums are all 0 load, so the game is not known to check it."""

import os
import shutil
import struct
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.slots import Packer, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

from .textures import CUBE_TAG, TEXTURE, dds, shape
from .xxh64 import xxh64

SLOT = SlotDefinition("pack.tpac", "pack", "taleworlds", "tpac-writer")


def outputs(items: list, dest: Path) -> dict[str, tuple[int, int | None]]:
    """member name -> (item, segment; None: the texture's DDS), named as extraction names them."""
    names, out = ws.Names(dest), {}
    for i, (name, segments, kind, meta) in enumerate(items):
        target = names.target(name)
        if target is None:
            continue
        rel = target.relative_to(dest).as_posix()
        out |= {f"{rel}.{n}.bin": (i, n) for n in range(len(segments))}
        if _texture(items[i]):
            out[f"{rel}.dds"] = (i, None)
    return out


def _texture(item) -> tuple | None:
    """(format, shape, faces, the largest segment's index) of a texture extracted as a DDS."""
    _, segments, kind, meta = item
    if kind != TEXTURE or not segments:
        return None
    faces = 6 if CUBE_TAG in meta else 1
    big = max(range(len(segments)), key=lambda n: segments[n][1])
    found = shape(meta, segments[big][1], faces)
    return (*found, faces, big) if found else None


def _read(fh, segment) -> bytes:
    """A segment's data, uncompressed."""
    offset, actual, stored, fmt = segment[:4]
    fh.seek(offset)
    raw = fh.read(stored)
    if len(raw) < stored:
        raise ValueError("a segment past the end of the package")
    if fmt == 0 or (fmt == 1 and stored == actual):
        return raw
    if fmt != 1:
        raise ValueError(f"segment storage format {fmt} is not known")
    try:
        import lz4.block
    except ImportError:
        raise ValueError("an LZ4 segment: the lz4 package is needed (pip install lz4)") from None
    return lz4.block.decompress(raw, uncompressed_size=actual)


def _dds_writes(fh, item, edited: bytes, member: str) -> tuple[list, list[str]]:
    """(segment, new data) of an edited texture DDS, and what was left as it was."""
    fmt, size, faces, big = _texture(item)
    head = dds(b"", fmt, size, faces)
    if edited[: len(head)] != head or len(edited) - len(head) != item[1][big][1]:
        h, w = struct.unpack_from("<II", edited, 12) if len(edited) >= 20 else (0, 0)
        held = f"{size[0]}x{size[1]}, {size[2]} mip(s), {fmt}"
        raise ValueError(f"{member}: the edit ({w}x{h}) must keep the texture's {held}")
    new, old, left = edited[len(head) :], _read(fh, item[1][big]), []
    writes = [(item[1][big], new)]
    for n, segment in enumerate(item[1]):
        if n == big:
            continue
        data = _read(fh, segment)
        if len(data) < len(old) and old.endswith(data):
            writes.append((segment, new[len(new) - len(data) :]))
        else:
            left.append(f"{member}: segment {n} is not a part of its chain: left as it was")
    return writes, left


def _stored(data: bytes, fmt: int) -> tuple[bytes, int, str]:
    """(bytes to store, storage format, a note when it had to change)."""
    if fmt != 1:
        return data, 0, ""
    try:
        import lz4.block
    except ImportError:
        return data, 0, "the lz4 package is missing: a segment was stored uncompressed"
    return (
        lz4.block.compress(data, mode="high_compression", compression=12, store_size=False),
        1,
        "",
    )


def _shared(segment, every: list) -> bool:
    """Whether another entry reads any byte of this segment's stored data."""
    start, end = segment[0], segment[0] + segment[2]
    return any(o is not segment and o[0] < end and start < o[0] + o[2] for o in every)


def _apply(fh, writes: list, every: list) -> list[str]:
    """Write each (segment, data) into the open copy and patch its entry; the notes."""
    notes = []
    for segment, data in writes:
        stored, fmt, note = _stored(data, segment[3])
        notes += [note] if note and note not in notes else []
        at = segment[0]
        if len(stored) > segment[2] or _shared(segment, every):
            at = fh.seek(0, os.SEEK_END)
        fh.seek(at)
        fh.write(stored + bytes(segment[2] - len(stored) if at == segment[0] else 0))
        fh.seek(segment[4])
        fh.write(struct.pack("<QQQ", at, len(data), len(stored)))
        fh.seek(segment[4] + 56)
        fh.write(struct.pack("<Q", xxh64(data)))
        fh.seek(segment[4] + 68)
        fh.write(bytes((fmt,)))
    return notes


def _plan(fh, members: dict[str, Path], dest: Path) -> tuple[list, list, list[str]]:
    """(every segment, the writes, notes) for the edited members."""
    from . import entries

    items = list(entries(fh))
    every = [segment for item in items for segment in item[1]]
    named, writes, notes = outputs(items, dest), [], []
    for member, path in sorted(members.items()):
        if member not in named:
            notes.append(f"{member}: not a member of this package: not written")
            continue
        index, n = named[member]
        if n is not None:
            writes.append((items[index][1][n], path.read_bytes()))
            continue
        more, left = _dds_writes(fh, items[index], path.read_bytes(), member)
        writes, notes = writes + more, notes + left
    spots = [segment[4] for segment, _ in writes]
    if len(spots) != len(set(spots)):  # a texture's DDS and one of its .bin files
        raise ValueError("two edited members write the same segment: edit one of them")
    return every, writes, notes


def write_tpac(original: Path, members: dict[str, Path], target: Path) -> list[str]:
    """`target`: `original` with the edited members (see the module); the notes. Read back:
    every written segment must give the data meant for it."""
    with open(original, "rb") as fh:
        every, writes, notes = _plan(fh, members, original.parent / ".viwo-tpac-names")
    shutil.copyfile(original, target)
    with open(target, "r+b") as fh:
        notes += _apply(fh, writes, every)
    from . import entries

    with open(target, "rb") as fh:
        moved = {s[4]: s for item in entries(fh) for s in item[1]}
        for segment, data in writes:
            if _read(fh, moved[segment[4]]) != data:
                raise ValueError("a written segment did not read back as written")
    return notes


class TpacWriter(Packer):
    backend_id, owner, license = "tpac-writer", "taleworlds", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        temp = container.with_name(container.name + ".viwo-tmp")
        try:
            notes = write_tpac(container, members, temp)
            os.replace(temp, container)
        except (OSError, ValueError, IndexError, struct.error, ImportError) as exc:
            temp.unlink(missing_ok=True)
            return Outcome(OutcomeKind.FAILED, error=f"TPAC not rewritten: {exc}"[:300])
        return Outcome(OutcomeKind.OK, len(members), notes=tuple(notes))
