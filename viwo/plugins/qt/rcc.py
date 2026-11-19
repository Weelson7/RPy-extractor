"""Qt resource collection (`.rcc`) reader and writer, versions 1-3 (the `qres` binary form Qt's
rcc tool writes and QResource loads). Three big-endian tables: a node tree (`qt_resource_struct`),
a name table (`qt_resource_name`) and the data blobs (`qt_resource_data`). A node is 14 bytes in
version 1 and 22 bytes in versions 2-3 (an 8-byte timestamp on every node). A blob may be stored
raw, zlib-compressed (Qt's qCompress: a 4-byte length then the zlib stream) or zstd-compressed
(no decoder here: reported). The writer keeps the name tree and node tree verbatim and only lays
the data out again, so an unchanged resource comes back byte for byte and an edit changes nothing
else."""

import struct
import zlib

MAGIC = b"qres"
COMPRESSED = 0x01
DIRECTORY = 0x02
COMPRESSED_ZSTD = 0x04


def parse_header(raw: bytes) -> tuple[int, int, int, int]:
    """(version, tree offset, data offset, name offset); all offsets absolute."""
    if raw[:4] != MAGIC:
        raise ValueError("not an rcc file (no qres magic)")
    version, tree_off, data_off, name_off = struct.unpack_from(">IIII", raw, 4)
    if version not in (1, 2, 3):
        raise ValueError(f"rcc version {version}: only 1-3 are known")
    return version, tree_off, data_off, name_off


def _name(raw: bytes, name_off: int, rel: int) -> tuple[str, int]:
    """(name, bytes the entry occupies) at name_off + rel."""
    (length,) = struct.unpack_from(">H", raw, name_off + rel)
    text = raw[name_off + rel + 6 : name_off + rel + 6 + length * 2].decode("utf-16-be")
    return text, 6 + length * 2


def read_tree(raw: bytes):
    """(version, data offset, [(path, flags, data rel, node base)], total nodes, name end)."""
    version, tree_off, data_off, name_off = parse_header(raw)
    size = 14 if version == 1 else 22
    files: list[tuple[str, int, int, int]] = []
    state = {"nodes": 1, "name_end": 0}

    def walk(i: int, prefix: str) -> None:
        base = tree_off + i * size
        name_rel, flags = struct.unpack_from(">IH", raw, base)
        name, used = ("", 0) if i == 0 else _name(raw, name_off, name_rel)
        state["name_end"] = max(state["name_end"], name_rel + used)
        path = f"{prefix}/{name}" if prefix and name else (name or prefix)
        if flags & DIRECTORY:
            count, first = struct.unpack_from(">II", raw, base + 6)
            state["nodes"] = max(state["nodes"], first + count)
            for child in range(first, first + count):
                walk(child, path)
        else:
            (data_rel,) = struct.unpack_from(">I", raw, base + 10)
            files.append((path, flags, data_rel, base))

    walk(0, "")
    return version, data_off, files, state["nodes"], state["name_end"]


def blob(raw: bytes, data_off: int, data_rel: int, flags: int) -> bytes:
    at = data_off + data_rel
    (size,) = struct.unpack_from(">I", raw, at)
    chunk = raw[at + 4 : at + 4 + size]
    if len(chunk) != size:
        raise ValueError("a resource runs past the end of the rcc")
    if flags & COMPRESSED_ZSTD:
        raise ValueError("zstd-compressed resource (no decoder)")
    return zlib.decompress(chunk[4:]) if flags & COMPRESSED else chunk


def extract(raw: bytes) -> list[tuple[str, bytes, str]]:
    """[(path, content, note)] for every file node; note is "" unless the blob could not be read."""
    version, data_off, files, _, _ = read_tree(raw)
    out = []
    for path, flags, data_rel, _ in files:
        try:
            out.append((path, blob(raw, data_off, data_rel, flags), ""))
        except (ValueError, zlib.error, struct.error) as exc:
            out.append((path, b"", str(exc)))
    return out


def build(raw: bytes, edited: dict[str, bytes]) -> bytes:
    """`raw` rebuilt with edited (path -> new bytes); byte-identical when edited is empty and the
    tables sit in tree/name/data order. Edited blobs are stored raw (compressed flag cleared)."""
    _, tree_off, _, name_off = parse_header(raw)
    version, data_off, files, nodes, name_end = read_tree(raw)
    size = 14 if version == 1 else 22
    head_len = 24 if version >= 3 else 20
    tree = bytearray(raw[tree_off : tree_off + nodes * size])
    names = raw[name_off : name_off + name_end]
    data, at = bytearray(), 0
    for path, flags, data_rel, base in sorted(files, key=lambda f: f[2]):
        rel = base - tree_off
        if path in edited:
            payload = struct.pack(">I", len(edited[path])) + edited[path]
            struct.pack_into(">H", tree, rel + 4, flags & ~(COMPRESSED | COMPRESSED_ZSTD))
        else:
            (stored,) = struct.unpack_from(">I", raw, data_off + data_rel)
            payload = raw[data_off + data_rel : data_off + data_rel + 4 + stored]
        struct.pack_into(">I", tree, rel + 10, at)
        data += payload
        at += len(payload)
    tree_at, name_at = head_len, head_len + len(tree)
    header = MAGIC + struct.pack(">IIII", version, tree_at, name_at + len(names), name_at)
    if version >= 3:
        header += raw[20:24]
    return header + bytes(tree) + names + bytes(data)
