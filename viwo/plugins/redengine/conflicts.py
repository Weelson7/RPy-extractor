"""Mod-over-base archive conflicts (doc 16.0c): which members the installed mods replace in the
game's own archives, and which members more than one mod carries (the first archive by name in
`archive/pc/mod` wins, REDmod's `mods/<name>/archives` come after). Only the indexes are read."""

import struct
from pathlib import Path

from .rdar import Archive

BASE = (("archive", "pc", "content"), ("archive", "pc", "ep1"))
EXAMPLES = 3  # members named per finding


def archives(game: Path) -> tuple[list[Path], list[Path]]:
    """(base archives, mod archives in load order)."""
    base = [p for parts in BASE for p in sorted(game.joinpath(*parts).glob("*.archive"))]
    mods = sorted(game.joinpath("archive", "pc", "mod").glob("*.archive"), key=lambda p: p.name)
    mods += sorted(game.glob("mods/*/archives/*.archive"))
    return base, mods


def hashes(path: Path) -> set[int] | None:
    try:
        with open(path, "rb") as fh:
            return {entry.name_hash for entry in Archive(fh).entries()}
    except (OSError, ValueError, struct.error):
        return None


def report(game: Path, name=lambda h: f"{h:016x}") -> list[str]:
    """One line per finding; empty when no mod is installed."""
    base_files, mod_files = archives(game)
    if not mod_files:
        return []
    base, unread = set(), []
    for path in base_files:
        found = hashes(path)
        base |= found if found is not None else set()
        unread += [path.name] if found is None else []
    winner: dict[int, str] = {}
    shadowed: list[tuple[int, str, str]] = []
    for path in mod_files:
        found = hashes(path)
        if found is None:
            unread.append(path.name)
            continue
        for h in sorted(found):
            if h in winner:
                shadowed.append((h, path.name, winner[h]))
            else:
                winner[h] = path.name
    replaced = len(winner.keys() & base)
    lines = [
        f"mods: {len(mod_files)} archive(s) replace {replaced} member(s) of the game's archives"
    ]
    if shadowed:
        e_g = "; ".join(
            f"{name(h)} in {lost} (loses to {won})" for h, lost, won in shadowed[:EXAMPLES]
        )
        lines.append(f"mods: {len(shadowed)} member(s) carried by more than one mod, e.g. {e_g}")
    if unread:
        lines.append(f"mods: {len(unread)} archive(s) could not be read: {', '.join(unread[:5])}")
    return lines
