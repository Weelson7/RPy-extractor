"""L3: signature carver: every format at a known offset, no false hits on noise, pipeline."""

from __future__ import annotations

import io
import random
import struct
import tempfile
import unittest
import wave
import zipfile
import zlib
from pathlib import Path

from tests.helpers import make_png, runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.contracts.pipeline import CarveMode
from viwo.core.carve import carve_file, scan
from viwo.core.carve.formats import OGG_CRC
from viwo.core.pipeline.runner import extract


def ogg_page() -> bytes:
    body = b"\x01vorbis" + b"\0" * 40
    page = bytearray(
        b"OggS\x00\x06" + b"\0" * 8 + struct.pack("<III", 7, 0, 0) + bytes([1, len(body)])
    )
    page += body
    crc = 0
    for byte in page:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ OGG_CRC[((crc >> 24) ^ byte) & 0xFF]
    page[22:26] = struct.pack("<I", crc)
    return bytes(page)


def wav(tag: int = 1) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1), w.setsampwidth(1), w.setframerate(8000), w.writeframes(b"\x80" * 100)
    data = bytearray(out.getvalue())
    data[20:22] = struct.pack("<H", tag)
    return bytes(data)


def jpeg() -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\0" + b"\0" * 9
    sos = b"\xff\xda" + struct.pack(">H", 8) + b"\0" * 6
    return b"\xff\xd8" + app0 + sos + b"\x12\xff\x00\x34" * 80 + b"\xff\xd9"


def gif() -> bytes:
    return (
        b"GIF89a"
        + struct.pack("<HHBBB", 1, 1, 0, 0, 0)
        + b"\x2c"
        + b"\0" * 8
        + b"\0"
        + b"\x02\x02\x4c\x01\x00\x3b"
        + b"\0" * 50
    )


SAMPLES = {
    ".png": lambda tmp: make_png(tmp / "a.png", 8, 8).read_bytes(),
    ".jpg": lambda tmp: jpeg(),
    ".gif": lambda tmp: gif()[:-50] + b"",
    ".wav": lambda tmp: wav(),
    ".wem": lambda tmp: wav(0xFFFF),
    ".ogg": lambda tmp: ogg_page(),
    ".mid": lambda tmp: (
        b"MThd" + struct.pack(">IHHH", 6, 0, 1, 96) + b"MTrk" + struct.pack(">I", 60) + b"\0" * 60
    ),
    ".mp4": lambda tmp: (
        struct.pack(">I", 16)
        + b"ftypisom"
        + b"\0" * 4
        + struct.pack(">I", 72)
        + b"moov"
        + b"\0" * 64
    ),
    ".bik": lambda tmp: b"BIKi" + struct.pack("<6I", 84, 10, 50, 10, 320, 200) + b"\0" * 64,
    ".fsb": lambda tmp: b"FSB5" + struct.pack("<6I", 1, 1, 8, 0, 32, 15) + b"\0" * 32 + b"\0" * 40,
    ".bnk": lambda tmp: (
        b"BKHD" + struct.pack("<I", 8) + b"\0" * 8 + b"HIRC" + struct.pack("<I", 56) + b"\0" * 56
    ),
    ".dds": lambda tmp: (
        b"DDS "
        + struct.pack("<7I", 124, 0, 4, 4, 0, 0, 1)
        + b"\0" * 44
        + struct.pack("<II", 32, 4)
        + b"DXT1"
        + b"\0" * 40
        + b"\xaa" * 8
    ),
    ".glb": lambda tmp: b"glTF" + struct.pack("<III", 2, 80, 60) + b"JSON" + b" " * 60,
}


def zip_bytes() -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("inner/readme.txt", "hello from a carved zip")
    return out.getvalue()


def seven_zip() -> bytes:
    tail = b"\x01\x04\x06\x00\x01\x09\x00\x00"
    start = struct.pack("<QQI", 0, len(tail), zlib.crc32(tail))
    return (
        b"7z\xbc\xaf\x27\x1c\x00\x04"
        + struct.pack("<I", zlib.crc32(start))
        + start
        + tail
        + b"\0" * 40
    )


def blob(tmp: Path) -> tuple[bytes, dict[str, tuple[int, int]]]:
    rng, data, where = random.Random(7), bytearray(), {}
    items = [(k, f(tmp)) for k, f in SAMPLES.items()] + [
        (".zip", zip_bytes()),
        (".7z", seven_zip()[:-40]),
    ]
    for suffix, sample in items:
        data += rng.randbytes(rng.randint(10, 300))
        where[suffix] = (len(data), len(sample))
        data += sample
    return bytes(data + rng.randbytes(100)), where


