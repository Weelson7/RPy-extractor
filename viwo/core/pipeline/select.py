"""Plugin selection (doc 3.3): a pure function, so every combination is testable."""

from typing import Mapping, Sequence

from viwo.contracts.errors import ViwoError
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
    unknown = [p for p in request.plugins if p not in enabled]
    if unknown and request.mode in (ExtractionMode.SINGLE, ExtractionMode.MIXED):
        raise ViwoError(
            "invalid_request",
            f"unknown or disabled plugin(s): {', '.join(unknown)}",
            hint=f"enabled plugins: {', '.join(sorted(enabled))}",
        )
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


def with_games(plugins: Mapping, chosen: Sequence[str], detections: Mapping) -> tuple[str, ...]:
    """Doc 2.10: a game plugin never runs alone. A chosen game plugin brings its engine (first);
    the game plugins of the chosen engines whose own detection names their game (confidence
    >= 0.5) run with them, after them."""
    order: list[str] = []
    for pid in chosen:
        engine = plugins[pid].manifest.engine if pid in plugins else ""
        for wanted in (engine, pid) if engine in plugins else (pid,):
            if wanted not in order:
                order.append(wanted)
    games = [
        pid
        for pid, plugin in sorted(plugins.items())
        if plugin.manifest.engine in order
        and pid not in order
        and pid in detections
        and detections[pid].confidence >= 0.5
    ]
    return (*order, *games)
