"""Guest virtual -> guest physical addresses (doc 11.8): the x86 page walk, done live over a
tier's physical memory, so a guest process's address space is reached whichever process the
vCPU happens to run. The page-table root (the process's DTB / CR3) comes from the guest OS
(core.isolation.guest asks Volatility for it); this is architecture only, no OS knowledge. Three
paging modes: x64 (4 levels, 1 GB and 2 MB pages), PAE (3 levels, 2 MB pages) and legacy 32-bit
(2 levels, 4 MB pages), plus "phys" for a CPU with paging off (an address is physical). A page
that is not present (paged out, never touched) is NotResident."""

from viwo.contracts.patcher import MemoryFault

PRESENT, LARGE = 0x1, 0x80
WIDE = 0x000F_FFFF_FFFF_F000  # the frame bits of an 8-byte entry
NARROW = 0xFFFF_F000  # the frame bits of a 4-byte entry
# levels as (shift, index mask, may map a large page); mode: (entry size, root mask, levels)
X64 = ((39, 0x1FF, False), (30, 0x1FF, True), (21, 0x1FF, True), (12, 0x1FF, False))
PAE = ((30, 0x3, False), (21, 0x1FF, True), (12, 0x1FF, False))
X86 = ((22, 0x3FF, True), (12, 0x3FF, False))
MODES = {"x64": (8, WIDE, X64), "pae": (8, 0xFFFF_FFE0, PAE), "x86": (4, NARROW, X86)}


class NotResident(MemoryFault):
    """The page is not in guest RAM: paged out, never touched, or not mapped at all."""


def translate(read, dtb: int, va: int, mode: str = "x64") -> tuple[int, int]:
    """(the physical address of `va`, how many bytes are left in its page) in the address space
    rooted at `dtb`. `read(pa, n)` reads guest physical memory."""
    if mode == "phys":
        return va, 0x1000 - (va & 0xFFF)
    size, root, levels = MODES[mode]
    frame = WIDE if size == 8 else NARROW
    table = dtb & root
    for shift, index, large in levels:
        entry = int.from_bytes(read(table + ((va >> shift) & index) * size, size), "little")
        if not entry & PRESENT:
            raise NotResident(f"{va:#x} is not resident (level {shift} entry not present)")
        if shift == 12 or (large and entry & LARGE):
            span = 1 << shift
            offset = va & (span - 1)
            return (entry & frame & ~(span - 1)) + offset, span - offset
        table = entry & frame
    raise NotResident(f"{va:#x}: no page")  # unreachable: the last level always returns


def mode_of(cr0: int, cr4: int, efer: int) -> str:
    """The paging mode a vCPU's control registers select."""
    if not cr0 & 0x8000_0000:
        return "phys"
    if efer & 0x400:  # EFER.LMA: long mode
        return "x64"
    return "pae" if cr4 & 0x20 else "x86"


def spans(read, dtb: int, va: int, size: int, mode: str = "x64") -> list[tuple[int, int]]:
    """[(physical address, length)] covering `size` bytes from `va`, split at page edges. Every
    page is translated before any byte is touched, so a write is all or nothing."""
    out = []
    while size > 0:
        pa, left = translate(read, dtb, va, mode)
        n = min(left, size)
        out.append((pa, n))
        va, size = va + n, size - n
    return out
