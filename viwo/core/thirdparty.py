"""third_party/: pinned tools installed automatically (doc 10, viwo/data/tools.json).

Executables: downloaded from pinned HTTPS releases, checked against the pinned sha256, unpacked
safely into third_party/<id>/ and found there at boot. A spec may need other entries first
("needs": 7-Zip unpacks self-extractors, the .NET runtime runs framework-dependent tools), may
borrow another entry's folder ("from") and may run through a prefix ("argv", e.g. dotnet + dll,
or qrenderdoc --py). Python packages: pinned pip install into third_party/python (sys.path);
worker packages (never imported, GPL) into third_party/<id>/, run as processes (core/workers.py).
Nothing is installed outside third_party/.
"""

import gzip
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.workspace import inside
from viwo.os import host_os_id

from . import downloads, workers

MANIFEST = Path(__file__).resolve().parent.parent / "data" / "tools.json"
PLATFORM = host_os_id()
FROZEN = bool(getattr(sys, "frozen", False))
Argv = tuple[str, ...]


def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def home_of(config) -> Path:
    """third_party/ lives next to the active startup.ini (or the current folder)."""
    return config.path.parent if config.path is not None else Path.cwd()


def python_dir(home: Path) -> Path:
    return home / "third_party" / "python"


def activate(home: Path) -> None:
    folder = str(python_dir(home))
    if os.path.isdir(folder) and folder not in sys.path:
        sys.path.append(folder)
    dotnet = home / "third_party" / "dotnet"
    if dotnet.is_dir():  # ViWo-owned .NET runtime: framework-dependent tools find it here
        os.environ["DOTNET_ROOT"] = str(dotnet)


CACHE = ".viwo-tools.json"  # per tool folder: find name -> relative hit (boot never rglobs twice)


def _hit(folder: Path, name: str) -> Path | None:
    """First file called `name` under folder; the answer is cached next to the tool."""
    if not folder.is_dir():
        return None
    cache = folder / CACHE
    try:
        known = json.loads(cache.read_text(encoding="utf-8"))
        hit = folder / known[name]
        if isinstance(known, dict) and hit.is_file():
            return hit
    except (OSError, ValueError, KeyError, TypeError):
        known = {}
    hit = next((p for p in sorted(folder.rglob(name)) if p.is_file()), None)
    if hit is not None:
        try:
            known = {**known, name: hit.relative_to(folder).as_posix()}
            cache.write_text(json.dumps(known), encoding="utf-8")
        except OSError:
            pass  # a read-only folder still works, just slower
    return hit


def spec_of(dep_id: str) -> dict | None:
    return manifest()["tools"].get(dep_id, {}).get(PLATFORM)


RUNTIMES = {"{dotnet}": "dotnet", "{java}": "jdk"}


def tool_argv(dep_id: str, home: Path, spec: dict | None = None) -> Argv | None:
    """How to run an installed entry (None when it is not installed)."""
    spec = spec or spec_of(dep_id)
    if spec is None:
        return None
    hit = _hit(home / "third_party" / spec.get("from", dep_id), spec["find"])
    if hit is None:
        return None
    argv: list[str] = []
    for part in spec.get("argv") or ["{path}"]:
        if part == "{python}":  # pure-Python tools run by ViWo's own interpreter
            part = sys.executable
        if part in RUNTIMES:  # a pinned runtime runs the tool ({dotnet} + dll, {java} -jar)
            runtime_id = RUNTIMES[part]
            found = _hit(
                home / "third_party" / runtime_id, manifest()["tools"][runtime_id][PLATFORM]["find"]
            )
            if found is None:
                return None
            part = str(found)
        argv.append(part.replace("{path}", str(hit)))
    return tuple(argv)


def found_tools(home: Path) -> dict[str, str | Argv]:
    """dep id -> executable (or argv prefix) installed under third_party/ for this platform."""
    out: dict[str, str | Argv] = {}
    for dep, entry in manifest()["tools"].items():
        spec = entry.get(PLATFORM)
        if spec and not entry.get("hidden"):
            argv = tool_argv(dep, home, spec)
            if argv:
                out[dep] = argv[0] if len(argv) == 1 else argv
    return {**out, **workers.found(home)}


def installed_version(dep_id: str, home: Path) -> str:
    """The pinned version when the tool runs from third_party/, else ""."""
    if dep_id in workers.entries():
        return workers.entries()[dep_id]["version"] if workers.argv(dep_id, home) else ""
    entry = manifest()["tools"].get(dep_id, {})
    spec = entry.get(PLATFORM)
    if spec and tool_argv(dep_id, home, spec):
        return str(spec.get("version") or entry.get("version", ""))
    return ""


def on_demand(dep_id: str) -> bool:
    """Heavy pins (Ghidra) install only when asked by name, never by the startup preflight."""
    entry = manifest()["tools"].get(dep_id) or workers.entries().get(dep_id) or {}
    return bool(entry.get("on_demand"))


def installable(dep_id: str, kind: str) -> bool:
    data = manifest()
    if kind == "python":
        return not FROZEN and dep_id in data["python"]
    return PLATFORM in data["tools"].get(dep_id, {}) or (not FROZEN and dep_id in workers.entries())


