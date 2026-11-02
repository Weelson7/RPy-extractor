"""OS layer selection (doc 1). Absolute imports keep the stdlib `os` module intact."""

from __future__ import annotations

import sys
from typing import Mapping

from viwo.contracts.errors import ViwoError
from viwo.contracts.os import OS

from .linux import LinuxOS
from .windows import WindowsOS

OS_LAYERS = {"linux": LinuxOS, "windows": WindowsOS}


def host_os_id() -> str:
    return "windows" if sys.platform == "win32" else "linux"


def select_os(os_id: str = "auto", tool_overrides: Mapping[str, str] | None = None) -> OS:
    key = host_os_id() if os_id in ("", "auto") else os_id
    if key not in OS_LAYERS:
        raise ViwoError("invalid_request", f"unknown OS layer: {os_id}")
    layer = OS_LAYERS[key](tool_overrides)
    if not layer.is_supported_host():
        raise ViwoError("refused", f"OS layer '{key}' cannot run on this host")
    return layer
