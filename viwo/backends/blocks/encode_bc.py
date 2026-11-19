"""Block compression for the way back of decode.image and decode.ctex (doc 18.3): BC1, BC2, BC3,
BC4 and BC5 written from 8-bit RGBA pixels (BC6H and BC7: encode_bptc.py), first-party, pure
Python, deterministic (the same pixels give the same bytes). Correctness over quality: each 4x4
block is fitted on its own range.

- Colour (BC1, the colour half of BC3): the endpoints are the corners of the block's colour
  box, along the diagonal its covariance points to (a block of two colours gets exactly those
  two), rounded to RGB565; each pixel takes the palette entry nearest its projection on that
  line. A flat block takes the endpoint pair whose 2/3 mix shows the colour best: exactly, as
  ffmpeg (ViWo's decoder) expands RGB565, for every colour an endpoint holds; within 1 for the
  others and under Pillow's expansion (no BC1 block can do better for every colour).
- BC1 alpha: a pixel under 128 is transparent (the 3-colour mode, index 3); a block with none
  uses the 4-colour mode. A fully transparent block is transparent black.
- BC2 alpha: each pixel's 4 bits, the nearest step of 17 (within 8); its colour half as BC3's.
- Single channel (BC4, both halves of BC5, the alpha half of BC3): the block's minimum and
  maximum, eight levels between them; each value takes the nearest level, so 0 and 255 are
  exact and no value is further than (max - min) / 14, plus the decoder's rounding.
Blocks at the right and bottom edge repeat the last column and row."""

import struct
from operator import mul

KINDS = {"BC1": 8, "BC2": 16, "BC3": 16, "BC4": 8, "BC5": 16}  # bytes per 4x4 block
KINDS |= {"BC4S": 8, "BC5S": 16, "DXT2": 16, "DXT4": 16}  # signed BC4/BC5, premultiplied BC2/BC3
BPTC = {"BC6H": 16, "BC6HS": 16, "BC7": 16}  # encode_bptc.py: BC6H unsigned and signed, BC7
KINDS |= BPTC


