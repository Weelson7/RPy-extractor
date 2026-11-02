"""L1/L3: diagnostics bundle (secrets stripped), update checks (no network), notices file."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.helpers import runtime
from viwo import __version__
from viwo.contracts import ViwoError
from viwo.contracts import workspace as ws
from viwo.core import diag

ROOT = Path(__file__).resolve().parent.parent


def fake_fetch(url: str):
    if "RPy-extractor" in url:
        return {"tag_name": "v9.0.0", "html_url": "https://example.test/app"}
    return None  # the indexes repository has no release yet


class DiagTests(unittest.TestCase):
    def test_bundle_collects_and_scrubs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = runtime(root, "[server]\nlogs = logs\nworkspace = ws\n")
            logs = rt.config.server.logs
            logs.mkdir(parents=True)
            (logs / "viwo-today.log").write_text("[RUN] aes_key = 0xDEADBEEF ok\ntoken: abc\n")
            runs = rt.config.server.workspace / ws.RUNS_DIR
            runs.mkdir(parents=True)
            (runs / "r1.json").write_text(json.dumps({"request": {"password": "hunter2"}}))
            out = diag.bundle(rt, rt.config.server.workspace, root / "d.zip")
            with zipfile.ZipFile(out) as z:
                names = set(z.namelist())
                self.assertTrue({"about.json", "info.json", "slots.json", "tools.json"} <= names)
                log = z.read("logs/viwo-today.log").decode()
                self.assertNotIn("DEADBEEF", log)
                self.assertNotIn("abc", log)
                self.assertIn("aes_key = <secret>", log)
                record = json.loads(z.read("runs/r1.json"))
                self.assertEqual(record, {"request": {"password": "<secret>"}})
                self.assertEqual(json.loads(z.read("about.json"))["viwo"], __version__)

    def test_update_check_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            report = diag.check_updates(home, fake_fetch)
            self.assertEqual(
                report["app"],
                {"current": __version__, "latest": "9.0.0", "url": "https://example.test/app"},
            )
            self.assertEqual(report["indexes"]["current"], "none")
            self.assertEqual(report["indexes"]["latest"], "")
            (home / "indexes").mkdir()
            (home / "indexes" / "VERSION").write_text("v1.3\n")
            self.assertEqual(diag.check_updates(home, fake_fetch)["indexes"]["current"], "v1.3")

    def test_github_refuses_http_and_reports_offline(self) -> None:
        with self.assertRaises(ViwoError) as err:
            diag.github_json("http://example.test/x")
        self.assertEqual(err.exception.code, "refused")
        with self.assertRaises(ViwoError) as err:
            diag.github_json("https://127.0.0.1:9/nothing", timeout=0.5)
        self.assertEqual(err.exception.code, "offline")
        self.assertEqual(err.exception.code, "offline")

    def test_notices_file_is_up_to_date(self) -> None:
        spec = importlib.util.spec_from_file_location("notices", ROOT / "tools" / "notices.py")
        notices = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(notices)
        current = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertEqual(current, notices.render(), "run python tools/notices.py")
        self.assertIn("| quickbms |", current)


if __name__ == "__main__":
    unittest.main()
