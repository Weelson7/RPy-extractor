"""Main entry point for RPy Extractor web server."""
import json
import mimetypes
import os
import sys
import tempfile
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse
from logging_utils import configure_log_directory

# Import all modular components
from models import AppConfig, SESSIONS
from startup import startup_dependency_preflight, dependency_status_snapshot, tlog
from handlers import (
    get_initial_state,
    extract_repo,
    scan_extensions,
    get_extensions_list,
    get_sort_status,
    keep_selected,
    move_to_trash_endpoint,
    restore_from_trash_endpoint,
    delete_from_trash_endpoint,
    clear_trash_endpoint,
    get_assets_for_preview,
    get_asset_preview_url,
    list_assets_for_sorting_window,
    get_asset_preview_content,
    sort_keep_asset,
    sort_trash_asset,
    sort_undo_last_action,
    sort_rename_asset,
    save_remaining_assets,
    list_all_logs,
    clear_all_logs,
    load_log_file_entries,
    open_log_dir,
    open_folder_path,
    get_session_state,
    resume_session,
    browse_folder,
)


# ============================================================================
# Configuration
# ============================================================================

def get_app_config() -> AppConfig:
    """Get application configuration from config.json with safe defaults."""
    root = Path(__file__).parent
    cfg_path = root / "config.json"

    cfg: dict[str, Any] = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            tlog(f"[CONFIG] Loaded config from {cfg_path}")
        except Exception as exc:
            tlog(f"[WARN] Failed to parse config.json, using defaults: {exc}")

    # Extract configuration with defaults
    host = str(cfg.get("host", "localhost"))
    port = int(cfg.get("port", 8000))
    
    # Resolve temp path
    temp_raw = str(cfg.get("tempPath", "./tmp"))
    temp_path = Path(temp_raw)
    if not temp_path.is_absolute():
        temp_path = root / temp_path
    temp_path.mkdir(parents=True, exist_ok=True)
    tlog(f"[CONFIG] Temp path: {temp_path}")

    # Resolve output directory name
    output_raw = str(cfg.get("outputDir", "./assets"))
    output_dir_name = Path(output_raw).name or "assets"

    # Resolve web directory
    web_raw = str(cfg.get("webDir", "web"))
    web_dir_path = Path(web_raw)
    if not web_dir_path.is_absolute():
        web_dir_path = root / web_dir_path
    tlog(f"[CONFIG] Web files: {web_dir_path}")

    # Resolve log directory
    log_raw = str(cfg.get("logDir", "./logs"))
    log_dir_path = Path(log_raw)
    if not log_dir_path.is_absolute():
        log_dir_path = root / log_dir_path
    log_dir_path.mkdir(parents=True, exist_ok=True)
    configure_log_directory(log_dir_path)
    tlog(f"[CONFIG] Log directory: {log_dir_path}")

    config = AppConfig(
        host=host,
        port=port,
        temp_path=temp_path,
        output_dir_name=output_dir_name,
        web_dir_name=str(web_dir_path),
        log_dir=log_dir_path,
    )
    
    tlog(f"[CONFIG] Server: {host}:{port}")
    return config


# ============================================================================
# HTTP Request Handler
# ============================================================================

