"""decode.locres (doc 16.0c): Unreal localization tables (`.locres`) to JSON, read by ViWo:
`{namespace: {key: text}}` in the file's order, UTF-8. Every version the format has: 0 (legacy,
no magic: texts inline), 1 (compact: texts in a shared array), 2 (keys hashed with CRC32, the
array's reference counts) and 3 (keys hashed with CityHash64); another is refused by name. The
way back (doc 18.3) rewrites the table in its own version: source and key hashes, the order and
each string's storage (ANSI or UTF-16) kept, so an unchanged table comes back byte for byte."""

import json
import struct
import zlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

MAGIC = struct.pack("<4I", 0x7574140E, 0xFC034A67, 0x9D90154A, 0x1B7F37C3)
VERSIONS = ("legacy", "compact", "CRC32 keys", "CityHash64 keys")
SLOT = SlotDefinition("decode.locres", "decode", "unreal", "locres-builtin", suffixes=(".locres",))


@dataclass
class Table:
    version: int
    rows: dict = field(default_factory=dict)  # namespace -> key -> (text, source hash)
    hashes: dict = field(default_factory=dict)  # (namespace,) or (namespace, key) -> hash
    pool: list = field(default_factory=list)  # versions 1+: [text, reference count]
    ansi: set = field(default_factory=set)  # strings the file stores as ANSI
    wide: set = field(default_factory=set)  # strings the file stores as UTF-16


class _Reader:
    def __init__(self, data: bytes, table: Table, at: int = 0) -> None:
        self.data, self.table, self.at = data, table, at

    def take(self, fmt: str) -> int:
        (value,) = struct.unpack_from(fmt, self.data, self.at)
        self.at += struct.calcsize(fmt)
        return value

    def string(self) -> str:
        n = self.take("<i")
        if n == 0:
            return ""
        width = 1 if n > 0 else 2
        end = self.at + abs(n) * width
        if n == -(1 << 31) or end > len(self.data):
            raise ValueError("a string runs past the end")
        raw, self.at = self.data[self.at : end], end
        if any(raw[-width:]):
            raise ValueError("a string without its terminator")
        text = raw[:-width].decode("latin-1" if width == 1 else "utf-16-le")
        (self.table.ansi if width == 1 else self.table.wide).add(text)
        return text

    def key(self, *where: str) -> str:
        if self.table.version >= 2:
            hashed = self.take("<I")
            text = self.string()
            self.table.hashes[(*where, text)] = hashed
            return text
        return self.string()


def _pool(r: _Reader, version: int) -> list:
    offset = r.take("<q")
    if offset == -1:
        return []
    at = _Reader(r.data, r.table, offset)
    return [[at.string(), at.take("<i") if version >= 2 else -1] for _ in range(at.take("<i"))]


def _text(r: _Reader, pool: list) -> str:
    if r.table.version == 0:
        return r.string()
    index = r.take("<i")
    if not 0 <= index < len(pool):
        raise ValueError(f"string index {index} outside the table's {len(pool)} strings")
    return pool[index][0]


def read_table(data: bytes) -> Table:
    """The whole table; ValueError on an unknown version or anything damaged."""
    version = data[16] if data[:16] == MAGIC and len(data) > 16 else 0
    if version >= len(VERSIONS):
        raise ValueError(f"locres version {version} is not known (0 to 3 are)")
    table = Table(version)
    r = _Reader(data, table, 17 if version else 0)
    try:
        table.pool = _pool(r, version) if version else []
        if version >= 2:
            r.take("<I")  # the number of entries, recounted when written
        for _ in range(r.take("<I")):
            ns = r.key()
            keys = table.rows.setdefault(ns, {})
            for _ in range(r.take("<I")):
                key = r.key(ns)
                source = r.take("<I")
                keys[key] = (_text(r, table.pool), source)
    except (struct.error, UnicodeDecodeError) as exc:
        raise ValueError(f"damaged .locres table: {exc}") from None
    return table


def str_crc32(text: str) -> int:
    """Unreal's FCrc::StrCrc32: each UTF-16 unit as four little-endian bytes, CRC-32."""
    units = struct.unpack(f"<{len(text.encode('utf-16-le')) // 2}H", text.encode("utf-16-le"))
    return zlib.crc32(struct.pack(f"<{len(units)}I", *units))


