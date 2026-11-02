"""Ren'Py engine plugin (doc 2.7): RPA archives, `game/` as the loose-file root."""

from __future__ import annotations

from pathlib import Path

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import SlotDefinition
from viwo.contracts.types import DetectionResult

from .rpa import RpaSafe, Unrpa

MANIFEST = PluginManifest("renpy", "Ren'Py", "0.1.0", engine_type="renpy", priority=10)
RPA_SLOT = SlotDefinition(
    "unarchive.rpa", "unarchive", "renpy", "rpa-safe", "unrpa", suffixes=(".rpa",), magic=(b"RPA-",)
)


class RenPyPlugin(EnginePlugin):
    @property
    def manifest(self) -> PluginManifest:
        return MANIFEST

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

    def slot_definitions(self):
        return (RPA_SLOT,)

    def backends(self):
        return (RpaSafe(), Unrpa())

    def source_roots(self, game_root: Path, probe: GameProbe):
        game_dir = game_root / "game"
        return (game_dir,) if game_dir.is_dir() else (game_root,)
