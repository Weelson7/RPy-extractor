"""`[hooks]` (doc 9.5): commands the user writes, run before and after each job.

`before_<kind>`, `after_<kind>`, `before_any` and `after_any` name a command line, run through
the host's shell from the ini's folder. Before a job: `before_any`, then `before_<kind>`; after
it: `after_<kind>`, then `after_any`. The job is told in environment variables (kind, id,
state, error code, workspace, game; never an option, so never a secret). Every line a hook
prints is an event of the job (`[HOOKS:<KEY>]`); a hook that fails, is missing or outlives
`timeout` (killed then) is a warning, never a failure of the job.
"""

from dataclasses import dataclass, field
from pathlib import Path

from viwo.contracts.types import ProgressEvent

KINDS = (  # every job kind the runner knows (doc 12.3)
    "extract survey repack patch mod preflight install capture dump trace hook profile agent "
    "record analyze cleanup merge indexes"
).split()
TIMEOUT = 60.0  # seconds, `[hooks] timeout`; 0 = no limit
NOT_FOUND = {9009: "cmd", 127: "sh"}  # the shell's code for a command it cannot find


def valid_key(key: str) -> bool:
    phase, _, kind = key.partition("_")
    return phase in ("before", "after") and (kind == "any" or kind in KINDS)


@dataclass
class Hooks:
    commands: dict[str, str] = field(default_factory=dict)  # "before_extract" -> command line
    timeout: float = TIMEOUT
    cwd: Path | None = None
    process: object = None  # the OS layer's ProcessRunner

    @classmethod
    def of(cls, rt) -> "Hooks | None":
        """The runtime's hooks; None when the ini names none."""
        config = rt.config
        if not getattr(config, "hooks", None):
            return None
        folder = config.path.parent if config.path is not None else None
        return cls(dict(config.hooks), config.hook_timeout, folder, rt.os.process)

    def keys(self, phase: str, kind: str) -> list[str]:
        order = ["before_any", f"before_{kind}"] if phase == "before" else []
        order = order or [f"after_{kind}", "after_any"]
        return [key for key in order if self.commands.get(key, "").strip()]

    def fire(self, phase: str, job, sink, cancel=None) -> None:
        """Run the hooks of `phase` for `job` (a Job: kind, id, state, error, where)."""
        for key in self.keys(phase, job.kind):
            try:
                self._run(key, job, sink, cancel)
            except Exception as exc:  # noqa: BLE001  (a hook never breaks its job)
                _say(sink, key, f"hook not run: {type(exc).__name__}: {exc}", "warn")

    def _run(self, key: str, job, sink, cancel) -> None:
        command, process = self.commands[key], self.process
        _say(sink, key, f"running: {command}")
        result = process.run(
            process.shell_command(command),
            cwd=self.cwd,
            timeout=self.timeout or None,
            cancel=cancel,
            env=environment(key, job),
            on_line=lambda line: _say(sink, key, line),
        )
        if result.timed_out:
            why = f"stopped after {self.timeout:g} s ([hooks] timeout)"
            if cancel is not None and cancel.cancelled:
                why = "stopped: the job was cancelled"
            _say(sink, key, f"hook {why}; the job goes on", "warn")
        elif result.returncode in NOT_FOUND:
            _say(sink, key, f"command not found ({result.returncode}); the job goes on", "warn")
        elif result.returncode:
            _say(sink, key, f"hook exited with {result.returncode}; the job goes on", "warn")


def environment(key: str, job) -> dict[str, str]:
    where = getattr(job, "where", {}) or {}
    error = (job.error or {}).get("code", "") if isinstance(job.error, dict) else ""
    return {
        "VIWO_HOOK": key,
        "VIWO_JOB_ID": job.job_id,
        "VIWO_JOB_KIND": job.kind,
        "VIWO_JOB_STATE": job.state,
        "VIWO_JOB_ERROR": error,
        "VIWO_WORKSPACE": str(where.get("workspace") or ""),
        "VIWO_GAME": str(where.get("game") or ""),
    }


def _say(sink, key: str, message: str, level: str = "info") -> None:
    if sink is not None:
        sink(ProgressEvent(message, level, "hooks", key))
