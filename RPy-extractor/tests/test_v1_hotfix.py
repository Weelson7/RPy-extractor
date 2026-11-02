"""Regression tests for the v1 data-safety hotfix.

Run from RPy-extractor/:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import http.client
import io
import json
import sys
import tarfile
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from api.extraction_handlers import claim_workspace  # noqa: E402
from extraction_core.archive import try_python_archive_extract  # noqa: E402
from extraction_core.pipeline import extract_assets  # noqa: E402
from models import WORKSPACE_MARKER, AppConfig  # noqa: E402


class GameFolderIsReadOnly(unittest.TestCase):
    def test_extraction_copies_instead_of_moving(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game_root"
            (game / "game" / "images").mkdir(parents=True)
            (game / "game" / "images" / "bg.png").write_bytes(b"png-bytes")
            (game / "game" / "script.rpy").write_text("label start:\n", encoding="utf-8")
            (root / "tmp").mkdir()
            before = sorted(p.relative_to(game).as_posix() for p in game.rglob("*") if p.is_file())

            result = extract_assets(game, root / "out", None, root / "tmp")

            after = sorted(p.relative_to(game).as_posix() for p in game.rglob("*") if p.is_file())
            self.assertEqual(before, after, "game folder must not lose files")
            self.assertTrue((root / "out" / "png" / "bg.png").exists())
            self.assertEqual(result["copiedFiles"], 2)


class WorkspaceOwnership(unittest.TestCase):
    def test_unmarked_folder_with_content_is_not_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_dir = root / "my_documents"
            user_dir.mkdir()
            (user_dir / "important.txt").write_text("keep me", encoding="utf-8")
            game = root / "game_root"
            game.mkdir()
            (root / "tmp").mkdir()

            self.assertTrue(claim_workspace(user_dir, root / "default"))
            with self.assertRaises(ValueError):
                extract_assets(game, user_dir, None, root / "tmp")
            self.assertTrue((user_dir / "important.txt").exists())

    def test_empty_and_default_folders_are_claimed_and_reusable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game_root"
            game.mkdir()
            (game / "a.txt").write_text("x", encoding="utf-8")
            (root / "tmp").mkdir()
            default = root / "assets"
            default.mkdir()
            (default / "old.png").write_bytes(b"old")  # pre-hotfix default workspace

            self.assertEqual(claim_workspace(default, default), "")
            extract_assets(game, default, None, root / "tmp")
            self.assertTrue((default / WORKSPACE_MARKER).exists())
            self.assertFalse((default / "old.png").exists())
            # Second run into the now-marked folder works.
            extract_assets(game, default, None, root / "tmp")
            self.assertTrue((default / "txt" / "a.txt").exists())


class SafeTarExtraction(unittest.TestCase):
    def test_traversal_and_links_are_not_extracted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "evil.tar"
            with tarfile.open(archive, "w") as tf:
                for name, data in (("../escaped.txt", b"bad"), ("ok/inside.txt", b"good")):
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    tf.addfile(info, io.BytesIO(data))
                link = tarfile.TarInfo("ok/link")
                link.type = tarfile.SYMTYPE
                link.linkname = "/etc/passwd"
                tf.addfile(link)
            dest = root / "dest"
            dest.mkdir()

            ok, err = try_python_archive_extract(archive, dest)

            self.assertTrue(ok, err)
            self.assertFalse((root / "escaped.txt").exists())
            self.assertTrue((dest / "ok" / "inside.txt").exists())
            self.assertFalse((dest / "ok" / "link").exists())


class ApiSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import extract

        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        extract.Handler.app_config = AppConfig(
            host="127.0.0.1", port=0, temp_path=tmp, output_dir_name="assets",
            merger_dir=tmp / "merged", web_dir_name=str(APP_DIR / "web"), log_dir=tmp / "logs",
        )
        extract.Handler.api_token = "test-token"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), extract.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls._tmp.cleanup()

    def request(self, method: str, path: str, headers: dict[str, str], body: bytes = b"") -> int:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(method, path, body=body or None, headers=headers)
        status = conn.getresponse().status
        conn.close()
        return status

    def headers(self, **extra: str) -> dict[str, str]:
        base = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json", "X-RPYX-Token": "test-token"}
        base.update(extra)
        return base

    def test_post_requires_token(self) -> None:
        h = self.headers()
        del h["X-RPYX-Token"]
        self.assertEqual(self.request("POST", "/api/logs/clear", h, b"{}"), 403)

    def test_cross_site_simple_post_is_rejected(self) -> None:
        h = self.headers(**{"Content-Type": "text/plain"})
        self.assertEqual(self.request("POST", "/api/logs/clear", h, b"{}"), 415)

    def test_foreign_host_is_rejected(self) -> None:
        h = self.headers(Host="attacker.example:80")
        self.assertEqual(self.request("POST", "/api/logs/clear", h, b"{}"), 403)

    def test_valid_request_succeeds(self) -> None:
        self.assertEqual(self.request("POST", "/api/logs/clear", self.headers(), b"{}"), 200)

    def test_get_api_requires_token(self) -> None:
        h = self.headers()
        del h["X-RPYX-Token"]
        self.assertEqual(self.request("GET", "/api/logs", h), 403)

    def test_static_traversal_is_blocked(self) -> None:
        self.assertEqual(self.request("GET", "/..%2fextract.py", {"Host": f"127.0.0.1:{self.port}"}), 404)

    def test_index_carries_token(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", "/", headers={"Host": f"127.0.0.1:{self.port}"})
        html = conn.getresponse().read().decode("utf-8")
        conn.close()
        self.assertIn('name="rpyx-token" content="test-token"', html)


if __name__ == "__main__":
    unittest.main()
