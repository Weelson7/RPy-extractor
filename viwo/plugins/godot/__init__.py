"""Godot engine plugin (doc 13.3): PCK v1-v4, embedded PCKs, GDRE Tools / GodotPckTool."""

from __future__ import annotations

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest, PluginOption
from viwo.contracts.slots import SlotDefinition
from viwo.contracts.types import DetectionResult

from .pck import MAGIC, GdreTools, GodotPckPacker, GodotPckTool, embedded_chunk, identify_pck

MANIFEST = PluginManifest(
    "godot",
    "Godot",
    "0.1.0",
    engine_type="godot",
    priority=15,
    options=(PluginOption("encryption_key", "PCK encryption key (64 hex chars)", "secret"),),
)
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


class GodotPlugin(EnginePlugin):
    @property
    def manifest(self) -> PluginManifest:
        return MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        if any(probe.head(p, 4) == MAGIC for p in probe.with_suffix(".pck")[:20]):
            evidence.append("PCK archive (GDPC)")
        if any(embedded_chunk(p, probe.tail(p, 64)) for p in probe.with_suffix(*EXECUTABLES)[:20]):
            evidence.append("PCK embedded in the executable")
        strong = bool(evidence)
        if probe.has_name("project.godot", ".import") or probe.find(".godot", limit=1):
            evidence.append("Godot project files")
        score = 0.9 if strong else (0.7 if evidence else 0.0)
        return DetectionResult("godot", score, tuple(evidence), "godot")

    def slot_definitions(self):
        return (PCK_SLOT, SlotDefinition("pack.pck", "pack", "godot", "godotpcktool-pack"))

    def backends(self):
        return (GdreTools(), GodotPckTool(), GodotPckPacker())

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.pck" if unarchive_slot == "unarchive.pck" else ""
