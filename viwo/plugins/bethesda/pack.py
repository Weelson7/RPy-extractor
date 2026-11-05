"""pack.bsa / pack.ba2 (doc 18): edited members of a Bethesda archive written as loose files in
the game's `Data/` folder, where Gamebryo and Creation Engine games load a loose file over the
same path in any archive (Fallout 4 and later also want `bInvalidateOlderFiles=1` and an empty
`sResourceDataDirsFinal=` in their ini: said in the notes). The archives stay as they are."""

from __future__ import annotations

from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.slots import Packer, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

SLOTS = (
    SlotDefinition("pack.bsa", "pack", "bethesda", "loose-override"),
    SlotDefinition("pack.ba2", "pack", "bethesda", "loose-override"),
)
INI = "Fallout 4 and later load loose files only with bInvalidateOlderFiles=1 and an empty "
INI += "sResourceDataDirsFinal= under [Archive] in the game's custom ini"


class LooseOverride(Packer):
    backend_id, owner, license = "loose-override", "bethesda", "MIT"
    override = True  # the loose files hold the edits; the archive keeps the rest

    def output_for(self, container: Path) -> Path:
        return container.parent  # Data/, beside the archive

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        written, unsafe = 0, 0
        for member, source in members.items():
            target = ws.member_path(container.parent, member)
            if target is None:
                unsafe += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            written += 1
        notes = [f"edits as loose files in {container.parent.name}/, over the archives"]
        notes += [INI] if container.suffix.lower() == ".ba2" else []
        notes += [f"{unsafe} member(s) whose path leads out of the folder: not written"] * bool(
            unsafe
        )
        kind = OutcomeKind.OK if written or not members else OutcomeKind.FAILED
        return Outcome(
            kind, written, error="" if written else "nothing written", notes=tuple(notes)
        )

    def verify(self, output: Path, members: dict[str, Path], ctx) -> list[str]:
        bad = []
        for member, source in members.items():
            target = ws.member_path(output, member)
            if target is None or not target.is_file() or target.read_bytes() != source.read_bytes():
                bad.append(member)
        return sorted(bad)
