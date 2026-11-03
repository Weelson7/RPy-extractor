"""Server application state: runtime, jobs, active workspace, sort history, activity log."""

from __future__ import annotations

import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Mapping

from viwo.contracts.errors import ViwoError
from viwo.contracts.pipeline import (
    CarveMode,
    ExtractionMode,
    ExtractionRequest,
    MixedPolicy,
    OnExisting,
)
from viwo.core.curation.trash import migrate
from viwo.core.jobs import JobRunner
from viwo.core.pipeline.runner import extract
from viwo.core.wiring.boot import Runtime, boot
from viwo.core.workspace import precheck, workspace_lock


class App:
    def __init__(self, rt: Runtime, ini: Path | None = None) -> None:
        self.rt, self.ini = rt, ini
        self.server = rt.config.server
        self.jobs = JobRunner()
        self.workspace = self.server.workspace
        self.history: list[dict] = []
        self._log: deque[str] = deque(maxlen=2000)
        self._lock = threading.Lock()
        for folder in (
            self.server.logs,
            self.server.temp,
            self.server.workspace,
            self.server.merged,
        ):
            folder.mkdir(parents=True, exist_ok=True)  # a fresh install works out of the box

    def reload(self) -> None:
        """Boot again (after installing a tool) so new tools bind; jobs and workspace stay."""
        self.rt = boot(self.ini)

    def log(self, line: str) -> None:
        stamped = f"[{time.strftime('%H:%M:%S')}] {line}"
        with self._lock:
            self._log.append(stamped)
            path = self.server.logs / f"viwo-{time.strftime('%Y-%m-%d')}.log"
            try:
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(stamped + "\n")
            except OSError:
                pass  # logging must never break a request

    def logs(self) -> list[str]:
        with self._lock:
            return list(self._log)

    def clear_logs(self) -> None:
        with self._lock:
            self._log.clear()

    def set_workspace(self, path: Path) -> None:
        with self._lock:
            if path != self.workspace:
                self.history.clear()  # undo history belongs to one workspace
            self.workspace = path

    def extract(self, payload: dict) -> dict:
        """One extraction as a job; returns the /api/extract response shape (doc 3.5)."""
        request = request_from_payload(payload, str(self.workspace))
        try:  # questions and refusals are answered before any job starts
            precheck(self.workspace, request.on_existing, self.server.workspace)
        except ViwoError as exc:
            return {
                "success": False,
                "error": exc.message,
                "details": exc.hint,
                "code": exc.code,
                "needsDecision": exc.code == "needs_decision",
                "options": ["new", "replace", "cancel"],
            }
        job = self.jobs.submit_with_listener(
            lambda e: self.log(e.legacy_line()),
            "extract",
            lambda jid, s, c: extract(self.rt, request, jid, s, c, self.server.workspace),
            background=False,
        )
        if job.error:
            return {
                "success": False,
                "error": job.error["message"],
                "details": job.error["hint"],
                "code": job.error["code"],
                "needsDecision": job.error["code"] == "needs_decision",
                "options": ["new", "replace", "cancel"],
                "jobId": job.job_id,
            }
        result = job.result.to_legacy_dict()
        self.set_workspace(Path(job.result.workspace))
        return {
            "success": True,
            "result": result,
            "assetPath": job.result.workspace,
            "extractorType": result["extractorType"],
            "detection": result["detection"],
            "jobId": job.job_id,
        }

    def locked(self, fn: Callable[[], dict], folder: Path | None = None) -> dict:
        """A curation call under the workspace lock: busy while a job writes there."""
        target = folder or self.workspace
        try:
            with workspace_lock(target):
                migrate(target)
                return fn()
        except ViwoError as exc:
            return {"success": False, "error": exc.message, "code": exc.code, "hint": exc.hint}

    def locked_job(self, kind: str, folder: Path, fn: Callable[..., dict]) -> dict:
        """fn(sink, cancel) runs as a job under the workspace lock."""

        def run() -> dict:
            job = self.jobs.submit_with_listener(
                lambda e: self.log(e.legacy_line()),
                kind,
                lambda jid, s, c: fn(s, c),
                background=False,
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

        return self.locked(run, folder)


_STATE: dict[str, App] = {}
_GUARD = threading.Lock()


def get_app(ini: Path | None = None) -> App:
    with _GUARD:
        if "app" not in _STATE:
            _STATE["app"] = App(boot(ini), ini)
        return _STATE["app"]


def reset_app(app: App | None = None) -> None:
    """Tests: replace or drop the process-wide app."""
    with _GUARD:
        _STATE.pop("app", None)
        if app is not None:
            _STATE["app"] = app


def request_from_payload(data: Mapping[str, Any], workspace: str = "") -> ExtractionRequest:
    """Map a v1-style /api/extract payload (doc 3.2) onto the request record."""
    raw = str(data.get("extractionType") or "auto").strip().lower()
    exts = data.get("selectedExts")
    selected = frozenset(str(e).lower() for e in exts) if isinstance(exts, list) else None
    plugins = tuple(str(p).strip().lower() for p in data.get("plugins") or ())
    policy = str(data.get("mixedPolicy") or "selected").lower()
    on_existing = str(data.get("onExisting") or "ask").lower()
    carve = str(data.get("carve") or "unknown").lower()
    mode = {"": ExtractionMode.AUTO, "auto": ExtractionMode.AUTO}.get(raw)
    if mode is None:
        mode = ExtractionMode.MIXED if raw == "mixed" else ExtractionMode.SINGLE
        plugins = plugins if raw == "mixed" else (raw,)
    return ExtractionRequest(
        game_path=str(data.get("gamePath", "")),
        workspace=workspace,
        selected_exts=selected or None,
        mode=mode,
        plugins=plugins,
        mixed_policy=MixedPolicy(policy)
        if policy in MixedPolicy._value2member_map_
        else MixedPolicy.SELECTED,
        plugin_options=dict(data.get("pluginOptions") or {}),
        on_existing=OnExisting(on_existing)
        if on_existing in OnExisting._value2member_map_
        else OnExisting.ASK,
        carve=CarveMode(carve) if carve in CarveMode._value2member_map_ else CarveMode.UNKNOWN,
    )
