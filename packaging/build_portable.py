"""Build the portable bundle (dist/viwo/ with viwo.exe on Windows) and smoke-test it.

Usage: python packaging/build_portable.py [--out DIR]
Needs: pip install pyinstaller ".[unity,sevenzip,renpy]"
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEP = ";" if os.name == "nt" else ":"


ENTRY_POINTS = {"cli.py", "__main__.py"}


def scripts() -> list[Path]:
    """Modules that run as their own process (a `__main__` block: RenderDoc helpers, worker
    scripts). --collect-data leaves .py files out, so each must be added as data."""
    return sorted(
        p
        for p in (ROOT / "viwo").rglob("*.py")
        if p.name not in ENTRY_POINTS and '__name__ == "__main__"' in p.read_text(encoding="utf-8")
    )


def script_data() -> list[str]:
    out: list[str] = []
    for path in scripts():
        out += ["--add-data", f"{path}{SEP}{path.parent.relative_to(ROOT).as_posix()}"]
    return out


def build(out: Path) -> Path:
    work = Path(tempfile.mkdtemp(prefix="viwo-build-"))
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--console",
        "--name",
        "viwo",
        "--distpath",
        str(out),
        "--workpath",
        str(work / "build"),
        "--specpath",
        str(work),
        "--collect-submodules",
        "viwo",
        "--hidden-import",
        "ssl",  # urllib only imports it lazily: without it https downloads fail in the bundle
        "--hidden-import",
        "_ssl",
        "--collect-data",
        "viwo",
        *script_data(),
        "--add-data",
        f"{ROOT / 'indexes'}{SEP}indexes",  # per-game indexes ship with the bundle
    ]
    for package in ("UnityPy", "py7zr", "unrpa"):
        args += ["--collect-all", package]
    subprocess.run([*args, str(ROOT / "packaging" / "viwo_entry.py")], check=True, cwd=ROOT)
    bundle = out / "viwo"
    for name in (
        "startup.ini",
        "README.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "CONTRIBUTING.md",
    ):
        shutil.copy2(ROOT / name, bundle / name)
    _fix_openssl(bundle / "_internal")
    return bundle


def _fix_openssl(internal: Path) -> None:
    """PyInstaller resolves libssl/libcrypto by name and can pick a foreign build from PATH
    (MSYS2, Git): the interpreter's own copies must ship, or https fails in the bundle."""
    if os.name != "nt":
        return
    base = Path(sys.base_prefix)
    for name in ("libssl-3-x64.dll", "libcrypto-3-x64.dll", "libssl-3.dll", "libcrypto-3.dll"):
        for folder in (base / "Library" / "bin", base / "DLLs", base):
            if (folder / name).is_file():
                shutil.copy2(folder / name, internal / name)
                break


def smoke(bundle: Path) -> None:
    exe = bundle / ("viwo.exe" if os.name == "nt" else "viwo")
    game = Path(tempfile.mkdtemp(prefix="viwo-smoke-")) / "game"
    game.mkdir()
    with zipfile.ZipFile(game / "data.zip", "w") as z:
        z.writestr("img/a.png", b"\x89PNG\r\n\x1a\n" + b"\0" * 64)
    for argv in (
        ["info"],
        ["slots"],
        ["--json", "detect", str(game)],
        ["extract", str(game), "--workspace", str(game.parent / "ws")],
        ["-m", "unrpa", "--version"],
        ["-m", "ssl"],  # the installer needs https inside the bundle
    ):
        result = subprocess.run([str(exe), *argv], capture_output=True, text=True)
        print(f"$ viwo {' '.join(argv)} -> {result.returncode}")
        if result.returncode != 0:
            raise SystemExit(result.stdout + result.stderr)
    if not (game.parent / "ws" / "zip" / "data.zip").is_file():
        raise SystemExit("smoke: the extraction did not produce the workspace")


if __name__ == "__main__":
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else ROOT / "dist"
    bundle = build(out)
    smoke(bundle)
    print(f"portable bundle ready: {bundle}")
