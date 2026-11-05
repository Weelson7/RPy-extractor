"""pack.wad (doc 18): an edited IWAD/PWAD rebuilt in the patched copy. A member is found by the
name the unpacker gave its lump; what was converted on the way out is converted back: a PNG to
a Doom picture (posts per column, the grAb offsets kept) or a flat through the game's palette
(nearest colour, alpha < 128 transparent), a WAV to DMX sound; every other lump is written as
it is. Lumps keep their order (markers included). The read-back decodes the new lumps again and
compares them with the edit after the palette mapping, the only loss the format imposes."""

from __future__ import annotations

import io
import os
import struct
import wave
from pathlib import Path

from viwo.contracts.slots import Packer, SlotDefinition
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

from . import lumps
from .wad import UNSAFE, convert, directory, layout, palette, read

SLOT = SlotDefinition("pack.wad", "pack", "doom", "wad-writer")
PILLOW = DependencySpec("pillow", "Pillow", kind="python", import_name="PIL")


def members(path: Path, pal: bytes) -> dict[str, tuple[int, str]]:
    """member name -> (lump index, how it was converted: picture, flat, dmx or raw)."""
    _, entries = directory(path)
    index = {id(lump): i for i, lump in enumerate(entries)}
    out: dict[str, tuple[int, str]] = {}
    for lump, space, map_name in layout(entries):
        name = UNSAFE.sub("_", lump.name) or "UNNAMED"
        data = read(path, lump)
        if map_name:
            folder, suffix, how = "maps", ".txt" if lump.name == "TEXTMAP" else ".lmp", "raw"
            name = f"{UNSAFE.sub('_', map_name)}_{name}"
        else:
            folder, suffix, shown = convert(lump, data, space, pal)
            how = (
                "raw"
                if shown == data
                else {"flats": "flat", "sounds": "dmx"}.get(folder, "picture")
            )
        member, n = f"{folder}/{name}{suffix}", 1
        while member in out:  # the unpacker's next free name
            member, n = f"{folder}/{name}__{n}{suffix}", n + 1
        out[member] = (index[id(lump)], how)
    return out


def _indices(png: bytes, pal: bytes) -> tuple[int, int, list[int | None], tuple[int, int]]:
    from PIL import Image

    with Image.open(io.BytesIO(png)) as img:
        rgba = img.convert("RGBA")
    grab = _grab(png)
    colours = [tuple(pal[i * 3 : i * 3 + 3]) for i in range(256)]
    cache: dict[tuple, int] = {}

    def nearest(r, g, b):
        key = (r, g, b)
        if key not in cache:
            cache[key] = min(
                range(256), key=lambda i: sum((a - c) ** 2 for a, c in zip(key, colours[i]))
            )
        return cache[key]

    pixels = [None if a < 128 else nearest(r, g, b) for r, g, b, a in rgba.getdata()]
    return rgba.width, rgba.height, pixels, (int(grab[0]), int(grab[1]))


def _grab(png: bytes) -> tuple[int, int]:
    """The grAb chunk (ZDoom's picture offsets) the unpacker wrote, else (0, 0)."""
    at = 8
    while at + 8 <= len(png):
        size, kind = struct.unpack_from(">I4s", png, at)
        if kind == b"grAb" and size == 8:
            return struct.unpack_from(">ii", png, at + 8)
        at += 12 + size
    return 0, 0


def picture(width: int, height: int, pixels: list, offsets: tuple[int, int]) -> bytes:
    """Doom picture: header, column offsets, then per column its posts (at most 254 high)."""
    if height > 254:
        raise ValueError("pictures taller than 254 pixels are not written yet")
    columns = []
    for x in range(width):
        column, y = bytearray(), 0
        while y < height:
            if pixels[y * width + x] is None:
                y += 1
                continue
            run = []
            while y < height and pixels[y * width + x] is not None and len(run) < 128:
                run.append(pixels[y * width + x])
                y += 1
            top = y - len(run)
            column += bytes([top, len(run), run[0]]) + bytes(run) + bytes([run[-1]])
        columns.append(bytes(column) + b"\xff")
    table, body, at = b"", b"", 8 + 4 * width
    for column in columns:
        table, body = table + struct.pack("<I", at + len(body)), body + column
    return struct.pack("<HHhh", width, height, *offsets) + table + body


