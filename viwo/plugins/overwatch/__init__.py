"""Overwatch (D16): static extraction of the local install through DataTool (overtools).

Marked terms-of-service sensitive: never picked by AUTO detection (choose it explicitly),
every run carries a reminder, runtime capture and repacking are refused, and real-game
testing is done by the independent operator (doc 17.4b).
"""

from __future__ import annotations

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest, PluginOption
from viwo.contracts.slots import Exporter, SlotDefinition
from viwo.contracts.types import DependencySpec, DetectionResult, Outcome, OutcomeKind

DATATOOL = DependencySpec(
    "datatool",
    "DataTool (overtools)",
    env_var="VIWO_DATATOOL",
    executables=("DataTool", "DataTool.exe"),
    install_dirs=("DataTool", "toolchain-release"),
    hint="install DataTool from overtools/OWLib (MIT)",
)
MODES = "extract-unlocks,extract-general,extract-maps"
MANIFEST = PluginManifest(
    "overwatch",
    "Overwatch (DataTool)",
    "0.1.0",
    engine_type="overwatch",
    priority=5,
    tos_sensitive=True,
    options=(PluginOption("modes", "DataTool modes to run, comma separated", "string", MODES),),
)
REMINDER = "Overwatch: personal, offline use of your own install; respect Blizzard's terms"


class DataToolExporter(Exporter):
    backend_id, owner, license, isolation = "datatool", "overwatch", "MIT", "subprocess"

    def dependencies(self):
        return (DATATOOL,)

    def export(self, ctx) -> Outcome:
        tool = ctx.os.tools.locate(DATATOOL)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=DATATOOL.hint)
        modes = [m.strip() for m in str(ctx.options.get("modes") or MODES).split(",") if m.strip()]
        failed = []
        for mode in modes:
            out = ctx.staging / mode
            ctx.log(f"DataTool {mode}", stage="export")
            argv = [*tool.argv_prefix, str(ctx.game_root), mode, str(out)]
            if not ctx.os.process.run(argv, timeout=12 * 3600, cancel=ctx.cancel).ok:
                failed.append(mode)
        files = sum(1 for p in ctx.staging.rglob("*") if p.is_file())
        if failed and not files:
            return Outcome(OutcomeKind.FAILED, error=f"DataTool failed: {', '.join(failed)}")
        notes = (REMINDER,) + ((f"failed modes: {', '.join(failed)}",) if failed else ())
        return Outcome(OutcomeKind.OK, files, notes=notes)


class OverwatchPlugin(EnginePlugin):
    @property
    def manifest(self) -> PluginManifest:
        return MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = ()
        if probe.has_name("overwatch.exe", "overwatch launcher.exe"):
            evidence += ("Overwatch executable",)
        if probe.has_name(".build.info") and probe.find("casc", limit=1):
            evidence += ("Blizzard CASC storage",)
        score = 0.95 if len(evidence) == 2 else (0.6 if evidence else 0.0)
        return DetectionResult("overwatch", score, evidence, "overwatch")

    def slot_definitions(self):
        return (SlotDefinition("export.overwatch", "export", "overwatch", "datatool"),)

    def backends(self):
        return (DataToolExporter(),)

    def export_slot(self) -> str:
        return "export.overwatch"

    def skip_dirs(self):
        return ("data",)  # CASC storage: DataTool reads it; never copied raw

    def verify(self, ctx, collected: int):
        return (REMINDER,)
