"""decode.redscripts (doc 16.0c): Cyberpunk 2077's compiled game scripts (`r6/cache/
final.redscripts`) decompiled into redscript source, one `.script` file per stored file, through
redscript's console (MIT, run as its own process; the 0.5 line is the one with a decompiler)."""

from pathlib import Path

from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

REDSCRIPT = DependencySpec.of("redscript")
SLOT = SlotDefinition(
    "decode.redscripts", "decode", "cyberpunk2077", "redscript-decompile", suffixes=(".redscripts",)
)


class RedscriptDecompile(Decoder):
    backend_id, owner, isolation = "redscript-decompile", "cyberpunk2077", "subprocess"
    license = "MIT"
    requires = (REDSCRIPT,)

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        if (tool := ctx.os.tools.locate(REDSCRIPT)) is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=REDSCRIPT.hint)
        out = dest / path.name.replace(".", "_")
        result = ctx.os.process.run(
            [*tool.argv_prefix, "decompile", "-i", str(path), "-o", str(out), "-f"],
            cwd=str(dest),
            timeout=3600,
            cancel=ctx.cancel,
        )
        files = sum(1 for p in dest.rglob("*.script") if p.is_file())
        if not files:
            said = (result.stderr or result.stdout).strip()[-300:]
            return Outcome(OutcomeKind.FAILED, error=said or "redscript wrote nothing")
        note = f"{path.name}: {files} script file(s) decompiled (redscript)"
        return Outcome(OutcomeKind.OK, files, notes=(note,))
