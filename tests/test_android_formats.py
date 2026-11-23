"""L3: Android binary XML and resources.arsc, on fixtures written byte by byte from the format's
description (tests/android_build.py): both decode to exactly the expected text / JSON (UTF-16
and UTF-8 pools); an unchanged decode goes back byte for byte; an edited one goes back and reads
back as edited (types kept from the original, new strings appended, every other value as it
was); what cannot go back is refused by name; damaged or random bytes are a ValueError or a
named FAILED Outcome, never another exception."""

from __future__ import annotations

import json
import random
import struct
import tempfile
import unittest
from pathlib import Path

from tests import android_build as b
from viwo.plugins.android import values
from viwo.plugins.android.arsc import read_table
from viwo.plugins.android.arsc_write import write_arsc
from viwo.plugins.android.axml import read_axml, to_text
from viwo.plugins.android.axml_write import encode_axml
from viwo.plugins.android.decoders import ArscDecoder, AxmlDecoder

EDITED = b.MANIFEST_TEXT.replace('android:versionName="1.0"', 'android:versionName="2"')
EDITED = EDITED.replace(
    'android:debuggable="false">',
    'android:debuggable="true" android:exported="false" extra="5">',
)
EDITED = EDITED.replace(
    '            <meta-data android:name="Café ☕ &amp; &lt;tags&gt;" android:value="1.5"/>\n', ""
)


def _attr(doc, element: str, name: str):
    todo = [doc.root]
    while todo:
        el = todo.pop()
        todo += [c for c in el.children if not isinstance(c, str)]
        if el.name == element:
            return next(a for a in el.attrs if a.name == name)
    raise KeyError(element)


class BinaryXmlTests(unittest.TestCase):
    def test_decodes_to_the_expected_text_in_both_pool_encodings(self) -> None:
        for utf8 in (False, True):
            text, problems = to_text(read_axml(b.manifest(utf8)))
            self.assertEqual((text, problems), (b.MANIFEST_TEXT, 0))

    def test_unchanged_goes_back_byte_for_byte(self) -> None:
        for utf8 in (False, True):
            original = b.manifest(utf8)
            self.assertEqual(encode_axml(b.MANIFEST_TEXT.encode(), original), original)
            crlf = b.MANIFEST_TEXT.replace("\n", "\r\n").encode("utf-8-sig")
            self.assertEqual(encode_axml(crlf, original), original)  # an editor's line ends

    def test_an_edit_goes_back_and_reads_back_as_edited(self) -> None:
        for utf8 in (False, True):
            out = encode_axml(EDITED.encode(), b.manifest(utf8))
            doc = read_axml(out)
            self.assertEqual(to_text(doc), (EDITED, 0))
            self.assertEqual(doc.pool.utf8, utf8)
            name = _attr(doc, "manifest", "versionName")
            self.assertEqual((name.code, name.raw), (values.STRING, "2"))  # stays a string
            self.assertEqual(_attr(doc, "application", "debuggable").data, 0xFFFFFFFF)
            self.assertEqual(_attr(doc, "application", "exported").rid, 0x01010010)
            extra = _attr(doc, "application", "extra")
            self.assertEqual((extra.code, extra.data, extra.rid), (0x10, 5, None))
            # the resource map covers exactly the names that carry an id
            self.assertEqual(sorted(doc.ids), doc.ids)
            self.assertTrue(all(doc.pool.strings[i] in b.ID_NAMES for i in range(len(doc.ids))))

    def test_an_untouched_value_keeps_its_exact_data_in_an_edited_file(self) -> None:
        plain_false = b"\x08\x00\x00\x12\x00\x00\x00\x00"  # debuggable: bool, data 0
        original = b.manifest().replace(plain_false, b"\x08\x00\x00\x12\x01\x00\x00\x00")
        shown, _ = to_text(read_axml(original))
        self.assertIn('android:debuggable="true"', shown)
        edited = shown.replace('android:versionName="1.0"', 'android:versionName="3"')
        doc = read_axml(encode_axml(edited.encode(), original))
        self.assertEqual(_attr(doc, "application", "debuggable").data, 1)  # not 0xffffffff
        self.assertEqual(_attr(doc, "manifest", "versionName").raw, "3")

    def test_what_cannot_go_back_is_named(self) -> None:
        original = b.manifest()
        unknown = b.MANIFEST_TEXT.replace("<uses-sdk ", '<uses-sdk android:brandNew="1" ')
        with self.assertRaisesRegex(ValueError, "resource id is not known"):
            encode_axml(unknown.encode(), original)
        wrong = b.MANIFEST_TEXT.replace('android:versionCode="1"', 'android:versionCode="x"')
        with self.assertRaisesRegex(ValueError, "is not a int as in the original"):
            encode_axml(wrong.encode(), original)
        with self.assertRaisesRegex(ValueError, "does not parse"):
            encode_axml(b"<manifest><unclosed></manifest>", original)

    def test_typed_values_read_back_to_the_same_data(self) -> None:
        rng = random.Random(41)
        for code in (0x01, 0x02, 0x04, 0x05, 0x06, 0x10, 0x11, 0x12, 0x1C, 0x1D, 0x1E, 0x1F):
            for _ in range(200):
                data = rng.getrandbits(32)
                if code == 0x12:
                    data = rng.choice((0, 0xFFFFFFFF))
                if code == 0x1D:
                    data |= 0xFF000000
                if code in (0x1E, 0x1F):
                    data = int.from_bytes(bytes(rng.randrange(16) * 0x11 for _ in "argb"), "big")
                    data |= 0xFF000000 if code == 0x1F else 0
                if code in (0x05, 0x06):
                    mantissa = rng.getrandbits(24)
                    data = (mantissa << 8) | (rng.randrange(4) << 4) | rng.randrange(2)
                    data = values.to_complex(values.complex_value(data), data & 0xF)
                if code == 0x04 and values.to_float(data) != values.to_float(data):
                    continue  # NaN payloads are not kept
                text = values.render(code, data)
                self.assertEqual(values.parse(code, text), data, (code, text))
        self.assertEqual(values.guess("16dp"), (0x05, 0x1001))
        self.assertEqual(values.guess("hello"), (values.STRING, 0))
        self.assertEqual(values.guess("-1"), (0x10, 0xFFFFFFFF))

    def test_damaged_files_are_value_errors_and_named_failures(self) -> None:
        rng = random.Random(42)
        good = b.manifest()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(400):
                blob = _damaged(rng, good)
                try:
                    read_axml(blob)
                except ValueError:
                    pass
                path = root / f"m{i}.xml"
                path.write_bytes(blob)
                out = root / f"o{i}"
                out.mkdir()
                outcome = AxmlDecoder().decode(path, out, None)
                self.assertTrue(outcome.ok or outcome.error)


