"""Windows OS layer."""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence

from viwo.contracts.os import FileSystemPolicy

from ._shared import HostOS, Locator, SubprocessRunner, TkShell

_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RESERVED = {"con", "prn", "aux", "nul"} | {f"{p}{i}" for p in ("com", "lpt") for i in range(1, 10)}


def _kill_tree(proc: subprocess.Popen) -> None:
    subprocess.run(
        ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    proc.kill()


def _wrap(path: Path) -> tuple[str, ...]:
    """Batch files run through cmd; `call` keeps a quoted path with spaces intact (cmd /c
    strips the outer quotes of a command line that starts with one)."""
    if path.suffix.lower() in {".bat", ".cmd"}:
        return ("cmd", "/c", "call", str(path))
    return (str(path),)


def _cap_child(proc, ceiling: int) -> str:
    from ._win_memory import cap_child

    return cap_child(proc, ceiling)


class WindowsFs(FileSystemPolicy):
    @property
    def case_sensitive(self) -> bool:
        return False

    def path_key(self, path: Path) -> str:
        return path.as_posix().casefold()

    def sanitize_filename(self, raw: str, fallback: str) -> str:
        name = _FORBIDDEN.sub("_", raw).strip(" .")[:255].rstrip(" .")
        if name and name.split(".")[0].lower() in _RESERVED:
            name = f"_{name}"
        return name if self.is_valid_filename(name) else fallback

    def is_valid_filename(self, name: str) -> bool:
        if not name or len(name) > 255 or _FORBIDDEN.search(name) or name.endswith((" ", ".")):
            return False
        return name.split(".")[0].lower() not in _RESERVED

    def long_path(self, path: Path) -> Path:
        text = str(path)
        if len(text) < LONG_PATH_LIMIT or text.startswith(("\\\\?\\", "\\\\.\\")):
            return path
        absolute = os.path.abspath(text)
        if absolute.startswith("\\\\"):  # UNC share
            return Path("\\\\?\\UNC\\" + absolute.lstrip("\\"))
        return Path("\\\\?\\" + absolute)


class WindowsShell(TkShell):
    def open_folder(self, path: Path) -> tuple[bool, str]:
        if not path.is_dir():
            return False, f"Folder not found: {path}"
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True, ""
        except OSError as exc:
            return False, str(exc)


LONG_PATH_LIMIT = 248  # MAX_PATH minus room for a file name: beyond it, extended-length form


def _processes() -> list[tuple[int, str]]:
    """(pid, lowercased image name) of every process from a Toolhelp snapshot: the names come
    as UTF-16, so non-ASCII names match (tasklist prints them in the OEM code page)."""
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):  # PROCESSENTRY32W
        _fields_ = [
            ("size", wintypes.DWORD),
            ("usage", wintypes.DWORD),
            ("pid", wintypes.DWORD),
            ("heap", ctypes.c_size_t),
            ("module", wintypes.DWORD),
            ("threads", wintypes.DWORD),
            ("parent", wintypes.DWORD),
            ("priority", wintypes.LONG),
            ("flags", wintypes.DWORD),
            ("exe", wintypes.WCHAR * 260),
        ]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.c_void_p)
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snap in (None, wintypes.HANDLE(-1).value):
        raise OSError(ctypes.get_last_error(), "cannot list the running processes")
    entry, found = Entry(), []
    entry.size = ctypes.sizeof(Entry)
    try:
        more = k32.Process32FirstW(snap, ctypes.byref(entry))
        while more:
            found.append((int(entry.pid), entry.exe.lower()))
            more = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return found


def _install_roots() -> list[Path]:
    """Doc 1.2: Program Files (both), LOCALAPPDATA\\Programs, scoop apps, chocolatey tools."""
    env = os.environ
    roots = [Path(env[n]) for n in ("ProgramFiles", "ProgramFiles(x86)") if env.get(n)]
    if env.get("LOCALAPPDATA"):
        roots += [Path(env["LOCALAPPDATA"]) / "Programs", Path(env["LOCALAPPDATA"])]
    if env.get("ProgramData"):
        roots.append(Path(env["ProgramData"]))
    home = Path.home()
    scoop = Path(env.get("SCOOP", home / "scoop"))
    choco = Path(env.get("ChocolateyInstall", "C:/ProgramData/chocolatey"))
    return roots + [
        scoop / "apps" / "*" / "current",
        scoop / "shims",
        choco / "lib" / "*" / "tools",
        choco / "bin",
    ]


