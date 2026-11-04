"""ViWo web server: local API + static UI, with the hotfix security model (doc 4.1)."""

from __future__ import annotations

import hmac
import ipaddress
import json
import mimetypes
import secrets
import sys
import threading
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from viwo.contracts.errors import ViwoError
from viwo.core.curation.sorting import resolve

from . import plugin_assets, routes
from .app import App, get_app
from .handlers import GET, POST
from .ranges import ABORTED, _copy, byte_range

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
TOKEN_HEADER = "X-VIWO-Token"
COOKIE = "viwo_token"  # the same token, for media the page loads without headers
MAX_BODY = 16 << 20  # JSON requests only; anything bigger is not a ViWo request


WILDCARD_OR_LOOPBACK = {"0.0.0.0", "::", "", "127.0.0.1", "localhost", "::1"}


def _loopback(peer: str) -> bool:
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return address.is_loopback or bool(mapped and mapped.is_loopback)


class Handler(BaseHTTPRequestHandler):
    app: App
    token = ""
    server_version = "ViWo"

    def log_message(self, fmt: str, *args) -> None:  # quiet: the activity log is the record
        pass

    def _host_ok(self) -> bool:
        """The Host header names this machine (DNS rebinding) and the peer is this machine,
        unless the server is bound to one LAN address on purpose (then the token guards)."""
        host = str(self.headers.get("Host", "")).lower()
        name = host.rsplit("]", 1)[0] + "]" if host.startswith("[") else host.rsplit(":", 1)[0]
        bound = self.app.server.host.lower()
        if name not in {"127.0.0.1", "localhost", "[::1]", bound}:
            return False
        return bound not in WILDCARD_OR_LOOPBACK or _loopback(str(self.client_address[0]))

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
        if html_token:  # previews load as <img>/<video>, which send no header: a cookie
            self.send_header("Set-Cookie", f"{COOKIE}={self.token}; HttpOnly; SameSite=Strict")
        self.end_headers()
        self.wfile.write(body)

    def _reject(self, status: int, message: str) -> None:
        """Refused before the body is read: answer, then take in what the client already sent
        (at most 1 MiB, 0.2 s), so closing is a clean close and not a reset that can reach the
        client before the answer does (Windows sends RST over unread data)."""
        self.app.log(f"[SECURITY] {self.command} {self.path} rejected: {message}")
        self.close_connection = True
        self.send_json({"success": False, "error": message}, status)
        self.wfile.flush()
        self.connection.settimeout(0.2)
        try:
            for _ in range(16):
                if not self.rfile.read1(1 << 16):
                    break
        except OSError:  # the timeout: nothing more is coming
            pass

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
            query = {k: v[0] for k, v in parse_qs(url.query).items()}  # scalars for handlers
            return self._api(GET, routes.handle_get, path, query)
        if path.startswith("/preview/"):  # resolve() decodes once: pass the raw path
            return self._preview(url.path[len("/preview/") :])
        if plugin_assets.serve(self, path):  # plugin UI add-ons: /plugins/<id>/ui.js
            return
        self._static(path, parse_qs(url.query).get("key", [""])[0])

    def do_POST(self) -> None:
        path = unquote(urlparse(self.path).path)
        if not self._host_ok():
            return self._reject(403, "Host not allowed")
        if not self._token_ok():
            return self._reject(403, "Missing or invalid API token")
        kind = str(self.headers.get("Content-Type", "")).split(";", 1)[0].strip().lower()
        if kind != "application/json":
            return self._reject(415, "Content-Type must be application/json")
        try:
            size = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            size = -1
        if size < 0 or size > MAX_BODY:
            return self._reject(413, "Request body too large or malformed")
        try:
            data = json.loads(self.rfile.read(size).decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self.send_json({"success": False, "error": "Invalid JSON"}, 400)
        self._api(POST, routes.handle_post, path, data if isinstance(data, dict) else {})

    def do_HEAD(self) -> None:
        url = urlparse(self.path)
        if not self._host_ok() or not url.path.startswith("/preview/"):
            return self.send_error(404)
        self._preview(url.path[len("/preview/") :], head=True)

    def _cookie_ok(self) -> bool:
        """This machine, or a peer that was given the page with the token (its cookie)."""
        if _loopback(str(self.client_address[0])):
            return True
        jar = SimpleCookie(str(self.headers.get("Cookie", "")))
        sent = jar[COOKIE].value if COOKIE in jar else ""
        return bool(self.token) and hmac.compare_digest(sent, self.token)

    def _preview(self, rel: str, head: bool = False) -> None:
        """Workspace files, streamed, with single byte ranges so media can seek; a LAN peer
        needs the token's cookie (the workspace is the user's data)."""
        if not self._cookie_ok():
            return self.send_error(403)
        try:
            path = resolve(self.app.workspace, rel)
        except ViwoError:
            return self.send_error(404)
        try:
            self._stream(path, head)
        except ABORTED:
            pass

    def _stream(self, path: Path, head: bool) -> None:
        size = path.stat().st_size
        span = byte_range(str(self.headers.get("Range", "")), size)
        if span == (-1, -1):
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            return self.end_headers()
        start, end = span or (0, size - 1)
        self.send_response(206 if span else 200)
        self.send_header(
            "Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        )
        self.send_header("Content-Length", str(max(0, end - start + 1)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        if span:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if not head and size:
            with path.open("rb") as handle:
                handle.seek(start)
                _copy(handle, self.wfile, end - start + 1)

    def _static(self, path: str, key: str = "") -> None:
        """The page carries the API token for this machine only; a LAN peer (a server bound to
        a LAN address on purpose) gets it with the `?key=` link `viwo serve` prints."""
        rel = (path.lstrip("/") or "index.html") + (
            "index.html" if path.endswith("/") and path != "/" else ""
        )
        target = (WEB_ROOT / rel).resolve()
        if WEB_ROOT.resolve() not in target.parents or not target.is_file():
            return self.send_error(404)
        local = _loopback(str(self.client_address[0]))
        keyed = bool(key) and hmac.compare_digest(key, self.token)
        self.send_file(target, html_token=target.name == "index.html" and (local or keyed))


class QuietServer(ThreadingHTTPServer):
    """socketserver prints every handler exception; a client that went away is not one."""

    def handle_error(self, request, client_address) -> None:
        if not isinstance(sys.exc_info()[1], ABORTED):
            super().handle_error(request, client_address)


def make_server(app: App, host: str | None = None, port: int | None = None) -> ThreadingHTTPServer:
    Handler.app = app
    Handler.token = secrets.token_urlsafe(32)
    return QuietServer(
        (host or app.server.host, app.server.port if port is None else port), Handler
    )


def strict_check(app: App) -> list[str]:
    """doc 9.3 step 9: run the preflight (installs), rebind, list plugin slots still unbound."""
    from viwo.core.preflight import preflight, strict_problems

    report = preflight(app.rt, lambda e: print(e.legacy_line(), flush=True))
    if report["installed"]:
        app.reload()
    return strict_problems(app.rt)


def serve(
    ini: Path | None = None, host: str | None = None, port: int | None = None, browser: bool = True
) -> int:
    app = get_app(ini)
    if app.rt.config.strict_preflight and (missing := strict_check(app)):
        print("viwo: strict_preflight is on and these formats have no tool:", flush=True)
        print("\n".join(f"  {m}" for m in missing), flush=True)
        return 4
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
    if app.server.host.lower() not in WILDCARD_OR_LOOPBACK:  # reachable from the LAN on purpose
        print(
            f"From another machine: {url}?key={Handler.token}  (keep this link private)", flush=True
        )
    print(f"Workspace: {app.workspace}   (Ctrl+C stops the server)", flush=True)
    if browser:
        threading.Timer(0.6, webbrowser.open, [url]).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
    return 0
