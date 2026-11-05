"""Cyberpunk 2077, the game plugin under REDengine (doc 2.10): what only this title has. Its
path list names the members of its archives (the engine's RDAR reader takes `name_lists` from
the run's game plugins), its compiled scripts are decompiled by redscript, and its executables
are the detection evidence for the title."""

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest, PluginOption
from viwo.contracts.slots import Backend
from viwo.contracts.types import DependencySpec, DetectionResult

from .scripts import SLOT, RedscriptDecompile

CP77_HASHES = DependencySpec(
    "cp77-hashes",
    "Cyberpunk 2077 path list (WolvenKit)",
    hint="`viwo install cp77-hashes` (data from WolvenKit, pinned by commit)",
)
MARKERS = ("redprelauncher.exe", "cyberpunk2077.exe", "redlauncher.exe")
MANIFEST = PluginManifest(
    "cyberpunk2077",
    "Cyberpunk 2077",
    "0.1.0",
    engine_type="redengine",
    engine="redengine",
    options=(PluginOption("decompile", "decompile final.redscripts (redscript)", "bool", "on"),),
)


class PathList(Backend):
    """No slot: the path list is data the engine's reader uses; declaring it here lets the
    preflight install it and SYSTEM list it."""

    backend_id, owner, license = "cp77-path-list", "cyberpunk2077", "MIT"
    families = frozenset({"names"})
    requires = (CP77_HASHES,)


class Cyberpunk2077Plugin(EnginePlugin):
    manifest = MANIFEST
    name_lists = (CP77_HASHES,)  # the REDengine archive reader names members from these

    def detect(self, probe: GameProbe) -> DetectionResult:
        found = probe.has_name(*MARKERS)
        evidence = ("Cyberpunk 2077 launcher or executable",) if found else ()
        return DetectionResult("redengine", 0.9 if found else 0.0, evidence, "cyberpunk2077")

    def slot_definitions(self):
        return (SLOT,)

    def backends(self):
        return (RedscriptDecompile(), PathList())
