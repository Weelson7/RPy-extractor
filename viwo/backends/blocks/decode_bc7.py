"""A first-party BC7 (BPTC) block decoder, every mode, as the D3D11 specification has it: the
partition and anchor tables below, endpoints with their p-bits expanded by bit replication,
interpolation ((64 - w) * e0 + w * e1 + 32) >> 6, mode 4 and 5 rotations and mode 4's index
selection. A reserved block (mode 8, no mode bit in its first byte) is transparent black.
Checked block for block against Pillow's decoder (tests/test_decode_bc.py)."""

# the subset of each pixel: 2 subsets, one 16-bit word per partition (bit i: pixel i)
P2 = bytes.fromhex(
    "cccc8888eeeeecc8c880feecfec8ec80c800ffecfe80e800ffe8ff00fff0f000"
    "f710008e710008ce008c731031008cce088c31106666366c17e80ff0718e399c"
    "aaaaf0f05a5a33cc3c3c55aa9696a55a73ce13c8324c3bdc6996c33c99660660"
    "027204e44e402720c936936c39c6639c93369cc6817ee718ccf00fcc7744ee22"
)
# 3 subsets: 16 digits per partition, pixel by pixel
P3 = (
    "0011001102212222000100112211222100002001221122110222002200110111"
    "0000000011221122001100110022002200220022111111110011001122112211"
    "0000000011112222000011111111222200001111222222220012001200120012"
    "0112011201120112012201220122012200110112112212220011200122002220"
    "0001001101121122011100112001220000001122112211220022002200221111"
    "0111011102220222000100012221222100000011012201220000110022102210"
    "0122012200110000001200121122222201101221122101100000011012211221"
    "0022110211020022011001102002222200110122012200110000200022112221"
    "0000000211221222022200220012001100110012002202220120012001200120"
    "0000111122220000012012012012012001202012120101200011220011220011"
    "0011112222000011010101012222222200000000212121210022112200221122"
    "0022001100220011022012210220122101012222222201010000212121212121"
    "0101010101012222022201110222011100021112000211120000211221122112"
    "0222011101110222000211121112000201100110011022220000000021122112"
    "0110011022222222002200110011002200221122112200220000000000002112"
    "0002000100020001022212220222122201012222222222220111201122012220"
)
# the anchor pixel of the second subset (2 subsets), of the second and third (3 subsets)
A2 = "fffffffffffffffff282288f28228822ff6828ff28222ff66268ff22fffff22f"
A3A = "33ff83ff88666533338f336a588685ff8f356a8ff3f5ffff3f55585a5a8dfc33"
A3B = "f883ff38fffffff8f8f3f8f83f6affa8f3faa89a6f8f3668f3ffffffffff3ff8"
# per mode: subsets, partition bits, rotation bits, index selection bit, colour bits, alpha
# bits, a p-bit per endpoint, a p-bit per subset, index bits, second index bits
MODES = (
    (3, 4, 0, 0, 4, 0, 1, 0, 3, 0),
    (2, 6, 0, 0, 6, 0, 0, 1, 3, 0),
    (3, 6, 0, 0, 5, 0, 0, 0, 2, 0),
    (2, 6, 0, 0, 7, 0, 1, 0, 2, 0),
    (1, 0, 2, 1, 5, 6, 0, 0, 2, 3),
    (1, 0, 2, 0, 7, 8, 0, 0, 2, 2),
    (1, 0, 0, 0, 7, 7, 1, 0, 4, 0),
    (2, 6, 0, 0, 5, 5, 1, 0, 2, 0),
)
WEIGHTS = {
    2: (0, 21, 43, 64),
    3: (0, 9, 18, 27, 37, 46, 55, 64),
    4: (0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64),
}
CLEAR = bytes(64)


class _Bits:
    def __init__(self, block: bytes) -> None:
        self.bits, self.at = int.from_bytes(block, "little"), 0

    def take(self, n: int) -> int:
        value = (self.bits >> self.at) & ((1 << n) - 1)
        self.at += n
        return value


