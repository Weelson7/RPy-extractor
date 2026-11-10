"""Linux OS layer."""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence

from viwo.contracts.os import FileSystemPolicy

from ._shared import HostOS, Locator, SubprocessRunner, TkShell, open_with

PROC = Path("/proc")  # the procfs root (tests point it at a fake tree)


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()


def _cap_child(proc, ceiling: int) -> str:
    """The child's data limit, set from outside right after it starts (prlimit)."""
    try:
        import resource

        resource.prlimit(proc.pid, resource.RLIMIT_DATA, (ceiling, ceiling))
    except (ImportError, AttributeError, ValueError, OSError) as exc:
        return f"the data limit could not be set ({exc})"
    return ""


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


class LinuxShell(TkShell):
    def open_folder(self, path: Path) -> tuple[bool, str]:
        if not path.is_dir():
            return False, f"Folder not found: {path}"
        return open_with(["xdg-open", str(path)])


def _processes() -> list[tuple[int, str]]:
    """(pid, lowercased command name) from /proc/<pid>/comm; a process that exits while the
    list is read is left out."""
    found = []
    for comm in PROC.glob("[0-9]*/comm"):
        try:
            name = comm.read_text(encoding="utf-8", errors="replace").strip().lower()
        except OSError:
            continue
        found.append((int(comm.parent.name), name))
    return found


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


def _proc_dump(pid: int, out: Path) -> Path:
    """Every readable mapping of /proc/<pid>/mem, back to back, with regions.json saying where
    each one starts in the dump (ptrace rules apply: same user, or a permissive ptrace_scope)."""
    regions, dump = [], out / f"{pid}.mem"
    with (
        open(PROC / str(pid) / "maps", encoding="utf-8") as maps,
        open(PROC / str(pid) / "mem", "rb") as mem,
        open(dump, "wb") as fh,
    ):
        for line in maps:
            parts = line.split()
            start, end = (int(x, 16) for x in parts[0].split("-"))
            if "r" not in parts[1]:
                continue
            try:
                mem.seek(start)
                data = mem.read(end - start)
            except OSError:
                continue
            regions.append(
                {
                    "start": hex(start),
                    "end": hex(end),
                    "perms": parts[1],
                    "path": parts[5] if len(parts) > 5 else "",
                    "at": fh.tell(),
                }
            )
            fh.write(data)
    (out / "regions.json").write_text(json.dumps(regions, indent=1), encoding="utf-8")
    return dump


def _sample(pid: int, seconds: float, cancel=None) -> tuple[list, list]:
    from ._linux_probe import sample_threads

    return sample_threads(pid, seconds, cancel)


class LinuxOS(HostOS):
    os_id = "linux"
    display_name = "Linux"
    name_limit = 15  # /proc/<pid>/comm keeps 15 characters
    _dump, _sample = staticmethod(_proc_dump), staticmethod(_sample)

    def __init__(self, tool_overrides: Mapping[str, str | Sequence[str]] | None = None) -> None:
        arg_max = os.sysconf("SC_ARG_MAX") if hasattr(os, "sysconf") else 131072
        self._process = SubprocessRunner(
            max(4096, arg_max // 2), {"start_new_session": True}, _kill_group, _processes
        )
        self._process.cap_child = _cap_child
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

    def config_home(self) -> Path:
        return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")

    def data_home(self) -> Path:
        return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")

    def limit_memory(self, ceiling: int) -> str:
        """The soft data limit (heap and private mappings, not mapped files); child tools
        inherit a soft limit and may raise it back to the hard one."""
        try:
            import resource

            hard = resource.getrlimit(resource.RLIMIT_DATA)[1]
            soft = ceiling if hard == resource.RLIM_INFINITY else min(ceiling, hard)
            resource.setrlimit(resource.RLIMIT_DATA, (soft, hard))
        except (ImportError, ValueError, OSError) as exc:
            return f"the data limit could not be set ({exc})"
        return ""

    def memory_room(self, extra: int | None) -> None:
        """The soft data limit at what the process holds plus `extra`; None: back to the hard
        one or the ceiling limit_memory set (kept in the soft limit's first value)."""
        try:
            import resource

            soft, hard = resource.getrlimit(resource.RLIMIT_DATA)
            self._base = getattr(self, "_base", soft)
            if extra is not None:
                with open("/proc/self/statm", encoding="ascii") as fh:
                    held = int(fh.read().split()[5]) * os.sysconf("SC_PAGE_SIZE")
                soft = (
                    held + extra
                    if self._base == resource.RLIM_INFINITY
                    else min(self._base, held + extra)
                )
            resource.setrlimit(resource.RLIMIT_DATA, (self._base if extra is None else soft, hard))
        except (ImportError, ValueError, OSError, IndexError):
            pass  # no tighter ceiling on this host: the process ceiling still holds

    def memory_bytes(self) -> int:
        try:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (ValueError, OSError, AttributeError):
            return 0
