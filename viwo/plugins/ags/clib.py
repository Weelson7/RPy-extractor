"""AGS CLIB packfiles, read as the engine reads them (AGS `Common/data/multifilelib.cpp`): the
library at the start of a file (`.ags`, `.vox`, `ac2game.dat`) or appended to the game's
executable, found then by the 12-byte tail signature and the 64- or 32-bit offset before it.
Versions 6 (one file: names shifted by a per-library byte, data in sequence), 10, 11 and 15
(fixed-width names, encrypted from 11 on), 20 (names encrypted with AGS's text key), 21 (every
field through AGS's pseudo-random generator) and 30 (plain, 64-bit offsets); another is refused
by name. Each value's place in the table of contents is kept, so the way back (pack.py) rewrites
offsets and sizes in place and leaves every other byte as it was."""

import struct
from dataclasses import dataclass, field
from pathlib import Path

HEAD = b"CLIB\x1a"
TAIL = b"CLIB\x01\x02\x03\x04SIGE"
VERSIONS = (6, 10, 11, 15, 20, 21, 30)
SEED = 9338638  # the engine's salt for version 21's generator
KEY = b"My\x01\xde\x04Jibzle"  # the engine's text key (versions 11 to 20)
TOC_LIMIT = 64 << 20  # a table of contents past this is damage


@dataclass(frozen=True)
class Field:
    """Where a value sits in the table of contents (from the library's start)."""

    at: int
    width: int
    rand: int | None = None  # version 21: the generator's state before the field's first byte


@dataclass
class Asset:
    name: str
    uid: int  # the library part holding it (0: this file)
    offset: int  # from its part's start
    size: int
    fields: dict = field(default_factory=dict)  # "offset", "size", "uid" -> Field


@dataclass
class Lib:
    version: int
    base: int  # where the library starts in its file (after an executable)
    ender: int  # width of the offset before the tail signature: 8, 4, or 0 without one
    index: int = 0  # this file's place in a multi-file library (0: the one with the table)
    end: int = 0  # end of the table of contents, from the library's start
    parts: list = field(default_factory=list)
    assets: list = field(default_factory=list)


def next_rand(state: int) -> tuple[int, int]:
    """AGS's generator: (new state, the 15-bit value it subtracts)."""
    state = (state * 214013 + 2531011) & 0xFFFFFFFF
    return state, (state >> 16) & 0x7FFF


class _Toc:
    def __init__(self, data: bytes, at: int, rand: int | None = None) -> None:
        self.data, self.at, self.rand = data, at, rand

    def raw(self, n: int) -> bytes:
        chunk = self.data[self.at : self.at + n]
        if len(chunk) < n:
            raise ValueError("the table of contents runs past the end")
        self.at += n
        if self.rand is None:
            return chunk
        out = bytearray()
        for b in chunk:
            self.rand, r = next_rand(self.rand)
            out.append((b - r) & 0xFF)
        return bytes(out)

    def num(self, width: int, key: str = "", asset: Asset | None = None) -> int:
        if asset is not None:
            asset.fields[key] = Field(self.at, width, self.rand)
        return int.from_bytes(self.raw(width), "little")

    def cstr(self, limit: int = 1 << 12) -> str:
        out = bytearray()
        while len(out) < limit:
            c = self.raw(1)[0]
            if not c:
                return out.decode("latin-1")
            out.append(c)
        return out.decode("latin-1")  # the engine stops at its buffer's length too


def decrypt_text(raw: bytes) -> str:
    """AGS's DecryptText: each byte less the text key's, up to the first that becomes 0."""
    out = bytearray()
    for i, b in enumerate(raw):
        c = (b - KEY[i % len(KEY)]) & 0xFF
        if not c:
            return out.decode("latin-1")
        out.append(c)
    raise ValueError("an encrypted asset name without its end")


def _numbers(t: _Toc, assets: list, width: int = 4) -> None:
    """The three arrays of versions 10 to 21: offsets, sizes, parts."""
    for key, w in (("offset", width), ("size", width), ("uid", 1)):
        for asset in assets:
            setattr(asset, key, t.num(w, key, asset))


