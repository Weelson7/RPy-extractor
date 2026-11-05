"""Unreal .pak footers, IoStore .utoc headers, key verification and the CLI backends."""

import os
import shutil
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path

from viwo.contracts.slots import Match, Packer, Unarchiver
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind
from viwo.contracts.workspace import count_files, stage_members

from .aes import decrypt_block
from .keys import resolve_key

PAK_MAGIC = struct.pack("<I", 0x5A6F12E1)
UTOC_MAGIC = b"-==--==--==--==-"
TAIL = 512
REPAK = DependencySpec(
    "repak",
    "repak",
    env_var="VIWO_REPAK",
    executables=("repak",),
    hint="install repak (MIT/Apache-2.0) from trumank/repak",
)
RETOC = DependencySpec(
    "retoc",
    "retoc",
    env_var="VIWO_RETOC",
    executables=("retoc",),
    hint="install retoc (MIT) from trumank/retoc for UE5 IoStore (.utoc/.ucas)",
)


@dataclass(frozen=True)
class PakInfo:
    version: int
    index_offset: int
    index_size: int
    encrypted_index: bool


def pak_info(path: Path, tail: bytes | None = None) -> PakInfo | None:
    """Footer of a pak (versions 1-11): magic, version, index offset/size, encryption flag."""
    if tail is None:
        size = path.stat().st_size
        with open(path, "rb") as fh:
            fh.seek(max(0, size - TAIL))
            tail = fh.read()
    at = tail.rfind(PAK_MAGIC)
    if at < 0 or at + 24 > len(tail):
        return None
    version, offset, length = struct.unpack_from("<IQQ", tail, at + 4)
    if not 1 <= version <= 15:
        return None
    encrypted = version >= 4 and at >= 1 and tail[at - 1] == 1
    return PakInfo(version, offset, length, encrypted)


def identify_unreal(path: Path, head: bytes, tail: bytes) -> Match | None:
    name = path.name.lower()
    if name.endswith(".utoc") and head.startswith(UTOC_MAGIC):
        return Match("unarchive.utoc", path)
    if name.endswith(".pak") and pak_info(path) is not None:
        return Match("unarchive.upak", path)
    return None


def key_opens(path: Path, info: PakInfo, key: bytes) -> bool:
    """A key is right when the decrypted index starts with a sane mount point FString."""
    with open(path, "rb") as fh:
        fh.seek(info.index_offset)
        block = fh.read(16)
    if len(block) < 16:
        return False
    plain = decrypt_block(key, block)
    (length,) = struct.unpack_from("<i", plain)
    text = plain[4 : 4 + min(length, 12)] if 0 < length <= 1024 else b""
    return bool(text) and all(32 <= b < 127 for b in text.rstrip(b"\0")) and b"/" in text


class _UnrealCli(Unarchiver):
    spec: DependencySpec
    owner, isolation, supports_keys = "unreal", "subprocess", True

    def dependencies(self):
        return (self.spec,)

    def input_for(self, archive: Path, ctx) -> Path:
        """What the tool reads for this archive (the archive itself unless a backend says)."""
        return archive

    def extract(self, archive, dest, ctx) -> Outcome:
        if (tool := ctx.os.tools.locate(self.spec)) is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=self.spec.hint)
        key, problem = resolve_key(archive, ctx)
        if problem:
            return Outcome(OutcomeKind.NEEDS_KEY, error=problem)
        # repak 0.2 and retoc 0.1 take the key only as --aes-key (no env var or key file), so
        # it is on the command line of that one process; it is never logged by ViWo (run
        # records store <secret>) and every text the tool prints back is masked below.
        prefix = ["--aes-key", f"0x{key}"] if key else []
        source = self.input_for(archive, ctx)
        try:
            result = ctx.os.process.run(
                [*tool.argv_prefix, *prefix, *self.argv(source, dest)],
                timeout=6 * 3600,
                cancel=ctx.cancel,
                on_line=ctx.tool_output("unpack", mask=key),
            )
        finally:
            if source != archive:  # a staging folder (links or copies): never kept
                shutil.rmtree(source, ignore_errors=True)
        text = (result.stderr or result.stdout).strip()
        if key:
            text = text.replace(key, "<secret>").replace(key.upper(), "<secret>")
        if not result.ok:
            kind = (
                OutcomeKind.NEEDS_KEY
                if "aes" in text.lower() or "encrypt" in text.lower()
                else OutcomeKind.FAILED
            )
            return Outcome(kind, error=text[-300:] or f"exit {result.returncode}")
        return Outcome(OutcomeKind.OK, count_files(dest))


