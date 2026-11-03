"""Unity engine plugin (doc 2.7, D3, D7): UnityPy main, AssetStudioModCLI spare."""

from __future__ import annotations

from viwo.contracts.analysis import AnalysisTarget
from viwo.contracts.plugin import (
    EnginePlugin,
    GameProbe,
    PluginManifest,
    PluginOption,
    VerifyReport,
)
from viwo.contracts.slots import SlotDefinition
from viwo.contracts.types import DetectionResult

from .exporters import AssetStudioModCli, UnityPyExporter
from .pack import UnityPyPacker

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
        PluginOption("meshes", "Export meshes as Wavefront .obj files", "bool", True),
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
    SlotDefinition("pack.unity", "pack", "unity", "unitypy-pack"),
)
CLAIMED = (".assets", ".ress", ".resource", ".unity3d", ".bundle", ".assetbundle", "")
STRONG = (
    "unityplayer.dll",
    "unityplayer.so",
    "globalgamemanagers",
    "data.unity3d",
    "maindata",
    "globalgamemanagers.assets",
    "unity default resources",
)


PLUGIN = "UnityPlugin"  # discovered by viwo.core.wiring.registry


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

    def analysis_targets(self, probe: GameProbe):
        """IL2CPP (GameAssembly + metadata) and the managed Assembly-CSharp (doc 6.1)."""
        out = []
        assembly = probe.find("GameAssembly.dll", limit=1)
        meta = probe.find("global-metadata.dat", limit=1)
        exes = [p for p in probe.with_suffix(".exe") if (p.parent / f"{p.stem}_Data").is_dir()]
        if assembly and meta and exes:  # the executable carries the Unity version (Cpp2IL)
            paths = (assembly[0], meta[0], exes[0])
            out.append(AnalysisTarget("gameassembly", "il2cpp", paths, "unity", "IL2CPP"))
        for dll in probe.find("Assembly-CSharp.dll", limit=1):
            out.append(AnalysisTarget("assembly-csharp", "dotnet_assembly", (dll,), "unity"))
        return out

    def slot_definitions(self):
        return SLOTS

    def backends(self):
        return (UnityPyExporter(), AssetStudioModCli(), UnityPyPacker())

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.unity" if unarchive_slot == "exported" else ""

    def claimed_suffixes(self):
        return CLAIMED

    def export_slot(self) -> str:
        return "export.unity"

    def verify_report(self, ctx, inventory, export, collected: int) -> VerifyReport:
        if collected:
            return VerifyReport(True, ())
        return VerifyReport(False, ("Unity detected but nothing was collected",))
