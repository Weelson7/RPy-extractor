"""Ren'Py engine plugin (doc 2.7): RPA archives, `game/` as the loose-file root, .rpyc decompile."""

from __future__ import annotations

from pathlib import Path

from viwo.contracts.analysis import AnalysisTarget
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest, PluginOption
from viwo.contracts.slots import SlotDefinition
from viwo.contracts.types import DetectionResult

from .decompile import ANALYSIS_SLOT, RPYC_SLOT, UnrpycAnalyzer, UnrpycCli
from .pack import RpaWriter
from .rpa import RpaSafe, Unrpa

MANIFEST = PluginManifest(
    "renpy",
    "Ren'Py",
    "0.2.0",
    engine_type="renpy",
    priority=10,
    options=(PluginOption("decompile", "decompile .rpyc scripts to .rpy (unrpyc)", "bool", "on"),),
)
RPA_SLOT = SlotDefinition(
    "unarchive.rpa", "unarchive", "renpy", "rpa-safe", "unrpa", suffixes=(".rpa",), magic=(b"RPA-",)
)

PACK_SLOT = SlotDefinition("pack.rpa", "pack", "renpy", "rpa-writer")


PLUGIN = "RenPyPlugin"  # discovered by viwo.core.wiring.registry


class RenPyPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        checks = (
            (0.45, bool(probe.find("renpy", limit=1)), "renpy/ engine folder"),
            (0.4, bool(probe.with_suffix(".rpa")), ".rpa archives"),
            (0.3, bool(probe.with_suffix(".rpyc", ".rpy")), ".rpy/.rpyc scripts"),
            (0.3, probe.has_name("script_version.txt"), "script_version.txt"),
        )
        evidence = tuple(label for _, hit, label in checks if hit)
        score = min(0.95, sum(weight for weight, hit, _ in checks if hit))
        return DetectionResult("renpy", round(score, 2), evidence, "renpy")

    def analysis_targets(self, probe: GameProbe):
        """`.rpyc` scripts as one python_bytecode target (analysis.python, unrpyc)."""
        files = tuple(probe.with_suffix(".rpyc")[:500])
        label = f"{len(files)} .rpyc"
        return (AnalysisTarget("rpyc", "python_bytecode", files, "renpy", label),) if files else ()

    def slot_definitions(self):
        return (RPA_SLOT, PACK_SLOT, RPYC_SLOT, ANALYSIS_SLOT)

    def backends(self):
        return (RpaSafe(), Unrpa(), RpaWriter(), UnrpycCli(), UnrpycAnalyzer())

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.rpa" if unarchive_slot == "unarchive.rpa" else ""

    def source_roots(self, game_root: Path, probe: GameProbe):
        game_dir = game_root / "game"
        return (game_dir,) if game_dir.is_dir() else (game_root,)
