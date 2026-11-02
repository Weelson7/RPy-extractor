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
        "--collect-data",
        "viwo",
        "--add-data",
        f"{ROOT / 'viwo/core/capture/rd_harvest.py'}{SEP}viwo/core/capture",
    ]
    for package in ("UnityPy", "py7zr", "unrpa"):
        args += ["--collect-all", package]
    subprocess.run([*args, str(ROOT / "packaging" / "viwo_entry.py")], check=True, cwd=ROOT)
    bundle = out / "viwo"
    for name in ("startup.ini", "README.md", "LICENSE"):
        shutil.copy2(ROOT / name, bundle / name)
    return bundle


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
