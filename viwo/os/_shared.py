"""Shared OS-layer building blocks; subclasses only differ in OS-specific details."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Mapping, Sequence

from viwo.contracts.os import ProcessRunner, ToolLocator
from viwo.contracts.types import DependencySpec, ProcessResult, ToolLocation

KillTree = Callable[[subprocess.Popen], None]


class SubprocessRunner(ProcessRunner):
    def __init__(self, max_len: int, popen_kwargs: dict, kill_tree: KillTree) -> None:
        self._max_len = max_len
        self._popen_kwargs = popen_kwargs
        self._kill_tree = kill_tree

    @property
    def max_command_length(self) -> int:
        return self._max_len

    @property
    def python_executable(self) -> str:
        return sys.executable

    def run(self, argv, cwd=None, timeout=None, cancel=None, env=None) -> ProcessResult:
        merged_env = {**os.environ, **env} if env else None
        proc = subprocess.Popen(
            [str(a) for a in argv],
            cwd=str(cwd) if cwd else None,
            env=merged_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            **self._popen_kwargs,
        )
        deadline = time.monotonic() + timeout if timeout else None
        while True:
            try:
                out, err = proc.communicate(timeout=0.2)
                return ProcessResult(proc.returncode, out or "", err or "")
            except subprocess.TimeoutExpired:
                expired = deadline is not None and time.monotonic() > deadline
                if expired or (cancel is not None and cancel.cancelled):
                    self._kill_tree(proc)
                    out, err = proc.communicate()
                    return ProcessResult(-9, out or "", err or "", timed_out=True)


class Locator(ToolLocator):
    """Search order: config override, env var, python module, PATH, known dirs."""

    def __init__(
        self,
        overrides: Mapping[str, str],
        roots: Sequence[Path],
        suffixes: Sequence[str],
        wrap: Callable[[Path], tuple[str, ...]],
    ) -> None:
        self._overrides = dict(overrides)
        self._roots = list(roots)
        self._suffixes = list(suffixes)
        self._wrap = wrap

    def known_install_dirs(self, spec: DependencySpec) -> Sequence[Path]:
        dirs: list[Path] = []
        for root in self._roots:
            dirs.append(root)
            for name in spec.install_dirs:
                dirs += [root / name, root / name / "bin"]
        return dirs

    def _found(self, spec: DependencySpec, path: Path, source: str) -> ToolLocation:
        return ToolLocation(spec.dep_id, self._wrap(path), str(path), source)

    def locate(self, spec: DependencySpec) -> ToolLocation | None:
        override = self._overrides.get(spec.dep_id, "")
        if override and Path(override).exists():
            return self._found(spec, Path(override), "config")
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
        for name in spec.executables:
            hit = shutil.which(name)
            if hit:
                return self._found(spec, Path(hit), "path")
        for folder in self.known_install_dirs(spec):
            for name in spec.executables:
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


def tk_pick_folder(title: str, initial: Path | None) -> Path | None:
    """v1 folder dialog (tkinter); None when no display or cancelled."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askdirectory(initialdir=str(initial or Path.home()), title=title)
        root.destroy()
        return Path(chosen) if chosen else None
    except Exception:
        return None


def tk_pick_file(title: str, initial: Path | None, patterns: Sequence[str]) -> Path | None:
    """v1 file dialog (tkinter); None when no display or cancelled."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        start = initial.parent if initial and initial.is_file() else (initial or Path.home())
        types = [("Supported files", " ".join(patterns))] if patterns else []
        chosen = filedialog.askopenfilename(
            initialdir=str(start), title=title, filetypes=types + [("All files", "*.*")]
        )
        root.destroy()
        return Path(chosen) if chosen else None
    except Exception:
        return None
