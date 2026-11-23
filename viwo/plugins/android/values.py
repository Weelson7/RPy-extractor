"""Android's typed values (Res_value: a type byte and 32 bits of data) as text and back. One
spelling per type, chosen so that reading the text back gives the same data: `@0x7f010000`
(reference), `?0x7f010000` (attribute), `16.0dip` (dimension), `50.0%` (fraction), `#ff00ff00`
(colours), `true`/`false`, decimal and `0x` integers, the shortest float that reads back to the
same 32 bits. Strings live in a string pool; their callers handle them."""

import re
import struct

STRING = 0x03
NAMES = {
    0x00: "null",
    0x01: "reference",
    0x02: "attribute",
    0x03: "string",
    0x04: "float",
    0x05: "dimension",
    0x06: "fraction",
    0x07: "dynamic_reference",
    0x08: "dynamic_attribute",
    0x10: "int",
    0x11: "hex",
    0x12: "bool",
    0x1C: "color_argb8",
    0x1D: "color_rgb8",
    0x1E: "color_argb4",
    0x1F: "color_rgb4",
}
TYPES = {name: code for code, name in NAMES.items()}
UNITS = ("px", "dip", "sp", "pt", "in", "mm")
FRACTIONS = ("%", "%p")
RADIX = (0, 7, 15, 23)  # fraction bits of the mantissa for radix 0..3
RAW = re.compile(r"0x[0-9a-fA-F]{1,8}")
NUMBER = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
COMPLEX = re.compile(rf"({NUMBER})(px|dip|dp|sp|pt|in|mm|%p|%)")


def type_name(code: int) -> str:
    return NAMES.get(code, f"0x{code:02x}")


def type_code(name: str) -> int:
    if name in TYPES:
        return TYPES[name]
    if RAW.fullmatch(name) and int(name, 16) < 256:
        return int(name, 16)
    raise ValueError(f"unknown value type {name!r}")


def to_float(data: int) -> float:
    return struct.unpack("<f", struct.pack("<I", data))[0]


def _float_text(data: int) -> str:
    value, raw = to_float(data), struct.pack("<I", data)
    if value != value or value in (float("inf"), float("-inf")):
        return repr(value)
    text = repr(value)
    for digits in range(1, 10):
        text = f"{value:.{digits}g}"
        if struct.pack("<f", float(text)) == raw:
            break
    return text if any(c in text for c in ".en") else text + ".0"


def complex_value(data: int) -> float:
    mantissa = struct.unpack("<i", struct.pack("<I", data & 0xFFFFFF00))[0] >> 8
    return mantissa / (1 << RADIX[(data >> 4) & 3])


def to_complex(value: float, unit: int) -> int:
    """aapt's floatToComplex: the smallest radix that keeps the value's 23 fraction bits."""
    negative, value = value < 0, abs(value)
    bits = int(value * (1 << 23) + 0.5)
    if bits & 0x7FFFFF == 0:
        radix, shift = 0, 23
    elif bits & ~0x7FFFFF == 0:
        radix, shift = 3, 0
    elif bits & ~0x7FFFFFFF == 0:
        radix, shift = 2, 8
    elif bits & ~0x7FFFFFFFFF == 0:
        radix, shift = 1, 16
    else:
        radix, shift = 0, 23
    mantissa = (bits >> shift) & 0xFFFFFF
    if negative:
        mantissa = -mantissa & 0xFFFFFF
    return (mantissa << 8) | (radix << 4) | unit


def _color(data: int, digits: int) -> str:
    if digits == 8:
        return f"#{data:08x}"
    if digits == 6:
        return f"#{data & 0xFFFFFF:06x}"
    shifts = (28, 20, 12, 4) if digits == 4 else (20, 12, 4)
    return "#" + "".join(f"{(data >> s) & 0xF:x}" for s in shifts)


