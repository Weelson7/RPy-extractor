"""Godot engine plugin (doc 13.3): PCK v1-v4, embedded PCKs, GDRE Tools / GodotPckTool."""

from viwo.contracts.analysis import AnalysisTarget
from viwo.contracts.plugin import (
    EnginePlugin,
    GameProbe,
    PluginManifest,
    PluginOption,
    VerifyReport,
    option_bool,
)
from viwo.contracts.slots import SlotDefinition
from viwo.contracts.types import DetectionResult

from .gdscript import GdreDecompile, engine_version
from .pck import (
    MAGIC,
    GdreRecover,
    GdreTools,
    GodotPckPacker,
    GodotPckTool,
    embedded_chunk,
    godot_executable,
    identify_pck,
)

MANIFEST = PluginManifest(
    "godot",
    "Godot",
    "0.1.0",
    engine_type="godot",
    profile="godot",
    priority=15,
    options=(
        PluginOption("encryption_key", "PCK encryption key (64 hex chars)", "secret"),
        PluginOption(
            "recover",
            "Recover the project with GDRE Tools (scripts, scenes) during EXPORT",
            "bool",
            False,
            help="[options.godot] recover = on; needs GDRE Tools; slow on big games",
        ),
    ),
    description="Godot 3/4 games: PCK archives, embedded PCKs, encrypted PCKs with a key",
    capabilities=("detect", "unpack", "export", "pack"),
    dependencies=("gdre", "godotpcktool"),
)
EXPORT_SLOT = SlotDefinition("export.godot", "export", "godot", "gdre-recover")
PCK_SLOT = SlotDefinition(
    "unarchive.pck",
    "unarchive",
    "godot",
    "gdre-tools",
    "godotpcktool",
    suffixes=(".pck",),
    magic=(MAGIC,),
    identify=identify_pck,
)
EXECUTABLES = (".exe", ".x86_64", ".x86_32", ".arm64", ".arm32")
NO_DATA = "Godot executable (PE pck section) without PCK data"
NO_PCK_HINT = (
    "no PCK data: the executable carries an empty pck section and no .pck sits next to it; "
    "copy the game's .pck beside the executable (or the export embedded nothing)"
)


class GodotPlugin(EnginePlugin):
    def __init__(self) -> None:
        self._recover = False

    manifest = MANIFEST

    def configure(self, options) -> None:
        self._recover = option_bool(options, "recover")

    def export_slot(self) -> str:
        return "export.godot" if self._recover else ""

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        if any(probe.head(p, 4) == MAGIC for p in probe.with_suffix(".pck")[:20]):
            evidence.append("PCK archive (GDPC)")
        if any(embedded_chunk(p, probe.tail(p, 64)) for p in probe.with_suffix(*EXECUTABLES)[:20]):
            evidence.append("PCK embedded in the executable")
        strong = bool(evidence)
        if probe.has_name("project.godot", ".import") or probe.find(".godot", limit=1):
            evidence.append("Godot project files")
        exes = probe.with_suffix(*EXECUTABLES)[:20]
        if not evidence and any(godot_executable(probe.head(p, 4096)) for p in exes):
            evidence.append(NO_DATA)  # an engine binary with nothing to extract: say so
        score = (
            0.9
            if strong
            else 0.7
            if "Godot project files" in evidence
            else 0.6
            if evidence
            else 0.0
        )
        return DetectionResult("godot", score, tuple(evidence), "godot")

    def verify_report(self, ctx, inventory, export, collected) -> VerifyReport:
        if NO_DATA in ctx.detection.evidence:
            return VerifyReport(False, (NO_PCK_HINT,), 0, 0)
        return super().verify_report(ctx, inventory, export, collected)

    def analysis_targets(self, probe: GameProbe):
        """Compiled GDScript (`.gdc`), one target for all of them (doc 6.1)."""
        files = tuple(probe.with_suffix(".gdc"))  # every script: GDRE runs them in batches
        if not files:
            return ()
        exes = sorted(probe.with_suffix(".exe", ".x86_64"), key=lambda p: -p.stat().st_size)
        version = engine_version(exes[0]) if exes else ""  # only read when .gdc files exist
        hints = {"engine_version": version} if version else {}
        target = AnalysisTarget(
            "gdscript", "gdscript_bytecode", files, "godot", f"{len(files)} .gdc", hints
        )
        return (target,)

    def slot_definitions(self):
        return (
            PCK_SLOT,
            EXPORT_SLOT,
            SlotDefinition("pack.pck", "pack", "godot", "godotpcktool-pack"),
            SlotDefinition("analysis.gdscript", "analysis", "godot", "gdre-decompile"),
        )

    def backends(self):
        return (GdreTools(), GodotPckTool(), GodotPckPacker(), GdreRecover(), GdreDecompile())

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.pck" if unarchive_slot == "unarchive.pck" else ""
