"""L6: new HTTP routes (doc 4.1/12.5) through the bridge, plus the v1 extract adapter."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_game, write_ini
from viwo import CONTRACT_VERSION
from viwo.api import app as app_module
from viwo.api.routes import handle_get, handle_post
from viwo.core.wiring.boot import boot


class RouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        rt = boot(write_ini(root, "[server]\nworkspace = ws\nlogs = logs\ntemp = tmp\n"))
        rt.temp_root = rt.config.server.temp
        self.app = app_module.App(rt)
        app_module.reset_app(self.app)

    def tearDown(self) -> None:
        app_module.reset_app()
        self._tmp.cleanup()

    def test_distro_plugins_detect(self) -> None:
        body, status = handle_get("/api/distro", {})
        self.assertEqual(
            (status, body["ok"], body["data"]["contract"]), (200, True, CONTRACT_VERSION)
        )
        body, _ = handle_get("/api/plugins", {})
        godot = next(p for p in body["data"] if p["id"] == "godot")
        self.assertEqual(godot["options"][0]["kind"], "secret")
        self.assertEqual(godot["capabilities"][:2], ["detect", "unpack"])  # doc 4.1 fields
        self.assertIn("gdre", godot["dependencies"])
        self.assertEqual((godot["error"], godot["loaded"]), ("", True))
        with tempfile.TemporaryDirectory() as tmp:
            game = make_game(Path(tmp))
            body, status = handle_post("/api/detect", {"gamePath": str(game)})
            self.assertEqual((status, body["data"]["auto"]), (200, ["generic"]))
        body, status = handle_post("/api/detect", {"gamePath": "/nope/missing"})
        self.assertEqual((status, body["error"]["code"]), (400, "invalid_request"))

    def test_generic_job_submit_runs_the_kind_handler(self) -> None:
        """Doc 12.5: POST /api/jobs {kind, params} lands on the same handler as the route."""
        from viwo.api.handlers import POST
        from viwo.api.handlers_jobs import KINDS

        self.assertIn("/api/jobs", POST)
        bad = POST["/api/jobs"](self.app, {"kind": "nope"})
        self.assertEqual((bad["success"], bad["code"]), (False, "invalid_request"))
        self.assertEqual(
            set(KINDS),
            {
                "extract",
                "survey",
                "repack",
                "preflight",
                "install",
                "capture",
                "cleanup",
                "analyze",
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            make_game(Path(tmp))
            body = POST["/api/jobs"](self.app, {"kind": "survey", "params": {"folder": tmp}})
        self.assertTrue(body.get("success"), body)
        self.assertEqual(self.app.jobs.get(body["jobId"]).kind, "survey")

    def test_jobs_events_and_cancel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = make_game(root)
            response = self.app.extract({"gamePath": str(game)})
            self.assertTrue(response["success"], response)
        body, _ = handle_get("/api/jobs", {})
        job_id = body["data"][-1]["id"]
        body, status = handle_get(f"/api/jobs/{job_id}", {})
        self.assertEqual((status, body["data"]["state"]), (200, "succeeded"))
        self.assertTrue(body["data"]["result"]["success"])
        body, _ = handle_get(f"/api/jobs/{job_id}/events", {"from": "1"})
        self.assertEqual(body["data"]["from"], 1)
        self.assertTrue(body["data"]["events"][0]["line"].startswith("["))
        body, status = handle_post(f"/api/jobs/{job_id}/cancel", {})
        self.assertEqual(status, 200)
        body, status = handle_get("/api/jobs/no-such-job", {})
        self.assertEqual((status, body["error"]["code"]), (404, "not_found"))
        self.assertIsNone(handle_get("/api/unknown", {}))


if __name__ == "__main__":
    unittest.main()
