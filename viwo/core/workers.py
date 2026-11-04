"""Worker tools (viwo/data/tools.json "workers"): pinned Python packages that ViWo never imports.
pip installs each pin into third_party/<id>/ (not on sys.path); the backend runs the worker
script viwo/data/workers/<script> with ViWo's interpreter as a separate process (`-I`, so
nothing from the user's environment leaks in), handing it that folder (`--lib`). This is how
GPL code (Unicorn, angr's engine) is used: a process boundary, never an import (CLAUDE.md)."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from viwo.contracts.errors import ViwoError

SCRIPTS = Path(__file__).resolve().parent.parent / "data" / "workers"
MARK = ".viwo-pin"  # the pin a folder was installed from; another pin means not installed


def entries() -> dict[str, dict]:
    from .thirdparty import manifest

    return {k: v for k, v in manifest().get("workers", {}).items() if not k.startswith("_")}


def folder(home: Path, dep_id: str) -> Path:
    return home / "third_party" / dep_id


def argv(dep_id: str, home: Path) -> tuple[str, ...] | None:
    """[python, -I, script, --lib, folder] when the pinned packages are installed, else None."""
    entry = entries().get(dep_id)
    lib = folder(home, dep_id)
    if entry is None or not _installed(lib, entry["pin"]):
        return None
    return (sys.executable, "-I", str(SCRIPTS / entry["script"]), "--lib", str(lib))


def _installed(lib: Path, pin: str) -> bool:
    try:
        return (lib / MARK).read_text(encoding="utf-8").strip() == pin
    except OSError:
        return False


def found(home: Path) -> dict[str, tuple[str, ...]]:
    return {dep_id: hit for dep_id in entries() if (hit := argv(dep_id, home))}


def install(dep_id: str, home: Path, runner) -> str:
    """pip install the pin into third_party/<id>/ (unattended), then mark it."""
    pin = entries()[dep_id]["pin"]
    lib = folder(home, dep_id)
    fresh = lib.with_name(f".{dep_id}-new")  # a fresh folder: a pin change never mixes versions
    shutil.rmtree(fresh, ignore_errors=True)
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check"]
    result = runner.run([*cmd, "--target", str(fresh), *pin.split()], timeout=3600)
    if not result.ok:
        shutil.rmtree(fresh, ignore_errors=True)
        raise ViwoError("failed", f"pip could not install {pin}", hint=(result.stderr or "")[-300:])
    (fresh / MARK).write_text(pin, encoding="utf-8")
    shutil.rmtree(lib, ignore_errors=True)
    fresh.rename(lib)
    return " ".join(argv(dep_id, home) or ())
