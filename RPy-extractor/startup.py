"""Startup and dependency checking for RPy Extractor."""
import shutil
import subprocess
import sys
import os
from pathlib import Path
from typing import Callable
from logging_utils import emit_log


def tlog(message: str) -> None:
    """Log with timestamp."""
    emit_log(message)


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Run command and capture output."""
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr


def module_available(module: str) -> bool:
    """Check if Python module is available."""
    code, _, _ = run([sys.executable, "-m", module, "--help"])
    return code == 0


def import_available(module: str) -> bool:
    """Check if Python import works for a module."""
    code, _, _ = run([sys.executable, "-c", f"import {module}"])
    return code == 0


def ensure_python_module(module: str, import_name: str | None = None, required: bool = False) -> bool:
    """Ensure a Python package can be imported, with pip and pip --user fallback."""
    import_target = import_name or module

    if import_available(import_target):
        tlog(f"[PREFLIGHT] ✓ {module} module is available")
        return True

    tlog(f"[PREFLIGHT] Installing {module} module...")
    code, _, _ = run([sys.executable, "-m", "pip", "install", module])
    if code == 0 and import_available(import_target):
        tlog(f"[PREFLIGHT] ✓ {module} installed and available")
        return True

    tlog(f"[PREFLIGHT] Trying --user install for {module}...")
    code, _, _ = run([sys.executable, "-m", "pip", "install", "--user", module])
    result = code == 0 and import_available(import_target)
    if result:
        tlog(f"[PREFLIGHT] ✓ {module} installed (--user) and available")
    else:
        severity = "✗" if required else "⚠"
        tlog(f"[PREFLIGHT] {severity} Failed to install {module}")
    return result


def command_exists(name: str) -> bool:
    """Check if command exists in PATH."""
    return shutil.which(name) is not None


def any_command_exists(names: tuple[str, ...]) -> bool:
    """Check if any of the commands exist."""
    return any(command_exists(name) for name in names)


def ensure_unrpa() -> bool:
    """Ensure unrpa is installed with detailed logging."""
    return ensure_python_module("unrpa", import_name="unrpa", required=True)


def ensure_unitypy() -> bool:
    """Ensure UnityPy is installed for Unity extraction."""
    result = ensure_python_module("UnityPy", import_name="UnityPy", required=False)
    if not result:
        tlog("[PREFLIGHT] ⚠ UnityPy not available - Unity extraction will be limited")
    return result


def _check_7zip_installed() -> bool:
    """Check if 7zip is installed, including common Windows paths with verbose logging."""
    if any_command_exists(("7z", "7za", "7zr")):
        tlog("[7ZIP] ✓ Found 7zip in PATH")
        return True
    
    tlog("[7ZIP] Searching common installation paths...")
    common_paths = [
        Path("C:/Program Files/7-Zip"),
        Path("C:/Program Files (x86)/7-Zip"),
        Path(os.path.expandvars("%PROGRAMFILES%/7-Zip")),
        Path(os.path.expandvars("%PROGRAMFILES(x86)%/7-Zip")),
        Path(os.path.expandvars("%USERPROFILE%/scoop/apps/7zip/current")),
        Path("C:/ProgramData/chocolatey/lib/7zip/tools"),
        Path(os.path.expandvars("%ALLUSERSPROFILE%/chocolatey/lib/7zip/tools")),
    ]
    
    for base_path in common_paths:
        for exe in ("7z.exe", "7za.exe", "7zr.exe"):
            exe_path = base_path / exe
            if exe_path.exists():
                tlog(f"[7ZIP] ✓ Found 7zip at: {exe_path}")
                return True
    
    tlog("[7ZIP] 7zip not found in common paths")
    return False


def install_7zip_best_effort() -> bool:
    """Attempt to install 7zip via winget/choco/scoop with detailed logging."""
    tlog("[7ZIP] ✓ Verifying 7zip installation...")
    
    if _check_7zip_installed():
        tlog("[7ZIP] ✓ 7zip is available")
        return True
    
    tlog("[7ZIP] 7zip not found, attempting installation via package managers...")
    
    installers = [
        ("winget", ["winget", "install", "--id", "7zip.7zip", "-e", "--accept-package-agreements", "--accept-source-agreements"]),
        ("choco", ["choco", "install", "7zip", "-y"]),
        ("scoop", ["scoop", "install", "7zip"]),
    ]
    
    for installer_name, cmd in installers:
        if not command_exists(installer_name):
            tlog(f"[7ZIP] ✗ {installer_name} not available, skipping")
            continue
        
        tlog(f"[7ZIP] Trying {installer_name}...")
        code, stdout, stderr = run(cmd)
        output = (stdout or stderr)[:200] if stdout or stderr else ""
        
        if code == 0:
            tlog(f"[7ZIP] {installer_name} completed with status {code}")
        else:
            tlog(f"[7ZIP] {installer_name} failed with status {code}")
        
        if output:
            tlog(f"[7ZIP] {installer_name} output: {output.split(chr(10))[0]}")
        
        if _check_7zip_installed():
            tlog(f"[7ZIP] ✓ 7zip confirmed available after {installer_name}")
            return True
    
    result = _check_7zip_installed()
    if result:
        tlog("[7ZIP] ✓ 7zip is now available")
    else:
        tlog("[7ZIP] ✗ 7zip not found - .7z file extraction will fail (optional)")
    
    return result


def startup_dependency_preflight() -> dict[str, object]:
    """Check all required dependencies at startup with detailed logging."""
    report: list[str] = []

    tlog("[PREFLIGHT] ========== Dependency Preflight Check ==========")
    report.append("Dependency preflight start")

    # Check unrpa (REQUIRED)
    tlog("[PREFLIGHT] Checking unrpa Python module...")
    unrpa_ready = module_available("unrpa")
    if not unrpa_ready:
        tlog("[PREFLIGHT] unrpa not found, attempting installation...")
        unrpa_ready = ensure_unrpa()
        if not unrpa_ready:
            tlog("[PREFLIGHT] ✗ CRITICAL: unrpa installation failed")
        else:
            tlog("[PREFLIGHT] ✓ unrpa successfully installed")
    else:
        tlog("[PREFLIGHT] ✓ unrpa module available")
    report.append(f"[REQUIRED] unrpa: {'✓ ready' if unrpa_ready else '✗ missing'}")

    # Check 7zip (OPTIONAL but recommended)
    tlog("[PREFLIGHT] Checking 7zip CLI...")
    sevenzip_ready = any_command_exists(("7z", "7za", "7zr"))
    if not sevenzip_ready:
        tlog("[PREFLIGHT] 7zip not found in PATH, attempting installation...")
        sevenzip_ready = install_7zip_best_effort()
    else:
        tlog("[PREFLIGHT] ✓ 7zip already available")
    report.append(f"[OPTIONAL] 7zip: {'✓ ready' if sevenzip_ready else '⚠ missing (many archives still work)'}")

    # Check unrar (OPTIONAL)
    tlog("[PREFLIGHT] Checking unrar CLI...")
    unrar_ready = command_exists("unrar")
    if unrar_ready:
        tlog("[PREFLIGHT] ✓ unrar available")
    else:
        tlog("[PREFLIGHT] ⚠ unrar not found (7zip can extract most .rar files)")
    report.append(f"[OPTIONAL] unrar: {'✓ ready' if unrar_ready else '⚠ missing (7zip can handle most .rar)'}")

    # Unity-specific tooling checks (OPTIONAL unless extracting Unity content)
    tlog("[PREFLIGHT] Checking UnityPy module for Unity extraction...")
    unitypy_ready = import_available("UnityPy")
    if not unitypy_ready:
        tlog("[PREFLIGHT] UnityPy not found, attempting installation...")
        unitypy_ready = ensure_unitypy()
    else:
        tlog("[PREFLIGHT] ✓ UnityPy module available")
    report.append(f"[UNITY] UnityPy: {'✓ ready' if unitypy_ready else '⚠ missing (Unity extraction fallback only)'}")

    tlog("[PREFLIGHT] Checking AssetRipper CLI...")
    assetripper_ready = any_command_exists(("AssetRipper.Console", "AssetRipper.Console.exe", "AssetRipper"))
    if assetripper_ready:
        tlog("[PREFLIGHT] ✓ AssetRipper available")
    else:
        tlog("[PREFLIGHT] ⚠ AssetRipper not found (optional Unity fallback)")
    report.append(f"[UNITY] AssetRipper: {'✓ ready' if assetripper_ready else '⚠ missing (optional fallback)'}")

    tlog("[PREFLIGHT] Checking UABEA CLI...")
    uabea_ready = any_command_exists(("UABEAvalonia", "UABEAvalonia.exe", "UABEA", "UABEA.exe", "uabea-cli"))
    if uabea_ready:
        tlog("[PREFLIGHT] ✓ UABEA available")
    else:
        tlog("[PREFLIGHT] ⚠ UABEA not found (optional Unity fallback)")
    report.append(f"[UNITY] UABEA: {'✓ ready' if uabea_ready else '⚠ missing (optional fallback)'}")

    # Overall status
    all_required = unrpa_ready
    status = "✓ PASS" if all_required else "✗ FAIL"
    tlog(f"[PREFLIGHT] {status} - Preflight check complete")
    tlog("[PREFLIGHT] ==========================================")
    
    return {
        "ok": all_required,
        "unrpa": unrpa_ready,
        "sevenzip": sevenzip_ready,
        "unrar": unrar_ready,
        "unitypy": unitypy_ready,
        "assetripper": assetripper_ready,
        "uabea": uabea_ready,
        "report": report,
    }


def dependency_status_snapshot() -> dict[str, object]:
    """Return dependency availability without install side effects."""
    statuses = [
        {
            "id": "unrpa",
            "label": "unrpa",
            "required": True,
            "available": module_available("unrpa"),
            "category": "required",
        },
        {
            "id": "sevenzip",
            "label": "7zip (7z/7za/7zr)",
            "required": False,
            "available": any_command_exists(("7z", "7za", "7zr")),
            "category": "optional",
        },
        {
            "id": "unrar",
            "label": "unrar",
            "required": False,
            "available": command_exists("unrar"),
            "category": "optional",
        },
        {
            "id": "unitypy",
            "label": "UnityPy",
            "required": False,
            "available": import_available("UnityPy"),
            "category": "unity",
        },
        {
            "id": "assetripper",
            "label": "AssetRipper",
            "required": False,
            "available": any_command_exists(("AssetRipper.Console", "AssetRipper.Console.exe", "AssetRipper")),
            "category": "unity",
        },
        {
            "id": "uabea",
            "label": "UABEA",
            "required": False,
            "available": any_command_exists(("UABEAvalonia", "UABEAvalonia.exe", "UABEA", "UABEA.exe", "uabea-cli")),
            "category": "unity",
        },
    ]

    required_ok = all(item["available"] for item in statuses if item["required"])

    return {
        "success": True,
        "requiredOk": required_ok,
        "dependencies": statuses,
    }
