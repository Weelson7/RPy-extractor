"""Capture policy (doc 11.1, 1.1): checked before any launch. ViWo refuses nothing because of
what the game is. Anti-cheat markers in the folder, an anti-cheat service that is running,
online titles, terms-of-service-sensitive plugins and a reachable network produce warnings;
the user confirms once per game (own install, offline use, own responsibility) and the capture
runs. The only gate is the `capture` feature switch in the ini.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

from viwo.contracts.errors import ViwoError

from ..workspace import write_atomic

POLICY_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "capture_policy.json"
DEFAULT_AUTO = 30.0  # seconds; unattended by default (minimal-prompt rule): one frame, then stop

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


def running_processes(rt) -> set[str]:
    """Lowercase image names of the running processes, through the OS layer (principle 3)."""
    return rt.os.process.running_images() if rt is not None else set()


def network_reachable() -> bool:
    """Best effort: one short connection attempt; True when the network answers."""
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=0.8):
            return True
    except OSError:
        return False


def warnings_for(game: Path, sensitive: list[str], rt=None) -> list[str]:
    """What the user should know before capturing this game (never a refusal)."""
    policy = load_policy()
    out = []
    found = _markers(game, policy["anti_cheat_markers"])
    if found:
        out.append(
            f"anti-cheat present: {'; '.join(found[:3])}. ViWo does not evade it: the capture may "
            "be blocked, and running a capture tool next to it can get an account banned"
        )
    services = policy.get("anti_cheat_services", {})
    running = sorted(services[n] for n in running_processes(rt) if n in services)
    if running:
        out.append(f"anti-cheat service running now: {', '.join(running)}")
    title = next((v for k, v in policy["online_titles"].items() if k in game.name.lower()), "")
    if title:
        out.append(
            f"online/competitive title: {title}. Intended for offline use of your own install"
        )
    if sensitive:
        out.append(f"terms-of-service-sensitive plugin: {', '.join(sensitive)}")
    if rt is not None and network_reachable():
        out.append("the network is reachable: go offline before launching if the game allows it")
    return out


def _confirmations(rt) -> Path:
    return rt.temp_root.parent / "capture" / "confirmed.json"


def confirmed_games(rt) -> set[str]:
    path = _confirmations(rt)
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def remember(rt, game: Path) -> None:
    """The confirmation holds once per game (doc 11.1): recorded next to the capture journals."""
    path = _confirmations(rt)
    path.parent.mkdir(parents=True, exist_ok=True)
    games = sorted(confirmed_games(rt) | {str(game.resolve())})
    write_atomic(path, json.dumps(games, indent=2))


def check(rt, game: Path, confirmed: bool, sensitive: list[str]) -> list[str]:
    """Raise only when capture is switched off or not yet confirmed for this game; otherwise
    return the warnings. A confirmation given once is remembered for that game folder."""
    if "capture" not in rt.config.features:
        raise ViwoError(
            "refused", "runtime capture is off", hint="add capture to [startup] features in the ini"
        )
    warnings = warnings_for(game, sensitive, rt)
    if confirmed:
        remember(rt, game)
    elif str(game.resolve()) not in confirmed_games(rt):
        raise ViwoError(
            "needs_decision",
            "confirm before capturing",
            hint=CONFIRMATION + "; " + "; ".join(warnings),
        )
    return warnings + [
        "Go offline first if the game allows it; capture records what the game draws."
    ]
