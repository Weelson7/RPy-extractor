"""AES key resolution (D18): the user's key wins; otherwise candidates from the game's own
executables, each verified against an encrypted pak index. Nothing is guessed."""

from __future__ import annotations

import base64
import binascii
import mmap
import re
import struct
from pathlib import Path

# 8 x "mov dword ptr [reg+disp], imm32" with displacements 4 apart: an inlined 32-byte key.
MOVS = (  # (pattern, instruction length, displacement offset, displacement format)
    (re.compile(rb"(?:\xc7[\x40-\x43\x45-\x47][\x00-\xff]{5}){8}", re.S), 7, 2, "<b"),
    (re.compile(rb"(?:\xc7\x44\x24[\x00-\xff]{5}){8}", re.S), 8, 3, "<b"),
    (re.compile(rb"(?:\xc7\x85[\x00-\xff]{8}){8}", re.S), 10, 2, "<i"),
    (re.compile(rb"(?:\xc7\x84\x24[\x00-\xff]{8}){8}", re.S), 11, 3, "<i"),
)
HEX = re.compile(rb"(?<![0-9A-Fa-f])(?:0x)?([0-9A-Fa-f]{64})(?![0-9A-Fa-f])")
UTOC_FLAGS, ENCRYPTED = 80, 2
_CACHE: dict[tuple, list[bytes]] = {}


def parse_key(text: str) -> bytes | None:
    """Hex (optional 0x) or base64, 32 bytes."""
    text = text.strip()
    try:
        raw = bytes.fromhex(text[2:] if text.lower().startswith("0x") else text)
    except ValueError:
        try:
            raw = base64.b64decode(text + "=" * (-len(text) % 4), validate=True)
        except (binascii.Error, ValueError):
            return None
    return raw if len(raw) == 32 else None


def _from_movs(m) -> list[bytes]:
    found = []
    for pattern, size, at, fmt in MOVS:
        width = struct.calcsize(fmt)
        for match in pattern.finditer(m):
            run = match.group(0)
            disps = [struct.unpack_from(fmt, run, i * size + at)[0] for i in range(8)]
            if all(b - a == 4 for a, b in zip(disps, disps[1:])):
                found.append(
                    b"".join(run[i * size + at + width : (i + 1) * size] for i in range(8))
                )
    return found


def candidates(game_root: Path) -> list[bytes]:
    """Distinct plausible keys from executables under the game folder (cached per file state)."""
    exes = [p for p in sorted(game_root.rglob("*")) if p.is_file() and _is_binary(p)]
    state = tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in exes)
    if state not in _CACHE:
        keys: list[bytes] = []
        for exe in exes:
            with open(exe, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as m:
                keys += _from_movs(m) + [bytes.fromhex(h.decode()) for h in HEX.findall(m)]
        _CACHE[state] = [k for k in dict.fromkeys(keys) if len(set(k)) >= 12]
    return _CACHE[state]


def _is_binary(path: Path) -> bool:
    name, size = path.name.lower(), path.stat().st_size
    if not 4096 <= size <= 2 << 30:
        return False
    return name.endswith((".exe", ".dll")) or (
        "binaries" in path.as_posix().lower() and "." not in name
    )


def _encrypted(archive: Path) -> tuple[bool, Path | None]:
    """(needs a key, a pak whose index can verify one)."""
    from .pak import pak_info

    if archive.suffix.lower() == ".pak":
        info = pak_info(archive)
        return bool(info and info.encrypted_index), archive
    with open(archive, "rb") as fh:
        head = fh.read(UTOC_FLAGS + 1)
    paks = [
        p for p in sorted(archive.parent.glob("*.pak")) if (i := pak_info(p)) and i.encrypted_index
    ]
    return len(head) > UTOC_FLAGS and bool(head[UTOC_FLAGS] & ENCRYPTED), (
        paks[0] if paks else None
    )


def resolve_key(archive: Path, ctx) -> tuple[str, str]:
    """(hex key or "", problem). The problem is set only when a key is needed and missing."""
    from .pak import key_opens, pak_info

    needed, probe = _encrypted(archive)
    user = str(ctx.options.get("aes_key") or "")
    if user:
        key = parse_key(user)
        return (key.hex(), "") if key else ("", "aes_key must be 32 bytes as hex or base64")
    if not needed:
        return "", ""
    if not ctx.options.get("find_key", True) or probe is None:
        return "", "encrypted: give the AES key (option aes_key)"
    info = pak_info(probe)
    for key in candidates(ctx.game_root):
        if info and key_opens(probe, info, key):
            ctx.log(
                f"AES key found in the game's executable, verified on {probe.name}", stage="unpack"
            )
            return key.hex(), ""
    return "", "encrypted: no key in the game's executables opens the index; give aes_key"
