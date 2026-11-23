"""`resources.arsc` (the compiled resource table) read into JSON: per package, each type chunk
in file order with its configuration (qualifiers and the raw record), and its entries by
resource id: the key, the value's type and text (values.py), or for a bag (styles, arrays,
plurals) the parent and each item. Dense, sparse and 16-bit-offset type chunks and compact
entries are read. Not shown, kept as they are: type specs (configuration-change flags), shared
library, overlayable and staged-alias chunks, string style spans. Every value's place in the
file is kept beside the JSON for the way back (arsc_write.py)."""

import struct
from dataclasses import dataclass, field

from .arsc_config import qualifiers
from .strpool import Pool, chunk_head, read_pool
from .values import STRING, render, type_name

TABLE, PACKAGE, TYPE, SPEC = 0x0002, 0x0200, 0x0201, 0x0202
NAMED = {0x0203: "shared library", 0x0204: "overlayable", 0x0206: "staged alias"}
SPARSE, OFFSET16 = 0x01, 0x02  # type chunk flags
COMPLEX, COMPACT = 0x0001, 0x0008  # entry flags
NONE32, NONE16 = 0xFFFFFFFF, 0xFFFF
FORMAT = "viwo resources.arsc 1"


@dataclass
class Table:
    pool: Pool
    data: dict  # the JSON
    spots: dict = field(default_factory=dict)  # (package, type, id, item or -1) -> position
    skipped: list = field(default_factory=list)


@dataclass
class _Package:
    index: int
    pid: int
    types: Pool
    keys: Pool
    offset: int  # typeIdOffset
    out: dict


def _value(table: Table, code: int, data: int) -> dict:
    text = table.pool.get(data) if code == STRING else render(code, data)
    return {"type": type_name(code), "value": text if text is not None else ""}


def _offsets(raw: bytes, at: int, head: int, flags: int, count: int) -> list[tuple[int, int]]:
    """(entry index, offset from the entries' start) of every entry present."""
    if flags & SPARSE:
        pairs = struct.unpack_from(f"<{2 * count}H", raw, at + head)
        return [(pairs[i], pairs[i + 1] * 4) for i in range(0, len(pairs), 2)]
    if flags & OFFSET16:
        offs = struct.unpack_from(f"<{count}H", raw, at + head)
        return [(i, o * 4) for i, o in enumerate(offs) if o != NONE16]
    offs = struct.unpack_from(f"<{count}I", raw, at + head)
    return [(i, o) for i, o in enumerate(offs) if o != NONE32]


def _bag(raw: bytes, base: int, size: int, end: int, where: tuple, table: Table) -> dict:
    parent, count = struct.unpack_from("<II", raw, base + 8)
    if base + size + 12 * count > end:
        raise ValueError(f"a bag of {count} items runs past its chunk")
    items = []
    for n in range(count):
        at = base + size + 12 * n
        name, code, data = struct.unpack_from("<I3xBI", raw, at)
        items.append({"name": f"0x{name:08x}", **_value(table, code, data)})
        table.spots[(*where, n)] = at + 4
    return {"parent": f"@0x{parent:08x}", "items": items}


def _entry(raw: bytes, base: int, end: int, where: tuple, table: Table, pkg: _Package) -> dict:
    size, flags = struct.unpack_from("<HH", raw, base)
    if flags & COMPACT:  # key in the first half, type in the flags' high byte, data after
        (data,) = struct.unpack_from("<I", raw, base + 4)
        table.spots[(*where, -1)] = base
        return {"key": pkg.keys.get(size), **_value(table, flags >> 8, data)}
    (key,) = struct.unpack_from("<I", raw, base + 4)
    least = 16 if flags & COMPLEX else 8
    if size < least or base + size + (0 if flags & COMPLEX else 8) > end:
        raise ValueError(f"an entry of {size} bytes at {base} does not fit its chunk")
    out = {"key": pkg.keys.get(key)}
    if flags & COMPLEX:
        return {**out, **_bag(raw, base, size, end, where, table)}
    code, data = struct.unpack_from("<3xBI", raw, base + size)
    table.spots[(*where, -1)] = base + size
    return {**out, **_value(table, code, data)}


