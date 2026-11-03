"""decode.rpyc: compiled Ren'Py scripts (.rpyc) back to readable .rpy through unrpyc (MIT),
run as a separate process (pinned source archive in third_party/unrpyc, run by ViWo's Python).
Plugin option `decompile = on|off` (default on) switches the slot.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from viwo.contracts.analysis import AnalysisTarget, Analyzer
from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

UNRPYC = DependencySpec(
    "unrpyc",
    "unrpyc (Ren'Py decompiler)",
    env_var="VIWO_UNRPYC",
    executables=("unrpyc",),
    hint="install unrpyc (MIT) from CensoredUsername/unrpyc to turn .rpyc into .rpy",
)
RPYC_SLOT = SlotDefinition("decode.rpyc", "decode", "renpy", "unrpyc-cli", suffixes=(".rpyc",))
ANALYSIS_SLOT = SlotDefinition("analysis.python", "analysis", "renpy", "unrpyc-analyze")


class UnrpycCli(Decoder):
    backend_id, owner, license, isolation = "unrpyc-cli", "renpy", "MIT", "subprocess"

    def dependencies(self):
        return (UNRPYC,)

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        """unrpyc writes <name>.rpy next to its input: work on a copy inside dest."""
        tool = ctx.os.tools.locate(UNRPYC)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=UNRPYC.hint)
        dest.mkdir(parents=True, exist_ok=True)
        copy = dest / path.name
        shutil.copy2(path, copy)
        argv = [*tool.argv_prefix, "--clobber", "--processes", "1", str(copy)]
        result = ctx.os.process.run(argv, timeout=1800, cancel=ctx.cancel)
        copy.unlink(missing_ok=True)
        out = copy.with_suffix(".rpy")
        if not result.ok or not out.is_file():
            text = (result.stderr or result.stdout).strip()
            return Outcome(OutcomeKind.FAILED, error=text[-300:] or f"exit {result.returncode}")
        return Outcome(OutcomeKind.OK, 1)


class UnrpycAnalyzer(Analyzer):
    """analysis.python (doc 6, A2): every .rpyc of the target in one unrpyc run over the copied
    inputs (unrpyc walks the folder), the .rpy files moved into the output folder."""

    backend_id, owner, license, isolation = "unrpyc-analyze", "renpy", "MIT", "subprocess"
    kinds = ("python_bytecode",)

    def dependencies(self):
        return (UNRPYC,)

    def analyze(self, target: AnalysisTarget, ctx) -> Outcome:
        tool = ctx.os.tools.locate(UNRPYC)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=UNRPYC.hint)
        folder = target.paths[0].parent  # the copies ViWo made (doc 6.5), never the game
        ctx.log(f"unrpyc: decompiling {len(target.paths)} .rpyc file(s)", stage="analyze")
        argv = [*tool.argv_prefix, "--clobber", "--processes", "4", str(folder)]
        result = ctx.os.process.run(argv, timeout=3600, cancel=ctx.cancel)
        done = 0
        for script in sorted(folder.glob("*.rpy")):
            shutil.move(str(script), str(ctx.staging / script.name))
            done += 1
        if not done:
            text = (result.stderr or result.stdout).strip()
            return Outcome(OutcomeKind.FAILED, error=text[-300:] or "unrpyc wrote no .rpy")
        return Outcome(OutcomeKind.OK, done, notes=(f"{done}/{len(target.paths)} scripts",))
