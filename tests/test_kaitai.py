"""L3: the first-party Kaitai `.ksy` interpreter (doc 13.2) and the declarative plugin form.
Property tests on bytes the test writes by hand: the bundled wav.ksy parses a WAV built byte by
byte (magic, little-endian integers, the enum format tag, a user type repeated to the end of the
stream); an inline definition exercises big-endian integers, a counted repeat, a sized raw field
and a user type; a wrong magic and an unreadable construct are refused by name; the plugin exposes
a decode slot per definition and writes the tree as JSON, is one way, and detects nothing."""

from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from viwo.contracts.types import OutcomeKind
from viwo.plugins.kaitai import DEFS, KaitaiPlugin
from viwo.plugins.kaitai.ksy import load_ksy, parse

INLINE = """
meta:
  id: rec
  endian: be
seq:
  - id: magic
    contents: "RC"
  - id: count
    type: u1
  - id: kind
    type: u2
    enum: kinds
  - id: items
    type: item
    repeat: expr
    repeat-expr: count
  - id: trailer
    size: 2
types:
  item:
    seq:
      - id: value
        type: u2
enums:
  kinds:
    1: first
    2: second
"""


def wav_bytes(samples: bytes = b"\x01\x02\x03\x04") -> bytes:
    fmt = struct.pack("<HHIIHH", 1, 2, 44100, 44100 * 4, 4, 16)  # pcm, 2ch, 16-bit
    data = b"data" + struct.pack("<I", len(samples)) + samples
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


class KsyInterpreterTests(unittest.TestCase):
    def test_bundled_wav_parses_a_hand_built_wav(self) -> None:
        ksy = load_ksy((DEFS / "wav.ksy").read_text(encoding="utf-8"))
        tree = parse(ksy, wav_bytes(b"\xaa\xbb\xcc\xdd"))
        self.assertEqual(tree["riff_magic"], "RIFF")
        self.assertEqual(tree["format"]["format_tag"], {"value": 1, "enum": "pcm"})
        self.assertEqual(tree["format"]["sample_rate"], 44100)
        self.assertEqual(tree["chunks"][0]["chunk_id"], b"data".hex())  # a sized raw field: hex
        self.assertEqual(tree["chunks"][0]["data"], "aabbccdd")

    def test_inline_definition_exercises_the_subset(self) -> None:
        ksy = load_ksy(INLINE)
        data = b"RC" + bytes([2]) + struct.pack(">H", 2) + struct.pack(">HH", 7, 9) + b"\xff\xee"
        tree = parse(ksy, data)
        self.assertEqual(tree["count"], 2)
        self.assertEqual(tree["kind"], {"value": 2, "enum": "second"})  # big-endian, enum
        self.assertEqual([it["value"] for it in tree["items"]], [7, 9])  # repeat-expr, user type
        self.assertEqual(tree["trailer"], "ffee")  # sized raw field

    def test_a_bad_magic_and_a_short_read_are_refused_by_name(self) -> None:
        ksy = load_ksy((DEFS / "wav.ksy").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError, "riff_magic"):
            parse(ksy, b"RIFX" + bytes(40))
        with self.assertRaisesRegex(ValueError, "past the end"):
            parse(ksy, b"RIFF" + struct.pack("<I", 4) + b"WAVE")


class KaitaiPluginTests(unittest.TestCase):
    def test_slot_backend_and_a_decoded_tree(self) -> None:
        plugin = KaitaiPlugin()
        slot = {s.slot_id: s for s in plugin.slot_definitions()}["decode.kaitai_wav"]
        self.assertEqual(slot.suffixes, (".wav",))
        self.assertEqual(slot.owner, "kaitai")
        backend = {b.backend_id: b for b in plugin.backends()}["kaitai-wav"]
        self.assertFalse(backend.encodes)  # one way
        self.assertIn("no way back", backend.one_way)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "s.wav").write_bytes(wav_bytes())
            out = backend.decode(root / "s.wav", root, SimpleNamespace())
            self.assertEqual(out.kind, OutcomeKind.OK, out.error)
            tree = json.loads((root / "s.json").read_text(encoding="utf-8"))
            self.assertEqual(tree["format"]["channels"], 2)
            bad = backend.decode(_write(root / "b.wav", b"nope"), root, SimpleNamespace())
            self.assertEqual(bad.kind, OutcomeKind.FAILED)
            self.assertIn("b.wav", bad.error)

    def test_detects_nothing(self) -> None:
        self.assertEqual(KaitaiPlugin().detect(SimpleNamespace()).confidence, 0.0)


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


if __name__ == "__main__":
    unittest.main()
