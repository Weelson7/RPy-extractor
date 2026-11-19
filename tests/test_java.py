"""Java jar/war/ear (doc 8, doc 18): a jar is a zip, so it extracts and rebuilds through the
stdlib zip path. Every member comes out (resources, .properties, .class bytes, the manifest); an
edited member goes back and the rest are kept; the jar reads back with the edit."""

import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from viwo.plugins.java import JarBackend, JarPacker, JavaPlugin

CTX = SimpleNamespace(cancel=SimpleNamespace(cancelled=False))


def make_jar(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


class JavaTests(unittest.TestCase):
    def test_extract_edit_repack_reads_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            members = {
                "META-INF/MANIFEST.MF": b"Manifest-Version: 1.0\r\n",
                "app/Main.class": b"\xca\xfe\xba\xbe\x00\x00\x00\x34rest",
                "app/config.properties": b"max.connections=20\n",
                "res/logo.png": b"\x89PNG\r\n\x1a\n",
            }
            jar = root / "app.jar"
            make_jar(jar, members)
            dest = root / "out"
            dest.mkdir()
            out = JarBackend().extract(jar, dest, CTX)
            self.assertEqual(out.files, len(members), out)
            self.assertEqual((dest / "app/config.properties").read_bytes(), b"max.connections=20\n")

            edit = root / "edit"
            edit.write_bytes(b"max.connections=128\n")
            copy = root / "copy.jar"
            copy.write_bytes(jar.read_bytes())
            res = JarPacker().pack(copy, {"app/config.properties": edit}, CTX)
            self.assertTrue(res.ok, res)
            with zipfile.ZipFile(copy) as zf:
                self.assertEqual(zf.read("app/config.properties"), b"max.connections=128\n")
                self.assertEqual(zf.read("app/Main.class"), members["app/Main.class"])

    def test_detects_jars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jar = root / "lib.jar"
            make_jar(jar, {"a.txt": b"x"})
            probe = SimpleNamespace(
                with_suffix=lambda *s: [jar] if ".jar" in s else [],
                head=lambda p, n=64: p.read_bytes()[:n],
                has_name=lambda *n: False,
            )
            result = JavaPlugin().detect(probe)
            self.assertGreaterEqual(result.confidence, 0.8)
            self.assertIn("Java archives (.jar/.war/.ear)", result.evidence)


if __name__ == "__main__":
    unittest.main()
