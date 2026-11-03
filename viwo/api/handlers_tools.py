"""Handlers for the platform tools: survey (+ saved reports), sanitizer (as the "cleanup"
job), round trip (repack), preflight and installs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from viwo.contracts.errors import ViwoError
from viwo.contracts.types import ProgressEvent
from viwo.core import sanitizer, surveys
from viwo.core.preflight import install, preflight
from viwo.core.roundtrip import repack
from viwo.core.sanitizer_rules import collect_rules
from viwo.core.survey import survey

from .app import App


def survey_library(app: App, d: dict) -> dict:
    """Read-only coverage survey of a game folder or library, as a job (events per game)."""
    folder = Path(str(d.get("folder", "")).strip())
    if not str(folder) or not folder.is_dir():
        return {"success": False, "error": f"Folder not found: {folder}", "code": "not_found"}

    reports, deep = _reports_dir(app), bool(d.get("deep"))

    def run(jid, sink, cancel) -> dict:
        def note(game: Path, index: int, total: int) -> None:
            sink(
                ProgressEvent(f"Surveying {game.name} ({index}/{total})", "info", "core", "survey")
            )

        games = survey(app.rt, folder, deep, note, cancel, sink)
        saved = surveys.save(reports, folder, deep, games)
        sink(ProgressEvent(f"Report saved: {saved['path']}", "info", "core", "report"))
        return {"success": True, "games": games, "reportId": saved["id"], **_meta(saved)}

    return app.job("survey", run)


def _reports_dir(app: App) -> Path:
    return app.server.logs.parent / "surveys"


def _meta(saved: dict) -> dict:
    return {"reportPath": saved["path"], "when": saved["when"]}


def survey_reports(app: App, q: dict) -> dict:
    """Every saved survey report (header only), newest first."""
    return {"success": True, "reports": surveys.list_reports(_reports_dir(app))}


def survey_report(app: App, q: dict) -> dict:
    try:
        report = surveys.load(_reports_dir(app), q.get("id", ""))
    except ViwoError as exc:
        return {"success": False, "error": exc.message, "code": exc.code}
    return {"success": True, "report": report}


def sanitize_handler(op: str) -> Callable[[App, dict], dict]:
    def handler(app: App, d: dict) -> dict:
        folder = app.workspace  # read once: the workspace can be switched meanwhile

        def run(sink, cancel) -> dict:  # a "cleanup" job: visible in 04 JOBS and the chips
            if op == "plan":
                opts = {k: d.get(k) for k in ("path", "offset", "limit")}
                opts["recipe"], opts["rules"] = d.get("recipeId"), collect_rules(app.rt)
                return {"success": True, **sanitizer.plan(folder, sink, cancel, **opts)}
            if op == "apply":
                accept = d.get("accept") or "all-safe"
                plan_id = str(d.get("planId", ""))
                return {"success": True, **sanitizer.apply(folder, plan_id, accept, sink, cancel)}
            token = str(d.get("undoToken", ""))
            return {"success": True, **sanitizer.undo(folder, token, sink, cancel)}

        return app.locked_job("cleanup", folder, run)

    return handler


def repack_workspace(app: App, d: dict) -> dict:
    """Round trip of the active workspace: plan (plan=true) or build a patched copy (job)."""
    out, folder = str(d.get("out", "")).strip(), app.workspace
    if d.get("plan"):
        return app.locked(
            lambda: {"success": True, **repack(app.rt, folder, None, apply=False)}, folder
        )
    if not out:
        return {
            "success": False,
            "error": "Choose a target folder for the patched copy",
            "code": "invalid_request",
        }

    def run(sink, cancel) -> dict:
        return {"success": True, **repack(app.rt, folder, Path(out), sink, cancel)}

    return app.locked_job("repack", folder, run)


def run_preflight(app: App, d: dict) -> dict:
    """Startup check (job "preflight"): one event per dependency, for the landing screen."""

    def run(jid, sink, cancel) -> dict:
        report = preflight(app.rt, sink, cancel)
        if report["installed"]:
            app.reload()  # newly installed tools bind now
        return {"success": True, **report}

    return app.job("preflight", run)


def install_dependency(app: App, d: dict) -> dict:
    """Install one dependency as a visible job, then reload the tool bindings."""

    def run(jid, sink, cancel) -> dict:
        done = install(app.rt, str(d.get("id", "")), sink, cancel)
        app.reload()
        return {"success": True, **done}

    return app.job("install", run)


TOOL_GET: dict[str, Callable[[App, dict], Any]] = {
    "/api/sanitizer/recipes": lambda app, q: {
        "success": True,
        "recipes": sanitizer.recipes(collect_rules(app.rt)),
    },
    "/api/surveys": survey_reports,
    "/api/survey-report": survey_report,
}
TOOL_POST: dict[str, Callable[[App, dict], Any]] = {
    "/api/preflight": run_preflight,
    "/api/preflight/install": install_dependency,
    "/api/survey": survey_library,
    "/api/repack": repack_workspace,
    "/api/sanitizer/plan": sanitize_handler("plan"),
    "/api/sanitizer/apply": sanitize_handler("apply"),
    "/api/sanitizer/undo": sanitize_handler("undo"),
}
