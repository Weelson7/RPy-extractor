"""The workflow recorder (doc 19.3): one recording at a time, held by the App. The action routes
are wrapped once, so a success in any view adds a step while the recording runs and is not
paused; `stop` saves it as the user's runbook, its steps carrying what they answered."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from viwo.contracts.errors import ViwoError
from viwo.core import guides, runbooks, workflows

from .app import App, failure, safe
from .handlers_jobs import KINDS

ROUTES = {  # action route -> (job kind, the parameters the route itself implies)
    "/api/extract": ("extract", {}),
    "/api/survey": ("survey", {}),
    "/api/repack": ("repack", {}),
    "/api/patch": ("patch", {}),
    "/api/mod": ("mod", {}),
    "/api/capture": ("capture", {}),
    "/api/analysis/run": ("analyze", {}),
    **{f"/api/sanitizer/{op}": ("cleanup", {"op": op}) for op in ("plan", "apply", "undo")},
    **{f"/api/runtime/{k}": (k, {}) for k in ("dump", "trace", "profile", "agent", "record")},
}


@dataclass
class Recording:
    title: str
    game: str
    paused: bool = False
    steps: list[dict] = field(default_factory=list)
    answers: list[dict | None] = field(default_factory=list)  # per step: what it answered
    inputs: list[dict] = field(default_factory=list)  # secret inputs, a process id
    warnings: list[str] = field(default_factory=list)
    running: int = 0  # actions started while recording that have not answered yet

    def view(self) -> dict:
        shown = [{"title": s["title"], "do": s.get("do", "")} for s in self.steps]
        head = {"title": self.title, "game": self.game, "paused": self.paused, "steps": shown}
        return {**head, "running": self.running, "warnings": list(self.warnings)}

    def add(self, step: dict, answer: dict | None) -> None:  # under LOCK
        self.steps.append(step)
        self.answers.append(answer)


LOCK = threading.Lock()  # the recorder's state: request threads start, stop and add at once


def wrap(post: dict[str, Callable[[App, dict], Any]]) -> None:
    """Every action route records its successes while a recording runs (once: a route already
    wrapped is left as it is)."""
    for route, (kind, implied) in ROUTES.items():
        if route in post and not getattr(post[route], "recorded", False):
            post[route] = _recorded(kind, implied, post[route])


def _recorded(kind: str, implied: dict, handler):
    def run(app: App, d: dict):
        with LOCK:  # taken when the action starts: a pause or stop meanwhile counts
            rec = app.recording
            live = rec is not None and not rec.paused
            if live:
                rec.running += 1
        step = answer = None
        try:
            answer = handler(app, d)
            if live and isinstance(answer, dict) and answer.get("success"):
                seen = {"game": rec.game, "workspace": str(app.workspace)}  # after the action
                step = workflows.record_step(app.rt, kind, {**d, **implied}, answer, seen, rec)
        finally:
            if live:
                with LOCK:  # added before it stops counting: a stop never saves without it
                    if step is not None:
                        _foreign_game(rec, step)
                        rec.add(step, answer)
                    rec.running -= 1
        return answer

    run.recorded = True
    return run


def _foreign_game(rec: Recording, step: dict) -> None:
    """A step naming another game folder than the recording's is kept, and said."""
    for key in ("gamePath", "folder"):
        value = step["with"].get(key)
        if isinstance(value, str) and value and not value.startswith("{game}"):
            number = len(rec.steps) + 1
            rec.warnings.append(f"step {number} ({step['title']}) names another game: {value}")


def _running(app: App) -> Recording:
    if app.recording is None:
        raise ViwoError("invalid_request", "no recording runs", hint="start one first")
    return app.recording


def _start(app: App, d: dict) -> dict:
    if app.recording is not None:
        raise ViwoError("refused", f"recording {app.recording.title!r} runs: stop or discard it")
    title, game = str(d.get("title") or "").strip(), str(d.get("game") or "").strip()
    if not title:
        raise ViwoError("invalid_request", "give the workflow a title")
    if not game:  # without it nothing recorded could become {game}: no replay would match
        raise ViwoError("invalid_request", "pick the game first (the top bar's GAME)")
    app.recording = Recording(title, game)
    return {}


def _note(app: App, d: dict) -> dict:
    title, text = str(d.get("title") or "").strip(), str(d.get("text") or "").strip()
    if not (title and text):
        raise ViwoError("invalid_request", "a step you do needs a title and a text")
    _running(app).add({"title": title, "text": text, "workbook": ""}, None)
    return {}


def _stop(app: App, d: dict) -> dict:
    rec = _running(app)
    if rec.running:  # its step would be lost: never silently
        raise ViwoError("busy", f"{rec.running} recorded action(s) still running: stop when done")
    if not rec.steps:
        raise ViwoError("invalid_request", "nothing recorded yet: run an action, or discard")
    taken = {b["id"] for b in runbooks.load(app.rt, KINDS)[0]} | guides.file_ids(
        app.rt, runbooks.KIND
    )  # a broken file of the user's holding an id is never overwritten
    base = re.sub(r"[^a-z0-9]+", "-", rec.title.lower()).strip("-") or "workflow"
    free = next(i for i in (base, *(f"{base}-{n}" for n in range(2, 999))) if i not in taken)
    when = time.strftime("%Y-%m-%d %H:%M")
    game = Path(rec.game).name if rec.game else "no game"  # a shared workflow names no user path
    summary = f"Recorded {when} on {game}: a replay stops where an answer differs."
    book = {"id": free, "title": rec.title, "summary": summary, "inputs": rec.inputs}
    path = runbooks.save(app.rt, KINDS, {**book, "steps": rec.steps})
    app.recording = None
    return {"saved": free, "path": str(path), "warnings": rec.warnings}


def _set_paused(paused: bool):
    def act(app: App, d: dict) -> dict:
        _running(app).paused = paused
        return {}

    return act


def _discard(app: App, d: dict) -> dict:
    _running(app)
    app.recording = None
    return {}


ACTIONS = {"start": _start, "pause": _set_paused(True), "continue": _set_paused(False),
           "note": _note, "stop": _stop, "discard": _discard}  # fmt: skip


def recording_get(app: App, q: dict) -> dict:
    """GET /api/recording: the recording that runs, or null."""
    rec = app.recording
    return {"success": True, "recording": rec.view() if rec is not None else None}


def recording_post(app: App, d: dict) -> dict:
    """POST /api/recording {action: start|pause|continue|note|stop|discard, ...}."""
    act = ACTIONS.get(str(d.get("action", "")))
    if act is None:
        return failure(ViwoError("invalid_request", f"action: one of {', '.join(ACTIONS)}"))

    def locked() -> dict:  # one at a time: two starts never both win, a stop sees every add
        with LOCK:
            return {"success": True, **act(app, d), **recording_get(app, {})}

    return safe(locked)


def install(get: dict, post: dict) -> None:
    """The guide routes of doc 19 (runbooks, the recorder) into the route tables, then every
    action route wrapped to record (after the tables are complete)."""
    from .handlers_runbooks import RUNBOOKS_GET, RUNBOOKS_POST

    get.update({**RUNBOOKS_GET, "/api/recording": recording_get})
    post.update({**RUNBOOKS_POST, "/api/recording": recording_post})
    wrap(post)
