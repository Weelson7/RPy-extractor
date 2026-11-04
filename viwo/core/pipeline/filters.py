"""The extension filter (doc 3.2) on what ends up in the workspace: a source that a decoder
turns into a chosen type is collected and decoded, then the files of types not chosen are
left out; what the filter left out is said."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from viwo.contracts import workspace as ws


def widened(run, selected: frozenset[str] | None) -> frozenset[str] | None:
    """The chosen extensions plus every suffix a bound decoder of this run reads."""
    if selected is None:
        return None
    from ..decode import _wanted

    return selected | frozenset(_wanted(run, run.ctx("core").options))


def prune(run, workspace: Path, collected, selected: frozenset[str] | None) -> list[str]:
    """Remove the decoded sources of types not chosen; returns the warning lines."""
    if selected is None:
        return []
    groups = {ws.ext_folder(ext) for ext in selected}
    dropped: Counter = Counter()
    kept = []
    for row in collected.provenance:
        group = row["path"].split("/", 1)[0]
        if group in groups:
            kept.append(row)
            continue
        target = workspace / row["path"]
        if target.is_file():
            target.unlink()
            dropped[group] += 1
    collected.provenance[:] = kept
    for group, count in dropped.items():
        collected.by_ext[group] -= count
        _remove_empty(workspace / group)
    collected.by_ext = +collected.by_ext  # groups that reached zero are gone
    left = collected.skipped_by_ext + dropped
    if not left:
        return []
    top = ", ".join(f"{g} {n}" for g, n in left.most_common(8))
    line = f"extension filter: {sum(left.values())} file(s) of other types left out ({top})"
    run.log(line, "collect")
    return [line]


def _remove_empty(folder: Path) -> None:
    if folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
