"""L2: the 3D preview of SORT. Properties: every model extension is the `model` kind, in any
letter case, and its preview answers a URL like the other media; the viewer script is served
only from its pinned copy under third_party/ (absent: no file, and no other name under
/vendor/ is ever answered); the pin is HTTPS with a sha256, and the page imports exactly a
path the server knows."""

import random
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.helpers import runtime
from viwo.api import plugin_assets
from viwo.contracts.errors import ViwoError
from viwo.core import thirdparty
from viwo.core.curation import sorting
from viwo.core.media import MODEL, media_type

ROOT = Path(__file__).resolve().parents[1]


class ModelPreviewTests(unittest.TestCase):
    def test_a_model_is_its_own_kind_and_previews_by_url(self) -> None:
        rng = random.Random(67)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "ws"
            (folder / "glb").mkdir(parents=True)
            for ext in sorted(MODEL):
                spelled = "".join(rng.choice((c.upper(), c)) for c in ext)
                self.assertEqual(media_type(spelled), "model")
                file = folder / "glb" / f"hero{rng.randint(0, 99)}{ext}"
                file.write_bytes(b"glTF" + rng.randbytes(20))
                answer = sorting.preview(folder, sorting.encode(folder.resolve(), file))
                self.assertEqual((answer["type"], answer["name"]), ("model", file.name))
                self.assertTrue(answer["url"].startswith("/preview/"))
            self.assertEqual(media_type(".obj"), "other")  # not opened by the viewer: not claimed

    def test_the_viewer_script_comes_only_from_its_pinned_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = runtime(Path(tmp))
            path = next(iter(plugin_assets.VENDOR))
            home = thirdparty.home_of(rt.config) / "third_party" / plugin_assets.VENDOR[path]
            asked = []

            def install(tool, where, runner):  # the pinned installer, stood in for
                asked.append(tool)
                if len(asked) > 1:
                    home.mkdir(parents=True)
                    (home / "model-viewer.min.js").write_text("export {};")
                else:
                    raise ViwoError("failed", "no connection")

            rt.config.auto_install = False
            with mock.patch.object(thirdparty, "install_tool", install):
                self.assertIsNone(plugin_assets.vendor(rt, path))  # switched off: left out
                rt.config.auto_install = True
                self.assertIsNone(plugin_assets.vendor(rt, path))  # it failed: nothing served
                self.assertEqual(plugin_assets.vendor(rt, path), home / "model-viewer.min.js")
                plugin_assets.vendor(rt, path)
            self.assertEqual(asked, ["model-viewer"] * 2)  # installed once, then just served
            (home / "other.js").write_text("x")
            self.assertEqual(plugin_assets.vendor(rt, path), home / "model-viewer.min.js")
            sent = []
            handler = SimpleNamespace(
                app=SimpleNamespace(rt=rt), send_file=sent.append, send_error=sent.append
            )
            self.assertTrue(plugin_assets.serve(handler, path))
            for other in ("/vendor/other.js", "/vendor/../startup.ini", "/vendor/"):
                self.assertFalse(plugin_assets.serve(handler, other), other)  # not this route's
            self.assertEqual(sent, [home / "model-viewer.min.js"])

    def test_the_pin_and_the_page_agree(self) -> None:
        pin = thirdparty.manifest()["tools"]["model-viewer"]
        for os_id in ("windows", "linux"):
            self.assertTrue(pin[os_id]["url"].startswith("https://"))
            self.assertIn(f"@{pin['version']}/", pin[os_id]["url"])
            self.assertRegex(pin[os_id]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(pin[os_id]["save_as"], "model-viewer.min.js")
        page = (ROOT / "viwo/web/js/views/sort-model.js").read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'import\("([^"]+)"\)', page)), set(plugin_assets.VENDOR))


if __name__ == "__main__":
    unittest.main()
