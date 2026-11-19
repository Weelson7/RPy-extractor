"""L3: ViWo's first-party block decoders (viwo/backends/blocks, doc 18.3), against Pillow on
random blocks. BC7: every mode (random bits under each mode's leading bit, so every partition,
rotation, index selection and p-bit comes up) decodes to exactly Pillow's pixels; a reserved
block is transparent black (the specification; Pillow shows it opaque). BC1 to BC5: within 1 of
Pillow, which expands RGB565 by repeating bits where ViWo uses ffmpeg's expansion (the same
blocks were checked byte for byte against the pinned ffmpeg by hand; BC5's blue is 0
where ffmpeg rebuilds a normal's z). Images of any size crop their edge blocks; data cut short
and unknown formats are named."""

from __future__ import annotations

import random
import unittest

from tests.test_encode_bc import pillow
from viwo.backends.blocks.decode_bc import KINDS, decompress, pixels
from viwo.backends.blocks.decode_bc7 import bc7


def with_mode(rng, mode: int) -> bytes:
    """A random BC7 block whose first byte says `mode` (0-7; 8: reserved)."""
    block = bytearray(rng.randbytes(16))
    block[0] = ((block[0] & ~((2 << mode) - 1)) | (1 << mode)) & 0xFF if mode < 8 else 0
    return bytes(block)


class Bc7Tests(unittest.TestCase):
    def test_every_mode_decodes_as_pillow_does(self) -> None:
        rng = random.Random(91)
        for mode in range(8):
            for _ in range(300):
                block = with_mode(rng, mode)
                self.assertEqual(bc7(block), pillow("BC7", block, 4, 4), (mode, block.hex()))

    def test_a_reserved_block_is_transparent_black(self) -> None:
        rng = random.Random(92)
        self.assertEqual(bc7(with_mode(rng, 8)), bytes(64))


class BlockTests(unittest.TestCase):
    def test_bc1_to_bc5_stay_within_1_of_pillow(self) -> None:
        rng = random.Random(93)
        for kind in ("BC1", "BC2", "BC3", "BC4", "BC5"):
            for _ in range(200):
                block = rng.randbytes(KINDS[kind])
                mine = pixels(block, kind)
                theirs = pillow(kind, block, 4, 4)
                for c in range(4 if kind != "BC5" else 2):
                    worst = max(abs(a - b) for a, b in zip(mine[c::4], theirs[c::4]))
                    self.assertLessEqual(worst, 1, (kind, c, block.hex()))

    def test_images_of_any_size_crop_their_edge_blocks(self) -> None:
        rng = random.Random(94)
        for _ in range(30):
            w, h, kind = rng.randint(1, 13), rng.randint(1, 13), rng.choice(list(KINDS))
            data = rng.randbytes(((w + 3) // 4) * ((h + 3) // 4) * KINDS[kind])
            got = decompress(data, w, h, kind)
            self.assertEqual(len(got), w * h * 4)
            wide = decompress(data, (w + 3) // 4 * 4, (h + 3) // 4 * 4, kind)
            row = (w + 3) // 4 * 16
            self.assertEqual(got, b"".join(wide[y * row : y * row + 4 * w] for y in range(h)))

    def test_cut_short_and_unknown_formats_are_named(self) -> None:
        with self.assertRaisesRegex(ValueError, "BC7 data cut short"):
            decompress(bytes(15), 4, 4, "BC7")
        for call in (lambda: decompress(bytes(8), 4, 4, "ETC1"), lambda: pixels(bytes(8), "X")):
            with self.assertRaisesRegex(ValueError, "not a block format ViWo decodes"):
                call()


if __name__ == "__main__":
    unittest.main()