class ScanTests(unittest.TestCase):
    def test_every_format_is_found_at_its_offset_with_its_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data, where = blob(Path(tmp))
            path = Path(tmp) / "pack.dat"
            path.write_bytes(data)
            found = {h.suffix: (h.offset, h.size) for h in scan(path, CancelToken())}
            self.assertEqual(found, where)

    def test_noise_gives_no_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "noise.bin"
            rng = random.Random(3)
            needles = b"".join(
                (b"\x89PNG\r\n\x1a\n", b"OggS", b"RIFF", b"PK\x03\x04", b"DDS |", b"\xff\xd8\xff")
            )
            path.write_bytes(b"".join(rng.randbytes(4096) + needles for _ in range(256)))
            self.assertEqual(scan(path, CancelToken()), [])

    def test_png_inside_a_zip_stays_in_the_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = io.BytesIO()
            with zipfile.ZipFile(out, "w") as z:  # stored: the PNG bytes are visible
                z.writestr("a.png", make_png(Path(tmp) / "a.png").read_bytes())
            path = Path(tmp) / "x.bin"
            path.write_bytes(b"\0" * 100 + out.getvalue())
            self.assertEqual([h.suffix for h in scan(path, CancelToken())], [".zip"])


class CarvePropertyTests(unittest.TestCase):
    def test_placed_files_are_found_exactly_and_damage_never_misleads(self) -> None:
        """Valid samples at random places in noise come out at their offset and size; damaged
        ones (cut, bytes flipped) never crash the scan, never overlap and never run past it."""
        from viwo.core.carve import MIN_SIZE, scan_buffer

        rng = random.Random(19)
        with tempfile.TemporaryDirectory() as tmp:
            samples = {k: f(Path(tmp)) for k, f in SAMPLES.items()}
            samples[".zip"] = zip_bytes()
            for _ in range(40):
                data, where = bytearray(), {}
                for suffix in rng.sample(sorted(samples), rng.randint(1, 5)):
                    data += bytes(rng.randint(8, 200))  # zeros: no false signature
                    where[len(data)] = (len(samples[suffix]), suffix)
                    data += samples[suffix]
                data += bytes(50)
                hits = scan_buffer(bytes(data), len(data), CancelToken())
                self.assertEqual({h.offset: (h.size, h.suffix) for h in hits}, where)
            for suffix, good in samples.items():
                for _ in range(60):
                    bad = bytearray(good)
                    for _ in range(rng.randint(1, 4)):
                        bad[rng.randrange(len(bad))] = rng.randrange(256)
                    if rng.random() < 0.4:
                        bad = bad[: rng.randrange(1, len(bad))]
                    blob = bytes(16) + bytes(bad) + bytes(16)
                    hits = scan_buffer(blob, len(blob), CancelToken())
                    end = 0
                    for h in hits:  # in order, apart, inside, never a tiny "file"
                        self.assertGreaterEqual(h.offset, end, suffix)
                        self.assertLessEqual(h.offset + h.size, len(blob), suffix)
                        self.assertGreaterEqual(h.size, MIN_SIZE, suffix)
                        end = h.offset + h.size


class StreamTests(unittest.TestCase):
    def test_custom_archive_with_compressed_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            png = make_png(root / "p.png", 8, 8).read_bytes()
            text = b"dialogue line one\nline two\n" * 10
            raw = random.Random(5).randbytes(500)
            gz = __import__("gzip").compress(wav())
            entries = [zlib.compress(png), zlib.compress(text), gz, zlib.compress(raw, 1)]
            pack = b"MYPAK\x01" + b"".join(struct.pack("<I", len(e)) + e for e in entries)
            path = root / "data.pak"
            path.write_bytes(pack)
            out = root / "out"
            self.assertEqual(carve_file(path, out, CancelToken()), 4)
            names = sorted(p.suffix for p in out.iterdir())
            self.assertEqual(names, [".bin", ".png", ".txt", ".wav"])
            self.assertIn(png, [p.read_bytes() for p in out.iterdir()])

    def test_noise_with_zlib_headers_gives_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rng = random.Random(11)
            path = Path(tmp) / "noise.bin"
            path.write_bytes(
                b"".join(rng.randbytes(2048) + b"\x78\x9c" + b"\x1f\x8b\x08" for _ in range(500))
            )
            self.assertEqual(carve_file(path, Path(tmp) / "out", CancelToken()), 0)


