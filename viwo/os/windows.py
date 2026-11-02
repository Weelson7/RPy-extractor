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
    if path.suffix.lower() in {".bat", ".cmd"}:
        return ("cmd", "/c", str(path))
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


def _install_roots() -> list[Path]:
    names = ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "ProgramData")
    roots = [Path(os.environ[n]) for n in names if os.environ.get(n)]
    home = Path.home()
    return roots + [home / "scoop" / "shims", Path("C:/ProgramData/chocolatey/bin")]


class WindowsOS(OS):
    os_id = "windows"

    def __init__(self, tool_overrides: Mapping[str, str | Sequence[str]] | None = None) -> None:
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self._process = SubprocessRunner(32767, {"creationflags": flags}, _kill_tree)
        suffixes = [".exe", ".bat", ".cmd", ""]
        self._tools = Locator(tool_overrides or {}, _install_roots(), suffixes, _wrap)
        self._fs = WindowsFs()
        self._shell = WindowsShell()

    def is_supported_host(self) -> bool:
        return sys.platform == "win32"

    @property
    def process(self) -> SubprocessRunner:
        return self._process

    @property
    def tools(self) -> Locator:
        return self._tools

    @property
    def fs(self) -> WindowsFs:
        return self._fs

    @property
    def shell(self) -> WindowsShell:
        return self._shell
