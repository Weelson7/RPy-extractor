"""L3: Godot plugin: PCK identification, carving, failover and keys (fake CLI tools)."""

from __future__ import annotations

import stat
import struct
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest, OnExisting
from viwo.core.pipeline.identify import carve, identify
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import extract
from viwo.plugins.godot import NO_DATA, PCK_SLOT, GodotPlugin


def fake_pe(sections: tuple[str, ...]) -> bytes:
    """A minimal PE image: MZ stub, COFF header without optional header, named sections."""
    pe = 0x80
    head = bytearray(b"MZ" + b"\0" * (0x3C - 2)) + struct.pack("<I", pe)
    head += b"\0" * (pe - len(head))
    head += b"PE\0\0" + struct.pack("<HHIIIHH", 0x8664, len(sections), 0, 0, 0, 0, 0)
    for name in sections:
        head += name.encode().ljust(8, b"\0") + b"\0" * 32
    return bytes(head) + b"\0" * 512


FAKE_TOOL = """#!{python}
import sys
from pathlib import Path
args = sys.argv[1:]
opt = lambda name: next((a.split("=", 1)[1] for a in args if a.startswith(name + "=")), None)
pck = opt("--extract") or args[args.index("--pack") + 1]
out = opt("--output") or args[args.index("--output") + 1]
data = Path(pck).read_bytes()
if data[:4] != b"GDPC":
    sys.exit("not a pck")
if b"ENC" in data and opt("--key") != "ab" * 32:
    sys.exit("pck is encrypted")
if b"BROKEN" in data and "{name}" == "gdre":
    sys.exit("unsupported pck version")
target = Path(out) / "res" / "icon.png"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(b"PNG-" + data[-6:])
print("fake tool progress: 1 file written")
"""


def make_pck(marker: bytes = b"") -> bytes:
    return b"GDPC" + struct.pack("<IIII", 2, 4, 3, 0) + marker + b"payload"


def embed(exe: Path, pck: bytes) -> Path:
    exe.write_bytes(b"MZ" + b"\0" * 64 + pck + struct.pack("<Q", len(pck)) + b"GDPC")
    return exe


def fake_tools(folder: Path) -> str:
    """Python stand-ins for the CLI tools; a .cmd wrapper makes them runnable on Windows."""
    lines = []
    for name, dep in (("gdre", "gdre"), ("pcktool", "godotpcktool")):
        script = folder / f"fake_{name}.py"
        script.write_text(FAKE_TOOL.format(python=sys.executable, name=name))
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        tool = script
        if sys.platform == "win32":
            tool = folder / f"fake_{name}.cmd"
            tool.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
        lines.append(f"{dep} = {tool}")
    return "[plugins]\ngodot = on\n[tools]\n" + "\n".join(lines) + "\n"


class IdentifyTests(unittest.TestCase):
    def test_standalone_and_embedded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pck = make_pck()
            (root / "data.pck").write_bytes(pck)
            exe = embed(root / "Game.exe", pck)
            self.assertEqual(identify(root / "data.pck", [PCK_SLOT]).slot_id, "unarchive.pck")
            match = identify(exe, [PCK_SLOT])
            self.assertTrue(match.embedded)
            self.assertEqual(carve(match, root / "scratch").read_bytes(), pck)
            self.assertEqual(GodotPlugin().detect(FolderProbe(root)).confidence, 0.9)
            (root / "Game.exe").unlink()
            (root / "data.pck").unlink()
            (root / "project.godot").write_text("[application]")
            self.assertEqual(GodotPlugin().detect(FolderProbe(root)).confidence, 0.7)


class GodotPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.game = self.root / "game"
        self.game.mkdir()
        self.rt = runtime(self.root, fake_tools(self.root))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_it(self, **kw):
        request = ExtractionRequest(str(self.game), str(self.root / "ws"), **kw)
        self.events = []
        return extract(self.rt, request, "j", self.events.append, CancelToken())

    def test_embedded_and_failover(self) -> None:
        embed(self.game / "Game.exe", make_pck())
        (self.game / "extra.pck").write_bytes(make_pck(b"BROKEN"))
        result = self.run_it()
        self.assertTrue(any("fake tool progress" in e.message for e in self.events))
        self.assertEqual(result.runs[0].plugin_id, "godot")
        self.assertEqual(dict(result.by_backend), {"gdre-tools": 1, "godotpcktool": 1})
        self.assertIn("png/icon.png", tree_hashes(self.root / "ws", skip_reserved=True))

    def test_godot_executable_without_data_is_named(self) -> None:
        """A bare export template (PE "pck" section, nothing embedded, no .pck beside it) is a
        Godot game with its data missing, not a generic folder."""
        (self.game / "Game.exe").write_bytes(fake_pe(("text", "pck", "rsrc")))
        det = GodotPlugin().detect(FolderProbe(self.game))
        self.assertEqual((det.confidence, det.evidence), (0.6, (NO_DATA,)))
        result = self.run_it()
        self.assertEqual(result.runs[0].plugin_id, "godot")
        self.assertTrue(any("no PCK data" in w for w in result.runs[0].warnings), result.runs)
        self.assertFalse(result.runs[0].verify_passed)

    def test_encrypted_needs_key_and_spare_is_not_tried(self) -> None:
        (self.game / "data.pck").write_bytes(make_pck(b"ENC"))
        result = self.run_it()
        self.assertEqual(result.archives_extracted, 0)
        self.assertTrue(any("needs_key" in w for w in result.warnings))
        keyed = self.run_it(
            plugin_options={"godot": {"encryption_key": "ab" * 32}}, on_existing=OnExisting.REPLACE
        )
        self.assertEqual(dict(keyed.by_backend), {"gdre-tools": 1})


if __name__ == "__main__":
    unittest.main()
