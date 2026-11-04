"""L6: the web UI in a real headless browser (Edge/Chrome over the DevTools protocol, driven by
tests/ui/smoke.mjs with Node). Skipped when no Chromium binary or no Node is found."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from tests.helpers import make_game, write_ini
from viwo.api import app as app_module
from viwo.api.server import make_server
from viwo.core.wiring.boot import boot

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)


def browser() -> str:
    for name in ("google-chrome", "chromium", "chromium-browser", "msedge"):
        hit = shutil.which(name)
        if hit:
            return hit
    return next((c for c in CANDIDATES if Path(c).is_file()), "")


BROWSER, NODE = browser(), shutil.which("node")


@unittest.skipUnless(BROWSER and NODE, "needs a Chromium browser and Node")
@unittest.skipIf(os.environ.get("VIWO_UI") == "0", "VIWO_UI=0 disables the browser smoke")
class UiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(
            ignore_cleanup_errors=True
        )  # Edge keeps its profile open
        cls.root = Path(cls._tmp.name)
        ini = write_ini(
            cls.root,
            "[startup]\nauto_install = off\n[plugins]\ngeneric = on\n[server]\n"
            "workspace = data/ws\nmerged = data/merged\nlogs = data/logs\ntemp = data/tmp\n",
        )
        rt = boot(ini)
        rt.temp_root = rt.config.server.temp
        cls.app = app_module.App(rt, ini)
        app_module.reset_app(cls.app)
        cls.httpd = make_server(cls.app, "127.0.0.1", 0)
        cls.url = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.game = make_game(cls.root)
        cls.out = Path(os.environ.get("VIWO_UI_OUT") or cls.root / "shots")
        with socket.socket() as probe:  # a free DevTools port, so runs never share a browser
            probe.bind(("127.0.0.1", 0))
            cls.cdp = probe.getsockname()[1]
        cls.edge = subprocess.Popen(
            [
                BROWSER,
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                f"--remote-debugging-port={cls.cdp}",
                f"--user-data-dir={cls.root / 'profile'}",
                "--window-size=1440,900",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        script = ROOT / "tests" / "ui" / "smoke.mjs"
        for _ in range(3):  # the debugging port needs a moment
            run = subprocess.run(
                [NODE, str(script), cls.url, str(cls.cdp), str(cls.game), str(cls.out)],
                capture_output=True,
                text=True,
                timeout=400,
            )
            if run.returncode == 0:
                break
        cls.proc = run
        cls.report = json.loads(run.stdout) if run.returncode == 0 and run.stdout else None

    @classmethod
    def tearDownClass(cls) -> None:
        if os.name == "nt":  # the browser is a process tree
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(cls.edge.pid)], capture_output=True)
        cls.edge.kill()
        cls.edge.wait(timeout=20)
        cls.httpd.shutdown()
        cls.httpd.server_close()
        app_module.reset_app()
        cls._tmp.cleanup()

    def setUp(self) -> None:
        if self.report is None:
            self.fail(f"smoke script failed:\n{self.run.stdout[-1500:]}\n{self.run.stderr[-3000:]}")

    def test_landing_then_every_view_without_console_errors(self) -> None:
        r = self.report
        self.assertTrue(r["checks"]["landingSeen"] and r["checks"]["landingDone"], r["checks"])
        self.assertEqual(r["console"], [], json.dumps(r["console"], indent=1)[:3000])
        self.assertGreaterEqual(len(r["checks"]["views"]), 17)
        for view, info in r["views"].items():
            self.assertTrue(info.get("visible"), f"{view}: {info}")
            self.assertFalse(info.get("overflow"), f"{view} overflows horizontally")
            self.assertEqual(info.get("nullText"), [], f"{view} renders a literal null/undefined")

    def test_three_arms_and_the_global_strip(self) -> None:
        a = self.report["checks"]["arms"]
        self.assertEqual(a["strip"], ["system", "jobs", "settings"])
        self.assertEqual(a["static"][:3], ["static", "survey", "extract"])
        self.assertEqual(a["dynamic"], ["dynamic", "capture", "runtime"])
        self.assertEqual(a["afterGlobal"], a["dynamic"])  # a strip view keeps the arm
        self.assertEqual(
            (a["patching"], a["patchingHash"]), (["patching", "repack", "patches"], "#patching")
        )

    def test_toast_sits_at_the_bottom_right(self) -> None:
        t = self.report["checks"]["toast"]
        self.assertIsNotNone(t)
        self.assertLessEqual(t["bottomGap"], 40, t)
        self.assertLessEqual(t["rightGap"], 40, t)

    def test_system_gap_and_settings_table(self) -> None:
        c = self.report["checks"]
        self.assertIsNotNone(c["systemGap"])
        self.assertGreaterEqual(c["systemGap"], 12, c["systemGap"])
        self.assertIsNotNone(c["slotsTable"])
        self.assertGreaterEqual(
            c["slotsTable"]["table"], 0.9 * c["slotsTable"]["column"], c["slotsTable"]
        )
        self.assertEqual(c["settingsNull"], [])

    def test_theme_switch_changes_html_and_stylesheet(self) -> None:
        t = self.report["checks"]["theme"]
        self.assertEqual(t["before"]["theme"], "wormhole")
        self.assertEqual(t["after"]["theme"], "plain")
        self.assertIn("plain.css", t["after"]["href"])

    def test_detect_percent_rail_skip_and_sort_counts(self) -> None:
        c = self.report["checks"]
        self.assertTrue(c["detectPct"], "no detection rows")
        for text in c["detectPct"]:
            self.assertRegex(text, r"^\d{1,3}%$")
        self.assertTrue(c["extractDone"], "extraction did not finish")
        skipped = [s for s in c["rail"] if s["s"] == "skip"]
        self.assertTrue(skipped, c["rail"])
        for s in skipped:
            self.assertEqual(s["note"], "skipped")
            self.assertTrue(s["noteVisible"], s)
        self.assertTrue(c["sortFilters"])
        self.assertTrue(
            any("on this page" in f for f in c["sortFilters"]) or len(c["sortFilters"]) > 0
        )

    def test_cleanup_runs_as_a_visible_job(self) -> None:
        c = self.report["checks"]
        self.assertTrue(c["cleanupJobShown"], c)
        self.assertTrue(c["cleanupDone"], c)
        self.assertIn(c["cleanupState"], ("done", "fail"))


if __name__ == "__main__":
    unittest.main()
