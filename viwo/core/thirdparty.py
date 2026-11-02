"""third_party/: pinned tools installed automatically (doc 10, viwo/data/tools.json).

Executables: downloaded from pinned GitHub releases, checked against the pinned sha256, unpacked
safely into third_party/<id>/ and found there at boot. Python packages: pinned pip install into
third_party/python (added to sys.path). Nothing is installed outside third_party/.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.workspace import inside, safe_member

from .pipeline.ticker import Ticker

MANIFEST = Path(__file__).resolve().parent.parent / "data" / "tools.json"
PLATFORM = "windows" if sys.platform == "win32" else "linux"
FROZEN = bool(getattr(sys, "frozen", False))


def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def home_of(config) -> Path:
    """third_party/ lives next to the active startup.ini (or the current folder)."""
    first = str(config.source).split(" <- ")[0]
    return Path(first).parent if config.source != "defaults" else Path.cwd()


def python_dir(home: Path) -> Path:
    return home / "third_party" / "python"


def activate(home: Path) -> None:
    folder = str(python_dir(home))
    if os.path.isdir(folder) and folder not in sys.path:
        sys.path.append(folder)


def found_tools(home: Path) -> dict[str, str]:
    """dep id -> executable installed under third_party/<id>/ for this platform."""
    out = {}
    for dep, entry in manifest()["tools"].items():
        spec, folder = entry.get(PLATFORM), home / "third_party" / dep
        if spec and folder.is_dir():
            hit = next((p for p in sorted(folder.rglob(spec["find"])) if p.is_file()), None)
            if hit is not None:
                out[dep] = str(hit)
    return out


def installable(dep_id: str, kind: str) -> bool:
    data = manifest()
    if kind == "python":
        return not FROZEN and dep_id in data["python"]
    return PLATFORM in data["tools"].get(dep_id, {})


def _download(url: str, target: Path, size: int, say, cancel) -> str:
    digest, ticker = hashlib.sha256(), Ticker(say, f"Downloading {target.name}, KB:", size // 1024)
    with urllib.request.urlopen(url, timeout=60) as response, open(target, "wb") as out:
        while chunk := response.read(1 << 20):
            if cancel is not None and cancel.cancelled:
                raise ViwoError("cancelled", "download cancelled")
            out.write(chunk)
            digest.update(chunk)
            ticker.tick(len(chunk) // 1024)
    return digest.hexdigest()


def _unzip(file: Path, out: Path) -> None:
    with zipfile.ZipFile(file) as archive:
        for info in archive.infolist():
            rel = safe_member(info.filename)
            if rel is None or info.is_dir():
                continue
            target = out.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


def _untar(file: Path, out: Path) -> None:
    with tarfile.open(file) as archive:
        for member in archive.getmembers():
            rel = safe_member(member.name)
            if rel is None or not member.isfile():
                continue  # links, devices and traversal are never extracted
            target = out.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


def _unpack(kind: str, file: Path, out: Path, spec: dict, runner) -> None:
    out.mkdir(parents=True, exist_ok=True)
    if kind == "zip":
        _unzip(file, out)
    elif kind == "tar":
        _untar(file, out)
    elif kind == "gz":
        with gzip.open(file) as src, open(out / spec["save_as"], "wb") as dst:
            shutil.copyfileobj(src, dst)
    elif kind == "raw":
        shutil.copy2(file, out / spec["save_as"])
    elif kind == "msi":  # administrative install: unpacks the MSI, no admin rights needed
        result = runner.run(["msiexec", "/a", str(file), "/qn", f"TARGETDIR={out}"], timeout=600)
        if not result.ok:
            raise ViwoError(
                "failed", "msiexec could not unpack the installer", hint=result.stderr[-200:]
            )


def install_tool(dep_id: str, home: Path, runner, say=None, cancel=None) -> str:
    spec = manifest()["tools"].get(dep_id, {}).get(PLATFORM)
    if spec is None:
        raise ViwoError("unavailable", f"no pinned {dep_id} build for {PLATFORM}")
    root = home / "third_party"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{dep_id}-", dir=root) as tmp:
        file = Path(tmp) / spec["url"].rsplit("/", 1)[-1]
        if _download(spec["url"], file, spec["size"], say, cancel) != spec["sha256"]:
            raise ViwoError("refused", f"{file.name}: checksum mismatch, not installed")
        out = Path(tmp) / "out"
        _unpack(spec["kind"], file, out, spec, runner)
        dest = root / dep_id
        if dest.exists():
            shutil.rmtree(dest)
        os.replace(out, dest)
    path = found_tools(home).get(dep_id)
    if path is None or not inside(root, Path(path)):
        raise ViwoError("failed", f"{dep_id}: {spec['find']} not found after unpacking")
    if PLATFORM != "windows":
        os.chmod(path, os.stat(path).st_mode | 0o111)
    return path


def install_python(dep_id: str, home: Path, runner) -> str:
    pin = manifest()["python"][dep_id]
    target = python_dir(home)
    argv = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--target",
        str(target),
        pin,
    ]
    result = runner.run(argv, timeout=1800)
    if not result.ok:
        raise ViwoError("failed", f"pip could not install {pin}", hint=(result.stderr or "")[-300:])
    activate(home)
    return pin
