"""L3: Total War DB tables (export.warscape). Any table written with a random schema is read back
exactly, with or without its GUID and version markers; a table whose version the schema lacks is
read by the table's other definitions; a cut or wrong table is a named failure; the schema's
localised fields are left out; the exporter reads only `db/` members of every pack, names the
tables it could not read and the schema a game needs. Verified on real data: Rome II's
data_rome2.pack (611 of 624 tables with a schema decoded, 332,081 rows)."""

from __future__ import annotations

import json
import random
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.test_containers import pack
from viwo.contracts import CancelToken
from viwo.plugins.warscape import db

KINDS = [
    "Boolean",
    "F32",
    "I32",
    "I64",
    "StringU8",
    "StringU16",
    "OptionalStringU8",
    "OptionalStringU16",
]


def encode(kind: str, value) -> bytes:
    if kind == "Boolean":
        return bytes([value])
    if kind in db.NUMBERS:
        return struct.pack(db.NUMBERS[kind], value)
    if kind.startswith("Optional"):
        return b"\x00" if value is None else b"\x01" + encode(kind[8:], value)
    raw = value.encode("utf-16-le" if kind == "StringU16" else "utf-8")
    return struct.pack("<H", len(raw) // (2 if kind == "StringU16" else 1)) + raw


def random_value(rng: random.Random, kind: str):
    if kind == "Boolean":
        return rng.random() < 0.5
    if kind == "F32":
        return struct.unpack("<f", struct.pack("<f", rng.uniform(-1e3, 1e3)))[0]
    if kind in ("I32", "I64"):
        return rng.randint(-(2**31), 2**31 - 1)
    if kind.startswith("Optional") and rng.random() < 0.3:
        return None
    return "".join(rng.choice("abc_xyzé漢") for _ in range(rng.randint(0, 9)))


def table(fields, rows, version=None, guid=True) -> bytes:
    out = db.GUID + struct.pack("<H", 4) + "abcd".encode("utf-16-le") if guid else b""
    out += db.VERSIONED + struct.pack("<i", version) if version is not None else b""
    out += b"\x01" + struct.pack("<I", len(rows))
    for row in rows:
        out += b"".join(encode(kind, row[name]) for name, kind in fields)
    return out


def ron(tables: dict[str, dict[int, list]]) -> str:
    lines = ["(", "    version: 5,", "    definitions: {"]
    for name, versions in tables.items():
        lines.append(f'        "{name}": [')
        for version, fields in versions.items():
            lines += [
                "            (",
                f"                version: {version},",
                "                fields: [",
            ]
            for field, kind in fields:
                lines += [
                    "                    (",
                    f'                        name: "{field}",',
                    f"                        field_type: {kind},",
                    "                    ),",
                ]
            lines += [
                "                ],",
                "                localised_fields: [",
                "                    (",
                '                        name: "title",',
                "                        field_type: StringU16,",
                "                    ),",
                "                ],",
                "            ),",
            ]
        lines.append("        ],")
    return "\n".join(lines + ["    },", ")"]) + "\n"


class TableTests(unittest.TestCase):
    def test_every_random_table_reads_back_exactly(self) -> None:
        rng = random.Random(21)
        for _ in range(40):
            fields = [(f"f{i}", rng.choice(KINDS)) for i in range(rng.randint(1, 8))]
            rows = [{n: random_value(rng, k) for n, k in fields} for _ in range(rng.randint(0, 15))]
            version = rng.choice([None, 0, 3, 7])
            data = table(fields, rows, version, guid=rng.random() < 0.7)
            self.assertEqual(db.read_table(data, {version or 0: fields}), rows)

    def test_a_missing_version_falls_back_and_damage_is_named(self) -> None:
        old, new = [("key", "StringU8")], [("key", "StringU8"), ("n", "I32")]
        data = table(new, [{"key": "a", "n": 4}], version=9)  # the schema knows 2 and 5
        self.assertEqual(db.read_table(data, {2: old, 5: new}), [{"key": "a", "n": 4}])
        for broken in (data[:-1], data + b"\0", data[:10]):
            with self.assertRaises(ValueError):
                db.read_table(broken, {5: new})
        with self.assertRaises(ValueError):
            db.read_table(table([("x", "Boolean")], [{"x": True}]), {0: [("x", "ColourRGB")]})

    def test_the_schema_leaves_localised_fields_out(self) -> None:
        text = ron(
            {"units_tables": {3: [("key", "StringU8"), ("cost", "I32")]}, "empty_tables": {0: []}}
        )
        self.assertEqual(
            db.schema(text),
            {"units_tables": {3: [("key", "StringU8"), ("cost", "I32")]}, "empty_tables": {0: []}},
        )


class ExportTests(unittest.TestCase):
    def ctx(self, root: Path, schema_path):
        tool = SimpleNamespace(path=str(schema_path)) if schema_path else None
        return SimpleNamespace(
            game_root=root / "game",
            staging=root / "out",
            cancel=CancelToken(),
            os=SimpleNamespace(tools=SimpleNamespace(locate=lambda s: tool)),
            log=lambda *a, **k: None,
        )

    def test_only_db_members_are_read_and_every_unread_table_is_named(self) -> None:
        fields = [("key", "StringU8"), ("cost", "I32")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "game" / "data").mkdir(parents=True)
            (root / "game" / "Rome2.exe").write_bytes(b"MZ")
            good = table(fields, [{"key": "hastati", "cost": 300}], version=3)
            members = {
                "db/units_tables/data__": good,
                "db/unknown_tables/x": b"junk",
                "db/units_tables/cut": good[:-3],  # a string runs past the end
                "db/units_tables/short": good[:8],  # not even a header
                "text/a.loc": b"x",
                "db/units_tables/../../evil": good,
            }
            (root / "game" / "data" / "data.pack").write_bytes(pack(members))
            (root / "game" / "data" / "broken.pack").write_bytes(b"PFH4 broken")
            schema_path = root / "schema_rom2.ron"
            schema_path.write_text(ron({"units_tables": {3: fields}}), encoding="utf-8")
            out = db.DbBuiltin().export(self.ctx(root, schema_path))
            self.assertEqual(out.files, 1)
            got = json.loads(
                (root / "out" / "db" / "units_tables" / "data__.json").read_text("utf-8")
            )
            self.assertEqual(got, [{"key": "hastati", "cost": 300}])
            self.assertIn("unknown_tables", out.notes[0])
            self.assertIn(
                "4 DB table(s) not read", out.notes[0]
            )  # unknown, cut, short, broken.pack (the traversal name is no table)
            self.assertIn("broken.pack", out.notes[0])
            self.assertFalse((root / "evil.json").exists())  # a traversal name never writes outside
            missing = db.DbBuiltin().export(self.ctx(root, None))
            self.assertEqual(
                missing.notes, ("DB tables not read: needs `viwo install rpfm-schema-rom2`",)
            )

    def test_the_game_names_its_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder, exe, want in (
                ("A", "Warhammer3.exe", "wh3"),
                ("Pharaoh Dynasties", "Pharaoh.exe", "ph_dyn"),
                ("P", "Pharaoh.exe", "ph"),
                ("X", "Other.exe", ""),
            ):
                (root / folder).mkdir()
                (root / folder / exe).write_bytes(b"MZ")
                self.assertEqual(db.game_of(root / folder), want)
            ctx = self.ctx(root, None)
            ctx.game_root = root / "X"
            self.assertIn("not recognised", db.DbBuiltin().export(ctx).notes[0])
            self.assertEqual(len(db.DbBuiltin().dependencies()), 14)


if __name__ == "__main__":
    unittest.main()