def _fstring(text: str, table: Table) -> bytes:
    if not text:
        return b"\0\0\0\0"
    if text not in table.wide and (text.isascii() or text in table.ansi):
        raw = text.encode("latin-1") + b"\0"
        return struct.pack("<i", len(raw)) + raw
    raw = text.encode("utf-16-le") + b"\0\0"
    return struct.pack("<i", -(len(raw) // 2)) + raw


def _merged(edited: dict, table: Table) -> list:
    """[(namespace, [(key, text, source hash)])]: the table's order, removed keys and namespaces
    left out, new ones at the end with the CRC32 of their own text as source hash."""
    out = []
    for ns, keys in [*table.rows.items(), *((n, {}) for n in edited if n not in table.rows)]:
        given = edited.get(ns, {})
        rows = [(k, given[k], src) for k, (_, src) in keys.items() if k in given]
        rows += [(k, t, str_crc32(t)) for k, t in given.items() if k not in keys]
        new = [k for k in given if k not in keys]
        if table.version == 3 and (new or ns not in table.rows):
            what = f"{ns}/{new[0]}" if new else ns
            raise ValueError(f"{what}: a new key in a version 3 table needs its CityHash64")
        if ns in edited:  # a namespace the edit removed is left out
            out.append((ns, rows))
    return out


def _new_pool(table: Table, merged: list) -> list:
    """The string array: the original's in its order with reference counts moved by the edit
    (a string no row uses any more left out), then each new text in the order of first use."""
    uses = Counter(text for _, rows in merged for _, text, _ in rows)
    before = Counter(text for keys in table.rows.values() for text, _ in keys.values())
    pool = [
        [text, ref + uses[text] - before[text] if ref != -1 else -1]
        for text, ref in table.pool
        if uses[text] or not before[text]
    ]
    known = {text for text, _ in pool}
    for text in uses:
        if text not in known:
            pool.append([text, uses[text] if table.version >= 2 else -1])
            known.add(text)
    return pool


def _key(table: Table, where: tuple, text: str) -> bytes:
    if table.version < 2:
        return _fstring(text, table)
    hashed = table.hashes.get((*where, text), str_crc32(text))
    return struct.pack("<I", hashed) + _fstring(text, table)


def write_locres(edited: dict, original: bytes) -> bytes:
    """The original table carrying the edited texts, in its own version and layout."""
    table = read_table(original)
    merged, pool = _merged(edited, table), []
    index: dict = {}
    if table.version:
        pool = _new_pool(table, merged)
        for i, (text, _) in enumerate(pool):
            index.setdefault(text, i)
    body = bytearray(struct.pack("<I", len(merged)))
    for ns, rows in merged:
        body += _key(table, (), ns) + struct.pack("<I", len(rows))
        for key, text, source in rows:
            body += _key(table, (ns,), key) + struct.pack("<I", source)
            body += struct.pack("<i", index[text]) if table.version else _fstring(text, table)
    if not table.version:
        return bytes(body)
    if table.version >= 2:
        body[:0] = struct.pack("<I", sum(len(rows) for _, rows in merged))
    head = MAGIC + bytes([table.version])
    strings = b"".join(
        _fstring(t, table) + (struct.pack("<i", ref) if table.version >= 2 else b"")
        for t, ref in pool
    )
    at = len(head) + 8 + len(body)
    return head + struct.pack("<q", at) + bytes(body) + struct.pack("<i", len(pool)) + strings


def read_locres(data: bytes) -> dict:
    """{namespace: {key: text}}; ValueError on anything that is not a whole table."""
    table = read_table(data)
    return {ns: {k: text for k, (text, _) in keys.items()} for ns, keys in table.rows.items()}


class LocresBuiltin(Decoder):
    backend_id, owner, license = "locres-builtin", "unreal", "MIT"
    parses_untrusted_in_process = True  # doc 8.4
    encodes = True  # the edited JSON back to the table (doc 18.3)

    def refuses(self, original: Path) -> str:
        with open(original, "rb") as fh:
            head = fh.read(17)
        if head[:16] == MAGIC and len(head) > 16 and head[16] >= len(VERSIONS):
            return f"{original.name}: locres version {head[16]} is not known (0 to 3 are)"
        return ""

    def encode(self, edited: Path, original: Path, out: Path, ctx) -> Outcome:
        try:
            rows = json.loads(edited.read_text(encoding="utf-8"))
            if not isinstance(rows, dict) or not all(
                isinstance(keys, dict) and all(isinstance(t, str) for t in keys.values())
                for keys in rows.values()
            ):
                raise ValueError("the edited table must stay {namespace: {key: text}}")
            out.write_bytes(write_locres(rows, original.read_bytes()))
        except (OSError, ValueError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{edited.name}: {exc}")
        return Outcome(OutcomeKind.OK, 1)

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        try:
            rows = read_locres(path.read_bytes())
        except (OSError, ValueError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{path.name}: {exc}")
        target = dest / f"{path.name}.json"
        target.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        return Outcome(OutcomeKind.OK, 1)
