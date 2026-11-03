"""Fallback plugin: plain archives and loose files (v1 generic behavior)."""

from __future__ import annotations

from viwo.contracts.analysis import AnalysisTarget, target_key
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.types import DetectionResult

MANIFEST = PluginManifest("generic", "Generic", "0.1.0", engine_type="generic", priority=-100)


PLUGIN = "GenericPlugin"  # discovered by viwo.core.wiring.registry


LUA_SUFFIXES = (".lua", ".luac", ".lub", ".luc", ".out")


def lua_targets(probe: GameProbe) -> list[AnalysisTarget]:
    """Compiled Lua chunks (`\\x1bLua` header) as one script_vm target for unluac."""
    chunks = [p for p in probe.with_suffix(*LUA_SUFFIXES)[:2000] if probe.head(p, 4) == b"\x1bLua"]
    if not chunks:
        return []
    label = f"{len(chunks)} Lua bytecode chunk(s)"
    return [AnalysisTarget("lua-bytecode", "script_vm", tuple(chunks[:500]), "generic", label)]


class GenericPlugin(EnginePlugin):
    @property
    def manifest(self) -> PluginManifest:
        return MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        return DetectionResult(
            "generic", 0.4, ("No strong engine-specific signature needed",), "generic"
        )

    def analysis_targets(self, probe: GameProbe):
        """Executables up to two folders down (doc 6.1, generic row), and Lua bytecode."""
        out = lua_targets(probe)
        for path in probe.with_suffix(".exe", ".x86_64", ".x86", ".elf")[:50]:
            rel = path.relative_to(probe.root)
            if len(rel.parts) <= 3 and "crashhandler" not in path.name.lower():
                out.append(AnalysisTarget(target_key(path), "native_binary", (path,), "generic"))
        return out