def _expand(value: int, bits: int) -> int:
    return (value << (8 - bits)) | (value >> (2 * bits - 8))


def _subsets(ns: int, part: int) -> tuple[list[int], set[int]]:
    """(the subset of each pixel, the anchor pixels) of a partition."""
    if ns == 1:
        return [0] * 16, {0}
    if ns == 2:
        word = int.from_bytes(P2[2 * part : 2 * part + 2], "big")
        return [(word >> i) & 1 for i in range(16)], {0, int(A2[part], 16)}
    digits = P3[16 * part : 16 * part + 16]
    return [int(d) for d in digits], {0, int(A3A[part], 16), int(A3B[part], 16)}


SUBSETS = {ns: [_subsets(ns, part) for part in range(64)] for ns in (1, 2, 3)}


def _endpoints(bits: _Bits, spec: tuple) -> list[list[int]]:
    """The 2 x subsets endpoints, RGBA in 8 bits each."""
    ns, cb, ab, epb, spb = spec[0], spec[4], spec[5], spec[6], spec[7]
    n = 2 * ns
    ends = [[bits.take(cb) for _ in range(n)] for _ in range(3)]
    ends.append([bits.take(ab) for _ in range(n)] if ab else [255] * n)
    pbits = [bits.take(1) for _ in range(n)] if epb else []
    if spb:
        pbits = [p for p in (bits.take(1) for _ in range(ns)) for _ in (0, 1)]
    out = []
    for e in range(n):
        point = []
        for c, width in enumerate((cb, cb, cb, ab)):
            value, size = ends[c][e], width
            if c == 3 and not ab:
                point.append(255)
                continue
            if pbits:
                value, size = (value << 1) | pbits[e], width + 1
            point.append(_expand(value, size))
        out.append(point)
    return out


def _indices(bits: _Bits, size: int, anchors: set[int]) -> list[int]:
    word, at, out = bits.bits, bits.at, []
    for i in range(16):
        width = size - 1 if i in anchors else size
        out.append((word >> at) & ((1 << width) - 1))
        at += width
    bits.at = at
    return out


def _mix(e0: list[int], e1: list[int], w: int, v: int) -> bytes:
    """One pixel: colour at weight w, alpha at weight v."""
    r, g, b, a = e0
    r1, g1, b1, a1 = e1
    u, t = 64 - w, 64 - v
    return bytes(
        (u * r + w * r1 + 32 >> 6, u * g + w * g1 + 32 >> 6, u * b + w * b1 + 32 >> 6)
        + (t * a + v * a1 + 32 >> 6,)
    )


def bc7(block: bytes) -> bytes:
    """The 16 RGBA pixels of one BC7 block, row by row (64 bytes)."""
    if not block[0]:
        return CLEAR
    mode = (block[0] & -block[0]).bit_length() - 1
    spec = MODES[mode]
    bits = _Bits(block)
    bits.take(mode + 1)
    part, rot, sel = bits.take(spec[1]), bits.take(spec[2]), bits.take(spec[3])
    ends = _endpoints(bits, spec)
    subset, anchors = SUBSETS[spec[0]][part]
    first = _indices(bits, spec[8], anchors)
    second = _indices(bits, spec[9], {0}) if spec[9] else first
    cw, aw = WEIGHTS[spec[8]], WEIGHTS[spec[9] or spec[8]]
    colour, alpha = (second, first) if sel else (first, second)
    if sel:
        cw, aw = aw, cw
    out, seen = bytearray(64), {}
    for i in range(16):
        key = (subset[i], colour[i], alpha[i])
        if key not in seen:  # a pixel like one before it is not mixed again
            s = 2 * key[0]
            seen[key] = _mix(ends[s], ends[s + 1], cw[key[1]], aw[key[2]])
        out[4 * i : 4 * i + 4] = seen[key]
    if rot:  # the alpha and the channel the rotation names change places
        out[rot - 1 :: 4], out[3::4] = out[3::4], out[rot - 1 :: 4]
    return bytes(out)