class TableTests(unittest.TestCase):
    def test_decodes_every_chunk_form(self) -> None:
        for utf8 in (False, True):
            data = read_table(b.arsc(utf8)).data
            types = data["packages"][0]["types"]
            self.assertEqual([t["config"] for t in types][:2], ["default", "fr"])
            self.assertEqual(types[1]["entries"]["0x7f010000"]["value"], "Bonjour")
            bag = types[3]["entries"]["0x7f030000"]
            self.assertEqual(
                (bag["parent"], bag["items"][0]["value"]), ("@0x01030005", "#ff112233")
            )
            colors = types[4]["entries"]
            self.assertEqual(colors["0x7f040001"], {"key": "primary", "type": "color_argb8",
                                                    "value": "#ff0000ff"})  # fmt: skip
            self.assertEqual(types[5]["config"], "night")
            self.assertEqual(types[5]["entries"]["0x7f040001"]["value"], "7")

    def test_unchanged_goes_back_byte_for_byte_and_edits_read_back(self) -> None:
        for utf8 in (False, True):
            original = b.arsc(utf8)
            data = read_table(original).data
            self.assertEqual(write_arsc(json.loads(json.dumps(data)), original), (original, []))
            edited = json.loads(json.dumps(data))
            types = edited["packages"][0]["types"]
            types[0]["entries"]["0x7f010000"]["value"] = "Hi"  # a styled string
            types[0]["entries"]["0x7f010001"]["value"] = "Salut 🌍"
            types[3]["entries"]["0x7f030000"]["items"][0]["value"] = "#ff445566"
            types[4]["entries"]["0x7f040000"]["value"] = "#123456"
            types[4]["entries"]["0x7f040001"]["value"] = "#ff00ff00"  # the compact entry
            types[5]["entries"]["0x7f040001"].update(type="hex", value="0x10")
            out, notes = write_arsc(edited, original)
            self.assertEqual(read_table(out).data, edited)
            self.assertEqual(len(notes), 1)
            self.assertIn("style spans", notes[0])
            pool = read_table(out).pool
            self.assertEqual(pool.strings[: len(b.GLOBAL)], b.GLOBAL)  # old indexes still hold
            self.assertEqual(struct.unpack_from("<I", out, 4)[0], len(out))

    def test_a_structure_change_is_refused_by_name(self) -> None:
        original = b.arsc()
        data = read_table(original).data
        for change, where in (
            (lambda t: t[0]["entries"]["0x7f010000"].update(key="renamed"), "key"),
            (lambda t: t[1]["entries"].pop("0x7f010000"), "entries"),
            (lambda t: t[3]["entries"]["0x7f030000"]["items"].pop(), "items"),
            (lambda t: t.pop(), "types"),
        ):
            edited = json.loads(json.dumps(data))
            change(edited["packages"][0]["types"])
            with self.assertRaisesRegex(ValueError, f"structure changed at .*{where}"):
                write_arsc(edited, original)
        wrong = json.loads(json.dumps(data))
        wrong["packages"][0]["types"][4]["entries"]["0x7f040000"]["value"] = "green"
        with self.assertRaisesRegex(ValueError, "not a color_rgb8"):
            write_arsc(wrong, original)

    def test_damaged_tables_are_value_errors_and_named_failures(self) -> None:
        rng = random.Random(43)
        good = b.arsc()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(400):
                blob = _damaged(rng, good)
                try:
                    read_table(blob)
                except ValueError:
                    pass
                path = root / f"r{i}.arsc"
                path.write_bytes(blob)
                out = root / f"o{i}"
                out.mkdir()
                outcome = ArscDecoder().decode(path, out, None)
                self.assertTrue(outcome.ok or outcome.error)


