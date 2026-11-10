"""Windows: a ceiling on this process's own memory, through a job object. An allocation past it
fails inside the process (Python raises MemoryError) instead of taking the machine down. Child
processes are left out of the job (silent breakaway): a tool ViWo starts keeps its own needs."""

import ctypes
from ctypes import wintypes

PROCESS_MEMORY, SILENT_BREAKAWAY = 0x100, 0x1000  # JOB_OBJECT_LIMIT_*
EXTENDED = 9  # JobObjectExtendedLimitInformation
_JOBS: list = []  # the job's handle, kept for the life of the process


class _Basic(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _Extended(ctypes.Structure):
    _fields_ = [
        ("Basic", _Basic),
        ("Io", ctypes.c_uint64 * 6),  # IO_COUNTERS
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def limit(ceiling: int) -> str:
    """Set the ceiling in bytes; "" when it holds, else why not. Set once per process: a second
    call changes the same job."""
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype = k.GetCurrentProcess.restype = wintypes.HANDLE
    k.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    info = _Extended()
    info.Basic.LimitFlags = PROCESS_MEMORY | SILENT_BREAKAWAY
    info.ProcessMemoryLimit = ceiling
    job = _JOBS[0] if _JOBS else k.CreateJobObjectW(None, None)
    ok = job and k.SetInformationJobObject(job, EXTENDED, ctypes.byref(info), ctypes.sizeof(info))
    if ok and not _JOBS:
        ok = k.AssignProcessToJobObject(job, k.GetCurrentProcess())
    if not ok:
        return f"Windows refused the job object (error {ctypes.get_last_error()})"
    _JOBS[:] = [job]
    return ""