def _unpack(kind: str, file: Path, out: Path, spec: dict, runner, home: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    if kind == "zip":
        downloads.unzip(file, out)
    elif kind == "tar":
        downloads.untar(file, out)
    elif kind == "gz":
        with gzip.open(file) as src:
            downloads.write(src, out / spec["save_as"], 0o755)
    elif kind == "raw":
        with open(file, "rb") as src:
            downloads.write(src, out / spec["save_as"], 0o755)
    elif kind == "msi":  # administrative install (no admin rights); msiexec parses its own
        # command line, so the quotes around paths with spaces must reach it verbatim
        done = subprocess.run(f'msiexec /a "{file}" /qn TARGETDIR="{out}"', timeout=600)
        if done.returncode:
            raise ViwoError(
                "failed", f"msiexec could not unpack {file.name} (code {done.returncode})"
            )
    elif kind == "sfx":  # 7-Zip opens the self-extracting stub
        argv = [*(tool_argv("sevenzip", home) or ()), "x", "-y", f"-o{out}", str(file)]
        result = runner.run(argv, timeout=600)
        if not result.ok:
            raise ViwoError(
                "failed", f"7-Zip could not unpack {file.name}", hint=result.stderr[-200:]
            )
    else:
        raise ViwoError("failed", f"{file.name}: unknown archive kind {kind!r} in tools.json")


def install_tool(dep_id: str, home: Path, runner, say=None, cancel=None) -> str:
    """Install one entry (and what it needs first); returns how it runs."""
    if dep_id in workers.entries():
        return workers.install(dep_id, home, runner)
    spec = spec_of(dep_id)
    if spec is None:
        raise ViwoError("unavailable", f"no pinned {dep_id} build for {PLATFORM}")
    for need in spec.get("needs", ()):
        if tool_argv(need, home) is None:
            install_tool(need, home, runner, say, cancel)
    root = home / "third_party"
    root.mkdir(parents=True, exist_ok=True)
    if "url" in spec:
        _fetch(dep_id, spec, root, runner, say, cancel)
    argv = tool_argv(dep_id, home, spec)
    if argv is None or not inside(root, Path(_hit(root / spec.get("from", dep_id), spec["find"]))):
        raise ViwoError("failed", f"{dep_id}: {spec['find']} not found after unpacking")
    for folder in spec.get("mkdir", ()):
        (root / dep_id / folder).mkdir(parents=True, exist_ok=True)
    return " ".join(argv)


def _fetch(dep_id: str, spec: dict, root: Path, runner, say, cancel) -> None:
    with tempfile.TemporaryDirectory(prefix=f".{dep_id}-", dir=root) as tmp:
        file = Path(tmp) / spec["url"].rsplit("/", 1)[-1]
        if downloads.download(spec["url"], file, spec["size"], say, cancel) != spec["sha256"]:
            raise ViwoError("refused", f"{file.name}: checksum mismatch, not installed")
        out = Path(tmp) / "out"
        try:
            _unpack(spec["kind"], file, out, spec, runner, root.parent)
        except OSError as exc:
            raise ViwoError(
                "failed",
                f"{file.name}: downloaded and verified, but it could not be unpacked ({exc})",
                hint="an antivirus may have quarantined the file: check its history and allow "
                "the third_party folder, then install again",
            )
        if not spec.get("from") and _hit(out, spec["find"]) is None:  # the old tool stays
            raise ViwoError("failed", f"{dep_id}: {spec['find']} not found after unpacking")
        downloads.swap(out, root / dep_id)


def lock_file(dep_id: str) -> Path:
    """The hash lock of a pinned Python package for this platform and interpreter."""
    python = f"{sys.version_info.major}.{sys.version_info.minor}"
    return MANIFEST.parent / "locks" / f"{dep_id}-{PLATFORM}-{python}.txt"


def pip_install(dep_id: str, target: Path, runner) -> None:
    """Every file of the pin's closure, each checked against its sha256 (tools/pin_python.py);
    a pin without a lock for this platform and Python is not installed unpinned."""
    lock = lock_file(dep_id)
    if not lock.is_file():
        raise ViwoError(
            "unavailable",
            f"no hash lock for {dep_id} on {PLATFORM} with Python {sys.version.split()[0]}",
            hint="tools/pin_python.py writes it (or says the pin has no build for this Python)",
        )
    argv = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--upgrade"]
    argv += ["--require-hashes", "--no-deps", "--target", str(target), "-r", str(lock)]
    result = runner.run(argv, timeout=3600)
    if not result.ok:
        raise ViwoError(
            "failed", f"pip could not install {dep_id}", hint=(result.stderr or "")[-300:]
        )


PINS = ".viwo-pins.json"  # dep id -> the pin installed (a bump or a broken install reinstalls)


def installed_pins(home: Path) -> dict[str, str]:
    try:
        return json.loads((python_dir(home) / PINS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def python_stale(dep_id: str, home: Path) -> bool:
    """A Python pin ViWo installed at another version than tools.json pins now (a pin bump):
    the startup check installs it again, over what is there (--upgrade). A package found
    elsewhere (a venv, the system) is the user's and is left alone."""
    pin, recorded = manifest()["python"].get(dep_id), installed_pins(home).get(dep_id)
    return bool(pin and recorded and recorded != pin)


def install_python(dep_id: str, home: Path, runner) -> str:
    pin = manifest()["python"][dep_id]
    pip_install(dep_id, python_dir(home), runner)
    pins = {**installed_pins(home), dep_id: pin}
    python_dir(home).mkdir(parents=True, exist_ok=True)
    (python_dir(home) / PINS).write_text(json.dumps(pins, indent=1), encoding="utf-8")
    activate(home)
    return pin
