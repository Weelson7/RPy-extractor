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
    created: float = field(default_factory=time.time)  # JobHandle (doc 12.3)
    started: float = 0.0  # when the function began running (0 while queued)
    finished: float = 0.0

    def emit(self, event: ProgressEvent) -> None:
        self.events.append(event)

    def summary(self) -> dict:
        """JobHandle {id, kind, state, created, started, finished} plus counts (doc 12.3)."""
        begun = self.started or self.created
        return {
            "id": self.job_id,
            "kind": self.kind,
            "state": self.state,
            "events": len(self.events),
            "error": self.error,
            "created": self.created,
            "started": begun,
            "finished": self.finished or None,
            "elapsed": round((self.finished or time.time()) - begun, 2),
        }


KEEP = 200  # finished jobs kept in memory


class JobRunner:
    def __init__(self, listener: ProgressSink | None = None) -> None:
        self._jobs: dict[str, Job] = {}
        self._listener = listener

    def submit(self, kind: str, fn: JobFn, background: bool = True) -> Job:
        return self.submit_with_listener(self._listener, kind, fn, background)

    def submit_with_listener(
        self, listener: ProgressSink | None, kind: str, fn: JobFn, background: bool = True
    ) -> Job:
        job = Job(f"{time.strftime('%Y%m%d-%H%M%S')}-{next(_IDS):04d}", kind)
        self._forget_old()
        self._jobs[job.job_id] = job
        if background:
            threading.Thread(target=self._run, args=(job, fn, listener), daemon=True).start()
        else:
            self._run(job, fn, listener)
        return job

    def _forget_old(self) -> None:
        """A long-running server keeps the last KEEP finished jobs (their run records stay on
        disk); running jobs are never dropped."""
        finished = [j for j in self._jobs.values() if j.done.is_set()]
        for job in finished[: max(0, len(finished) - KEEP + 1)]:  # room for the new one
            self._jobs.pop(job.job_id, None)

    def list(self) -> list[Job]:
        return list(self._jobs.values())

    @staticmethod
    def _sink(job: Job, listener: ProgressSink | None) -> ProgressSink:
        def sink(event: ProgressEvent) -> None:
            job.emit(event)
            if listener:
                listener(event)

        return sink

    def _run(self, job: Job, fn: JobFn, listener: ProgressSink | None = None) -> None:
        job.state, job.started = "running", time.time()
        try:
            job.result = fn(job.job_id, self._sink(job, listener), job.cancel)
            job.state = "cancelled" if job.cancel.cancelled else "succeeded"
        except ViwoError as exc:
            job.state = "cancelled" if exc.code == "cancelled" else "failed"
            job.error = exc.to_dict()
        except Exception as exc:  # internal errors become a failed job, never a crash
            job.state = "failed"
            job.error = ViwoError("internal", f"{type(exc).__name__}: {exc}").to_dict()
        finally:
            job.finished = time.time()
            job.done.set()

    def get(self, job_id: str) -> Job:
        if job_id not in self._jobs:
            raise ViwoError("not_found", f"no job {job_id}")
        return self._jobs[job_id]

    def wait(self, job_id: str, timeout: float | None = None) -> Job:
        job = self.get(job_id)
        job.done.wait(timeout)
        return job
