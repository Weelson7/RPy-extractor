"""The way back for Wolf RPG archives (doc 18.3): the container rewritten with its edited members
(Wolf RPG loads nothing over its archive, so it is rebuilt, not overridden). Every member is
stored raw (not DXA-compressed) in a fresh version 6 DXArchive; a key, when the original had one,
re-applies as the same XOR stream. The reader (`wolf.py`) reads it back, so VERIFY re-extracts."""

import struct

from .wolf import HEADER, MAGIC, NONE, VERSION, unkey


def _field(text: bytes) -> bytes:
    """A NUL-terminated name padded to a 4-byte boundary."""
    out = text + b"\x00"
    return out + b"\x00" * ((-len(out)) % 4)


def _packet(name: str) -> bytes:
    """A FileNameTable packet: units, parity, the upper-case copy, then the real name."""
    body = _field(name.upper().encode("utf-8")) + _field(name.encode("utf-8"))
    return struct.pack("<HH", (4 + len(body)) // 4, 0) + body


class _Tree:
    """A directory of the archive while it is laid out."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.dirs: dict[str, _Tree] = {}


def _insert(root: _Tree, path: str, data: bytes) -> None:
    node, parts = root, [p for p in path.split("/") if p]
    for part in parts[:-1]:
        node = node.dirs.setdefault(part, _Tree())
    node.files[parts[-1]] = data


def _order(root: _Tree) -> list:
    """Directories in breadth-first index order, each with its parent's index."""
    dirs, queue = [(root, "", 0xFFFFFFFFFFFFFFFF)], [(root, 0)]
    while queue:
        node, index = queue.pop(0)
        for name, child in node.dirs.items():
            queue.append((child, len(dirs)))
            dirs.append((child, name, index))
    return dirs


def _build(members: dict[str, bytes]) -> bytes:
    root = _Tree()
    for path, data in sorted(members.items()):
        _insert(root, path, data)
    dirs = _order(root)
    index_of = {id(node): i for i, (node, _, _) in enumerate(dirs)}
    names, files, data_blob = bytearray(), bytearray(), bytearray()
    dir_runs = []  # (first file-table byte offset, child count) per directory
    for node, _, _ in dirs:
        dir_runs.append((len(files), len(node.files) + len(node.dirs)))
        for name, blob in sorted(node.files.items()):
            files += _entry(names, name, 0, len(data_blob), len(blob), NONE)
            data_blob += blob
        for name, child in node.dirs.items():
            files += _entry(names, name, 0x10, index_of[id(child)] * 32, 0, 0)
    dirtable = _dir_table(dirs, index_of, dir_runs)
    return _assemble(names, files, dirtable, data_blob)


def _entry(names: bytearray, name: str, attr: int, offset: int, size: int, pressed: int) -> bytes:
    name_off = len(names)
    names += _packet(name)
    return struct.pack("<IIQQQQQQ", name_off, attr, 0, 0, 0, offset, size, pressed)


def _dir_table(dirs: list, index_of: dict, runs: list) -> bytearray:
    table = bytearray()
    for i, (_, _, parent) in enumerate(dirs):
        first, count = runs[i]
        table += struct.pack("<4Q", 0, parent, count, first)
    return table


def _assemble(names: bytes, files: bytes, dirtable: bytes, data: bytes) -> bytes:
    head_size = len(names) + len(files) + len(dirtable)
    data_start = HEADER + head_size
    header = struct.pack(
        "<HHIIIIII",
        MAGIC,
        VERSION,
        head_size,
        data_start,
        0,
        len(names),
        len(names) + len(files),
        0,
    )
    return header + bytes(names) + bytes(files) + bytes(dirtable) + bytes(data)


def write_archive(members: dict[str, bytes], key: bytes = b"") -> bytes:
    """A version 6 DXArchive holding `members` (path -> bytes), stored raw, keyed when `key`."""
    blob = _build(members)
    return unkey(blob, key) if key else blob