class RepakCli(_UnrealCli):
    backend_id, license, spec = "repak-cli", "MIT OR Apache-2.0", REPAK

    def argv(self, archive, dest):
        return ["unpack", "--quiet", "--output", str(dest), str(archive)]


class RetocLegacy(_UnrealCli):
    """IoStore to legacy .uasset/.uexp (what most asset viewers read)."""

    backend_id, license, spec = "retoc-legacy", "MIT", RETOC

    def argv(self, archive, dest):
        return ["to-legacy", str(archive), str(dest)]

    def input_for(self, archive: Path, ctx) -> Path:
        """A game container needs the script objects of `global.utoc` beside it, and retoc reads
        those only from a folder: one folder with global and this container (hard links, a copy
        where the volume refuses), so every container converts once and stays its own."""
        glob_toc = archive.with_name("global.utoc")
        if archive.name.lower() == "global.utoc" or not glob_toc.is_file():
            return archive
        ctx.scratch.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix="retoc-", dir=ctx.scratch))
        for src in (glob_toc, glob_toc.with_suffix(".ucas"), archive, archive.with_suffix(".ucas")):
            if src.is_file():
                try:
                    os.link(src, folder / src.name)
                except OSError:  # another volume, or links refused: copy
                    shutil.copy2(src, folder / src.name)
        return folder


class RetocUnpack(_UnrealCli):
    """IoStore chunks as loose Zen packages: the fallback when conversion fails."""

    backend_id, license, spec = "retoc-unpack", "MIT", RETOC

    def argv(self, archive, dest):
        return ["unpack", str(archive), str(dest)]


REPAK_VERSIONS = {v: f"V{v}" for v in range(1, 12)} | {8: "V8B"}


class RepakPatch(Packer):
    """Round trip by override: edited assets go into <container>_P.pak, which the engine
    mounts over the original. Signed games (.sig) may refuse it; that is reported."""

    backend_id, owner, license, isolation = (
        "repak-patch",
        "unreal",
        "MIT OR Apache-2.0",
        "subprocess",
    )

    requires = (REPAK,)
    override = True

    def output_for(self, container: Path) -> Path:
        return container.with_name(f"{container.stem}_P.pak")

    def pack(self, container, members, ctx) -> Outcome:
        tool, info = ctx.os.tools.locate(REPAK), pak_info(container)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=REPAK.hint)
        ctx.scratch.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix="pak-", dir=ctx.scratch))  # one per pack call
        staged = stage_members(members, root)  # unsafe names are skipped, not counted
        version = REPAK_VERSIONS.get(info.version if info else 8, "V8B")
        argv = [
            *tool.argv_prefix,
            "pack",
            "--version",
            version,
            str(root),
            str(self.output_for(container)),
        ]
        result = ctx.os.process.run(
            argv, timeout=3600, cancel=ctx.cancel, on_line=ctx.tool_output("pack")
        )
        if not result.ok:
            return Outcome(OutcomeKind.FAILED, error=(result.stderr or result.stdout)[-300:])
        notes = (
            ("signed game (.sig files): it may refuse the patch",)
            if list(container.parent.glob("*.sig"))
            else ()
        )
        return Outcome(OutcomeKind.OK, len(staged), notes=notes)
