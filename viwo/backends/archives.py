"""Core-owned unarchive backends (doc 8.4): stdlib zip/tar, 7-Zip CLI, py7zr, unrar CLI."""

import shutil
import tarfile
import zipfile
import zlib
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.slots import Unarchiver
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind
from viwo.contracts.workspace import count_files

SEVENZIP = DependencySpec.of("sevenzip")
UNRAR = DependencySpec.of("unrar")
PY7ZR = DependencySpec.of("py7zr")


# what the stdlib readers raise on damaged bytes besides their own error: a bad name
# (UnicodeDecodeError is a ValueError), a stream cut short (EOFError), bad deflate data
DAMAGED = (OSError, ValueError, EOFError, zlib.error)


def _done(dest: Path, names: ws.Names | None = None, links: int = 0) -> Outcome:
    files = count_files(dest)
    notes = (f"{links} link or device member(s) skipped",) if links else ()
    return Outcome(OutcomeKind.OK, files, notes=(names.save() if names else ()) + notes)


def _cancelled(ctx) -> bool:
    """A verify read-back may run without a cancel token."""
    return bool(getattr(getattr(ctx, "cancel", None), "cancelled", False))


def _copy_member(names: ws.Names, name: str, src) -> None:
    target = names.target(name)
    if target is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        with src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)


class ZipBackend(Unarchiver):
    backend_id, license = "py-zipfile", "PSF-2.0"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def extract(self, archive, dest, ctx) -> Outcome:
        names = ws.Names(dest)
        try:
            with zipfile.ZipFile(archive) as zf:
                for info in zf.infolist():
                    if _cancelled(ctx):
                        break
                    if not info.is_dir():
                        _copy_member(names, info.filename, zf.open(info))
        except (zipfile.BadZipFile, *DAMAGED, RuntimeError, NotImplementedError) as exc:
            return Outcome(OutcomeKind.FAILED, error=str(exc)[:300])
        return _done(dest, names)


class TarBackend(Unarchiver):
    """Regular files only: links and devices are never recreated (counted)."""

    backend_id, license = "py-tarfile", "PSF-2.0"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    def extract(self, archive, dest, ctx) -> Outcome:
        names, links = ws.Names(dest), 0
        try:
            with tarfile.open(archive, "r:*") as tf:
                for member in tf:
                    if _cancelled(ctx):
                        break
                    if member.isfile():
                        _copy_member(names, member.name, tf.extractfile(member))
                    else:
                        links += not member.isdir()
        except (tarfile.TarError, *DAMAGED) as exc:
            return Outcome(OutcomeKind.FAILED, error=str(exc)[:300])
        return _done(dest, names, links)


class _CliBackend(Unarchiver):
    """A command-line unpacker; each subclass gives its `argv(archive, dest)`."""

    spec: DependencySpec

    def dependencies(self):
        return (self.spec,)

    def extract(self, archive, dest, ctx) -> Outcome:
        if (tool := ctx.os.tools.locate(self.spec)) is None:
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
    self_check_args = ()

    def argv(self, archive: Path, dest: Path) -> list[str]:
        return ["x", "-y", "-p", f"-o{dest}", str(archive)]


class UnrarCli(_CliBackend):
    backend_id, license, isolation, spec = "unrar-cli", "unRAR", "subprocess", UNRAR
    self_check_args = ()

    def argv(self, archive: Path, dest: Path) -> list[str]:
        return ["x", "-o+", "-y", "-p-", str(archive), f"{dest}/"]


class Py7zrBackend(Unarchiver):
    backend_id, license = "py7zr", "LGPL-2.1"
    parses_untrusted_in_process = True  # doc 8.4: untrusted bytes in the ViWo process

    requires = (PY7ZR,)

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
