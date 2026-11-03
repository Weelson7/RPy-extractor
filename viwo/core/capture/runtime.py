"""D3 headless (doc 16.2b, dynamic arm): a memory dump of a running game (the OS layer writes
it: a full minidump on Windows, the readable mappings on Linux) and an API trace through Frida's
frida-trace (wxWindows licence; a separate process, its Python packages pinned), for a set
number of seconds. Both read a running process and write only into the workspace, behind the
`capture` feature switch like the rest of the dynamic arm."""

from __future__ import annotations

import os
import sys
import time
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


def _enabled(rt) -> None:
    if "capture" not in rt.config.features:
        raise ViwoError(
            "refused",
            "the dynamic arm is off",
            hint="add capture to [startup] features (11 SETTINGS)",
        )


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


def _out(workspace: Path, kind: str, pid: int) -> Path:
    return workspace.resolve() / ".runtime" / kind / f"{pid}-{time.strftime('%Y%m%d-%H%M%S')}"


def dump(rt, workspace: Path, pid: int = 0, image: str = "") -> dict:
    _enabled(rt)
    pid = resolve_pid(rt, pid, image)
    out = _out(workspace, "dump", pid)
    try:
        path = rt.os.dump_process(pid, out)
    except OSError as exc:
        raise ViwoError("failed", f"cannot dump process {pid}: {exc}") from exc
    return {"pid": pid, "dump": str(path), "size": path.stat().st_size, "outputDir": str(out)}


def trace(
    rt, workspace: Path, process: tuple[int, str], functions: list[str], seconds: float, cancel=None
) -> dict:
    """frida-trace -p <pid> -i <function>... for `seconds`, its log in the workspace;
    `process` is (pid, image name), either may be empty."""
    _enabled(rt)
    pid = resolve_pid(rt, *process)
    out = _out(workspace, "trace", pid)
    out.mkdir(parents=True, exist_ok=True)
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
    for name in functions:
        argv += ["-i", name]
    env = {
        "PYTHONPATH": os.pathsep.join(
            [str(thirdparty.python_dir(home)), os.environ.get("PYTHONPATH", "")]
        )
    }
    result = rt.os.process.run(argv, cwd=out, timeout=seconds, cancel=cancel, env=env)
    log = out / "trace.log"
    if not log.is_file():
        raise ViwoError(
            "failed", "frida-trace wrote no log", hint=(result.stderr or result.stdout)[-300:]
        )
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"pid": pid, "log": str(log), "events": len(lines), "outputDir": str(out)}


class FridaTrace(Backend):
    """trace.api: owns the Frida dependency so preflight, 05 SYSTEM and `viwo install` see it;
    the run itself is trace() above (frida-trace as a separate process)."""

    backend_id, license, isolation = "frida-trace", "wxWindows-3.1", "subprocess"
    families = frozenset({"trace"})

    def dependencies(self):
        return (FRIDA,)