def dmx(data: bytes) -> bytes:
    """WAV (any width, mono or stereo) to DMX: 8-bit unsigned mono, 16 pad samples each side."""
    with wave.open(io.BytesIO(data)) as w:
        rate, width, channels = w.getframerate(), w.getsampwidth(), w.getnchannels()
        frames = w.readframes(w.getnframes())
    step = width * channels
    samples = bytearray()
    for i in range(0, len(frames) - step + 1, step):
        value = frames[i + width - 1]  # the most significant byte of the first channel
        samples.append(value if width == 1 else (value + 128) & 0xFF)
    first, last = samples[:1] or b"\x80", samples[-1:] or b"\x80"
    body = first * 16 + bytes(samples) + last * 16
    return struct.pack("<HHI", 3, rate, len(body)) + body


def encode(how: str, data: bytes, pal: bytes) -> bytes:
    if how == "raw":
        return data
    if how == "dmx":
        return dmx(data)
    width, height, pixels, grab = _indices(data, pal)
    if how == "flat":
        return bytes(0 if p is None else p for p in pixels)
    return picture(width, height, pixels, grab)


def write_wad(path: Path, edits: dict[int, bytes], target: Path) -> None:
    kind, entries = directory(path)
    body, table = bytearray(), bytearray()
    for i, lump in enumerate(entries):
        data = edits[i] if i in edits else read(path, lump)
        name = lump.name.encode("ascii", "replace")[:8].ljust(8, b"\0")
        table += struct.pack("<ii", 12 + len(body), len(data)) + name
        body += data
    target.write_bytes(kind + struct.pack("<ii", len(entries), 12 + len(body)) + body + table)


class WadWriter(Packer):
    backend_id, owner, license = "wad-writer", "doom", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process
    requires = (PILLOW,)

    def pack(self, container: Path, edited: dict[str, Path], ctx) -> Outcome:
        temp = container.with_name(container.name + ".viwo-tmp")
        try:
            pal = palette(container, container.parent)
            known = members(container, pal)
            edits = {
                known[m][0]: encode(known[m][1], src.read_bytes(), pal)
                for m, src in edited.items()
                if m in known
            }
            write_wad(container, edits, temp)
            os.replace(temp, container)
        except (OSError, ValueError, struct.error, wave.Error) as exc:
            temp.unlink(missing_ok=True)
            return Outcome(OutcomeKind.FAILED, error=f"WAD not rebuilt: {exc}"[:300])
        unknown = sorted(set(edited) - set(known))
        notes = (f"{len(unknown)} member(s) the WAD does not hold: not added",) if unknown else ()
        return Outcome(OutcomeKind.OK, len(edits), notes=notes)

    def verify(self, output: Path, edited: dict[str, Path], ctx) -> list[str]:
        """Each edited lump decoded again equals the edit as the palette can hold it."""
        pal = palette(output, output.parent)
        known, (_, entries) = members(output, pal), directory(output)
        bad = []
        for member, src in edited.items():
            if member not in known:
                bad.append(member)
                continue
            index, how = known[member]
            written = read(output, entries[index])
            if written != encode(how, src.read_bytes(), pal):
                bad.append(member)
        return sorted(bad)


def decoded(data: bytes, how: str, pal: bytes) -> bytes:
    """What the unpacker shows for a lump (used by tests): PNG or WAV bytes."""
    if how == "flat":
        return lumps.flat(data, pal) or b""
    if how == "dmx":
        return lumps.dmx_sound(data) or b""
    return lumps.picture(data, pal) or b"" if how == "picture" else data
