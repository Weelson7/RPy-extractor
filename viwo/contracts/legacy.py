"""v1 response shapes kept for compatibility (doc 0.4, doc 3.5)."""

from __future__ import annotations

from typing import Any


def run_to_legacy(r) -> dict[str, Any]:
    """One `plugins[]` entry of the v1 extract result."""
    return {
        "id": r.plugin_id,
        "detection": r.detection.to_legacy_dict(),
        "exported": r.exported,
        "exportedByKind": dict(sorted(r.exported_by_kind.items())),
        "exportedByTool": r.backend,
        "inventoryCount": r.inventory_items or r.inventory_found,
        "verifyPassed": r.verify_passed,
        "backend": r.backend,
        "warnings": list(r.warnings),
        "error": r.error,
    }
