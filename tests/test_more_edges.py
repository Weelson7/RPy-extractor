"""L3: Skyrim SE archives (BSA 105: LZ4 frames, names embedded before the data) read back byte
for byte, and without the lz4 module they are counted, never garbled; the carver splits an
inflated stream holding several files into each of them and names an unreadable input; `viwo
analyze` names a missing game or workspace and waits for a GUI tool it opened."""

from __future__ import annotations

import random
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from viwo.contracts import CancelToken
from viwo.contracts.types import OutcomeKind


def bsa105(files: dict[str, bytes], embed: bool) -> bytes:
    """Version 105: 24-byte folder records, LZ4-frame compressed entries; `embed` stores each
    entry's full path (a length byte, then the bytes) in front of its data (flag 0x100)."""
    import lz4.frame

    folder = b"meshes\\actors"
    names = b"".join(n.encode() + b"\0" for n in files)
    header_end = 36 + 24 + 1 + len(folder) + 1 + 16 * len(files) + len(names)
    records, body, offset = b"", b"", header_end
    for i, (name, data) in enumerate(files.items()):
        lead = bytes([len(name)]) + name.encode() if embed else b""
        blob = lead + struct.pack("<I", len(data)) + lz4.frame.compress(data)
        records += struct.pack("<QII", i, len(blob), offset)
        body, offset = body + blob, offset + len(blob)
    flags = 0x7 | (0x100 if embed else 0)
    head = b"BSA\0" + struct.pack(
        "<8I", 105, 36, flags, 1, len(files), len(folder) + 1, len(names), 0
    )
    folders = struct.pack("<QIIQ", 0, len(files), 0, 0) + bytes([len(folder) + 1]) + folder + b"\0"
    return head + folders + records + names + body


class Bsa105Tests(unittest.TestCase):
    def test_lz4_entries_with_and_without_embedded_names(self) -> None:
        from viwo.plugins.bethesda.archives import bsa_data, bsa_entries

        rng = random.Random(3)
        for embed in (False, True):
            files = {f"f{i}.nif": rng.randbytes(rng.randint(1, 200)) for i in range(4)}
            blob = bsa105(files, embed)
            version, flags, entries = bsa_entries(blob)
            got = {
                Path(e[0].replace("\\", "/")).name: bsa_data(blob, version, flags, e)
                for e in entries
            }
            self.assertEqual(got, files)
            with mock.patch.dict(sys.modules, {"lz4": None, "lz4.frame": None}):
                self.assertIsNone(
                    bsa_data(blob, version, flags, entries[0])
                )  # counted, not garbled
            bad = bytearray(blob)
            version, flags, entries = bsa_entries(bytes(bad))
            _, offset, size, _ = entries[0]
            start = offset + (1 + bad[offset] if embed else 0)
            struct.pack_into("<I", bad, start, size * 9)  # claims more than the frame holds
            with self.assertRaises(ValueError):
                bsa_data(bytes(bad), version, flags, entries[0])


class CarverTests(unittest.TestCase):
    def test_a_stream_of_several_files_is_split_and_bad_input_named(self) -> None:
        from tests.test_carve import SAMPLES
        from viwo.core.carve import SignatureCarver, carve_file, count_embedded, scan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inner = SAMPLES[".wav"](root) + bytes(64) + SAMPLES[".png"](root)
            path = root / "pack.dat"
            path.write_bytes(bytes(100) + zlib.compress(inner) + bytes(100))
            out = root / "out"
            self.assertEqual(carve_file(path, out, CancelToken()), 2)
            suffixes = sorted(p.suffix for p in out.iterdir())
            self.assertEqual(suffixes, [".png", ".wav"])  # both files, each on its own
            tiny = root / "tiny.bin"
            tiny.write_bytes(b"x")
            self.assertEqual(
                (scan(tiny, CancelToken()), count_embedded(tiny, CancelToken())), ([], 0)
            )
            self.assertEqual(carve_file(tiny, root / "t", CancelToken()), 0)
            ctx = SimpleNamespace(cancel=CancelToken())
            missing = SignatureCarver().carve(root / "gone.bin", root / "g", ctx)
            self.assertEqual(missing.kind, OutcomeKind.FAILED)


class AnalyzeCliTests(unittest.TestCase):
    def test_missing_game_missing_workspace_and_open(self) -> None:
        from tests.helpers import write_ini
        from tests.test_cli import run

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ini = str(write_ini(root, "[startup]\nfeatures = analysis\n[plugins]\ngeneric = on\n"))
            (root / "game").mkdir()
            code, _, err = run(["--ini", ini, "analyze", str(root / "nowhere"), "--target", "x"])
            self.assertIn("not_found", err)
            code, _, err = run(["--ini", ini, "analyze", str(root / "game"), "--target", "x"])
            self.assertIn("--workspace", err)
            opened = {"label": "Continue in Ghidra", "pid": 77, "handoff": "ghidra-gui"}
            with (
                mock.patch("viwo.core.analysis.open_in", return_value=opened),
                mock.patch("viwo.core.handoff.wait_for", return_value=True) as wait,
            ):
                argv = ["--ini", ini, "analyze", str(root / "game"), "--target", "x"]
                code, out, err = run([*argv, "--workspace", str(root / "ws"), "--open"])
            self.assertEqual(code, 0, err)
            wait.assert_called_once_with(77)  # the tool is ViWo's child: the CLI waits for it
            self.assertIn("Continue in Ghidra running (pid 77)", err)


if __name__ == "__main__":
    unittest.main()
