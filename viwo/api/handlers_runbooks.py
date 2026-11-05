"""RUNBOOKS (doc 19.2): the runbooks, one action step at a time through the handler POST
/api/jobs uses (so every action keeps its own checks), and the user's saved copies."""

from __future__ import annotations

from typing import Any, Callable

from viwo.contracts.errors import ViwoError
from viwo.core import runbooks
from viwo.core.guides import delete

from .app import App, failure, safe
from .handlers_jobs import KINDS, submit


def list_runbooks(app: App, q: dict) -> dict:
    """GET /api/runbooks: every runbook, the files that could not be used, the job kinds."""
    books, problems = runbooks.load(app.rt, KINDS)
    return {"success": True, "runbooks": books, "problems": problems, "kinds": sorted(KINDS)}


def find(app: App, book_id: str) -> dict:
    book = next((b for b in runbooks.load(app.rt, KINDS)[0] if b["id"] == book_id), None)
    if book is None:
        raise ViwoError("not_found", f"no runbook {book_id!r}", hint="GET /api/runbooks lists them")
    return book


def run_step(app: App, book: dict, index: int, values: dict) -> dict:
    """One action step in the active workspace: the job's answer plus `step`."""
    if not 0 <= index < len(book["steps"]) or "do" not in book["steps"][index]:
        raise ViwoError("invalid_request", f"step {index + 1} of {book['id']} is not an action")
    step, game = book["steps"][index], str(values.get("game") or "")
    params = runbooks.resolve(step["with"], runbooks.values_for(book, values, game, app.workspace))
    app.log(f"[RUNBOOK] {book['id']} step {index + 1}/{len(book['steps'])}: {step['title']}")
    return {**submit(app, {"kind": step["do"], "params": params}), "step": index}


def step_route(app: App, d: dict) -> dict:
    """POST /api/runbooks/step {id, step, values}."""
    try:
        index = int(d.get("step", -1))
    except (TypeError, ValueError):
        return failure(ViwoError("invalid_request", "step must be a number (from 0)"))
    values = d.get("values") if isinstance(d.get("values"), dict) else {}
    return safe(lambda: run_step(app, find(app, str(d.get("id", ""))), index, values))


def save_route(app: App, d: dict) -> dict:
    """POST /api/runbooks/save {runbook}: the user's copy, validated first."""
    raw = d.get("runbook")
    return safe(lambda: {"success": True, "path": str(runbooks.save(app.rt, KINDS, raw))})


def delete_route(app: App, d: dict) -> dict:
    """POST /api/runbooks/delete {id}: only the user's own file."""
    book_id = str(d.get("id", ""))
    return safe(lambda: {"success": True, "deleted": str(delete(app.rt, runbooks.KIND, book_id))})


RUNBOOKS_GET: dict[str, Callable[[App, dict], Any]] = {"/api/runbooks": list_runbooks}
RUNBOOKS_POST: dict[str, Callable[[App, dict], Any]] = {
    "/api/runbooks/step": step_route,
    "/api/runbooks/save": save_route,
    "/api/runbooks/delete": delete_route,
}
