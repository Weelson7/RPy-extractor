"""L3/L5: Ren'Py plugin and the safe RPA reader (doc 13.3, D11)."""

from __future__ import annotations

import os
import pickle
import tempfile
import unittest
import zlib
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest, OutcomeKind
from viwo.core.pipeline.runner import extract
from viwo.os import select_os
from viwo.plugins.renpy.rpa import RpaSafe, Unrpa


class _Ctx:
    os = select_os()
    cancel = CancelToken()


def make_rpa(
    path: Path,
    files: dict[str, bytes],
    version: str = "3.0",
    key: int = 0x42424242,
    payload: bytes | None = None,
    prefix_len: int = 0,
) -> Path:
    header_len = 34 if version == "3.0" else 25
    key = key if version == "3.0" else 0
    index = {}
    with open(path, "wb") as fh:
        fh.write(b"\0" * header_len)
        for name, data in files.items():
            prefix, rest = data[:prefix_len], data[prefix_len:]
            offset = fh.tell()
            fh.write(rest)
            index[name] = [(offset ^ key, len(data) ^ key, prefix)]
        index_offset = fh.tell()
        fh.write(zlib.compress(payload or pickle.dumps(index, protocol=2)))
        fh.seek(0)
        extra = f" {key:08x}" if version == "3.0" else ""
        fh.write(f"RPA-{version} {index_offset:016x}{extra}\n".encode())
    return path


class _Evil:
    def __init__(self, marker: Path) -> None:
        self.marker = marker

    def __reduce__(self):
        return (os.mkdir, (str(self.marker),))


class SafeReaderTests(unittest.TestCase):
    def test_versions_prefix_and_traversal(self) -> None:
        files = {"images/bg.png": b"PNGDATA", "../escape.txt": b"bad", "audio/a.ogg": b"OGG!"}
        for version, prefix_len in (("3.0", 0), ("3.0", 3), ("2.0", 0)):
            with (
                self.subTest(version=version, prefix=prefix_len),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp)
                archive = make_rpa(root / "a.rpa", files, version, prefix_len=prefix_len)
                (root / "out").mkdir()
                outcome = RpaSafe().extract(archive, root / "out", _Ctx())
                self.assertTrue(outcome.ok, outcome.error)
                self.assertEqual((root / "out/images/bg.png").read_bytes(), b"PNGDATA")
                self.assertEqual(outcome.files, 2)
                self.assertFalse((root / "escape.txt").exists())

    def test_malicious_index_never_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "pwned"
            payload = pickle.dumps({"x": _Evil(marker)}, protocol=2)
            archive = make_rpa(root / "evil.rpa", {}, payload=payload)
            (root / "out").mkdir()
            outcome = RpaSafe().extract(archive, root / "out", _Ctx())
            self.assertEqual(outcome.kind, OutcomeKind.FAILED)
            self.assertIn("forbidden global", outcome.error)
            self.assertFalse(marker.exists())


class RenPyPipelineTests(unittest.TestCase):
    def test_detect_and_extract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "MyVN"
            (game / "renpy").mkdir(parents=True)
            (game / "renpy" / "engine.py").write_text("engine")
            (game / "game").mkdir()
            (game / "game" / "script.rpyc").write_bytes(b"RENPY RPC2")
            make_rpa(game / "game" / "images.rpa", {"images/cg 01.png": b"cg"})
            before = tree_hashes(game)
            rt = runtime(root, "[plugins]\nrenpy = on\n")
            result = extract(
                rt,
                ExtractionRequest(str(game), str(root / "ws")),
                "j",
                lambda e: None,
                CancelToken(),
            )
            self.assertEqual(result.runs[0].plugin_id, "renpy")
            files = tree_hashes(root / "ws", skip_reserved=True)
            self.assertIn("png/cg 01.png", files)
            self.assertIn("rpyc/script.rpyc", files)
            self.assertNotIn("py/engine.py", files)  # only game/ is a loose-file root
            self.assertEqual(tree_hashes(game), before)
            self.assertEqual(dict(result.by_backend), {"rpa-safe": 1})


@unittest.skipUnless(os.environ.get("VIWO_L5"), "L5 real-tool test (set VIWO_L5=1)")
class UnrpaSmokeTest(unittest.TestCase):
    def test_unrpa_extracts_fixture(self) -> None:
        if not Unrpa().available(_Ctx.os)[0]:
            self.skipTest("unrpa not installed")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = make_rpa(root / "a.rpa", {"images/bg.png": b"PNGDATA"})
            (root / "out").mkdir()
            outcome = Unrpa().extract(archive, root / "out", _Ctx())
            self.assertTrue(outcome.ok, outcome.error)
            self.assertEqual((root / "out/images/bg.png").read_bytes(), b"PNGDATA")


if __name__ == "__main__":
    unittest.main()
