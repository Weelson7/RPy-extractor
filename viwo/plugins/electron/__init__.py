"""Electron / NW.js apps (TyranoScript, Construct, RPG Maker MV deployments...): app.asar.

NW.js package.nw files are zips (core zip slot); loose app folders are collected as is.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind

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
            names = ws.Names(dest)
            written, cut = _write_all(fh, tree, found[1], names, ctx)
        notes = (f"{cut} entr(ies) past the end of the archive (cut short)",) if cut else ()
        return Outcome(OutcomeKind.OK, written, notes=names.save() + notes)


def _write_all(fh, tree: dict, base: int, names: ws.Names, ctx) -> tuple[int, int]:
    """(written, entries past the end of a cut archive); names counts the escapes."""
    written, cut = 0, 0
    total = fh.seek(0, 2)
    for name, offset, size in _walk(tree):
        if ctx.cancel.cancelled:
            break
        if base + offset + size > total:
            cut += 1
            continue
        target = names.target(name)
        if target is None:
            continue
        fh.seek(base + offset)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(fh.read(size))
        written += 1
    return written, cut


SLOT = SlotDefinition(
    "unarchive.asar", "unarchive", "electron", "asar-builtin", suffixes=(".asar",)
)


PLUGIN = "ElectronPlugin"  # discovered by viwo.core.wiring.registry


class ElectronPlugin(EnginePlugin):
    manifest = MANIFEST

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
