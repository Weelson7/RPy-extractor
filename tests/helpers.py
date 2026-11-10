"""Shared fakes and synthetic fixture builders (doc 17.4). No real game data."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import tarfile
import time
import unittest
import zipfile
from pathlib import Path

from viwo.contracts import Outcome, OutcomeKind, Unarchiver
from viwo.core.wiring.boot import boot

ROOT = Path(__file__).resolve().parent.parent


def needs(module: str):
    """Skip a test whose module (an optional extra: UnityPy, lz4, py7zr) is not installed."""
    found = importlib.util.find_spec(module) is not None
    return unittest.skipUnless(found, f"{module} not installed")


def homes(tmp) -> dict[str, str]:
    """The config and data homes of both OS layers (Windows and XDG) inside tmp, for
    mock.patch.dict(os.environ, ...): a test never writes into the real user's folders."""
    names = ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME")
    return {name: str(Path(tmp) / name.lower()) for name in names}


def cleanup(tmp, seconds: float = 10.0) -> None:
    """TemporaryDirectory.cleanup() that waits for Windows to let go: a child process killed by
    the test (taskkill /T) releases its working folder a moment after it is reported gone."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            return tmp.cleanup()
        except PermissionError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)


class FakeUnarchiver(Unarchiver):
    """Backend whose availability and outcome are set by the test."""

    def __init__(self, backend_id: str, kind: OutcomeKind = OutcomeKind.OK, up: bool = True):
        self.backend_id, self.kind, self.up, self.calls = backend_id, kind, up, 0

    def available(self, os):
        return (self.up, "" if self.up else "down")

    def extract(self, archive, dest, ctx) -> Outcome:
        self.calls += 1
        if self.kind is OutcomeKind.OK:
            (dest / f"{self.backend_id}.txt").write_text("x")
            return Outcome(OutcomeKind.OK, 1)
        return Outcome(self.kind, error=f"{self.backend_id} says {self.kind.value}")


def write_ini(folder: Path, body: str = "") -> Path:
    path = folder / "test.ini"
    path.write_text(body or "[plugins]\ngeneric = on\n", encoding="utf-8")
    return path


def runtime(folder: Path, body: str = ""):
    return boot(write_ini(folder, body), temp_root=folder / "tmp")


def make_zip(path: Path, members: dict[str, bytes]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def make_tar(path: Path, members: dict[str, bytes]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:gz") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return path


def make_game(root: Path) -> Path:
    """Loose files, a nested zip, and a tar with a traversal member."""
    game = root / "game"
    (game / "data").mkdir(parents=True)
    (game / "data" / "bg.png").write_bytes(b"png-1")
    inner = make_zip(root / "build" / "inner.zip", {"voice/hello.ogg": b"ogg-1"})
    make_zip(game / "outer.zip", {"nested/inner.zip": inner.read_bytes(), "t.txt": b"t"})
    make_tar(game / "extra.tar.gz", {"../escape.txt": b"bad", "ok/readme.md": b"md"})
    return game


def tree_hashes(folder: Path, skip_reserved: bool = False) -> dict[str, str]:
    out = {}
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder).as_posix()
        if path.is_file() and not (skip_reserved and rel.startswith(".")):
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def make_rar(path: Path, members: dict[str, bytes]) -> Path:
    """Minimal RAR 4 archive with stored (uncompressed) members, built from the format spec.
    Free tools cannot create RAR files, so the L5 unrar test uses this builder."""
    import struct
    import zlib

    def block(head_type: int, flags: int, payload: bytes) -> bytes:
        body = struct.pack("<BHH", head_type, flags, 7 + len(payload)) + payload
        return struct.pack("<H", zlib.crc32(body) & 0xFFFF) + body

    dos_time = (2020 - 1980) << 25 | 1 << 21 | 1 << 16
    out = b"Rar!\x1a\x07\x00" + block(0x73, 0, b"\0" * 6)
    for name, data in members.items():
        raw = name.replace("/", "\\").encode("ascii")
        fields = struct.pack(
            "<IIBIIBBHI",
            len(data),
            len(data),
            0,
            zlib.crc32(data),
            dos_time,
            20,
            0x30,
            len(raw),
            0x20,
        )
        out += block(0x74, 0x8000, fields + raw) + data
    path.write_bytes(out + block(0x7B, 0x4000, b""))
    return path


def make_png(path: Path, width: int = 16, height: int = 16, rgb=(255, 59, 59)) -> Path:
    """Tiny valid PNG (solid colour) without any imaging library."""
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    raw = b"".join(b"\0" + bytes(rgb) * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return path
