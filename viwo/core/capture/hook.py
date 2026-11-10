"""D4 `hook.inject` (doc 11.7): the user's own script in a running game, through the pinned
Frida's own command line (`frida -q -t SECONDS -p PID -l SCRIPT`, wxWindows licence, a separate
process). ViWo writes no loader and ships no hook script: Frida attaches, loads the script and
reloads it whenever the file is saved (its own hot reload); ViWo starts it as a tracked child,
relays every line it prints to the console and keeps them in the workspace. Behind the
`capture` switch like the trace, which attaches the same way."""

from viwo.contracts.errors import ViwoError

from ..steps import tell
from .policy import services_running
from .runtime import FRIDA, RuntimeRequest, _enabled, frida, resolve_pid, run_dir

# Frida detaches by itself after its time, then its process stays for about 30 s on Windows
# with nothing left to do (measured, frida 17.25.2): ViWo stops it this long after the time.
GRACE = 10
REFUSED = "Failed to "  # how Frida's first line starts when it could not attach


class _Stop:
    """Ends the run when the user cancels, or at once when Frida could not attach."""

    def __init__(self, cancel) -> None:
        self.cancel, self.refused = cancel, False

    @property
    def by_user(self) -> bool:
        return self.cancel is not None and self.cancel.cancelled

    @property
    def cancelled(self) -> bool:
        return self.refused or self.by_user


def _script(req: RuntimeRequest):
    if not req.script.is_file():
        raise ViwoError(
            "invalid_request",
            f"no hook script at {req.script}",
            hint="give your own Frida script (JavaScript): --script FILE",
        )
    if req.seconds <= 0:
        raise ViwoError("invalid_request", "give the seconds the script runs (more than 0)")
    return req.script.resolve()


def hook(rt, req: RuntimeRequest, sink=None, cancel=None) -> dict:
    """Frida runs the script in the process for `seconds`; what it printed is in hook.log."""
    _enabled(rt)
    script = _script(req)
    if rt.os.tools.locate(FRIDA) is None:
        raise ViwoError("unavailable", "Frida is not installed", hint=FRIDA.hint)
    pid = resolve_pid(rt, req.pid, req.name)
    out = run_dir(req.workspace, "hook", pid)
    argv, env = frida(rt, "repl")
    argv += ["-q", "-t", f"{req.seconds:g}", "-p", str(pid), "-l", str(script)]
    tell(sink, f"Frida loads {script.name} into process {pid} for {req.seconds:g} s", "hook")
    tell(sink, f"Save {script} while it runs and Frida loads it again", "hook")
    if running := services_running(rt):  # a warning, never a gate (doc 11.1)
        names = ", ".join(running)
        what = "ViWo does not evade it: the hook may be blocked and can get an account banned"
        tell(sink, f"anti-cheat service running now: {names}. {what}", "hook", "warn")
    lines: list[str] = []
    stop = _Stop(cancel)

    def relay(line: str) -> None:  # never silent: every line of the script, as it comes
        stop.refused = stop.refused or (not lines and line.startswith(REFUSED))
        lines.append(line)
        tell(sink, line, "hook")

    result = rt.os.process.run(
        argv, cwd=out, timeout=req.seconds + GRACE, cancel=stop, env=env, on_line=relay
    )
    log = out / "hook.log"
    log.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    if stop.refused or (result.returncode and not result.timed_out):
        hint = "\n".join(lines[-5:]) or "Frida printed nothing"
        raise ViwoError("failed", f"Frida could not run {script.name} in process {pid}", hint=hint)
    tell(sink, f"{len(lines)} line(s) from {script.name}: {log}", "hook")
    done = {"pid": pid, "script": str(script), "log": str(log), "lines": len(lines)}
    return {**done, "stopped": stop.by_user, "outputDir": str(out)}
