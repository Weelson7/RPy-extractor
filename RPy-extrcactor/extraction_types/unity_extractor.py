"""Unity extraction strategy (initial media-first baseline)."""
from pathlib import Path
from typing import Callable

from extraction import extract_assets, log_append

from .base import DetectionResult, Extractor


class UnityExtractor(Extractor):
    """Extractor implementation for Unity projects."""

    extractor_type = "unity"

    def extract(
        self,
        game_root: Path,
        output_dir: Path,
        selected_exts: set[str] | None,
        temp_root: Path,
        detection: DetectionResult,
        progress: Callable[[str], None] | None = None,
    ) -> dict:
        if progress:
            progress("[UNITY] Starting Unity extraction pipeline (baseline)")

        core = extract_assets(
            game_root=game_root,
            output_dir=output_dir,
            selected_exts=selected_exts,
            temp_root=temp_root,
            progress=progress,
        )

        logs = list(core.get("logs", []))
        log_append(
            logs,
            "[UNITY] Baseline mode active: generic archive/file extraction is used while Unity object-level exporters are being integrated.",
            progress,
        )

        return {
            **core,
            "logs": logs,
            "extractorType": self.extractor_type,
            "detection": {
                "type": detection.engine_type,
                "confidence": detection.confidence,
                "evidence": detection.evidence,
            },
        }
