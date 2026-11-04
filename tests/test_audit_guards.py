"""L3: the guards the 1.15 audit added. A folder that is neither a ViWo workspace nor a patched
copy (a game folder, the user's own) opened as the workspace is never curated, and its files
are untouched; a read-only call there writes no lock. A game inside its workspace is refused,
and "replace" never clears a folder ViWo did not write. Merger outputs never overwrite each
other; API paths are absolute; a Python pin bumped after a ViWo install is reinstalled; a patch
whose file the copy lacks fails alone; the page gives the API token to this machine only, or
to a LAN peer with the key."""

from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.helpers import runtime, tree_hashes
from viwo.api.app import App
from viwo.api.handlers import POST
from viwo.contracts import ViwoError
from viwo.contracts import workspace as ws
from viwo.contracts.pipeline import OnExisting


class CurationGuardTests(unittest.TestCase):
    def test_a_foreign_folder_is_never_curated_and_an_owned_one_is(self) -> None:
        rng = random.Random(15)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = App(runtime(root))
            game = root / "game"
            for name in ("Data", "Engine", "png"):
                (game / name).mkdir(parents=True)
            for i in range(rng.randint(3, 8)):
                (game / rng.choice(["Data", "Engine", "png"]) / f"f{i}.png").write_bytes(b"x" * i)
            before = tree_hashes(game)
            app.set_workspace(game)
            for route, body in (
                ("/api/keep-selected", {"selectedExts": ["png"]}),
                ("/api/trash", {"folder": "Data"}),
                ("/api/clear-trash", {}),
                ("/api/sort-trash", {"path": "png/f1.png"}),
                ("/api/sanitizer/apply", {"planId": "x"}),
            ):
                said = POST[route](app, body)
                self.assertEqual(said["code"], "refused", (route, said))
            self.assertEqual(tree_hashes(game), before)  # not one file moved
            self.assertFalse((game / ws.METADATA_DIR).exists())  # nor a lock written
            owned = root / "ws"
            (owned / "png").mkdir(parents=True)
            (owned / "png" / "a.png").write_bytes(b"png")
            from viwo.core.workspace import claim

            claim(owned)
            app.set_workspace(owned)
            self.assertTrue(POST["/api/trash"](app, {"folder": "png"})["success"])
            fresh = root / "fresh"  # empty: ViWo may start writing there
            fresh.mkdir()
            app.set_workspace(fresh)
            self.assertNotEqual(POST["/api/clear-trash"](app, {}).get("code"), "refused")


class ExtractionGuardTests(unittest.TestCase):
    def test_a_game_inside_its_workspace_and_a_foreign_replace_are_refused(self) -> None:
        from viwo.core.pipeline.guard import refuse_writes_inside
        from viwo.core.workspace import precheck

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "W" / "pak").mkdir(parents=True)
            with self.assertRaises(ViwoError) as err:
                refuse_writes_inside(root / "W" / "pak", workspace=root / "W")
            self.assertIn("inside the workspace", err.exception.message)
            refuse_writes_inside(root / "W" / "pak", temp_folder=root)  # temp may hold it
            default = root / "default"
            default.mkdir()
            (default / "notes.txt").write_text("mine")
            with self.assertRaises(ViwoError) as err:
                precheck(default, OnExisting.REPLACE, default)
            self.assertIn("replace would delete", err.exception.message)
            precheck(default, OnExisting.NEW, default)  # a fresh sibling is fine


class SmallerFixTests(unittest.TestCase):
    def test_merger_outputs_never_overwrite_each_other(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            first = ws.next_free(out / "Scene_1.mp4")
            first.write_bytes(b"one")
            self.assertEqual(ws.next_free(out / "Scene_1.mp4").name != "Scene_1.mp4", True)

    def test_repack_and_diff_take_absolute_paths_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = App(runtime(Path(tmp)))
            self.assertEqual(
                POST["/api/repack"](app, {"out": "patched"})["code"], "invalid_request"
            )
            said = POST["/api/analysis/diff"](app, {"old": "a", "new": "b"})
            self.assertEqual(said["code"], "invalid_request")

    def test_a_bumped_python_pin_is_installed_again_a_foreign_one_left_alone(self) -> None:
        from viwo.core import thirdparty

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            pins = {"unitypy": "UnityPy==9.9"}
            with mock.patch.object(thirdparty, "manifest", return_value={"python": pins}):
                self.assertFalse(thirdparty.python_stale("unitypy", home))  # not ViWo's install
                (home / "third_party" / "python").mkdir(parents=True)
                marker = home / "third_party" / "python" / thirdparty.PINS
                marker.write_text(json.dumps({"unitypy": "UnityPy==1.0"}))
                self.assertTrue(thirdparty.python_stale("unitypy", home))
                marker.write_text(json.dumps({"unitypy": "UnityPy==9.9"}))
                self.assertFalse(thirdparty.python_stale("unitypy", home))

    def test_a_patch_whose_file_the_copy_lacks_fails_alone(self) -> None:
        from viwo.core import patchsets

        with tempfile.TemporaryDirectory() as tmp:
            result = {"offset": 0, "new": "90", "file": "gone.exe", "old": "00"}
            self.assertFalse(patchsets.write(Path(tmp), {"file": "gone.exe"}, result))
            report = {"results": [result]}
            patchsets.export(Path(tmp), {"patches": [{"file": "gone.exe"}]}, report, Path(tmp), "p")
            self.assertIn("not in this folder", (Path(tmp) / "p.diff.txt").read_text())


class TokenTests(unittest.TestCase):
    def test_the_page_carries_the_token_for_this_machine_or_the_key_only(self) -> None:
        from viwo.api import server

        sent = []
        handler = SimpleNamespace(
            token="T0KEN", send_error=lambda code: sent.append(("error", code)),
            send_file=lambda target, html_token: sent.append((target.name, html_token)),
        )  # fmt: skip
        for peer, key, want in (
            ("127.0.0.1", "", True),
            ("192.168.1.9", "", False),
            ("192.168.1.9", "T0KEN", True),
            ("192.168.1.9", "nope", False),
        ):
            handler.client_address = (peer, 5000)
            sent.clear()
            server.Handler._static(handler, "/", key)
            self.assertEqual(sent, [("index.html", want)], (peer, key))


if __name__ == "__main__":
    unittest.main()
