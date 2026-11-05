"""Windows thread sampling for profile.sample: every thread's instruction pointer, read while
the thread is held for an instant (SuspendThread + GetThreadContext, no administrator rights),
and the modules the process has loaded (EnumProcessModulesEx)."""

import ctypes
import time
from ctypes import wintypes as wt

TH32CS_SNAPTHREAD, THREAD_ACCESS = 0x4, 0x2 | 0x8 | 0x40  # suspend/resume, get context, query
PROCESS_ACCESS = 0x400 | 0x10  # query information, read memory
CONTEXT_CONTROL, WOW64_CONTEXT_CONTROL = 0x00100001, 0x00010001
CONTEXT_SIZE, RIP_AT, FLAGS_AT = 1232, 0xF8, 0x30  # x64 CONTEXT
WOW64_SIZE, EIP_AT = 716, 0xB8  # WOW64_CONTEXT (a 32-bit game)


class THREADENTRY32(ctypes.Structure):
    _fields_ = [(n, wt.DWORD) for n in ("dwSize", "cntUsage", "th32ThreadID", "th32OwnerProcessID")]
    _fields_ += [("tpBasePri", wt.LONG), ("tpDeltaPri", wt.LONG), ("dwFlags", wt.DWORD)]


class MODULEINFO(ctypes.Structure):
    _fields_ = [("base", ctypes.c_void_p), ("size", wt.DWORD), ("entry", ctypes.c_void_p)]


def _k32():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenThread.restype = k32.OpenProcess.restype = wt.HANDLE
    k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    return k32


def _open(k32, pid: int):
    process = k32.OpenProcess(PROCESS_ACCESS, False, pid)
    if not process:
        raise OSError(ctypes.get_last_error(), f"cannot open process {pid}")
    return process


def threads_of(pid: int) -> list[int]:
    k32 = _k32()
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    entry, out = THREADENTRY32(), []
    entry.dwSize = ctypes.sizeof(THREADENTRY32)
    try:
        more = k32.Thread32First(snap, ctypes.byref(entry))
        while more:
            if entry.th32OwnerProcessID == pid:
                out.append(entry.th32ThreadID)
            more = k32.Thread32Next(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return out


def _pc(k32, handle, wow64: bool) -> int | None:
    """One thread's instruction pointer; the thread is held for the read only."""
    raw = ctypes.create_string_buffer((WOW64_SIZE if wow64 else CONTEXT_SIZE) + 16)
    at = (ctypes.addressof(raw) + 15) & ~15  # a CONTEXT must be 16-byte aligned
    flags_at, pc_at = (0, EIP_AT) if wow64 else (FLAGS_AT, RIP_AT)
    flags = WOW64_CONTEXT_CONTROL if wow64 else CONTEXT_CONTROL
    ctypes.c_uint32.from_address(at + flags_at).value = flags
    if k32.SuspendThread(handle) == 0xFFFFFFFF:
        return None
    try:
        get = k32.Wow64GetThreadContext if wow64 else k32.GetThreadContext
        if not get(handle, ctypes.c_void_p(at)):
            return None
    finally:
        k32.ResumeThread(handle)
    return (ctypes.c_uint32 if wow64 else ctypes.c_uint64).from_address(at + pc_at).value


def _rounds(k32, pid: int, wow64: bool, until: float, cancel) -> list[tuple[int, int]]:
    samples, handles = [], {}
    try:
        while time.monotonic() < until and not (cancel and cancel.cancelled):
            for tid in threads_of(pid):
                if tid not in handles:  # opened once per thread, closed at the end
                    handles[tid] = k32.OpenThread(THREAD_ACCESS, False, tid)
                pc = _pc(k32, handles[tid], wow64) if handles[tid] else None
                if pc:
                    samples.append((tid, pc))
            time.sleep(0.001)
    finally:
        for handle in handles.values():
            if handle:
                k32.CloseHandle(handle)
    return samples


def sample_threads(pid: int, seconds: float, cancel=None) -> tuple[list, list]:
    """((thread id, pc) about every millisecond for `seconds`, (base, size, path) modules)."""
    k32, winmm = _k32(), ctypes.WinDLL("winmm")
    process, wow64 = _open(k32, pid), wt.BOOL()
    try:
        k32.IsWow64Process(process, ctypes.byref(wow64))
        modules = modules_of(pid)
    finally:
        k32.CloseHandle(process)
    winmm.timeBeginPeriod(1)  # 1 ms rounds (the default sleep granularity is about 15 ms)
    try:
        return _rounds(k32, pid, bool(wow64.value), time.monotonic() + seconds, cancel), modules
    finally:
        winmm.timeEndPeriod(1)


def modules_of(pid: int) -> list[tuple[int, int, str]]:
    k32, psapi = _k32(), ctypes.WinDLL("psapi", use_last_error=True)
    process = _open(k32, pid)
    try:
        handles, needed = (ctypes.c_void_p * 4096)(), wt.DWORD()
        size = ctypes.sizeof(handles)
        psapi.EnumProcessModulesEx(process, handles, size, ctypes.byref(needed), 3)
        out = []
        for handle in handles[: needed.value // ctypes.sizeof(ctypes.c_void_p)]:
            info, name = MODULEINFO(), ctypes.create_unicode_buffer(1024)
            module = ctypes.c_void_p(handle)
            psapi.GetModuleInformation(process, module, ctypes.byref(info), ctypes.sizeof(info))
            psapi.GetModuleFileNameExW(process, module, name, 1024)
            out.append((info.base or 0, info.size, name.value))
        return out
    finally:
        k32.CloseHandle(process)
