"""L6: new HTTP routes (doc 4.1/12.5) through the bridge, plus the v1 extract adapter."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_game
from viwo.api import legacy
from viwo.api.routes import handle_get, handle_post


class RouteTests(unittest.TestCase):
    def test_distro_plugins_detect(self) -> None:
        body, status = handle_get("/api/distro", {})
        self.assertEqual((status, body["ok"], body["data"]["contract"]), (200, True, "1.0"))
        body, _ = handle_get("/api/plugins", {})
        godot = next(p for p in body["data"] if p["id"] == "godot")
        self.assertEqual(godot["options"][0]["kind"], "secret")
        with tempfile.TemporaryDirectory() as tmp:
            game = make_game(Path(tmp))
            body, status = handle_post("/api/detect", {"gamePath": str(game)})
            self.assertEqual((status, body["data"]["auto"]), (200, ["generic"]))
        body, status = handle_post("/api/detect", {"gamePath": "/nope/missing"})
        self.assertEqual((status, body["error"]["code"]), (400, "invalid_request"))

    def test_jobs_events_and_cancel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = make_game(root)
            response = legacy.extract_for_v1(
                {"gamePath": str(game)}, root / "ws", root / "ws", root / "tmp"
            )
            self.assertTrue(response["success"], response)
        body, _ = handle_get("/api/jobs", {})
        job_id = body["data"][-1]["id"]
        body, status = handle_get(f"/api/jobs/{job_id}", {})
        self.assertEqual((status, body["data"]["state"]), (200, "succeeded"))
        self.assertTrue(body["data"]["result"]["success"])
        body, _ = handle_get(f"/api/jobs/{job_id}/events", {"from": ["1"]})
        self.assertEqual(body["data"]["from"], 1)
        self.assertTrue(body["data"]["events"][0]["line"].startswith("["))
        body, status = handle_post(f"/api/jobs/{job_id}/cancel", {})
        self.assertEqual(status, 200)
        body, status = handle_get("/api/jobs/no-such-job", {})
        self.assertEqual((status, body["error"]["code"]), (404, "not_found"))
        self.assertIsNone(handle_get("/api/unknown", {}))


if __name__ == "__main__":
    unittest.main()
