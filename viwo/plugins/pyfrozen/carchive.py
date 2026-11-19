"""PyInstaller's CArchive (appended to the bootloader in a onefile exe) and its inner PYZ. The
cookie at the archive's end (`MEI\\x0c\\x0b\\x0a\\x0b\\x0e`) gives the package length and the TOC
position; each TOC entry names a member, its position and length, a zlib flag and a typecode
(`x` data, `b` binary/extension, `m`/`s`/`M` a Python module, `z`/`Z` the PYZ). A module's stored
bytes are a marshalled code object; this writes it back as a `.pyc` (the real Python magic from
the PYZ header), so the bytecode comes out whole for the matching interpreter. marshal is read
only for the PYZ's own table (names and ints, version-independent); code objects are not loaded
here (that is `decode.pyc`, host-version only)."""

import marshal
import struct
import zlib

PKG_MAGIC = b"MEI\x0c\x0b\x0a\x0b\x0e"
COOKIE = "!8sIIii64s"  # magic, package length, TOC position, TOC length, py version, py lib name
COOKIE_SIZE = struct.calcsize(COOKIE)
ENTRY = ">IIIIBc"  # struct length, data pos, data length, uncompressed length, zlib flag, typecode
ENTRY_SIZE = struct.calcsize(ENTRY)
PYZ_MAGIC = b"PYZ\x00"
MODULE_TYPES = b"msM"


def find_archive(raw: bytes) -> tuple[int, int, int, bytes]:
    """(archive start, TOC absolute position, TOC length, python lib name) from the cookie."""
    at = raw.rfind(PKG_MAGIC)
    if at < 0:
        raise ValueError("no PyInstaller cookie (MEI magic) in the file")
    _, pkg_len, toc_pos, toc_len, _, pylib = struct.unpack_from(COOKIE, raw, at)
    start = at + COOKIE_SIZE - pkg_len
    if not 0 <= start <= at:
        raise ValueError("the PyInstaller package length is out of range")
    return start, start + toc_pos, toc_len, pylib.split(b"\x00", 1)[0]


def toc(raw: bytes, toc_abs: int, toc_len: int) -> list[tuple[str, int, int, int, int, bytes]]:
    """[(name, data pos, data length, uncompressed length, zlib flag, typecode)]."""
    entries, pos, end = [], toc_abs, toc_abs + toc_len
    while pos + ENTRY_SIZE <= end:
        slen, dpos, dlen, ulen, cflag, typ = struct.unpack_from(ENTRY, raw, pos)
        if slen < ENTRY_SIZE or pos + slen > end:
            raise ValueError("a PyInstaller TOC entry runs past the table")
        name = raw[pos + ENTRY_SIZE : pos + slen].split(b"\x00", 1)[0].decode("utf-8", "replace")
        entries.append((name, dpos, dlen, ulen, cflag, typ))
        pos += slen
    return entries


def member_bytes(raw: bytes, start: int, dpos: int, dlen: int, cflag: int) -> bytes:
    blob = raw[start + dpos : start + dpos + dlen]
    if len(blob) != dlen:
        raise ValueError("a PyInstaller member runs past the end of the file")
    return zlib.decompress(blob) if cflag else blob


def pyz_magic(raw: bytes, start: int, entries) -> bytes:
    """The real Python bytecode magic from the first PYZ (for the .pyc header); b"" if none."""
    for _, dpos, dlen, _, _, typ in entries:
        if typ in b"zZ":
            blob = raw[start + dpos : start + dpos + dlen]
            if blob[:4] == PYZ_MAGIC:
                return blob[4:8]
    return b""


def pyz_modules(pyz: bytes) -> list[tuple[str, bool, bytes]]:
    """[(module name, is package, marshalled code bytes)] from a PYZ archive."""
    if pyz[:4] != PYZ_MAGIC:
        raise ValueError("not a PYZ archive")
    (toc_off,) = struct.unpack_from("!i", pyz, 8)
    table = marshal.loads(pyz[toc_off:])
    out = []
    for name, entry in table:
        is_pkg, pos, length = entry
        out.append((str(name), bool(is_pkg), zlib.decompress(pyz[pos : pos + length])))
    return out


def as_pyc(magic: bytes, code: bytes) -> bytes:
    """A loadable .pyc (16-byte header: magic + zeroed flags/mtime/size) around a code object."""
    return magic + struct.pack("<III", 0, 0, 0) + code
