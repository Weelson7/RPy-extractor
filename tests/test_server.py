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
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tests.helpers import make_game, write_ini
from viwo.api import app as app_module
from viwo.api.server import Handler, byte_range, make_server
from viwo.contracts.errors import ViwoError
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

    def raw(self, method: str, path: str, body: bytes = b"", **headers: str):
        base = {"Host": f"127.0.0.1:{self.port}", "X-VIWO-Token": Handler.token, **headers}
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        conn.request(method, path, body=body or None, headers=base)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp, data

    def test_every_ui_file_is_served_as_is_and_nothing_else(self) -> None:
        """index.html carries this server's token and is never cached; every other UI file comes
        back byte for byte; nothing outside viwo/web is ever served."""
        from viwo.api.server import WEB_ROOT

        resp, html = self.raw("GET", "/")
        self.assertEqual(resp.status, 200)
        self.assertIn(f'content="{Handler.token}"'.encode(), html)
        self.assertEqual(resp.getheader("Cache-Control"), "no-store")
        for file in sorted(p for p in WEB_ROOT.rglob("*") if p.is_file()):
            rel = file.relative_to(WEB_ROOT).as_posix()
            if rel == "index.html" or "__pycache__" in rel:
                continue
            resp, body = self.raw("GET", "/" + rel, **{"X-VIWO-Token": ""})  # no token needed
            self.assertEqual((resp.status, body), (200, file.read_bytes()), rel)
            self.assertEqual(resp.getheader("Cache-Control"), "no-cache")
        outsides = ("/../pyproject.toml", "/%2e%2e/viwo/cli.py", "/nope.js", "/js/")
        for outside in (*outsides, "/plugins/nope/ui.js"):
            self.assertEqual(self.raw("GET", outside)[0].status, 404, outside)
        self.assertEqual(self.raw("GET", "/", Host="evil.example")[0].status, 403)
        self.assertEqual(self.raw("HEAD", "/preview/x", Host="evil.example")[0].status, 404)

    def test_malformed_bodies_and_a_crashing_route_never_stop_the_server(self) -> None:
        from viwo.api import handlers

        post = {"Content-Type": "application/json"}
        self.assertEqual(self.raw("POST", "/api/logs/clear", b"{not json", **post)[0].status, 400)
        bad_len = {**post, "Content-Length": "abc"}
        self.assertEqual(self.raw("POST", "/api/logs/clear", b"{}", **bad_len)[0].status, 413)
        self.assertEqual(self.call("POST", "/api/logs/clear", [1, 2])[0], 200)  # not an object
        # a RuntimeError is a 500 "internal"; a ViwoError says its own code and status, not a 500
        cases = [(RuntimeError("x"), 500, "internal"), (ViwoError("refused", ""), 403, "refused")]
        for err, want_status, want_code in cases:
            with mock.patch.dict(handlers.GET, {"/api/logs": mock.Mock(side_effect=err)}):
                status, body = self.call("GET", "/api/logs")
            self.assertEqual((status, body["code"]), (want_status, want_code))
        self.assertEqual(self.call("GET", "/api/logs")[0], 200)  # still serving


class ServeTests(unittest.TestCase):
    """viwo serve: every way it ends says why, with its own exit code."""

    def _app(self, strict: bool = False):
        with tempfile.TemporaryDirectory() as tmp:
            rt = boot(write_ini(Path(tmp)))
        rt.config = mock.Mock(wraps=rt.config, strict_preflight=strict)
        app = mock.Mock(rt=rt, workspace=Path("ws"))
        app.server.host, app.server.port = "127.0.0.1", 8123
        app.rt.problems = ["a problem"]
        return app

    def test_strict_preflight_port_in_use_and_a_clean_stop(self) -> None:
        from viwo.api import server

        out = io.StringIO()
        app = self._app(strict=True)
        with (
            mock.patch.object(server, "get_app", return_value=app),
            mock.patch.object(server, "strict_check", return_value=["unarchive.x: none"]),
            redirect_stdout(out),
        ):
            self.assertEqual(server.serve(browser=False), 4)
        self.assertIn("unarchive.x: none", out.getvalue())
        app = self._app()
        with (
            mock.patch.object(server, "get_app", return_value=app),
            mock.patch.object(server, "make_server", side_effect=OSError("in use")),
            redirect_stdout(out),
        ):
            self.assertEqual(server.serve(port=8123, browser=False), 2)
        self.assertIn("127.0.0.1:8123", out.getvalue())
        httpd = mock.Mock(server_address=("127.0.0.1", 8123))
        httpd.serve_forever.side_effect = KeyboardInterrupt
        with (
            mock.patch.object(server, "get_app", return_value=app),
            mock.patch.object(server, "make_server", return_value=httpd),
            mock.patch.object(server.threading, "Timer") as timer,
            redirect_stdout(out),
        ):
            self.assertEqual(server.serve(), 0)
            self.assertEqual(server.serve(browser=False), 0)
        self.assertEqual(httpd.shutdown.call_count, 2)
        timer.assert_called_once()  # the browser opens on the served URL, only when asked
        self.assertIn("http://127.0.0.1:8123/", out.getvalue())
        logged = " ".join(str(c) for c in app.log.call_args_list)
        self.assertIn("a problem", logged)  # boot notes reach the log

    def test_strict_check_rebinds_after_installing(self) -> None:
        from viwo.api import server
        from viwo.core import preflight

        app = self._app()
        for installed in ([], ["vgmstream"]):
            app.reload.reset_mock()
            with (
                mock.patch.object(preflight, "preflight", return_value={"installed": installed}),
                mock.patch.object(preflight, "strict_problems", return_value=[]),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(server.strict_check(app), [])
            self.assertEqual(app.reload.called, bool(installed))

    def test_a_vanished_client_is_quiet_any_other_error_is_reported(self) -> None:
        from viwo.api import server

        quiet = server.QuietServer.__new__(server.QuietServer)
        for exc, said in ((ConnectionResetError(), False), (ValueError("x"), True)):
            with mock.patch.object(server.ThreadingHTTPServer, "handle_error") as base:
                try:
                    raise exc
                except Exception:  # noqa: BLE001
                    quiet.handle_error(None, ("127.0.0.1", 1))
            self.assertEqual(base.called, said)
        src = io.BytesIO(b"abc")
        dst = io.BytesIO()
        server._copy(src, dst, 10)  # a short file ends the copy, never loops
        self.assertEqual(dst.getvalue(), b"abc")


if __name__ == "__main__":
    unittest.main()
