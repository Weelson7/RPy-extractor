"""A first-party, pure-Python LZX decompressor for XNA's XMemCompress (`0x80` XNB files),
documented from the public LZX / cabinet format description (as libmspack's lzxd and MonoGame's
LzxDecoder read it), the GPL code never used.

Bit layout: the compressed stream is a sequence of little-endian 16-bit words; bits are taken
most-significant first. A block starts (once per stream) with a 1-bit Intel-E8 flag, then a
3-bit block type (1 verbatim, 2 aligned, 3 uncompressed) and a 24-bit block length (its output
bytes). Verbatim and aligned blocks carry canonical Huffman trees whose code lengths are
delta-encoded against the previous block's through a 20-symbol pretree; the main tree's 256
literals and `posn_slots * 8` match symbols give a literal (symbol < 256) or a match (length in
the low 3 bits, extended by the length tree at 7; a position slot in the high bits picking a
repeated offset R0/R1/R2 or a base plus extra bits, aligned blocks taking the low 3 offset bits
from the aligned tree). An Intel-E8 stream is refused by name: XNB does not use it and ViWo does
not apply that translation. The window is the whole output so far, so a match is `out[pos - off]`.

XNB framing (`decompress`): after the 14-byte header, frames of `hi lo` (a 16-bit block size, a
0x8000 output frame) or `0xFF` then a 16-bit frame size and a 16-bit block size; a zero size
ends the stream."""

NUM_CHARS = 256
PRETREE_SYMS = 20
SECONDARY = 249
VERBATIM, ALIGNED, UNCOMPRESSED = 1, 2, 3
WINDOW_BITS = 16
POSN_SLOTS = WINDOW_BITS << 1  # 32 for a 64 KB window (XNA's XMemCompress)
MAIN_SYMS = NUM_CHARS + (POSN_SLOTS << 3)
FRAME = 0x8000


def _tables() -> tuple[list[int], list[int]]:
    extra, j = [], 0
    for i in range(0, 51, 2):
        extra += [j, j]
        if i != 0 and j < 17:
            j += 1
    base, pos = [], 0
    for value in extra[:51]:
        base.append(pos)
        pos += 1 << value
    return extra[:51], base


EXTRA, BASE = _tables()


class Bits:
    """The 16-bit-word, MSB-first bit reader (bit by bit: simple and exact)."""

    def __init__(self, data: bytes) -> None:
        self.data, self.widx, self.bidx = data, 0, 0

    def _byte(self, i: int) -> int:
        return self.data[i] if i < len(self.data) else 0

    def bits(self, n: int) -> int:
        value = 0
        for _ in range(n):
            word = self._byte(self.widx * 2) | (self._byte(self.widx * 2 + 1) << 8)
            value = (value << 1) | ((word >> (15 - self.bidx)) & 1)
            self.bidx += 1
            if self.bidx == 16:
                self.bidx, self.widx = 0, self.widx + 1
        return value

    def align16(self) -> None:
        if self.bidx:
            self.bidx, self.widx = 0, self.widx + 1

    def raw_u32(self) -> int:
        at = self.widx * 2
        self.widx += 2
        return sum(self._byte(at + k) << (8 * k) for k in range(4))

    def raw(self, n: int) -> bytes:
        at = self.widx * 2
        self.widx += (n + 1) // 2  # stay on 16-bit words
        return bytes(self._byte(at + k) for k in range(n))


def make_table(lengths: list[int]) -> tuple[list[int], list[int], int]:
    maxlen = max(lengths) if lengths else 0
    count = [0] * (maxlen + 1)
    for length in lengths:
        if length:
            count[length] += 1
    syms = [s for length in range(1, maxlen + 1) for s, ln in enumerate(lengths) if ln == length]
    return count, syms, maxlen


def read_huff(bits: Bits, table: tuple) -> int:
    count, syms, maxlen = table
    code = first = index = 0
    for length in range(1, maxlen + 1):
        code = (code << 1) | bits.bits(1)
        here = count[length]
        if code - first < here:
            return syms[index + code - first]
        index += here
        first = (first + here) << 1
    raise ValueError("a bad Huffman code in the LZX stream")


