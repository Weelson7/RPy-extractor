"""pack.rcc (doc 18): a `.rcc` rebuilt in the patched copy with the edited resources. QResource
loads nothing over a `.rcc`, so the container is rewritten (doc 18.3); the name tree and node
tree are kept, only the data is laid out again (rcc.build), so an unchanged resource comes back
byte for byte. Read back after writing."""

from pathlib import Path

from viwo.contracts.slots import Packer, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

from . import rcc

SLOT = SlotDefinition("pack.rcc", "pack", "qt", "rcc-writer")


class RccWriter(Packer):
    backend_id, owner, license = "rcc-writer", "qt", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: the read-back parses the written rcc

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        try:
            raw = container.read_bytes()
            paths = {p for p, _, _ in rcc.extract(raw)}
            edits = {m.replace("\\", "/"): s.read_bytes() for m, s in members.items()}
            unknown = sorted(set(edits) - paths)
            container.write_bytes(rcc.build(raw, {m: d for m, d in edits.items() if m in paths}))
        except (OSError, ValueError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"rcc not rebuilt: {exc}"[:300])
        notes = [f"{len(unknown)} member(s) not in the resource: not added"] * bool(unknown)
        return Outcome(OutcomeKind.OK, len(edits) - len(unknown), notes=tuple(notes))

    def verify(self, output: Path, members: dict[str, Path], ctx) -> list[str]:
        found = {p: data for p, data, _ in rcc.extract(output.read_bytes())}
        bad = []
        for member, source in members.items():
            path = member.replace("\\", "/")
            if path in found and found[path] != source.read_bytes():
                bad.append(member)
        return bad
