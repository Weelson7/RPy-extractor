"""Game engine detection helpers for extractor routing."""
from pathlib import Path

from .base import DetectionResult


def _contains_file(root: Path, names: set[str], max_scan: int = 50000) -> bool:
    count = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name.lower() in names:
            return True
        count += 1
        if count >= max_scan:
            break
    return False


def detect_engine(game_root: Path) -> DetectionResult:
    """Detect game engine type from on-disk signatures."""
    evidence: list[str] = []

    unity_markers = {
        "globalgamemanagers",
        "globalgamemanagers.assets",
        "unityplayer.dll",
        "resources.assets",
        "mainData",
    }

    if _contains_file(game_root, unity_markers):
        evidence.append("Found Unity marker files")

    data_folders = [p for p in game_root.glob("*_Data") if p.is_dir()]
    if data_folders:
        evidence.append("Found *_Data folder pattern")

    if evidence:
        return DetectionResult(engine_type="unity", confidence=0.92, evidence=evidence)

    renpy_markers = {"script.rpy", "renpy.py", "renpy.exe"}
    if _contains_file(game_root, renpy_markers):
        return DetectionResult(
            engine_type="renpy",
            confidence=0.78,
            evidence=["Found RenPy marker files"],
        )

    return DetectionResult(
        engine_type="generic",
        confidence=0.4,
        evidence=["No strong engine-specific signature found"],
    )
