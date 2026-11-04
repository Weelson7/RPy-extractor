"""decode.loc (doc 16.0c): Total War localisation tables (`.loc`, every Warscape game) to JSON,
read by ViWo: `{key: text}` in the file's order, UTF-8. Format: `FF FE "LOC" 00`, a version and
an entry count (u32), then per entry a key and a text (u16 length + UTF-16LE) and a flag byte."""

from __future__ import annotations

import json
import struct
from pathlib import Path

from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

MAGIC = b"\xff\xfeLOC\x00"
SLOT = SlotDefinition("decode.loc", "decode", "warscape", "loc-builtin", suffixes=(".loc",))


def read_loc(data: bytes) -> dict[str, str]:
    """{key: text}; ValueError on anything that is not a whole, well-formed table."""
    if not data.startswith(MAGIC):
        raise ValueError("not a Total War .loc table")
    try:
        _version, count = struct.unpack_from("<II", data, 6)
        at, rows = 14, {}
        for _ in range(count):
            pair = []
            for _ in range(2):
                (n,) = struct.unpack_from("<H", data, at)
                end = at + 2 + 2 * n
                if end > len(data):
                    raise ValueError("entry runs past the end")
                pair.append(data[at + 2 : end].decode("utf-16-le"))
                at = end
            at += 1  # the tooltip flag
            rows[pair[0]] = pair[1]
    except (struct.error, UnicodeDecodeError) as exc:
        raise ValueError(f"damaged .loc table: {exc}") from None
    if at != len(data):
        raise ValueError(f"{len(data) - at} byte(s) after the last entry")
    return rows


class LocBuiltin(Decoder):
    backend_id, owner, license = "loc-builtin", "warscape", "MIT"
    parses_untrusted_in_process = True  # doc 8.4

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        try:
            rows = read_loc(path.read_bytes())
        except (OSError, ValueError) as exc:
            return Outcome(OutcomeKind.FAILED, error=str(exc))
        target = dest / f"{path.name}.json"
        target.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        return Outcome(OutcomeKind.OK, 1)