class Handler(BaseHTTPRequestHandler):
    """HTTP request handler."""

    app_config: Any = None
    
    # Route handlers mapping for cleaner dispatch
    GET_ROUTES: dict[str, Callable[[], Any]] = {}
    POST_ROUTES: dict[str, Callable[[dict], Any]] = {}

    def log_message(self, format: str, *args: Any) -> None:
        """Override logging to use tlog with verbose routing info."""
        if str(self.path).startswith("/api/logs"):
            return
        tlog(f"[HTTP] {self.command} {self.path} - {format % args}")

    def _is_request_origin_allowed(self) -> bool:
        """Lightweight origin check for side-effect endpoints."""
        allowed_prefixes = (
            f"http://{self.app_config.host}:{self.app_config.port}",
            f"http://127.0.0.1:{self.app_config.port}",
            f"http://localhost:{self.app_config.port}",
        )

        origin = str(self.headers.get("Origin", "")).strip()
        referer = str(self.headers.get("Referer", "")).strip()

        if origin and not any(origin.startswith(prefix) for prefix in allowed_prefixes):
            return False
        if referer and not any(referer.startswith(prefix) for prefix in allowed_prefixes):
            return False
        return True

    def do_GET(self) -> None:
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)

        if path != "/api/logs":
            tlog(f"[GET] Route: {path}")

        # ---- API Routes ----
        try:
            if path == "/api/state":
                self.send_json_response(get_initial_state(self.app_config))
                return

            if path == "/api/status":
                self.send_json_response(get_sort_status(self.app_config))
                return

            if path == "/api/extensions":
                self.send_json_response(get_extensions_list(self.app_config))
                return

            if path == "/api/detected-extensions":
                result = scan_extensions(self.app_config)
                self.send_json_response(result)
                return

            if path == "/api/logs":
                logs = list_all_logs(self.app_config)
                self.send_json_response(logs)
                return

            if path == "/api/open-log-dir":
                self.send_json_response(open_log_dir(self.app_config))
                return

            if path == "/api/logs/load":
                self.send_json_response(load_log_file_entries(self.app_config))
                return

            if path == "/api/dependencies":
                self.send_json_response(dependency_status_snapshot())
                return

            if path == "/api/open-folder":
                self.send_json_response({"success": False, "error": "Use POST for this endpoint"}, 405)
                return

            if path == "/api/assets-window":
                offset_raw = query.get("offset", ["0"])[0]
                limit_raw = query.get("limit", ["100"])[0]
                try:
                    offset = int(offset_raw)
                except Exception:
                    offset = 0
                try:
                    limit = int(limit_raw)
                except Exception:
                    limit = 100
                self.send_json_response(list_assets_for_sorting_window(self.app_config, max_assets=limit, offset=offset))
                return

            if path == "/api/assets-window-preview":
                encoded_path = query.get("path", [""])[0]
                self.send_json_response(get_asset_preview_content(self.app_config, encoded_path))
                return

            if path == "/api/session":
                self.send_json_response(get_session_state(self.app_config))
                return

            if path == "/api/browse-folder":
                initial_path = query.get("initialPath", [""])[0]
                self.send_json_response(browse_folder(initial_path))
                return

            if path.startswith("/preview/"):
                rel_path = path[len("/preview/"):]
                self.serve_asset_preview(rel_path)
                return

        except Exception as exc:
            tlog(f"[ERROR] GET {path} failed: {exc}")
            self.send_json_response({"error": str(exc)}, 500)
            return

        # ---- Static Files ----
        self._serve_static_file(path)

    def _serve_static_file(self, path: str) -> None:
        """Serve static file from web directory."""
        # Default to index.html for root
        if path == "/" or path == "":
            path = "/index.html"

        if path.startswith("/"):
            path = path[1:]

        file_path = Path(self.app_config.web_dir_name) / path
        if not file_path.exists() or not file_path.is_file():
            tlog(f"[404] Static file not found: {file_path}")
            self.send_error(404, "Not Found")
            return

        self.serve_file(file_path)

    def do_POST(self) -> None:
        """Handle POST requests."""
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8", errors="replace")

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            tlog(f"[ERROR] Invalid JSON in POST {path}: {exc}")
            self.send_json_response({"error": "Invalid JSON"}, 400)
            return

        tlog(f"[POST] Route: {path}")

        try:
            # ---- API Routes ----
            if path == "/api/extract":
                game_path = data.get("gamePath", "")
                selected_exts = data.get("selectedExts", None)
                extraction_type = data.get("extractionType", None)
                result = extract_repo(
                    game_path,
                    self.app_config,
                    selected_exts,
                    extraction_type,
                    self.progress_callback,
                )
                self.send_json_response(result)
                return

            if path == "/api/scan":
                asset_path = data.get("assetPath", None)
                result = scan_extensions(self.app_config, asset_path, self.progress_callback)
                self.send_json_response(result)
                return

            if path == "/api/keep-selected":
                selected_exts = data.get("selectedExts", [])
                result = keep_selected(self.app_config, selected_exts, self.progress_callback)
                self.send_json_response(result)
                return

            if path == "/api/trash":
                ext_folder = data.get("folder", "")
                result = move_to_trash_endpoint(self.app_config, ext_folder, self.progress_callback)
                self.send_json_response(result)
                return

            if path == "/api/restore":
                ext_folder = data.get("folder", "")
                result = restore_from_trash_endpoint(self.app_config, ext_folder, self.progress_callback)
                self.send_json_response(result)
                return

            if path == "/api/delete":
                ext_folder = data.get("folder", "")
                result = delete_from_trash_endpoint(self.app_config, ext_folder, self.progress_callback)
                self.send_json_response(result)
                return

            if path == "/api/clear-trash":
                result = clear_trash_endpoint(self.app_config, self.progress_callback)
                self.send_json_response(result)
                return

            if path == "/api/resume":
                game_path = data.get("gamePath", "")
                result = resume_session(self.app_config, game_path)
                self.send_json_response(result)
                return

            if path == "/api/assets-preview":
                ext_folder = data.get("folder", "")
                result = get_assets_for_preview(self.app_config, ext_folder)
                self.send_json_response(result)
                return

            if path == "/api/sort-keep":
                encoded_path = str(data.get("path", ""))
                self.send_json_response(sort_keep_asset(self.app_config, encoded_path))
                return

            if path == "/api/sort-trash":
                encoded_path = str(data.get("path", ""))
                self.send_json_response(sort_trash_asset(self.app_config, encoded_path))
                return

            if path == "/api/sort-undo":
                self.send_json_response(sort_undo_last_action(self.app_config))
                return

            if path == "/api/sort-rename":
                encoded_path = str(data.get("path", ""))
                new_name = str(data.get("newName", ""))
                self.send_json_response(sort_rename_asset(self.app_config, encoded_path, new_name))
                return

            if path == "/api/logs/clear":
                self.send_json_response(clear_all_logs(self.app_config))
                return

            if path == "/api/open-folder":
                if not self._is_request_origin_allowed():
                    self.send_json_response({"success": False, "error": "Request origin not allowed"}, 403)
                    return

                folder_path = str(data.get("path", ""))
                self.send_json_response(open_folder_path(folder_path))
                return

            if path == "/api/save-remaining-assets":
                encoded_paths = data.get("paths", [])
                destination_path = str(data.get("destinationPath", ""))
                if not isinstance(encoded_paths, list):
                    encoded_paths = []
                self.send_json_response(save_remaining_assets(self.app_config, encoded_paths, destination_path))
                return

            tlog(f"[404] POST route not found: {path}")
            self.send_error(404, "Not Found")

        except Exception as exc:
            tlog(f"[ERROR] POST {path} failed: {exc}")
            self.send_json_response({"error": str(exc)}, 500)

    def send_json_response(self, data: dict, status: int = 200) -> None:
        """Send JSON response."""
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        if not str(self.path).startswith("/api/logs"):
            tlog(f"[JSON] Status {status}: {len(body)} bytes")

    def _resolve_mime_type(self, file_path: Path) -> str:
        """Resolve MIME type for a file with logging."""
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "application/octet-stream"
            tlog(f"[MIME] No type for {file_path.suffix}, using {mime_type}")
        else:
            tlog(f"[MIME] {file_path.suffix} -> {mime_type}")
        return mime_type

    def serve_file(self, file_path: Path) -> None:
        """Serve static file with detailed logging."""
        if not file_path.exists():
            tlog(f"[FILE] Not found: {file_path}")
            self.send_error(404)
            return

        try:
            mime_type = self._resolve_mime_type(file_path)
            
            with open(file_path, "rb") as f:
                body = f.read()
            
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            
            tlog(f"[FILE] Served {file_path.name}: {len(body)} bytes ({mime_type})")
        except Exception as exc:
            tlog(f"[ERROR] Failed to serve {file_path}: {exc}")
            self.send_error(500)

    def serve_asset_preview(self, rel_path: str) -> None:
        """Serve asset preview file with logging."""
        try:
            assets_dir = (self.app_config.temp_path / self.app_config.output_dir_name).resolve()
            asset_path = (assets_dir / unquote(rel_path)).resolve()

            try:
                asset_path.relative_to(assets_dir)
            except Exception:
                tlog(f"[PREVIEW] Blocked invalid path: {rel_path}")
                self.send_error(404)
                return

            if not asset_path.exists() or not asset_path.is_file():
                tlog(f"[PREVIEW] Not found: {asset_path}")
                self.send_error(404)
                return

            mime_type = self._resolve_mime_type(asset_path)

            with open(asset_path, "rb") as f:
                body = f.read()

            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
            
            tlog(f"[PREVIEW] Served {asset_path.name}: {len(body)} bytes ({mime_type})")
        except Exception as exc:
            tlog(f"[ERROR] Failed to serve asset preview: {exc}")
            self.send_error(500)

    def progress_callback(self, message: str) -> None:
        """Progress callback for long-running operations with enhanced logging."""
        tlog(f"[PROGRESS] {message}")
        session = SESSIONS.get_current()
        if not session:
            session = {"logs": []}
            tlog("[PROGRESS] Created new session")
        logs = session.get("logs", [])
        logs.append(message)
        session["logs"] = logs
        SESSIONS.set_current(session)


