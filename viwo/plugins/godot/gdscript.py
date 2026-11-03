"""analysis.gdscript (doc 6, A2): GDRE Tools decompiles compiled GDScript (.gdc) to .gd text.
GDRE needs the bytecode revision: the `bytecode` option wins, then the engine version the game's
executable carries (the plugin puts it in the target hints), then the revision GDRE lists for
the header number of the files (`GDSC` + uint32)."""

from __future__ import annotations

import re
import struct
from pathlib import Path

from viwo.contracts.analysis import AnalysisTarget, Analyzer
from viwo.contracts.types import Outcome, OutcomeKind

from .pck import GDRE

VERSION = re.compile(rb"\b([34]\.\d{1,2}(?:\.\d{1,2})?)\.stable")
LISTED = re.compile(r"^(\d+\.\d+\.\d+)-\S+ \([0-9a-f]+ / [^/]+ / Bytecode version: (\d+)\)", re.M)
BATCH = 100  # files per GDRE run: keeps the command line far under the Windows limit


def engine_version(exe: Path) -> str:
    """`3.3.2` out of the `3.3.2.stable.official` an exported Godot executable carries."""
    try:
        hit = VERSION.search(exe.read_bytes())
    except OSError:
        return ""
    return hit.group(1).decode() if hit else ""


def _from_header(tool, gdc: Path, ctx) -> str:
    head = gdc.read_bytes()[:8]
    if len(head) < 8 or head[:4] != b"GDSC":
        return ""
    number = struct.unpack_from("<I", head, 4)[0]
    listing = ctx.os.process.run(
        [*tool.argv_prefix, "--headless", "--list-bytecode-versions"], timeout=120
    )
    for version, listed in LISTED.findall(listing.stdout or ""):
        if int(listed) == number:
            return version
    return ""


class GdreDecompile(Analyzer):
    backend_id, owner, license, isolation = "gdre-decompile", "godot", "MIT", "subprocess"
    kinds = ("gdscript_bytecode",)

    def dependencies(self):
        return (GDRE,)

    def analyze(self, target: AnalysisTarget, ctx) -> Outcome:
        tool = ctx.os.tools.locate(GDRE)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=GDRE.hint)
        files = [p for p in target.paths if p.suffix.lower() == ".gdc"]  # the copies (doc 6.5)
        bytecode = str(ctx.options.get("bytecode") or target.hints.get("engine_version", ""))
        bytecode = bytecode or _from_header(tool, files[0], ctx)
        if not bytecode:
            return Outcome(
                OutcomeKind.FAILED,
                error="unknown GDScript bytecode: give the bytecode option (e.g. 4.3.0)",
            )
        ctx.log(f"GDRE Tools: decompiling {len(files)} .gdc file(s) as {bytecode}", stage="analyze")
        result = None
        for start in range(0, len(files), BATCH):
            argv = [*tool.argv_prefix, "--headless", f"--bytecode={bytecode}"]
            argv += [f"--decompile={p}" for p in files[start : start + BATCH]]
            result = ctx.os.process.run(
                argv + [f"--output={ctx.staging}"], timeout=3600, cancel=ctx.cancel
            )
        done = sum(1 for _ in ctx.staging.rglob("*.gd"))
        if not done:
            text = (result.stderr or result.stdout).strip() if result else ""
            return Outcome(OutcomeKind.FAILED, error=text[-300:] or "GDRE wrote no .gd")
        return Outcome(
            OutcomeKind.OK, done, notes=(f"{done}/{len(files)} scripts, bytecode {bytecode}",)
        )
