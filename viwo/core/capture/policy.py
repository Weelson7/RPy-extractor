"""Capture policy (doc 11.1, revised): checked before any launch. ViWo refuses nothing because
of what the game is. Anti-cheat, online titles and terms-of-service-sensitive plugins produce
warnings; the user confirms once (offline, own install, own responsibility) and the capture
runs. The only gate is the `capture` feature switch in the ini.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from viwo.contracts.errors import ViwoError

POLICY_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "capture_policy.json"
CONFIRMATION = (
    "my own install, intended for offline use; I am responsible for terms of service, "
    "anti-cheat consequences and anything I do with the captures"
)


def load_policy() -> dict:
    return json.loads(POLICY_FILE.read_text(encoding="utf-8"))


def _markers(game: Path, markers: dict[str, str]) -> list[str]:
    found = []
    for dirpath, dirnames, filenames in os.walk(game):
        for name in dirnames + filenames:
            if name.lower() in markers:
                found.append(f"{markers[name.lower()]} ({Path(dirpath, name).relative_to(game)})")
    return found


def warnings_for(game: Path, sensitive: list[str]) -> list[str]:
    """What the user should know before capturing this game (never a refusal)."""
    policy = load_policy()
    out = []
    found = _markers(game, policy["anti_cheat_markers"])
    if found:
        out.append(
            f"anti-cheat present: {'; '.join(found[:3])}. ViWo does not evade it: the capture may "
            "be blocked, and running a capture tool next to it can get an account banned"
        )
    title = next((v for k, v in policy["online_titles"].items() if k in game.name.lower()), "")
    if title:
        out.append(
            f"online/competitive title: {title}. Intended for offline use of your own install"
        )
    if sensitive:
        out.append(f"terms-of-service-sensitive plugin: {', '.join(sensitive)}")
    return out


def check(rt, game: Path, confirmed: bool, sensitive: list[str]) -> list[str]:
    """Raise only when capture is switched off or not confirmed; otherwise return warnings."""
    if "capture" not in rt.config.features:
        raise ViwoError(
            "refused", "runtime capture is off", hint="add capture to [startup] features in the ini"
        )
    warnings = warnings_for(game, sensitive)
    if not confirmed:
        raise ViwoError(
            "needs_decision",
            "confirm before capturing",
            hint=CONFIRMATION + "; " + "; ".join(warnings),
        )
    return warnings + [
        "Go offline first if the game allows it; capture records what the game draws."
    ]