def _type(raw: bytes, at: int, head: int, size: int, table: Table, pkg: _Package) -> None:
    tid, flags, _, count, start = struct.unpack_from("<BBHII", raw, at + 8)
    (config_size,) = struct.unpack_from("<I", raw, at + 20)
    width = 4 if flags & SPARSE else (2 if flags & OFFSET16 else 4)
    if 20 + config_size > head or head + width * count > size or start > size:
        raise ValueError(f"type chunk at {at}: its header does not fit")
    config = raw[at + 20 : at + 20 + config_size]
    name = pkg.types.get(tid - 1 - pkg.offset) if tid > pkg.offset else f"type{tid}"
    chunk = {"type": name, "id": tid, "config": qualifiers(config), "config_raw": config.hex()}
    chunk["entries"] = entries = {}
    index = len(pkg.out["types"])
    for n, offset in _offsets(raw, at, head, flags, count):
        rid = f"0x{(pkg.pid << 24) | (tid << 16) | n:08x}"
        base = at + start + offset
        if base + 8 > at + size:
            raise ValueError(f"entry {rid} lies past its chunk")
        entries[rid] = _entry(raw, base, at + size, (pkg.index, index, rid), table, pkg)
    pkg.out["types"].append(chunk)


def _package(raw: bytes, at: int, head: int, size: int, table: Table) -> None:
    if head < 284:
        raise ValueError(f"a package header of {head} bytes")
    (pid,) = struct.unpack_from("<I", raw, at + 8)
    name = raw[at + 12 : at + 268].decode("utf-16-le").split("\0")[0]
    type_at, _, key_at, _ = struct.unpack_from("<4I", raw, at + 268)
    offset = struct.unpack_from("<I", raw, at + 284)[0] if head >= 288 else 0
    end = at + size
    types, keys = read_pool(raw, at + type_at, end), read_pool(raw, at + key_at, end)
    out = {"id": f"0x{pid:02x}", "name": name, "types": []}
    pkg = _Package(len(table.data["packages"]), pid, types, keys, offset, out)
    pos = at + head
    while pos < end:
        kind, chead, csize = chunk_head(raw, pos, end)
        if kind == TYPE:
            _type(raw, pos, chead, csize, table, pkg)
        elif kind not in (SPEC, 0x0001):
            table.skipped.append(f"{name}: a {NAMED.get(kind, f'0x{kind:04x}')} chunk")
        pos += csize
    table.data["packages"].append(out)


def read_table(raw: bytes) -> Table:
    """The whole table; ValueError on anything that is not a whole `resources.arsc`."""
    try:
        return _read(raw)
    except (struct.error, IndexError, UnicodeDecodeError) as exc:
        raise ValueError(f"damaged resources.arsc: {exc}") from None


def _read(raw: bytes) -> Table:
    kind, head, total = chunk_head(raw, 0, len(raw))
    if kind != TABLE:
        raise ValueError("not a resource table (no 0x0002 header)")
    table, pos = None, head
    while pos < total:
        kind, chead, csize = chunk_head(raw, pos, total)
        if kind == 0x0001 and table is None:
            table = Table(read_pool(raw, pos, total), {"format": FORMAT, "packages": []})
        elif kind == PACKAGE and table is not None:
            _package(raw, pos, chead, csize, table)
        elif table is not None:
            table.skipped.append(f"a {NAMED.get(kind, f'0x{kind:04x}')} chunk")
        else:
            raise ValueError("the global string pool does not come first")
        pos += csize
    if table is None:
        raise ValueError("no global string pool")
    table.data["not_shown"] = [
        "type specs (configuration-change flags)",
        "string style spans",
        *table.skipped,
    ]
    return table
