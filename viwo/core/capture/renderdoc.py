"""capture.gpu backend: RenderDoc (MIT). The game runs under renderdoccmd; the user takes
captures with RenderDoc's in-game hotkey (F12 / PrtScn); every capture is harvested to PNG."""

from __future__ import annotations

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
HELPER = Path(__file__).with_name("rd_harvest.py")


OFFLINE_ENV = {"VIWO_OFFLINE": "1"}  # doc 11.6: the hint runtime agents read; RenderDoc itself
# makes no network use (network = "none")


class RenderDocCapture(Backend):
    backend_id, license, isolation = "renderdoc", "MIT", "subprocess"
    self_check_args = ("--help",)  # renderdoccmd answers; qrenderdoc (rdpython) is never run here
    families = frozenset({"capture"})
    network = "none"  # doc 11.6 declaration: nothing is fetched or reported

    def dependencies(self):
        return (RENDERDOCCMD, RD_PYTHON)

    def capture(self, spec: dict, staging: Path, ctx) -> Outcome:
        """Launch, wait for the game to exit, then harvest every capture into staging."""
        cmd, py = ctx.os.tools.locate(RENDERDOCCMD), ctx.os.tools.locate(RD_PYTHON)
        if cmd is None or py is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=RENDERDOCCMD.hint)
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
        ctx.log(
            f"Launching {Path(spec['exe']).name} under RenderDoc: capture with F12 / PrtScn, "
            "then quit the game",
            stage="capture",
        )
        run = ctx.os.process.run(
            argv + [spec["exe"], *spec.get("args", [])],
            timeout=12 * 3600,
            cancel=ctx.cancel,
            env={**OFFLINE_ENV, **spec.get("env", {})},
        )
        files = sorted(captures.glob("*.rdc"))
        if not files:
            return Outcome(OutcomeKind.FAILED, error=(run.stderr or "no capture was taken")[-300:])
        harvested = self._harvest(py, files, staging, ctx)
        return Outcome(OutcomeKind.OK, harvested, notes=(f"{len(files)} capture(s)",))

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
