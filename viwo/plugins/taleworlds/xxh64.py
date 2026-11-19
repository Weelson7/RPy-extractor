"""XXH64 (seed 0), pure Python: the hash a TPAC segment entry holds of its uncompressed data
(measured on Bannerlord's packages). Checked against the reference vectors in
tests/test_tpac_pack.py."""

import struct

MASK = (1 << 64) - 1
P1, P2, P3 = 0x9E3779B185EBCA87, 0xC2B2AE3D27D4EB4F, 0x165667B19E3779F9
P4, P5 = 0x85EBCA77C2B2AE63, 0x27D4EB2F165667C5


def _round(acc: int, lane: int) -> int:
    acc = (acc + lane * P2) & MASK
    return (((acc << 31) | (acc >> 33)) & MASK) * P1 & MASK


def _rotl(x: int, r: int) -> int:
    return ((x << r) | (x >> (64 - r))) & MASK


def _stripes(data: bytes, end: int) -> int:
    v = [(P1 + P2) & MASK, P2, 0, (-P1) & MASK]
    for a, b, c, d in struct.iter_unpack("<4Q", memoryview(data)[:end]):
        v = [_round(v[0], a), _round(v[1], b), _round(v[2], c), _round(v[3], d)]
    h = (_rotl(v[0], 1) + _rotl(v[1], 7) + _rotl(v[2], 12) + _rotl(v[3], 18)) & MASK
    for lane in v:
        h = ((h ^ _round(0, lane)) * P1 + P4) & MASK
    return h


def xxh64(data: bytes) -> int:
    n = len(data)
    end = n - n % 32
    h = _stripes(data, end) if n >= 32 else P5
    h, i = (h + n) & MASK, end
    while i + 8 <= n:
        h ^= _round(0, struct.unpack_from("<Q", data, i)[0])
        h, i = (_rotl(h, 27) * P1 + P4) & MASK, i + 8
    if i + 4 <= n:
        h ^= struct.unpack_from("<I", data, i)[0] * P1 & MASK
        h, i = (_rotl(h, 23) * P2 + P3) & MASK, i + 4
    for byte in data[i:]:
        h = _rotl(h ^ (byte * P5 & MASK), 11) * P1 & MASK
    h = (h ^ (h >> 33)) * P2 & MASK
    h = (h ^ (h >> 29)) * P3 & MASK
    return h ^ (h >> 32)
