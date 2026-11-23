"""SEARCH (doc 6.7): a string, a number or a byte pattern in a workspace, a game folder or one
file, as a job of kind "search"; the report is saved in the active workspace's `.search/` (or
said not to be, with the reason)."""

from typing import Any, Callable

from viwo.contracts.errors import ViwoError
from viwo.core.search import Limits, results_folder, search
from viwo.core.search_query import build
from viwo.core.steps import tell

from .app import App, failure, path_param

CAPS = (("perFile", 100), ("maxHits", 1000), ("context", 16), ("signatures", 8))


def _number(d: dict, key: str, default: int) -> int:
    given = d.get(key)
    try:
        return default if given in (None, "") else int(given)
    except (TypeError, ValueError):
        raise ViwoError("invalid_request", f"{key} must be a whole number, not {given!r}") from None


def run_search(app: App, d: dict) -> dict:
    """POST /api/search {target, kind: text|number|bytes, value, ignoreCase?, widths?, perFile?,
    maxHits?, context?, signatures?}: the search as a job (read-only: no workspace lock)."""
    target = path_param(d, "target")
    if target is None or not target.exists():
        given = str(d.get("target") or "").strip() or "(none given)"
        why = f"nothing to search at {given}"
        return failure(ViwoError("not_found", why, hint="an absolute path to a file or a folder"))
    try:
        kind, value = str(d.get("kind") or "text"), str(d.get("value") or "")
        query = build(kind, value, bool(d.get("ignoreCase")), d.get("widths") or None)
        limits = Limits(*(_number(d, key, default) for key, default in CAPS))
    except ViwoError as exc:
        return failure(exc)
    try:
        folder, unsaved = results_folder(target, app.workspace), ""
    except ViwoError as exc:  # the search still runs: only its report is not kept
        folder, unsaved = None, f"the results are not saved in {app.workspace}: {exc.message}"

    def run(jid, sink, cancel) -> dict:
        if unsaved:
            tell(sink, unsaved, "search", "warn")
        report = search(target, query, limits, sink, cancel, folder)
        report["warnings"] = [unsaved, *report["warnings"]] if unsaved else report["warnings"]
        return {"success": True, **report}

    return app.job("search", run, {"workspace": folder, "game": target})


SEARCH_POST: dict[str, Callable[[App, dict], Any]] = {"/api/search": run_search}
