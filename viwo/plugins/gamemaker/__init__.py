"""GameMaker Studio games: the `FORM` container (`data.win`, `game.unx`, `game.ios`,
`game.droid`, audiogroup `.dat`), read and written first-party (iff.py). `unarchive.gamemaker`
surfaces every chunk, decodes the embedded PNG textures, audio and strings; `pack.gamemaker`
writes an edited member back in place when its size is unchanged and refuses a size change by
name. The container is UndertaleModTool's domain; ViWo neither imports it (GPL) nor re-chunks the
file. Not verified against a built GameMaker game."""

import json
import os
import struct
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest
from viwo.contracts.slots import Match, Packer, SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind

from .iff import FIRST, MAGIC, plan_edits, surface

MANIFEST = PluginManifest(
    "gamemaker",
    "GameMaker",
    "0.1.0",
    engine_type="gamemaker",
    priority=14,
    description="GameMaker Studio games: the FORM data file (data.win / game.unx / .ios / .dat)",
    capabilities=("detect", "unpack", "pack"),
)
NAMES = ("data.win", "game.unx", "game.ios", "game.droid")


def identify_gm(path: Path, head: bytes, tail: bytes) -> Match | None:
    if head[:4] == MAGIC and head[8:12] == FIRST:
        return Match("unarchive.gamemaker", path)
    return None


SLOTS = (
    SlotDefinition(
        "unarchive.gamemaker", "unarchive", "gamemaker", "gm-builtin", identify=identify_gm
    ),
    SlotDefinition("pack.gamemaker", "pack", "gamemaker", "gm-writer"),
)


class GmUnarchiver(Unarchiver):
    backend_id, owner, license = "gm-builtin", "gamemaker", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        try:
            blob = archive.read_bytes()
            ranges, strs, notes = surface(blob)
        except (OSError, ValueError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"bad GameMaker data file: {exc}"[:300])
        names, written = ws.Names(dest), 0
        for member, (off, length) in ranges.items():
            if ctx.cancel.cancelled:
                break
            target = names.target(member)  # the chunk name is untrusted (doc 2.5)
            if target is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob[off : off + length])
            written += 1
        if strs is not None and not ctx.cancel.cancelled:
            target = names.target("strings.json")
            if target is not None:
                target.write_text(json.dumps(strs, ensure_ascii=False, indent=1), encoding="utf-8")
                written += 1
        return Outcome(OutcomeKind.OK, written, notes=tuple([*names.save(), *notes]))


class GmWriter(Packer):
    """Each edited member written back in place when its size is unchanged (every absolute offset
    stays valid); a size change, and an edit to strings.json, are refused by name."""

    backend_id, owner, license = "gm-writer", "gamemaker", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: reads the game's data file

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        temp = container.with_name(container.name + ".viwo-tmp")
        try:
            blob = bytearray(container.read_bytes())
            ranges, _, _ = surface(bytes(blob))
            for (off, length), data in plan_edits(ranges, members):
                blob[off : off + length] = data
            temp.write_bytes(bytes(blob))
            os.replace(temp, container)
        except (OSError, ValueError, struct.error) as exc:
            temp.unlink(missing_ok=True)
            return Outcome(OutcomeKind.FAILED, error=f"{container.name}: {exc}"[:300])
        return Outcome(OutcomeKind.OK, len(members))


class GameMakerPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        hits = [p for name in NAMES for p in probe.find(name, 2)]
        strong = any(
            probe.head(p, 12)[:4] == MAGIC and probe.head(p, 12)[8:12] == FIRST for p in hits
        )
        evidence = ("GameMaker data file (FORM/GEN8 container)",) if strong else ()
        return DetectionResult("gamemaker", 0.9 if strong else 0.0, evidence, "gamemaker")

    def slot_definitions(self):
        return SLOTS

    def backends(self):
        return (GmUnarchiver(), GmWriter())

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.gamemaker" if unarchive_slot == "unarchive.gamemaker" else ""
