"""Archive member names for REDengine 4: a game stores each file under the FNV-1a 64 hash of its
path; a path list a game plugin supplies (Cyberpunk 2077: WolvenKit's `usedhashes.kark`, pinned
in tools.json as `cp77-hashes`) names them. The list is Kraken-compressed, so it is inflated
with the game's own Oodle (like the archives) once, then kept beside the pin as text plus a
sorted index
(`usedhashes.txt`, `usedhashes.idx`: hashes, then line offsets) that later runs only load."""

from __future__ import annotations

import bisect
import mmap
import struct
from array import array
from pathlib import Path


def fnv1a64(data: bytes) -> int:
    value = 0xCBF29CE484222325
    for byte in data:
        value = ((value ^ byte) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return value


def _build(kark: Path, oodle, text: Path, index: Path) -> None:
    packed = kark.read_bytes()
    if packed[:4] != b"KARK":
        raise ValueError(f"{kark.name} is not a KARK file")
    plain = oodle.decompress(packed[8:], struct.unpack_from("<I", packed, 4)[0])
    if plain is None:
        raise ValueError("the game's Oodle could not inflate the path list")
    rows, at = [], 0
    for line in plain.split(b"\r\n"):
        if line:
            rows.append((fnv1a64(line), at))
        at += len(line) + 2
    rows.sort()
    text.write_bytes(plain)
    with open(index, "wb") as fh:
        array("Q", (h for h, _ in rows)).tofile(fh)
        array("Q", (o for _, o in rows)).tofile(fh)


class Names:
    """hash -> path, from the inflated list (built on first use; None when unavailable)."""

    def __init__(self, text: Path, index: Path) -> None:
        raw = array("Q")
        with open(index, "rb") as fh:
            raw.fromfile(fh, index.stat().st_size // 8)
        half = len(raw) // 2
        self.hashes, self.offsets = raw[:half], raw[half:]
        with open(text, "rb") as fh:
            self.text = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)

    @classmethod
    def load(cls, kark: Path | None, oodle) -> "Names | None":
        if kark is None or oodle is None:
            return None
        text, index = kark.with_suffix(".txt"), kark.with_suffix(".idx")
        if not index.is_file() or index.stat().st_mtime < kark.stat().st_mtime:
            _build(kark, oodle, text, index)
        return cls(text, index)

    def get(self, name_hash: int) -> str | None:
        i = bisect.bisect_left(self.hashes, name_hash)
        if i == len(self.hashes) or self.hashes[i] != name_hash:
            return None
        start = self.offsets[i]
        end = self.text.find(b"\r\n", start)
        return self.text[start : end if end >= 0 else len(self.text)].decode("utf-8", "replace")

    def close(self) -> None:
        self.text.close()
