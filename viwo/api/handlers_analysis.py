"""12 ANALYSIS (doc 6.6): the targets a game offers, one analyzer run as a job of kind
"analyze", and the "continue in <tool>" handoff (doc 8.3a)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from viwo.contracts.errors import ViwoError
from viwo.core.analysis import (
    AnalysisRequest,
    analyze,
    extras_for,
    handoffs_for,
    open_in,
    slot_for,
    targets_for,
)
from viwo.core.workspace import claim

from .app import App, existing, failure


def _game(d: dict) -> Path | dict:
    return existing(d, "gamePath", "Game folder")


def analysis_targets(app: App, q: dict) -> dict:
    """GET /api/analysis/targets?gamePath=: proposals with their handoffs and analyzer state."""
    game = _game(q)
    if isinstance(game, dict):
        return game
    rt, problems = app.rt, []
    targets = []
    for t in targets_for(rt, game, problems):
        binding = rt.bindings.get(slot_for(t.kind))
        targets.append(
            {
                **t.to_dict(),
                "analyzer": binding.main if binding is not None and binding.bound else "",
                "handoffs": handoffs_for(rt, t.kind),
                "extras": extras_for(rt, t.kind),
            }
        )
    enabled = "analysis" in rt.config.features
    return {"success": True, "targets": targets, "enabled": enabled, "problems": problems}


def _request(app: App, d: dict) -> AnalysisRequest | dict:
    game = _game(d)
    if isinstance(game, dict):
        return game
    key = str(d.get("targetKey", "")).strip()
    if not key:
        return failure(ViwoError("invalid_request", "targetKey is required"))
    options = d.get("options") if isinstance(d.get("options"), dict) else {}
    return AnalysisRequest(game, app.workspace, key, dict(options), str(d.get("slot", "")))


def run_analysis(app: App, d: dict) -> dict:
    """POST /api/analysis/run: the analyzer as a job under the workspace lock."""
    req = _request(app, d)
    if isinstance(req, dict):
        return req
    if not req.workspace.exists() or not any(req.workspace.iterdir()):
        claim(req.workspace)

    def run(sink, cancel) -> dict:
        return {"success": True, **analyze(app.rt, req, sink, cancel)}

    return app.locked_job("analyze", req.workspace, run)


def open_handoff(app: App, d: dict) -> dict:
    """POST /api/analysis/open: prepare and launch the GUI tool (a tracked child)."""
    req = _request(app, d)
    if isinstance(req, dict):
        return req
    return {"success": True, **open_in(app.rt, req, str(d.get("handoff", "")))}


def diff_analyses(app: App, d: dict) -> dict:
    """POST /api/analysis/diff {old, new}: two analysis folders, the report under
    <workspace>/.analysis/diff/<old>--<new>/ (quick: no job)."""
    from viwo.core.analysis import diff

    old, new = Path(str(d.get("old", ""))), Path(str(d.get("new", "")))
    try:
        report = diff.diff(old, new)
    except ViwoError as exc:
        return failure(exc)
    out = diff.write(report, app.workspace / ".analysis" / "diff" / f"{old.name}--{new.name}")
    return {"success": True, "summary": report["summary"], "outputDir": str(out)}


ANALYSIS_GET: dict[str, Callable[[App, dict], Any]] = {"/api/analysis/targets": analysis_targets}
ANALYSIS_POST: dict[str, Callable[[App, dict], Any]] = {
    "/api/analysis/run": run_analysis,
    "/api/analysis/open": open_handoff,
    "/api/analysis/diff": diff_analyses,
}
