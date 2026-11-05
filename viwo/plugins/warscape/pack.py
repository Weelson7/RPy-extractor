"""pack.pack (doc 18): edited members of a Total War pack written as a new pack of type movie
in the game's `data/` folder, which Warscape loads by itself over the release packs; the game's
packs stay as they are. PFH4 (Empire through Attila, Rome II, Thrones of Britannia): the layout
read back on Rome II. A PFH5/PFH6 game (Warhammer II and later) is refused by name until its
index layout is verified on a real install."""

from __future__ import annotations

import struct
import time
from pathlib import Path

from viwo.contracts.slots import Packer, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

SLOT = SlotDefinition("pack.pack", "pack", "warscape", "movie-pack")
MOVIE = 4  # pack type: loaded by the game from data/, over the release packs
PREFIX = "viwo_"


def write_pack(members: dict[str, bytes], target: Path) -> None:
    """A PFH4 movie pack: header, no dependencies, the index (size, path), the data."""
    index, body = bytearray(), bytearray()
    for name, data in sorted(members.items()):
        index += struct.pack("<I", len(data)) + name.replace("/", "\\").encode("utf-8") + b"\0"
        body += data
    head = b"PFH4" + struct.pack("<6I", MOVIE, 0, 0, len(members), len(index), int(time.time()))
    target.write_bytes(head + bytes(index) + bytes(body))


class MoviePack(Packer):
    backend_id, owner, license = "movie-pack", "warscape", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: reads the container header, the read-back
    override = True  # the movie pack holds the edits; the release packs keep the rest

    def output_for(self, container: Path) -> Path:
        return container.with_name(f"{PREFIX}{container.stem}.pack")

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        with open(container, "rb") as fh:
            magic = fh.read(4)
        if magic != b"PFH4":
            why = f"{magic.decode('latin-1')} packs: the index layout is not verified yet"
            return Outcome(OutcomeKind.FAILED, error=why)
        target = self.output_for(container)
        try:
            write_pack({m: p.read_bytes() for m, p in members.items()}, target)
        except (OSError, ValueError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"movie pack not written: {exc}"[:300])
        return Outcome(OutcomeKind.OK, len(members), notes=(f"edits in data/{target.name}",))

    def verify(self, output: Path, members: dict[str, Path], ctx) -> list[str]:
        from . import entries

        with open(output, "rb") as fh:
            found = {}
            for name, offset, size in entries(fh):
                fh.seek(offset)
                found[name] = fh.read(size)
        return sorted(m for m, p in members.items() if found.get(m) != p.read_bytes())
