"""The ECMA-335 metadata tables (II.22), walked only as far as ManifestResource (table 0x28):
that table names each embedded resource and gives its offset into the CLI resources blob. To
reach it, every earlier present table's row size is computed from the heap-index sizes (the #~
HeapSizes byte) and the per-table row counts, including the coded-index column widths (II.24.2.6).
`manifest_resources` returns [(name, offset, flags, embedded)] for the resources this assembly
carries itself (Implementation 0)."""

import struct

# coded index groups: name -> (tag bits, referenced table ids)
CODED = {
    "TypeDefOrRef": (2, (2, 1, 27)),
    "HasConstant": (2, (4, 8, 23)),
    "HasCustomAttribute": (
        5,
        (6, 4, 1, 2, 8, 9, 10, 0, 14, 17, 20, 23, 21, 26, 27, 32, 35, 38, 39, 40, 42, 43),
    ),
    "HasFieldMarshal": (1, (4, 8)),
    "HasDeclSecurity": (2, (2, 6, 32)),
    "MemberRefParent": (3, (2, 1, 26, 6, 27)),
    "HasSemantics": (1, (20, 23)),
    "MethodDefOrRef": (1, (6, 10)),
    "MemberForwarded": (1, (4, 6)),
    "Implementation": (2, (38, 35, 39)),
    "CustomAttributeType": (3, (0, 0, 6, 10, 0)),
    "ResolutionScope": (2, (0, 26, 35, 1)),
    "TypeOrMethodDef": (1, (2, 6)),
}
# per table: columns as widths (int bytes), "S"/"G"/"B" heaps, "t<id>" simple index, or a CODED name
SCHEMA = {
    0: (2, "S", "G", "G", "G"),
    1: ("ResolutionScope", "S", "S"),
    2: (4, "S", "S", "TypeDefOrRef", "t4", "t6"),
    3: ("t4",),
    5: ("t6",),
    7: ("t8",),
    19: ("t20",),
    22: ("t23",),
    4: (2, "S", "B"),
    6: (4, 2, 2, "S", "B", "t8"),
    8: (2, 2, "S"),
    9: ("t2", "TypeDefOrRef"),
    10: ("MemberRefParent", "S", "B"),
    11: (2, "HasConstant", "B"),
    12: ("HasCustomAttribute", "CustomAttributeType", "B"),
    13: ("HasFieldMarshal", "B"),
    14: (2, "HasDeclSecurity", "B"),
    15: (2, 4, "t2"),
    16: (4, "t4"),
    17: ("B",),
    18: ("t2", "t20"),
    20: (2, "S", "TypeDefOrRef"),
    21: ("t2", "t23"),
    23: (2, "S", "B"),
    24: (2, "t6", "HasSemantics"),
    25: ("t2", "MethodDefOrRef", "MethodDefOrRef"),
    26: ("S",),
    27: ("B",),
    28: (2, "MemberForwarded", "S", "t26"),
    29: (4, "t4"),
    30: (4, 4),
    31: (4,),
    32: (4, 2, 2, 2, 2, 4, "B", "S", "S"),
    33: (4,),
    34: (4, 4, 4),
    35: (2, 2, 2, 2, 4, "B", "S", "S", "B"),
    36: (4, "t35"),
    37: (4, 4, 4, "t35"),
    38: (4, "S", "B"),
    39: (4, 4, "S", "S", "Implementation"),
    40: (4, 4, "S", "Implementation"),
}


def _heap(heap_sizes: int, bit: int) -> int:
    return 4 if heap_sizes & (1 << bit) else 2


def _coded_width(name: str, rows: dict[int, int]) -> int:
    tag_bits, tables = CODED[name]
    biggest = max((rows.get(t, 0) for t in tables), default=0)
    return 4 if biggest >= (1 << (16 - tag_bits)) else 2


def _col_width(col, rows: dict[int, int], heap_sizes: int) -> int:
    if isinstance(col, int):
        return col
    if col in ("S", "G", "B"):
        return _heap(heap_sizes, {"S": 0, "G": 1, "B": 2}[col])
    if col in CODED:
        return _coded_width(col, rows)
    return 4 if rows.get(int(col[1:]), 0) >= (1 << 16) else 2


def _row_size(table: int, rows: dict[int, int], heap_sizes: int) -> int:
    return sum(_col_width(c, rows, heap_sizes) for c in SCHEMA[table])


def manifest_resources(raw: bytes, tables_off: int) -> list[tuple[str, int, int, bool]]:
    heap_sizes = raw[tables_off + 6]
    valid = struct.unpack_from("<Q", raw, tables_off + 8)[0]
    present = [t for t in range(64) if valid & (1 << t)]
    rows = {}
    pos = tables_off + 24
    for t in present:
        rows[t] = struct.unpack_from("<I", raw, pos)[0]
        pos += 4
    str_wide = _heap(heap_sizes, 0)
    impl_wide = _coded_width("Implementation", rows)
    for t in present:
        if t == 40:
            return _read_mr(raw, pos, rows[40], str_wide, impl_wide, heap_sizes)
        if t > 40:
            break
        if t not in SCHEMA:
            raise ValueError(f"unknown metadata table {t:#x}")
        pos += rows[t] * _row_size(t, rows, heap_sizes)
    return []


def _read_mr(raw, pos, count, str_wide, impl_wide, heap_sizes):
    size = 4 + 4 + str_wide + impl_wide
    out = []
    for i in range(count):
        offset, flags = struct.unpack_from("<II", raw, pos + i * size)
        name_idx = int.from_bytes(raw[pos + i * size + 8 : pos + i * size + 8 + str_wide], "little")
        impl = int.from_bytes(raw[pos + i * size + 8 + str_wide : pos + i * size + size], "little")
        out.append((name_idx, offset, flags, impl == 0))
    return out


def string_at(raw: bytes, strings_off: int, index: int) -> str:
    end = raw.index(b"\x00", strings_off + index)
    return raw[strings_off + index : end].decode("utf-8", "replace")
