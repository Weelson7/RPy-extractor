"""Unity engine plugin (doc 2.7, D3, D7): UnityPy main, AssetStudioModCLI spare."""

from __future__ import annotations

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest, PluginOption
from viwo.contracts.slots import SlotDefinition
from viwo.contracts.types import DetectionResult

from .exporters import AssetStudioModCli, UnityPyExporter

MANIFEST = PluginManifest(
    "unity",
    "Unity",
    "0.1.0",
    engine_type="unity",
    priority=20,
    options=(
        PluginOption(
            "include_cache",
            "Also read the game's cache / persistent data (outside the game folder, read-only)",
            "bool",
            False,
        ),
    ),
)
SLOTS = (
    SlotDefinition(
        "unarchive.unitypackage",
        "unarchive",
        "unity",
        "py-tarfile",
        "sevenzip-cli",
        suffixes=(".unitypackage",),
    ),
    SlotDefinition("export.unity", "export", "unity", "unitypy", "assetstudiomod-cli"),
)
STRONG = (
    "unityplayer.dll",
    "unityplayer.so",
    "globalgamemanagers",
    "data.unity3d",
    "maindata",
    "globalgamemanagers.assets",
    "unity default resources",
)


class UnityPlugin(EnginePlugin):
    @property
    def manifest(self) -> PluginManifest:
        return MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        if probe.has_name(*STRONG):
            evidence.append("Unity player/data marker files")
        if probe.find("il2cpp_data", limit=1) or probe.find("assembly-csharp.dll", limit=1):
            evidence.append("Unity managed/IL2CPP code")
        data_dir = bool(probe.find("*_data", limit=1))
        if data_dir:
            evidence.append("*_Data folder pattern")
        strong = len(evidence) - int(data_dir)
        score = 0.92 if strong else (0.5 if data_dir else 0.0)
        return DetectionResult("unity", score, tuple(evidence), "unity")

    def slot_definitions(self):
        return SLOTS

    def backends(self):
        return (UnityPyExporter(), AssetStudioModCli())

    def export_slot(self) -> str:
        return "export.unity"

    def verify(self, ctx, collected: int):
        return () if collected else ("Unity detected but nothing was collected",)
