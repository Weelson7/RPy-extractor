"""Extraction type resolution and media-focused default filtering."""
from pathlib import Path

from models import IMAGE_EXTS, AUDIO_EXTS, VIDEO_EXTS


SUPPORTED_EXTRACTION_TYPES = {"auto", "unity", "renpy", "generic"}

# Optional 3D model extensions for a future model-focused pass.
MODEL_EXTS = {
    ".fbx",
    ".obj",
    ".dae",
    ".blend",
    ".3ds",
    ".stl",
    ".gltf",
    ".glb",
    ".usd",
    ".usdz",
}

UNITY_MEDIA_EXTS = IMAGE_EXTS | AUDIO_EXTS | VIDEO_EXTS


def _count_matches(root: Path, patterns: tuple[str, ...], limit: int = 64) -> int:
    """Count files matching glob patterns with an upper bound for speed."""
    found = 0
    for pattern in patterns:
        for _ in root.rglob(pattern):
            found += 1
            if found >= limit:
                return found
    return found


def detect_unity_confidence(game_root: Path) -> tuple[int, list[str]]:
    """Return a confidence score and reasons indicating Unity content."""
    score = 0
    reasons: list[str] = []

    # Strong signals: executable-adjacent Unity runtime artifacts.
    direct_patterns = (
        "*_Data/globalgamemanagers",
        "*_Data/globalgamemanagers.assets",
        "*_Data/level*",
        "UnityPlayer.dll",
    )
    direct_hits = _count_matches(game_root, direct_patterns)
    if direct_hits:
        score += 70
        reasons.append(f"runtime-artifacts:{direct_hits}")

    # Medium signals: common Unity asset containers.
    asset_patterns = (
        "*.assets",
        "*.resource",
        "*.resS",
        "*.unity3d",
        "*.bundle",
    )
    asset_hits = _count_matches(game_root, asset_patterns)
    if asset_hits:
        score += min(25, asset_hits)
        reasons.append(f"asset-containers:{asset_hits}")

    # Supporting signal: streaming assets folders are frequent in Unity games.
    stream_hits = _count_matches(game_root, ("**/StreamingAssets", "**/StreamingAssets/*"))
    if stream_hits:
        score += 10
        reasons.append("streaming-assets")

    return min(score, 100), reasons


def detect_renpy_confidence(game_root: Path) -> tuple[int, list[str]]:
    """Return a confidence score and reasons indicating Ren'Py content."""
    score = 0
    reasons: list[str] = []

    rpa_hits = _count_matches(game_root, ("*.rpa",))
    if rpa_hits:
        score += 75
        reasons.append(f"rpa-archives:{rpa_hits}")

    rpy_hits = _count_matches(game_root, ("game/*.rpy", "**/*.rpy"))
    if rpy_hits:
        score += min(20, rpy_hits)
        reasons.append(f"rpy-scripts:{rpy_hits}")

    return min(score, 100), reasons


def resolve_extraction_type(game_root: Path, requested_type: str | None) -> dict:
    """Resolve extraction type from user preference and folder signatures."""
    requested = (requested_type or "auto").strip().lower()
    if requested not in SUPPORTED_EXTRACTION_TYPES:
        requested = "auto"

    unity_score, unity_reasons = detect_unity_confidence(game_root)
    renpy_score, renpy_reasons = detect_renpy_confidence(game_root)

    candidates = {
        "unity": {"score": unity_score, "reasons": unity_reasons},
        "renpy": {"score": renpy_score, "reasons": renpy_reasons},
    }

    if requested != "auto":
        resolved = requested
    elif unity_score >= max(45, renpy_score):
        resolved = "unity"
    elif renpy_score > 0:
        resolved = "renpy"
    else:
        resolved = "generic"

    return {
        "requested": requested,
        "resolved": resolved,
        "candidates": candidates,
    }


def default_selected_exts_for_type(extraction_type: str) -> set[str] | None:
    """Return default extension filter for extraction type, if any.

    A ``None`` return means "no filtering" to preserve legacy behavior.
    """
    kind = (extraction_type or "").strip().lower()
    if kind == "unity":
        return set(UNITY_MEDIA_EXTS)
    return None
