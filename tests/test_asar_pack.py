"""L3: pack.asar's Electron details (doc 18). For random archives whose members carry
`integrity` (a whole-file SHA-256 and one per 4 MB block) and some marked `unpacked`: after an
edit every integrity record matches its member's bytes, block by block; an unpacked member is
written into `<archive>.unpacked/` (a new subfolder too) and never into the archive; a name that
leads out of that folder is said, never written; the archive reads back with every edit."""

import hashlib
import json
import random
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from viwo.plugins.electron import AsarBuiltin
from viwo.plugins.electron.pack import BLOCK, AsarWriter, _files, _header

CTX = SimpleNamespace(cancel=SimpleNamespace(cancelled=False))


def build(files: dict[str, bytes], unpacked: set[str]) -> bytes:
    """An asar with an integrity record on every packed member (Electron's layout)."""
    tree: dict = {"files": {}}
    body, at = b"", 0
    for path, data in files.items():
        node = tree
        for part in path.split("/")[:-1]:
            node = node["files"].setdefault(part, {"files": {}})
        if path in unpacked:
            node["files"][path.split("/")[-1]] = {"size": len(data), "unpacked": True}
            continue
        node["files"][path.split("/")[-1]] = {
            "size": len(data), "offset": str(at), "integrity": {"algorithm": "SHA256", "hash": "0"}
        }  # fmt: skip
        body, at = body + data, at + len(data)
    raw = json.dumps(tree).encode()
    pickle = struct.pack("<I", len(raw)) + raw
    pickle += b"\0" * (-len(pickle) % 4)
    return struct.pack("<III", 4, len(pickle) + 4, len(pickle)) + pickle + body


class AsarPackTests(unittest.TestCase):
    def test_integrity_follows_every_edit_and_unpacked_members_go_beside(self) -> None:
        rng = random.Random(77)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in range(6):
                files = {f"d{i % 2}/f{i}.js": rng.randbytes(rng.randint(0, 900)) for i in range(5)}
                files["big.bin"] = rng.randbytes(BLOCK + rng.randint(1, 4096))  # two blocks
                files["native/addon.node"] = rng.randbytes(64)
                marked = {"native/addon.node"}
                archive = root / f"c{case}" / "app.asar"
                archive.parent.mkdir()
                archive.write_bytes(build(files, marked))
                edits = {}
                for n, name in enumerate([*rng.sample(sorted(files), 3), "native/addon.node"]):
                    edit = root / f"e{case}-{n}"
                    edit.write_bytes(rng.randbytes(rng.choice([0, 10, BLOCK + 7])))
                    edits[name] = edit
                out = AsarWriter().pack(archive, edits, CTX)
                self.assertEqual(out.files, len(files), out)
                self._check(archive, files, edits, marked)

    def _check(self, archive: Path, files: dict, edits: dict, marked: set) -> None:
        with open(archive, "rb") as fh:
            tree, base = _header(fh)
            for path, node in _files(tree):
                if node.get("unpacked"):
                    continue
                fh.seek(base + int(node["offset"]))
                data = fh.read(node["size"])
                self.assertEqual(data, edits[path].read_bytes() if path in edits else files[path])
                record = node["integrity"]
                self.assertEqual(record["hash"], hashlib.sha256(data).hexdigest(), path)
                blocks = [data[i : i + BLOCK] for i in range(0, len(data), BLOCK)] or [data]
                self.assertEqual(record["blocks"], [hashlib.sha256(b).hexdigest() for b in blocks])
        beside = archive.with_name("app.asar.unpacked")
        for path in marked:
            want = edits[path].read_bytes() if path in edits else None
            self.assertEqual((beside / path).read_bytes(), want, path)  # a new subfolder too

    def test_an_unpacked_name_leading_out_is_said_and_a_reader_sees_the_edits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "app.asar"
            archive.write_bytes(build({"a.js": b"old", "../evil.node": b"x"}, {"../evil.node"}))
            edit = root / "e"
            edit.write_bytes(b"new")
            out = AsarWriter().pack(archive, {"a.js": edit, "../evil.node": edit}, CTX)
            self.assertIn(
                "1 unpacked member(s) whose path leads out of the folder", " ".join(out.notes)
            )
            self.assertFalse((root / "evil.node").exists())
            dest = root / "out"
            dest.mkdir()
            AsarBuiltin().extract(archive, dest, CTX)
            self.assertEqual((dest / "a.js").read_bytes(), b"new")


if __name__ == "__main__":
    unittest.main()
