"""REDengine 4 (Cyberpunk 2077): `.archive` containers (RDAR).

The index lists files by name hash (no names ship with the game), each as a run of segments;
a segment either sits raw in the archive or starts with `KARK` (Oodle Kraken). Members come out
at their paths from the community path list (names.py), or as `<hash>.<ext>` when the list does
not know them (the extension read from the CR2W root class or sniffed from the first bytes).
Kraken segments are inflated with the decompressor the game itself ships (`bin/x64/oo2ext_*.dll`,
found beside the archive; Windows only): ViWo authors no decompressor and fetches none.
"""

from __future__ import annotations

import struct
from pathlib import Path

from viwo.contracts.plugin import (
    EnginePlugin,
    GameProbe,
    PluginManifest,
    PluginOption,
    VerifyReport,
)
from viwo.contracts.slots import SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind
from viwo.contracts.workspace import count_files

from . import conflicts
from .export import SLOT as CR2W_SLOT
from .export import WolvenKitExport
from .names import CP77_HASHES, Names
from .pack import SLOT as PACK_SLOT
from .pack import WolvenKitPack
from .rdar import Archive, Oodle
from .scripts import SLOT as SCRIPTS_SLOT
from .scripts import RedscriptDecompile

MAGIC = b"RDAR"
MANIFEST = PluginManifest(
    "redengine",
    "REDengine 4 (Cyberpunk 2077)",
    "0.1.0",
    engine_type="redengine",
    priority=12,
    options=(PluginOption("decompile", "decompile final.redscripts (redscript)", "bool", "on"),),
)
MARKERS = ("redprelauncher.exe", "cyberpunk2077.exe", "redlauncher.exe")


class RdarBuiltin(Unarchiver):
    backend_id, owner, license = "rdar-builtin", "redengine", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def dependencies(self):
        return (CP77_HASHES,)

    def available(self, os):
        return True, ""  # the path list only names members; without it they keep their hash

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        oodle = Oodle.beside(archive, ctx.os)
        names, notes = _names(ctx, oodle)
        skipped = unnamed = 0
        try:
            with open(archive, "rb") as fh:
                rdar = Archive(fh)
                for entry in rdar.entries():
                    if ctx.cancel.cancelled:
                        break
                    name = names.get(entry.name_hash) if names else None
                    unnamed += name is None
                    skipped += not rdar.write(entry, dest, oodle, name or "")
        except (OSError, ValueError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad RDAR: {exc}")
        finally:
            if names:
                names.close()
        if skipped:
            why = "no Oodle decompressor found beside the archive" if oodle is None else "bad data"
            notes.append(f"{skipped} Kraken-compressed member(s) skipped: {why}")
        if unnamed and names:
            notes.append(f"{unnamed} member(s) not in the path list: kept as <hash>.<ext>")
        return Outcome(OutcomeKind.OK, count_files(dest), notes=tuple(notes))


def _names(ctx, oodle) -> tuple[Names | None, list[str]]:
    """The path list, or why members keep their hashes this run."""
    tool = ctx.os.tools.locate(CP77_HASHES)
    if tool is None:
        return None, [f"members keep their hashes: {CP77_HASHES.hint}"]
    if oodle is None:
        return None, ["members keep their hashes: the path list needs the game's Oodle (Windows)"]
    try:
        return Names.load(Path(tool.path), oodle), []
    except (OSError, ValueError) as exc:
        return None, [f"members keep their hashes: the path list did not load ({exc})"]


PLUGIN = "RedenginePlugin"  # discovered by viwo.core.wiring.registry


class RedenginePlugin(EnginePlugin):
    manifest = MANIFEST

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
            CR2W_SLOT,
            SCRIPTS_SLOT,
            PACK_SLOT,
        )

    def verify_report(self, ctx, inventory, export, collected) -> VerifyReport:
        """The plain verdict plus the installed mods' conflicts (names when the list loads)."""
        plain = super().verify_report(ctx, inventory, export, collected)
        game = Path(ctx.game_root)
        if not conflicts.archives(game)[1]:
            return plain
        names, _ = _names(ctx, Oodle.beside(game / "game", ctx.os))
        try:
            lines = conflicts.report(game, lambda h: (names and names.get(h)) or f"{h:016x}")
        finally:
            if names:
                names.close()
        return VerifyReport(plain.ok, plain.warnings + tuple(lines), plain.expected, plain.found)

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.archive" if unarchive_slot == "unarchive.archive" else ""

    def backends(self):
        return (RdarBuiltin(), WolvenKitExport(), RedscriptDecompile(), WolvenKitPack())
