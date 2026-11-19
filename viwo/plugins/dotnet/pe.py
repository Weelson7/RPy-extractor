"""The PE scaffolding a .NET assembly needs: the section table (RVA to file offset), the CLI
header (ECMA-335 II.25.3.3: it names the metadata root and the managed-resources blob) and the
metadata root with its streams (II.24.2.1-2). No table parsing here (that is meta.py); this finds
where things are."""

import struct

CLI_DIR = 14  # the COM descriptor data directory holds the CLI header RVA
BSJB = 0x424A5342  # "BSJB", the metadata root signature


def sections(raw: bytes) -> tuple[list[tuple[int, int, int, int]], int]:
    """([(virtual addr, virtual size, raw offset, raw size)], CLI header RVA)."""
    pe = struct.unpack_from("<I", raw, 0x3C)[0]
    if raw[pe : pe + 4] != b"PE\x00\x00":
        raise ValueError("not a PE file")
    nsec = struct.unpack_from("<H", raw, pe + 6)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", raw, opt)[0]
    rva_count_at = opt + (92 if magic == 0x10B else 108)
    nrva = struct.unpack_from("<I", raw, rva_count_at)[0]
    dirs = rva_count_at + 4
    (cli_rva,) = struct.unpack_from("<I", raw, dirs + CLI_DIR * 8)
    sec_at = dirs + nrva * 8
    secs = []
    for i in range(nsec):
        vsize, vaddr, rsize, roff = struct.unpack_from("<IIII", raw, sec_at + i * 40 + 8)
        secs.append((vaddr, vsize, roff, rsize))
    return secs, cli_rva


def has_cli(head: bytes) -> bool:
    """Whether a PE's head declares a CLI header (a managed assembly); tolerant of a short read."""
    try:
        pe = struct.unpack_from("<I", head, 0x3C)[0]
        if head[pe : pe + 4] != b"PE\x00\x00":
            return False
        opt = pe + 24
        magic = struct.unpack_from("<H", head, opt)[0]
        dirs = opt + (92 if magic == 0x10B else 108) + 4
        return struct.unpack_from("<I", head, dirs + CLI_DIR * 8)[0] != 0
    except (struct.error, IndexError):
        return False


def to_offset(secs, rva: int) -> int:
    for vaddr, vsize, roff, rsize in secs:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return roff + (rva - vaddr)
    raise ValueError(f"RVA {rva:#x} is in no section")


def cli_header(raw: bytes):
    """(metadata offset, metadata size, resources offset, resources size, sections)."""
    secs, cli_rva = sections(raw)
    if cli_rva == 0:
        raise ValueError("no CLI header (not a managed assembly)")
    cli = to_offset(secs, cli_rva)
    meta_rva, meta_size = struct.unpack_from("<II", raw, cli + 8)
    res_rva, res_size = struct.unpack_from("<II", raw, cli + 24)
    res_off = to_offset(secs, res_rva) if res_size else 0
    return to_offset(secs, meta_rva), meta_size, res_off, res_size, secs


def streams(raw: bytes, meta_off: int) -> dict[str, tuple[int, int]]:
    """{stream name: (absolute offset, size)} from the metadata root (II.24.2.1)."""
    if struct.unpack_from("<I", raw, meta_off)[0] != BSJB:
        raise ValueError("no BSJB metadata signature")
    (ver_len,) = struct.unpack_from("<I", raw, meta_off + 12)
    pos = meta_off + 16 + ver_len + 4  # skip version string (4-aligned) and flags
    (count,) = struct.unpack_from("<H", raw, pos - 2)
    out = {}
    for _ in range(count):
        offset, size = struct.unpack_from("<II", raw, pos)
        end = raw.index(b"\x00", pos + 8)
        name = raw[pos + 8 : end].decode("ascii")
        out[name] = (meta_off + offset, size)
        pos = end + 1 + (-(end + 1 - (pos + 8)) % 4)  # name padded to a 4-byte boundary
    return out
