"""ViWo worker for the isolation arm's T3 (doc 11.8): guest physical memory of a KVM/Xen domain
through the host's own LibVMI (libvmi.so, LGPL; loaded with ctypes in this separate process,
never in ViWo's). ViWo runs it for the length of one memory access batch:
    python -I libvmi_io.py <domain> [<KVMi socket>]
(a KVM domain is reached over its KVMi socket; Xen needs none) and speaks JSON lines on
stdin/stdout: {"op": "read", "pa": N, "n": N} -> {"ok": true, "hex": "..."}; {"op": "write",
"pa": N, "hex": "..."} -> {"ok": true}; a failure is {"ok": false, "error": "..."}. The first
line it prints says whether LibVMI opened the domain. Only LibVMI's stable physical-memory
calls are used (vmi_get_access_mode, vmi_init, vmi_read_pa, vmi_write_pa, vmi_destroy), so no
OS profile is needed: the page walk is ViWo's own."""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import sys

SUCCESS, INIT_DOMAINNAME = 0, 1  # VMI_SUCCESS, VMI_INIT_DOMAINNAME
KVMI_SOCKET = 2  # vmi_init_data_type_t: XEN_EVTCHN, MEMMAP, KVMI_SOCKET


class Entry(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint64), ("data", ctypes.c_void_p)]


class InitData(ctypes.Structure):  # vmi_init_data_t with one entry
    _fields_ = [("count", ctypes.c_uint64), ("entry", Entry * 1)]


def _init_data(socket: str):
    if not socket:
        return None, None
    path = ctypes.create_string_buffer(socket.encode())
    data = InitData(1, (Entry * 1)(Entry(KVMI_SOCKET, ctypes.cast(path, ctypes.c_void_p))))
    return ctypes.byref(data), (data, path)  # the second keeps both alive


def _say(**reply) -> None:
    sys.stdout.write(json.dumps(reply) + "\n")
    sys.stdout.flush()


def _open(domain: bytes, socket: str = ""):
    name = ctypes.util.find_library("vmi") or "libvmi.so"
    lib = ctypes.CDLL(name)
    mode, err = ctypes.c_int(0), ctypes.c_int(0)
    init, _keep = _init_data(socket)
    found = lib.vmi_get_access_mode(None, domain, INIT_DOMAINNAME, init, ctypes.byref(mode))
    if found != SUCCESS:
        raise OSError(f"LibVMI found no domain {domain.decode()!r} (KVMi or Xen)")
    vmi = ctypes.c_void_p()
    if lib.vmi_init(ctypes.byref(vmi), mode, domain, INIT_DOMAINNAME, init, ctypes.byref(err)):
        raise OSError(f"LibVMI could not open {domain.decode()!r} (error {err.value})")
    for fn in (lib.vmi_read_pa, lib.vmi_write_pa):
        fn.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_size_t, ctypes.c_void_p,
                       ctypes.POINTER(ctypes.c_size_t)]  # fmt: skip
    return lib, vmi, ("xen", "kvm", "file", "bareflank")[mode.value] if mode.value < 4 else "?"


def _serve(lib, vmi, request: dict) -> dict:
    done = ctypes.c_size_t(0)
    if request.get("op") == "read":
        n = int(request["n"])
        buf = ctypes.create_string_buffer(n)
        status = lib.vmi_read_pa(vmi, int(request["pa"]), n, buf, ctypes.byref(done))
        if status != SUCCESS or done.value != n:
            return {"ok": False, "error": f"read {n} bytes at {int(request['pa']):#x} failed"}
        return {"ok": True, "hex": buf.raw[:n].hex()}
    if request.get("op") == "write":
        data = bytes.fromhex(request["hex"])
        buf = ctypes.create_string_buffer(data, len(data))
        status = lib.vmi_write_pa(vmi, int(request["pa"]), len(data), buf, ctypes.byref(done))
        if status != SUCCESS or done.value != len(data):
            return {"ok": False, "error": f"write at {int(request['pa']):#x} failed"}
        return {"ok": True}
    if request.get("op") == "dump":
        return _dump(lib, vmi, request["path"])
    return {"ok": False, "error": f"unknown op {request.get('op')!r}"}


def _dump(lib, vmi, path: str) -> dict:
    """Guest physical memory up to LibVMI's highest address, as a raw image; a chunk LibVMI
    cannot read (a hole, MMIO) is zeros, and how many there were is said."""
    lib.vmi_get_max_physical_address.restype = ctypes.c_uint64
    top, chunk, holes = int(lib.vmi_get_max_physical_address(vmi)), 1 << 20, 0
    buf, done = ctypes.create_string_buffer(chunk), ctypes.c_size_t(0)
    with open(path, "wb") as out:
        for pa in range(0, top, chunk):
            n = min(chunk, top - pa)
            if lib.vmi_read_pa(vmi, pa, n, buf, ctypes.byref(done)) != SUCCESS or done.value != n:
                holes += 1
                out.write(bytes(n))
            else:
                out.write(buf.raw[:n])
    return {"ok": True, "bytes": top, "holes": holes}


def main(argv: list[str]) -> int:
    if len(argv) not in (1, 2):
        print("usage: libvmi_io.py <domain> [<KVMi socket>]", file=sys.stderr)
        return 2
    try:
        lib, vmi, mode = _open(argv[0].encode(), argv[1] if len(argv) == 2 else "")
    except OSError as exc:
        _say(ok=False, error=str(exc))
        return 1
    _say(ok=True, mode=mode)
    try:
        for line in sys.stdin:
            if line.strip():
                _say(**_serve(lib, vmi, json.loads(line)))
    finally:
        lib.vmi_destroy(vmi)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
