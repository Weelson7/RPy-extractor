"""Defold resource encryption: XTEA in counter (CTR) mode, as the engine decrypts it
(`engine/dlib/src/dlib/crypt.cpp`, `DecryptXTeaCTR`) and the bundler encrypts it
(`com.dynamo.bob.archive.ResourceEncryption`). 32 rounds, delta `0x9e3779b9`; the key is padded
with NUL to 16 bytes and read as four big-endian 32-bit words; each 8-byte block of data is XORed
with the big-endian XTEA of a 64-bit counter that starts at 0 and counts up one per block. XOR is
its own inverse, so one routine both decrypts and re-encrypts. `DEFAULT_KEY` is the engine's
built-in resource key, a public constant; a game may bundle with its own key, given by the user
as the `decryption_key` secret and verified before use (D18). ViWo authors no key search."""

import struct

DEFAULT_KEY = b"aQj8CScgNP4VsfXK"  # Defold's built-in resource key (a public engine constant)
ROUNDS, DELTA, MASK = 32, 0x9E3779B9, 0xFFFFFFFF


def _mix(x: int, y: int, total: int, key_word: int) -> int:
    return (x + (((((y << 4) & MASK) ^ (y >> 5)) + y & MASK) ^ ((total + key_word) & MASK))) & MASK


def _keystream(counter: int, key: list[int]) -> bytes:
    """The 8 keystream bytes XTEA makes from a counter value (big-endian v0 then v1)."""
    v0, v1, total = (counter >> 32) & MASK, counter & MASK, 0
    for _ in range(ROUNDS):
        v0 = _mix(v0, v1, total, key[total & 3])
        total = (total + DELTA) & MASK
        v1 = _mix(v1, v0, total, key[(total >> 11) & 3])
    return struct.pack(">II", v0, v1)


def crypt(data: bytes, key: bytes) -> bytes:
    """`data` XORed with the XTEA-CTR keystream of `key`: Defold's decrypt, and its own inverse."""
    words = list(struct.unpack(">IIII", key.ljust(16, b"\0")[:16]))
    out = bytearray(data)
    for i in range(0, len(out), 8):
        stream = _keystream(i // 8, words)
        for j in range(min(8, len(out) - i)):
            out[i + j] ^= stream[j]
    return bytes(out)
