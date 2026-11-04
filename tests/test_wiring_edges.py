"""L1/L3: wiring edges. The plugin conformance check names a capability list without detect or
unpack and a dependency declared twice under two labels; a plugin whose detect raises scores
zero and says why; an unreadable file reads as empty; an extraction that needs a decision says
so; GitHub's answers become data, `None` for a missing release, or a named offline error; a
workspace that is a file, a sibling name taken, and the process's own lock are each handled."""

from __future__ import annotations

import io
import json
import os
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from viwo.contracts import OnExisting, ViwoError
from viwo.contracts.types import DependencySpec


class ConformanceTests(unittest.TestCase):
    def test_capabilities_and_duplicate_dependencies_are_named(self) -> None:
        from viwo.contracts.slots import SlotDefinition
        from viwo.core.wiring.conformance import _capability_problems, _dependency_problems

        manifest = SimpleNamespace(capabilities=("unpack", "export"))
        slots = [SlotDefinition("unarchive.x", "unarchive", "p", "b")]
        plugin = SimpleNamespace(manifest=manifest, slot_definitions=lambda: slots)
        self.assertIn("capabilities do not include detect", _capability_problems(plugin))
        manifest.capabilities = ("detect",)
        self.assertIn("unarchive slots need the unpack capability", _capability_problems(plugin))
        a, b = DependencySpec("tool", "Tool"), DependencySpec("tool", "Another Tool")
        backends = [
            SimpleNamespace(dependencies=lambda: [a]),
            SimpleNamespace(dependencies=lambda: [b]),
        ]
        twice = _dependency_problems(SimpleNamespace(backends=lambda: backends))
        self.assertEqual(twice, ["dependency tool declared twice with different labels"])


class ProbeTests(unittest.TestCase):
    def test_a_raising_detect_scores_zero_and_a_locked_file_reads_empty(self) -> None:
        from viwo.core.pipeline.probe import FolderProbe, _cached, detect_all

        broken = SimpleNamespace(detect=mock.Mock(side_effect=RuntimeError("bad marker")))
        rt = SimpleNamespace(plugins={"x": broken})
        with tempfile.TemporaryDirectory() as tmp:
            found = detect_all(rt, FolderProbe(Path(tmp)))
            self.assertEqual(found["x"].confidence, 0.0)
            self.assertIn("detect failed: bad marker", found["x"].evidence[0])
            self.assertEqual(_cached(Path(tmp) / "gone.bin", 10, 0, 4, False), b"")


class AppTests(unittest.TestCase):
    def test_a_needed_decision_is_said_and_modes_are_read(self) -> None:
        from tests.helpers import runtime
        from viwo.api.app import App, request_from_payload

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = App(runtime(root))
            job = SimpleNamespace(
                error={"code": "needs_decision", "message": "exists", "owner": "core", "hint": ""},
                job_id="j1",
            )
            with mock.patch.object(app.jobs, "submit_with_listener", return_value=job):
                with mock.patch("viwo.api.app.precheck"):
                    answer = app.extract({"gamePath": str(root), "workspace": str(root / "ws")})
            self.assertTrue(answer["needsDecision"])
            self.assertEqual(answer["jobId"], "j1")
            single = request_from_payload({"gamePath": "g", "extractionType": "unity"}, str(root))
            mixed = request_from_payload(
                {"gamePath": "g", "extractionType": "mixed", "plugins": ["unity", "godot"]},
                str(root),
            )
            self.assertEqual((single.plugins, mixed.plugins), (("unity",), ("unity", "godot")))


