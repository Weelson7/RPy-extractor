"""Doom engine plugin (D16): IWAD / PWAD data for Doom, Heretic, Hexen, Freedoom and source ports.

The custom-engine showcase: everything runs in process with the standard library, and the
plugin only uses the public contracts, as an out-of-tree plugin would.
"""

from __future__ import annotations

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest, PluginOption
from viwo.contracts.slots import SlotDefinition
from viwo.contracts.types import DetectionResult

from .wad import MAGICS, WadBuiltin

MANIFEST = PluginManifest(
    "doom",
    "Doom (WAD)",
    "0.1.0",
    engine_type="doom",
    priority=10,
    options=(
        PluginOption("raw_lumps", "Also keep every converted lump as a raw .lmp", "bool", False),
    ),
)
WAD_SLOT = SlotDefinition(
    "unarchive.wad", "unarchive", "doom", "wad-builtin", suffixes=(".wad",), magic=MAGICS
)
SOURCE_PORTS = "gzdoom zdoom chocolate-doom crispy-doom prboom-plus dsda-doom woof".split()
PORTS = ("doom.exe", "doom2.exe", "heretic.exe", "hexen.exe")
PORTS += tuple(SOURCE_PORTS) + tuple(f"{p}.exe" for p in SOURCE_PORTS)  # Linux and Windows names


PLUGIN = "DoomPlugin"  # discovered by viwo.core.wiring.registry


class DoomPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        heads = [probe.head(p, 4) for p in probe.with_suffix(".wad")[:50]]
        evidence = []
        if b"IWAD" in heads:
            evidence.append("IWAD (Doom engine game data)")
        if b"PWAD" in heads:
            evidence.append("PWAD (Doom engine add-on data)")
        if probe.has_name(*PORTS):
            evidence.append("Doom engine executable / source port")
        score = 0.9 if b"IWAD" in heads else (0.6 if evidence else 0.0)
        return DetectionResult("doom", score, tuple(evidence), "doom")

    def slot_definitions(self):
        from .pack import SLOT as PACK_SLOT

        return (WAD_SLOT, PACK_SLOT)

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.wad" if unarchive_slot == "unarchive.wad" else ""

    def backends(self):
        from .pack import WadWriter

        return (WadBuiltin(), WadWriter())
