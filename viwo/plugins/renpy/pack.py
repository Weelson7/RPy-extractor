"""RPA-3.0 writer for the round trip: rebuild an archive with edited members replaced.

Unchanged members are streamed from the original; the index is pickled by us (protocol 2,
plain tuples), so nothing untrusted is ever unpickled.
"""

import os
import pickle
import zlib
from pathlib import Path

from viwo.contracts.slots import Packer
from viwo.contracts.types import Outcome, OutcomeKind

from .rpa import read_index

KEY = 0xDEADBEEF
HEADER = 34  # "RPA-3.0 " + 16 hex + " " + 8 hex + "\n"


def _copy(src, out, offset: int, length: int) -> None:
    src.seek(offset)
    while length > 0:
        chunk = src.read(min(1 << 20, length))
        if not chunk:
            break
        out.write(chunk)
        length -= len(chunk)


def write_rpa(original: Path, members: dict[str, Path], target: Path) -> int:
    """Write the rebuilt archive to target; returns the member count."""
    with open(original, "rb") as src:
        index = read_index(src)
        names = list(index) + [m for m in members if m not in index]
        table: dict[str, list[tuple[int, int, bytes]]] = {}
        with open(target, "wb") as out:
            out.write(b"\0" * HEADER)
            for name in names:
                start = out.tell()
                if name in members:
                    out.write(members[name].read_bytes())
                else:
                    for offset, length, prefix in index[name]:
                        out.write(prefix)
                        _copy(src, out, offset, length - len(prefix))
                table[name] = [(start ^ KEY, (out.tell() - start) ^ KEY, b"")]
            where = out.tell()
            out.write(zlib.compress(pickle.dumps(table, protocol=2)))
            out.seek(0)
            out.write(f"RPA-3.0 {where:016x} {KEY:08x}\n".encode())
    return len(names)


class RpaWriter(Packer):
    backend_id, owner, license = "rpa-writer", "renpy", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def pack(self, container, members, ctx) -> Outcome:
        temp = container.with_name(container.name + ".viwo-tmp")
        try:
            count = write_rpa(container, members, temp)
            os.replace(temp, container)
        except (OSError, ValueError, zlib.error, pickle.UnpicklingError) as exc:
            temp.unlink(missing_ok=True)
            return Outcome(OutcomeKind.FAILED, error=str(exc)[:300])
        return Outcome(OutcomeKind.OK, count)
