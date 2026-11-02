"""Unreal .pak footers, IoStore .utoc headers, key verification and the CLI backends."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from viwo.contracts.slots import Match, Unarchiver
from viwo.contracts.types import DependencySpec, Outcome, OutcomeKind

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


def _files(dest: Path) -> int:
    return sum(1 for p in dest.rglob("*") if p.is_file())


class _UnrealCli(Unarchiver):
    spec: DependencySpec
    owner, isolation, supports_keys = "unreal", "subprocess", True

    def dependencies(self):
        return (self.spec,)

    def argv(self, archive: Path, dest: Path) -> list[str]:
        raise NotImplementedError

    def extract(self, archive, dest, ctx) -> Outcome:
        tool = ctx.os.tools.locate(self.spec)
        if tool is None:
            return Outcome(OutcomeKind.UNAVAILABLE, error=self.spec.hint)
        key, problem = resolve_key(archive, ctx)
        if problem:
            return Outcome(OutcomeKind.NEEDS_KEY, error=problem)
        prefix = ["--aes-key", f"0x{key}"] if key else []
        result = ctx.os.process.run(
            [*tool.argv_prefix, *prefix, *self.argv(archive, dest)],
            timeout=6 * 3600,
            cancel=ctx.cancel,
        )
        text = (result.stderr or result.stdout).strip()
        if not result.ok:
            kind = (
                OutcomeKind.NEEDS_KEY
                if "aes" in text.lower() or "encrypt" in text.lower()
                else OutcomeKind.FAILED
            )
            return Outcome(kind, error=text[-300:] or f"exit {result.returncode}")
        return Outcome(OutcomeKind.OK, _files(dest))


class RepakCli(_UnrealCli):
    backend_id, license, spec = "repak-cli", "MIT OR Apache-2.0", REPAK

    def argv(self, archive, dest):
        return ["unpack", "--quiet", "--output", str(dest), str(archive)]


class RetocLegacy(_UnrealCli):
    """IoStore to legacy .uasset/.uexp (what most asset viewers read)."""

    backend_id, license, spec = "retoc-legacy", "MIT", RETOC

    def argv(self, archive, dest):
        return ["to-legacy", str(archive), str(dest)]


class RetocUnpack(_UnrealCli):
    """IoStore chunks as loose Zen packages: the fallback when conversion fails."""

    backend_id, license, spec = "retoc-unpack", "MIT", RETOC

    def argv(self, archive, dest):
        return ["unpack", str(archive), str(dest)]
