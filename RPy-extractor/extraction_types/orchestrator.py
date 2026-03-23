"""Extraction orchestrator for engine detection and strategy dispatch."""
from pathlib import Path
from typing import Callable

from .detector import detect_engine
from .registry import get_extractor


def run_extraction(
    game_root: Path,
    output_dir: Path,
    selected_exts: set[str] | None,
    temp_root: Path,
    requested_type: str | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Route extraction to the chosen strategy with auto detection support."""
    detected = detect_engine(game_root)

    route_type = (requested_type or "auto").strip().lower()
    if route_type in {"", "auto"}:
        extractor_type = detected.engine_type
    else:
        extractor_type = route_type

    extractor = get_extractor(extractor_type)

    if progress:
        progress(
            "[ROUTER] "
            f"Requested={route_type}, detected={detected.engine_type} "
            f"({detected.confidence:.2f}), using={extractor.extractor_type}"
        )

    result = extractor.extract(
        game_root=game_root,
        output_dir=output_dir,
        selected_exts=selected_exts,
        temp_root=temp_root,
        detection=detected,
        progress=progress,
    )

    result.setdefault("extractorType", extractor.extractor_type)
    result.setdefault(
        "detection",
        {
            "type": detected.engine_type,
            "confidence": detected.confidence,
            "evidence": detected.evidence,
        },
    )
    return result
