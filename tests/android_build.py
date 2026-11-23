"""Android fixtures written byte by byte from the format's description (AOSP ResourceTypes.h),
independent of ViWo's readers and writers: a binary AndroidManifest.xml, a resources.arsc with
dense, 16-bit-offset and sparse type chunks, a bag, a compact entry and a styled string, and
APK / bundle / OBB zips around them."""

from __future__ import annotations

import io
import struct
import zipfile

ANDROID = "http://schemas.android.com/apk/res/android"
NONE = 0xFFFFFFFF
END = 0xFFFFFFFF


def pool(strings: list[str], utf8: bool, styles: list[list[tuple]] | None = None) -> bytes:
    """A ResStringPool chunk; styles[i] holds (name index, first, last) spans of string i."""
    offsets, data = [], b""
    for text in strings:
        offsets.append(len(data))
        if utf8:
            raw = text.encode("utf-8")
            data += bytes([len(text.encode("utf-16-le")) // 2, len(raw)]) + raw + b"\0"
        else:
            data += struct.pack("<H", len(text.encode("utf-16-le")) // 2)
            data += text.encode("utf-16-le") + b"\0\0"
    data += b"\0" * (-len(data) % 4)
    styles = styles or []
    style_offsets, style_data = [], b""
    for spans in styles:
        style_offsets.append(len(style_data))
        style_data += b"".join(struct.pack("<3I", *span) for span in spans) + struct.pack("<I", END)
    if styles:
        style_data += struct.pack("<2I", END, END)
    head = 28 + 4 * (len(strings) + len(styles))
    styles_at = head + len(data) if styles else 0
    size = head + len(data) + len(style_data)
    fields = (len(strings), len(styles), 0x100 if utf8 else 0, head, styles_at)
    return (
        struct.pack("<HHI5I", 1, 28, size, *fields)
        + struct.pack(f"<{len(strings) + len(styles)}I", *offsets, *style_offsets)
        + data
        + style_data
    )


# ---- binary XML -------------------------------------------------------------------------------

ID_NAMES = ["versionCode", "versionName", "minSdkVersion", "targetSdkVersion", "label"]
ID_NAMES += ["debuggable", "icon", "name", "exported", "value"]
IDS = [0x0101021B, 0x0101021C, 0x0101020C, 0x01010270, 0x01010001]
IDS += [0x0101000F, 0x01010002, 0x01010003, 0x01010010, 0x01010024]
OTHER = ["android", ANDROID, "manifest", "package", "com.viwo.test", "platformBuildVersionCode"]
OTHER += ["uses-sdk", "application", "activity", ".Main", "meta-data", "x", "1.0"]
OTHER += ["Café ☕ & <tags>", "hello text", "note"]
STRINGS = ID_NAMES + OTHER


def s(text: str) -> int:
    return STRINGS.index(text)


def _node(kind: int, line: int, ext: bytes) -> bytes:
    return struct.pack("<HHIII", kind, 16, 16 + len(ext), line, NONE) + ext


def _start(line: int, name: str, attrs: list[tuple]) -> bytes:
    """attrs: (android namespace?, name, raw string or None, type, data)."""
    body = b""
    for android, attr, raw, code, data in attrs:
        ns = s(ANDROID) if android else NONE
        body += struct.pack("<IIIHBBI", ns, s(attr), s(raw) if raw else NONE, 8, 0, code, data)
    ext = struct.pack("<IIHHHHHH", NONE, s(name), 20, 20, len(attrs), 0, 0, 0) + body
    return _node(0x0102, line, ext)


def _end(line: int, name: str) -> bytes:
    return _node(0x0103, line, struct.pack("<II", NONE, s(name)))


def manifest(utf8: bool = False) -> bytes:
    ns = struct.pack("<II", s("android"), s(ANDROID))
    nodes = [
        _node(0x0100, 1, ns),
        _start(
            1,
            "manifest",
            [
                (1, "versionCode", None, 0x10, 1),
                (1, "versionName", "1.0", 0x03, s("1.0")),
                (0, "package", "com.viwo.test", 0x03, s("com.viwo.test")),
                (0, "platformBuildVersionCode", None, 0x10, 33),
            ],
        ),  # fmt: skip
        _start(
            2,
            "uses-sdk",
            [(1, "minSdkVersion", None, 0x10, 21), (1, "targetSdkVersion", None, 0x10, 33)],
        ),  # fmt: skip
        _end(2, "uses-sdk"),
        _start(
            3,
            "application",
            [
                (1, "label", None, 0x01, 0x7F010000),
                (1, "icon", None, 0x01, 0x7F020000),
                (1, "debuggable", None, 0x12, 0),
            ],
        ),  # fmt: skip
        _start(
            4,
            "activity",
            [(1, "name", ".Main", 0x03, s(".Main")), (1, "exported", None, 0x12, NONE)],
        ),  # fmt: skip
        _start(5, "meta-data", [(1, "name", "x", 0x03, s("x")), (1, "value", None, 0x05, 0x1001)]),
        _end(5, "meta-data"),
        _start(
            6,
            "meta-data",
            [
                (1, "name", "Café ☕ & <tags>", 0x03, s("Café ☕ & <tags>")),
                (1, "value", None, 0x04, 0x3FC00000),
            ],
        ),  # fmt: skip
        _end(6, "meta-data"),
        _end(7, "activity"),
        _start(8, "note", []),
        _node(0x0104, 8, struct.pack("<IHBBI", s("hello text"), 8, 0, 0, 0)),
        _end(8, "note"),
        _end(9, "application"),
        _end(10, "manifest"),
        _node(0x0101, 10, ns),
    ]
    resmap = struct.pack(f"<HHI{len(IDS)}I", 0x0180, 8, 8 + 4 * len(IDS), *IDS)
    body = pool(STRINGS, utf8) + resmap + b"".join(nodes)
    return struct.pack("<HHI", 3, 8, 8 + len(body)) + body


MANIFEST_TEXT = f"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="{ANDROID}" android:versionCode="1" android:versionName="1.0" \
package="com.viwo.test" platformBuildVersionCode="33">
    <uses-sdk android:minSdkVersion="21" android:targetSdkVersion="33"/>
    <application android:label="@0x7f010000" android:icon="@0x7f020000" android:debuggable="false">
        <activity android:name=".Main" android:exported="true">
            <meta-data android:name="x" android:value="16.0dip"/>
            <meta-data android:name="Café ☕ &amp; &lt;tags&gt;" android:value="1.5"/>
        </activity>
        <note>hello text</note>
    </application>
</manifest>
"""

# ---- resources.arsc ---------------------------------------------------------------------------

GLOBAL = ["Hello", "World", "res/drawable/icon.png", "Bonjour", "b"]
TYPES = ["string", "drawable", "style", "color"]
KEYS = ["app_name", "greeting", "icon", "AppTheme", "accent", "primary"]


def _chunk(kind: int, head: bytes, body: bytes) -> bytes:
    return struct.pack("<HHI", kind, 8 + len(head), 8 + len(head) + len(body)) + head + body


def _config(**fields) -> bytes:
    raw = bytearray(64)
    struct.pack_into("<I", raw, 0, 64)
    if "lang" in fields:
        raw[8:10] = fields["lang"].encode()
    if "ui" in fields:
        raw[29] = fields["ui"]
    return bytes(raw)


def _simple(key: int, code: int, data: int) -> bytes:
    return struct.pack("<HHI", 8, 0, key) + struct.pack("<HBBI", 8, 0, code, data)


def _type(tid: int, config: bytes, entries: list, flags: int = 0) -> bytes:
    """entries: one bytes (an entry) or None per index; flags 0x02 = 16-bit offsets, 0x01 sparse
    (then entries are (index, bytes) pairs)."""
    offsets, data = [], b""
    for item in entries:
        index, entry = item if flags & 1 else (0, item)
        if entry is None:
            offsets.append(0xFFFF if flags & 2 else NONE)
            continue
        where = len(data) // 4 if flags & 3 else len(data)  # sparse, 16-bit: in 4-byte units
        offsets.append((index, where) if flags & 1 else where)
        data += entry
    if flags & 1:
        table = b"".join(struct.pack("<HH", i, o) for i, o in offsets)
    else:
        table = struct.pack(f"<{len(offsets)}{'H' if flags & 2 else 'I'}", *offsets)
    table += b"\0" * (-len(table) % 4)
    head = struct.pack("<BBHII", tid, flags, 0, len(entries), 8 + 12 + len(config) + len(table))
    return _chunk(0x0201, head + config, table + data)


def _spec(tid: int, count: int) -> bytes:
    return _chunk(0x0202, struct.pack("<BBHI", tid, 0, 0, count), bytes(4 * count))


def _bag() -> bytes:
    head = struct.pack("<HHIII", 16, 1, KEYS.index("AppTheme"), 0x01030005, 2)
    items = struct.pack("<IHBBI", 0x01010098, 8, 0, 0x1C, 0xFF112233)
    return head + items + struct.pack("<IHBBI", 0x01010030, 8, 0, 0x01, 0x7F020000)


def arsc(utf8: bool = False) -> bytes:
    compact = struct.pack("<HHI", KEYS.index("primary"), (0x1C << 8) | 0x08, 0xFF0000FF)
    chunks = [
        pool(TYPES, utf8),
        pool(KEYS, utf8),
        _spec(1, 2),
        _type(1, _config(), [_simple(0, 0x03, 0), _simple(1, 0x03, 1)]),
        _type(1, _config(lang="fr"), [_simple(0, 0x03, 3), None]),
        _spec(2, 1),
        _type(2, _config(), [_simple(2, 0x03, 2)]),
        _spec(3, 1),
        _type(3, _config(), [_bag()]),
        _spec(4, 2),
        _type(4, _config(), [_simple(4, 0x1D, 0xFF00FF00), compact], flags=2),
        _type(4, _config(ui=0x20), [(1, _simple(5, 0x10, 7))], flags=1),
    ]
    name = "com.viwo.test".encode("utf-16-le").ljust(256, b"\0")
    types_at = 288
    keys_at = types_at + len(chunks[0])
    head = struct.pack("<I", 0x7F) + name + struct.pack("<5I", types_at, 4, keys_at, 6, 0)
    package = _chunk(0x0200, head, b"".join(chunks))
    strings = pool(GLOBAL, utf8, [[(GLOBAL.index("b"), 0, 2)]])
    return _chunk(0x0002, struct.pack("<I", 1), strings + package)


# ---- zips ---------------------------------------------------------------------------------------


def zip_of(members: dict[str, bytes], stored: tuple[str, ...] = (), pages: bool = False) -> bytes:
    """A zip as a build tool writes it: `stored` members uncompressed (at no particular
    alignment, unless `pages`: then every stored `.so` starts on a 4096-byte page)."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name, data in members.items():
            info = zipfile.ZipInfo(name, (2024, 1, 2, 3, 4, 6))
            method = zipfile.ZIP_STORED if name in stored else zipfile.ZIP_DEFLATED
            info.compress_type = method
            if pages and name.endswith(".so") and method == zipfile.ZIP_STORED:
                at = out.tell() + 30 + len(name.encode()) + 4
                info.extra = struct.pack("<HH", 0xCAFE, -at % 4096) + bytes(-at % 4096)
            zf.writestr(info, data)
    return out.getvalue()


def apk_members() -> dict[str, bytes]:
    return {
        "AndroidManifest.xml": manifest(),
        "classes.dex": b"dex\n035\0" + bytes(range(64)),
        "resources.arsc": arsc(),
        "res/layout/main.xml": manifest(utf8=True),
        "lib/arm64-v8a/libgame.so": b"\x7fELF" + bytes(300),
        "assets/readme.txt": b"plain asset",
        "META-INF/MANIFEST.MF": b"Manifest-Version: 1.0\r\n",
        "META-INF/CERT.SF": b"Signature-Version: 1.0\r\n",
        "META-INF/CERT.RSA": b"\x30\x82" + bytes(40),
    }


STORED = ("resources.arsc", "lib/arm64-v8a/libgame.so", "assets/readme.txt")
