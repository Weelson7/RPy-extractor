"""L6: the ViWo web server: security model, static/preview containment, routes, extraction."""

from __future__ import annotations

import http.client
import io
import json
import socket
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from tests.helpers import make_game, write_ini
from viwo.api import app as app_module
from viwo.api.server import Handler, byte_range, make_server
from viwo.core.curation.sorting import encode
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

    def scratch_workspace(self) -> Path:
        """A throwaway workspace for one test; the shared one is restored afterwards."""
        keep = self.app.workspace
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(lambda: self.app.set_workspace(keep))
        ws = Path(tmp.name) / "ws"
        ws.mkdir()
        (ws / ".viwo-workspace").write_text("")
        self.app.set_workspace(ws)
        return ws

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

    def test_preview_abort_is_quiet_and_server_keeps_serving(self) -> None:
        """A player that closes mid-stream (Windows: ConnectionAbortedError) is not an error."""
        ws = self.scratch_workspace()
        big = ws / "bin" / "large.bin"
        big.parent.mkdir(parents=True, exist_ok=True)
        big.write_bytes(b"\0" * (8 << 20))
        err = io.StringIO()
        with redirect_stderr(err):
            for _ in range(3):
                sock = socket.create_connection(("127.0.0.1", self.port), timeout=10)
                sock.sendall(
                    f"GET /preview/{encode(ws, big)} HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{self.port}\r\n\r\n".encode()
                )
                sock.recv(1024)  # a few bytes, then gone
                sock.setsockopt(
                    socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00"
                )
                sock.close()
            time.sleep(0.5)
            status, body = self.call("GET", "/api/logs")
        self.assertEqual(status, 200)
        self.assertNotIn("Traceback", err.getvalue())
        self.assertNotIn("Exception occurred", err.getvalue())

    def test_assets_window_counts_the_whole_workspace(self) -> None:
        ws = self.scratch_workspace()
        for name in ("one.png", "two.png", "song.ogg"):
            (ws / name[-3:] / name).parent.mkdir(parents=True, exist_ok=True)
            (ws / name[-3:] / name).write_bytes(b"x")
        status, body = self.call("GET", "/api/assets-window?offset=0&limit=1")
        self.assertEqual((status, body["indexedCount"]), (200, 1))
        self.assertGreaterEqual(body["typeCounts"]["image"], 2)
        self.assertGreaterEqual(body["typeCounts"]["audio"], 1)
        self.assertEqual(body["total"], sum(body["typeCounts"].values()))
        self.assertEqual(body["total"], body["totalCount"])

    def test_only_this_machine_unless_bound_to_a_lan_address(self) -> None:
        from types import SimpleNamespace

        from viwo.api.server import Handler

        def ok(bound: str, peer: str, host: str = "127.0.0.1:8000") -> bool:
            fake = SimpleNamespace(headers={"Host": host}, client_address=(peer, 50000))
            fake.app = SimpleNamespace(server=SimpleNamespace(host=bound))
            return Handler._host_ok(fake)

        local = ("127.0.0.1", "::1", "::ffff:127.0.0.1", "127.8.9.1")
        lan = ("10.0.0.5", "192.168.1.20", "fe80::1", "not-an-ip")
        for bound in ("127.0.0.1", "0.0.0.0", "::", "localhost"):
            self.assertTrue(all(ok(bound, p) for p in local), bound)
            self.assertFalse(any(ok(bound, p) for p in lan), bound)  # a faked Host header
        self.assertTrue(all(ok("192.168.1.10", p, "192.168.1.10:8000") for p in lan))
        self.assertFalse(ok("192.168.1.10", "127.0.0.1", "evil.example"))  # rebinding

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
        huge = {"Content-Length": str(64 << 20)}  # bodies are capped before they are read
        self.assertEqual(self.call("POST", "/api/logs/clear", {}, **huge)[0], 413)

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
        job = self.call("GET", f"/api/jobs/{body['jobId']}")[1]["data"]
        self.assertEqual(Path(job["result"]["workspace"]), Path(self.app.workspace))

    def test_preview_streams_byte_ranges(self) -> None:
        target = Path(self.app.workspace) / "bin" / "r.bin"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bytes(range(256)) * 4)
        self.assertEqual(self.call("GET", "/preview/bin/r.bin")[0], 200)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        host = {"Host": f"127.0.0.1:{self.port}"}
        for rng, status, body in (
            ("bytes=10-13", 206, bytes([10, 11, 12, 13])),
            ("bytes=-2", 206, bytes([254, 255])),
            ("bytes=1020-", 206, bytes([252, 253, 254, 255])),
            ("bytes=5000-", 416, b""),
        ):
            conn.request("GET", "/preview/bin/r.bin", headers={**host, "Range": rng})
            resp = conn.getresponse()
            self.assertEqual((resp.status, resp.read()), (status, body), rng)
        conn.request("HEAD", "/preview/bin/r.bin", headers=host)
        resp = conn.getresponse()
        self.assertEqual((resp.status, resp.getheader("Content-Length")), (200, "1024"))
        resp.read()
        conn.close()
        self.assertEqual(byte_range("bytes=0-0, 5-6", 10), None)  # multi-range: whole file

    def test_game_folder_and_unknown_routes(self) -> None:
        status, body = self.call("POST", "/api/workspace", {"path": str(self.root / "missing")})
        self.assertEqual(body["code"], "not_found")
        self.assertEqual(self.call("GET", "/api/nope")[0], 404)
        status, deps = self.call("GET", "/api/dependencies")
        self.assertIn("ffmpeg", {d["id"] for d in deps["dependencies"]})


if __name__ == "__main__":
    unittest.main()
