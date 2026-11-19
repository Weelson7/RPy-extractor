"""Qt resources (doc 8, doc 18). A qres .rcc is written byte by byte (versions 1-3, raw and
zlib blobs) and read back: every resource comes out under its path; an unchanged resource
rebuilds byte for byte; an edit changes only its own bytes. A .qm is built from blocks and its
messages read. The embedded-resource carver finds length-prefixed QML in a binary blob."""

import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace

from viwo.plugins.qt import RccBuiltin, binres, qm, rcc
from viwo.plugins.qt.pack import RccWriter

CTX = SimpleNamespace(cancel=SimpleNamespace(cancelled=False))


def make_rcc(files: dict[str, bytes], version: int = 3, compress: frozenset = frozenset()) -> bytes:
    root: dict = {"d": {}, "f": {}}
    for path, data in files.items():
        node = root
        for part in path.split("/")[:-1]:
            node = node["d"].setdefault(part, {"d": {}, "f": {}})
        node["f"][path.split("/")[-1]] = data
    names, name_buf = {}, bytearray()

    def name_off(n: str) -> int:
        if n not in names:
            names[n] = len(name_buf)
            name_buf.extend(struct.pack(">HI", len(n), 0) + n.encode("utf-16-be"))
        return names[n]

    nodes = [{"name": "", "dir": True, "node": root}]
    queue = [0]
    while queue:
        rec = nodes[queue.pop(0)]
        kids = [("d", n, c) for n, c in rec["node"]["d"].items()]
        kids += [("f", n, d) for n, d in rec["node"]["f"].items()]
        rec["first"], rec["count"] = (len(nodes) if kids else 0), len(kids)
        for kind, n, payload in kids:
            idx = len(nodes)
            nodes.append({"name": n, "dir": kind == "d", "node": payload, "data": payload})
            if kind == "d":
                queue.append(idx)
    data_buf = bytearray()
    for rec in nodes:
        if rec["dir"]:
            continue
        d = rec["data"]
        if rec["name"] in compress:
            stored, rec["flags"] = struct.pack(">I", len(d)) + zlib.compress(d), 0x01
        else:
            stored, rec["flags"] = d, 0x00
        rec["data_off"] = len(data_buf)
        data_buf.extend(struct.pack(">I", len(stored)) + stored)
    tree = bytearray()
    for rec in nodes:
        off = 0 if rec["name"] == "" else name_off(rec["name"])
        if rec["dir"]:
            tree.extend(struct.pack(">IHII", off, 0x02, rec["count"], rec["first"]))
        else:
            tree.extend(struct.pack(">IHHHI", off, rec["flags"], 0, 0, rec["data_off"]))
        if version >= 2:
            tree.extend(b"\0" * 8)
    head = 24 if version >= 3 else 20
    header = b"qres" + struct.pack(
        ">IIII", version, head, head + len(tree) + len(name_buf), head + len(tree)
    )
    if version >= 3:
        header += struct.pack(">I", 0)
    return header + bytes(tree) + bytes(name_buf) + bytes(data_buf)


FILES = {
    "qml/main.qml": b"import QtQuick\nItem{}\n",
    "qml/sub/x.qml": b"import QtQml\n",
    "d.json": b"{}",
}


class QtRccTests(unittest.TestCase):
    def test_versions_raw_and_zlib_identity_and_edit(self) -> None:
        for version in (1, 2, 3):
            for compress in (frozenset(), frozenset({"main.qml", "x.qml"})):
                raw = make_rcc(FILES, version, compress)
                got = {p: d for p, d, note in rcc.extract(raw) if not note}
                self.assertEqual(got, FILES, (version, compress))
                self.assertEqual({p: d for p, d, _ in rcc.extract(rcc.build(raw, {}))}, FILES)
                edited = rcc.build(raw, {"d.json": b'{"n":128}'})
                back = {p: d for p, d, _ in rcc.extract(edited)}
                self.assertEqual(back["d.json"], b'{"n":128}')
                self.assertEqual(back["qml/main.qml"], FILES["qml/main.qml"])

    def test_uncompressed_v3_rebuilds_byte_for_byte(self) -> None:
        raw = make_rcc(FILES, 3)
        self.assertEqual(rcc.build(raw, {}), raw)

    def test_extract_and_pack_verify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            res = root / "r.rcc"
            res.write_bytes(make_rcc(FILES, 3))
            dest = root / "out"
            dest.mkdir()
            self.assertEqual(RccBuiltin().extract(res, dest, CTX).files, 3)
            edit = root / "e"
            edit.write_bytes(b'{"n":128}')
            copy = root / "c.rcc"
            copy.write_bytes(make_rcc(FILES, 3))
            out = RccWriter().pack(copy, {"d.json": edit}, CTX)
            self.assertTrue(out.ok, out)
            self.assertEqual(RccWriter().verify(copy, {"d.json": edit}, CTX), [])


