"""Example drop-in plugin (docs/plugins.md): a `.hello` archive is a zip with another name.

Drop this folder into a folder listed in `[plugins] custom_dirs`, then `[plugins] hello = on`.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind
from viwo.contracts.workspace import safe_member

MANIFEST = PluginManifest(
    "hello", "Hello (example)", "0.1.0", engine_type="hello", priority=1, builtin=False
)


class HelloUnarchiver(Unarchiver):
    backend_id, owner, license = "hello-zip", "hello", "MIT"

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        written = 0
        try:
            with zipfile.ZipFile(archive) as zf:
                for info in zf.infolist():
                    rel = safe_member(info.filename)  # traversal, drive letters, links
                    if rel is None or info.is_dir():
                        continue
                    target = dest.joinpath(*rel.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zf.read(info))
                    written += 1
        except (zipfile.BadZipFile, OSError) as exc:
            return Outcome(OutcomeKind.FAILED, error=str(exc)[:300])
        return Outcome(OutcomeKind.OK, written)


class HelloPlugin(EnginePlugin):
    @property
    def manifest(self) -> PluginManifest:
        return MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        hits = probe.with_suffix(".hello")
        if not hits:
            return DetectionResult("hello", 0.0, (), "hello")
        return DetectionResult("hello", 0.9, (f"{len(hits)} .hello archive(s)",), "hello")

    def slot_definitions(self):
        return (
            SlotDefinition(
                "unarchive.hello",
                "unarchive",
                "hello",
                "hello-zip",
                suffixes=(".hello",),
                magic=(b"PK\x03\x04",),
            ),
        )

    def backends(self):
        return (HelloUnarchiver(),)
