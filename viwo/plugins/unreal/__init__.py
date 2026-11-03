"""Unreal Engine plugin (M7): .pak via repak, IoStore (.utoc/.ucas) via retoc; AES per D18.

Unpacking only: assets come out as .uasset/.uexp/.ubulk (the carver then pulls standard
media embedded in them). Decoding Unreal assets is a later milestone.
"""

from __future__ import annotations

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest, PluginOption
from viwo.contracts.slots import SlotDefinition
from viwo.contracts.types import DetectionResult

from .pak import (
    PAK_MAGIC,
    UTOC_MAGIC,
    RepakCli,
    RepakPatch,
    RetocLegacy,
    RetocUnpack,
    identify_unreal,
)

MANIFEST = PluginManifest(
    "unreal",
    "Unreal Engine",
    "0.1.0",
    engine_type="unreal",
    priority=18,
    options=(
        PluginOption("aes_key", "AES-256 key (hex or base64), if the paks are encrypted", "secret"),
        PluginOption(
            "find_key",
            "No key given: look for it in the game's own executables (verified on the pak index)",
            "bool",
            True,
        ),
    ),
)
SLOTS = (  # identified by footer / magic only: ".pak" is used by many engines
    SlotDefinition(
        "unarchive.upak",
        "unarchive",
        "unreal",
        "repak-cli",
        "quickbms-cli",  # doc 8.4: a .pak script in the QuickBMS scripts folder is the spare
        identify=identify_unreal,
    ),
    SlotDefinition("unarchive.utoc", "unarchive", "unreal", "retoc-legacy", "retoc-unpack"),
)
PACK_SLOT = SlotDefinition("pack.upak", "pack", "unreal", "repak-patch")
MARKERS = ("ue4game", "engine", "ue4prereqsetup_x64.exe", "ueprereqsetup_x64.exe")


PLUGIN = "UnrealPlugin"  # discovered by viwo.core.wiring.registry


class UnrealPlugin(EnginePlugin):
    @property
    def manifest(self) -> PluginManifest:
        return MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        paks = probe.with_suffix(".pak")[:20]
        if any(PAK_MAGIC in probe.tail(p, 512) for p in paks):
            evidence.append("Unreal .pak archives")
        if any(probe.head(p, 16) == UTOC_MAGIC for p in probe.with_suffix(".utoc")[:20]):
            evidence.append("Unreal IoStore containers (.utoc/.ucas)")
        strong = bool(evidence)
        if probe.find("*-shipping.exe", limit=1) or probe.find("*-shipping", limit=1):
            evidence.append("Unreal shipping executable")
        if probe.has_name(*MARKERS):
            evidence.append("Unreal engine folders")
        score = 0.92 if strong else (0.6 if evidence else 0.0)
        return DetectionResult("unreal", score, tuple(evidence), "unreal")

    def slot_definitions(self):
        return (*SLOTS, PACK_SLOT)

    def backends(self):
        return (RepakCli(), RetocLegacy(), RetocUnpack(), RepakPatch())

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.upak" if unarchive_slot == "unarchive.upak" else ""

    def claimed_suffixes(self):
        return (".ucas", ".sig")