class QtQmTests(unittest.TestCase):
    def test_messages_parsed(self) -> None:
        def sub(tag, data):
            return bytes([tag]) + struct.pack(">I", len(data)) + data

        msg = (
            sub(0x06, b"Hello")
            + sub(0x07, "Ctx".encode())
            + sub(0x03, "Hallo".encode("utf-16-be"))
            + b"\x01"
        )
        body = msg
        qmfile = (
            qm.MAGIC
            + b"\xa7"
            + struct.pack(">I", 5)
            + b"de_DE"
            + b"\x69"
            + struct.pack(">I", len(body))
            + body
        )
        out = qm.messages(qmfile)
        self.assertEqual(out, [{"source": "Hello", "context": "Ctx", "translation": "Hallo"}])
        self.assertIn(b'"language": "de_DE"', qm.to_json(qmfile))


class QtBinResTests(unittest.TestCase):
    def test_carves_length_prefixed_qml(self) -> None:
        qml = b"import QtQuick\nItem { property int x: 20 }\n"
        blob = b"\x00\x00\x00\x00" + struct.pack(">I", len(qml)) + qml + b"\xff\xff"
        found = binres.carve(blob)
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0][0].endswith(".qml"))
        self.assertEqual(found[0][1], qml)

    def test_kind_rejects_binary_and_unrecognized_text(self) -> None:
        self.assertIsNone(binres._kind(b"\x00" * 50 + b"import QtQuick"))  # too many NULs: not text
        self.assertIsNone(binres._kind(b"just some plain prose, nothing Qt here"))  # no pattern

    def test_carve_skips_a_bad_length_a_start_offset_and_a_non_text_blob(self) -> None:
        qml = b"import QtQuick\nItem{}"
        too_short = struct.pack(">I", 5) + qml  # length 5 < 16, and the match sits at offset 4
        self.assertEqual(binres.carve(too_short), [])  # bad length and prefix < 0 both skipped
        nulls = b"import QtQuick\n" + b"\x00" * 200  # a valid length but the blob is not text
        self.assertEqual(binres.carve(struct.pack(">I", len(nulls)) + nulls), [])


class QtQmEdgeTests(unittest.TestCase):
    def test_blocks_rejects_bad_magic_and_an_overrun(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a .qm"):
            qm.blocks(b"\x00" * 16)
        with self.assertRaisesRegex(ValueError, "past the end"):
            qm.blocks(qm.MAGIC + b"\x69" + struct.pack(">I", 99))  # declares 99, has none

    def test_messages_stops_at_an_unknown_sub_record(self) -> None:
        body = bytes([0x06]) + struct.pack(">I", 1) + b"A" + bytes([0x55])  # 0x55 not a sub record
        qmfile = qm.MAGIC + b"\x69" + struct.pack(">I", len(body)) + body
        self.assertEqual(qm.messages(qmfile), [])  # it broke before a record was completed


class QtRccEdgeTests(unittest.TestCase):
    def test_parse_header_rejects_bad_magic(self) -> None:
        with self.assertRaisesRegex(ValueError, "not an rcc"):
            rcc.parse_header(b"XXXX" + b"\x00" * 16)

    def test_blob_reports_zstd_and_a_short_blob(self) -> None:
        with self.assertRaisesRegex(ValueError, "zstd"):
            rcc.blob(struct.pack(">I", 3) + b"abc", 0, 0, rcc.COMPRESSED_ZSTD)
        with self.assertRaisesRegex(ValueError, "past the end"):
            rcc.blob(struct.pack(">I", 10) + b"abc", 0, 0, 0)  # declares 10, has 3

    def test_extract_notes_a_blob_it_cannot_read(self) -> None:
        raw = bytearray(make_rcc({"a.txt": b"hello"}, 3))
        _, _, files, _, _ = rcc.read_tree(bytes(raw))
        struct.pack_into(">H", raw, files[0][3] + 4, rcc.COMPRESSED_ZSTD)  # flag the file node zstd
        notes = {path: note for path, _, note in rcc.extract(bytes(raw))}
        self.assertIn("zstd", notes["a.txt"])


class QtRccPackEdgeTests(unittest.TestCase):
    def test_pack_reports_a_container_it_cannot_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = root / "bad.rcc"
            bad.write_bytes(b"not an rcc at all")
            src = root / "s"
            src.write_bytes(b"x")
            out = RccWriter().pack(bad, {"d.json": src}, CTX)
            self.assertFalse(out.ok, out)
            self.assertIn("rcc not rebuilt", out.error)

    def test_verify_flags_a_member_that_differs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy = root / "c.rcc"
            copy.write_bytes(make_rcc(FILES, 3))  # d.json holds b"{}"
            other = root / "o"
            other.write_bytes(b'{"n":1}')  # differs from what the rcc holds
            self.assertEqual(RccWriter().verify(copy, {"d.json": other}, CTX), ["d.json"])


if __name__ == "__main__":
    unittest.main()
