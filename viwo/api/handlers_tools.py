"""Handlers for the platform tools: survey, sanitizer, round trip (repack)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from viwo.contracts.types import ProgressEvent
from viwo.core import sanitizer
from viwo.core.preflight import install, preflight
from viwo.core.roundtrip import repack
from viwo.core.survey import survey

from .app import App


def survey_library(app: App, d: dict) -> dict:
    """Read-only coverage survey of a game folder or library, as a job (events per game)."""
    folder = Path(str(d.get("folder", "")).strip())
    if not str(folder) or not folder.is_dir():
        return {"success": False, "error": f"Folder not found: {folder}", "code": "not_found"}

    def run(jid, sink, cancel) -> dict:
        def note(game: Path, index: int, total: int) -> None:
            sink(
                ProgressEvent(f"Surveying {game.name} ({index}/{total})", "info", "core", "survey")
            )

        return {"success": True, "games": survey(app.rt, folder, bool(d.get("deep")), note)}

    job = app.jobs.submit_with_listener(
        lambda e: app.log(e.legacy_line()), "survey", run, background=False
    )
    if job.error:
        return {"success": False, "error": job.error["message"], "code": job.error["code"]}
    return {**job.result, "jobId": job.job_id}


RECIPES = [
    {
        "id": "phase1-safe",
        "name": "Safe cleanup",
        "lossy": False,
        "rules": ["core.zero_byte", "core.junk", "core.extension", "core.duplicate", "core.health"],
    }
]


def _sanitize(op: str) -> Callable[[App, dict], dict]:
    def handler(app: App, d: dict) -> dict:
        def run() -> dict:
            if op == "plan":
                return {"success": True, **sanitizer.plan(app.workspace)}
            if op == "apply":
                accept = d.get("accept") or "all-safe"
                return {
                    "success": True,
                    **sanitizer.apply(app.workspace, str(d.get("planId", "")), accept),
                }
            return {"success": True, **sanitizer.undo(app.workspace, str(d.get("undoToken", "")))}

        return app.locked(run)

    return handler


def repack_workspace(app: App, d: dict) -> dict:
    """Round trip of the active workspace: plan (plan=true) or build a patched copy (job)."""
    out = str(d.get("out", "")).strip()
    if d.get("plan"):
        return app.locked(
            lambda: {"success": True, **repack(app.rt, app.workspace, None, apply=False)}
        )
    if not out:
        return {
            "success": False,
            "error": "Choose a target folder for the patched copy",
            "code": "invalid_request",
        }

    def run(sink, cancel) -> dict:
        return {"success": True, **repack(app.rt, app.workspace, Path(out), sink, cancel)}

    return app.locked_job("repack", app.workspace, run)


def run_preflight(app: App, d: dict) -> dict:
    """Startup check (job "preflight"): one event per dependency, for the landing screen."""

    def run(jid, sink, cancel) -> dict:
        report = preflight(app.rt, sink, cancel)
        if report["installed"]:
            app.reload()  # newly installed tools bind now
        return {"success": True, **report}

    return _job(app, "preflight", run)


def install_dependency(app: App, d: dict) -> dict:
    """Install one dependency as a visible job, then reload the tool bindings."""

    def run(jid, sink, cancel) -> dict:
        done = install(app.rt, str(d.get("id", "")), sink, cancel)
        app.reload()
        return {"success": True, **done}

    return _job(app, "install", run)


def _job(app: App, kind: str, run) -> dict:
    job = app.jobs.submit_with_listener(
        lambda e: app.log(e.legacy_line()), kind, run, background=False
    )
    if job.error:
        return {
            "success": False,
            "error": job.error["message"],
            "code": job.error["code"],
            "hint": job.error["hint"],
            "jobId": job.job_id,
        }
    return {**job.result, "jobId": job.job_id}


TOOL_GET: dict[str, Callable[[App, dict], Any]] = {
    "/api/sanitizer/recipes": lambda app, q: {"success": True, "recipes": RECIPES},
}
TOOL_POST: dict[str, Callable[[App, dict], Any]] = {
    "/api/preflight": run_preflight,
    "/api/preflight/install": install_dependency,
    "/api/survey": survey_library,
    "/api/repack": repack_workspace,
    "/api/sanitizer/plan": _sanitize("plan"),
    "/api/sanitizer/apply": _sanitize("apply"),
    "/api/sanitizer/undo": _sanitize("undo"),
}