class LzxDecoder:
    def __init__(self) -> None:
        self.out = bytearray()
        self.r0 = self.r1 = self.r2 = 1
        self.block_type = self.block_remaining = 0
        self.header_read = False
        self.main_lens = [0] * MAIN_SYMS
        self.length_lens = [0] * (SECONDARY + 1)
        self.aligned_lens = [0] * 8
        self.main_table = self.length_table = self.aligned_table = None

    def _read_lens(self, bits: Bits, lens: list[int], start: int, stop: int) -> None:
        table = make_table([bits.bits(4) for _ in range(PRETREE_SYMS)])
        i = start
        while i < stop:
            z = read_huff(bits, table)
            if z == 17:
                i = _fill(lens, i, bits.bits(4) + 4, 0)
            elif z == 18:
                i = _fill(lens, i, bits.bits(5) + 20, 0)
            elif z == 19:
                run = bits.bits(1) + 4
                i = _fill(lens, i, run, (lens[i] - read_huff(bits, table)) % 17)
            else:
                lens[i] = (lens[i] - z) % 17
                i += 1

    def _header(self, bits: Bits) -> None:
        if not self.header_read:
            self.header_read = True
            if bits.bits(1):
                raise ValueError("LZX with Intel E8 preprocessing: not read by ViWo")
        self.block_type = bits.bits(3)
        self.block_remaining = (bits.bits(16) << 8) | bits.bits(8)
        if self.block_type == ALIGNED:
            self.aligned_lens = [bits.bits(3) for _ in range(8)]
            self.aligned_table = make_table(self.aligned_lens)
        if self.block_type in (VERBATIM, ALIGNED):
            self._read_lens(bits, self.main_lens, 0, NUM_CHARS)
            self._read_lens(bits, self.main_lens, NUM_CHARS, MAIN_SYMS)
            self.main_table = make_table(self.main_lens)
            self._read_lens(bits, self.length_lens, 0, SECONDARY)
            self.length_table = make_table(self.length_lens)
        elif self.block_type == UNCOMPRESSED:
            bits.align16()
            self.r0, self.r1, self.r2 = bits.raw_u32(), bits.raw_u32(), bits.raw_u32()
        else:
            raise ValueError(f"LZX block type {self.block_type}: not read by ViWo")

    def _match(self, bits: Bits, sym: int) -> tuple[int, int]:
        sym -= NUM_CHARS
        length = sym & 7
        if length == 7:
            length += read_huff(bits, self.length_table)
        length += 2
        slot = sym >> 3
        if slot == 0:
            offset = self.r0
        elif slot == 1:
            offset, self.r1, self.r0 = self.r1, self.r0, self.r1
        elif slot == 2:
            offset, self.r2, self.r0 = self.r2, self.r0, self.r2
        else:
            offset = _offset(bits, slot, self.block_type, self.aligned_table)
            self.r2, self.r1, self.r0 = self.r1, self.r0, offset
        return length, offset

    def _decode(self, bits: Bits, todo: int) -> int:
        emitted = 0
        while emitted < todo:
            sym = read_huff(bits, self.main_table)
            if sym < NUM_CHARS:
                self.out.append(sym)
                emitted += 1
            else:
                length, offset = self._match(bits, sym)
                if offset > len(self.out):
                    raise ValueError("an LZX match reaches before the start of the data")
                start = len(self.out) - offset
                for k in range(length):
                    self.out.append(self.out[start + k])
                emitted += length
        return emitted

    def frame(self, data: bytes, out_len: int) -> None:
        bits, target = Bits(data), len(self.out) + out_len
        while len(self.out) < target:
            if self.block_remaining == 0:
                self._header(bits)
            todo = min(self.block_remaining, target - len(self.out))
            if self.block_type == UNCOMPRESSED:
                self.out += bits.raw(todo)
                self.block_remaining -= todo
            else:
                self.block_remaining -= self._decode(bits, todo)


def _offset(bits: Bits, slot: int, block_type: int, aligned_table) -> int:
    extra = EXTRA[slot]
    if block_type == ALIGNED and extra >= 3:
        verbatim = bits.bits(extra - 3) << 3
        return BASE[slot] - 2 + verbatim + read_huff(bits, aligned_table)
    if extra:
        return BASE[slot] - 2 + bits.bits(extra)
    return BASE[slot] - 2


def _fill(lens: list[int], i: int, run: int, value: int) -> int:
    for _ in range(run):
        if i < len(lens):
            lens[i] = value
        i += 1
    return i


def decompress(data: bytes, out_size: int, start: int = 14) -> bytes:
    """The decompressed XNB body: `out_size` bytes from the LZX frames at `start`."""
    decoder, pos, remaining = LzxDecoder(), start, out_size
    while remaining > 0:
        if pos + 2 > len(data):
            raise ValueError("LZX frame header past the end")
        hi, lo = data[pos], data[pos + 1]
        pos += 2
        if hi == 0xFF:
            frame_size = (lo << 8) | data[pos]
            block_size = (data[pos + 1] << 8) | data[pos + 2]
            pos += 3
        else:
            frame_size, block_size = FRAME, (hi << 8) | lo
        if block_size == 0 or frame_size == 0:
            break
        if pos + block_size > len(data):
            raise ValueError("LZX frame past the end of the data")
        want = min(frame_size, remaining)
        decoder.frame(data[pos : pos + block_size], want)
        pos, remaining = pos + block_size, remaining - want
    if len(decoder.out) < out_size:
        raise ValueError("the LZX data does not inflate to its declared size")
    return bytes(decoder.out[:out_size])
