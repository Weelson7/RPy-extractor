"""The way back for decode.slp (doc 18.3): an edited sprite sheet written as the original SLP.

The sheet must keep the decoder's layout (16 frames per row, cells of the largest frame); each
frame keeps its size, hotspot, palette and properties, and the original's header. Pixels go
through the game's palette as the Doom packer does it (exact colour first, else the nearest):
transparent (alpha < 128) is skipped, the decoder's shadow colour is a shadow, a colour of
player 1's range (16-23) a player colour. The simplest valid encoding: colour lists, player
colour lists, shadows and skips per row, no fills (no run-length optimisation). Outline pixels,
which the decoder draws transparent, are not written back."""

import io
import struct

from .slp import PER_ROW, PLAYER, SHADOW

PLAYERS = range(PLAYER, PLAYER + 8)


class _Palette:
    def __init__(self, colors: list) -> None:
        self.colors = [c[:3] for c in colors]
        order = [i for i in range(len(colors)) if i not in PLAYERS] + list(PLAYERS)
        self.exact: dict = {}  # exact colours first; then each nearest one, once found
        for i in (i for i in order if i < len(colors)):
            self.exact.setdefault(self.colors[i], i)

    def index(self, rgb: tuple) -> int:
        if rgb not in self.exact:

            def distance(i: int) -> int:
                return sum((a - c) ** 2 for a, c in zip(rgb, self.colors[i]))

            self.exact[rgb] = min(range(len(self.colors)), key=distance)
        return self.exact[rgb]

    def pixel(self, rgba: tuple):
        """None (transparent), ("s",) shadow, ("p", n) player colour, ("c", i) colour."""
        if rgba == SHADOW:
            return ("s", 0)
        if rgba[3] < 128:
            return None
        i = self.index(rgba[:3])
        return ("p", i - PLAYER) if i in PLAYERS else ("c", i)


def _runs(row: list) -> list[tuple]:
    """Consecutive pixels of one kind: (kind, [values])."""
    runs: list = []
    for p in row:
        kind = "skip" if p is None else p[0]
        if runs and runs[-1][0] == kind:
            runs[-1][1].append(None if p is None else p[1])
        else:
            runs.append((kind, [None if p is None else p[1]]))
    return runs


def _command(kind: str, values: list) -> bytes:
    """One run as commands, split where a count field is full."""
    out = b""
    most = {"skip": 4095, "c": 4095, "p": 255, "s": 255}[kind]
    for at in range(0, len(values), most):
        part, n = values[at : at + most], len(values[at : at + most])
        if kind == "skip":
            out += bytes([n << 2 | 0x01]) if n < 64 else bytes([(n >> 8) << 4 | 0x03, n & 0xFF])
        elif kind == "c":
            head = bytes([n << 2]) if n < 64 else bytes([(n >> 8) << 4 | 0x02, n & 0xFF])
            out += head + bytes(part)
        else:  # player colours and shadows: a count in the high nibble, else the next byte
            low = 0x06 if kind == "p" else 0x0B
            out += bytes([n << 4 | low]) if n < 16 else bytes([low, n])
            out += bytes(part) if kind == "p" else b""
    return out


def _row(row: list) -> tuple[int, int, bytes]:
    """(left padding, right padding, commands) of one row; an empty row is 0x8000."""
    if all(p is None for p in row):
        return 0x8000, 0x8000, b"\x0f"
    left = next(i for i, p in enumerate(row) if p is not None)
    right = next(i for i, p in enumerate(reversed(row)) if p is not None)
    body = b"".join(_command(k, v) for k, v in _runs(row[left : len(row) - right]))
    return left, right, body + b"\x0f"


def _frames(png: bytes, original: bytes) -> tuple[list[tuple[bytes, list]], int]:
    """(the original's 32-byte frame record, rows of pixels) per frame, cut from the sheet,
    and how many painted pixels lie outside every frame (a frame keeps its size)."""
    from PIL import Image

    count = struct.unpack_from("<i", original, 4)[0]
    if not 0 < count < 10000:
        raise ValueError(f"frame count out of range: {count}")
    records = [original[32 + 32 * i : 64 + 32 * i] for i in range(count)]
    sizes = [struct.unpack_from("<ii", r, 16) for r in records]
    cell_w, cell_h = max(w for w, _ in sizes), max(h for _, h in sizes)
    cols = min(PER_ROW, count)
    want = (cell_w * cols, cell_h * -(-count // cols))
    with Image.open(io.BytesIO(png)) as opened:
        image = opened.convert("RGBA")
    if image.size != want:
        raise ValueError(f"the sheet is {image.size[0]}x{image.size[1]}, the SLP needs {want}")
    pixels, out, kept = image.load(), [], 0
    alpha = image.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    for i, (w, h) in enumerate(sizes):
        x0, y0 = (i % cols) * cell_w, (i // cols) * cell_h
        out.append((records[i], [[pixels[x0 + x, y0 + y] for x in range(w)] for y in range(h)]))
        kept += alpha.crop((x0, y0, x0 + w, y0 + h)).histogram()[255]
    return out, alpha.histogram()[255] - kept


def write_slp(png: bytes, original: bytes, colors: list) -> tuple[bytes, int]:
    """(the SLP, the painted pixels outside every frame, which no frame can hold)."""
    if not original[:4].startswith(b"2."):
        raise ValueError(f"not an SLP 2.x file ({original[:4]!r})")
    pal, (frames, outside) = _Palette(colors), _frames(png, original)
    records, body, base = b"", b"", 32 + 32 * len(frames)
    for record, rows in frames:
        coded = [_row([pal.pixel(p) for p in row]) for row in rows]
        outline_at = base + len(body)
        outline = b"".join(struct.pack("<HH", left, right) for left, right, _ in coded)
        cmds_at = outline_at + len(outline)
        offsets, stream = [], b""
        for _, _, commands in coded:
            offsets.append(cmds_at + 4 * len(coded) + len(stream))
            stream += commands
        body += outline + struct.pack(f"<{len(coded)}I", *offsets) + stream
        records += struct.pack("<II", cmds_at, outline_at) + record[8:]
    return original[:32] + records + body, outside