# ============================================================================
# Server Startup
# ============================================================================

def run_server(app_config: AppConfig) -> None:
    """Run the HTTP server with detailed logging."""
    Handler.app_config = app_config

    server_address = (app_config.host, app_config.port)
    server = ThreadingHTTPServer(server_address, Handler)

    tlog(f"[SERVER] Starting on http://{app_config.host}:{app_config.port}")
    tlog(f"[SERVER] Web files: {app_config.web_dir_name}")
    tlog(f"[SERVER] Temp path: {app_config.temp_path}")
    tlog(f"[SERVER] Output dir: {app_config.output_dir_name}")

    try:
        tlog("[SERVER] ✓ Ready for requests")
        server.serve_forever()
    except KeyboardInterrupt:
        tlog("[SERVER] ✗ Shutdown requested")
        server.shutdown()
        tlog("[SERVER] ✓ Shut down cleanly")


def main() -> None:
    """Main entry point."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tlog(f"=== RPy Extractor {stamp} ===")

    # Run startup checks
    preflight = startup_dependency_preflight()
    ok = bool(preflight.get("ok", False))
    raw_messages = preflight.get("report", [])
    messages = raw_messages if isinstance(raw_messages, list) else []
    for msg in messages:
        tlog(msg)

    if not ok:
        tlog("[ERROR] Startup preflight failed")
        sys.exit(1)

    # Get configuration
    app_config = get_app_config()

    # Run server
    run_server(app_config)


if __name__ == "__main__":
    main()