def _v10(t: _Toc, lib: Lib) -> None:
    lib.parts = [t.raw(20).split(b"\0")[0].decode("latin-1") for _ in range(t.num(4))]
    raws = [t.raw(25) for _ in range(t.num(4))]
    names = [
        decrypt_text(r) if lib.version >= 11 else r.split(b"\0")[0].decode("latin-1") for r in raws
    ]
    lib.assets = [Asset(n, 0, 0, 0) for n in names]
    _numbers(t, lib.assets)


def _v20(t: _Toc, lib: Lib) -> None:
    lib.parts = [t.cstr(50) for _ in range(t.num(4))]
    names = []
    for _ in range(t.num(4)):
        names.append(decrypt_text(t.raw(t.num(2) // 5)))
    lib.assets = [Asset(n, 0, 0, 0) for n in names]
    _numbers(t, lib.assets)


def _v21(t: _Toc, lib: Lib) -> None:
    t.rand = (t.num(4) + SEED) & 0xFFFFFFFF
    lib.parts = [t.cstr(50) for _ in range(t.num(4))]
    lib.assets = [Asset(t.cstr(100), 0, 0, 0) for _ in range(t.num(4))]
    _numbers(t, lib.assets)


def _v30(t: _Toc, lib: Lib) -> None:
    t.num(4)  # reserved flags
    lib.parts = [t.cstr() for _ in range(t.num(4))]
    for _ in range(t.num(4)):
        asset = Asset(t.cstr(), 0, 0, 0)
        asset.uid = t.num(1, "uid", asset)
        asset.offset = t.num(8, "offset", asset)
        asset.size = t.num(8, "size", asset)
        lib.assets.append(asset)


def _v6(t: _Toc, lib: Lib) -> None:
    shift = t.raw(2)[0]  # the per-library byte, and an unused one
    count = t.num(2)
    t.raw(13)
    lib.parts = [""]
    for raw in [t.raw(13) for _ in range(count)]:
        name = raw.split(b"\0")[0]
        lib.assets.append(Asset(bytes((c - shift) & 0xFF for c in name).decode("latin-1"), 0, 0, 0))
    for asset in lib.assets:
        asset.size = t.num(4, "size", asset)
    t.raw(2 * count)  # flags and ratio
    at = t.at
    for asset in lib.assets:  # stored one after the other, from the end of the table
        asset.offset, at = at, at + asset.size


def _locate(fh, size: int) -> tuple[int, int] | None:
    """(library start, width of the offset before the tail signature: 0 without one, -1 when
    the library starts the file and its version decides), or None."""
    fh.seek(max(0, size - 20))
    tail = fh.read(20)
    ended = tail.endswith(TAIL)
    fh.seek(0)
    if fh.read(5) == HEAD:
        return 0, -1 if ended else 0
    if not ended or size < 32:
        return None
    for width, value in (
        (8, struct.unpack_from("<q", tail)[0]),
        (4, struct.unpack_from("<i", tail, 4)[0]),
    ):
        if 0 < value < size - 20:  # the engine tries the 64-bit offset, then the 32-bit one
            fh.seek(value)
            if fh.read(5) == HEAD:
                return value, width
    return None


def read_lib(path: Path) -> Lib:
    """The library's table of contents; ValueError when it is not one the engine reads."""
    size = path.stat().st_size
    with open(path, "rb") as fh:
        found = _locate(fh, size)
        if found is None:
            raise ValueError("no CLIB library at its start or behind its executable")
        fh.seek(found[0])
        data = fh.read(min(size - found[0], TOC_LIMIT))
    if len(data) < 6:
        raise ValueError("a CLIB library cut short")
    ender = (8 if data[5] >= 30 else 4) if found[1] < 0 else found[1]
    lib = Lib(data[5], found[0], ender)
    if lib.version not in VERSIONS:
        raise ValueError(f"CLIB version {lib.version} is not one AGS reads ({VERSIONS})")
    t = _Toc(data, 6)
    try:
        if lib.version >= 10:
            lib.index = t.raw(1)[0]
            if lib.index:
                return lib  # a later part: its table is in the first part
        {6: _v6, 20: _v20, 21: _v21, 30: _v30}.get(lib.version, _v10)(t, lib)
    except (struct.error, UnicodeDecodeError, IndexError) as exc:
        raise ValueError(f"damaged CLIB table: {exc}") from None
    lib.end = t.at
    return lib
