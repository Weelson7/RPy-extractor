"""Shared OS-layer building blocks; subclasses only differ in OS-specific details."""

import atexit
import glob
import importlib.util
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Mapping, Sequence

from viwo.contracts.os import OS, Child, DesktopShell, FileSystemPolicy, ProcessRunner, ToolLocator
from viwo.contracts.types import DependencySpec, ProcessResult, ToolLocation

KillTree = Callable[[subprocess.Popen], None]
Lister = Callable[[], list[tuple[int, str]]]  # (pid, lowercased image name) per process


CHILDREN: list[Child] = []  # tracked GUI children (doc 8.3a), torn down at exit


def _reap_children() -> None:
    for child in CHILDREN:
        if child.alive():
            child.kill()


atexit.register(_reap_children)


class SubprocessRunner(ProcessRunner):
    def __init__(self, max_len: int, popen_kwargs: dict, kill_tree: KillTree, lister: Lister):
        self._max_len = max_len
        self._popen_kwargs = popen_kwargs
        self._kill_tree = kill_tree
        self.processes = lister  # the per-OS process listing (running_images, pids_of)

    def running_images(self) -> set[str]:
        try:
            return {name for _, name in self.processes()}
        except Exception:  # noqa: BLE001  (a process list is advice, never a blocker)
            return set()

    def launch(self, argv, cwd=None, env=None) -> Child:
        """A GUI tool as a tracked child (doc 8.3a): no pipes, same process group rules, killed
        with the tree on exit."""
        proc = subprocess.Popen(
            [str(a) for a in argv],
            cwd=str(cwd) if cwd else None,
            env={**os.environ, **env} if env else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **self._popen_kwargs,
        )
        child = Child(proc.pid, lambda: proc.poll() is None, lambda: self._kill_tree(proc))
        CHILDREN.append(child)
        return child

    @property
    def max_command_length(self) -> int:
        return self._max_len

    @property
    def python_executable(self) -> str:
        return sys.executable

    def _popen(self, argv, cwd, env) -> subprocess.Popen:
        return subprocess.Popen(
            [str(a) for a in argv],
            cwd=str(cwd) if cwd else None,
            env={**os.environ, **env} if env else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            **self._popen_kwargs,
        )

    def run(self, argv, cwd=None, timeout=None, cancel=None, env=None, on_line=None):
        """Output is read by pump threads and the call returns when the process exits: a
        grandchild that keeps the pipes open (the adb server qrenderdoc leaves behind) cannot
        hang it the way `communicate()` would."""
        proc = self._popen(argv, cwd, env)
        deadline = time.monotonic() + timeout if timeout else None
        return self._stream(proc, deadline, cancel, on_line or (lambda line: None))

    def _stream(self, proc, deadline, cancel, on_line) -> ProcessResult:
        """Capture stdout/stderr while handing every line to on_line as it arrives."""
        chunks: dict[str, list[str]] = {"out": [], "err": []}

        def pump(stream, key: str) -> None:
            for line in iter(stream.readline, ""):
                chunks[key].append(line)
                try:
                    on_line(line.rstrip("\r\n"))
                except Exception:  # noqa: BLE001  (a progress relay never kills the tool)
                    pass
            stream.close()

        threads = [
            threading.Thread(target=pump, args=(proc.stdout, "out"), daemon=True),
            threading.Thread(target=pump, args=(proc.stderr, "err"), daemon=True),
        ]
        for thread in threads:
            thread.start()
        timed_out = False
        while proc.poll() is None:
            expired = deadline is not None and time.monotonic() > deadline
            if expired or (cancel is not None and cancel.cancelled):
                self._kill_tree(proc)
                timed_out = True
                break
            time.sleep(0.1)
        proc.wait()
        for thread in threads:  # daemon pumps; a grandchild may still hold the pipes
            thread.join(timeout=1)
        out, err = "".join(chunks["out"]), "".join(chunks["err"])
        return ProcessResult(-9 if timed_out else proc.returncode, out, err, timed_out=timed_out)


