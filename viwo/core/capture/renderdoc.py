"""capture.gpu backend: RenderDoc (MIT). The game runs under renderdoccmd; the user takes
captures with RenderDoc's in-game hotkey (F12 / PrtScn); every capture is harvested to PNG."""

from __future__ import annotations

import json
from pathlib import Path

from viwo.contracts.slots import Backend
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

RENDERDOCCMD = DependencySpec(
    "renderdoccmd",
    "renderdoccmd",
    env_var="VIWO_RENDERDOCCMD",
    executables=("renderdoccmd",),
    install_dirs=("RenderDoc",),
    hint="install RenderDoc (MIT) for runtime capture",
)
RD_PYTHON = DependencySpec(
    "rdpython",
    "Python with RenderDoc's module",
    env_var="VIWO_RDPYTHON",
    hint="set [tools] rdpython = the Python that can import RenderDoc's renderdoc module",
)
# outside the package: next to this module, `import renderdoc` would find ViWo's own module
SCRIPTS = Path(__file__).resolve().parent.parent.parent / "data" / "renderdoc"
HELPER, TRIGGER = SCRIPTS / "rd_harvest.py", SCRIPTS / "rd_trigger.py"


OFFLINE_ENV = {"VIWO_OFFLINE": "1"}  # doc 11.6: the hint runtime agents read; RenderDoc itself
# makes no network use (network = "none")


def ui_config(host) -> Path:
    """qrenderdoc keeps UI.config under the roaming config home on Windows and under the Qt
    data home (~/.local/share) on Linux."""
    base = host.config_home() if host.os_id == "windows" else host.data_home()
    return base / "qrenderdoc" / "UI.config"


def quiet_ui(host) -> str:
    """Answer qrenderdoc's first-run prompts (analytics, tips, update check) once: they are
    modal and would block `qrenderdoc --py` forever in an unattended run. A choice the user
    already made about analytics or update checks is kept."""
    path = ui_config(host)
    try:
        cfg = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        if not cfg.get("Analytics_ManualCheck"):
            cfg["Analytics_ManualCheck"] = cfg["Analytics_TotalOptOut"] = True
        cfg["Tips_HasSeenFirst"] = True
        cfg.setdefault("CheckUpdate_AllowChecks", False)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
    except (OSError, ValueError) as exc:
        return f"RenderDoc's first-run answers not written ({exc}): a prompt may block it"
    return ""


class RenderDocCapture(Backend):
    backend_id, license, isolation = "renderdoc", "MIT", "subprocess"
    self_check_args = ("--help",)  # renderdoccmd answers; qrenderdoc (rdpython) is never run here
    families = frozenset({"capture"})
    network = "none"  # doc 11.6 declaration: nothing is fetched or reported

    requires = (RENDERDOCCMD, RD_PYTHON)

    def capture(self, spec: dict, staging: Path, ctx) -> Outcome:
        """Launch, wait for the game to exit, then harvest every capture into staging."""
        cmd, py = ctx.os.tools.locate(RENDERDOCCMD), ctx.os.tools.locate(RD_PYTHON)
        if cmd is None or py is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=RENDERDOCCMD.hint)
        problem = quiet_ui(ctx.os)
        if problem:
            ctx.log(problem, "warn", "capture")
        captures = staging.parent / "captures"
        captures.mkdir(parents=True, exist_ok=True)
        argv = [
            *cmd.argv_prefix,
            "capture",
            "-w",
            "-d",
            spec["workdir"],
            "-c",
            str(captures / "viwo"),
        ]
        argv += [spec["exe"], *spec.get("args", [])]
        env = {**OFFLINE_ENV, **spec.get("env", {})}
        after = float(spec.get("capture_after") or 0)
        if after > 0:
            error = self._auto(argv, env, after, py, ctx, Path(spec["exe"]).name)
        else:
            ctx.log(
                f"Launching {Path(spec['exe']).name} under RenderDoc: capture with F12 / PrtScn, "
                "then quit the game",
                stage="capture",
            )
            run = ctx.os.process.run(argv, timeout=12 * 3600, cancel=ctx.cancel, env=env)
            error = (run.stderr or "no capture was taken")[-300:]
        files = sorted(captures.glob("*.rdc"))
        if not files:
            return Outcome(OutcomeKind.FAILED, error=error)
        harvested = self._harvest(py, files, staging, ctx)
        return Outcome(OutcomeKind.OK, harvested, notes=(f"{len(files)} capture(s)",))

    @staticmethod
    def _auto(argv: list[str], env: dict, after: float, py, ctx, exe: str) -> str:
        """Unattended: the game runs as a tracked child, the trigger helper asks RenderDoc for
        one frame after `after` seconds, then the child is stopped (tree kill)."""
        ctx.log(
            f"Launching {exe} under RenderDoc; one frame captured after {after:.0f} s",
            stage="capture",
        )
        child = ctx.os.process.launch(argv, env=env)
        try:
            done = ctx.os.process.run(
                [*py.argv_prefix, str(TRIGGER), str(after), str(after + 120)],
                timeout=after + 180,
                cancel=ctx.cancel,
                env={"VIWO_RD_DELAY": str(after), "VIWO_RD_TIMEOUT": str(after + 120)},
            )
        finally:
            child.kill()
        ctx.log(f"Trigger helper exit {done.returncode}; stopped {exe}", stage="capture")
        return (done.stderr or done.stdout or "the trigger helper took no capture")[-300:]

    @staticmethod
    def _harvest(py, files: list[Path], staging: Path, ctx) -> int:
        """Every capture through the harvest helper; returns the PNG count."""
        harvested = 0
        for rdc in files:
            out = staging / rdc.stem
            done = ctx.os.process.run(
                [*py.argv_prefix, str(HELPER), str(rdc), str(out)],
                timeout=3600,
                cancel=ctx.cancel,
                env={"VIWO_RD_CAPTURE": str(rdc), "VIWO_RD_OUT": str(out)},
            )
            harvested += sum(1 for _ in out.glob("*.png")) if done.ok else 0
            ctx.log(f"Harvested {rdc.name}: {'ok' if done.ok else 'failed'}", stage="harvest")
        return harvested
