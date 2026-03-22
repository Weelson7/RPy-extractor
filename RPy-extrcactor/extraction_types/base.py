"""Base contracts for extraction strategies."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class DetectionResult:
    """Engine detection output used for routing and diagnostics."""
    engine_type: str
    confidence: float
    evidence: list[str]


class Extractor:
    """Base extractor interface."""

    extractor_type: str = "generic"

    def extract(
        self,
        game_root: Path,
        output_dir: Path,
        selected_exts: set[str] | None,
        temp_root: Path,
        detection: DetectionResult,
        progress: Callable[[str], None] | None = None,
    ) -> dict:
        """Run extraction and return normalized result payload."""
        raise NotImplementedError()
