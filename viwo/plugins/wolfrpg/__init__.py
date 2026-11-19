"""Wolf RPG Editor games: the DXArchive-derived `Data.wolf` / `*.wolf` containers (DxLib's
format), read and rebuilt first-party. `unarchive.wolf` extracts every raw member of a version 6
archive (DXA-compressed members are refused by name: ViWo's DXA decoder is unverified); a key the
user gives (`decryption_key`) is verified against the header before use (D18). `pack.wolf`
rebuilds the archive with the edited members, stored raw, read back by VERIFY. Not verified
against a real Wolf RPG game (none at hand): the format is implemented from its public
description."""

import os
import struct
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.plugin import EnginePlugin, GameProbe, PluginManifest, PluginOption
from viwo.contracts.slots import Packer, SlotDefinition, Unarchiver
from viwo.contracts.types import DetectionResult, Outcome, OutcomeKind

from .wolf import MAGIC, NONE, key_bytes, read_archive
from .wolf_pack import write_archive

MANIFEST = PluginManifest(
    "wolfrpg",
    "Wolf RPG",
    "0.1.0",
    engine_type="wolfrpg",
    priority=15,
    description="Wolf RPG Editor games: Data.wolf / *.wolf archives (DXArchive) in and out",
    capabilities=("detect", "unpack", "pack"),
    options=(PluginOption("decryption_key", "Archive key", kind="secret"),),
)
SLOTS = (
    SlotDefinition(
        "unarchive.wolf",
        "unarchive",
        "wolfrpg",
        "wolf-builtin",
        suffixes=(".wolf",),
        magic=(struct.pack("<H", MAGIC),),
    ),
    SlotDefinition("pack.wolf", "pack", "wolfrpg", "wolf-writer"),
)
MARKERS = ("data.wolf", "basicdata.wolf", "gurugurusmf4.dll")


def _key(ctx) -> bytes:
    return key_bytes(str((ctx.options or {}).get("decryption_key", "") or ""))


class WolfUnarchiver(Unarchiver):
    backend_id, owner, license = "wolf-builtin", "wolfrpg", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def extract(self, archive: Path, dest: Path, ctx) -> Outcome:
        try:
            body, entries = read_archive(archive.read_bytes(), _key(ctx))
        except (OSError, ValueError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=str(exc))
        names, written, packed = ws.Names(dest), 0, 0
        for entry in entries:
            if ctx.cancel.cancelled:
                break
            if entry.pressed != NONE:  # DXA-compressed: ViWo's decoder is unverified, so refused
                packed += 1
                continue
            target = names.target(entry.path)
            if target is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body[entry.offset : entry.offset + entry.size])
            written += 1
        notes = [f"{packed} DXA-compressed member(s) refused: unverified decoder"] if packed else []
        return Outcome(OutcomeKind.OK, written, notes=tuple([*names.save(), *notes]))


class WolfWriter(Packer):
    backend_id, owner, license = "wolf-writer", "wolfrpg", "MIT"
    parses_untrusted_in_process = True

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        key = _key(ctx)
        temp = container.with_name(container.name + ".viwo-tmp")
        try:
            body, entries = read_archive(container.read_bytes(), key)
            out = {}
            for entry in entries:
                if entry.pressed != NONE:
                    raise ValueError(f"{entry.path}: DXA-compressed member cannot be rebuilt")
                edited = members.get(entry.path)
                out[entry.path] = (
                    edited.read_bytes()
                    if edited
                    else body[entry.offset : entry.offset + entry.size]
                )
            temp.write_bytes(write_archive(out, key))
            os.replace(temp, container)
        except (OSError, ValueError, struct.error) as exc:
            temp.unlink(missing_ok=True)
            return Outcome(OutcomeKind.FAILED, error=f"archive not rebuilt: {exc}"[:300])
        new = sorted(set(members) - set(out))
        notes = (f"{len(new)} new member(s) not in the archive: not added",) if new else ()
        return Outcome(OutcomeKind.OK, len(out), notes=notes)


class WolfRpgPlugin(EnginePlugin):
    manifest = MANIFEST

    def detect(self, probe: GameProbe) -> DetectionResult:
        evidence = []
        if probe.with_suffix(".wolf")[:1]:
            evidence.append("Wolf RPG / DXArchive .wolf files")
        if probe.has_name(*MARKERS):
            evidence.append("Wolf RPG runtime / archive files")
        score = 0.9 if evidence else 0.0
        return DetectionResult("wolfrpg", score, tuple(evidence), "wolfrpg")

    def slot_definitions(self):
        return SLOTS

    def backends(self):
        return (WolfUnarchiver(), WolfWriter())

    def pack_slot(self, unarchive_slot: str) -> str:
        return "pack.wolf" if unarchive_slot == "unarchive.wolf" else ""
