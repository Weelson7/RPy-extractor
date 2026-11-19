"""BC7 and BC6H blocks for the way back of decode.image and decode.ctex (doc 18.3), first-party,
pure Python, deterministic, one mode each. Correctness over quality: every block is one line
through its colour box (the corners on the covariance's diagonal, encode_bc.corners), each pixel
on the weight nearest its projection on that line (4-bit indices, 16 weights).

- BC7: mode 6 only (one subset, RGBA endpoints of 7 bits plus a p-bit each). The p-bit is the
  one that brings an endpoint closest to its colour; an endpoint whose alpha is 0 or 255 takes
  the p-bit that holds that alpha exactly, so an opaque block stays opaque and a transparent
  one transparent; its colour channels are then within 1 of what was asked.
- BC6H: mode 11 only (one region, 10-bit endpoints, not transformed), unsigned (UF16) or
  signed (SF16, the endpoints' 9 bits of magnitude: values here are never negative). Its
  colours come from 8-bit pixels: each value v is aimed at the half float (v + 0.5) / 255 (0
  and 255 at 0.0 and 1.0), the middle of what Pillow (ViWo's BC6H decoder) shows as v, and
  placed in the unquantized integer space the format interpolates in. BC6H has no alpha."""

import struct

from .encode_bc import corners

CLAMPED = "BC6H holds HDR colour: shown clamped to 0..1 in 8 bits"  # said by its decoders
HDR = (  # said by the way back of each BC6H texture
    "BC6H written from the PNG's 8 bits: colour above 1.0 in the original was shown clamped "
    "and is not kept, and the format holds no alpha"
)
WEIGHTS = (0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64)
NEAR = [min(range(16), key=lambda k: abs(WEIGHTS[k] - t)) for t in range(65)]


def _half(v: int) -> int:
    f = 0.0 if v == 0 else 1.0 if v == 255 else (v + 0.5) / 255
    return struct.unpack("<H", struct.pack("<e", f))[0]


def unquantize(e: int, signed: bool) -> int:
    """A BC6H mode 11 endpoint in the integer space the format interpolates in."""
    if signed:
        return 0 if e == 0 else 0x7FFF if e >= 511 else ((e << 15) + 0x4000) >> 9
    return 0 if e == 0 else 0xFFFF if e == 1023 else ((e << 16) + 0x8000) >> 10


def finish(x: int, signed: bool) -> int:
    """The half float bits of an interpolated value (non-negative)."""
    return (x * 31) >> (5 if signed else 6)


# 8-bit value -> the smallest interpolation value that finishes as its half float
UF = [-(-64 * _half(v) // 31) for v in range(256)]
SF = [-(-32 * _half(v) // 31) for v in range(256)]
UQ = [unquantize(e, False) for e in range(1024)]
SQ = [unquantize(e, True) for e in range(512)]


def _nearest(u: int, table: list[int]) -> int:
    """The endpoint code whose unquantized value is nearest `u`."""
    guess = min(len(table) - 1, u >> 6)
    near = range(max(0, guess - 1), min(len(table), guess + 2))
    return min(near, key=lambda e: abs(table[e] - u))


def _indices(points: tuple, e0: list[int], e1: list[int]) -> list[int]:
    """Each pixel's index: the weight nearest its projection on the line e0 -> e1."""
    d = [b - a for a, b in zip(e0, e1)]
    dd = sum(x * x for x in d)
    if not dd:
        return [0] * 16
    at = sum(a * x for a, x in zip(e0, d))
    out = []
    for px in zip(*points):
        t = (sum(p * x for p, x in zip(px, d)) - at) * 64
        out.append(NEAR[min(64, max(0, (t + dd // 2) // dd))])
    return out


def _pack(head: tuple[int, int], fields: list[tuple[int, int]], idx: list[int]) -> bytes:
    """A 128-bit block: the mode, the fields, then the indices (the first one a bit short)."""
    bits, at = head
    for value, width in fields:
        bits, at = bits | (value << at), at + width
    for i, k in enumerate(idx):
        bits, at = bits | (k << at), at + (3 if i == 0 else 4)
    return bits.to_bytes(16, "little")


def _p_bit(point: list[int]) -> tuple[list[int], int]:
    """(7-bit codes, p-bit) of one BC7 endpoint (see the module for the alpha)."""
    choices = (1,) if point[3] == 255 else (0,) if point[3] == 0 else (0, 1)
    best = None
    for p in choices:
        codes = [min(127, max(0, (v - p + 1) // 2)) for v in point]
        err = sum(abs(2 * c + p - v) for c, v in zip(codes, point))
        if best is None or err < best[0]:
            best = (err, codes, p)
    return best[1], best[2]


def bc7(px: bytes) -> bytes:
    """One BC7 mode 6 block from 64 bytes of RGBA."""
    chans = (px[0::4], px[1::4], px[2::4], px[3::4])
    hi, lo = corners(chans)
    (c0, p0), (c1, p1) = _p_bit(hi), _p_bit(lo)
    e0, e1 = [2 * c + p0 for c in c0], [2 * c + p1 for c in c1]
    idx = _indices(chans, e0, e1)
    if idx[0] > 7:  # the first index has 3 bits: its top bit must be 0
        (c0, p0), (c1, p1), idx = (c1, p1), (c0, p0), [15 - k for k in idx]
    fields = [(v, 7) for c in range(4) for v in (c0[c], c1[c])] + [(p0, 1), (p1, 1)]
    return _pack((1 << 6, 7), fields, idx)


def bc6h(px: bytes, signed: bool) -> bytes:
    """One BC6H mode 11 block from 64 bytes of RGBA (the alpha is not kept)."""
    lut, table = (SF, SQ) if signed else (UF, UQ)
    chans = tuple([lut[v] for v in px[c::4]] for c in range(3))
    hi, lo = corners(chans)
    q0, q1 = [_nearest(u, table) for u in hi], [_nearest(u, table) for u in lo]
    idx = _indices(chans, [table[e] for e in q0], [table[e] for e in q1])
    if idx[0] > 7:
        q0, q1, idx = q1, q0, [15 - k for k in idx]
    return _pack((3, 5), [(e, 10) for e in (*q0, *q1)], idx)


def block(kind: str, px: bytes) -> bytes:
    """One block of `kind` (BC7, BC6H unsigned, BC6HS signed) from 64 bytes of RGBA."""
    return bc7(px) if kind == "BC7" else bc6h(px, kind == "BC6HS")
