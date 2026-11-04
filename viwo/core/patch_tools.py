"""T1 helpers (doc 18.8): PE addresses (RVA to file offset, the VA an edit lands at), assembly
through Keystone's `kstool` (GPL-2, so a separate process, never imported), disassembly through
capstone (BSD, a pinned Python package; optional), and AOB signatures that make a patch survive
the next game version (`patch.sig`)."""

from __future__ import annotations

import re
import struct

from viwo.contracts.errors import ViwoError
from viwo.contracts.slots import Backend, SlotDefinition
from viwo.contracts.types import DependencySpec

KEYSTONE = DependencySpec(
    "keystone",
    "Keystone assembler (kstool)",
    env_var="VIWO_KSTOOL",
    executables=("kstool",),
    hint="install Keystone (GPL-2, run as a separate process): `viwo install keystone`",
)
CAPSTONE = DependencySpec(
    "capstone",
    "capstone (disassembler)",
    kind="python",
    import_name="capstone",
    hint="install capstone (BSD) for the disassembly in patch plans: `viwo install capstone`",
)
MACHINES = {0x8664: ("x64", 64), 0x14C: ("x32", 32)}
SLOTS = (SlotDefinition("patch.bytes", "patch", "core", "viwo-patcher"),)


class Patcher(Backend):
    """patch.bytes (doc 18.8): ViWo's own byte writer; `patch.sig` is its signature() below.
    The writing itself is core (viwo/core/patchsets.py); this backend owns the tools it uses,
    so preflight, SYSTEM and `viwo install` see them."""

    backend_id, license, isolation = "viwo-patcher", "MIT", "inprocess"
    families = frozenset({"patch"})

    requires = (KEYSTONE, CAPSTONE)

    def available(self, os):
        return True, ""  # writing bytes needs nothing; asm and disassembly are optional extras


KSTOOL_OUT = re.compile(r"=\s*\[\s*([0-9a-fA-F ]+?)\s*\]")


def pe(data: bytes) -> dict | None:
    """machine, image base and sections of a PE image (None for anything else)."""
    if data[:2] != b"MZ" or len(data) < 0x40:
        return None
    head = struct.unpack_from("<I", data, 0x3C)[0]
    if data[head : head + 4] != b"PE\0\0":
        return None
    machine, count = struct.unpack_from("<HH", data, head + 4)
    opt_size = struct.unpack_from("<H", data, head + 20)[0]
    opt = head + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    base = (
        struct.unpack_from("<Q", data, opt + 24)[0]
        if magic == 0x20B
        else struct.unpack_from("<I", data, opt + 28)[0]
    )
    table, sections = opt + opt_size, []
    for i in range(count):
        vsize, va, raw_size, raw = struct.unpack_from("<IIII", data, table + i * 40 + 8)
        sections.append((va, max(vsize, raw_size), raw, raw_size))
    return {"machine": machine, "base": base, "sections": sections}


def rva_to_offset(data: bytes, rva: int) -> int:
    info = pe(data)
    for va, size, raw, raw_size in (info or {}).get("sections", []):
        if va <= rva < va + size and rva - va < raw_size:
            return raw + rva - va
    raise ViwoError("invalid_request", f"RVA {rva:#x} is in no section of the file (or not a PE)")


def address_of(data: bytes, offset: int) -> int:
    """The virtual address an offset is loaded at (the offset itself outside a PE)."""
    info = pe(data)
    for va, _size, raw, raw_size in (info or {}).get("sections", []):
        if raw <= offset < raw + raw_size:
            return info["base"] + va + offset - raw
    return offset


def arch(data: bytes) -> tuple[str, int]:
    info = pe(data)
    return MACHINES.get(info["machine"], ("x64", 64)) if info else ("x64", 64)


def assemble(ctx_os, text: str, data: bytes, offset: int) -> bytes:
    """`jmp 0x1010; nop` assembled for the file's architecture at the edit's address."""
    tool = ctx_os.tools.locate(KEYSTONE)
    if tool is None:
        raise ViwoError("unavailable", "an `asm` patch needs Keystone", hint=KEYSTONE.hint)
    mode, _ = arch(data)
    argv = [*tool.argv_prefix, mode, text, f"{address_of(data, offset):x}"]
    result = ctx_os.process.run(argv, timeout=30)
    hit = KSTOOL_OUT.search(result.stdout or "")
    if hit is None:
        raise ViwoError(
            "invalid_request",
            f"Keystone could not assemble {text!r}",
            hint=(result.stdout or result.stderr)[-200:],
        )
    return bytes.fromhex(hit.group(1))


def disassemble(data: bytes, code: bytes, offset: int, span: int = 0) -> list[str]:
    """`address: mnemonic operands` for every instruction of `code` (placed at `offset`) that
    starts inside the first `span` bytes; [] when capstone is not installed."""
    try:
        import capstone  # BSD; optional
    except ImportError:
        return []
    _, bits = arch(data)
    md = capstone.Cs(
        capstone.CS_ARCH_X86, capstone.CS_MODE_64 if bits == 64 else capstone.CS_MODE_32
    )
    start = address_of(data, offset)
    span = span or len(code)
    return [
        f"{i.address:x}: {i.mnemonic} {i.op_str}".strip()
        for i in md.disasm(code, start)
        if i.address < start + span
    ]


def around(data: bytes, offset: int, new: bytes) -> dict[str, list[str]]:
    """The instructions an edit touches, before and after it (the bytes that follow the edit
    are decoded too, so a cut instruction shows as what the CPU will now read)."""
    tail = data[offset + len(new) : offset + len(new) + 15]
    return {
        "old": disassemble(data, data[offset : offset + len(new) + 15], offset, len(new)),
        "new": disassemble(data, new + tail, offset, len(new)),
    }


def signature(data: bytes, offset: int, length: int = 8, limit: int = 64) -> tuple[str, int]:
    """(AOB pattern, at) unique in the file that locates `offset`: the bytes from the offset on,
    grown until they occur once; if 64 bytes never do, windows that start earlier are tried."""
    for back in (0, 8, 16, 32):
        start = max(0, offset - back)
        for size in range(length, limit + 1, 4):
            window = data[start : start + size]
            if len(window) == size and data.count(window) == 1:
                return " ".join(f"{b:02X}" for b in window), offset - start
    raise ViwoError("failed", f"no unique signature of up to {limit} bytes around {offset:#x}")
