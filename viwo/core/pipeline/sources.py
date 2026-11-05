"""Where COLLECT reads from: game roots (copied), unpack/carve/export outputs (moved)."""

import json
from pathlib import Path

from viwo.contracts import workspace as ws

from .collect import Source
from .probe import FolderProbe


def sources_for(run, chosen, moved: dict[Path, str], runs) -> list[Source]:
    """Game roots are copied; unpack, carve and export outputs are moved."""
    sources = _game_sources(run, chosen, claimed(run, runs))
    for folder, origin in moved.items():
        direct = origin.startswith("game:") and "!" not in origin  # one container deep
        kind, container = ("member", origin[5:]) if direct else ("derived", "")
        names = ws.renamed(folder)
        sources.append(Source(folder, True, origin, kind=kind, container=container, renamed=names))
    staging = run.work / "staging"
    return sources + [
        Source(
            staging / r.plugin_id,
            True,
            f"export:{r.backend}",
            # an engine found inside a wrapper (doc 3.1) mapped paths in the unpacked wrapper,
            # not in the game: no container to write back to, so derived, never misplaced
            kind="export" if r.plugin_id in chosen else "derived",
            mapped=_export_map(staging / r.plugin_id, r.plugin_id) if r.plugin_id in chosen else {},
        )
        for r in runs
        if r.backend
    ]


def _export_map(folder: Path, plugin_id: str) -> dict:
    """Exporters may record which game container and member each exported file came from."""
    path = folder / ws.EXPORT_MAP
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except ValueError:
        return {}
    return {rel: [str(c), str(m), plugin_id] for rel, (c, m) in raw.items()}


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
