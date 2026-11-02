"""L6: the ViWo web server: security model, static/preview containment, routes, extraction."""

from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from tests.helpers import make_game, write_ini
from viwo.api import app as app_module
from viwo.api.server import Handler, make_server
from viwo.core.wiring.boot import boot


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        ini = write_ini(
            cls.root,
            "[plugins]\ngeneric = on\n[server]\nworkspace = data/ws\n"
            "merged = data/merged\nlogs = data/logs\ntemp = data/tmp\n",
        )
        rt = boot(ini)
        rt.temp_root = rt.config.server.temp
        cls.app = app_module.App(rt)
        app_module.reset_app(cls.app)
        cls.httpd = make_server(cls.app, "127.0.0.1", 0)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.game = make_game(cls.root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()
        app_module.reset_app()
        cls._tmp.cleanup()

    def call(self, method: str, path: str, body=None, **headers: str) -> tuple[int, dict | str]:
        base = {
            "Host": f"127.0.0.1:{self.port}",
            "X-VIWO-Token": Handler.token,
            "Content-Type": "application/json",
        }
        base.update(headers)
        base = {k: v for k, v in base.items() if v is not None}
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        conn.request(
            method, path, body=json.dumps(body).encode() if body is not None else None, headers=base
        )
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", "replace")
        conn.close()
        try:
            return resp.status, json.loads(raw)
        except json.JSONDecodeError:
            return resp.status, raw

    def test_security_model(self) -> None:
        self.assertEqual(self.call("POST", "/api/logs/clear", {}, **{"X-VIWO-Token": None})[0], 403)
        self.assertEqual(self.call("GET", "/api/logs", **{"X-VIWO-Token": "wrong"})[0], 403)
        self.assertEqual(
            self.call("POST", "/api/logs/clear", {}, **{"Content-Type": "text/plain"})[0], 415
        )
        self.assertEqual(self.call("POST", "/api/logs/clear", {}, Host="evil.example")[0], 403)
        self.assertEqual(self.call("GET", "/..%2f..%2fpyproject.toml")[0], 404)
        self.assertEqual(self.call("GET", "/preview/..%2f..%2fstartup.ini")[0], 404)
        self.assertEqual(self.call("POST", "/api/logs/clear", {})[0], 200)

    def test_extract_curate_and_jobs(self) -> None:
        status, body = self.call("POST", "/api/extract", {"gamePath": str(self.game)})
        self.assertTrue(body["success"], body)
        status, again = self.call("POST", "/api/extract", {"gamePath": str(self.game)})
        self.assertTrue(again["needsDecision"])
        status, summary = self.call("GET", "/api/status")
        self.assertIn("png", summary["kept"])
        status, moved = self.call("POST", "/api/trash", {"folder": "png"})
        self.assertTrue(moved["success"], moved)
        status, window = self.call("GET", "/api/assets-window?offset=0&limit=10")
        self.assertTrue(all(not a["path"].startswith(".") for a in window["assets"]))
        status, jobs = self.call("GET", "/api/jobs")
        self.assertTrue(any(j["kind"] == "extract" for j in jobs["data"]))
        self.assertEqual(
            self.call("GET", f"/api/jobs/{body['jobId']}")[1]["data"]["state"], "succeeded"
        )

    def test_game_folder_and_unknown_routes(self) -> None:
        status, body = self.call("POST", "/api/workspace", {"path": str(self.root / "missing")})
        self.assertEqual(body["code"], "not_found")
        self.assertEqual(self.call("GET", "/api/nope")[0], 404)
        status, deps = self.call("GET", "/api/dependencies")
        self.assertIn("ffmpeg", {d["id"] for d in deps["dependencies"]})


if __name__ == "__main__":
    unittest.main()