def _expand(bits: int) -> list[int]:
    """An endpoint channel in 8 bits as ffmpeg (ViWo's decoder) expands it: about x * 255 / 31
    (or / 63), by its integer formula."""
    top, half = 1 << bits, 1 << (bits - 1)
    return [((x * 255 + half) // top + x * 255 + half) // top for x in range(top)]


def _replicate(bits: int) -> list[int]:
    """The same as Pillow and other decoders expand it: the high bits repeated."""
    return [(x << (8 - bits)) | (x >> (2 * bits - 8)) for x in range(1 << bits)]


E5, E6 = _expand(5), _expand(6)
Q5 = [min(range(32), key=lambda c: abs(E5[c] - v)) for v in range(256)]
Q6 = [min(range(64), key=lambda c: abs(E6[c] - v)) for v in range(256)]


def _single(bits: int) -> list[tuple[int, int]]:
    """value -> (code a, code b) whose 2/3 a + 1/3 b shows it best under both expansions
    (within 1 for every value), exactly under ffmpeg's where it can."""
    best: dict[int, tuple] = {}
    ours, theirs = _expand(bits), _replicate(bits)
    for a in range(1 << bits):
        for b in range(1 << bits):
            s, t = (2 * ours[a] + ours[b]) // 3, (2 * theirs[a] + theirs[b]) // 3
            for v in range(max(0, s - 1), min(255, s + 1) + 1):
                cost = (max(abs(s - v), abs(t - v)), abs(s - v))
                if v not in best or cost < best[v][0]:
                    best[v] = (cost, a, b)
    return [best[v][1:] for v in range(256)]


S5, S6 = _single(5), _single(6)


def _rgb565(r: int, g: int, b: int) -> int:
    return (r << 11) | (g << 5) | b


def _flat(r: int, g: int, b: int) -> bytes:
    """A block of one colour, every pixel on index 2 (2/3 c0 + 1/3 c1)."""
    c0 = _rgb565(S5[r][0], S6[g][0], S5[b][0])
    c1 = _rgb565(S5[r][1], S6[g][1], S5[b][1])
    if c0 == c1:
        return struct.pack("<HHI", c0, c1, 0)
    if c0 < c1:  # the 4-colour mode needs c0 > c1: swapped, the same mix is index 3
        return struct.pack("<HHI", c1, c0, 0xFFFFFFFF)
    return struct.pack("<HHI", c0, c1, 0xAAAAAAAA)


def corners(chans: tuple) -> tuple[list, list]:
    """The two corners of the colour box of the pixels that count (their values per channel:
    R, G and B, or more), on the diagonal the covariance with the widest channel points to."""
    lo, hi = [min(c) for c in chans], [max(c) for c in chans]
    main = max(range(len(chans)), key=lambda k: hi[k] - lo[k])
    n, m = len(chans[0]), chans[main]
    total = sum(m)
    for k in range(len(chans)):  # the sign of n * cov: below 0, it falls as the main rises
        if k != main and n * sum(map(mul, m, chans[k])) < total * sum(chans[k]):
            lo[k], hi[k] = hi[k], lo[k]
    return hi, lo


def _rgb(c: int) -> tuple[int, int, int]:
    """An RGB565 endpoint as the decoder expands it."""
    return E5[c >> 11], E6[(c >> 5) & 63], E5[c & 31]


def _color(r: bytes, g: bytes, b: bytes, alpha: bytes | None) -> bytes:
    """One BC1 colour block. alpha None: always 4 colours (BC3); else BC1 with punch-through."""
    clear = [] if alpha is None else [i for i in range(16) if alpha[i] < 128]
    if len(clear) == 16:
        return struct.pack("<HHI", 0, 0, 0xFFFFFFFF)  # transparent black
    if clear:
        chans = tuple([c[i] for i in range(16) if alpha[i] >= 128] for c in (r, g, b))
    elif r.count(r[0]) == 16 and g.count(g[0]) == 16 and b.count(b[0]) == 16:
        return _flat(r[0], g[0], b[0])
    hi, lo = corners(chans if clear else (r, g, b))
    c0 = _rgb565(Q5[hi[0]], Q6[hi[1]], Q5[hi[2]])
    c1 = _rgb565(Q5[lo[0]], Q6[lo[1]], Q5[lo[2]])
    if (c0 > c1) if clear else (c0 < c1):  # 4 colours: c0 > c1; 3 and transparent: c0 <= c1
        c0, c1 = c1, c0
    codes = _codes((r, g, b), _rgb(c0), _rgb(c1), not clear)
    for i in clear:
        codes[i] = 3
    bits = 0
    for code in reversed(codes):
        bits = (bits << 2) | code
    return struct.pack("<HHI", c0, c1, bits)


def _codes(rgb: tuple, p0: tuple, p1: tuple, four: bool) -> list[int]:
    """Each pixel's palette index, from where it projects on the line p1 -> p0."""
    d0, d1, d2 = p0[0] - p1[0], p0[1] - p1[1], p0[2] - p1[2]
    dd = d0 * d0 + d1 * d1 + d2 * d2
    if not dd:
        return [0] * 16
    at = p1[0] * d0 + p1[1] * d1 + p1[2] * d2
    ts = [x * d0 + y * d1 + z * d2 - at for x, y, z in zip(*rgb)]
    if four:  # p1 at 0, index 3 at 1/3, index 2 at 2/3, p0 at 1
        a, b, c = dd, 3 * dd, 5 * dd
        return [1 if 6 * t < a else 3 if 6 * t < b else 2 if 6 * t < c else 0 for t in ts]
    return [1 if 4 * t < dd else 2 if 4 * t < 3 * dd else 0 for t in ts]  # p1, the half, p0


def _single_channel(v: bytes, signed: bool = False) -> bytes:
    """One BC4 block (8 levels from the maximum to the minimum). `signed` (SNORM BC4S/BC5S): the
    same block with each endpoint byte offset by 128, which a decoder reads back as s + 128 (the
    interpolation cancels the offset), so a signed block is the unsigned one with its two endpoint
    bytes XORed by 0x80."""
    hi, lo = max(v), min(v)
    if hi == lo:
        block = bytes((hi, lo)) + bytes(6)
    else:
        span, half, bits = hi - lo, (hi - lo) // 2, 0
        for i in range(16):
            step = ((hi - v[i]) * 7 + half) // span  # 0 = hi ... 7 = lo
            bits |= (0 if step == 0 else 1 if step == 7 else step + 1) << (3 * i)
        block = bytes((hi, lo)) + bits.to_bytes(6, "little")
    return bytes((block[0] ^ 0x80, block[1] ^ 0x80)) + block[2:] if signed else block


def _premul(c: bytes, a: bytes) -> bytes:
    """A colour channel premultiplied by alpha (DXT2/DXT4): round(c * a / 255) per pixel."""
    return bytes((v * al + 127) // 255 for v, al in zip(c, a))


def _explicit(a: bytes) -> bytes:
    """BC2's alpha half: each pixel's alpha in 4 bits, the nearest of the 16 steps of 17."""
    bits = 0
    for i in range(16):
        bits |= ((a[i] + 8) // 17) << (4 * i)
    return bits.to_bytes(8, "little")


def _block(kind: str, px: bytes) -> bytes:
    """One block from 64 bytes of RGBA (16 pixels, row by row)."""
    r, g, b, a = px[0::4], px[1::4], px[2::4], px[3::4]
    if kind == "BC1":
        return _color(r, g, b, a if min(a) < 128 else None)
    if kind in ("DXT2", "DXT4"):  # premultiplied: colour times alpha, the alpha half unchanged
        r, g, b = _premul(r, a), _premul(g, a), _premul(b, a)
        kind = "BC2" if kind == "DXT2" else "BC3"
    if kind in ("BC2", "BC3"):
        alpha = _explicit(a) if kind == "BC2" else _single_channel(a)
        return alpha + _color(r, g, b, None)
    signed = kind in ("BC4S", "BC5S")
    if kind in ("BC4", "BC4S"):
        return _single_channel(r, signed)
    return _single_channel(r, signed) + _single_channel(g, signed)


def size(kind: str, width: int, height: int) -> int:
    """Bytes of one image of this size."""
    return ((width + 3) // 4) * ((height + 3) // 4) * KINDS[kind]


def compress(rgba: bytes, width: int, height: int, kind: str) -> bytes:
    """The blocks of one image (RGBA bytes, row by row), left to right, top to bottom."""
    if kind not in KINDS:
        raise ValueError(f"{kind} is not a block format ViWo writes")
    if kind in BPTC:
        from .encode_bptc import block as encode

        one = lambda px: encode(kind, px)  # noqa: E731
    else:
        one = lambda px: _block(kind, px)  # noqa: E731
    w4 = (width + 3) // 4 * 4
    rows = []
    for y in range((height + 3) // 4 * 4):
        row = rgba[min(y, height - 1) * width * 4 : (min(y, height - 1) + 1) * width * 4]
        rows.append(row + row[-4:] * (w4 - width))
    out = bytearray()
    for y in range(0, len(rows), 4):
        band = rows[y : y + 4]
        for x in range(0, w4 * 4, 16):
            out += one(b"".join(row[x : x + 16] for row in band))
    return bytes(out)
