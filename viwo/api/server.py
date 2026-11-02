"""ViWo web server: local API + static UI, with the hotfix security model (doc 4.1)."""

from __future__ import annotations

import hmac
import json
import mimetypes
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from viwo.contracts.errors import ViwoError
from viwo.core.curation.sorting import resolve

from . import routes
from .app import App, get_app
from .handlers import GET, POST

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
TOKEN_HEADER = "X-VIWO-Token"


class Handler(BaseHTTPRequestHandler):
    app: App
    token = ""
    server_version = "ViWo"

    def log_message(self, fmt: str, *args) -> None:  # quiet: the activity log is the record
        pass

    def _host_ok(self) -> bool:
        host = str(self.headers.get("Host", "")).lower()
        name = host.rsplit("]", 1)[0] + "]" if host.startswith("[") else host.rsplit(":", 1)[0]
        return name in {"127.0.0.1", "localhost", "[::1]", self.app.server.host.lower()}

    def _token_ok(self) -> bool:
        sent = str(self.headers.get(TOKEN_HEADER, ""))
        return bool(self.token) and hmac.compare_digest(sent, self.token)

    def send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, html_token: bool = False) -> None:
        body = path.read_bytes()
        if html_token:
            meta = f'<meta name="viwo-token" content="{self.token}">'
            body = body.replace(b"</head>", f"  {meta}\n</head>".encode(), 1)
        kind = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header(
            "Content-Type", kind + ("; charset=utf-8" if kind.startswith("text") else "")
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if html_token else "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _reject(self, status: int, message: str) -> None:
        self.app.log(f"[SECURITY] {self.command} {self.path} rejected: {message}")
        self.send_json({"success": False, "error": message}, status)

    def _api(self, table: dict, routed, path: str, arg) -> None:
        try:
            bridged = routed(path, arg)
            if bridged is not None:
                self.send_json(*bridged)
            elif path in table:
                self.send_json(table[path](self.app, arg))
            else:
                self.send_json({"success": False, "error": f"Unknown route {path}"}, 404)
        except Exception as exc:  # internal errors never crash the server
            self.app.log(f"[ERROR] {self.command} {path}: {type(exc).__name__}: {exc}")
            self.send_json({"success": False, "error": "internal error", "code": "internal"}, 500)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        path = unquote(url.path)
        if not self._host_ok():
            return self._reject(403, "Host not allowed")
        if path.startswith("/api/"):
            if not self._token_ok():
                return self._reject(403, "Missing or invalid API token")
            return self._api(GET, routes.handle_get, path, parse_qs(url.query))
        if path.startswith("/preview/"):
            return self._preview(path[len("/preview/") :])
        self._static(path)

    def do_POST(self) -> None:
        path = unquote(urlparse(self.path).path)
        if not self._host_ok():
            return self._reject(403, "Host not allowed")
        if not self._token_ok():
            return self._reject(403, "Missing or invalid API token")
        kind = str(self.headers.get("Content-Type", "")).split(";", 1)[0].strip().lower()
        if kind != "application/json":
            return self._reject(415, "Content-Type must be application/json")
        size = int(self.headers.get("Content-Length", 0) or 0)
        try:
            data = json.loads(self.rfile.read(size).decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self.send_json({"success": False, "error": "Invalid JSON"}, 400)
        self._api(POST, routes.handle_post, path, data if isinstance(data, dict) else {})

    def _preview(self, rel: str) -> None:
        try:
            self.send_file(resolve(self.app.workspace, rel))
        except ViwoError:
            self.send_error(404)

    def _static(self, path: str) -> None:
        rel = (path.lstrip("/") or "index.html") + (
            "index.html" if path.endswith("/") and path != "/" else ""
        )
        target = (WEB_ROOT / rel).resolve()
        if WEB_ROOT.resolve() not in target.parents or not target.is_file():
            return self.send_error(404)
        self.send_file(target, html_token=target.name == "index.html")


def make_server(app: App, host: str | None = None, port: int | None = None) -> ThreadingHTTPServer:
    Handler.app = app
    Handler.token = secrets.token_urlsafe(32)
    return ThreadingHTTPServer(
        (host or app.server.host, app.server.port if port is None else port), Handler
    )


def serve(ini: Path | None = None, host: str | None = None, port: int | None = None) -> int:
    app = get_app(ini)
    try:
        httpd = make_server(app, host, port)
    except OSError as exc:
        where = f"{host or app.server.host}:{app.server.port if port is None else port}"
        print(
            f"viwo: cannot listen on {where}: {exc.strerror or exc}. "
            "Use --port or change [server] port in startup.ini.",
            flush=True,
        )
        return 2
    url = f"http://{app.server.host}:{httpd.server_address[1]}/"
    app.log(f"[SERVER] ViWo listening on {url} (workspace {app.workspace})")
    for problem in app.rt.problems:
        app.log(f"[SERVER] note: {problem}")
    print(f"ViWo // Vidya Wormhole -> {url}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
    return 0
