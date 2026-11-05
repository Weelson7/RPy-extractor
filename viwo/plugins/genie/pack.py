"""pack.drs (doc 18): a Genie DRS archive rebuilt in the patched copy with the edited members:
the header, every table and every entry stay in place (`<id>.<ext>` names the entry), the data
is laid out again. Members a DRS does not list are said, not added."""

from __future__ import annotations

import os
import struct
from pathlib import Path

from viwo.contracts.slots import Packer, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

SLOT = SlotDefinition("pack.drs", "pack", "genie", "drs-writer")


def write_drs(original: Path, members: dict[str, Path], target: Path) -> int:
    from . import HEADER, entries

    with open(original, "rb") as fh:
        head = fh.read(HEADER + 8)
        tables, _ = struct.unpack_from("<II", head, HEADER)
        specs = [struct.unpack("<4sII", fh.read(12)) for _ in range(tables)]
        fh.seek(0)
        rows = list(entries(fh))
        blobs = []
        for name, offset, size in rows:
            if name in members:
                blobs.append(members[name].read_bytes())
            else:
                fh.seek(offset)
                blobs.append(fh.read(size))
    entries_at = HEADER + 8 + 12 * tables
    data_at = entries_at + 12 * len(rows)
    out_specs, out_rows, at, i = b"", b"", data_at, 0
    for kind, _offset, count in specs:
        out_specs += struct.pack("<4sII", kind, entries_at + len(out_rows), count)
        for name, _, _ in rows[i : i + count]:
            file_id = int(name.split(".", 1)[0])
            out_rows += struct.pack("<III", file_id, at, len(blobs[i]))
            at += len(blobs[i])
            i += 1
    with open(target, "wb") as out:
        out.write(head[:HEADER] + struct.pack("<II", tables, data_at) + out_specs + out_rows)
        for blob in blobs:
            out.write(blob)
    return len(rows)


class DrsWriter(Packer):
    backend_id, owner, license = "drs-writer", "genie", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        temp = container.with_name(container.name + ".viwo-tmp")
        try:
            count = write_drs(container, members, temp)
            os.replace(temp, container)
        except (OSError, ValueError, struct.error) as exc:
            temp.unlink(missing_ok=True)
            return Outcome(OutcomeKind.FAILED, error=f"DRS not rebuilt: {exc}"[:300])
        return Outcome(OutcomeKind.OK, count)
