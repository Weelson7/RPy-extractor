"""Core-owned unarchive backends (doc 8.4): stdlib zip/tar, 7-Zip CLI, py7zr, unrar CLI."""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

from viwo.contracts.slots import Unarchiver
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

SEVENZIP = DependencySpec(
    "sevenzip",
    "7-Zip (7z/7za/7zr)",
    executables=("7z", "7zz", "7za", "7zr"),
    install_dirs=("7-Zip",),
    hint="install 7-Zip (Windows) or p7zip-full (Linux)",
)
UNRAR = DependencySpec("unrar", "unrar", executables=("unrar",), hint="install unrar")
PY7ZR = DependencySpec(
    "py7zr", "py7zr", kind="python", import_name="py7zr", hint="pip install py7zr"
)


def count_files(folder: Path) -> int:
    return sum(1 for p in folder.rglob("*") if p.is_file())


def _done(dest: Path) -> Outcome:
    return Outcome(OutcomeKind.OK, count_files(dest))


def safe_tar_members(tf: tarfile.TarFile, dest: Path) -> list[tarfile.TarInfo]:
    """Regular files and dirs that stay inside dest (no links, devices, traversal)."""
    root = dest.resolve()
    keep = []
    for member in tf.getmembers():
        target = (root / member.name).resolve()
        inside = target == root or root in target.parents
        if inside and (member.isfile() or member.isdir()):
            keep.append(member)
    return keep


class ZipBackend(Unarchiver):
    backend_id, license = "py-zipfile", "PSF-2.0"

    def extract(self, archive, dest, ctx) -> Outcome:
        try:
            with zipfile.ZipFile(archive) as zf:  # zipfile strips ".." and absolute paths
                zf.extractall(dest)
        except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError) as exc:
            return Outcome(OutcomeKind.FAILED, error=str(exc)[:300])
        return _done(dest)


class TarBackend(Unarchiver):
    backend_id, license = "py-tarfile", "PSF-2.0"

    def extract(self, archive, dest, ctx) -> Outcome:
        try:
            with tarfile.open(archive, "r:*") as tf:
                members = safe_tar_members(tf, dest)
                if hasattr(tarfile, "data_filter"):
                    tf.extractall(dest, members=members, filter="data")
                else:
                    tf.extractall(dest, members=members)
        except (tarfile.TarError, OSError) as exc:
            return Outcome(OutcomeKind.FAILED, error=str(exc)[:300])
        return _done(dest)


class _CliBackend(Unarchiver):
    spec: DependencySpec

    def dependencies(self):
        return (self.spec,)

    def argv(self, archive: Path, dest: Path) -> list[str]:
        raise NotImplementedError

    def extract(self, archive, dest, ctx) -> Outcome:
        tool = ctx.os.tools.locate(self.spec)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=self.spec.hint)
        result = ctx.os.process.run(
            [*tool.argv_prefix, *self.argv(archive, dest)], timeout=3600, cancel=ctx.cancel
        )
        if not result.ok:
            text = (result.stderr or result.stdout).strip()
            kind = OutcomeKind.NEEDS_KEY if "password" in text.lower() else OutcomeKind.FAILED
            return Outcome(kind, error=text[:300] or f"exit code {result.returncode}")
        return _done(dest)


class SevenZipCli(_CliBackend):
    backend_id, license, isolation, spec = "sevenzip-cli", "LGPL-2.1", "subprocess", SEVENZIP

    def argv(self, archive: Path, dest: Path) -> list[str]:
        return ["x", "-y", "-p", f"-o{dest}", str(archive)]


class UnrarCli(_CliBackend):
    backend_id, license, isolation, spec = "unrar-cli", "unRAR", "subprocess", UNRAR

    def argv(self, archive: Path, dest: Path) -> list[str]:
        return ["x", "-o+", "-y", "-p-", str(archive), f"{dest}/"]


class Py7zrBackend(Unarchiver):
    backend_id, license = "py7zr", "LGPL-2.1"

    def dependencies(self):
        return (PY7ZR,)

    def extract(self, archive, dest, ctx) -> Outcome:
        try:
            import py7zr
        except ImportError:
            return Outcome(OutcomeKind.UNAVAILABLE, error=PY7ZR.hint)
        try:
            with py7zr.SevenZipFile(archive, mode="r") as sz:
                if sz.needs_password():
                    return Outcome(OutcomeKind.NEEDS_KEY, error="archive is encrypted")
                sz.extractall(path=dest)
        except Exception as exc:  # py7zr raises many unrelated types
            return Outcome(OutcomeKind.FAILED, error=str(exc)[:300])
        return _done(dest)
