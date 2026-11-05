"""SLP sprites (Age of Empires I/II, Genie engine) to PNG: one sprite sheet per SLP, its frames
side by side (16 per row), drawn with the game's own palette (interfac.drs, BINA 50500, a
JASC-PAL text) collected next to it in the workspace. Player colours are player 1's, shadows
half-transparent black, outlines transparent.

Format (SLP 2.0N): header (version, frame count, comment), 32-byte frame records (command and
outline table offsets, palette, properties, width, height, hotspot), per row: left/right
padding (0x8000 = empty row) and a command stream ended by 0x0F."""

import struct
from pathlib import Path

from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

SLP_SLOT = SlotDefinition("decode.slp", "decode", "genie", "slp-builtin", suffixes=(".slp",))
PILLOW = DependencySpec(
    "pillow", "Pillow", kind="python", import_name="PIL", hint="pip install Pillow"
)
PALETTE = Path("bina") / "50500.bina"  # where the collect step puts interfac.drs's palette
PLAYER, SHADOW, PER_ROW = 16, (0, 0, 0, 128), 16


def palette(text: str) -> list[tuple[int, int, int, int]]:
    """JASC-PAL: 'JASC-PAL', '0100', the count, then one 'r g b' line per colour."""
    lines = text.split()
    if len(lines) < 3 or lines[0] != "JASC-PAL":
        raise ValueError("not a JASC-PAL palette")
    count = int(lines[2])
    values = [int(v) for v in lines[3 : 3 + 3 * count]]
    return [(*values[i : i + 3], 255) for i in range(0, 3 * count, 3)]


def _count(cmd: int, data: bytes, at: int) -> tuple[int, int]:
    """The run length of a 4-bit command: the high nibble, or the next byte when it is 0."""
    return (cmd >> 4, at) if cmd >> 4 else (data[at], at + 1)


def _row(data: bytes, at: int, colors: list, width: int = 4096) -> list:
    """One row's pixels after its left padding, until the 0x0F end-of-row command, or once
    the row is full; a row that needs more commands than its width could justify is damage
    (a crafted file could replay one long stream for every row of every frame)."""
    out: list = []
    for _ in range(2 * width + 64):
        if len(out) >= width:
            return out
        cmd = data[at]
        at += 1
        low2, low4 = cmd & 0x03, cmd & 0x0F
        if low4 == 0x0F:
            return out
        if low2 == 0x00:  # colour list, 6-bit count
            out += [colors[b] for b in data[at : at + (cmd >> 2)]]
            at += cmd >> 2
        elif low2 == 0x01:  # skip, 6-bit count
            out += [None] * (cmd >> 2)
        elif low4 in (0x02, 0x03):  # big colour list / big skip: 12-bit count
            n = ((cmd & 0xF0) << 4) + data[at]
            at += 1
            out += [colors[b] for b in data[at : at + n]] if low4 == 0x02 else [None] * n
            at += n if low4 == 0x02 else 0
        else:
            at = _special(cmd, low4, data, at, colors, out)
    raise ValueError("an SLP row runs on past its width")


def _special(cmd: int, low4: int, data: bytes, at: int, colors: list, out: list) -> int:
    if low4 == 0x0E:  # extended: outline pixel (x4E, x6E) or span (x5E, x7E)
        n = 1 if cmd in (0x4E, 0x6E) else data[at] if cmd in (0x5E, 0x7E) else 0
        out += [None] * n
        return at + (1 if cmd in (0x5E, 0x7E) else 0)
    n, at = _count(cmd, data, at)
    if low4 == 0x06:  # player colour list
        out += [colors[b + PLAYER] for b in data[at : at + n]]
        return at + n
    if low4 in (0x07, 0x0A):  # fill, player colour fill
        out += [colors[data[at] + (PLAYER if low4 == 0x0A else 0)]] * n
        return at + 1
    if low4 == 0x0B:  # shadow
        out += [SHADOW] * n
        return at
    raise ValueError(f"unknown SLP command 0x{cmd:02x}")


def frames(data: bytes, colors: list) -> list[tuple[int, int, list]]:
    """(width, height, rows of RGBA or None) per frame."""
    if not data[:4].startswith(b"2."):
        raise ValueError(f"not an SLP 2.x file ({data[:4]!r})")
    count = struct.unpack_from("<i", data, 4)[0]
    if not 0 < count < 10000:
        raise ValueError(f"frame count out of range: {count}")
    out = []
    for i in range(count):
        cmds, outline, _, _, width, height, _, _ = struct.unpack_from(
            "<IIIIiiii", data, 32 + 32 * i
        )
        if not (0 < width <= 4096 and 0 < height <= 4096):
            raise ValueError(f"frame {i}: size {width}x{height} out of range")
        rows = []
        for y in range(height):
            left, _right = struct.unpack_from("<HH", data, outline + 4 * y)
            if left == 0x8000:
                rows.append([])
                continue
            row = [None] * left + _row(
                data, struct.unpack_from("<I", data, cmds + 4 * y)[0], colors, max(width - left, 0)
            )
            rows.append(row[:width])
        out.append((width, height, rows))
    return out


def sheet(found: list[tuple[int, int, list]]):
    from PIL import Image

    cell_w, cell_h = max(w for w, _, _ in found), max(h for _, h, _ in found)
    cols = min(PER_ROW, len(found))
    image = Image.new("RGBA", (cell_w * cols, cell_h * -(-len(found) // cols)), (0, 0, 0, 0))
    pixels = image.load()
    for i, (_, _, rows) in enumerate(found):
        x0, y0 = (i % cols) * cell_w, (i // cols) * cell_h
        for y, row in enumerate(rows):
            for x, rgba in enumerate(row):
                if rgba is not None:
                    pixels[x0 + x, y0 + y] = rgba
    return image


class SlpDecoder(Decoder):
    backend_id, owner, license = "slp-builtin", "genie", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def dependencies(self):
        return (PILLOW,)

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        pal = path.parent.parent / PALETTE
        if not pal.is_file():
            return Outcome(OutcomeKind.FAILED, error="no palette: interfac.drs (BINA 50500)")
        try:
            colors = palette(pal.read_text(encoding="ascii", errors="replace"))
            found = frames(path.read_bytes(), colors)
            sheet(found).save(dest / f"{path.stem}.png")
        except (ValueError, IndexError, struct.error, OSError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{path.name}: {exc}")
        return Outcome(OutcomeKind.OK, 1, notes=(f"{len(found)} frame(s)",))