class Locator(ToolLocator):
    """Search order: config override, env var, python module, PATH, known dirs."""

    def __init__(
        self,
        overrides: Mapping[str, str | Sequence[str]],
        roots: Sequence[Path],
        suffixes: Sequence[str],
        wrap: Callable[[Path], tuple[str, ...]],
        os_id: str = "",
    ) -> None:
        self._overrides = dict(overrides)
        self._roots = list(roots)  # a root may hold a glob ("scoop/apps/*/current", doc 1.2)
        self._suffixes = list(suffixes)
        self._wrap = wrap
        self._os_id = os_id

    def _expanded_roots(self) -> list[Path]:
        out: list[Path] = []
        for root in self._roots:
            text = str(root)
            if "*" in text:
                out += [Path(p) for p in sorted(glob.glob(text)) if os.path.isdir(p)]
            else:
                out.append(root)
        return out

    def known_install_dirs(self, spec: DependencySpec) -> Sequence[Path]:
        dirs: list[Path] = []
        for root in self._expanded_roots():
            dirs.append(root)
            for name in spec.install_dirs:
                dirs += [root / name, root / name / "bin"]
        return dirs

    def _found(self, spec: DependencySpec, path: Path, source: str) -> ToolLocation:
        return ToolLocation(spec.dep_id, self._wrap(path), str(path), source)

    def locate(self, spec: DependencySpec) -> ToolLocation | None:
        override = self._overrides.get(spec.dep_id, "")
        if isinstance(override, str):
            if override and Path(override).exists():
                return self._found(spec, Path(override), "config")
        elif override and Path(override[0]).exists():  # argv prefix, e.g. dotnet + dll
            path = next((a for a in reversed(override) if Path(a).exists()), override[0])
            return ToolLocation(spec.dep_id, tuple(override), str(path), "config")
        env_value = os.environ.get(spec.env_var, "") if spec.env_var else ""
        if env_value and Path(env_value).exists():
            return self._found(spec, Path(env_value), "env")
        if spec.kind == "python":
            name = spec.import_name or spec.dep_id
            found = _module_present(name)
            return (
                ToolLocation(spec.dep_id, (sys.executable, "-m", name), "", "python")
                if found
                else None
            )
        names = spec.executables_for(self._os_id)
        for name in names:
            hit = shutil.which(name)
            if hit:
                return self._found(spec, Path(hit), "path")
        for folder in self.known_install_dirs(spec):
            for name in names:
                for suffix in self._suffixes:
                    candidate = folder / f"{name}{suffix}"
                    if candidate.is_file():
                        return self._found(spec, candidate, "known_dir")
        return None


def _module_present(name: str) -> bool:
    if sys.modules.get(name) is not None:
        return True
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):  # e.g. a module blocked with sys.modules[name] = None
        return False


def open_with(command: Sequence[str]) -> tuple[bool, str]:
    try:
        subprocess.Popen([*command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, ""
    except OSError as exc:
        return False, str(exc)


def _tk_ask(kind: str, **options) -> Path | None:
    """A tkinter dialog (`askdirectory`, `askopenfilename`) on top; None when there is no
    display or the user cancelled."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = getattr(filedialog, kind)(**options)
        root.destroy()
        return Path(chosen) if chosen else None
    except Exception:
        return None


class TkShell(DesktopShell):
    """The folder and file pickers both OS layers use (tkinter); open_folder is per OS."""

    def pick_folder(self, title: str, initial: Path | None = None) -> Path | None:
        return _tk_ask("askdirectory", initialdir=str(initial or Path.home()), title=title)

    def pick_file(self, title: str, initial: Path | None = None, patterns=()) -> Path | None:
        start = initial.parent if initial and initial.is_file() else (initial or Path.home())
        types = [("Supported files", " ".join(patterns))] if patterns else []
        types.append(("All files", "*.*"))
        return _tk_ask("askopenfilename", initialdir=str(start), title=title, filetypes=types)


class HostOS(OS):
    """What both OS layers share: the services their __init__ sets up, pids_of over the
    per-OS process listing, and dump_process over the per-OS dumper."""

    _process: SubprocessRunner
    _tools: Locator
    name_limit = 0  # characters of a process name the OS keeps (Linux comm: 15)

    @property
    def process(self) -> SubprocessRunner:
        return self._process

    @property
    def tools(self) -> Locator:
        return self._tools

    @property
    def fs(self) -> FileSystemPolicy:
        return self._fs

    @property
    def shell(self) -> DesktopShell:
        return self._shell

    def pids_of(self, image: str) -> list[int]:
        key = image.lower()[: self.name_limit or None]
        return [pid for pid, name in self._process.processes() if name == key]

    def dump_process(self, pid: int, out: Path) -> Path:
        out.mkdir(parents=True, exist_ok=True)
        return self._dump(pid, out)  # each OS layer sets _dump (minidump, /proc mem)

    def sample_threads(self, pid: int, seconds: float, cancel=None) -> tuple[list, list]:
        return self._sample(pid, seconds, cancel)  # each OS layer sets _sample
