"""AES-256 single-block decryption (FIPS-197), used only to verify a candidate key against a
pak index; bulk decryption is left to the unpack tools."""

from __future__ import annotations


def _xtime(a: int) -> int:
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1


def _mul(a: int, b: int) -> int:
    out = 0
    while b:
        if b & 1:
            out ^= a
        a, b = _xtime(a), b >> 1
    return out


def _sbox() -> list[int]:
    exp, log, x = [0] * 255, [0] * 256, 1
    for i in range(255):  # 3 generates the multiplicative group of GF(2^8)
        exp[i], log[x] = x, i
        x = _mul(x, 3)
    box = []
    for x in range(256):
        inv = exp[(255 - log[x]) % 255] if x else 0
        s = inv
        for shift in range(1, 5):
            s ^= ((inv << shift) | (inv >> (8 - shift))) & 0xFF
        box.append(s ^ 0x63)
    return box


SBOX = _sbox()
INV = [0] * 256
for _i, _v in enumerate(SBOX):
    INV[_v] = _i


def _expand(key: bytes) -> list[list[int]]:
    words = [list(key[i : i + 4]) for i in range(0, 32, 4)]
    rcon = 1
    for i in range(8, 60):
        t = list(words[i - 1])
        if i % 8 == 0:
            t = [SBOX[b] for b in t[1:] + t[:1]]
            t[0] ^= rcon
            rcon = _xtime(rcon)
        elif i % 8 == 4:
            t = [SBOX[b] for b in t]
        words.append([a ^ b for a, b in zip(words[i - 8], t)])
    return [sum(words[r * 4 : r * 4 + 4], []) for r in range(15)]


def _inv_mix(s: list[int]) -> list[int]:
    out = []
    for c in range(4):
        a = s[c * 4 : c * 4 + 4]
        for r in range(4):
            out.append(
                _mul(a[r], 14)
                ^ _mul(a[(r + 1) % 4], 11)
                ^ _mul(a[(r + 2) % 4], 13)
                ^ _mul(a[(r + 3) % 4], 9)
            )
    return out


def _inv_shift(s: list[int]) -> list[int]:
    return [s[((c - r) % 4) * 4 + r] for c in range(4) for r in range(4)]


def decrypt_block(key: bytes, block: bytes) -> bytes:
    rounds = _expand(key)
    s = [a ^ b for a, b in zip(block, rounds[14])]
    for rnd in range(13, 0, -1):
        s = [INV[b] for b in _inv_shift(s)]
        s = _inv_mix([a ^ b for a, b in zip(s, rounds[rnd])])
    s = [INV[b] for b in _inv_shift(s)]
    return bytes(a ^ b for a, b in zip(s, rounds[0]))
