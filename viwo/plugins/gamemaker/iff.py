"""GameMaker Studio data files (`data.win`, `game.unx`, `game.ios`, `game.droid`, audiogroup
`.dat`): the IFF/RIFF-like `FORM` container, read first-party from its public description
(UndertaleModTool). A `FORM` chunk (`FORM` + little-endian u32 size) holds named sub-chunks
(`NAME` + u32 size + payload, contiguous), the first of them `GEN8`.

Surfaced (each byte region of the file shown exactly once, so a repack reads back cleanly):

- `TXTR` texture pages: each embedded PNG (self-delimiting) to `textures/NNNN.png`;
- `AUDO` embedded audio: a pointer list (u32 count, u32 absolute offsets, each a u32 size + data)
  to `audio/NNNN.wav` / `.ogg` / `.bin` by the stored header;
- `STRG` strings: a pointer list (u32 count, u32 absolute offsets to a u32 length + UTF-8 + NUL)
  decoded to `strings.json`, a read-only view (its way back would move every string pointer);
- every other chunk's payload raw as `chunks/<NAME>.bin`, so the whole container is surfaced.

The way back writes an edited member in place when its byte length is unchanged (every absolute
offset in the file stays valid); a size change, and an edit to `strings.json`, are refused by
name, because full re-chunking (which would move every pointer target across every chunk) is not
done. Not verified against a built GameMaker game."""

import struct

MAGIC, FIRST = b"FORM", b"GEN8"
PNG_SIG = b"\x89PNG\r\n\x1a\n"
DECODED = ("TXTR", "AUDO", "STRG")  # shown as assets/JSON, not as raw chunks (no overlap)


def read_form(blob: bytes) -> list[tuple[str, int, int]]:
    """[(chunk name, payload offset, payload size)]; ValueError when not a GameMaker FORM."""
    if blob[:4] != MAGIC:
        raise ValueError("not a GameMaker data file (no FORM header)")
    total = struct.unpack_from("<I", blob, 4)[0]
    end, at, out = min(8 + total, len(blob)), 8, []
    while at + 8 <= end:
        name = blob[at : at + 4].decode("latin-1")
        size = struct.unpack_from("<I", blob, at + 4)[0]
        start = at + 8
        if start + size > len(blob):
            raise ValueError(f"chunk {name} runs past the end")
        out.append((name, start, size))
        at = start + size
    if not out or out[0][0] != FIRST.decode():
        raise ValueError("not a GameMaker data file (first chunk is not GEN8)")
    return out


def _png_end(payload: bytes, start: int) -> int | None:
    """The offset past a complete PNG beginning at `start`, or None when it is cut short."""
    at = start + 8
    while at + 8 <= len(payload):
        length = struct.unpack_from(">I", payload, at)[0]
        kind = payload[at + 4 : at + 8]
        at += 12 + length  # u32 length + 4-byte type + data + u32 CRC
        if kind == b"IEND":
            return at if at <= len(payload) else None
    return None


def pngs(payload: bytes, base: int) -> list[tuple[int, int]]:
    """(absolute offset, length) of every complete PNG in a chunk payload (self-delimiting)."""
    out, at = [], payload.find(PNG_SIG)
    while at >= 0:
        end = _png_end(payload, at)
        if end is None:
            break
        out.append((base + at, end - at))
        at = payload.find(PNG_SIG, end)
    return out


def pointer_list(blob: bytes, off: int, size: int) -> list[int]:
    """The absolute offsets of a pointer-list chunk (u32 count, then one u32 offset each)."""
    count = struct.unpack_from("<I", blob, off)[0]
    if count < 0 or off + 4 + count * 4 > off + size:
        raise ValueError("pointer list runs past its chunk")
    return [struct.unpack_from("<I", blob, off + 4 + i * 4)[0] for i in range(count)]


def _sized(blob: bytes, offsets: list[int]) -> list[tuple[int, int]]:
    """(data offset, length) of each u32-length-prefixed entry a pointer list points at."""
    out = []
    for o in offsets:
        if o + 4 > len(blob):
            raise ValueError("list entry runs past the end")
        length = struct.unpack_from("<I", blob, o)[0]
        if o + 4 + length > len(blob):
            raise ValueError("list entry data runs past the end")
        out.append((o + 4, length))
    return out


def _audio_ext(head: bytes) -> str:
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    return "ogg" if head[:4] == b"OggS" else "bin"


def surface(blob: bytes) -> tuple[dict[str, tuple[int, int]], list[str] | None, list[str]]:
    """(member path -> (offset, length) of each writable member, decoded strings or None, notes).
    Writable members never overlap: TXTR/AUDO/STRG show as assets/JSON, the rest as raw chunks."""
    ranges: dict[str, tuple[int, int]] = {}
    notes: list[str] = []
    strs: list[str] | None = None
    tex = aud = 0
    for name, off, size in read_form(blob):
        if name == "TXTR":
            for at, length in pngs(blob[off : off + size], off):
                ranges[f"textures/{tex:04d}.png"] = (at, length)
                tex += 1
        elif name == "AUDO":
            for start, length in _sized(blob, pointer_list(blob, off, size)):
                ext = _audio_ext(blob[start : start + 12])
                ranges[f"audio/{aud:04d}.{ext}"] = (start, length)
                aud += 1
        elif name == "STRG":
            strs = [
                blob[start : start + length].decode("utf-8", "replace")
                for start, length in _sized(blob, pointer_list(blob, off, size))
            ]
        else:
            ranges[f"chunks/{name}.bin"] = (off, size)
    if tex:
        notes.append(f"{tex} texture PNG(s) (texture-page metadata is not a writable member)")
    if aud:
        notes.append(f"{aud} embedded audio file(s)")
    if strs is not None:
        notes.append(f"{len(strs)} string(s) to strings.json (a read-only view)")
    return ranges, strs, notes


def plan_edits(
    ranges: dict[str, tuple[int, int]], members: dict
) -> list[tuple[tuple[int, int], bytes]]:
    """Each edit as ((offset, length), bytes); ValueError by name for an unknown member or a
    size change (the file's absolute offsets would move, and re-chunking is not done)."""
    out = []
    for member, path in sorted(members.items()):
        rng = ranges.get(member)
        if rng is None:
            raise ValueError(f"{member}: not a writable member (strings.json is a read-only view)")
        data = path.read_bytes()
        if len(data) != rng[1]:
            raise ValueError(f"{member}: size changed ({len(data)} vs {rng[1]}); re-chunk not done")
        out.append((rng, data))
    return out