class GithubTests(unittest.TestCase):
    def test_answers_missing_releases_and_offline(self) -> None:
        from viwo.core import diag

        body = io.BytesIO(json.dumps({"tag_name": "v1.0.0"}).encode())
        response = mock.MagicMock()
        response.__enter__.return_value = body
        with mock.patch.object(diag.urllib.request, "urlopen", return_value=response):
            self.assertEqual(diag.github_json("https://api.github.com/x")["tag_name"], "v1.0.0")
        for code, want in ((404, None), (500, "offline")):
            error = urllib.error.HTTPError("u", code, "no", {}, None)
            with mock.patch.object(diag.urllib.request, "urlopen", side_effect=error):
                if want is None:
                    self.assertIsNone(diag.github_json("https://api.github.com/x"))
                else:
                    with self.assertRaises(ViwoError) as err:
                        diag.github_json("https://api.github.com/x")
                    self.assertEqual(err.exception.code, "offline")


class WorkspaceTests(unittest.TestCase):
    def test_a_file_a_taken_sibling_and_the_own_lock(self) -> None:
        from viwo.core import workspace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            afile = root / "ws.txt"
            afile.write_text("x")
            with self.assertRaises(ViwoError) as err:
                workspace.precheck(afile, OnExisting.NEW)
            self.assertEqual(err.exception.code, "invalid_request")
            self.assertEqual(workspace._lock_file(afile), (None, False))  # precheck reports it
            workspace._unlock_file(None, False)  # nothing held: nothing to do
            ws = workspace.claim(root / "game")
            (ws / "png").mkdir()
            (root / "game-2").mkdir()  # the next sibling name is taken
            sibling = workspace._new_sibling(ws)
            self.assertEqual(sibling.name, "game-3")
            only_marker = workspace.claim(root / "fresh")
            self.assertFalse(workspace._has_content(only_marker))  # the marker is no content
            lock = root / "own" / workspace.LOCK_FILE
            lock.parent.mkdir(parents=True)
            lock.write_text(json.dumps({"pid": os.getpid(), "time": time.time()}))
            self.assertEqual(workspace._stale(lock), "")  # our own live lock is not stale
            with self.assertRaises(ViwoError) as err:
                workspace._lock_file(root / "own")
            self.assertEqual(err.exception.code, "busy")


class ModOrderTests(unittest.TestCase):
    def test_load_order_respects_every_need_and_names_cycles_and_conflicts(self) -> None:
        import random

        from viwo.core import mods

        rng = random.Random(21)
        for _ in range(60):
            names = [f"m{i}" for i in range(rng.randint(2, 7))]
            manifests = {}
            for i, name in enumerate(names):  # edges only to earlier mods: no cycle yet
                earlier = names[:i]
                manifests[name] = {
                    "name": name,
                    "requires": rng.sample(earlier, rng.randint(0, min(2, len(earlier)))),
                    "after": rng.sample(earlier, rng.randint(0, min(1, len(earlier)))),
                    "files": [{"path": f"f{rng.randrange(4)}", "sha256": rng.choice("ab")}],
                }
            paths = [Path(f"{n}.zip") for n in names]
            rng.shuffle(paths)
            read = lambda p: manifests[p.stem]  # noqa: E731
            with mock.patch.object(mods, "read_manifest", side_effect=read):
                ordered = [p.stem for p in mods.order(paths)]
                for name in names:
                    for dep in manifests[name]["requires"] + manifests[name]["after"]:
                        self.assertLess(ordered.index(dep), ordered.index(name))
                found = mods.conflicts([Path(f"{n}.zip") for n in ordered])
                for line in found:  # a conflict is real and undeclared
                    path, pair = line.split(": ", 1)
                    first, second = pair.split(" and ")
                    self.assertNotIn(
                        first, manifests[second]["after"] + manifests[second]["requires"]
                    )
                if len(names) > 2:  # a back edge makes a cycle: refused with its path
                    manifests[names[0]]["requires"] = [names[-1]]
                    manifests[names[-1]]["requires"] = list(
                        {*manifests[names[-1]]["requires"], names[0]}
                    )
                    with self.assertRaisesRegex(ViwoError, "cycle"):
                        mods.order(paths)
                manifests[names[0]]["requires"] = ["absent"]
                with self.assertRaisesRegex(ViwoError, "requires absent"):
                    mods.order(paths)


if __name__ == "__main__":
    unittest.main()
