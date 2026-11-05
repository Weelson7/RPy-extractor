"""Handlers for the platform tools: survey (+ saved reports), sanitizer (as the "cleanup"
job), round trip (repack), preflight and installs."""

from pathlib import Path
from typing import Any, Callable

from viwo.contracts.errors import ViwoError
from viwo.core import sanitizer, surveys
from viwo.core.preflight import install, preflight
from viwo.core.roundtrip import repack
from viwo.core.sanitizer_rules import collect_rules
from viwo.core.steps import tell
from viwo.core.survey import survey

from .app import App, existing, failure, path_param, safe


def survey_library(app: App, d: dict) -> dict:
    """Read-only coverage survey of a game folder or library, as a job (events per game)."""
    if isinstance(folder := existing(d, "folder", "Folder"), dict):
        return folder

    reports, deep = _reports_dir(app), bool(d.get("deep"))

    def run(jid, sink, cancel) -> dict:
        def note(game: Path, index: int, total: int) -> None:
            tell(sink, f"Surveying {game.name} ({index}/{total})", "survey")

        games = survey(app.rt, folder, deep, note, cancel, sink)
        saved = surveys.save(reports, folder, deep, games)
        tell(sink, f"Report saved: {saved['path']}", "report")
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
    reports = _reports_dir(app)
    return safe(lambda: {"success": True, "report": surveys.load(reports, q.get("id", ""))})


def sanitize_handler(op: str) -> Callable[[App, dict], dict]:
    def handler(app: App, d: dict) -> dict:
        folder = app.workspace  # read once: the workspace can be switched meanwhile

        def run(sink, cancel) -> dict:  # a "cleanup" job: visible in JOBS and the chips
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

        return app.locked_job("cleanup", folder, run, writes=op != "plan")

    return handler


def repack_workspace(app: App, d: dict) -> dict:
    """Round trip of the active workspace: plan (plan=true) or build a patched copy (job)."""
    folder = app.workspace
    if d.get("plan"):
        return app.locked(
            lambda: {"success": True, **repack(app.rt, folder, None, apply=False)}, folder, False
        )
    out = path_param(d, "out")  # absolute only (doc 4.1 rule 6): never the server's own folder
    if out is None:
        return failure(
            ViwoError("invalid_request", "Choose an absolute target folder for the patched copy")
        )

    def run(sink, cancel) -> dict:
        return {"success": True, **repack(app.rt, folder, out, sink, cancel)}

    return app.locked_job("repack", folder, run, writes=False)


def apply_patch_set(app: App, d: dict) -> dict:
    """POST /api/patch {gamePath, patchSet, out, plan}: check (plan) or apply a T1 patch set
    into a patched copy (job kind patch)."""
    from viwo.core import patchsets

    game, set_path = (
        existing(d, "gamePath", "Game folder"),
        existing(d, "patchSet", "Patch set", False),
    )
    for given in (game, set_path):
        if isinstance(given, dict):
            return given
    out = path_param(d, "out")
    if str(d.get("out") or "").strip() and out is None:
        return failure(ViwoError("invalid_request", "out must be an absolute folder"))
    if d.get("plan") or out is None:
        return safe(
            lambda: {"success": True, **patchsets.plan(game, patchsets.load(set_path), app.rt.os)}
        )

    def run(sink, cancel) -> dict:
        return {"success": True, **patchsets.apply(app.rt, game, set_path, out, sink)}

    return app.locked_job("patch", out, run)


def mod_package(app: App, d: dict) -> dict:
    """POST /api/mod {action: pack|check|apply, gamePath, mod, copy, name}: T2 mod packages
    (pack and apply run as job kind mod)."""
    from viwo.core import mods

    action, game = str(d.get("action", "")), existing(d, "gamePath", "Game folder")
    if action not in ("pack", "check", "apply"):
        return failure(ViwoError("invalid_request", "give action pack|check|apply"))
    if isinstance(game, dict):
        return game
    listed = d.get("mods") if isinstance(d.get("mods"), list) else [d.get("mod", "")]
    mod_list = [p for p in (path_param({"m": m}, "m") for m in listed) if p is not None]
    if not mod_list:
        return failure(ViwoError("invalid_request", "give the mod zip as an absolute path"))
    mod, copy = mod_list[0], path_param(d, "copy")
    if action == "check":
        return safe(lambda: {"success": True, **mods.check(game, mod)})

    if copy is None:  # pack reads it, apply writes it: never the server's own folder
        return failure(ViwoError("invalid_request", f"mod {action} needs copy, an absolute folder"))

    def run(sink, cancel) -> dict:
        if action == "pack":
            return {"success": True, **mods.pack(game, copy, mod, str(d.get("name", "")))}
        return {"success": True, **mods.apply(app.rt, game, mod_list, copy, sink)}

    return app.locked_job("mod", copy, run)


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
    "/api/patch": apply_patch_set,
    "/api/mod": mod_package,
    "/api/sanitizer/plan": sanitize_handler("plan"),
    "/api/sanitizer/apply": sanitize_handler("apply"),
    "/api/sanitizer/undo": sanitize_handler("undo"),
}
