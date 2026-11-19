"""decode.loc (doc 16.0c): Total War localisation tables (`.loc`, every Warscape game) to JSON,
read by ViWo: `{key: text}` in the file's order, UTF-8. Format: `FF FE "LOC" 00`, a version and
an entry count (u32), then per entry a key and a text (u16 length + UTF-16LE) and a flag byte."""

import json
import struct
from pathlib import Path

from viwo.contracts.slots import Decoder, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

MAGIC = b"\xff\xfeLOC\x00"
SLOT = SlotDefinition("decode.loc", "decode", "warscape", "loc-builtin", suffixes=(".loc",))


def read_entries(data: bytes) -> tuple[int, list[tuple[str, str, int]]]:
    """(version, [(key, text, flag)] in the file's order); ValueError on anything that is not a
    whole, well-formed table."""
    if not data.startswith(MAGIC):
        raise ValueError("not a Total War .loc table")
    try:
        version, count = struct.unpack_from("<II", data, 6)
        at, rows = 14, []
        for _ in range(count):
            pair = []
            for _ in range(2):
                (n,) = struct.unpack_from("<H", data, at)
                end = at + 2 + 2 * n
                if end > len(data):
                    raise ValueError("entry runs past the end")
                pair.append(data[at + 2 : end].decode("utf-16-le"))
                at = end
            rows.append((pair[0], pair[1], data[at]))  # the tooltip flag
            at += 1
    except (struct.error, UnicodeDecodeError, IndexError) as exc:
        raise ValueError(f"damaged .loc table: {exc}") from None
    if at != len(data):
        raise ValueError(f"{len(data) - at} byte(s) after the last entry")
    return version, rows


def read_loc(data: bytes) -> dict[str, str]:
    """{key: text}; ValueError on anything that is not a whole, well-formed table."""
    return {key: text for key, text, _ in read_entries(data)[1]}


def write_loc(edited: dict[str, str], original: bytes) -> bytes:
    """The original table with the edited texts: its version, order and flags kept, a key the
    edit removed left out, a new key added at the end with the table's most common flag."""
    version, rows = read_entries(original)
    flags = [flag for _, _, flag in rows]
    common = max(set(flags), key=flags.count) if flags else 1
    kept = [(k, edited[k], f) for k, _, f in rows if k in edited]
    known = {k for k, _, _ in rows}
    out = [*kept, *((k, t, common) for k, t in edited.items() if k not in known)]
    body = b"".join(_field(k) + _field(t) + bytes([f]) for k, t, f in out)
    return MAGIC + struct.pack("<II", version, len(out)) + body


def _field(text: str) -> bytes:
    raw = text.encode("utf-16-le")
    if len(raw) // 2 > 0xFFFF:
        raise ValueError(f"a text of {len(raw) // 2} UTF-16 units does not fit a .loc entry")
    return struct.pack("<H", len(raw) // 2) + raw


class LocBuiltin(Decoder):
    backend_id, owner, license = "loc-builtin", "warscape", "MIT"
    parses_untrusted_in_process = True  # doc 8.4
    encodes = True  # the edited JSON back to the table (doc 18.3)

    def encode(self, edited: Path, original: Path, out: Path, ctx) -> Outcome:
        try:
            rows = json.loads(edited.read_text(encoding="utf-8"))
            if not isinstance(rows, dict) or not all(isinstance(v, str) for v in rows.values()):
                raise ValueError("the edited table must stay a JSON object of key: text")
            out.write_bytes(write_loc(rows, original.read_bytes()))
        except (OSError, ValueError) as exc:
            return Outcome(OutcomeKind.FAILED, error=f"{edited.name}: {exc}")
        return Outcome(OutcomeKind.OK, 1)

    def decode(self, path: Path, dest: Path, ctx) -> Outcome:
        try:
            rows = read_loc(path.read_bytes())
        except (OSError, ValueError) as exc:
            return Outcome(OutcomeKind.FAILED, error=str(exc))
        target = dest / f"{path.name}.json"
        target.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        return Outcome(OutcomeKind.OK, 1)
