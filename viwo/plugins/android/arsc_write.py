"""The way back of decode.arsc: an edited JSON's values written into the original table. Only
values go back: an entry's or a bag item's type and value. Everything else (packages, type
chunks, configurations, entry ids, keys, parents, item names) must stay as decoded; a change
there is refused by naming the first place it differs. Each changed value is written in place
(4 bytes and its type byte); a new string is appended to the global string pool, whose every
original byte is kept, so every other entry still reads what it read. An unchanged JSON gives
the original bytes back."""

import struct

from .arsc import read_table
from .strpool import append_pool
from .values import STRING, parse, type_code


def _difference(a, b, path: str) -> str:
    """The first place two JSON values differ, a value's own `type` and `value` aside; ""."""
    if isinstance(a, dict) and isinstance(b, dict):
        if list(a) != list(b):
            return f"{path}: keys {sorted(set(a) ^ set(b))[:3]} added, removed or reordered"
        free = ("type", "value") if "value" in a else ()
        for key in (k for k in a if k not in free):
            found = _difference(a[key], b[key], f"{path}.{key}")
            if found:
                return found
        return ""
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return f"{path}: {len(a)} items became {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            found = _difference(x, y, f"{path}[{i}]")
            if found:
                return found
        return ""
    return "" if a == b else f"{path}: {a!r} became {b!r}"


def _values(data: dict):
    """((package, type, id, item or -1), the value dict) of every value, in file order."""
    for p, package in enumerate(data["packages"]):
        for t, chunk in enumerate(package["types"]):
            for rid, entry in chunk["entries"].items():
                if "items" in entry:
                    for n, item in enumerate(entry["items"]):
                        yield (p, t, rid, n), item
                else:
                    yield (p, t, rid, -1), entry


class _Changes:
    def __init__(self, table, raw: bytes) -> None:
        self.table, self.raw, self.patches, self.strings, self.notes = table, raw, [], {}, []

    def string(self, text: str) -> int:
        base = len(self.table.pool.strings)
        return self.strings.setdefault(text, base + len(self.strings))

    def add(self, where: tuple, old: dict, new: dict) -> None:
        if not isinstance(new.get("value"), str) or not isinstance(new.get("type"), str):
            raise ValueError(f"{where[2]}: `type` and `value` must stay strings")
        code = type_code(new["type"])
        data = self.string(new["value"]) if code == STRING else parse(code, new["value"])
        at = self.table.spots[where]
        self.patches.append((at, code, data))
        index = struct.unpack_from("<I", self.raw, at + 4)[0]
        if old["type"] == "string" and index in self.table.pool.styled:
            self.notes.append(f"{where[2]}: the edited string has no style spans (bold, links)")


def write_arsc(edited: dict, original: bytes) -> tuple[bytes, list[str]]:
    """(the table carrying the edited values, notes on what they do not keep)."""
    table = read_table(original)
    if not isinstance(edited, dict) or not isinstance(edited.get("packages"), list):
        raise ValueError("the edited file is not a decoded resources.arsc (no `packages`)")
    where = _difference(table.data, edited, "")
    if where:
        raise ValueError(f"only values go back; the structure changed at {where.lstrip('.')}")
    changes = _Changes(table, original)
    for (spot, old), (_, new) in zip(_values(table.data), _values(edited)):
        if (old["type"], old["value"]) != (new.get("type"), new.get("value")):
            changes.add(spot, old, new)
    if not changes.patches:
        return original, []
    out = bytearray(original)
    for at, code, data in changes.patches:
        out[at + 3] = code
        struct.pack_into("<I", out, at + 4, data)
    if changes.strings:
        pool = table.pool
        chunk = append_pool(original, pool, list(changes.strings))
        out[pool.start : pool.start + pool.size] = chunk
        struct.pack_into("<I", out, 4, len(out))
    return bytes(out), changes.notes
