"""Plugin selection (doc 3.3): a pure function, so every combination is testable."""

from __future__ import annotations

from typing import Mapping, Sequence

from viwo.contracts.pipeline import (
    GENERIC_PLUGIN_ID,
    ExtractionMode,
    ExtractionRequest,
    MixedPolicy,
)
from viwo.contracts.types import DetectionResult


def select_plugins(
    request: ExtractionRequest,
    detections: Sequence[DetectionResult],
    priorities: Mapping[str, int],
) -> tuple[str, ...]:
    """Run order: confidence desc, priority desc, id. Never empty."""
    ranked = sorted(
        detections, key=lambda d: (-d.confidence, -priorities.get(d.plugin_id, 0), d.plugin_id)
    )
    order = [d.plugin_id for d in ranked]
    enabled = set(order)
    if request.mode is ExtractionMode.SINGLE:
        chosen = [p for p in request.plugins[:1] if p in enabled]
    elif request.mode is ExtractionMode.MIXED:
        if request.mixed_policy is MixedPolicy.ALL:
            chosen = order
        elif request.mixed_policy is MixedPolicy.DETECTED:
            strong = {d.plugin_id for d in ranked if d.confidence >= request.mixed_threshold}
            chosen = [p for p in order if p in strong]
        else:
            chosen = [p for p in order if p in set(request.plugins)]
    else:
        best = [d for d in ranked if d.plugin_id != GENERIC_PLUGIN_ID and d.confidence > 0]
        chosen = [best[0].plugin_id] if best else []
    if not chosen:
        chosen = [GENERIC_PLUGIN_ID] if GENERIC_PLUGIN_ID in enabled else order[:1]
    return tuple(chosen)
