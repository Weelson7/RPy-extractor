"""RenPy extraction strategy."""
from pathlib import Path
from typing import Callable

from extraction import extract_assets

from .base import DetectionResult, Extractor


class RenPyExtractor(Extractor):
    """Extractor implementation for RenPy projects."""

    extractor_type = "renpy"

    def extract(
        self,
        game_root: Path,
        output_dir: Path,
        selected_exts: set[str] | None,
        temp_root: Path,
        detection: DetectionResult,
        progress: Callable[[str], None] | None = None,
    ) -> dict:
        core = extract_assets(
            game_root=game_root,
            output_dir=output_dir,
            selected_exts=selected_exts,
            temp_root=temp_root,
            progress=progress,
        )

        return {
            **core,
            "extractorType": self.extractor_type,
            "detection": {
                "type": detection.engine_type,
                "confidence": detection.confidence,
                "evidence": detection.evidence,
            },
        }
