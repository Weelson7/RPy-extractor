"""pack.apk / pack.apks / pack.obb: the zip rebuilt in the patched copy with the edited members.
Every other member's compressed bytes are copied unchanged, in their order; each member keeps its
compression method; stored members are aligned as zipalign aligns them (4 bytes; 4096 for `.so`
when the original page-aligned them). An APK's old signature cannot survive an edit: its v1 files
(`META-INF/MANIFEST.MF`, `*.SF`, `*.RSA`, `*.DSA`, `*.EC`) are left out and its v2/v3 signing
block (between the members and the directory) is not copied; sign.py then signs the result."""

import os
import re
import zipfile
import zlib
from dataclasses import replace
from pathlib import Path

from viwo.contracts.slots import Packer, SlotDefinition
from viwo.contracts.types import Outcome, OutcomeKind

from . import zipfmt as z
from .sign import sign

SIGNATURE = re.compile(r"META-INF/(MANIFEST\.MF|[^/]+\.(SF|RSA|DSA|EC))", re.IGNORECASE)
STORED_NEW = (".so", ".arsc")  # new members Android reads in place (mapped): stored
SLOTS = (
    SlotDefinition("pack.apk", "pack", "android", "apk-pack"),
    SlotDefinition("pack.apks", "pack", "android", "apks-pack"),
    SlotDefinition("pack.obb", "pack", "android", "obb-pack"),
)


def _copy(src, out, entry: z.Entry, start: int) -> None:
    src.seek(start)
    left = entry.csize
    while left > 0:
        chunk = src.read(min(left, 1 << 20))
        if not chunk:
            raise ValueError(f"{entry.text}: its data runs past the end of the file")
        out.write(chunk)
        left -= len(chunk)


def _write(out, entry: z.Entry, extra: bytes, body, align: int) -> z.Entry:
    """Write one member at the output's position; returns its record with the new offset."""
    at = out.tell()
    if entry.method == z.STORED:
        extra = z.aligned(extra, at + 30 + len(entry.name) + len(extra), align)
    out.write(z.local_header(entry, extra))
    if isinstance(body, bytes):
        out.write(body)
    else:
        body(out)
    return replace(entry, offset=at)


def _alignment(entry: z.Entry, pages: bool) -> int:
    return z.PAGE if pages and entry.text.endswith(".so") else 4


def rebuild(container: Path, temp: Path, members: dict[str, Path], unsign: bool) -> list[str]:
    """Write the rebuilt zip to temp; the notes on what it changed beyond the edits."""
    notes, written, dropped = [], [], 0
    with open(container, "rb") as src, open(temp, "wb") as out:
        entries, comment = z.read_entries(src, container.stat().st_size)
        pages = z.page_aligned(src, entries)
        for entry in entries:
            if unsign and SIGNATURE.fullmatch(entry.text):
                dropped += 1
                continue
            start, local_extra = z.data_at(src, entry)
            extra = z.records(local_extra)
            if entry.text in members:
                if entry.method not in (z.STORED, z.DEFLATED):
                    notes.append(f"{entry.text}: method {entry.method} rewritten as deflate")
                entry, body = z.packed(entry, members[entry.text].read_bytes())
            else:
                body = lambda fh, e=entry, s=start: _copy(src, fh, e, s)  # noqa: E731
            written.append(_write(out, entry, extra, body, _alignment(entry, pages)))
        known = {e.text for e in entries}
        for name in sorted(set(members) - known):
            method = z.STORED if name.lower().endswith(STORED_NEW) else z.DEFLATED
            entry, body = z.new_entry(name, members[name].read_bytes(), method)
            written.append(_write(out, entry, b"", body, _alignment(entry, pages)))
        cd_at = out.tell()
        for entry in written:
            out.write(z.central_record(entry))
        out.write(z.end_record(len(written), out.tell() - cd_at, cd_at, comment))
    if dropped:
        notes.append(f"{dropped} old v1 signature file(s) left out (META-INF): they sign the "
                     "original bytes")  # fmt: skip
    how = "4096 for .so, 4 for the rest" if pages else "4 bytes"
    return [*notes, f"stored members aligned ({how}), every untouched member's bytes copied"]


class _ZipPacker(Packer):
    owner, license = "android", "MIT"
    parses_untrusted_in_process = True  # doc 8.4: reads the package's zip
    unsign = False

    def __init__(self, settings: dict | None = None) -> None:
        self.settings = settings if settings is not None else {}

    def pack(self, container: Path, members: dict[str, Path], ctx) -> Outcome:
        temp = container.with_name(container.name + ".viwo-tmp")
        try:
            notes = rebuild(container, temp, members, self.unsign)
            os.replace(temp, container)
        except (OSError, ValueError, zlib.error) as exc:
            temp.unlink(missing_ok=True)
            return Outcome(OutcomeKind.FAILED, error=f"{container.name}: {exc}"[:300])
        if self.unsign:
            notes += sign(container, ctx, self.settings)
        return Outcome(OutcomeKind.OK, len(members), notes=tuple(notes))

    def verify(self, output: Path, members: dict[str, Path], ctx):
        """The edited members as the rebuilt zip holds them (a signer adds its own files)."""
        bad = []
        try:
            with zipfile.ZipFile(output) as zf:
                names = set(zf.namelist())
                for member, edited in members.items():
                    if member not in names or zf.read(member) != edited.read_bytes():
                        bad.append(member)
        except (OSError, ValueError, zipfile.BadZipFile, zlib.error):
            return list(members)
        return bad


class ApkPacker(_ZipPacker):
    backend_id, unsign = "apk-pack", True


class BundlePacker(_ZipPacker):
    backend_id = "apks-pack"  # .xapk / .apks / .apkm: a zip of APKs, never signed itself


class ObbPacker(_ZipPacker):
    backend_id = "obb-pack"  # an expansion file: a plain zip, never signed
