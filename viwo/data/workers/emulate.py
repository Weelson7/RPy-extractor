"""ViWo worker for analysis.emulate (doc 6.2, rung A4): one routine of a PE or ELF binary (x86,
x64) run in Unicorn. ViWo runs it as its own process and never imports it (Unicorn: GPL-2.0):
    python -I emulate.py --lib <third_party/unicorn> <spec.json> <out folder>
The image is mapped at its preferred base, import slots point at stubs (a call into one stops
the run and names it), arguments follow the ABI (Win64, SysV, cdecl), buffers live in a heap
after the image. Writes <out>/result.json and one argN.bin per requested dump."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PAGE, HEAP_SIZE, STACK_SIZE, STUBS = 0x1000, 0x400000, 0x100000, 0x1000
REGS = {"win64": ("rcx", "rdx", "r8", "r9"), "sysv": ("rdi", "rsi", "rdx", "rcx", "r8", "r9")}


def align(value: int, to: int = PAGE) -> int:
    return (value + to - 1) // to * to


def load_pe(data: bytes) -> dict:
    import pefile

    pe = pefile.PE(data=data)
    bits = {0x8664: 64, 0x14C: 32}.get(pe.FILE_HEADER.Machine)
    if bits is None:
        raise ValueError(f"unsupported PE machine 0x{pe.FILE_HEADER.Machine:x} (x86/x64 only)")
    base, opt = pe.OPTIONAL_HEADER.ImageBase, pe.OPTIONAL_HEADER
    image = bytearray(align(opt.SizeOfImage))
    image[: opt.SizeOfHeaders] = data[: opt.SizeOfHeaders]
    for sec in pe.sections:
        raw = sec.get_data()[: max(sec.Misc_VirtualSize, sec.SizeOfRawData)]
        image[sec.VirtualAddress : sec.VirtualAddress + len(raw)] = raw
    table = getattr(pe, "DIRECTORY_ENTRY_EXPORT", None)
    exports = {
        s.name.decode(): base + s.address for s in (table.symbols if table else []) if s.name
    }
    imports = [
        (imp.address, f"{entry.dll.decode()}!{imp.name.decode() if imp.name else imp.ordinal}")
        for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])
        for imp in entry.imports
    ]
    abi = "win64" if bits == 64 else "cdecl"
    return {"bits": bits, "abi": abi, "base": base, "segments": [(base, bytes(image))],
            "exports": exports, "imports": imports}  # fmt: skip


def load_elf(path: Path) -> dict:
    from elftools.elf.elffile import ELFFile

    with open(path, "rb") as fh:
        elf = ELFFile(fh)
        bits = {"EM_X86_64": 64, "EM_386": 32}.get(elf["e_machine"])
        if bits is None:
            raise ValueError(f"unsupported ELF machine {elf['e_machine']} (x86/x64 only)")
        bias = 0x10000000 if elf["e_type"] == "ET_DYN" else 0  # a PIE gets a fixed load bias
        segments = [_segment(seg, bias) for seg in elf.iter_segments(type="PT_LOAD")]
        exports: dict[str, int] = {}
        for name in (".symtab", ".dynsym"):
            table = elf.get_section_by_name(name)
            for sym in table.iter_symbols() if table else ():
                if sym.name and sym["st_value"] and sym["st_info"]["type"] == "STT_FUNC":
                    exports.setdefault(sym.name, bias + sym["st_value"])
    abi = "sysv" if bits == 64 else "cdecl"
    base = min(start for start, _ in segments)
    return {"bits": bits, "abi": abi, "base": base, "segments": segments,
            "exports": exports, "imports": []}  # fmt: skip


def _segment(seg, bias: int) -> tuple[int, bytes]:
    start = (bias + seg["p_vaddr"]) // PAGE * PAGE
    body = b"\0" * (bias + seg["p_vaddr"] - start) + seg.data()
    body += b"\0" * (seg["p_memsz"] - seg["p_filesz"])
    return start, body + b"\0" * (align(len(body)) - len(body))


def load(path: Path) -> dict:
    data = path.read_bytes()
    if data[:2] == b"MZ":
        return load_pe(data)
    if data[:4] == b"\x7fELF":
        return load_elf(path)
    raise ValueError("not a PE or ELF binary")


def address(text: str, image: dict) -> int:
    kind, _, value = text.partition(":")
    if kind == "rva":
        return image["base"] + int(value, 0)
    if kind == "export":
        if value not in image["exports"]:
            known = ", ".join(sorted(image["exports"])[:8]) or "none"
            raise ValueError(f"no export {value!r} (known: {known})")
        return image["exports"][value]
    return int(text, 0)


def buffers(args: list[dict], heap: int) -> tuple[list[int], list[tuple[int, bytes]]]:
    """Argument values (a buffer passes its address) and the bytes to write into the heap."""
    values, writes, at = [], [], heap
    for arg in args:
        if "int" in arg:
            values.append(arg["int"])
            continue
        if "sym" in arg:
            raise ValueError("sym: arguments are for analysis.symbolic")
        if "hex" in arg:
            body = bytes.fromhex(arg["hex"])
        else:
            body = Path(arg["file"]).read_bytes() if "file" in arg else b"\0" * arg["zeros"]
        values.append(at)
        writes.append((at, body))
        at = align(at + len(body) + 1, 16)
    if at - heap > HEAP_SIZE:
        raise ValueError(f"buffers need {at - heap} bytes, the heap holds {HEAP_SIZE}")
    return values, writes


def frame(abi: str, values: list[int], stack_top: int, ret: int) -> tuple[dict, int, bytes]:
    """(register args, initial stack pointer, stack words) at the routine's first instruction:
    the return address on top, the Win64 shadow space, then the arguments past the registers."""
    names = REGS.get(abi, ())
    size = 4 if abi == "cdecl" else 8
    words = [ret] + ([0, 0, 0, 0] if abi == "win64" else []) + values[len(names) :]
    sp = (stack_top - 0x1000 - size * len(words)) // 16 * 16 - (8 if size == 8 else 0)
    return dict(zip(names, values)), sp, b"".join(w.to_bytes(size, "little") for w in words)


def run(spec: dict, out: Path) -> dict:
    import unicorn as uc
    from unicorn import x86_const as x86

    image = load(Path(spec["binary"]))
    bits = image["bits"]
    reg = lambda name: getattr(x86, f"UC_X86_REG_{name.upper()}")  # noqa: E731
    pc, sp_reg, ax = ("rip", "rsp", "rax") if bits == 64 else ("eip", "esp", "eax")
    emu = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_64 if bits == 64 else uc.UC_MODE_32)
    for start, body in image["segments"]:
        emu.mem_map(start, len(body))
        emu.mem_write(start, body)
    stubs = align(max(s + len(b) for s, b in image["segments"]) + PAGE)
    heap, stack_top = stubs + STUBS, stubs + STUBS + HEAP_SIZE + STACK_SIZE
    emu.mem_map(stubs, stack_top - stubs)
    emu.mem_write(stubs, b"\xc3" * STUBS)
    stopped: dict = {}
    _wire_imports(uc, emu, image, stubs, stopped)
    values, writes = buffers(spec["args"], heap)
    for at, body in writes:
        emu.mem_write(at, body)
    ret = stubs + STUBS - 1  # the sentinel: the routine returning lands here
    in_regs, sp, words = frame(image["abi"], values, stack_top, ret)
    emu.mem_write(sp, words)
    for name, value in {**in_regs, sp_reg: sp}.items():
        emu.reg_write(reg(name), value)
    start = address(spec["start"], image)
    report = _emulate(emu, uc, (start, ret, reg(pc)), spec["max_insns"], stopped)
    report.update(pc=hex(emu.reg_read(reg(pc))), files=_dumps(emu, spec["dump"], values, out))
    return {**report, "return": hex(emu.reg_read(reg(ax))), "start": hex(start), "bits": bits}


def _wire_imports(uc, emu, image: dict, stubs: int, stopped: dict) -> None:
    """Each import slot gets its own stub address: a call into one stops the run, named."""
    names = [name for _, name in image["imports"]]
    for i, (slot, _) in enumerate(image["imports"]):
        emu.mem_write(slot, (stubs + i).to_bytes(image["bits"] // 8, "little"))

    def hit(emu, addr, size, data) -> None:
        stopped["reason"] = f"the routine called the import {names[addr - stubs]}"
        emu.emu_stop()

    if names:  # an empty range would hook every instruction
        emu.hook_add(uc.UC_HOOK_CODE, hit, begin=stubs, end=stubs + len(names) - 1)


def _emulate(emu, uc, where: tuple[int, int, int], budget: int, stopped: dict) -> dict:
    start, ret, pc = where
    try:
        emu.emu_start(start, ret, count=budget)
    except uc.UcError as exc:
        return {"status": "fault", "reason": f"{exc} (an isolated routine: no OS, no imports)"}
    if stopped:
        return {"status": "import", **stopped}
    if emu.reg_read(pc) == ret:
        return {"status": "returned", "reason": "the routine returned"}
    return {"status": "limit", "reason": f"stopped after {budget} instructions"}


def _dumps(emu, dumps: list[dict], values: list[int], out: Path) -> list[str]:
    files = []
    for dump in dumps:
        index, size = dump["arg"], dump["size"]
        if index >= len(values):
            raise ValueError(f"dump arg{index}: the routine has {len(values)} argument(s)")
        (out / f"arg{index}.bin").write_bytes(bytes(emu.mem_read(values[index], size)))
        files.append(f"arg{index}.bin")
    return files


def main(argv: list[str]) -> int:
    lib, spec_file, out = argv[argv.index("--lib") + 1], argv[-2], Path(argv[-1])
    sys.path.insert(0, lib)
    out.mkdir(parents=True, exist_ok=True)
    try:
        report = run(json.loads(Path(spec_file).read_text(encoding="utf-8")), out)
    except Exception as exc:  # noqa: BLE001 (never silent: any failure is the report)
        report = {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}
    (out / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"emulate: {report['status']}: {report.get('reason', '')}")
    return 0 if report["status"] in ("returned", "limit") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
