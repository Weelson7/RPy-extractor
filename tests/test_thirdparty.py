"""L3: third_party installer: verified download, safe unpack, discovery, checksum refusal."""

from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from viwo.contracts import ViwoError
from viwo.core import thirdparty


def fake_manifest(archive: Path, digest: str) -> dict:
    spec = {
        "url": archive.as_uri(),
        "sha256": digest,
        "size": archive.stat().st_size,
        "kind": "zip",
        "find": "repak.exe" if thirdparty.PLATFORM == "windows" else "repak",
    }
    return {"python": {}, "tools": {"repak": {thirdparty.PLATFORM: spec}}}


class InstallerTests(unittest.TestCase):
    def test_install_verify_and_find(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            name = "repak.exe" if thirdparty.PLATFORM == "windows" else "repak"
            data = io.BytesIO()
            with zipfile.ZipFile(data, "w") as z:
                z.writestr(f"repak_cli/{name}", b"binary")
                z.writestr("../evil.txt", b"no")
            archive = root / "repak.zip"
            archive.write_bytes(data.getvalue())
            good = hashlib.sha256(data.getvalue()).hexdigest()
            home = root / "home"
            with mock.patch.object(thirdparty, "manifest", lambda: fake_manifest(archive, good)):
                path = thirdparty.install_tool("repak", home, None)
                self.assertEqual(Path(path), home / "third_party" / "repak" / "repak_cli" / name)
                self.assertEqual(thirdparty.found_tools(home), {"repak": path})
                self.assertFalse(list(root.rglob("evil.txt")))
            with mock.patch.object(
                thirdparty, "manifest", lambda: fake_manifest(archive, "0" * 64)
            ):
                with self.assertRaises(ViwoError) as err:
                    thirdparty.install_tool("repak", root / "other", None)
                self.assertEqual(err.exception.code, "refused")
                self.assertFalse((root / "other" / "third_party" / "repak").exists())

    def test_manifest_pins_match_pyproject(self) -> None:
        text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text()
        for pin in thirdparty.manifest()["python"].values():
            self.assertIn(f'"{pin}"', text)


if __name__ == "__main__":
    unittest.main()
