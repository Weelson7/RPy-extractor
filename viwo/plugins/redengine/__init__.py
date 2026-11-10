"""REDengine 4 (Cyberpunk 2077): `.archive` containers (RDAR).

The index lists files by name hash (no names ship with the game), each as a run of segments;
a segment either sits raw in the archive or starts with `KARK` (Oodle Kraken). Members come out
at their paths from the community path list (names.py), or as `<hash>.<ext>` when the list does
not know them (the extension read from the CR2W root class or sniffed from the first bytes).
Kraken segments are inflated with the decompressor the game itself ships (`bin/x64/oo2ext_*.dll`,
found beside the archive; Windows only): ViWo authors no decompressor and fetches none.
"""

import struct
import threading
import time
from pathlib import Path

from viwo.contracts import workspace as ws
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
from .names import Names
from .pack import SLOT as PACK_SLOT
from .pack import WolvenKitPack
from .rdar import Archive, Oodle

MAGIC = b"RDAR"
MANIFEST = PluginManifest(
    "redengine",
    "REDengine 4",
    "0.1.0",
    engine_type="redengine",
    priority=12,
)


class RdarBuiltin(Unarchiver):
    backend_id, owner, license = "rdar-builtin", "redengine", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def available(self, os):
        return True, ""  # the path list only names members; without it they keep their hash

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        oodle = Oodle.beside(archive, ctx.os)
        names, notes = _names(ctx, oodle)
        skipped = unnamed = 0
        out, handles, local = ws.Names(dest), [], threading.local()

        def handle():  # the archive, opened once per worker: a shared handle cannot seek for two
            if not hasattr(local, "fh"):
                local.fh = open(archive, "rb")  # noqa: SIM115 (closed with `handles` below)
                handles.append(local.fh)
            return local.fh

        try:
            with open(archive, "rb") as fh:
                rdar, plan = Archive(fh), []
                for entry in rdar.entries():  # names in the members' order: one writer
                    name = names.get(entry.name_hash) if names else None
                    unnamed += name is None
                    plan.append((entry, Archive.place(out, name or "")))
                one = lambda i: rdar.write(i[0], out, oodle, at=(i[1], handle()))  # noqa: E731
                said = time.monotonic()
                for done, written in enumerate(ctx.each(one, plan, ctx.cancel), 1):
                    skipped += not written
                    if ctx.cancel.cancelled:
                        break
                    if time.monotonic() - said >= 1:  # never silent: a large archive is minutes
                        said = time.monotonic()
                        ctx.log(f"{archive.name}: {done}/{len(plan)} members", stage="unpack")
        except (OSError, ValueError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad RDAR: {exc}")
        finally:
            for opened in handles:
                opened.close()
            if names:
                names.close()
        if skipped:
            why = "no Oodle decompressor found beside the archive" if oodle is None else "bad data"
            notes.append(f"{skipped} Kraken-compressed member(s) skipped: {why}")
        if unnamed and names:
            notes.append(f"{unnamed} member(s) not in the path list: kept as <hash>.<ext>")
        files = count_files(dest)
        return Outcome(OutcomeKind.OK, files, notes=tuple(notes) + out.save())


def _names(ctx, oodle) -> tuple[Names | None, list[str]]:
    """The path list a game plugin of this run supplies (doc 2.10), or why members keep their
    hashes this run."""
    lists = [spec for game in ctx.games for spec in getattr(game, "name_lists", ())]
    if not lists:
        return None, ["members keep their hashes: no game plugin supplies this game's paths"]
    tool = next((t for t in map(ctx.os.tools.locate, lists) if t is not None), None)
    if tool is None:
        return None, [f"members keep their hashes: {lists[0].hint}"]
    if oodle is None:
        return None, ["members keep their hashes: the path list needs the game's Oodle (Windows)"]
    try:
        return Names.load(Path(tool.path), oodle), []
    except (OSError, ValueError) as exc:
        return None, [f"members keep their hashes: the path list did not load ({exc})"]


class RedenginePlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        """The engine's own signature (RDAR archives), never a game's executable name."""
        found = any(probe.head(p, 4) == MAGIC for p in probe.with_suffix(".archive")[:10])
        evidence = ("RDAR archives",) if found else ()
        return DetectionResult("redengine", 0.85 if found else 0.0, evidence, "redengine")

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
        return (RdarBuiltin(), WolvenKitExport(), WolvenKitPack())
