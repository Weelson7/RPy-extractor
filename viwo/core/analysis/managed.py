"""analysis.dotnet, analysis.il2cpp and analysis.script (doc 6, rung A2): managed and bytecode
targets through pinned decompilers, each a separate process reading a copy of the input.
ilspycmd (MIT) writes a C# project, Cpp2IL (MIT) rebuilds stub assemblies from an IL2CPP binary
and its metadata, unluac (MIT, on the pinned JDK) decompiles Lua bytecode. Artifacts land under
`ctx.staging`; the input copies in `ctx.scratch` are ViWo's to move around."""

from __future__ import annotations

import shutil
from pathlib import Path

from viwo.contracts.analysis import AnalysisTarget, Analyzer
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

from ._process import failed, run_tool
from .ghidra import JDK, java_env

ILSPY = DependencySpec(
    "ilspycmd",
    "ILSpy command line (ilspycmd)",
    env_var="VIWO_ILSPYCMD",
    executables=("ilspycmd",),
    hint="install ilspycmd (MIT): `viwo install ilspycmd`",
)
CPP2IL = DependencySpec(
    "cpp2il",
    "Cpp2IL (IL2CPP to stub assemblies)",
    env_var="VIWO_CPP2IL",
    executables=("Cpp2IL",),
    hint="install Cpp2IL (MIT): `viwo install cpp2il`",
)
UNLUAC = DependencySpec(
    "unluac",
    "unluac (Lua bytecode decompiler)",
    env_var="VIWO_UNLUAC",
    hint="install unluac (MIT): `viwo install unluac` (it runs on the pinned JDK)",
)
DOTNET = DependencySpec(
    "dotnet",
    ".NET runtime",
    kind="runtime",
    env_var="VIWO_DOTNET",
    executables=("dotnet",),
    hint="install the .NET runtime: `viwo install dotnet`",
)
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
    self_check_args = ("--version",)

    def dependencies(self):
        return (ILSPY, DOTNET)

    def analyze(self, target: AnalysisTarget, ctx) -> Outcome:
        tool = ctx.os.tools.locate(ILSPY)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=ILSPY.hint)
        argv = [*tool.argv_prefix, "-p", "-o", str(ctx.staging), str(target.paths[0])]
        ctx.log(f"ilspycmd: decompiling {target.paths[0].name} into a C# project", stage="analyze")
        result = _run(ctx, argv, dotnet_env(ctx))
        sources = sum(1 for _ in ctx.staging.rglob("*.cs"))
        if result.timed_out or not sources:
            return failed(result, "ilspycmd produced no C# source")
        return Outcome(OutcomeKind.OK, sources, notes=(f"{sources} C# files (project mode)",))


def il2cpp_layout(target: AnalysisTarget, folder: Path) -> Path | None:
    """Cpp2IL wants the game's own layout (`<Game>.exe`, `GameAssembly.dll`,
    `<Game>_Data/il2cpp_data/Metadata/global-metadata.dat`) and reads the Unity version from
    the executable: rebuilt here from the copied inputs, which are ViWo's to move."""
    by_name = {p.name.lower(): p for p in target.paths}
    exe = next((p for p in target.paths if p.suffix.lower() == ".exe"), None)
    assembly, meta = by_name.get("gameassembly.dll"), by_name.get("global-metadata.dat")
    if exe is None or assembly is None or meta is None:
        return None
    metadata = folder / f"{exe.stem}_Data" / "il2cpp_data" / "Metadata"
    metadata.mkdir(parents=True, exist_ok=True)
    for src, dst in (
        (exe, folder / exe.name),
        (assembly, folder / assembly.name),
        (meta, metadata),
    ):
        shutil.move(str(src), str(dst))
    return folder


class Cpp2Il(Analyzer):
    """IL2CPP binary + metadata to stub assemblies (types, methods, fields; no bodies), the
    input every .NET tool expects next."""

    backend_id, license, isolation = "cpp2il", "MIT", "subprocess"
    kinds = ("il2cpp",)
    self_check_args = ("--help",)

    def dependencies(self):
        return (CPP2IL,)

    def analyze(self, target: AnalysisTarget, ctx) -> Outcome:
        tool = ctx.os.tools.locate(CPP2IL)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=CPP2IL.hint)
        game = il2cpp_layout(target, ctx.scratch / "il2cpp")
        if game is None:
            return Outcome(
                OutcomeKind.FAILED,
                error="il2cpp needs GameAssembly.dll, global-metadata.dat and the game executable",
            )
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

    def dependencies(self):
        return (UNLUAC, JDK)

    def analyze(self, target: AnalysisTarget, ctx) -> Outcome:
        tool, env = ctx.os.tools.locate(UNLUAC), java_env(ctx)
        if tool is None or env is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=UNLUAC.hint if tool is None else JDK.hint)
        ctx.log(f"unluac: decompiling {len(target.paths)} Lua chunk(s)", stage="analyze")
        done, result = 0, None
        for path in target.paths:
            out = ctx.staging / f"{path.stem}.lua"
            result = _run(ctx, [*tool.argv_prefix, "--output", str(out), str(path)], env)
            if result.timed_out:
                return failed(result, "unluac timed out")
            done += int(out.is_file() and out.stat().st_size > 0)
        if not done:
            return failed(result, "unluac produced nothing")
        return Outcome(OutcomeKind.OK, done, notes=(f"{done}/{len(target.paths)} chunks",))
