"""export.warscape (doc 16.0c): Total War DB tables to JSON for every Warscape game, read by ViWo
from the game's packs with the game's RPFM schema (MIT, pinned per game, installed when asked):
`db/<table>/<file>.json`, one object per row. A table whose version the schema does not define is
tried against the table's other definitions (decoding to the last byte is the check); a table
the schema lacks or that no definition reads is counted and named."""

from __future__ import annotations

import json
import re
import struct
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.slots import Exporter, SlotDefinition
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

SLOT = SlotDefinition("export.warscape", "export", "warscape", "db-builtin")
GAMES = {  # the game's executable -> its RPFM schema
    "rome2": "rom2", "attila": "att", "warhammer": "wh", "warhammer2": "wh2", "warhammer3": "wh3",
    "threekingdoms": "3k", "troy": "troy", "pharaoh": "ph", "shogun2": "sho2", "empire": "emp",
    "napoleon": "nap", "thrones": "tob", "arena": "are",
}  # fmt: skip
TABLE = re.compile(r'^ {8}"([^"]+)": \[$')
VERSION = re.compile(r"^ {16}version: (-?\d+),$")
NAME = re.compile(r'^ {24}name: "([^"]*)",$')
TYPE = re.compile(r"^ {24}field_type: ([A-Za-z0-9]+)")
GUID, VERSIONED = b"\xfd\xfe\xfc\xff", b"\xfc\xfd\xfe\xff"
NUMBERS = {"F32": "<f", "F64": "<d", "I16": "<h", "I32": "<i", "I64": "<q"}


def schema_spec(game: str) -> DependencySpec:
    dep = f"rpfm-schema-{game.replace('_', '-')}"
    return DependencySpec(dep, f"RPFM schema ({game})", hint=f"`viwo install {dep}`")


def game_of(game_root: Path) -> str:
    for exe in sorted(game_root.glob("*.exe")):
        key = GAMES.get(exe.stem.lower())
        if key == "ph" and "dynast" in game_root.name.lower():
            return "ph_dyn"
        if key:
            return key
    return ""


def schema(text: str) -> dict[str, dict[int, list[tuple[str, str]]]]:
    """table -> version -> [(field, type)] from an RPFM schema (`.ron`), read by its layout;
    localised fields live in the .loc tables, not in the binary, and are left out."""
    out: dict = {}
    table, fields, name = "", None, ""
    for line in text.splitlines():
        if m := TABLE.match(line):
            table = m.group(1)
        elif m := VERSION.match(line):
            fields = out.setdefault(table, {}).setdefault(int(m.group(1)), [])
        elif line.startswith(" " * 16 + "localised_fields:"):
            fields = None
        elif m := NAME.match(line):
            name = m.group(1)
        elif (m := TYPE.match(line)) and fields is not None:
            fields.append((name, m.group(1)))
    return out


def _value(data: bytes, at: int, kind: str):
    if kind == "Boolean":
        return bool(data[at]), at + 1
    if kind in NUMBERS:
        return struct.unpack_from(NUMBERS[kind], data, at)[0], at + struct.calcsize(NUMBERS[kind])
    if kind.startswith("Optional"):
        return (None, at + 1) if not data[at] else _value(data, at + 1, kind[8:])
    if kind in ("StringU8", "StringU16"):
        (n,) = struct.unpack_from("<H", data, at)
        wide = 2 if kind == "StringU16" else 1
        raw = data[at + 2 : at + 2 + wide * n]
        if len(raw) != wide * n:
            raise ValueError("string runs past the end")
        return raw.decode("utf-16-le" if wide == 2 else "utf-8"), at + 2 + wide * n
    raise ValueError(f"field type {kind} is not read yet")


def header(data: bytes) -> tuple[int, int, int]:
    """(version, rows, offset of the first row)."""
    at, version = 0, 0
    if data[:4] == GUID:
        at = 6 + 2 * struct.unpack_from("<H", data, 4)[0]
    if data[at : at + 4] == VERSIONED:
        version, at = struct.unpack_from("<i", data, at + 4)[0], at + 8
    return version, struct.unpack_from("<I", data, at + 1)[0], at + 5


def rows(data: bytes, fields: list[tuple[str, str]]) -> list[dict]:
    _version, count, at = header(data)
    if count > len(data) or (count and not fields):  # a row takes at least a byte
        raise ValueError(f"{count} row(s) cannot fit in {len(data)} byte(s)")
    out = []
    for _ in range(count):
        row = {}
        for name, kind in fields:
            row[name], at = _value(data, at, kind)
        out.append(row)
    if at != len(data):
        raise ValueError(f"{len(data) - at} byte(s) after the last row")
    return out


def read_table(data: bytes, versions: dict[int, list]) -> list[dict]:
    """The table's own version first, then every other definition, newest first."""
    try:
        version = header(data)[0]
    except struct.error:
        raise ValueError("no DB table header") from None
    order = ([versions[version]] if version in versions else []) + [
        f for v, f in sorted(versions.items(), reverse=True) if v != version
    ]
    for fields in order:
        try:
            return rows(data, fields)
        except (ValueError, struct.error, IndexError, UnicodeDecodeError):
            continue
    raise ValueError("no definition of the schema reads it")


class DbBuiltin(Exporter):
    backend_id, owner, license = "db-builtin", "warscape", "MIT"
    parses_untrusted_in_process = True  # doc 8.4

    def dependencies(self):
        return tuple(schema_spec(g) for g in sorted({*GAMES.values(), "ph_dyn"}))

    def available(self, os):
        return True, ""  # without the schema the tables are named, the rest of the export runs

    def export(self, ctx) -> Outcome:
        game = game_of(ctx.game_root)
        tool = ctx.os.tools.locate(schema_spec(game)) if game else None
        if tool is None:
            why = f"needs {schema_spec(game).hint}" if game else "game not recognised"
            return Outcome(OutcomeKind.OK, 0, notes=(f"DB tables not read: {why}",))
        tables = schema(Path(tool.path).read_text(encoding="utf-8"))
        written, unread = _export_packs(ctx, tables)
        notes = (
            (f"{len(unread)} DB table(s) not read, e.g. {', '.join(unread[:3])}",) if unread else ()
        )
        ctx.log(f"{written} DB table(s) to JSON (db/)", stage="export")
        return Outcome(OutcomeKind.OK, written, notes=notes)


def _export_packs(ctx, tables: dict) -> tuple[int, list[str]]:
    from . import entries  # the pack index reader lives with the plugin

    written, unread = 0, []
    for pack in ws.files(ctx.game_root, "*.pack"):
        try:
            with open(pack, "rb") as fh:
                for name, offset, size in entries(fh):
                    parts = name.split("/")
                    if len(parts) != 3 or parts[0].lower() != "db" or ctx.cancel.cancelled:
                        continue
                    fh.seek(offset)
                    ok = _one(ctx, parts[1], parts[2], fh.read(size), tables)
                    written += ok
                    unread += [] if ok else [parts[1]]
        except (OSError, ValueError, struct.error):
            unread.append(pack.name)
    return written, unread


def _one(ctx, table: str, file: str, data: bytes, tables: dict) -> bool:
    try:
        found = read_table(data, tables[table]) if table in tables else None
    except (ValueError, struct.error, IndexError):
        found = None
    rel = ws.safe_member(f"db/{table}/{file or 'table'}.json")  # names come from the pack
    if found is None or rel is None:
        return False
    target = ctx.staging.joinpath(*rel.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target = ws.next_free(target)
    target.write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
    return True
