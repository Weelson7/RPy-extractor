""".NET managed resources (doc 8, doc 18): a minimal managed PE is written byte by byte (section
table, CLI header, BSJB metadata root, a #~ tables stream with Module + ManifestResource, a
#Strings heap and the resources blob). Every embedded resource is listed and extracted under its
name; a same-size edit is written back in place and reads back, a size change is refused by name,
and the rest of the file is untouched."""

import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from viwo.plugins.dotnet import DotnetResources, pe, resources
from viwo.plugins.dotnet.pack import ResourcesWriter

CTX = SimpleNamespace(cancel=SimpleNamespace(cancelled=False))


def _strings(names: list[str]) -> tuple[bytes, list[int]]:
    heap, idx = bytearray(b"\x00"), []
    for n in names:
        idx.append(len(heap))
        heap += n.encode("utf-8") + b"\x00"
    return bytes(heap), idx


def _tables(name_idx: list[int], offsets: list[int]) -> bytes:
    valid = (1 << 0) | (1 << 40)
    out = bytearray(struct.pack("<IBBBBQQ", 0, 2, 0, 0, 0, valid, 0))
    out += struct.pack("<II", 1, len(offsets))  # row counts: Module, ManifestResource
    out += struct.pack("<HHHHH", 0, 1, 0, 0, 0)  # Module row (Name -> string 1)
    for off, ni in zip(offsets, name_idx):
        out += struct.pack("<IIHH", off, 0, ni, 0)  # ManifestResource: offset, flags, name, impl=0
    return bytes(out)


def _metadata(tables: bytes, strings: bytes) -> bytes:
    ver = b"v4.0.30319\x00"
    ver += b"\x00" * (-len(ver) % 4)
    head = struct.pack("<IHHI", 0x424A5342, 1, 1, 0) + struct.pack("<I", len(ver)) + ver
    head += struct.pack("<HH", 0, 2)
    body_at = len(head) + 32  # two stream headers below (12 + 20 bytes)
    headers = struct.pack("<II", body_at, len(tables)) + b"#~\x00\x00"
    headers += struct.pack("<II", body_at + len(tables), len(strings)) + b"#Strings\x00\x00\x00\x00"
    return head + headers + tables + strings


def make_dotnet(res: list[tuple[str, bytes]]) -> bytes:
    strings, idx = _strings(["<Module>"] + [n for n, _ in res])
    blob, offsets, at = bytearray(), [], 0
    for _, data in res:
        offsets.append(at)
        blob += struct.pack("<I", len(data)) + data
        at += 4 + len(data)
    meta = _metadata(_tables(idx[1:], offsets), strings)
    cli = struct.pack("<IHHIIIIII", 72, 2, 5, 0, 0, 0, 0, 0, 0)  # placeholders for rvas
    cli += b"\x00" * (72 - len(cli))
    section = bytearray(cli + meta + bytes(blob))
    meta_rva, res_rva = 0x2000 + len(cli), 0x2000 + len(cli) + len(meta)
    struct.pack_into("<IIIIII", section, 8, meta_rva, len(meta), 0, 0, res_rva, len(blob))
    return _pe(bytes(section))


def _pe(section: bytes) -> bytes:
    dos = bytearray(0x80)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 0x80)
    coff = b"PE\x00\x00" + struct.pack("<HHIIIHH", 0x8664, 1, 0, 0, 0, 224, 0x2102)
    opt = bytearray(224)
    struct.pack_into("<H", opt, 0, 0x10B)  # PE32
    struct.pack_into("<I", opt, 92, 16)  # NumberOfRvaAndSizes
    struct.pack_into("<I", opt, 96 + 14 * 8, 0x2000)  # CLI header RVA = data dir 14
    sec = bytearray(40)
    sec[0:5] = b".text"
    struct.pack_into("<IIII", sec, 8, len(section), 0x2000, len(section), 0x400)
    out = bytearray(0x400)
    out[0 : len(dos)] = dos
    out[0x80 : 0x80 + len(coff)] = coff
    out[0x80 + len(coff) : 0x80 + len(coff) + 224] = opt
    pos = 0x80 + len(coff) + 224
    out[pos : pos + 40] = sec
    return bytes(out) + section


RES = [("App.Strings.resources", b"NAME=max_connections;VALUE=00020"), ("Other.resources", b"abc")]


class DotnetTests(unittest.TestCase):
    def test_lists_and_extracts(self) -> None:
        raw = make_dotnet(RES)
        got = dict(resources.extract(raw))
        self.assertEqual(got, dict(RES))

    def test_same_size_edit_reads_back_and_rest_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = make_dotnet(RES)
            dll = root / "a.dll"
            dll.write_bytes(raw)
            dest = root / "out"
            dest.mkdir()
            out = DotnetResources().extract(dll, dest, CTX)
            self.assertEqual(out.files, 2, out)
            edit = root / "e"
            edit.write_bytes(b"NAME=max_connections;VALUE=00128")  # same length
            copy = root / "copy.dll"
            copy.write_bytes(raw)
            res = ResourcesWriter().pack(copy, {"resources/App.Strings.resources": edit}, CTX)
            self.assertTrue(res.ok, res)
            self.assertEqual(res.files, 1)
            back = dict(resources.extract(copy.read_bytes()))
            self.assertEqual(back["App.Strings.resources"], b"NAME=max_connections;VALUE=00128")
            self.assertEqual(back["Other.resources"], b"abc")
            self.assertEqual(dll.read_bytes(), raw)  # original untouched

    def test_size_change_is_refused_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            copy = root / "c.dll"
            copy.write_bytes(make_dotnet(RES))
            big = root / "big"
            big.write_bytes(b"too long to fit in place")
            out = ResourcesWriter().pack(copy, {"resources/Other.resources": big}, CTX)
            self.assertEqual(out.files, 0)
            self.assertIn("Other.resources", " ".join(out.notes))


def _native_pe() -> bytes:
    """A valid PE32 with one section but no CLI data directory (a native, unmanaged assembly)."""
    dos = bytearray(0x80)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 0x80)
    coff = b"PE\x00\x00" + struct.pack("<HHIIIHH", 0x8664, 1, 0, 0, 0, 224, 0x2102)
    opt = bytearray(224)
    struct.pack_into("<H", opt, 0, 0x10B)  # PE32
    struct.pack_into("<I", opt, 92, 16)  # NumberOfRvaAndSizes; the CLI directory (14) stays 0
    sec = bytearray(40)
    sec[0:5] = b".text"
    struct.pack_into("<IIII", sec, 8, 0x100, 0x2000, 0x100, 0x400)
    return bytes(dos) + coff + bytes(opt) + bytes(sec)


class DotnetPeTests(unittest.TestCase):
    """pe.py error paths: an RVA in no section, a native PE with no CLI header, a missing BSJB."""

    def test_to_offset_rejects_an_rva_in_no_section(self) -> None:
        with self.assertRaisesRegex(ValueError, "no section"):
            pe.to_offset([(0x2000, 0x100, 0x400, 0x100)], 0x9999)

    def test_cli_header_refuses_a_pe_without_a_cli_directory(self) -> None:
        with self.assertRaisesRegex(ValueError, "no CLI header"):
            pe.cli_header(_native_pe())

    def test_streams_needs_the_bsjb_signature(self) -> None:
        with self.assertRaisesRegex(ValueError, "BSJB"):
            pe.streams(b"\x00" * 32, 0)


if __name__ == "__main__":
    unittest.main()