class CarvePipelineTests(unittest.TestCase):
    def run_it(self, root: Path, carve: CarveMode):
        request = ExtractionRequest(
            str(root / "game"), str(root / f"ws-{carve.value}"), carve=carve
        )
        return extract(runtime(root), request, "j", lambda e: None, CancelToken())

    def test_unknown_blobs_are_carved_and_archives_inside_unpacked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            data, _ = blob(root)
            (game / "assets.pak").write_bytes(data)
            (game / "Game.exe").write_bytes(b"MZ" + b"\0" * 2000 + ogg_page())
            before = tree_hashes(game)
            result = self.run_it(root, CarveMode.UNKNOWN)
            ws = root / "ws-unknown"
            png_at = data.index(b"\x89PNG")
            self.assertTrue((ws / "png" / f"assets.pak@{png_at:08x}.png").is_file())
            self.assertTrue((ws / "txt" / "readme.txt").is_file())  # from the carved zip
            self.assertGreaterEqual(result.carved_files, 15)
            self.assertFalse(any("Game.exe@" in p.name for p in ws.rglob("*.ogg")))  # code skipped
            everything = self.run_it(root, CarveMode.ALL)
            self.assertTrue(any("Game.exe@" in p.name for p in (root / "ws-all").rglob("*.ogg")))
            self.assertGreater(everything.carved_files, result.carved_files)
            self.assertEqual(self.run_it(root, CarveMode.OFF).carved_files, 0)
            self.assertEqual(tree_hashes(game), before)


if __name__ == "__main__":
    unittest.main()


class StreamBoundTests(unittest.TestCase):
    def test_oversized_stream_is_skipped(self) -> None:
        """Doc 17.3: a stream that inflates past LIMIT is dropped, not kept in memory."""
        from unittest import mock

        from viwo.core.carve import streams

        data = b"\0" * 5 + zlib.compress(b"A" * 4096)
        with mock.patch.object(streams, "LIMIT", 1024):
            self.assertEqual(list(streams.find_streams(data, len(data), [], CancelToken())), [])
        self.assertEqual(len(list(streams.find_streams(data, len(data), [], CancelToken()))), 1)


class OptionalStreamTests(unittest.TestCase):
    """Ladder rung 4 (doc 16.0b): LZ4 and zstd frames are inflated when their modules exist,
    and silently skipped (never a crash) when they do not."""

    def test_lz4_frame_is_inflated_when_the_module_is_present(self) -> None:
        try:
            import lz4.frame
        except ImportError:
            self.skipTest("lz4 not installed")
        from viwo.core.carve import streams

        self.assertIn(("lz4"), [k for _, k in streams.heads()])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            png = make_png(root / "p.png", 8, 8).read_bytes()
            text = b"spoken line\n" * 20
            pack = b"PAK4" + lz4.frame.compress(png) + b"\0" * 7 + lz4.frame.compress(text)
            (root / "data.bin").write_bytes(pack)
            # the inflated PNG and text, plus the PNG bytes LZ4 stored literally (also real)
            self.assertGreaterEqual(carve_file(root / "data.bin", root / "out", CancelToken()), 2)
            found = sorted(p.suffix for p in (root / "out").iterdir())
            self.assertIn(".txt", found)
            self.assertIn(".png", found)
            self.assertIn(text, [p.read_bytes() for p in (root / "out").iterdir()])

    def test_zstd_frame_is_inflated_when_the_module_is_present(self) -> None:
        try:
            import zstandard
        except ImportError:
            self.skipTest("zstandard not installed")
        from viwo.core.carve import streams

        self.assertIn("zstd", [k for _, k in streams.heads()])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = b"zstd stored text\n" * 30
            (root / "data.bin").write_bytes(b"\xff" * 9 + zstandard.compress(text))
            self.assertEqual(carve_file(root / "data.bin", root / "out", CancelToken()), 1)

    def test_missing_optional_module_only_drops_that_kind(self) -> None:
        from unittest import mock

        from viwo.core.carve import streams

        with mock.patch.object(
            streams, "decoder", lambda kind: None if kind == "lz4" else object()
        ):
            kinds = [k for _, k in streams.heads()]
            self.assertNotIn("lz4", kinds)
            self.assertIn(15, kinds)
        self.assertIsNone(streams.inflate(b"\x04\x22\x4d\x18" + b"\0" * 64, 0, 68, "nope"))
