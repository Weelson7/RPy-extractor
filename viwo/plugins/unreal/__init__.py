"""Unreal Engine plugin (M7): .pak via repak, IoStore (.utoc/.ucas) via retoc; AES per D18.

Members come out as .uasset/.uexp/.ubulk; `export.unreal` (UnrealAssetScout) decodes them into
PNG textures, models (UEFormat, and glTF through uemodel.py), animations, sounds and JSON, with
the mappings the RUNTIME agent writes; `decode.locres` (locres.py) turns localization tables into
JSON and back.
"""

from viwo.contracts.analysis import AnalysisTarget
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest, PluginOption
from viwo.contracts.slots import SlotDefinition
from viwo.contracts.types import DetectionResult

from .agent import Ue4ssAgent
from .assets import SLOT as EXPORT_SLOT
from .assets import UasExport
from .keys import SLOT as KEYS_SLOT
from .keys import ExecutableKeys
from .locres import SLOT as LOCRES_SLOT
from .locres import LocresBuiltin
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
    profile="unreal",
    priority=18,
    options=(
        PluginOption("aes_key", "AES-256 key (hex or base64), if the paks are encrypted", "secret"),
        PluginOption(
            "find_key",
            "No key given: look for it in the game's own executables (verified on the pak index)",
            "bool",
            True,
        ),
        PluginOption(
            "usmap", "Mappings (.usmap) for cooked assets; empty: the RUNTIME agent's", "path"
        ),
        PluginOption(
            "engine", "Engine version for asset export (e.g. GAME_UE5_3); empty: detected", "string"
        ),
        PluginOption(
            "models",
            "glb: every exported model also as a .glb (LOD 0, skeleton and weights); uemodel: "
            "UnrealAssetScout's UEFormat files only",
            "string",
            "glb",
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


class UnrealPlugin(EnginePlugin):
    manifest = MANIFEST

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

    def analysis_targets(self, probe: GameProbe):
        """The shipping executable, with any `.usmap` beside it as companions (doc 6.1)."""
        exes = probe.find("*-shipping.exe", limit=1)
        if not exes:
            return ()
        paths = (exes[0], *probe.with_suffix(".usmap")[:4])
        return (AnalysisTarget("shipping-exe", "native_binary", paths, "unreal", exes[0].name),)

    def slot_definitions(self):
        return (
            *SLOTS,
            PACK_SLOT,
            EXPORT_SLOT,
            KEYS_SLOT,
            LOCRES_SLOT,
            SlotDefinition("runtime.unreal", "runtime", "unreal", "ue4ss-agent"),
        )

    def backends(self):
        kinds = (RepakCli, RetocLegacy, RetocUnpack, RepakPatch, Ue4ssAgent, UasExport)
        return (*(kind() for kind in kinds), ExecutableKeys(), LocresBuiltin())

    def export_slot(self) -> str:
        return "export.unreal"

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.upak" if unarchive_slot == "unarchive.upak" else ""

    def claimed_suffixes(self):
        return (".ucas", ".sig")
