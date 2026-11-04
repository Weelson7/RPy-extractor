"""D3 headless (doc 16.2b, dynamic arm): a memory dump of a running game (the OS layer writes
it: a full minidump on Windows, the readable mappings on Linux) and an API trace through Frida's
frida-trace (wxWindows licence; a separate process, its Python packages pinned), for a set
number of seconds. Both read a running process and write only into the workspace, behind the
`capture` feature switch like the rest of the dynamic arm. `run` is the one dispatch the CLI
(`viwo dump|trace|record|agent`) and the API (POST /api/runtime/<kind>) share."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.slots import Backend
from viwo.contracts.types import DependencySpec

from .. import thirdparty

FRIDA = DependencySpec(
    "frida-tools",
    "Frida (frida-trace)",
    kind="python",
    import_name="frida_tools",
    hint="install Frida: `viwo install frida-tools` (and `frida`)",
)


@dataclass(frozen=True)
class RuntimeRequest:
    """One headless dynamic run; each kind reads the fields it needs (dump and trace: pid or
    name; trace and record: seconds; agent: game, exe, copy, timeout)."""

    workspace: Path
    pid: int = 0
    name: str = ""
    functions: tuple[str, ...] = ("CreateFileW",)
    seconds: float = 10
    game: Path = Path()
    exe: Path = Path()
    copy: Path | None = None  # the agent's patched copy (default: beside the workspace)
    timeout: float = 600


def run(rt, kind: str, req: RuntimeRequest, sink=None, cancel=None) -> dict:
    from .agents import run_agent
    from .audio import record

    runs = {
        "dump": lambda: dump(rt, req.workspace, req.pid, req.name),
        "trace": lambda: trace(rt, req, cancel),
        "agent": lambda: run_agent(rt, req, sink, cancel),
        "record": lambda: record(rt, req.workspace, req.seconds),
    }
    return runs[kind]()


def _enabled(rt) -> None:
    if "capture" not in rt.config.features:
        raise ViwoError(
            "refused",
            "the dynamic arm is off",
            hint="add capture to [startup] features (11 SETTINGS)",
        )


def runtime_dir(workspace: Path, *parts: str) -> Path:
    """`<workspace>/.runtime/<parts>`, made: where every dynamic run writes its files."""
    out = workspace.resolve().joinpath(".runtime", *parts)
    out.mkdir(parents=True, exist_ok=True)
    return out


def stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def resolve_pid(rt, pid: int = 0, image: str = "") -> int:
    if pid:
        return pid
    found = rt.os.pids_of(image) if image else []
    if len(found) != 1:
        raise ViwoError(
            "not_found" if not found else "needs_decision",
            f"{len(found)} running process(es) named {image!r}",
            hint="give --pid",
        )
    return found[0]


def dump(rt, workspace: Path, pid: int = 0, image: str = "") -> dict:
    _enabled(rt)
    pid = resolve_pid(rt, pid, image)
    out = runtime_dir(workspace, "dump", f"{pid}-{stamp()}")
    try:
        path = rt.os.dump_process(pid, out)
    except OSError as exc:
        raise ViwoError("failed", f"cannot dump process {pid}: {exc}") from exc
    return {"pid": pid, "dump": str(path), "size": path.stat().st_size, "outputDir": str(out)}


def trace(rt, req: RuntimeRequest, cancel=None) -> dict:
    """frida-trace -p <pid> -i <function>... for `seconds`, its log in the workspace."""
    _enabled(rt)
    pid = resolve_pid(rt, req.pid, req.name)
    out = runtime_dir(req.workspace, "trace", f"{pid}-{stamp()}")
    home = thirdparty.home_of(rt.config)
    argv = [
        sys.executable,
        "-m",
        "frida_tools.tracer",
        "-p",
        str(pid),
        "-o",
        str(out / "trace.log"),
    ]
    for name in req.functions:
        argv += ["-i", name]
    env = {
        "PYTHONPATH": os.pathsep.join(
            [str(thirdparty.python_dir(home)), os.environ.get("PYTHONPATH", "")]
        )
    }
    result = rt.os.process.run(argv, cwd=out, timeout=req.seconds, cancel=cancel, env=env)
    log = out / "trace.log"
    if not log.is_file():
        raise ViwoError(
            "failed", "frida-trace wrote no log", hint=(result.stderr or result.stdout)[-300:]
        )
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"pid": pid, "log": str(log), "events": len(lines), "outputDir": str(out)}


class FridaTrace(Backend):
    """Owns the Frida dependency so preflight, 05 SYSTEM and `viwo install` see it. It serves no
    slot: trace() above is the one way to run frida-trace (a separate process); there is no
    other tracer to bind or fail over to."""

    backend_id, license, isolation = "frida-trace", "wxWindows-3.1", "subprocess"

    requires = (FRIDA,)
