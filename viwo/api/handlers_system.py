"""System handlers: diagnostics bundle, update checks (on click only), indexes update job,
workbooks."""

from typing import Any, Callable

from viwo import __version__
from viwo.contracts.errors import ViwoError
from viwo.core import diag
from viwo.core.indexes import update_indexes
from viwo.core.thirdparty import home_of

from .app import App, path_param, safe


def check_updates(app: App, q: dict) -> dict:
    """GET /api/updates: latest ViWo and indexes releases; never called automatically."""
    return safe(lambda: {"success": True, **diag.check_updates(home_of(app.rt.config))})


def make_diag(app: App, d: dict) -> dict:
    """POST /api/diag {out?}: zip logs, run records and tool status (secrets stripped)."""
    out = path_param(d, "out")
    if str(d.get("out") or "").strip() and out is None:
        return {
            "success": False,
            "error": "out must be an absolute path",
            "code": "invalid_request",
        }
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


def workbooks(app: App, q: dict) -> dict:
    """GET /api/workbooks: every workbook (doc 19.1) and the files that could not be used."""
    from viwo.core.workbooks import load

    books, problems = load(app.rt)
    return {"success": True, "workbooks": books, "problems": problems}


SYSTEM_GET: dict[str, Callable[[App, dict], Any]] = {
    "/api/updates": check_updates,
    "/api/workbooks": workbooks,
}
SYSTEM_POST: dict[str, Callable[[App, dict], Any]] = {
    "/api/diag": make_diag,
    "/api/indexes/update": indexes_update,
}