def _is_admin() -> bool:
    import ctypes

    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def _ps_list(paths) -> str:
    return ",".join("'" + str(p).replace("'", "''") + "'" for p in paths)


def _minidump(pid: int, out: Path) -> Path:
    """out/<pid>.dmp: MiniDumpWithFullMemory through dbghelp (part of Windows)."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    dbghelp = ctypes.WinDLL("dbghelp", use_last_error=True)  # its own error code, not kernel32's
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    write = dbghelp.MiniDumpWriteDump
    write.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.HANDLE, wintypes.DWORD) + (
        ctypes.c_void_p,
    ) * 3
    handle = k32.OpenProcess(0x0410, False, pid)  # QUERY_INFORMATION | VM_READ
    if not handle:
        raise OSError(ctypes.get_last_error(), f"cannot open process {pid}")
    path = out / f"{pid}.dmp"
    try:
        with open(path, "wb") as fh:
            if not write(handle, pid, msvcrt.get_osfhandle(fh.fileno()), 0x2, None, None, None):
                raise OSError(ctypes.get_last_error(), f"MiniDumpWriteDump failed for {pid}")
    except OSError:
        path.unlink(missing_ok=True)  # never leave a partial dump that looks complete
        raise
    finally:
        k32.CloseHandle(handle)
    return path


def _sample(pid: int, seconds: float, cancel=None) -> tuple[list, list]:
    from ._win_probe import sample_threads

    return sample_threads(pid, seconds, cancel)


def _load_native(path: Path):
    import ctypes

    return ctypes.CDLL(str(path))


class WindowsOS(HostOS):
    os_id = "windows"
    display_name = "Windows"
    _dump, _sample = staticmethod(_minidump), staticmethod(_sample)
    load_native = staticmethod(_load_native)

    def __init__(self, tool_overrides: Mapping[str, str | Sequence[str]] | None = None) -> None:
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self._process = SubprocessRunner(32767, {"creationflags": flags}, _kill_tree, _processes)
        self._process.cap_child = _cap_child
        self._process.capped_kwargs = {"creationflags": flags | 0x4}  # CREATE_SUSPENDED
        suffixes = [".exe", ".bat", ".cmd", ""]
        self._tools = Locator(tool_overrides or {}, _install_roots(), suffixes, _wrap, "windows")
        self._fs = WindowsFs()
        self._shell = WindowsShell()

    def is_supported_host(self) -> bool:
        return sys.platform == "win32"

    @staticmethod
    def pid_alive(pid: int) -> bool:
        import ctypes  # os.kill(pid, 0) would TERMINATE the process on Windows

        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        alive = kernel.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == 259
        kernel.CloseHandle(handle)
        return bool(alive)

    def exclude_from_scan(self, paths) -> tuple[list[Path], str]:
        """Windows Defender: only an elevated process may read or change its exclusions, so a
        normal ViWo says so once and scanning stays on. Folders already excluded by the user
        are left out (and so are never removed afterwards)."""
        if not _is_admin():
            return (
                [],
                "antivirus exclusions skipped: Defender takes them from an elevated ViWo only",
            )
        listed = self._ps("(Get-MpPreference).ExclusionPath")
        known = {line.strip().lower() for line in listed.stdout.splitlines()}
        new = [Path(p) for p in paths if str(p).lower() not in known]
        if new and not self._ps(f"Add-MpPreference -ExclusionPath {_ps_list(new)}").ok:
            return [], "antivirus exclusions skipped: Add-MpPreference was refused"
        return new, ""

    def include_in_scan(self, paths) -> bool:
        return not paths or self._ps(f"Remove-MpPreference -ExclusionPath {_ps_list(paths)}").ok

    def _ps(self, command: str):
        argv = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
        return self._process.run(argv, timeout=60)

    def config_home(self) -> Path:
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")

    def data_home(self) -> Path:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")

    def limit_memory(self, ceiling: int) -> str:
        from ._win_memory import limit

        return limit(ceiling)

    def memory_bytes(self) -> int:
        import ctypes

        class Status(ctypes.Structure):  # MEMORYSTATUSEX
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong)
                for name in ("total", "free", "pagefile", "freepage", "virtual", "freevirt", "ext")
            ]

        status = Status()
        status.length = ctypes.sizeof(Status)
        ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return int(status.total) if ok else 0
