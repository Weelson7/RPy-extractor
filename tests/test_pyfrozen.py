"""Frozen Python (doc 8, doc 18): a PyInstaller CArchive (bootloader prefix, members, TOC,
cookie) with an inner PYZ is written byte by byte. Data, a top-level module and every PYZ module
come out (modules as .pyc with the real magic); an unchanged exe rebuilds byte for byte; an
edited data file goes back and the rest are kept. decode.pyc disassembles a host-version .pyc."""

import importlib.util
import marshal
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace

from viwo.plugins.pyfrozen import PycDecoder, PyiBuiltin
from viwo.plugins.pyfrozen import carchive as c
from viwo.plugins.pyfrozen.pack import PyiWriter, build_archive

CTX = SimpleNamespace(cancel=SimpleNamespace(cancelled=False))
MAGIC = importlib.util.MAGIC_NUMBER


def _code(src: str):
    return compile(src, "<m>", "exec")


def make_pyz(mods: dict[str, bytes]) -> bytes:
    body, table = bytearray(), []
    for name, code in mods.items():
        blob = zlib.compress(code)
        table.append((name, (False, 12 + len(body), len(blob))))  # pos is absolute in the PYZ
        body += blob
    header = c.PYZ_MAGIC + MAGIC + struct.pack("!i", 12 + len(body))
    # fix positions now that header length (12) is known: pos already includes the 12-byte header
    return header + bytes(body) + marshal.dumps(table)


def make_exe(prefix: bytes, members: list[tuple[str, bytes, bytes]]) -> bytes:
    """members: (name, typecode, data). Builds [prefix][bodies][TOC][cookie]."""
    body, table, at = bytearray(), bytearray(), 0
    for name, typ, data in members:
        raw_name = name.encode() + b"\x00"
        slen = c.ENTRY_SIZE + len(raw_name)
        slen += (-slen) % 16
        table += struct.pack(c.ENTRY, slen, at, len(data), len(data), 0, typ)
        table += raw_name + b"\x00" * (slen - c.ENTRY_SIZE - len(raw_name))
        body += data
        at += len(data)
    toc_at = len(body)
    total = toc_at + len(table) + c.COOKIE_SIZE
    cookie = struct.pack(c.COOKIE, c.PKG_MAGIC, total, toc_at, len(table), 313, b"python313.dll")
    return prefix + bytes(body) + bytes(table) + cookie


class PyFrozenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pyz = make_pyz(
            {"json": marshal.dumps(_code("x = 1")), "os.path": marshal.dumps(_code("y = 2"))}
        )
        self.app = marshal.dumps(_code("print('hi')"))
        self.members = [
            ("data.txt", b"x", b"max_connections=20\n"),
            ("app", b"s", self.app),
            ("PYZ-00.pyz", b"z", self.pyz),
        ]
        self.raw = make_exe(b"MZ" + b"\x00" * 4094, self.members)

    def test_reader_finds_everything(self) -> None:
        start, toc_abs, toc_len, pylib = c.find_archive(self.raw)
        self.assertEqual(pylib, b"python313.dll")
        entries = c.toc(self.raw, toc_abs, toc_len)
        self.assertEqual({n for n, *_ in entries}, {"data.txt", "app", "PYZ-00.pyz"})
        self.assertEqual(c.pyz_magic(self.raw, start, entries), MAGIC)
        mods = c.pyz_modules(self.pyz)
        self.assertEqual({m[0] for m in mods}, {"json", "os.path"})

    def test_extract_writes_pyc_and_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            out = PyiBuiltin().extract(self._exe(tmp), dest, CTX)
            self.assertTrue(out.ok, out)
            self.assertEqual((dest / "data.txt").read_bytes(), b"max_connections=20\n")
            self.assertEqual((dest / "app.pyc").read_bytes()[:4], MAGIC)
            self.assertTrue((dest / "PYZ-contents/json.pyc").is_file())
            self.assertTrue((dest / "PYZ-contents/os/path.pyc").is_file())

    def test_rebuild_identity_and_edit(self) -> None:
        self.assertEqual(build_archive(self.raw, {}), self.raw)
        edited = build_archive(self.raw, {"data.txt": b"max_connections=128\n"})
        start, ta, tl, _ = c.find_archive(edited)
        got = {
            n: c.member_bytes(edited, start, dp, dl, cf)
            for n, dp, dl, _, cf, _ in c.toc(edited, ta, tl)
        }
        self.assertEqual(got["data.txt"], b"max_connections=128\n")
        self.assertEqual(got["app"], self.app)

    def test_pack_from_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "app.exe"
            copy.write_bytes(self.raw)
            edit = Path(tmp) / "e"
            edit.write_bytes(b"max_connections=128\n")
            out = PyiWriter().pack(copy, {"data.txt": edit}, CTX)
            self.assertTrue(out.ok, out)
            start, ta, tl, _ = c.find_archive(copy.read_bytes())
            got = {
                n: c.member_bytes(copy.read_bytes(), start, dp, dl, cf)
                for n, dp, dl, _, cf, _ in c.toc(copy.read_bytes(), ta, tl)
            }
            self.assertEqual(got["data.txt"], b"max_connections=128\n")

    def test_decode_pyc_disassembles_host_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out"
            dest.mkdir()
            pyc = Path(tmp) / "m.pyc"
            pyc.write_bytes(c.as_pyc(MAGIC, self.app))
            out = PycDecoder().decode(pyc, dest, CTX)
            self.assertTrue(out.ok, out)
            self.assertIn("LOAD_CONST", (dest / "m.dis.txt").read_text())

    def _exe(self, tmp: str) -> Path:
        path = Path(tmp) / "a.exe"
        path.write_bytes(self.raw)
        return path


if __name__ == "__main__":
    unittest.main()
