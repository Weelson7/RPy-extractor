"""decode.redscripts (doc 16.0c): Cyberpunk 2077's compiled game scripts (`r6/cache/
final.redscripts`) decompiled into redscript source, one `.script` file per stored file, through
redscript's console (MIT, run as its own process; the 0.5 line is the one with a decompiler).

The way back (doc 18.3) is the game's modding convention: an edited script goes into the
patched copy as a loose source, `r6/scripts/<its path in the decompiled tree>.reds`, beside
`final.redscripts`, which stays; the redscript compiler installed in the copy compiles it when
the game starts. ViWo does not compile it, and the plan says what the copy needs."""

import shutil
from pathlib import Path, PurePosixPath

from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

REDSCRIPT = DependencySpec.of("redscript")
SLOT = SlotDefinition(
    "decode.redscripts", "decode", "cyberpunk2077", "redscript-decompile", suffixes=(".redscripts",)
)
SCRIPTS = "r6/scripts"  # where redscript reads loose sources, from the game folder
NOTE = (
    "redscript sources under r6/scripts take effect only with the redscript compiler installed "
    "in the patched copy (it compiles them over final.redscripts when the game starts; ViWo "
    "does not compile); a decompiled file that declares again what final.redscripts holds may "
    "be refused by it: its change then goes into an @replaceMethod or @wrapMethod annotation"
)


class RedscriptDecompile(Decoder):
    backend_id, owner, isolation = "redscript-decompile", "cyberpunk2077", "subprocess"
    license = "MIT"
    requires = (REDSCRIPT,)
    encodes, adds, back_note = True, True, NOTE

    def member_back(self, member: str, out: str = "") -> str:
        """`r6/scripts/` and the script's path past the decompiler's own folder, as `.reds`."""
        parts = PurePosixPath(out.replace("\\", "/")).parts
        rest = PurePosixPath(*(parts[1:] or parts or ("decompiled.script",)))
        return f"{SCRIPTS}/{rest.with_suffix('.reds').as_posix()}"

    def encode(self, edited: Path, original: Path, out: Path, ctx) -> Outcome:
        """The edited source as it is (redscript reads UTF-8): nothing to convert."""
        try:
            edited.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{edited.name}: not UTF-8 text ({exc})")
        shutil.copyfile(edited, out)
        return Outcome(OutcomeKind.OK, 1)

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
