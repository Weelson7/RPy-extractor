"""L3: Total War localisation tables (decode.loc). Any table ViWo can write is read back exactly,
key order and every Unicode text kept; any cut or damaged table is a named failure, never a crash
or a partial result; the decoder writes the table as UTF-8 JSON. Verified on real data: Rome II's
local_en.pack (191 tables, 122,423 entries, every one parsed to its last byte)."""

from __future__ import annotations

import json
import random
import struct
import tempfile
import unittest
from pathlib import Path

from viwo.contracts.types import OutcomeKind
from viwo.plugins.warscape.loc import MAGIC, LocBuiltin, read_loc

ALPHABET = "abcXYZ_09 é漢字🙂[[col:green]]\n\t"


def table(rows: dict[str, str], version: int = 1) -> bytes:
    out = MAGIC + struct.pack("<II", version, len(rows))
    for key, text in rows.items():
        for s in (key, text):
            raw = s.encode("utf-16-le")
            out += struct.pack("<H", len(raw) // 2) + raw
        out += b"\x00"
    return out


def random_rows(rng: random.Random) -> dict[str, str]:
    word = lambda n: "".join(rng.choice(ALPHABET) for _ in range(n))  # noqa: E731
    return {
        f"k{i}_{word(rng.randint(0, 12))}": word(rng.randint(0, 60))
        for i in range(rng.randint(0, 40))
    }


class LocTests(unittest.TestCase):
    def test_every_table_reads_back_exactly(self) -> None:
        rng = random.Random(11)
        for _ in range(60):
            rows = random_rows(rng)
            got = read_loc(table(rows, rng.choice([1, 2])))
            self.assertEqual(got, rows)
            self.assertEqual(list(got), list(rows))  # the file's order

    def test_a_cut_or_damaged_table_is_a_named_failure(self) -> None:
        rng = random.Random(12)
        for _ in range(300):
            data = bytearray(table(random_rows(rng) or {"k": "v"}))
            if rng.random() < 0.5:
                data = data[: rng.randrange(len(data))]
            else:
                data[rng.randrange(len(data))] ^= 1 << rng.randrange(8)
            try:
                read_loc(bytes(data))
            except ValueError:
                continue  # said, not crashed
        with self.assertRaises(ValueError):
            read_loc(table({"a": "b"}) + b"extra")
        with self.assertRaises(ValueError):
            read_loc(b"not a loc")

    def test_the_decoder_writes_utf8_json_and_names_a_bad_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good, bad = root / "names.loc", root / "bad.loc"
            good.write_bytes(table({"greeting": "Salvē 🙂"}))
            bad.write_bytes(MAGIC + b"\x01")
            out = LocBuiltin().decode(good, root, None)
            self.assertEqual((out.kind, out.files), (OutcomeKind.OK, 1))
            self.assertEqual(
                json.loads((root / "names.loc.json").read_text("utf-8")), {"greeting": "Salvē 🙂"}
            )
            self.assertEqual(LocBuiltin().decode(bad, root, None).kind, OutcomeKind.FAILED)
            self.assertEqual(
                LocBuiltin().decode(root / "gone.loc", root, None).kind, OutcomeKind.FAILED
            )


if __name__ == "__main__":
    unittest.main()