def render(code: int, data: int) -> str:
    """The text of a non-string value."""
    name = NAMES.get(code, "")
    if name == "null":
        return {0: "@null", 1: "@empty"}.get(data, f"0x{data:08x}")
    if name in ("reference", "dynamic_reference"):
        return f"@0x{data:08x}"
    if name in ("attribute", "dynamic_attribute"):
        return f"?0x{data:08x}"
    if name == "float":
        return _float_text(data)
    if name in ("dimension", "fraction"):
        units = UNITS if name == "dimension" else FRACTIONS
        if (data & 0xF) >= len(units):
            return f"0x{data:08x}"
        scale = 1 if name == "dimension" else 100
        return f"{complex_value(data) * scale!r}{units[data & 0xF]}"
    if name == "int":
        return str(struct.unpack("<i", struct.pack("<I", data))[0])
    if name == "bool":
        return "true" if data else "false"
    if name == "hex":
        return f"0x{data:x}"
    if name.startswith("color_"):
        return _color(data, {"argb8": 8, "rgb8": 6, "argb4": 4, "rgb4": 3}[name[6:]])
    return f"0x{data:08x}"


def _parsed(code: int, text: str) -> int | None:
    name = NAMES.get(code, "")
    if name == "null":
        return {"@null": 0, "@empty": 1}.get(text)
    if name in ("reference", "dynamic_reference", "attribute", "dynamic_attribute"):
        mark = "?" if "attribute" in name else "@"
        return int(text[1:], 16) if text[:1] == mark and RAW.fullmatch(text[1:]) else None
    if name == "float":
        return struct.unpack("<I", struct.pack("<f", float(text)))[0]
    if name in ("dimension", "fraction"):
        found = COMPLEX.fullmatch(text)
        units = UNITS if name == "dimension" else FRACTIONS
        unit = {"dp": "dip"}.get(found.group(2), found.group(2)) if found else ""
        if unit not in units:
            return None
        scale = 1 if name == "dimension" else 100
        return to_complex(float(found.group(1)) / scale, units.index(unit))
    if name == "int":
        return int(text) & 0xFFFFFFFF if -(1 << 31) <= int(text) < (1 << 32) else None
    if name == "hex":
        return int(text, 16) if RAW.fullmatch(text) else None
    if name == "bool":
        return {"true": 0xFFFFFFFF, "false": 0}.get(text)
    if name.startswith("color_"):
        return _color_data(text, {"argb8": 8, "rgb8": 6, "argb4": 4, "rgb4": 3}[name[6:]])
    return None


def _color_data(text: str, digits: int) -> int | None:
    if not re.fullmatch(rf"#[0-9a-fA-F]{{{digits}}}", text):
        return None
    value = text[1:]
    if digits <= 4:
        value = "".join(c * 2 for c in value)
    return int(value, 16) | (0xFF000000 if digits in (6, 3) else 0)


def parse(code: int, text: str) -> int:
    """The data of `text` read as type `code`; ValueError when it is not that type's text.
    Every non-string type also takes the raw `0x` + 8 hex digits form."""
    try:
        data = _parsed(code, text.strip())
    except (ValueError, OverflowError, struct.error):
        data = None
    if data is None and RAW.fullmatch(text.strip()) and code != STRING:
        data = int(text.strip(), 16)
    if data is None:
        raise ValueError(f"{text!r} is not a {type_name(code)} value")
    return data


GUESSES = (0x00, 0x01, 0x02, 0x12, 0x1C, 0x1D, 0x1E, 0x1F, 0x05, 0x06, 0x10, 0x11, 0x04)


def guess(text: str) -> tuple[int, int]:
    """(type, data) for a value with no type to go by (an attribute the original never had):
    the first type whose text it is, else a string (data left to the caller)."""
    stripped = text.strip()
    for code in GUESSES:
        if code == 0x04 and not re.fullmatch(NUMBER, stripped):
            continue  # "inf" and "nan" stay words
        try:
            data = _parsed(code, stripped)
        except (ValueError, OverflowError, struct.error):
            data = None
        if data is not None:
            return code, data
    return STRING, 0
