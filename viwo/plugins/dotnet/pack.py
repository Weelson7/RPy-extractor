"""pack.resources (doc 18): an edited managed resource written back into a .NET assembly in the
patched copy, in place. A resource lives in the CLI resources blob at its ManifestResource
offset as `[u32 length][bytes]`; replacing it with bytes of the SAME length leaves every offset,
the metadata and the PE layout untouched, so the assembly stays valid and reads back with the
edit. A different length would mean rewriting the ManifestResource offsets, the CLI header size
and the section table (not done here): that member is refused by name, never written wrong."""

import struct
from pathlib import Path

from viwo.contracts.slots import Packer, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

from . import resources

SLOT = SlotDefinition("pack.resources", "pack", "dotnet", "resources-writer")


class ResourcesWriter(Packer):
    backend_id, owner, license = "resources-writer", "dotnet", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: the read-back parses the written assembly

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        try:
            raw = bytearray(container.read_bytes())
            table = {
                n: (off, length) for n, off, length, emb in resources.listed(bytes(raw)) if emb
            }
            res_off = resources.blob_offset(bytes(raw))
            written, refused, unknown = _apply(raw, members, table, res_off)
            container.write_bytes(bytes(raw))
        except (OSError, ValueError, struct.error) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"resources not written: {exc}"[:300])
        notes = []
        if refused:
            notes.append(
                f"{len(refused)} resource(s) whose size changed: not written ("
                + ", ".join(refused)
                + ")"
            )
        if unknown:
            notes.append(f"{len(unknown)} member(s) with no matching resource: not written")
        return Outcome(OutcomeKind.OK, written, notes=tuple(notes))

    def verify(self, output: Path, members: dict[str, Path], ctx) -> list[str]:
        found = {name: data for name, data in resources.extract(output.read_bytes())}
        bad = []
        for member, source in members.items():
            name = member.replace("\\", "/").split("resources/", 1)[-1]
            data = source.read_bytes()
            if name in found and len(data) == len(found.get(name, b"")) and found[name] != data:
                bad.append(member)
        return bad


def _apply(raw: bytearray, members, table, res_off):
    """Overwrite same-size resources in place; return (written, refused names, unknown members)."""
    written, refused, unknown = 0, [], []
    for member, source in members.items():
        name = member.replace("\\", "/").split("resources/", 1)[-1]
        data = source.read_bytes()
        if name not in table:
            unknown.append(member)
        elif len(data) != table[name][1]:
            refused.append(name)
        else:
            at = res_off + table[name][0] + 4
            raw[at : at + len(data)] = data
            written += 1
    return written, refused, unknown
