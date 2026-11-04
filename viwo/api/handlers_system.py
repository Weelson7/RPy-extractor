"""System handlers: diagnostics bundle, update checks (on click only), indexes update job."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from viwo import __version__
from viwo.contracts.errors import ViwoError
from viwo.core import diag
from viwo.core.indexes import update_indexes
from viwo.core.thirdparty import home_of

from .app import App, safe


def check_updates(app: App, q: dict) -> dict:
    """GET /api/updates: latest ViWo and indexes releases; never called automatically."""
    return safe(lambda: {"success": True, **diag.check_updates(home_of(app.rt.config))})


def make_diag(app: App, d: dict) -> dict:
    """POST /api/diag {out?}: zip logs, run records and tool status (secrets stripped)."""
    out = Path(str(d.get("out", "")).strip()) if d.get("out") else None
    try:
        path = diag.bundle(app.rt, app.workspace, out)
    except (ViwoError, OSError) as exc:
        message = exc.message if isinstance(exc, ViwoError) else str(exc)
        return {"success": False, "error": message, "code": "failed"}
    return {"success": True, "path": str(path)}


def indexes_update(app: App, d: dict) -> dict:
    """POST /api/indexes/update: job "indexes", the latest release for this major version."""
    major = int(__version__.split(".")[0])

    def run(jid, sink, cancel) -> dict:
        return {"success": True, **update_indexes(home_of(app.rt.config), major, sink, cancel)}

    return app.job("indexes", run)


SYSTEM_GET: dict[str, Callable[[App, dict], Any]] = {"/api/updates": check_updates}
SYSTEM_POST: dict[str, Callable[[App, dict], Any]] = {
    "/api/diag": make_diag,
    "/api/indexes/update": indexes_update,
}
