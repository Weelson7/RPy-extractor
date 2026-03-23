"""Unity discovery phase."""
from pathlib import Path
from typing import Callable

from extraction_core import log_append
from extraction_types.unity.discovery import build_discovery_index, DiscoveryIndex


def run_discovery_phase(
    game_root: Path,
    progress: Callable[[str], None] | None,
    logs: list[str],
) -> tuple[DiscoveryIndex | None, int]:
    """Build discovery index and return index + discovered count."""
    if progress:
        progress("[UNITY:DISCOVERY] Building discovery index")

    try:
        discovery_index = build_discovery_index(game_root, progress)
        discovered_count = len(discovery_index.discovered_assets)
        log_append(
            logs,
            f"[DISCOVERY] Built index: {discovered_count} assets across {len(discovery_index.containers_scanned)} containers",
            progress,
        )
        return discovery_index, discovered_count
    except Exception as exc:
        log_append(logs, f"[DISCOVERY] Failed: {exc}", progress)
        return None, 0
