"""Linux OS layer."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence

from viwo.contracts.os import OS, DesktopShell, FileSystemPolicy

from ._shared import Locator, SubprocessRunner, open_with, tk_pick_file, tk_pick_folder


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()


class PosixFs(FileSystemPolicy):
    @property
    def case_sensitive(self) -> bool:
        return True

    def path_key(self, path: Path) -> str:
        return path.as_posix()

    def sanitize_filename(self, raw: str, fallback: str) -> str:
        name = raw.replace("/", "_").replace("\x00", "").strip()[:255]
        return name if self.is_valid_filename(name) else fallback

    def is_valid_filename(self, name: str) -> bool:
        bad = name in {"", ".", ".."} or "/" in name or "\x00" in name
        return not bad and len(name.encode("utf-8")) <= 255


class LinuxShell(DesktopShell):
    def open_folder(self, path: Path) -> tuple[bool, str]:
        if not path.is_dir():
            return False, f"Folder not found: {path}"
        return open_with(["xdg-open", str(path)])

    def pick_folder(self, title: str, initial: Path | None = None) -> Path | None:
        return tk_pick_folder(title, initial)

    def pick_file(self, title: str, initial: Path | None = None, patterns=()) -> Path | None:
        return tk_pick_file(title, initial, patterns)


def _running_images(_runner: SubprocessRunner) -> set[str]:
    """Command names from /proc/<pid>/comm, lowercased."""
    names = set()
    for comm in Path("/proc").glob("[0-9]*/comm"):
        names.add(comm.read_text(encoding="utf-8", errors="replace").strip().lower())
    return names


def _install_roots() -> list[Path]:
    """Doc 1.2: /usr/bin, /usr/local/bin, /opt/*, ~/.local/bin, flatpak exports."""
    home = Path.home()
    return [
        Path("/usr/local/bin"),
        Path("/usr/bin"),
        home / ".local/bin",
        Path("/opt/*"),
        Path("/opt"),
        Path("/var/lib/flatpak/exports/bin"),
        home / ".local/share/flatpak/exports/bin",
    ]


class LinuxOS(OS):
    os_id = "linux"
    display_name = "Linux"

    def __init__(self, tool_overrides: Mapping[str, str | Sequence[str]] | None = None) -> None:
        arg_max = os.sysconf("SC_ARG_MAX") if hasattr(os, "sysconf") else 131072
        self._process = SubprocessRunner(
            max(4096, arg_max // 2), {"start_new_session": True}, _kill_group, _running_images
        )
        self._tools = Locator(
            tool_overrides or {}, _install_roots(), [""], lambda p: (str(p),), "linux"
        )
        self._fs = PosixFs()
        self._shell = LinuxShell()

    def is_supported_host(self) -> bool:
        return sys.platform.startswith("linux")

    @staticmethod
    def pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @property
    def process(self) -> SubprocessRunner:
        return self._process

    @property
    def tools(self) -> Locator:
        return self._tools

    @property
    def fs(self) -> PosixFs:
        return self._fs

    def config_home(self) -> Path:
        return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")

    def data_home(self) -> Path:
        return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")

    @property
    def shell(self) -> LinuxShell:
        return self._shell
