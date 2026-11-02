"""Capture policy (doc 11.1): checked before any launch. Refusals have no override."""

from __future__ import annotations

import json
import os
from pathlib import Path

from viwo.contracts.errors import ViwoError

POLICY_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "capture_policy.json"
CONFIRMATION = "local, offline, single-player use; I am responsible for EULA compliance"


def load_policy() -> dict:
    return json.loads(POLICY_FILE.read_text(encoding="utf-8"))


def _markers(game: Path, markers: dict[str, str]) -> list[str]:
    found = []
    for dirpath, dirnames, filenames in os.walk(game):
        for name in dirnames + filenames:
            if name.lower() in markers:
                found.append(f"{markers[name.lower()]} ({Path(dirpath, name).relative_to(game)})")
    return found


def check(rt, game: Path, confirmed: bool, sensitive: list[str]) -> list[str]:
    """Raise when capture is not allowed; return warnings when it is."""
    if "capture" not in rt.config.features:
        raise ViwoError(
            "refused", "runtime capture is off", hint="add capture to [startup] features in the ini"
        )
    policy = load_policy()
    found = _markers(game, policy["anti_cheat_markers"])
    if found:
        raise ViwoError(
            "refused", f"anti-cheat present: {'; '.join(found[:3])}", hint="no override"
        )
    title = next((v for k, v in policy["online_titles"].items() if k in game.name.lower()), "")
    if title:
        raise ViwoError("refused", f"online/competitive title: {title}", hint="no override")
    if sensitive:
        raise ViwoError("refused", f"terms-of-service-sensitive plugin: {', '.join(sensitive)}")
    if not confirmed:
        raise ViwoError("needs_decision", "confirm before capturing", hint=CONFIRMATION)
    return ["Go offline first if the game allows it; capture records what the game draws."]
