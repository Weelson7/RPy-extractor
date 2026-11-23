"""What one content search looks for (doc 6.7): a query turned into its needles, one per byte
encoding tried, each named. Text is tried as UTF-8, UTF-16LE and UTF-16BE (case-insensitive:
every letter in its lower and upper form, in any script); an integer as 1/2/4/8-byte little- and
big-endian, signed when negative (2/4/8 by default: a 1-byte value is found nearly everywhere, so
it is tried only when asked); a number with a point or an exponent as a 32- and 64-bit float; a
byte pattern with `??` wildcards exactly as a patch set's AOB (core/patchsets.py `aob`)."""

import re
import struct
from dataclasses import dataclass

from viwo.contracts.errors import ViwoError

from .patchsets import aob

KINDS = ("text", "number", "bytes")
CODECS = (("utf-8", "utf-8"), ("utf-16-le", "utf-16le"), ("utf-16-be", "utf-16be"))
WIDTHS = (2, 4, 8)
FLOATS = (("<f", "f32le"), (">f", "f32be"), ("<d", "f64le"), (">d", "f64be"))
LONGEST = 1 << 16  # bytes one needle may span: the overlap two chunks of a file share


@dataclass(frozen=True)
class Needle:
    """One byte form of the query: `literal` bytes, or `rx` (wildcards, case-insensitive text);
    `size` is the longest match it can have."""

    label: str
    size: int
    literal: bytes = b""
    rx: re.Pattern | None = None

    def find(self, buf, pos: int, end: int) -> tuple[int, int] | None:
        """(start, end) of the first match inside buf[pos:end], or None."""
        if self.rx is None:
            at = buf.find(self.literal, pos, end)
            return None if at < 0 else (at, at + len(self.literal))
        hit = self.rx.search(buf, pos, end)
        return None if hit is None else hit.span()


@dataclass(frozen=True)
class Query:
    kind: str
    value: str
    needles: tuple[Needle, ...]
    notes: tuple[str, ...] = ()  # what was not tried, and why: said with the results

    def tried(self) -> list[str]:
        return [n.label for n in self.needles]

    def describe(self) -> str:
        return f"{self.kind} {self.value!r} as {', '.join(self.tried())}"

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "value": self.value,
            "tried": self.tried(),
            "notes": [*self.notes],
        }


def build(kind: str, value: str, ignore_case: bool = False, widths=None) -> Query:
    """The query of `viwo search --text/--number/--bytes` and of POST /api/search."""
    value = str(value)
    if kind not in KINDS:
        raise ViwoError("invalid_request", f"search for text, a number or bytes, not {kind!r}")
    if not value.strip():
        raise ViwoError("invalid_request", f"give the {kind} to search for")
    if kind == "text":
        query = Query(kind, value, tuple(_text(value, ignore_case)))
    elif kind == "bytes":
        pattern, mask, rx = aob(value)
        whole = all(mask)  # no wildcard: a plain byte search, the fastest
        query = Query(kind, value, (Needle("bytes", len(pattern), pattern if whole else b"", rx),))
    else:
        query = _number(value.strip(), _widths(widths or WIDTHS))
    if max(n.size for n in query.needles) > LONGEST:
        raise ViwoError("invalid_request", f"search for at most {LONGEST:,} bytes at once")
    return query


def _text(text: str, ignore_case: bool) -> list[Needle]:
    out = []
    for codec, label in CODECS:
        try:
            if not ignore_case:
                data = text.encode(codec)
                out.append(Needle(label, len(data), data))
                continue
            forms = [_forms(ch, codec) for ch in text]
        except UnicodeEncodeError as exc:
            raise ViwoError("invalid_request", f"the text cannot be encoded: {exc}") from exc
        rx = b"".join(_alternatives(f) for f in forms)
        size = sum(max(len(x) for x in f) for f in forms)
        out.append(Needle(f"{label} (any case)", size, b"", re.compile(rx, re.DOTALL)))
    return out


def _forms(ch: str, codec: str) -> list[bytes]:
    """A letter's single-character case forms, encoded (`ß`'s upper form `SS` is two)."""
    return sorted({f.encode(codec) for f in (ch, ch.lower(), ch.upper()) if len(f) == 1})


def _alternatives(forms: list[bytes]) -> bytes:
    if len(forms) == 1:
        return re.escape(forms[0])
    if all(len(f) == 1 for f in forms):
        return b"[" + b"".join(re.escape(f) for f in forms) + b"]"
    return b"(?:" + b"|".join(re.escape(f) for f in forms) + b")"


def _widths(given) -> tuple[int, ...]:
    """`1,2,4` or [1, 2, 4] as sorted byte widths; anything else is refused by name."""
    items = str(given).split(",") if isinstance(given, (str, int)) else list(given)
    try:
        widths = tuple(sorted({int(str(w).strip()) for w in items}))
    except ValueError:
        widths = ()
    if not widths or any(w not in (1, 2, 4, 8) for w in widths):
        raise ViwoError("invalid_request", f"integer widths are 1, 2, 4 or 8 bytes, not {given!r}")
    return widths


def _number(value: str, widths: tuple[int, ...]) -> Query:
    try:
        number = int(value, 0) if value.lower().lstrip("+-").startswith("0x") else int(value)
    except ValueError:
        try:
            return _floats(value, float(value))
        except ValueError:
            raise ViwoError("invalid_request", f"not a number: {value!r}") from None
    return _ints(value, number, widths)


def _ints(value: str, number: int, widths: tuple[int, ...]) -> Query:
    found: dict[bytes, list[str]] = {}
    notes = [] if 1 in widths else ["1-byte forms not tried (ask for width 1)"]
    for width in widths:
        bits = 8 * width
        if not -(1 << bits - 1) <= number < 1 << bits:
            notes.append(f"{bits}-bit forms not tried: the value does not fit")
            continue
        sign = "i" if number < 0 else "u"
        for order, tag in (("little", "le"), ("big", "be")) if width > 1 else (("little", ""),):
            data = number.to_bytes(width, order, signed=number < 0)
            found.setdefault(data, []).append(f"{sign}{bits}{tag}")
    if not found:
        raise ViwoError("invalid_request", f"{value} fits none of the widths {list(widths)}")
    needles = tuple(Needle("/".join(names), len(d), d) for d, names in found.items())
    return Query("number", value, needles, tuple(notes))


def _floats(value: str, number: float) -> Query:
    needles, notes = [], []
    for fmt, label in FLOATS:
        try:
            data = struct.pack(fmt, number)
        except OverflowError:
            notes.append(f"{label} not tried: the value does not fit in 32 bits")
            continue
        needles.append(Needle(label, len(data), data))
    single = needles[0].literal if needles and needles[0].label == "f32le" else b""
    if single and struct.unpack("<f", single)[0] != number:
        notes.append("f32 is the nearest single-precision value (an exact bit match only)")
    return Query("number", value, tuple(needles), tuple(notes))