def _damaged(rng: random.Random, good: bytes) -> bytes:
    if rng.random() < 0.1:
        return good[:8] + rng.randbytes(rng.randint(0, 400))
    blob = bytearray(good)
    for _ in range(rng.randint(1, 6)):
        at = rng.randrange(len(blob))
        blob[at : at + rng.choice((1, 4))] = rng.randbytes(rng.choice((1, 4)))
    return bytes(blob[: rng.randrange(1, len(blob))] if rng.random() < 0.2 else blob)


class DecoderTests(unittest.TestCase):
    def test_the_decoders_write_text_and_json_and_leave_plain_xml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AndroidManifest.xml").write_bytes(b.manifest())
            (root / "resources.arsc").write_bytes(b.arsc())
            (root / "plain.xml").write_text("<config/>")
            (root / "odd.xml").write_bytes(b"\x00\x01binary")
            out = root / "out"
            out.mkdir()
            done = AxmlDecoder().decode(root / "AndroidManifest.xml", out, None)
            self.assertEqual((done.files, done.notes), (1, ()))
            self.assertEqual((out / "AndroidManifest.text.xml").read_text("utf-8"), b.MANIFEST_TEXT)
            self.assertEqual(AxmlDecoder().decode(root / "plain.xml", out, None).files, 0)
            self.assertIn(
                "not Android binary XML", AxmlDecoder().decode(root / "odd.xml", out, None).notes[0]
            )
            self.assertIn("plain.xml", AxmlDecoder().refuses(root / "plain.xml"))
            table = ArscDecoder().decode(root / "resources.arsc", out, None)
            self.assertIn("type specs", table.notes[0])
            data = json.loads((out / "resources.arsc.json").read_text("utf-8"))
            self.assertEqual(data["format"], "viwo resources.arsc 1")
            back = root / "back.arsc"
            ArscDecoder().encode(out / "resources.arsc.json", root / "resources.arsc", back, None)
            self.assertEqual(back.read_bytes(), b.arsc())
            (out / "bad.json").write_text("{}")
            self.assertFalse(
                ArscDecoder().encode(out / "bad.json", root / "resources.arsc", back, None).ok
            )
            (out / "e.xml").write_text(EDITED, encoding="utf-8")
            done = AxmlDecoder().encode(out / "e.xml", root / "AndroidManifest.xml", back, None)
            self.assertTrue(done.ok, done.error)
            self.assertEqual(to_text(read_axml(back.read_bytes()))[0], EDITED)


if __name__ == "__main__":
    unittest.main()
