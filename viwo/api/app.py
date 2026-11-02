"""Server application state: runtime, jobs, active workspace, sort history, activity log."""

from __future__ import annotations

import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

from viwo.contracts.errors import ViwoError
from viwo.contracts.pipeline import ExtractionRequest
from viwo.core.curation.trash import migrate
from viwo.core.jobs import JobRunner
from viwo.core.pipeline.runner import extract
from viwo.core.wiring.boot import Runtime, boot
from viwo.core.workspace import workspace_lock


class App:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self.server = rt.config.server
        self.jobs = JobRunner()
        self.workspace = self.server.workspace
        self.history: list[dict] = []
        self._log: deque[str] = deque(maxlen=2000)
        self._lock = threading.Lock()
        self.server.logs.mkdir(parents=True, exist_ok=True)

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
        request = ExtractionRequest.from_payload(payload, str(self.workspace))
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

    def locked_job(self, kind: str, folder: Path, fn: Callable[[], dict]) -> dict:
        def run() -> dict:
            job = self.jobs.submit_with_listener(
                lambda e: self.log(e.legacy_line()), kind, lambda jid, s, c: fn(), background=False
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
            rt = boot(ini)
            rt.temp_root = rt.config.server.temp
            _STATE["app"] = App(rt)
        return _STATE["app"]


def reset_app(app: App | None = None) -> None:
    """Tests: replace or drop the process-wide app."""
    with _GUARD:
        _STATE.pop("app", None)
        if app is not None:
            _STATE["app"] = app
