"""Windows: a ceiling on this process's own memory, through a job object. An allocation past it
fails inside the process (Python raises MemoryError) instead of taking the machine down. Child
processes are left out of the job (silent breakaway): a tool ViWo starts keeps its own needs."""

import ctypes
from ctypes import wintypes

PROCESS_MEMORY, SILENT_BREAKAWAY = 0x100, 0x1000  # JOB_OBJECT_LIMIT_*
EXTENDED = 9  # JobObjectExtendedLimitInformation
SUSPENDED = 0x4  # CREATE_SUSPENDED
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


def _kernel():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype = k.GetCurrentProcess.restype = wintypes.HANDLE
    k.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    return k


def _job(k, job, ceiling: int, flags: int, process) -> bool:
    info = _Extended()
    info.Basic.LimitFlags = flags
    info.ProcessMemoryLimit = ceiling
    held = job and k.SetInformationJobObject(job, EXTENDED, ctypes.byref(info), ctypes.sizeof(info))
    return bool(held and (process is None or k.AssignProcessToJobObject(job, process)))


def limit(ceiling: int) -> str:
    """Set this process's ceiling in bytes; "" when it holds, else why not. Set once per
    process: a second call changes the same job."""
    k = _kernel()
    job = _JOBS[0] if _JOBS else k.CreateJobObjectW(None, None)
    process = None if _JOBS else k.GetCurrentProcess()
    if not _job(k, job, ceiling, PROCESS_MEMORY | SILENT_BREAKAWAY, process):
        return f"Windows refused the job object (error {ctypes.get_last_error()})"
    _JOBS[:] = [job]
    return ""


def cap_child(proc, ceiling: int) -> str:
    """A child tool (and what it starts) held under `ceiling` bytes each: past it the tool
    fails by itself, the machine stays up. The tool was started suspended (SUSPENDED), so
    nothing it starts can slip out before the job holds; the job lives as long as they do."""
    k = _kernel()
    job = k.CreateJobObjectW(None, None)
    held = _job(k, job, ceiling, PROCESS_MEMORY, int(proc._handle))
    error = ctypes.get_last_error()
    if job:
        k.CloseHandle(job)
    ctypes.WinDLL("ntdll").NtResumeProcess(wintypes.HANDLE(int(proc._handle)))  # started suspended
    return "" if held else f"Windows refused the job object (error {error})"
