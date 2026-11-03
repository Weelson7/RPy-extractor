"""Windows OS layer."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence

from viwo.contracts.os import OS, DesktopShell, FileSystemPolicy

from ._shared import Locator, SubprocessRunner, tk_pick_file, tk_pick_folder

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


class WindowsShell(DesktopShell):
    def open_folder(self, path: Path) -> tuple[bool, str]:
        if not path.is_dir():
            return False, f"Folder not found: {path}"
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True, ""
        except OSError as exc:
            return False, str(exc)

    def pick_folder(self, title: str, initial: Path | None = None) -> Path | None:
        return tk_pick_folder(title, initial)

    def pick_file(self, title: str, initial: Path | None = None, patterns=()) -> Path | None:
        return tk_pick_file(title, initial, patterns)


LONG_PATH_LIMIT = 248  # MAX_PATH minus room for a file name: beyond it, extended-length form


def _running_images(runner: SubprocessRunner) -> set[str]:
    """Image names from `tasklist` (CSV, no header), lowercased."""
    result = runner.run(["tasklist", "/FO", "CSV", "/NH"], timeout=10)
    rows = (line.split('","')[0].strip('"') for line in result.stdout.splitlines())
    return {name.lower() for name in rows if name}


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


class WindowsOS(OS):
    os_id = "windows"
    display_name = "Windows"

    def __init__(self, tool_overrides: Mapping[str, str | Sequence[str]] | None = None) -> None:
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self._process = SubprocessRunner(
            32767, {"creationflags": flags}, _kill_tree, _running_images
        )
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

    @property
    def process(self) -> SubprocessRunner:
        return self._process

    @property
    def tools(self) -> Locator:
        return self._tools

    @property
    def fs(self) -> WindowsFs:
        return self._fs

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

    def include_in_scan(self, paths) -> None:
        if paths:
            self._ps(f"Remove-MpPreference -ExclusionPath {_ps_list(paths)}")

    def _ps(self, command: str):
        argv = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
        return self._process.run(argv, timeout=60)

    def config_home(self) -> Path:
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")

    def data_home(self) -> Path:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")

    @property
    def shell(self) -> WindowsShell:
        return self._shell
