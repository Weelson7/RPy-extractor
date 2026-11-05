"""analysis.native main: Ghidra headless (Apache-2.0) with ViWo's export script, and the
"Continue in Ghidra" handoff that opens the same project in the GUI (doc 6.4, 8.3a)."""

import os
from pathlib import Path

from viwo.contracts.analysis import AnalysisTarget, Analyzer, Handoff, LaunchSpec
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

from ._process import failed, run_tool

GHIDRA = DependencySpec(
    "ghidra",
    "Ghidra (analyzeHeadless)",
    env_var="VIWO_GHIDRA",
    executables=("analyzeHeadless",),
    install_dirs=("ghidra",),
    hint="install Ghidra (Apache-2.0): `viwo install ghidra` (with the JDK it needs)",
)
JDK = DependencySpec(
    "jdk",
    "Java runtime for Ghidra (Temurin 25)",
    kind="runtime",
    env_var="VIWO_JDK",
    executables=("java",),
    hint="install the JDK: `viwo install jdk`",
)
SCRIPTS = Path(__file__).resolve().parents[2] / "data" / "ghidra"
PROJECT = "viwo"  # project name inside project_dir()
ARTIFACTS = ("functions.csv", "decompiled.c", "strings.txt", "symbols.tsv")
DEFAULT_TIMEOUT = 4 * 3600


def java_env(ctx) -> dict[str, str] | None:
    """JAVA_HOME and PATH for Ghidra's launchers, from the pinned (or found) JDK."""
    if (java := ctx.os.tools.locate(JDK)) is None:
        return None
    home = Path(java.path).resolve().parent.parent
    path = f"{home / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"
    env = {"JAVA_HOME": str(home), "PATH": path}
    if not ({"GHIDRA_MAXMEM", "GHIDRA_HEADLESS_MAXMEM"} & set(os.environ)):  # the user's wins
        memory = getattr(ctx.os, "memory_bytes", lambda: 0)()  # unknown: Ghidra's own 2 GB
        env["GHIDRA_HEADLESS_MAXMEM"] = heap(memory)
    return env


def heap(memory: int) -> str:
    """Headless Ghidra's heap: half the machine's memory, 2 to 16 GB (its own default, 2 GB,
    runs out on a large game executable)."""
    gigabytes = memory // (2 << 30) if memory else 2
    return f"{max(2, min(16, gigabytes))}G"


def project_dir(staging: Path) -> Path:
    """Ghidra refuses any path element starting with a dot, so the project cannot live under
    `.analysis/`: it goes beside the workspace, `<workspace>.ghidra/<target key>/`, and the
    exports stay in `staging` (= `<workspace>/.analysis/<backend>/<key>/`)."""
    workspace = staging.parents[2]
    return workspace.parent / f"{workspace.name}.ghidra" / staging.name


ANSWERS = {"USER_AGREEMENT": "ACCEPT", "SHOW_TIPS": "false"}


def quiet_gui(host, root: Path) -> str:
    """Pre-answer the GUI's first-run prompts (user agreement, tip of the day) in Ghidra's
    per-version preferences: an unattended handoff must not wait on a dialog. The ViWo
    disclaimer covers the agreement; an answer already there (the user's) is kept. Returns
    why the preferences could not be written ("" when fine): the dialog may then show."""
    path = host.config_home() / "ghidra" / root.name / "preferences"
    try:
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        known = {line.split("=", 1)[0] for line in lines}
        missing = [f"{k}={v}" for k, v in ANSWERS.items() if k not in known]
        if missing:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join([*lines, *missing, ""]), encoding="utf-8")
    except OSError as exc:
        return f"Ghidra's first-run answers not written ({exc}): its dialogs may show once"
    return ""


def _gui_argv(headless: Path, java: Path, gpr: Path) -> list[str] | None:
    """The GUI's JVM command (what ghidraRun's batch file ends up starting, minus the
    detaching `start`): a direct child, so ViWo can track and stop it (doc 8.3a)."""
    root = headless.resolve().parent.parent
    utility = root / "Ghidra" / "Framework" / "Utility" / "lib" / "Utility.jar"
    if not utility.is_file():
        return None
    return [
        str(java),
        "-Djava.system.class.loader=ghidra.GhidraClassLoader",
        "-Dfile.encoding=UTF8",
        "-Dsun.java2d.d3d=false",
        "-cp",
        str(utility),
        "ghidra.Ghidra",
        "ghidra.GhidraRun",
        str(gpr),
    ]


class GhidraHeadless(Analyzer):
    """One import + auto-analysis + export per target; the project stays for the handoff."""

    backend_id, license, isolation = "ghidra-headless", "Apache-2.0", "subprocess"
    kinds = ("native_binary",)
    self_check_args = ()  # analyzeHeadless with no arguments prints its usage

    requires = (GHIDRA, JDK)

    def analyze(self, target: AnalysisTarget, ctx) -> Outcome:
        tool, env = ctx.os.tools.locate(GHIDRA), java_env(ctx)
        if tool is None or env is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=GHIDRA.hint if tool is None else JDK.hint)
        project = project_dir(ctx.staging)
        project.mkdir(parents=True, exist_ok=True)
        argv = [*tool.argv_prefix, str(project), PROJECT, "-import", str(target.paths[0])]
        argv += ["-overwrite", "-postScript", "ViwoExport.java", str(ctx.staging)]
        argv += ["-scriptPath", str(SCRIPTS)]
        ctx.log(f"Ghidra: importing and analysing {target.paths[0].name}", stage="analyze")
        result = run_tool(ctx, argv, env, DEFAULT_TIMEOUT, lambda ln: _relay(ctx, ln))
        found = [a for a in ARTIFACTS if (ctx.staging / a).is_file()]
        if result.timed_out or "functions.csv" not in found:
            return failed(result, "Ghidra wrote no functions.csv")
        return Outcome(OutcomeKind.OK, len(found), notes=tuple(found))


def _relay(ctx, line: str) -> None:
    text = line.strip()
    if text.startswith(("INFO  ", "ERROR ", "WARN  ")) or "ViWo export" in text:
        ctx.log(text[:200], level="warn" if text.startswith("ERROR") else "info", stage="analyze")


class GhidraGui(Handoff):
    """Opens the project a headless run left behind; without one it says so."""

    backend_id, license, isolation = "ghidra-gui", "Apache-2.0", "subprocess"
    label, accepts = "Continue in Ghidra", ("native_binary",)
    self_check_args = ()

    requires = (GHIDRA, JDK)

    def prepare(self, target: AnalysisTarget, ctx) -> LaunchSpec | Outcome:
        tool, env = ctx.os.tools.locate(GHIDRA), java_env(ctx)
        if tool is None or env is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=GHIDRA.hint if tool is None else JDK.hint)
        gpr = project_dir(ctx.staging) / f"{PROJECT}.gpr"
        if not gpr.is_file():
            return Outcome(
                OutcomeKind.FAILED, error="no Ghidra project yet: run the analysis first"
            )
        java = ctx.os.tools.locate(JDK)
        argv = _gui_argv(Path(tool.path), Path(java.path), gpr) if java else None
        if argv is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error="Ghidra's Utility.jar not found")
        problem = quiet_gui(ctx.os, Path(tool.path).resolve().parent.parent)
        if problem:
            ctx.log(problem, "warn", "analyze")
        return LaunchSpec(tuple(argv), gpr.parent, env)
