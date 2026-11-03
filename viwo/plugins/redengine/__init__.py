"""REDengine 4 (Cyberpunk 2077): `.archive` containers (RDAR).

The index lists files by name hash (no names ship with the game), each as a run of segments;
a segment either sits raw in the archive or starts with `KARK` (Oodle Kraken). Members come out
as `<hash>.<ext>`, the extension read from the CR2W root class or sniffed from the first bytes.
Kraken segments are inflated with the decompressor the game itself ships (`bin/x64/oo2ext_*.dll`,
found beside the archive; Windows only): ViWo authors no decompressor and fetches none.
"""

from __future__ import annotations

import struct
from pathlib import Path

from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind
from viwo.contracts.workspace import count_files

from .rdar import Archive, Oodle

MAGIC = b"RDAR"
MANIFEST = PluginManifest(
    "redengine", "REDengine 4 (Cyberpunk 2077)", "0.1.0", engine_type="redengine", priority=12
)
MARKERS = ("redprelauncher.exe", "cyberpunk2077.exe", "redlauncher.exe")


class RdarBuiltin(Unarchiver):
    backend_id, owner, license = "rdar-builtin", "redengine", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        oodle = Oodle.beside(archive)
        skipped = 0
        try:
            with open(archive, "rb") as fh:
                rdar = Archive(fh)
                for entry in rdar.entries():
                    if ctx.cancel.cancelled:
                        break
                    if not rdar.write(entry, dest, oodle):
                        skipped += 1
        except (OSError, ValueError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad RDAR: {exc}")
        notes = ()
        if skipped:
            why = "no Oodle decompressor found beside the archive" if oodle is None else "bad data"
            notes = (f"{skipped} Kraken-compressed member(s) skipped: {why}",)
        return Outcome(OutcomeKind.OK, count_files(dest), notes=notes)


PLUGIN = "RedenginePlugin"  # discovered by viwo.core.wiring.registry


class RedenginePlugin(EnginePlugin):
    @property
    def manifest(self) -> PluginManifest:
        return MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        if any(probe.head(p, 4) == MAGIC for p in probe.with_suffix(".archive")[:10]):
            evidence.append("RDAR archives")
        if probe.has_name(*MARKERS):
            evidence.append("REDengine launcher or executable")
        score = 0.9 if len(evidence) == 2 else 0.7 if evidence else 0.0
        return DetectionResult("redengine", score, tuple(evidence), "redengine")

    def slot_definitions(self):
        return (
            SlotDefinition(
                "unarchive.archive",
                "unarchive",
                "redengine",
                "rdar-builtin",
                suffixes=(".archive",),
                magic=(MAGIC,),
            ),
        )

    def backends(self):
        return (RdarBuiltin(),)
