"""A resource configuration (ResTable_config) as the qualifiers a developer writes in a `res/`
folder name (`en-rUS-night-xhdpi-v21`): the common fields, read only as far as the record's
own size reaches. The record itself travels as hex beside it, so nothing is lost by what this
summary leaves out (keyboard, navigation and input flags, screen pixels, colour mode, script,
variant and numbering system are only in the hex)."""

import struct

DENSITY = {120: "ldpi", 160: "mdpi", 213: "tvdpi", 240: "hdpi", 320: "xhdpi", 480: "xxhdpi"}
DENSITY.update({640: "xxxhdpi", 0xFFFE: "anydpi", 0xFFFF: "nodpi"})
ORIENTATION = {1: "port", 2: "land", 3: "square"}
TOUCH = {1: "notouch", 2: "stylus", 3: "finger"}
SIZE = {1: "small", 2: "normal", 3: "large", 4: "xlarge"}
LONG = {0x10: "notlong", 0x20: "long"}
DIRECTION = {0x40: "ldltr", 0x80: "ldrtl"}
UI_TYPE = {2: "desk", 3: "car", 4: "television", 5: "appliance", 6: "watch", 7: "vrheadset"}
NIGHT = {0x10: "notnight", 0x20: "night"}


def _field(config: bytes, at: int, fmt: str) -> int:
    return struct.unpack_from(fmt, config, at)[0] if at + struct.calcsize(fmt) <= len(config) else 0


def _locale(config: bytes) -> list[str]:
    if len(config) < 12:
        return []
    lang, country = config[8:10], config[10:12]
    out = []
    if any(lang):
        out.append(lang.decode("latin-1") if lang[0] < 0x80 else f"lang{lang.hex()}")
    if any(country):
        out.append("r" + (country.decode("latin-1") if country[0] < 0x80 else country.hex()))
    return ["-".join(out)] if out else []


def _screen(config: bytes) -> list[str]:
    layout, ui = _field(config, 28, "<B"), _field(config, 29, "<B")
    out = [DIRECTION.get(layout & 0xC0, "")]
    sw, w, h = _field(config, 30, "<H"), _field(config, 32, "<H"), _field(config, 34, "<H")
    out += [f"sw{sw}dp" if sw else "", f"w{w}dp" if w else "", f"h{h}dp" if h else ""]
    out += [SIZE.get(layout & 0x0F, ""), LONG.get(layout & 0x30, "")]
    out.append(ORIENTATION.get(_field(config, 12, "<B"), ""))
    out += [UI_TYPE.get(ui & 0x0F, ""), NIGHT.get(ui & 0x30, "")]
    density = _field(config, 14, "<H")
    out.append(DENSITY.get(density, f"{density}dpi") if density else "")
    out.append(TOUCH.get(_field(config, 13, "<B"), ""))
    return out


def qualifiers(config: bytes) -> str:
    """`default` for the empty configuration, else the qualifiers joined by `-`."""
    mcc, mnc = _field(config, 4, "<H"), _field(config, 6, "<H")
    parts = [f"mcc{mcc}" if mcc else "", f"mnc{mnc}" if mnc else ""]
    parts += _locale(config) + _screen(config)
    sdk = _field(config, 24, "<H")
    parts.append(f"v{sdk}" if sdk else "")
    return "-".join(p for p in parts if p) or "default"
