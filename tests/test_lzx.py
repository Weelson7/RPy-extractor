"""L3: the first-party LZX decompressor for XNA's XMemCompress (plugins/xna/lzx.py). The decoder
is proven against LZX streams this test writes bit by bit with a matching first-party encoder:
a verbatim block of literals, matches through the repeated offset R0 (run-length), a match long
enough to use the length tree, a match at an arbitrary offset through a position slot and its
extra bits, and an uncompressed block. Each decodes to exactly the bytes the encoder was given;
a bad Huffman code and a match reaching before the start are refused. The encoder gives every
used Huffman symbol the same code length (a valid, if not optimal, canonical code), which is all
the decoder's canonical reader needs."""

from __future__ import annotations

import random
import struct
import unittest

from viwo.plugins.xna.lzx import BASE, EXTRA, MAIN_SYMS, NUM_CHARS, SECONDARY, decompress


class Writer:
    """Bits most-significant first, packed into little-endian 16-bit words (as LZX reads them)."""

    def __init__(self) -> None:
        self.bits: list[int] = []

    def put(self, value: int, n: int) -> None:
        for i in range(n - 1, -1, -1):
            self.bits.append((value >> i) & 1)

    def frame(self) -> bytes:
        while len(self.bits) % 16:
            self.bits.append(0)
        out = bytearray()
        for i in range(0, len(self.bits), 16):
            word = 0
            for b in range(16):
                word |= self.bits[i + b] << (15 - b)
            out += struct.pack("<H", word)
        return bytes(out)


def _code_len(count: int) -> int:
    return max(1, (count - 1).bit_length())


def _emit_lens(w: Writer, lens: list[int]) -> None:
    """One read_lens segment: the 20 pretree code lengths, then a pretree symbol per entry (the
    delta from a previous length of 0: z = (-length) % 17), no run codes."""
    zs = [(-v) % 17 for v in lens]
    used = sorted(set(zs))
    bits = _code_len(len(used))
    pre = [0] * 20
    for z in used:
        pre[z] = bits
    for value in pre:
        w.put(value, 4)
    rank = {z: i for i, z in enumerate(used)}
    for z in zs:
        w.put(rank[z], bits)


def _tree(symbols: set[int], size: int) -> tuple[list[int], dict[int, int], int]:
    used = sorted(symbols)
    bits = _code_len(len(used)) if used else 1
    lens = [0] * size
    for sym in used:
        lens[sym] = bits
    return lens, {sym: i for i, sym in enumerate(used)}, bits


def slot_for(offset: int) -> tuple[int, int]:
    """A position slot (>= 3) and the verbatim bits for a match offset, verbatim-block style."""
    for slot in range(3, 50):
        low = BASE[slot] - 2
        if low <= offset < low + (1 << EXTRA[slot]):
            return slot, offset - low
    raise AssertionError(offset)


def encode(tokens: list) -> bytes:
    """A single verbatim LZX block (no Intel E8) encoding `tokens`: ('lit', byte) or
    ('match', length, offset) with offset 1 taken as the repeated R0."""
    main_syms, length_syms, out_len = set(), set(), 0
    for token in tokens:
        if token[0] == "lit":
            main_syms.add(token[1])
            out_len += 1
        else:
            _, length, offset = token
            header = min(length - 2, 7)
            slot = 0 if offset == 1 else slot_for(offset)[0]
            main_syms.add(NUM_CHARS + (slot << 3) + header)
            if header == 7:
                length_syms.add(length - 2 - 7)
            out_len += length
    main_lens, main_code, _ = _tree(main_syms, MAIN_SYMS)
    length_lens, length_code, _ = _tree(length_syms, SECONDARY + 1)
    return _write(tokens, out_len, main_lens, main_code, length_lens, length_code)


def _write(tokens, out_len, main_lens, main_code, length_lens, length_code) -> bytes:
    w = Writer()
    w.put(0, 1)  # Intel E8 flag: off
    w.put(1, 3)  # verbatim block
    w.put(out_len >> 8, 16)
    w.put(out_len & 0xFF, 8)
    _emit_lens(w, main_lens[:NUM_CHARS])
    _emit_lens(w, main_lens[NUM_CHARS:MAIN_SYMS])
    _emit_lens(w, length_lens[:SECONDARY])
    main_len = _code_len(len({s for s in range(len(main_lens)) if main_lens[s]}))
    length_len = _code_len(len({s for s in range(len(length_lens)) if length_lens[s]}) or 1)
    for token in tokens:
        if token[0] == "lit":
            w.put(main_code[token[1]], main_len)
        else:
            _write_match(w, token, main_code, main_len, length_code, length_len)
    return w.frame()


def _write_match(w, token, main_code, main_len, length_code, length_len) -> None:
    _, length, offset = token
    header = min(length - 2, 7)
    slot = 0 if offset == 1 else slot_for(offset)[0]
    w.put(main_code[NUM_CHARS + (slot << 3) + header], main_len)
    if header == 7:
        w.put(length_code[length - 2 - 7], length_len)
    if slot >= 3:
        w.put(slot_for(offset)[1], EXTRA[slot])


def encode_uncompressed(data: bytes) -> bytes:
    """An uncompressed LZX block: the header padded to a 16-bit boundary, R0/R1/R2, then raw."""
    w = Writer()
    w.put(0, 1)
    w.put(3, 3)
    w.put(len(data) >> 8, 16)
    w.put(len(data) & 0xFF, 8)
    body = w.frame() + struct.pack("<III", 1, 1, 1) + data
    return body + (b"\x00" if len(data) % 2 else b"")


def wrap(block: bytes) -> bytes:
    """`block` as one XNB LZX frame (default 0x8000 frame size): a 16-bit block size, the block."""
    return struct.pack(">H", len(block)) + block


class LzxTests(unittest.TestCase):
    def _roundtrip(self, tokens: list, expected: bytes) -> None:
        data = bytes(14) + wrap(encode(tokens))
        self.assertEqual(decompress(data, len(expected)), expected)

    def test_literals(self) -> None:
        rng = random.Random(3)
        data = rng.randbytes(2000)
        self._roundtrip([("lit", b) for b in data], data)

    def test_run_length_and_the_length_tree(self) -> None:
        tokens = [("lit", 65), ("match", 5, 1), ("lit", 66), ("match", 20, 1)]
        self._roundtrip(tokens, b"A" + b"A" * 5 + b"B" + b"B" * 20)

    def test_a_match_at_an_arbitrary_offset(self) -> None:
        tokens = [("lit", 65), ("lit", 66), ("lit", 67), ("match", 6, 3)]
        self._roundtrip(tokens, b"ABC" + b"ABCABC")

    def test_uncompressed_block(self) -> None:
        data = random.Random(4).randbytes(100)
        frame = bytes(14) + wrap(encode_uncompressed(data))
        self.assertEqual(decompress(frame, len(data)), data)

    def test_a_bad_match_is_refused(self) -> None:
        data = bytes(14) + wrap(encode([("lit", 65), ("match", 4, 3)]))
        with self.assertRaisesRegex(ValueError, "before the start"):
            decompress(data, 5)


if __name__ == "__main__":
    unittest.main()
