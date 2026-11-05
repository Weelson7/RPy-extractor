"""RPG Maker plugin: MV/MZ encrypted media (exporter) and XP/VX/VX Ace RGSSAD archives."""

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import SlotDefinition
from viwo.contracts.types import DetectionResult

from .mv import SUFFIXES, RpgMvExporter, RpgMvPacker
from .rgss import MAGIC, RgssadBuiltin

MANIFEST = PluginManifest("rpgmaker", "RPG Maker", "0.1.0", engine_type="rpgmaker", priority=16)
from .rgss_pack import SLOT as RGSS_PACK_SLOT  # noqa: E402
from .rgss_pack import RgssadWriter  # noqa: E402

SLOTS = (
    SlotDefinition(
        "unarchive.rgssad",
        "unarchive",
        "rpgmaker",
        "rgssad-builtin",
        suffixes=(".rgssad", ".rgss2a", ".rgss3a"),
        magic=(MAGIC,),
    ),
    SlotDefinition("export.rpgmaker", "export", "rpgmaker", "rpgmv-builtin"),
    SlotDefinition("pack.rpgmaker", "pack", "rpgmaker", "rpgmv-pack"),
    RGSS_PACK_SLOT,
)
MARKERS = ("rpg_core.js", "rmmz_core.js", "rpg_managers.js", "rmmz_managers.js", "game.rgssad")
MARKERS += ("game.rgss2a", "game.rgss3a", "rgss102e.dll", "rgss202e.dll", "rgss301.dll")


class RpgMakerPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        if probe.has_name(*MARKERS):
            evidence.append("RPG Maker runtime / archive files")
        if probe.with_suffix(*SUFFIXES)[:1]:
            evidence.append("RPG Maker MV/MZ encrypted media")
        strong = bool(evidence)
        if probe.has_name("system.json") and probe.find("img", limit=1):
            evidence.append("RPG Maker data/System.json + img/")
        score = 0.9 if strong else (0.6 if evidence else 0.0)
        return DetectionResult("rpgmaker", score, tuple(evidence), "rpgmaker")

    def slot_definitions(self):
        return SLOTS

    def backends(self):
        return (RgssadBuiltin(), RpgMvExporter(), RpgMvPacker(), RgssadWriter())

    def pack_slot(self, unarchive_slot: str) -> str:
        return {"exported": "pack.rpgmaker", "unarchive.rgssad": "pack.rgssad"}.get(
            unarchive_slot, ""
        )

    def export_slot(self) -> str:
        return "export.rpgmaker"

    def claimed_suffixes(self):
        return tuple(SUFFIXES)
