"""Shared fakes and synthetic fixture builders (doc 17.4). No real game data."""

from __future__ import annotations

import hashlib
import io
import tarfile
import zipfile
from pathlib import Path

from viwo.contracts import Outcome, OutcomeKind, Unarchiver
from viwo.core.wiring.boot import boot

ROOT = Path(__file__).resolve().parent.parent


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
