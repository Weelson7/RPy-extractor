"""RDAR index reader, CR2W type sniffing and the Oodle bridge (the game's own DLL)."""

import ctypes
import struct
from dataclasses import dataclass
from pathlib import Path

from viwo.contracts import workspace as ws

KARK = b"KARK"
LIMIT = 1 << 30  # one segment, inflated
FAR = 1 << 48  # no file offset lies beyond this: a larger one is damage, not data
ENTRY, SEGMENT = 56, 16
# CR2W root class -> the extension the game's tooling uses (unknown classes keep `.cr2w`)
CLASSES = {
    "CBitmapTexture": "xbm",
    "CMesh": "mesh",
    "entEntityTemplate": "ent",
    "appearanceAppearanceResource": "app",
    "CMaterialInstance": "mi",
    "CMaterialTemplate": "mt",
    "animAnimSet": "anims",
    "animRig": "rig",
    "MorphTargetMesh": "morphtarget",
    "CCubeTexture": "cubemap",
    "inkWidgetLibraryResource": "inkwidget",
    "JsonResource": "json",
    "questQuestPhaseResource": "questphase",
    "scnSceneResource": "scene",
    "gameJournalResource": "journal",
    "rendFont": "fnt",
    "audioCookedMetadataResource": "audio_metadata",
    "worldStreamingSector": "streamingsector",
    "CParticleSystem": "particle",
    "physicsSystemResource": "physicalscene",
}
SNIFF = ((b"KB2", "bk2"), (b"BIK", "bik"), (b"RIFF", "wem"), (b"OggS", "opus"), (b"\x89PNG", "png"))


@dataclass(frozen=True)
class Entry:
    name_hash: int
    segments: tuple[tuple[int, int, int], ...]  # (offset, packed size, size)


class Archive:
    """One open `.archive`: header, index, entries, member writing."""

    def __init__(self, fh) -> None:
        self.fh = fh
        head = fh.read(24)
        if head[:4] != b"RDAR":
            raise ValueError("not an RDAR archive")
        _version, index_pos, index_size = struct.unpack_from("<IQI", head, 4)
        if index_size > 1 << 28 or index_pos > FAR:
            raise ValueError("index too large or out of the file")
        fh.seek(index_pos)
        self.index = fh.read(index_size)
        _, _, _, self.files, self.segs, _ = struct.unpack_from("<IIQIII", self.index, 0)
        if self.files > 1 << 22 or self.segs > 1 << 24:
            raise ValueError("index counts out of range")
        self.entries_at = 28
        self.segments_at = self.entries_at + ENTRY * self.files

    def _segment(self, i: int) -> tuple[int, int, int]:
        if i >= self.segs:
            raise ValueError("segment index out of range")
        return struct.unpack_from("<QII", self.index, self.segments_at + SEGMENT * i)

    def entries(self):
        for i in range(self.files):
            at = self.entries_at + ENTRY * i
            name_hash, _stamp, _inline, first, last = struct.unpack_from("<QQIII", self.index, at)
            if last < first or last - first > 1 << 16:
                raise ValueError("segment range out of range")
            yield Entry(name_hash, tuple(self._segment(s) for s in range(first, last)))

    def _read(self, segment: tuple[int, int, int], oodle: "Oodle | None") -> bytes | None:
        offset, packed, size = segment
        if size > LIMIT or packed > LIMIT or offset > FAR:
            raise ValueError("segment out of range")
        self.fh.seek(offset)
        data = self.fh.read(packed)
        if packed == size or not data.startswith(KARK):
            return data
        if oodle is None:
            return None
        (raw_size,) = struct.unpack_from("<I", data, 4)
        return oodle.decompress(data[8:], min(raw_size, size))

    def write(self, entry: Entry, out, oodle: "Oodle | None", name: str = "") -> bool:
        """The game's own file at its path when the name is known (else `<hash>.<ext>`): the
        main segment inflated, then the buffer segments exactly as stored (the CR2W buffer
        table gives their on-disk sizes and the reader inflates them itself), the form the
        game and the community tools read."""
        if not entry.segments:
            return True
        main = self._read(entry.segments[0], oodle)
        if main is None:
            return False
        out = out if isinstance(out, ws.Names) else ws.Names(out)  # a folder: its own record
        named = bool(name) and ws.writable(name) is not None  # an escape: kept by its hash, not
        target = out.target(name) if named else None  # counted as skipped (it is not)
        if target is None:
            target = out.dest / f"{entry.name_hash:016x}.{extension(main)}"
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as fh:
            fh.write(main)
            for offset, packed, size in entry.segments[1:]:
                if offset > FAR or packed > LIMIT:
                    raise ValueError("segment out of range")
                self.fh.seek(offset)
                fh.write(self.fh.read(packed))
        return True


def extension(data: bytes) -> str:
    """The CR2W root class mapped to its extension, else a sniffed media type, else `bin`."""
    if data[:4] == b"CR2W":
        name = root_class(data)
        return CLASSES.get(name, "cr2w")
    for magic, ext in SNIFF:
        if data.startswith(magic):
            return ext
    return "bin"


def root_class(data: bytes) -> str:
    """CR2W: table 0 holds the strings, table 1 the names (offset, hash), table 4 the chunks;
    chunk 0's class name is the resource type."""
    try:
        tables = [struct.unpack_from("<III", data, 40 + 12 * t) for t in range(10)]  # 40: header
        strings_at = tables[0][0]
        names_at, _, _ = tables[1]
        chunks_at, chunk_count, _ = tables[4]
        if not chunk_count:
            return ""
        (class_index,) = struct.unpack_from("<H", data, chunks_at)
        (string_offset,) = struct.unpack_from("<I", data, names_at + 8 * class_index)
        end = data.index(b"\0", strings_at + string_offset)
        return data[strings_at + string_offset : end].decode("ascii", "replace")
    except (struct.error, ValueError, IndexError):
        return ""


class Oodle:
    """`OodleLZ_Decompress` from the decompressor the game ships, loaded by the OS layer (which
    answers None where a Windows DLL cannot load)."""

    def __init__(self, lib) -> None:
        self.lib = lib
        fn = self.lib.OodleLZ_Decompress
        fn.restype = ctypes.c_int64
        fn.argtypes = [
            ctypes.c_char_p,
            ctypes.c_int64,
            ctypes.c_void_p,
            ctypes.c_int64,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_int64,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int64,
            ctypes.c_int,
        ]
        self.fn = fn

    @classmethod
    def beside(cls, archive: Path, host) -> "Oodle | None":
        """The game's own `oo2ext_*.dll`, searched upwards from the archive (`bin/x64`)."""
        for parent in [archive.parent, *archive.parents]:
            hits = sorted((parent / "bin" / "x64").glob("oo2ext_*_win64.dll"))
            if hits:
                try:
                    lib = host.load_native(hits[0])
                    return cls(lib) if lib is not None else None
                except OSError:
                    return None
        return None

    def decompress(self, packed: bytes, size: int) -> bytes | None:
        out = ctypes.create_string_buffer(size)
        got = self.fn(packed, len(packed), out, size, 1, 0, 0, None, 0, None, None, None, 0, 3)
        return out.raw[:got] if got > 0 else None
