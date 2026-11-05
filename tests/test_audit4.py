"""L3/L4: the fourth audit's findings, each as a property. Members whose names differ only in
case, that Windows cannot hold, or that are named like ViWo's own files are all kept, never
overwritten, and each maps back to its original through the record; a patched copy whose
container holds such a name verifies; a Bethesda override says what each archive version needs
and why a member was not written."""

from __future__ import annotations

import random
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.helpers import make_zip, runtime
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.contracts import workspace as ws
from viwo.core.pipeline.runner import extract
from viwo.core.roundtrip import repack

POOL = ["a.txt", "A.TXT", "b/c.png", "B/c.png", "what?.js", "what*.js", "con.txt", "x.", "y "]
POOL += [ws.NAMES_FILE, ws.EXPORT_MAP, f"d/{ws.MARKER}", "a.txt"]


class NamesTests(unittest.TestCase):
    def test_every_member_is_kept_and_maps_back_to_its_name(self) -> None:
        rng = random.Random(41)
        for case in range(120):
            with tempfile.TemporaryDirectory() as tmp:
                dest, names = Path(tmp), None
                names = ws.Names(dest)
                picks = [rng.choice(POOL) for _ in range(rng.randint(1, 8))]
                for name in picks:
                    target = names.target(name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(name, encoding="utf-8")
                names.save()
                record = ws.renamed(dest)
                files = [p for p in dest.rglob("*") if p.is_file() and p != dest / ws.NAMES_FILE]
                self.assertEqual(len(files), len(picks), (case, picks))  # nothing overwritten
                for path in files:
                    rel = path.relative_to(dest).as_posix()
                    original = record.get(rel, rel)
                    self.assertEqual(original, path.read_text(encoding="utf-8").strip("/"), rel)
                    self.assertNotIn(path.name, ws.OWN_FILES, rel)  # never ViWo's own name


class RoundTripNamesTests(unittest.TestCase):
    def test_a_container_holding_a_name_windows_cannot_hold_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt, game = runtime(root), root / "love"
            game.mkdir()
            make_zip(game / "data.zip", {"what?.lua": b"keep me", "main.lua": b"print()"})
            work = root / "ws"
            extract(rt, ExtractionRequest(str(game), str(work)), "j", lambda e: None, CancelToken())
            (work / "lua" / "main.lua").write_bytes(b"print('mod')")
            report = repack(rt, work, root / "out")
            self.assertTrue(report["verified"], report)  # the untouched odd name is found
            with zipfile.ZipFile(root / "out" / "data.zip") as z:
                self.assertEqual(z.read("what?.lua"), b"keep me")  # written back as it was


class BethesdaNotesTests(unittest.TestCase):
    def test_each_archive_version_says_what_it_needs_and_why_a_member_was_not_written(self):
        from viwo.plugins.bethesda.pack import INI, INVALIDATION, LooseOverride

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "Data"
            data.mkdir()
            edit = Path(tmp) / "edit.dds"
            edit.write_bytes(b"DDS ")
            members = {"textures/a.dds": edit, "textures/b?.dds": edit, "../c.dds": edit}
            for name, head, want in (
                ("old.bsa", b"BSA\0" + bytes([103, 0, 0, 0]), INVALIDATION),
                ("fnv.bsa", b"BSA\0" + bytes([104, 0, 0, 0]), INVALIDATION),
                ("sse.bsa", b"BSA\0" + bytes([105, 0, 0, 0]), None),
                ("fo4.ba2", b"BTDX" + bytes(4), INI),
            ):
                archive = data / name
                archive.write_bytes(head + bytes(32))
                notes = LooseOverride().pack(archive, members, None).notes
                self.assertEqual(INVALIDATION in notes, want == INVALIDATION, name)
                self.assertEqual(INI in notes, want == INI, name)
                said = " ".join(notes)
                self.assertIn("1 member(s) whose path leads out of the folder", said)
                self.assertIn("1 member(s) with a name Windows cannot hold", said)
            self.assertTrue((data / "textures" / "a.dds").is_file())
            self.assertFalse((Path(tmp) / "c.dds").exists())


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        from viwo.api.app import App

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.app = App(runtime(self.root, "[plugins]\ngeneric = on\n[server]\ntemp = tmp\n"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_a_failed_install_fails_its_job_and_says_why(self) -> None:
        from unittest import mock

        from viwo.api import handlers_settings
        from viwo.contracts import ViwoError

        said = []
        refused = ViwoError("failed", "download refused")
        with mock.patch.object(handlers_settings, "install", side_effect=refused):
            job_id = handlers_settings._install_job(self.app, ["x64dbg"])
            job = self.app.jobs.wait(job_id, 30)
        said = [e.message for e in job.events]
        self.assertEqual(job.state, "failed")
        self.assertIn("x64dbg: download refused", job.error["message"])
        self.assertTrue(any("Could not install x64dbg" in m for m in said), said)

    def test_runtime_and_attach_refuse_a_foreign_workspace_and_name_a_bad_number(self) -> None:
        from viwo.api.handlers_capture import CAPTURE_POST

        game = self.root / "game"
        game.mkdir()
        (game / "Game.exe").write_bytes(b"MZ")
        self.app.set_workspace(game)  # a game folder opened as the workspace
        for route, body in (
            ("/api/runtime/dump", {"name": "Game.exe"}),
            ("/api/runtime/attach", {"gamePath": str(game), "targetKey": "game-exe"}),
        ):
            self.assertEqual(CAPTURE_POST[route](self.app, body)["code"], "refused", route)
        self.assertEqual(list(game.iterdir()), [game / "Game.exe"])  # nothing written there
        self.app.set_workspace(self.root / "ws")
        for pid in ("12a", True, [3]):
            answer = CAPTURE_POST["/api/runtime/dump"](self.app, {"pid": pid})
            self.assertEqual(answer["code"], "invalid_request", pid)

    def test_of_many_concurrent_starts_exactly_one_records(self) -> None:
        import threading

        from viwo.api.recording import recording_post

        answers, gate = [], threading.Barrier(8)

        def start(n: int) -> None:
            gate.wait()
            answers.append(
                recording_post(self.app, {"action": "start", "title": f"t{n}", "game": "G"})
            )

        threads = [threading.Thread(target=start, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        self.assertEqual(sum(bool(a["success"]) for a in answers), 1)
        self.assertEqual(
            sorted(a.get("code", "") for a in answers if not a["success"]), ["refused"] * 7
        )


if __name__ == "__main__":
    unittest.main()
