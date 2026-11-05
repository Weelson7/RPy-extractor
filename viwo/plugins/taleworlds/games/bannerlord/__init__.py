"""Mount & Blade II: Bannerlord, the game plugin under TaleWorlds (doc 2.10): its executables
name the title; its tooling (module SDK, the game's XML data) belongs here as it is added."""

from __future__ import annotations

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.types import DetectionResult

MARKERS = ("bannerlord.exe", "taleworlds.mountandblade.launcher.exe", "bannerlord.native.exe")
MANIFEST = PluginManifest(
    "bannerlord",
    "Mount & Blade II: Bannerlord",
    "0.1.0",
    engine_type="taleworlds",
    engine="taleworlds",
)

PLUGIN = "BannerlordPlugin"  # discovered by viwo.core.wiring.registry


class BannerlordPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        found = probe.has_name(*MARKERS)
        evidence = ("Bannerlord launcher or executable",) if found else ()
        return DetectionResult("taleworlds", 0.9 if found else 0.0, evidence, "bannerlord")
