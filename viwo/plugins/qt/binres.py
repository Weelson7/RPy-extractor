"""Qt resources compiled into an executable or DLL (no standalone `.rcc`): the `qt_resource_data`
blobs live in the binary with no findable header, so the tree names cannot be recovered from a
stripped binary. What can be recovered are the textual resources (QML, JS, QSS, JSON, SVG), each
stored as a big-endian u32 length then its bytes: they are carved by that length prefix and a
recognizable text start, named by index and kind. Said plainly: this reads content, not the
resource tree (a standalone `.rcc` goes through rcc.py, which keeps names)."""

import re

# (regex that must start the blob, extension) for the text resource kinds Qt apps embed
KINDS = (
    (re.compile(rb"\s*(import (QtQuick|QtQml|Qt\.labs|org\.)|/\*\*\*\*|pragma )"), "qml"),
    (re.compile(rb"\s*(\.[\w-]+\s*\{|/\*|@font-face|\* \{)"), "qss"),
    (re.compile(rb"<\?xml|<svg"), "svg"),
    (re.compile(rb"\s*[\{\[]\s*[\"\w]"), "json"),
)


def _kind(blob: bytes) -> str | None:
    head = blob[:400]
    if blob.count(b"\x00") > len(blob) * 0.02:  # not text
        return None
    for pattern, ext in KINDS:
        if pattern.match(head):
            return ext
    return None


def carve(raw: bytes, limit: int = 4_000_000) -> list[tuple[str, bytes]]:
    """[(name, content)] for every text resource blob carved from a binary, in file order."""
    found, seen, counts = [], set(), {}
    starts = re.finditer(
        rb"(import (QtQuick|QtQml|Qt\.labs|org\.)|/\*\*\*\*|<\?xml|<svg|pragma )", raw
    )
    for match in starts:
        for back in range(4):
            prefix = match.start() - back - 4
            if prefix < 0:
                continue
            length = int.from_bytes(raw[prefix : prefix + 4], "big")
            if not 16 <= length <= limit or prefix + 4 + length > len(raw):
                continue
            blob = raw[prefix + 4 : prefix + 4 + length]
            kind = _kind(blob)
            if kind is None or prefix in seen:
                continue
            seen.add(prefix)
            counts[kind] = counts.get(kind, 0) + 1
            found.append((f"{kind}/{kind}_{counts[kind]:04d}.{kind}", blob))
            break
    return found
