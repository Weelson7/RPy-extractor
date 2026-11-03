"""Generic job submit (doc 12.5): `POST /api/jobs {kind, params}` runs the same handler the
kind's own route uses, so every job kind is reachable from one entry point."""

from __future__ import annotations

from typing import Any, Callable

from .app import App
from .handlers_analysis import run_analysis
from .handlers_capture import run_capture
from .handlers_tools import (
    install_dependency,
    repack_workspace,
    run_preflight,
    sanitize_handler,
    survey_library,
)

KINDS: dict[str, Callable[[App, dict], dict]] = {
    "extract": lambda app, params: app.extract(params),
    "survey": survey_library,
    "repack": repack_workspace,
    "preflight": run_preflight,
    "install": install_dependency,
    "capture": run_capture,
    "analyze": run_analysis,
    "cleanup": lambda app, params: sanitize_handler(str(params.get("op") or "plan"))(app, params),
}


def submit(app: App, d: dict) -> dict:
    kind = str(d.get("kind", ""))
    params = d.get("params") if isinstance(d.get("params"), dict) else {}
    if kind not in KINDS:
        return {
            "success": False,
            "error": f"unknown job kind: {kind or '(none)'}",
            "code": "invalid_request",
            "hint": "kinds: " + ", ".join(sorted(KINDS)),
        }
    return KINDS[kind](app, params)


JOBS_POST: dict[str, Callable[[App, dict], Any]] = {"/api/jobs": submit}
