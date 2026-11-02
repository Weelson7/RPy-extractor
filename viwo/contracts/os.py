"""OS layer contract (doc 1): the only place for OS-specific behavior.

Prototype A scope: process running, tool location, filesystem rules and the
minimal desktop shell. The package installer comes after Prototype A.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .types import CancelToken, DependencySpec, ProcessResult, ToolLocation


class ProcessRunner(ABC):
    @property
    @abstractmethod
    def max_command_length(self) -> int:
        """Longest safe command line (Windows: 32767; Linux: ARG_MAX-derived)."""

    @property
    @abstractmethod
    def python_executable(self) -> str: ...

    @abstractmethod
    def run(
        self,
        argv: Sequence[str],
        cwd: Path | None = None,
        timeout: float | None = None,
        cancel: CancelToken | None = None,
        env: Mapping[str, str] | None = None,
        on_line: Callable[[str], None] | None = None,
    ) -> ProcessResult:
        """Run to completion; never raises for non-zero exits. On timeout or cancel
        the whole process tree is killed and timed_out=True is returned. on_line, when
        given, receives every stdout/stderr line as it arrives (output is still captured)."""


class ToolLocator(ABC):
    @abstractmethod
    def locate(self, spec: DependencySpec) -> ToolLocation | None:
        """Side-effect free. Order: config override, env var, python module,
        PATH, known install dirs."""

    @abstractmethod
    def known_install_dirs(self, spec: DependencySpec) -> Sequence[Path]: ...


class FileSystemPolicy(ABC):
    @property
    @abstractmethod
    def case_sensitive(self) -> bool: ...

    @abstractmethod
    def path_key(self, path: Path) -> str:
        """Stable dedupe key (casefolded where the filesystem is case-insensitive)."""

    @abstractmethod
    def sanitize_filename(self, raw: str, fallback: str) -> str: ...

    @abstractmethod
    def is_valid_filename(self, name: str) -> bool: ...


class DesktopShell(ABC):
    """May return False/None on headless hosts; callers fall back to text input."""

    @abstractmethod
    def open_folder(self, path: Path) -> tuple[bool, str]: ...

    @abstractmethod
    def pick_folder(self, title: str, initial: Path | None = None) -> Path | None: ...

    @abstractmethod
    def pick_file(
        self, title: str, initial: Path | None = None, patterns: Sequence[str] = ()
    ) -> Path | None: ...


class OS(ABC):
    """Host OS adapter. One instance per process."""

    os_id: str = ""

    @abstractmethod
    def is_supported_host(self) -> bool: ...

    @property
    @abstractmethod
    def process(self) -> ProcessRunner: ...

    @property
    @abstractmethod
    def tools(self) -> ToolLocator: ...

    @property
    @abstractmethod
    def fs(self) -> FileSystemPolicy: ...

    @property
    @abstractmethod
    def shell(self) -> DesktopShell: ...
