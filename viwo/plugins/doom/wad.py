"""WAD reading (IWAD / PWAD) and the in-process unpack backend."""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

from viwo.contracts.slots import Unarchiver
from viwo.contracts.types import Outcome, OutcomeKind
from viwo.contracts.workspace import next_free

from . import lumps

MAGICS = (b"IWAD", b"PWAD")
MARKER = re.compile(r"^(SS?|PP?|P\d|FF?|F\d|TX|HI|C|A|V)_(START|END)$")
SPACES = {"S": "sprites", "P": "patches", "F": "flats", "T": "textures", "H": "hires"}
SPACES |= {"C": "colormaps", "A": "acs", "V": "voxels"}
MAP_LUMPS = frozenset(
    "THINGS LINEDEFS SIDEDEFS VERTEXES SEGS SSECTORS NODES SECTORS REJECT BLOCKMAP BEHAVIOR "
    "SCRIPTS TEXTMAP ZNODES DIALOGUE ENDMAP LEFTOVERS".split()
)
UNSAFE = re.compile(r"[^A-Za-z0-9_\-\[\]^]")
RAW = re.compile(r"^(PLAYPAL|COLORMAP|ENDOOM|TEXTURE\d|PNAMES|GENMIDI|DMXGUSC?|DEMO\d+)$")


@dataclass(frozen=True)
class Lump:
    name: str
    offset: int
    size: int


def directory(path: Path) -> tuple[bytes, list[Lump]]:
    """(kind, lumps); ValueError when the header or directory is out of bounds."""
    size = path.stat().st_size
    with open(path, "rb") as fh:
        head = fh.read(12)
        if len(head) < 12 or head[:4] not in MAGICS:
            raise ValueError("not a WAD (no IWAD/PWAD header)")
        count, table = struct.unpack_from("<ii", head, 4)
        if count < 0 or table < 12 or table + 16 * count > size:
            raise ValueError("WAD directory lies outside the file")
        fh.seek(table)
        raw = fh.read(16 * count)
    entries = []
    for i in range(count):
        offset, length, name = struct.unpack_from("<ii8s", raw, 16 * i)
        if offset < 0 or length < 0 or offset + length > size:
            raise ValueError(f"lump {i} lies outside the file")
        entries.append(
            Lump(name.split(b"\0", 1)[0].decode("ascii", "replace").upper(), offset, length)
        )
    return head[:4], entries


def read(path: Path, lump: Lump) -> bytes:
    with open(path, "rb") as fh:
        fh.seek(lump.offset)
        return fh.read(lump.size)


def palette(path: Path, game_root: Path) -> bytes:
    """PLAYPAL from this WAD, else from an IWAD in the game folder (PWADs rarely ship one)."""
    for candidate in [path, *sorted(game_root.rglob("*.[wW][aA][dD]"))]:
        try:
            kind, entries = directory(candidate)
        except (OSError, ValueError):
            continue
        found = [e for e in entries if e.name == "PLAYPAL" and e.size >= 768]
        if found and (candidate == path or kind == b"IWAD"):
            return read(candidate, found[-1])[:768]
    return b""


def layout(entries: list[Lump]) -> list[tuple[Lump, str, str]]:
    """(lump, namespace, map name): namespaces from X_START/X_END markers, maps from markers
    followed by map lumps. Marker lumps themselves are dropped."""
    out, space, opener, current_map = [], "", "", ""
    for i, lump in enumerate(entries):
        marker = MARKER.match(lump.name)
        if marker:
            prefix = marker.group(1)
            if marker.group(2) == "START" and not space:
                space, opener = SPACES[prefix[0]], prefix
            elif marker.group(2) == "END" and prefix == opener:
                space, opener = "", ""
            continue
        nxt = entries[i + 1].name if i + 1 < len(entries) else ""
        if lump.name not in MAP_LUMPS and not lump.name.startswith("GL_"):
            current_map = lump.name if nxt in ("THINGS", "TEXTMAP") else ""
            if current_map:
                continue
        out.append((lump, space, current_map))
    return out


def convert(lump: Lump, data: bytes, space: str, pal: bytes) -> tuple[str, str, bytes]:
    """(folder, suffix, bytes) for one lump; unknown data stays a raw .lmp."""
    if not space and RAW.match(lump.name):
        return "lumps", ".lmp", data
    magic = lumps.by_magic(data)
    if magic:
        return (
            {".wav": "sounds", ".png": space or "graphics"}.get(magic, space or "music"),
            magic,
            data,
        )
    if space in ("sprites", "patches", "textures", "hires", "") and pal:
        if (image := lumps.picture(data, pal)) is not None:
            return space or "graphics", ".png", image
    if space == "flats" and pal and (image := lumps.flat(data, pal)) is not None:
        return "flats", ".png", image
    if not space and (sound := lumps.dmx_sound(data)) is not None:
        return "sounds", ".wav", sound
    if not space and lumps.is_text(data):
        return "text", ".txt", data
    return space or "lumps", ".lmp", data


class WadBuiltin(Unarchiver):
    """Pure-Python WAD reader: every lump out, pictures/flats to PNG, DMX sounds to WAV."""

    backend_id, owner, license = "wad-builtin", "doom", "MIT"

    def extract(self, archive, dest, ctx) -> Outcome:
        try:
            _, entries = directory(archive)
        except (OSError, ValueError) as exc:
            return Outcome(OutcomeKind.FAILED, error=str(exc))
        pal, raw, written = palette(archive, ctx.game_root), bool(ctx.options.get("raw_lumps")), 0
        for lump, space, map_name in layout(entries):
            if ctx.cancel.cancelled:
                break
            data, name = read(archive, lump), UNSAFE.sub("_", lump.name) or "UNNAMED"
            if map_name:
                folder, suffix = "maps", ".txt" if lump.name == "TEXTMAP" else ".lmp"
                name, out = f"{UNSAFE.sub('_', map_name)}_{name}", data
            else:
                folder, suffix, out = convert(lump, data, space, pal)
            written += _write(dest / folder / f"{name}{suffix}", out)
            if raw and suffix != ".lmp":
                written += _write(dest / "lumps" / f"{name}.lmp", data)
        notes = () if pal else ("no PLAYPAL palette found: pictures kept as raw lumps",)
        return Outcome(OutcomeKind.OK, written, notes=notes)


def _write(target: Path, data: bytes) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    next_free(target).write_bytes(data)
    return 1
