"""analysis.protector (doc 6, rung A3): what built and what wraps a binary, before anything
decompiles it. Detect It Easy's console scanner (`diec`, MIT) names the compiler, linker,
libraries, packers and protectors (Themida, VMProtect, Denuvo, UPX...) from its signature
database; ViWo keeps the JSON and writes a one-line-per-finding summary next to it."""

from __future__ import annotations

import json

from viwo.contracts.analysis import AnalysisTarget, Analyzer
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

from ._process import failed, run_tool

DIE = DependencySpec(
    "die",
    "Detect It Easy (diec)",
    env_var="VIWO_DIE",
    executables=("diec",),
    hint="install Detect It Easy (MIT): `viwo install die`",
)
WRAPPERS = ("protector", "packer", "cryptor", "installer", "sfx", "overlay", "dongle", "joiner")
DEFAULT_TIMEOUT = 900


def summarize(report: dict) -> tuple[list[str], list[str]]:
    """(every finding as `type: string`, the wrapper findings alone) out of diec's JSON."""
    lines, wrappers = [], []
    for detect in report.get("detects", []):
        lines.append(f"file: {detect.get('filetype', '?')} ({detect.get('parentfilepart', '')})")
        for value in detect.get("values", []):
            line = value.get("string") or f"{value.get('type')}: {value.get('name')}"
            lines.append(f"  {line}")
            if str(value.get("type", "")).lower() in WRAPPERS:
                wrappers.append(line)
    return lines, wrappers


class DetectItEasy(Analyzer):
    """`diec -j -d <binary>`: identify.json (raw) and identify.txt (one finding per line)."""

    backend_id, license, isolation = "die", "MIT", "subprocess"
    label = "Detect It Easy"
    kinds = ("native_binary", "dotnet_assembly", "il2cpp")

    requires = (DIE,)

    def analyze(self, target: AnalysisTarget, ctx) -> Outcome:
        tool = ctx.os.tools.locate(DIE)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=DIE.hint)
        binary = target.paths[0]
        ctx.log(f"Detect It Easy: identifying {binary.name}", stage="analyze")
        argv = [*tool.argv_prefix, "-j", "-d", str(binary)]
        result = run_tool(ctx, argv, None, DEFAULT_TIMEOUT)
        try:
            report = json.loads(result.stdout or "{}")
        except ValueError:
            report = {}
        if result.timed_out or not report.get("detects"):
            return failed(result, "diec found nothing")
        lines, wrappers = summarize(report)
        (ctx.staging / "identify.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (ctx.staging / "identify.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        note = "; ".join(wrappers) if wrappers else "no packer or protector detected"
        return Outcome(OutcomeKind.OK, len(lines), notes=(note,))
