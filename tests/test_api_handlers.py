"""L6: the workspace and tool routes of the web UI, as properties over random workspaces: group
trash, restore, delete and keep-selected never lose or invent a file (the bytes come back on
restore), the asset window pages through every file exactly once, save-remaining copies every
remaining asset out byte for byte, the patch and mod routes do what the core does, and the system
jobs rebind the tools they installed."""

from __future__ import annotations

import hashlib
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import runtime
from viwo.api.app import App
from viwo.api.handlers import GET, POST
from viwo.core.workspace import claim

GROUPS = ("png", "ogg", "txt", "json", "dds")


def _workspace(root: Path, rng: random.Random) -> Path:
    ws = root / "ws"
    (ws / ".viwo-workspace").parent.mkdir(parents=True, exist_ok=True)
    (ws / ".viwo-workspace").write_text("")
    for group in rng.sample(GROUPS, rng.randint(2, len(GROUPS))):
        for i in range(rng.randint(1, 5)):
            (ws / group).mkdir(exist_ok=True)
            (ws / group / f"f{i}.{group}").write_bytes(rng.randbytes(rng.randint(1, 80)))
    return ws


def _files(ws: Path) -> dict[str, str]:
    """name -> sha256 of every asset file, wherever it sits (kept or in the trash)."""
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in ws.rglob("*")
        if p.is_file() and not p.name.startswith(".viwo")
    }


