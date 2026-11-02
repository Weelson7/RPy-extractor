"""Jobs: background work with an event stream, cancellation and a result (doc 12.3)."""

from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from viwo.contracts.errors import ViwoError
from viwo.contracts.types import CancelToken, ProgressEvent, ProgressSink

_IDS = itertools.count(1)
JobFn = Callable[[str, ProgressSink, CancelToken], Any]


@dataclass
class Job:
    job_id: str
    kind: str
    state: str = "queued"  # queued -> running -> succeeded | failed | cancelled
    events: list[ProgressEvent] = field(default_factory=list)
    result: Any = None
    error: dict | None = None
    cancel: CancelToken = field(default_factory=CancelToken)
    done: threading.Event = field(default_factory=threading.Event)

    def emit(self, event: ProgressEvent) -> None:
        self.events.append(event)

    def summary(self) -> dict:
        return {
            "id": self.job_id,
            "kind": self.kind,
            "state": self.state,
            "events": len(self.events),
            "error": self.error,
        }


class JobRunner:
    def __init__(self, listener: ProgressSink | None = None) -> None:
        self._jobs: dict[str, Job] = {}
        self._listener = listener

    def submit(self, kind: str, fn: JobFn, background: bool = True) -> Job:
        job = Job(f"{time.strftime('%Y%m%d-%H%M%S')}-{next(_IDS):04d}", kind)
        self._jobs[job.job_id] = job
        if background:
            threading.Thread(target=self._run, args=(job, fn), daemon=True).start()
        else:
            self._run(job, fn)
        return job

    def _sink(self, job: Job) -> ProgressSink:
        def sink(event: ProgressEvent) -> None:
            job.emit(event)
            if self._listener:
                self._listener(event)

        return sink

    def _run(self, job: Job, fn: JobFn) -> None:
        job.state = "running"
        try:
            job.result = fn(job.job_id, self._sink(job), job.cancel)
            job.state = "cancelled" if job.cancel.cancelled else "succeeded"
        except ViwoError as exc:
            job.state = "cancelled" if exc.code == "cancelled" else "failed"
            job.error = exc.to_dict()
        except Exception as exc:  # internal errors become a failed job, never a crash
            job.state = "failed"
            job.error = ViwoError("internal", f"{type(exc).__name__}: {exc}").to_dict()
        finally:
            job.done.set()

    def get(self, job_id: str) -> Job:
        if job_id not in self._jobs:
            raise ViwoError("not_found", f"no job {job_id}")
        return self._jobs[job_id]

    def wait(self, job_id: str, timeout: float | None = None) -> Job:
        job = self.get(job_id)
        job.done.wait(timeout)
        return job
