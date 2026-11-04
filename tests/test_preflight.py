"""L3: the startup preflight (doc 9), the first-run path behind the minimal-prompts rule: over
random dependency reports it installs exactly the missing tools that can install themselves
(never the on-demand ones, nothing when auto_install is off), names every failure as a warning,
counts ready tools honestly and says each check; versions come without ever blocking."""

from __future__ import annotations

import importlib.metadata
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.helpers import runtime
from viwo.contracts import ViwoError
from viwo.core import preflight, thirdparty


def _report(rng: random.Random) -> list[dict]:
    items = []
    for i in range(rng.randint(1, 10)):
        items.append(
            {
                "id": f"t{i}",
                "label": f"Tool {i}",
                "kind": rng.choice(["executable", "python"]),
                "available": rng.random() < 0.4,
                "installable": rng.random() < 0.7,
                "onDemand": rng.random() < 0.2,
                "location": "",
            }
        )
    return items


class PreflightTests(unittest.TestCase):
    def test_first_run_installs_exactly_what_can_install_itself(self) -> None:
        rng = random.Random(10)
        with tempfile.TemporaryDirectory() as tmp:
            rt = runtime(Path(tmp))
            for _ in range(25):
                items = _report(rng)
                broken = {i["id"] for i in items if rng.random() < 0.3}
                auto = rng.random() < 0.8
                rt.config.auto_install = auto

                def install(dep, home, runner, say=None, cancel=None, broken=broken):
                    if dep in broken:
                        raise ViwoError("failed", f"{dep}: checksum mismatch")
                    return "ok"

                events = []
                with (
                    mock.patch.object(rt, "dependency_report", lambda: [dict(i) for i in items]),
                    mock.patch.object(preflight, "_version", lambda rt, item: ""),
                    mock.patch.object(thirdparty, "installable", lambda d, k: True),
                    mock.patch.object(thirdparty, "install_tool", install),
                    mock.patch.object(
                        thirdparty, "install_python", lambda d, h, r: install(d, h, r)
                    ),
                ):
                    report = preflight.preflight(rt, events.append)
                todo = [
                    i["id"]
                    for i in items
                    if auto and not i["available"] and i["installable"] and not i["onDemand"]
                ]
                self.assertEqual(report["installed"], [t for t in todo if t not in broken])
                self.assertEqual(len(report["failed"]), len([t for t in todo if t in broken]))
                ready = sum(i["available"] for i in items) + len(report["installed"])
                self.assertEqual((report["ready"], report["total"]), (ready, len(items)))
                said = [e.message for e in events]
                warned = [e.message for e in events if e.level == "warn"]
                self.assertEqual(len(warned), len(report["failed"]))  # every failure said
                self.assertEqual(sum(m.startswith("Checking ") for m in said), len(items))
                self.assertIn(f"Ready: {ready}/{len(items)} tools available", said)

    def test_install_refuses_what_has_no_automatic_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = runtime(Path(tmp))
            item = {"id": "x", "label": "X", "kind": "executable"}
            with mock.patch.object(rt, "dependency_report", lambda: [item]):
                for dep, installable in (("nope", True), ("x", False)):
                    with mock.patch.object(
                        thirdparty, "installable", lambda d, k, v=installable: v
                    ):
                        with self.assertRaises(ViwoError) as err:
                            preflight.install(rt, dep)
                    self.assertEqual(err.exception.code, "unavailable")
                said = []
                with (
                    mock.patch.object(thirdparty, "installable", lambda d, k: True),
                    mock.patch.object(thirdparty, "install_tool", return_value="x.exe"),
                ):
                    done = preflight.install(rt, "x", said.append)
                    self.assertEqual(preflight.install(rt, "x"), done)  # without a sink too
                self.assertEqual(done, {"installed": "x", "where": "x.exe"})
                self.assertEqual(len(said), 2)  # installing, installed

    def test_versions_never_block_and_never_lie(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = runtime(Path(tmp))
            gone = {"id": "a", "available": False, "kind": "executable"}
            self.assertEqual(preflight._version(rt, gone), "")
            py = {"id": "nosuchpkg", "available": True, "kind": "python"}
            with mock.patch.object(
                importlib.metadata, "version", side_effect=importlib.metadata.PackageNotFoundError
            ):
                self.assertEqual(preflight._version(rt, py), "")
            tool = {"id": "rdpython", "available": True, "kind": "executable", "location": "x"}
            with mock.patch.object(thirdparty, "installed_version", return_value=""):
                self.assertEqual(preflight._version(rt, tool), "")  # a GUI host is never run
                tool = {**tool, "id": "sometool"}
                with mock.patch.object(rt.os.process, "run", side_effect=OSError("a folder")):
                    self.assertEqual(preflight._version(rt, tool), "")
                answer = SimpleNamespace(stdout="", stderr="tool 1.2\nmore")
                with mock.patch.object(rt.os.process, "run", return_value=answer):
                    self.assertEqual(preflight._version(rt, tool), "tool 1.2")
            with mock.patch.object(thirdparty, "installed_version", return_value="9.9"):
                self.assertEqual(preflight._version(rt, tool), "9.9")  # the pin, not a run


if __name__ == "__main__":
    unittest.main()
