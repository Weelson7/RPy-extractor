"""First-party block decoders, pure Python: BC1, BC2, BC3, BC4, BC5 and BC7 (decode_bc7.py) to
8-bit RGBA. Godot's VRAM-compressed textures decode through them (decode.ctex), and the block
encoder's tests decode with them. BC1 to BC3 colours expand their RGB565 endpoints as ffmpeg
(ViWo's DDS decoder) does, the endpoint expansion encode_bc.py fits, with truncating mixes; BC2
alpha is its 4 bits times 17. BC4 shows as grey, BC5 as red and green with blue 0."""

import struct

from .decode_bc7 import bc7
from .encode_bc import E5, E6

KINDS = {"BC1": 8, "BC2": 16, "BC3": 16, "BC4": 8, "BC5": 16, "BC7": 16}  # bytes per block


def bc1(block: bytes, four: bool = False) -> bytes:
    """16 RGBA pixels; `four`: always the 4-colour mode (the colour half of BC2 and BC3)."""
    c0, c1, bits = struct.unpack("<HHI", block)
    p = [(E5[c >> 11], E6[(c >> 5) & 63], E5[c & 31], 255) for c in (c0, c1)]
    if four or c0 > c1:
        p.append(tuple((2 * x + y) // 3 for x, y in zip(p[0], p[1])))
        p.append(tuple((x + 2 * y) // 3 for x, y in zip(p[0], p[1])))
    else:
        p += [tuple((x + y) // 2 for x, y in zip(p[0], p[1])), (0, 0, 0, 0)]
    colours = [bytes(c) for c in p]
    return b"".join(colours[(bits >> (2 * i)) & 3] for i in range(16))


def bc4(block: bytes) -> bytes:
    """16 values of one single-channel block (8 levels, or 6 with 0 and 255)."""
    a0, a1 = block[0], block[1]
    if a0 > a1:
        levels = [a0, a1] + [((7 - s) * a0 + s * a1) // 7 for s in range(1, 7)]
    else:
        levels = [a0, a1] + [((5 - s) * a0 + s * a1) // 5 for s in range(1, 5)] + [0, 255]
    bits = int.from_bytes(block[2:8], "little")
    return bytes(levels[(bits >> (3 * i)) & 7] for i in range(16))


def bc2_alpha(block: bytes) -> bytes:
    """16 explicit 4-bit alphas, pixel 0 in the low nibble of the first byte."""
    bits = int.from_bytes(block[:8], "little")
    return bytes(((bits >> (4 * i)) & 15) * 17 for i in range(16))


def pixels(block: bytes, kind: str) -> bytes:
    """The 16 RGBA pixels of one block of `kind`, row by row (64 bytes)."""
    if kind == "BC1":
        return bc1(block)
    if kind == "BC7":
        return bc7(block)
    if kind in ("BC2", "BC3"):
        out = bytearray(bc1(block[8:], True))
        out[3::4] = bc2_alpha(block) if kind == "BC2" else bc4(block[:8])
        return bytes(out)
    if kind not in ("BC4", "BC5"):
        raise ValueError(f"{kind} is not a block format ViWo decodes")
    out = bytearray(b"\xff" * 64)
    red = bc4(block[:8])
    out[0::4], out[1::4], out[2::4] = red, red, red
    if kind == "BC5":
        out[1::4], out[2::4] = bc4(block[8:]), bytes(16)
    return bytes(out)


def decompress(data: bytes, width: int, height: int, kind: str) -> bytes:
    """RGBA bytes of a `width` x `height` image from its blocks (left to right, top to bottom);
    ValueError when the data is cut short."""
    step = KINDS.get(kind, 0)
    if not step:
        raise ValueError(f"{kind} is not a block format ViWo decodes")
    across = (width + 3) // 4
    if len(data) < across * ((height + 3) // 4) * step:
        raise ValueError(f"{kind} data cut short")
    out, at = bytearray(width * height * 4), 0
    for by in range(0, height, 4):
        rows = range(min(4, height - by))
        for bx in range(0, width, 4):
            block = pixels(data[at : at + step], kind)
            at, span = at + step, 4 * min(4, width - bx)
            for r in rows:  # row r of the block: 16 bytes, cut at the image's edge
                start = 4 * ((by + r) * width + bx)
                out[start : start + span] = block[16 * r : 16 * r + span]
    return bytes(out)
