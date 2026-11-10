"""analysis.dotnet, analysis.il2cpp and analysis.script (doc 6, rung A2): managed and bytecode
targets through pinned decompilers, each a separate process reading a copy of the input.
ilspycmd (MIT) writes a C# project, Cpp2IL (MIT) rebuilds stub assemblies from an IL2CPP binary
and its metadata, unluac (MIT, on the pinned JDK) decompiles Lua bytecode. Artifacts land under
`ctx.staging`; the input copies in `ctx.scratch` are ViWo's to move around."""

import shutil
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.analysis import AnalysisTarget, Analyzer
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

from ._process import failed, run_tool
from .ghidra import JDK, java_env

ILSPY = DependencySpec.of("ilspycmd")
CPP2IL = DependencySpec.of("cpp2il")
UNLUAC = DependencySpec.of("unluac")
DOTNET = DependencySpec.of("dotnet")
DEFAULT_TIMEOUT = 3600


def _run(ctx, argv: list[str], env: dict | None):
    return run_tool(ctx, argv, env, DEFAULT_TIMEOUT)


def dotnet_env(ctx) -> dict[str, str] | None:
    """DOTNET_ROOT for framework-dependent tools: the pinned runtime beats a system one."""
    dotnet = ctx.os.tools.locate(DOTNET)
    return {"DOTNET_ROOT": str(Path(dotnet.path).resolve().parent)} if dotnet else None


class IlSpy(Analyzer):
    """Assembly-CSharp.dll (and any .NET assembly) to a C# project, one file per type."""

    backend_id, license, isolation = "ilspycmd", "MIT", "subprocess"
    kinds = ("dotnet_assembly",)

    requires = (ILSPY, DOTNET)

    def analyze(self, target: AnalysisTarget, ctx) -> Outcome:
        if (tool := ctx.os.tools.locate(ILSPY)) is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=ILSPY.hint)
        argv = [*tool.argv_prefix, "-p", "-o", str(ctx.staging), str(target.paths[0])]
        ctx.log(f"ilspycmd: decompiling {target.paths[0].name} into a C# project", stage="analyze")
        result = _run(ctx, argv, dotnet_env(ctx))
        sources = sum(1 for _ in ctx.staging.rglob("*.cs"))
        if result.timed_out or not sources:
            return failed(result, "ilspycmd produced no C# source")
        return Outcome(OutcomeKind.OK, sources, notes=(f"{sources} C# files (project mode)",))


def laid_out(target: AnalysisTarget, folder: Path) -> Path | None:
    """The copied inputs moved where the tool expects them: the target's `layout` (doc 6.1), the
    engine's own folder structure as its plugin declares it. None when the target gives none or
    a place would leave the folder."""
    places = [ws.safe_member(rel) for rel in target.layout]
    if not places or len(places) != len(target.paths) or None in places:
        return None
    for src, rel in zip(target.paths, places):
        dst = folder.joinpath(*rel.parts)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not ws.inside(folder, dst):
            return None
        shutil.move(str(src), str(dst))
    return folder


class Cpp2Il(Analyzer):
    """IL2CPP binary + metadata to stub assemblies (types, methods, fields; no bodies), the
    input every .NET tool expects next."""

    backend_id, license, isolation = "cpp2il", "MIT", "subprocess"
    kinds = ("il2cpp",)
    self_check_args = ("--help",)

    requires = (CPP2IL,)

    def analyze(self, target: AnalysisTarget, ctx) -> Outcome:
        if (tool := ctx.os.tools.locate(CPP2IL)) is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=CPP2IL.hint)
        game = laid_out(target, ctx.scratch / "il2cpp")
        if game is None:
            why = "the il2cpp target gives no layout for its inputs (its plugin's analysis_targets)"
            return Outcome(OutcomeKind.FAILED, error=why)
        argv = [*tool.argv_prefix, "--game-path", str(game), "--output-as", "dummydll"]
        argv += ["--output-to", str(ctx.staging)]
        ctx.log("Cpp2IL: rebuilding stub assemblies from the IL2CPP binary", stage="analyze")
        result = _run(ctx, argv, None)
        dlls = [p for p in ctx.staging.glob("*.dll")]
        if result.timed_out or not dlls:
            return failed(result, "Cpp2IL produced no assemblies")
        note = f"{len(dlls)} stub assemblies (metadata only, no method bodies)"
        return Outcome(OutcomeKind.OK, len(dlls), notes=(note,))


class Unluac(Analyzer):
    """Every Lua bytecode chunk of the target to `<name>.lua`."""

    backend_id, license, isolation = "unluac", "MIT", "subprocess"
    kinds = ("script_vm",)
    self_check_args = ()  # `java -jar unluac.jar` with no file prints the usage

    requires = (UNLUAC, JDK)

    def analyze(self, target: AnalysisTarget, ctx) -> Outcome:
        tool, env = ctx.os.tools.locate(UNLUAC), java_env(ctx)
        if tool is None or env is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=UNLUAC.hint if tool is None else JDK.hint)
        ctx.log(f"unluac: decompiling {len(target.paths)} Lua chunk(s)", stage="analyze")
        done, result = 0, None
        for path in target.paths:
            out = ws.next_free(ctx.staging / f"{path.stem}.lua")  # main.lua + main.luac: both kept
            result = _run(ctx, [*tool.argv_prefix, "--output", str(out), str(path)], env)
            if result.timed_out:
                return failed(result, "unluac timed out")
            done += int(out.is_file() and out.stat().st_size > 0)
        if not done:
            return failed(result, "unluac produced nothing")
        return Outcome(OutcomeKind.OK, done, notes=(f"{done}/{len(target.paths)} chunks",))
