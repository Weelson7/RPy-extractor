"""Extractor registry for game type routing."""
from .base import Extractor
from .renpy_extractor import RenPyExtractor
from .unity_extractor import UnityExtractor


class GenericExtractor(RenPyExtractor):
    """Fallback extractor that uses the current generic archive pipeline."""

    extractor_type = "generic"


_EXTRACTORS: dict[str, Extractor] = {
    "renpy": RenPyExtractor(),
    "unity": UnityExtractor(),
    "generic": GenericExtractor(),
}


def get_extractor(extractor_type: str) -> Extractor:
    """Resolve extractor by type with generic fallback."""
    key = (extractor_type or "generic").strip().lower()
    return _EXTRACTORS.get(key, _EXTRACTORS["generic"])
