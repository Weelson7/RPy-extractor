"""Fallback plugin: plain archives and loose files (v1 generic behavior)."""

from __future__ import annotations

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.types import DetectionResult

MANIFEST = PluginManifest("generic", "Generic", "0.1.0", engine_type="generic", priority=-100)


class GenericPlugin(EnginePlugin):
    @property
    def manifest(self) -> PluginManifest:
        return MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        return DetectionResult(
            "generic", 0.4, ("No strong engine-specific signature needed",), "generic"
        )
