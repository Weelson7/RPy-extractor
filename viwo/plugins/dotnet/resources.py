"""The managed resources of a .NET assembly, wiring pe.py (where things are) and meta.py (the
ManifestResource table). `listed` names every resource with its blob offset, length and whether
it is embedded (Implementation 0) or linked in another file; `extract` yields the embedded ones'
bytes. Nothing here rewrites: pack.py does the in-place, same-size write back."""

import struct

from . import meta, pe


def _context(raw: bytes) -> tuple[int, int, int, int]:
    """(resources offset, resources size, tables offset, #Strings offset)."""
    meta_off, _, res_off, res_size, _ = pe.cli_header(raw)
    st = pe.streams(raw, meta_off)
    tables = st.get("#~") or st.get("#-")
    if tables is None:
        raise ValueError("no metadata tables stream")
    return res_off, res_size, tables[0], st["#Strings"][0]


def blob_offset(raw: bytes) -> int:
    return pe.cli_header(raw)[2]


def listed(raw: bytes) -> list[tuple[str, int, int, bool]]:
    """[(name, blob offset, length, embedded)]; length 0 for a linked (non-embedded) resource."""
    res_off, res_size, tables_off, strings = _context(raw)
    out = []
    for name_idx, offset, _, embedded in meta.manifest_resources(raw, tables_off):
        name = meta.string_at(raw, strings, name_idx)
        if not embedded:
            out.append((name, offset, 0, False))
        elif 0 <= offset + 4 <= res_size:
            (length,) = struct.unpack_from("<I", raw, res_off + offset)
            if offset + 4 + length <= res_size:
                out.append((name, offset, length, True))
    return out


def extract(raw: bytes):
    """(name, bytes) for every embedded resource."""
    res_off, _, _, _ = _context(raw)
    for name, offset, length, embedded in listed(raw):
        if embedded:
            yield name, raw[res_off + offset + 4 : res_off + offset + 4 + length]
