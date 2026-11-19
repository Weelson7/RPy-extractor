"""L3: Unreal localization tables (decode.locres), property tests on tables written here byte by
byte in every version (0 legacy, 1 compact, 2 CRC32 keys, 3 CityHash64 keys), with ANSI and UTF-16
strings, shared texts and arbitrary key and source hashes: each reads back as written, and an
unchanged table is written back byte for byte; an edit (texts changed, keys and namespaces
removed, new keys in versions 0 to 2) reads back as the edit with every kept hash in place; a new
key in a version 3 table, an unknown version and any damaged table are named failures."""

from __future__ import annotations

import json
import random
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from viwo.contracts.types import OutcomeKind
from viwo.plugins.unreal.locres import (
    MAGIC,
    LocresBuiltin,
    read_locres,
    read_table,
    str_crc32,
    write_locres,
)

WORDS = "abc XYZ_09 é ÿ漢字🙂 {0} \n"


def fstring(text: str, wide: bool) -> bytes:
    if not text:
        return struct.pack("<i", 0)
    if wide or not all(ord(c) < 256 for c in text):
        raw = text.encode("utf-16-le") + b"\0\0"
        return struct.pack("<i", -(len(raw) // 2)) + raw
    raw = text.encode("latin-1") + b"\0"
    return struct.pack("<i", len(raw)) + raw


def table(rows: dict, version: int, rng: random.Random) -> bytes:
    """rows: {ns: {key: text}}; random storage (ANSI where it fits, or UTF-16) and hashes."""
    wide = {t: rng.random() < 0.3 for keys in rows.values() for t in [*keys, *keys.values()]}
    wide |= {ns: rng.random() < 0.3 for ns in rows}
    hashed = lambda s: struct.pack("<I", rng.getrandbits(32)) if version >= 2 else b""  # noqa
    pool: list[str] = []
    body = struct.pack("<I", len(rows))
    for ns, keys in rows.items():
        body += hashed(ns) + fstring(ns, wide[ns]) + struct.pack("<I", len(keys))
        for key, text in keys.items():
            body += hashed(key) + fstring(key, wide[key]) + struct.pack("<I", rng.getrandbits(32))
            if version == 0:
                body += fstring(text, wide[text])
                continue
            if text not in pool:
                pool.append(text)
            body += struct.pack("<i", pool.index(text))
    if version == 0:
        return body
    uses = [sum(t == p for keys in rows.values() for t in keys.values()) for p in pool]
    if version >= 2:
        body = struct.pack("<I", sum(map(len, rows.values()))) + body
    strings = b"".join(
        fstring(t, wide[t]) + (struct.pack("<i", n) if version >= 2 else b"")
        for t, n in zip(pool, uses)
    )
    head = MAGIC + bytes([version])
    at = len(head) + 8 + len(body)
    return head + struct.pack("<q", at) + body + struct.pack("<i", len(pool)) + strings


def random_rows(rng: random.Random) -> dict:
    word = lambda: "".join(rng.choice(WORDS) for _ in range(rng.randint(0, 9)))  # noqa: E731
    texts = [word() for _ in range(rng.randint(1, 6))]  # few texts: keys share them
    return {
        f"ns{i}{word()}": {f"k{j}{word()}": rng.choice(texts) for j in range(rng.randint(0, 6))}
        for i in range(rng.randint(0, 4))
    }


def unreal_crc(text: str) -> int:
    """FCrc::StrCrc32 as Unreal writes it: a table-driven CRC over each UTF-16 unit's 4 bytes."""
    poly, crc = 0xEDB88320, 0xFFFFFFFF
    for unit in struct.unpack(f"<{len(text.encode('utf-16-le')) // 2}H", text.encode("utf-16-le")):
        for _ in range(4):
            crc ^= unit & 0xFF
            unit >>= 8
            for _ in range(8):
                crc = (crc >> 1) ^ (poly if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


class LocresTests(unittest.TestCase):
    def test_every_version_reads_back_and_writes_back_byte_for_byte(self) -> None:
        rng = random.Random(31)
        for case in range(160):
            rows, version = random_rows(rng), case % 4
            data = table(rows, version, rng)
            self.assertEqual(read_locres(data), rows)
            self.assertEqual(
                [list(k) for k in read_locres(data).values()], [list(k) for k in rows.values()]
            )
            self.assertEqual(write_locres(rows, data), data, (version, rows))

    def test_an_edit_reads_back_with_every_kept_hash(self) -> None:
        rng = random.Random(32)
        for case in range(160):
            version, rows = case % 4, random_rows(rng)
            data = table(rows, version, rng)
            edited = {ns: dict(keys) for ns, keys in rows.items() if rng.random() < 0.85}
            for keys in edited.values():
                for key in list(keys):
                    roll = rng.random()
                    if roll < 0.3:
                        keys[key] = keys[key] + rng.choice(WORDS)
                    elif roll < 0.4:
                        del keys[key]
            if version < 3 and rng.random() < 0.5:
                edited.setdefault("new ns", {})["new key ✓"] = "new text"
            out = write_locres(edited, data)
            self.assertEqual(read_locres(out), edited)
            before, after = read_table(data), read_table(out)
            for where, value in after.hashes.items():
                self.assertEqual(before.hashes.get(where, str_crc32(where[-1])), value)
            for ns, keys in after.rows.items():
                for key, (_, source) in keys.items():
                    old = before.rows.get(ns, {}).get(key)
                    self.assertEqual(source, old[1] if old else str_crc32(edited[ns][key]))
            if after.pool:
                uses = [t for keys in edited.values() for t in keys.values()]
                kept = [(t, n) for t, n in after.pool if t in uses]
                if version >= 2:
                    self.assertTrue(all(n == uses.count(t) for t, n in kept), after.pool)

    def test_new_keys_in_version_3_unknown_versions_and_damage_are_named(self) -> None:
        rng = random.Random(33)
        data = table({"ns": {"k": "v"}}, 3, rng)
        with self.assertRaisesRegex(ValueError, "CityHash64"):
            write_locres({"ns": {"k": "v", "k2": "w"}}, data)
        with self.assertRaisesRegex(ValueError, "version 4 is not known"):
            read_locres(MAGIC + b"\x04" + bytes(20))
        for _ in range(400):
            blob = bytearray(table(random_rows(rng) or {"a": {"b": "c"}}, rng.randrange(4), rng))
            if rng.random() < 0.5:
                blob = blob[: rng.randrange(len(blob))]
            else:
                blob[rng.randrange(len(blob))] ^= 1 << rng.randrange(8)
            try:
                read_locres(bytes(blob))
            except ValueError:
                continue  # said, never a crash

    def test_unreal_crc32_and_the_decoder_both_ways(self) -> None:
        for text in ("", "Game", "Ünïcødé 漢字", "🙂"):
            self.assertEqual(str_crc32(text), unreal_crc(text))
        self.assertEqual(str_crc32("a"), zlib.crc32(b"a\0\0\0"))
        rng = random.Random(34)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good, bad = root / "Game.locres", root / "New.locres"
            good.write_bytes(table({"": {"Title": "Salvē 🙂"}}, 2, rng))
            bad.write_bytes(MAGIC + b"\x07")
            out = LocresBuiltin().decode(good, root, None)
            self.assertEqual((out.kind, out.files), (OutcomeKind.OK, 1))
            shown = json.loads((root / "Game.locres.json").read_text("utf-8"))
            self.assertEqual(shown, {"": {"Title": "Salvē 🙂"}})
            self.assertIn("version 7", LocresBuiltin().refuses(bad))
            self.assertEqual(LocresBuiltin().refuses(good), "")
            (root / "edit.json").write_text(json.dumps({"": {"Title": "Hello"}}), "utf-8")
            done = LocresBuiltin().encode(root / "edit.json", good, root / "out.locres", None)
            self.assertEqual(done.kind, OutcomeKind.OK)
            self.assertEqual(
                read_locres((root / "out.locres").read_bytes()), {"": {"Title": "Hello"}}
            )
            (root / "edit.json").write_text(json.dumps({"": ["not", "a table"]}), "utf-8")
            done = LocresBuiltin().encode(root / "edit.json", good, root / "x.locres", None)
            self.assertEqual(done.kind, OutcomeKind.FAILED)
            self.assertEqual(LocresBuiltin().decode(bad, root, None).kind, OutcomeKind.FAILED)


if __name__ == "__main__":
    unittest.main()
