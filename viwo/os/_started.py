"""When a process started (doc 1, doc 4.3 lock): with its pid, it tells the process that wrote a
workspace lock from a later one that reuses the pid. A number of seconds, only compared with
another reading on the same host; None when the OS does not say."""

import os
import sys


def pid_started(pid: int) -> float | None:
    try:
        return _windows(pid) if sys.platform == "win32" else _linux(pid)
    except (OSError, ValueError, IndexError, AttributeError):
        return None


def _linux(pid: int) -> float | None:
    """Field 22 of /proc/<pid>/stat (clock ticks after boot); the name before it may hold
    spaces and parentheses, so the fields are counted from its last ")"."""
    with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as fh:
        fields = fh.read().rsplit(")", 1)[1].split()
    return int(fields[19]) / os.sysconf("SC_CLK_TCK")


def _windows(pid: int) -> float | None:
    """GetProcessTimes' creation time (100 ns steps); None once the process exited (its object
    can outlive it while a handle to it stays open)."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    times = [wintypes.FILETIME() for _ in range(4)]
    try:
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return None
    finally:
        kernel.CloseHandle(handle)
    created, ended = times[0], times[1]
    if ended.dwHighDateTime or ended.dwLowDateTime:
        return None
    return ((created.dwHighDateTime << 32) | created.dwLowDateTime) / 1e7