class CurationRouteTests(unittest.TestCase):
    def app(self, root: Path, ws: Path) -> App:
        app = App(runtime(root, "[startup]\nfeatures = extraction, sorting, merger\n"))
        app.set_workspace(ws)
        return app

    def test_group_moves_never_lose_or_invent_a_file(self) -> None:
        rng = random.Random(4)
        for _ in range(6):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                ws = _workspace(root, rng)
                app, before, deleted = self.app(root, ws), _files(ws), set()
                for _ in range(12):
                    group = rng.choice([*GROUPS, "../evil", ""])
                    op = rng.choice(["/api/trash", "/api/restore", "/api/delete"])
                    gone = {n for n in _files(ws) if n.endswith(f".{group}")}
                    answer = POST[op](app, {"folder": group})
                    if group in ("../evil", ""):
                        self.assertFalse(answer["success"])  # never outside the workspace
                    if answer["success"] and op == "/api/delete":
                        deleted |= gone
                    now = _files(ws)
                    want = {n: h for n, h in before.items() if n not in deleted}
                    self.assertEqual(now, want, op)  # same bytes, nothing invented
                    s = GET["/api/status"](app, {})
                    self.assertEqual(s["totalKept"] + s["totalTrashed"], len(now))
                for group in GROUPS:  # everything still in the trash comes back as it was
                    POST["/api/restore"](app, {"folder": group})
                self.assertEqual(GET["/api/status"](app, {})["totalTrashed"], 0)

    def test_keep_selected_and_clear_keep_exactly_the_choice(self) -> None:
        rng = random.Random(8)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = _workspace(root, rng)
            app = self.app(root, ws)
            present = set(GET["/api/status"](app, {})["kept"])
            keep = set(rng.sample(sorted(present), rng.randint(1, len(present))))
            POST["/api/keep-selected"](app, {"selectedExts": [f".{e}" for e in keep]})
            self.assertEqual(set(GET["/api/status"](app, {})["kept"]), keep)
            cleared = POST["/api/clear-trash"](app, {})
            self.assertEqual(cleared["summary"]["totalTrashed"], 0)
            self.assertEqual({Path(n).suffix[1:] for n in _files(ws)}, keep)

    def test_pages_cover_every_file_once_and_save_remaining_copies_them(self) -> None:
        rng = random.Random(2)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = _workspace(root, rng)
            app = self.app(root, ws)
            limit, seen, offset = rng.randint(1, 4), [], 0
            while True:
                page = GET["/api/assets-window"](app, {"offset": offset, "limit": limit})
                names = [a["name"] for a in page.get("assets", page.get("items", []))]
                seen += names
                offset += limit
                if not names or offset >= page["total"]:
                    break
            self.assertEqual(len(seen), len(set(seen)))
            self.assertEqual(len(seen), page["total"])
            self.assertEqual(sum(page["typeCounts"].values()), page["total"])
            self.assertFalse(
                GET["/api/assets-window"](app, {"offset": "x", "limit": None}).get("error")
            )  # junk paging falls back to the defaults
            out = root / "saved"
            refused = POST["/api/save-remaining-assets"](
                app, {"destinationPath": "rel", "all": True}
            )
            self.assertFalse(refused["success"])
            missing = POST["/api/save-remaining-assets"](
                app, {"destinationPath": str(out), "all": True}
            )
            self.assertFalse(missing["success"])  # the destination must exist
            out.mkdir()
            before = sorted(_files(ws).values())
            moved = POST["/api/save-remaining-assets"](
                app, {"destinationPath": str(out), "all": True}
            )
            self.assertEqual(moved["moved"], len(before))
            self.assertEqual(sorted(_files(out).values()), before)  # every asset, byte for byte
            self.assertEqual(_files(ws), {})  # moved out, none left behind
            leak = GET["/api/assets-window-preview"](app, {"path": "../../etc/passwd"})
            self.assertFalse(leak["success"])

    def test_workspace_folder_and_merger_routes_take_absolute_paths_only(self) -> None:
        rng = random.Random(1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = _workspace(root, rng)
            app = self.app(root, ws)
            self.assertTrue(GET["/api/workspace"](app, {})["owned"])
            self.assertFalse(
                POST["/api/workspace"](app, {"path": str(root / "nowhere")})["success"]
            )
            default = POST["/api/workspace"](app, {"path": str(app.server.workspace)})
            self.assertTrue(default["isDefault"] and app.server.workspace.is_dir())
            app.set_workspace(ws)
            shell = mock.Mock()
            shell.open_folder.return_value = (False, "no file manager")
            shell.pick_folder.return_value = root
            shell.pick_file.return_value = root / "song.txt"
            with mock.patch.object(app.rt.os, "_shell", shell):
                self.assertEqual(POST["/api/open-folder"](app, {"path": ""})["code"], "not_found")
                self.assertEqual(
                    POST["/api/open-folder"](app, {"path": str(ws)})["hint"],
                    "open the folder by hand",
                )
                self.assertEqual(GET["/api/browse-folder"](app, {})["path"], str(root))
                bad = POST["/api/media-merger/browse-overlay"](app, {})
                self.assertEqual(bad["code"], "invalid_request")  # not an audio file
            listed = POST["/api/media-merger/list"](
                app, {"workingDir": "ws", "allowedExts": ["png"]}
            )
            self.assertEqual(listed["code"], "not_found")  # a relative dir is refused, not swapped
            listed = POST["/api/media-merger/list"](app, {"allowedExts": ["png"]})
            self.assertEqual(listed["workingDir"], str(ws))  # none given: the workspace
            state = GET["/api/media-merger/state"](app, {})
            self.assertEqual(state["workingDir"], str(ws))


class ToolJobRouteTests(unittest.TestCase):
    def test_patch_and_mod_routes_do_what_the_core_does(self) -> None:
        import json

        from tests.test_mods import game_and_copy

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, copy = game_and_copy(root)
            app = App(runtime(root))
            app.set_workspace(root / "ws")
            set_path = root / "p.patch.json"
            out = root / "patched"
            self.assertFalse(
                POST["/api/patch"](
                    app, {"gamePath": str(game), "patchSet": str(set_path), "out": "rel"}
                )["success"]
            )
            done = POST["/api/patch"](
                app, {"gamePath": str(game), "patchSet": str(set_path), "out": str(out)}
            )
            self.assertTrue(done["success"], done)
            self.assertEqual((out / "Game.exe").read_bytes()[2], 0x90)
            mod = root / "m.zip"
            body = {"gamePath": str(game), "mod": str(mod), "copy": str(copy)}
            self.assertTrue(
                POST["/api/mod"](app, {**body, "action": "pack", "name": "m"})["success"]
            )
            self.assertTrue(POST["/api/mod"](app, {**body, "action": "check"})["fits"])
            target = root / "second"
            applied = POST["/api/mod"](app, {**body, "action": "apply", "copy": str(target)})
            self.assertTrue(applied["success"], applied)
            self.assertEqual((target / "Game.exe").read_bytes()[2], 0x90)
            for bad in (
                {"action": "nope"},
                {"action": "apply", "mod": ""},
                {"action": "pack", "copy": ""},
            ):
                self.assertFalse(POST["/api/mod"](app, {**body, **bad})["success"], bad)
            self.assertIn("schema", json.loads(set_path.read_text()))

    def test_system_jobs_rebind_what_they_installed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = App(runtime(Path(tmp)))
            for installed in ([], ["vgmstream"]):
                report = {"installed": installed, "failed": [], "ready": 1, "total": 1}
                with (
                    mock.patch("viwo.api.handlers_tools.preflight", return_value=report),
                    mock.patch.object(app, "reload") as reload,
                ):
                    done = POST["/api/preflight"](app, {})
                self.assertTrue(done["success"] and done["jobId"])
                self.assertEqual(reload.called, bool(installed))
            with (
                mock.patch("viwo.api.handlers_tools.install", return_value={"installed": "x"}),
                mock.patch.object(app, "reload") as reload,
            ):
                self.assertEqual(POST["/api/preflight/install"](app, {"id": "x"})["installed"], "x")
            reload.assert_called_once()


class NeverBlockedNeverSilentTests(unittest.TestCase):
    def test_a_writing_call_closes_previews_and_every_failure_is_logged(self) -> None:
        rng = random.Random(17)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ws" / "flac").mkdir(parents=True)
            app = App(runtime(root))
            claim(root / "ws")
            app.set_workspace(root / "ws")
            for case in range(20):
                files = [
                    root / "ws" / "flac" / f"{case}-{i}.flac" for i in range(rng.randint(1, 4))
                ]
                handles = []
                for path in files:
                    path.write_bytes(b"f" * rng.randint(1, 2000))
                    handles.append(path.open("rb"))  # a page holding its preview stream open
                    app.preview(handles[-1], True)
                writes = rng.random() < 0.7
                target = root / "ws" / f"moved-{case}"

                def move(target=target):  # Windows refuses this while a file inside is open
                    (root / "ws" / "flac").rename(target)
                    target.rename(root / "ws" / "flac")
                    return {"success": True}

                answer = app.locked(move if writes else lambda: {"success": True}, None, writes)
                self.assertTrue(answer["success"], (case, answer))
                self.assertEqual([h.closed for h in handles], [writes] * len(handles), case)
                for handle in handles:
                    handle.close()
                    app.preview(handle, False)
            before = len(app.logs())
            for answer, logged in (
                ({"success": True}, False),
                (
                    {
                        "success": False,
                        "error": "file in use",
                        "code": "failed",
                        "hint": "close it",
                    },
                    True,
                ),
                ({"ok": False, "error": {"message": "no tool", "code": "unavailable"}}, True),
                ({"success": False, "error": "replace?", "code": "needs_decision"}, False),
                ({"success": False, "error": "No folder selected", "code": "cancelled"}, False),
            ):
                app.said("POST /api/x", answer)
                self.assertEqual(len(app.logs()) - before, int(logged), answer)
                before = len(app.logs())
            self.assertIn("[FAILED] POST /api/x: no tool", app.logs()[-1])
            self.assertIn("file in use (close it)", app.logs()[-2])


if __name__ == "__main__":
    unittest.main()
