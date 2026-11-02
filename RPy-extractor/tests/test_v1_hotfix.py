"""Regression tests for the v1 data-safety hotfix.

Run from RPy-extractor/:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import http.client
import io
import sys
import tarfile
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

sys.path.insert(0, str(APP_DIR.parent))

from api.common import set_session_asset_path  # noqa: E402
from api.extraction_handlers import extract_repo  # noqa: E402
from models import SESSIONS, AppConfig  # noqa: E402


def _config(root: Path) -> AppConfig:
    return AppConfig(host="127.0.0.1", port=0, temp_path=root / "tmp", output_dir_name="assets",
                     merger_dir=root / "merged", web_dir_name=str(APP_DIR / "web"),
                     log_dir=root / "logs")


def _game(root: Path) -> Path:
    game = root / "game_root"
    (game / "game" / "images").mkdir(parents=True)
    (game / "game" / "images" / "bg.png").write_bytes(b"png-bytes")
    (game / "game" / "script.rpy").write_text("label start:\n", encoding="utf-8")
    with tarfile.open(game / "extra.tar", "w") as tf:
        for name, data in (("../escaped.txt", b"bad"), ("ok/inside.txt", b"good")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return game


class ExtractionSafety(unittest.TestCase):
    """H1, H2 and F17, checked through the v1 route (now served by the ViWo core)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "tmp").mkdir()
        self.cfg = _config(self.root)
        self.game = _game(self.root)
        SESSIONS.clear()

    def tearDown(self) -> None:
        SESSIONS.clear()
        self._tmp.cleanup()

    def files(self, folder: Path) -> list[str]:
        return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())

    def test_game_folder_untouched_and_traversal_blocked(self) -> None:
        before = self.files(self.game)
        response = extract_repo(str(self.game), self.cfg, None)
        self.assertTrue(response["success"], response)
        self.assertEqual(self.files(self.game), before)
        self.assertFalse((self.root / "escaped.txt").exists())
        assets = Path(response["assetPath"])
        self.assertTrue((assets / "png" / "bg.png").exists())
        self.assertTrue((assets / "txt" / "inside.txt").exists())

    def test_user_folder_is_never_cleared(self) -> None:
        user_dir = self.root / "my_documents"
        user_dir.mkdir()
        (user_dir / "important.txt").write_text("keep me", encoding="utf-8")
        set_session_asset_path(user_dir)
        response = extract_repo(str(self.game), self.cfg, None, None, None, "replace")
        self.assertFalse(response["success"])
        self.assertEqual(response["code"], "refused")
        self.assertTrue((user_dir / "important.txt").exists())

    def test_rerun_asks_then_replaces(self) -> None:
        self.assertTrue(extract_repo(str(self.game), self.cfg, None)["success"])
        again = extract_repo(str(self.game), self.cfg, None)
        self.assertTrue(again["needsDecision"])
        replaced = extract_repo(str(self.game), self.cfg, None, None, None, "replace")
        self.assertTrue(replaced["success"], replaced)


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
        conn.request("GET", "/legacy/", headers={"Host": f"127.0.0.1:{self.port}"})
        html = conn.getresponse().read().decode("utf-8")
        conn.close()
        self.assertIn('name="rpyx-token" content="test-token"', html)


if __name__ == "__main__":
    unittest.main()
