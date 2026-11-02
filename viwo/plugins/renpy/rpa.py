"""Ren'Py archive (RPA) backends: a safe in-process reader (main) and unrpa (spare).

RPA indexes are zlib-compressed Python pickles. Unpickling untrusted data runs
code, so the safe reader refuses every global except the two bytes builders
protocol 2 uses (`_codecs.encode`, `bytes`). Anything else marks the archive as failed.
"""

from __future__ import annotations

import codecs
import io
import pickle
import zlib
from pathlib import Path

from viwo.contracts.slots import Unarchiver
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

UNRPA = DependencySpec(
    "unrpa",
    "unrpa",
    kind="python",
    import_name="unrpa",
    hint="pip install unrpa (GPL-3.0, runs as a separate process)",
)


# The only callables an RPA index may reference: building bytes values.
_ALLOWED = {
    ("_codecs", "encode"): codecs.encode,
    ("builtins", "bytes"): bytes,
    ("__builtin__", "bytes"): bytes,
}


class _SafeUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        if (module, name) in _ALLOWED:
            return _ALLOWED[(module, name)]
        raise pickle.UnpicklingError(f"forbidden global in RPA index: {module}.{name}")


def _text(value) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.decode("latin-1")
    return str(value)


def read_index(fh) -> dict[str, list[tuple[int, int, bytes]]]:
    """Parse an RPA-2.0/3.0 header and index. Raises ValueError when unsupported."""
    parts = fh.readline().split()
    if not parts or parts[0] not in (b"RPA-2.0", b"RPA-3.0"):
        raise ValueError(f"unsupported RPA header {parts[:1]}")
    offset = int(parts[1], 16)
    key = int(parts[2], 16) if parts[0] == b"RPA-3.0" else 0
    fh.seek(offset)
    raw = _SafeUnpickler(io.BytesIO(zlib.decompress(fh.read())), encoding="bytes").load()
    if not isinstance(raw, dict):
        raise ValueError("RPA index is not a mapping")
    index: dict[str, list[tuple[int, int, bytes]]] = {}
    for name, chunks in raw.items():
        entries = []
        for chunk in chunks:
            start = chunk[2] if len(chunk) > 2 else b""
            prefix = start.encode("latin-1") if isinstance(start, str) else bytes(start)
            entries.append((int(chunk[0]) ^ key, int(chunk[1]) ^ key, prefix))
        index[_text(name)] = entries
    return index


def _target(dest: Path, name: str) -> Path | None:
    root = dest.resolve()
    target = (root / name.replace("\\", "/")).resolve()
    return target if root in target.parents else None


class RpaSafe(Unarchiver):
    backend_id, owner, license = "rpa-safe", "renpy", "MIT"

    def extract(self, archive, dest, ctx) -> Outcome:
        try:
            with open(archive, "rb") as fh:
                index = read_index(fh)
                written = sum(self._write(fh, dest, name, chunks) for name, chunks in index.items())
        except (ValueError, OSError, zlib.error, pickle.UnpicklingError, EOFError) as exc:
            return Outcome(OutcomeKind.FAILED, error=str(exc)[:300])
        return Outcome(OutcomeKind.OK, written)

    @staticmethod
    def _write(fh, dest: Path, name: str, chunks) -> int:
        target = _target(dest, name)
        if target is None:
            return 0  # traversal or absolute member name: skipped
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as out:
            for offset, length, prefix in chunks:
                fh.seek(offset)
                out.write(prefix + fh.read(max(0, length - len(prefix))))
        return 1


class Unrpa(Unarchiver):
    backend_id, owner, license, isolation = "unrpa", "renpy", "GPL-3.0", "subprocess"

    def dependencies(self):
        return (UNRPA,)

    def extract(self, archive, dest, ctx) -> Outcome:
        tool = ctx.os.tools.locate(UNRPA)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=UNRPA.hint)
        argv = [*tool.argv_prefix, "-mp", str(dest), str(archive)]
        result = ctx.os.process.run(argv, timeout=3600, cancel=ctx.cancel)
        if not result.ok:
            text = (result.stderr or result.stdout).strip()
            return Outcome(OutcomeKind.FAILED, error=text[:300] or f"exit {result.returncode}")
        return Outcome(OutcomeKind.OK, sum(1 for p in dest.rglob("*") if p.is_file()))
