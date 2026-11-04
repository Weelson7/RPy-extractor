"""Hash locks for the pinned Python packages (tools.json "python" and "workers").

Usage: python tools/pin_python.py [ID ...]
For each pin, platform (windows, linux) and supported CPython (3.11 to 3.14), pip downloads the
pin's whole dependency closure as wheels; every file's sha256 goes into
viwo/data/locks/<id>-<platform>-<python>.txt (`name==version --hash=sha256:...`). Installs use
`pip install --require-hashes --no-deps -r <lock>`: a file that does not match is refused.
Run it whenever a pin changes; a test checks that every pin has its locks.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCKS = ROOT / "viwo" / "data" / "locks"
PLATFORMS = {
    "windows": ["--platform", "win_amd64"],
    "linux": ["--platform", "manylinux2014_x86_64", "--platform", "manylinux_2_28_x86_64"],
}
PYTHONS = ("3.11", "3.12", "3.13", "3.14")  # pyproject: requires-python >= 3.11
WHEEL = re.compile(r"^(?P<name>[^-]+)-(?P<version>[^-]+)-")


def pins() -> dict[str, str]:
    data = json.loads((ROOT / "viwo" / "data" / "tools.json").read_text(encoding="utf-8"))
    workers = {k: v["pin"] for k, v in data.get("workers", {}).items() if not k.startswith("_")}
    return {**data["python"], **workers}


PIP = [sys.executable, "-m", "pip", "--disable-pip-version-check", "-q"]
MISSING = re.compile(
    r"No matching distribution found for ([A-Za-z0-9_.\-]+(?:==[A-Za-z0-9_.\-]+)?)"
)
SOURCES: dict[str, str] = {}  # sdist-only package -> its sdist's sha256 (one per run)
WHEELS = Path(tempfile.mkdtemp(prefix="viwo-pin-"))  # their locally built wheels, for every lock


def _source(name: str, wheels: Path) -> None:
    """An sdist-only package (no wheel anywhere): its sdist, built locally into a pure-Python
    wheel the cross-platform resolver can use; the lock records the sdist's hash."""
    with tempfile.TemporaryDirectory() as tmp:
        download = [*PIP, "download", "--no-deps", "--no-binary", ":all:", "-d", tmp, name]
        subprocess.run(download, check=True, timeout=600)
        sdist = next(Path(tmp).iterdir())
        subprocess.run([*PIP, "wheel", "--no-deps", "-w", str(wheels), str(sdist)], check=True)
        key = name.split("==")[0].replace("_", "-").lower()
        SOURCES[key] = hashlib.sha256(sdist.read_bytes()).hexdigest()


def _resolve(pin: str, platform: str, python: str, dest: Path, wheels: Path) -> None:
    argv = [*PIP, "download", "--only-binary", ":all:", "--python-version", python]
    argv += ["--implementation", "cp", *PLATFORMS[platform], "--find-links", str(wheels)]
    for _ in range(8):  # one sdist-only package more each round
        done = subprocess.run(
            [*argv, "-d", str(dest), *pin.split()], capture_output=True, text=True
        )
        missing = MISSING.search(done.stderr)
        if done.returncode == 0:
            return
        spec = missing[1].split(";")[0] if missing else ""  # a name, or name==version
        if not spec or spec.split("==")[0].replace("_", "-").lower() in SOURCES:
            raise subprocess.CalledProcessError(done.returncode, argv, done.stderr)
        _source(spec, wheels)
    raise subprocess.CalledProcessError(1, argv, "too many sdist-only packages")


def lock(pin: str, platform: str, python: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "dest"
        _resolve(pin, platform, python, dest, WHEELS)
        lines = []
        for wheel in sorted(dest.iterdir()):
            match = WHEEL.match(wheel.name)
            name, version = match["name"].replace("_", "-").lower(), match["version"]
            digest = SOURCES.get(name) or hashlib.sha256(wheel.read_bytes()).hexdigest()
            lines.append(f"{name}=={version} --hash=sha256:{digest}")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    LOCKS.mkdir(parents=True, exist_ok=True)
    for dep_id, pin in pins().items():
        if argv and dep_id not in argv:
            continue
        for platform in PLATFORMS:
            for python in PYTHONS:
                path = LOCKS / f"{dep_id}-{platform}-{python}.txt"
                try:
                    path.write_text(lock(pin, platform, python), encoding="utf-8")
                    print(f"{path.relative_to(ROOT).as_posix()}: {pin}", flush=True)
                except subprocess.CalledProcessError:
                    print(
                        f"{dep_id} {platform} {python}: no complete wheel set for {pin}", flush=True
                    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
