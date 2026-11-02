"""Where COLLECT reads from: game roots (copied), unpack/carve/export outputs (moved)."""

from __future__ import annotations

from pathlib import Path

from .collect import Source
from .probe import FolderProbe


def sources_for(run, chosen, moved: dict[Path, str], runs) -> list[Source]:
    """Game roots are copied; unpack, carve and export outputs are moved."""
    sources = _game_sources(run, chosen, claimed(run, runs))
    for folder, origin in moved.items():
        direct = origin.startswith("game:") and "!" not in origin  # one container deep
        kind, container = ("member", origin[5:]) if direct else ("derived", "")
        sources.append(Source(folder, True, origin, kind=kind, container=container))
    staging = run.work / "staging"
    return sources + [
        Source(staging / r.plugin_id, True, f"export:{r.backend}", kind="export")
        for r in runs
        if r.backend
    ]


def claimed(run, runs) -> frozenset[str]:
    """Suffixes/names a plugin handles (its exporter succeeded, or it has none and they are
    container parts): not carved, not copied raw."""
    plugins = run.rt.plugins
    decoded = [r for r in runs if r.backend or not plugins[r.plugin_id].export_slot()]
    return frozenset(s.lower() for r in decoded for s in plugins[r.plugin_id].claimed_suffixes())


def _game_sources(run, chosen: tuple[str, ...], exclude: frozenset[str]) -> list[Source]:
    probe = FolderProbe(run.game, limit=1)
    roots = {
        r.resolve() for pid in chosen for r in run.rt.plugins[pid].source_roots(run.game, probe)
    }
    outer = [r for r in roots if not any(o != r and o in r.parents for o in roots)]
    labels = {r: r.relative_to(run.game.resolve()).as_posix() for r in outer}
    return [
        Source(
            r,
            False,
            "game" if labels[r] == "." else f"game:{labels[r]}",
            exclude,
            kind="loose",
            prefix="" if labels[r] == "." else labels[r],
        )
        for r in sorted(outer)
    ]
