"""Electron / NW.js apps (TyranoScript, Construct, RPG Maker MV deployments...): app.asar.

NW.js package.nw files are zips (core zip slot); loose app folders are collected as is.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind
from viwo.contracts.workspace import safe_member

MANIFEST = PluginManifest(
    "electron", "Electron / NW.js", "0.1.0", engine_type="electron", priority=5
)
MARKERS = ("electron.exe", "nw.exe", "nw", "app.asar", "package.nw", "libnode.so", "nw.dll")


def asar_header(head: bytes) -> tuple[int, int] | None:
    """(json length, data start) from the Chromium pickle header."""
    if len(head) < 16:
        return None
    four, header_size, _, json_len = struct.unpack_from("<4I", head)
    if four != 4 or not 0 < json_len <= header_size < 1 << 30:
        return None
    return json_len, 8 + header_size


def _walk(tree: dict, prefix: str = ""):
    for name, node in (tree.get("files") or {}).items():
        path = f"{prefix}/{name}" if prefix else name
        if "files" in node:
            yield from _walk(node, path)
        elif not node.get("unpacked") and "offset" in node:
            offset, size = int(node["offset"]), int(node.get("size", 0))
            if offset >= 0 and size >= 0:  # negative values would read to the end of the file
                yield path, offset, size


class AsarBuiltin(Unarchiver):
    backend_id, owner, license = "asar-builtin", "electron", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        with open(archive, "rb") as fh:
            found = asar_header(fh.read(16))
            if found is None:
                return Outcome(OutcomeKind.FAILED, error="not an asar archive")
            try:
                tree = json.loads(fh.read(found[0]).decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                return Outcome(OutcomeKind.FAILED, error=f"bad asar header: {exc}")
            written = 0
            total = archive.stat().st_size
            for name, offset, size in _walk(tree):
                rel = safe_member(name)
                if rel is None or ctx.cancel.cancelled or found[1] + offset + size > total:
                    continue
                fh.seek(found[1] + offset)
                target = dest.joinpath(*rel.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(fh.read(size))
                written += 1
        return Outcome(OutcomeKind.OK, written)


SLOT = SlotDefinition(
    "unarchive.asar", "unarchive", "electron", "asar-builtin", suffixes=(".asar",)
)


PLUGIN = "ElectronPlugin"  # discovered by viwo.core.wiring.registry


class ElectronPlugin(EnginePlugin):
    @property
    def manifest(self) -> PluginManifest:
        return MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        if any(asar_header(probe.head(p, 16)) for p in probe.with_suffix(".asar")[:10]):
            evidence.append("app.asar archive")
        if probe.has_name(*MARKERS):
            evidence.append("Electron / NW.js runtime")
        score = 0.8 if len(evidence) == 2 else (0.55 if evidence else 0.0)
        return DetectionResult("electron", score, tuple(evidence), "electron")

    def slot_definitions(self):
        return (SLOT,)

    def backends(self):
        return (AsarBuiltin(),)
