"""decode.rpyc: compiled Ren'Py scripts (.rpyc) back to readable .rpy through unrpyc (MIT),
run as a separate process (pinned source archive in third_party/unrpyc, run by ViWo's Python).
Plugin option `decompile = on|off` (default on) switches the slot.
"""

from __future__ import annotations

import shutil
from pathlib import Path

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
