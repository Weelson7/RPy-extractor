"""Game-folder guard: extraction must never change the game (doc 0: the game folder is
read-only). ViWo writes only to staging, scratch and the workspace; this module refuses
layouts that would put those inside the game, and verifies the game afterwards.

`guarded` is the one way a writer gets the folder it writes into (doc 3.1 PREPARE): every
workspace, output folder and patched copy is handed out by it, after the guard ran."""

from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError

Snapshot = dict[str, tuple[int, int]]
PATCHED = ".viwo-patched"  # the marker of a patched copy (doc 18): a game one can run


def guarded(game: Path | None, folder: Path, label: str = "workspace", temp=None) -> Path:
    """`folder`, once it is known not to put a write into the game. With the game known: not
    the game, not inside it, not holding it (`temp`, ViWo's temp folder, may hold it). Without
    it (a run on a process id): a folder that may be a game, as far as that can be told (see
    `_unowned`). No marker switches the guard off: a patched copy copied over the install, its
    marker included, is the game."""
    if game is None:
        _unowned(folder, label)
        return folder
    _contained(game, folder, label, holds=True)
    if temp is not None:
        _contained(game, temp, "temp folder", holds=False)
    return folder


def refuse_writes_inside(game: Path, **targets: Path) -> None:
    """Refuse a target inside the game, and one that holds the game: a workspace or copy that
    contains the game would have it in its groups, which "replace" clears."""
    for label, target in targets.items():
        _contained(game, target, label, holds=label != "temp_folder")


def _contained(game: Path, target: Path, label: str, holds: bool) -> None:
    root, resolved = game.resolve(), target.resolve()
    where = "is the game folder" if resolved == root else "is inside the game folder"
    if resolved == root or root in resolved.parents:
        raise ViwoError(
            "refused",
            f"the {label} ({target}) {where}",
            hint="choose a location outside the game; ViWo never writes there",
        )
    if holds and resolved in root.parents:
        raise ViwoError(
            "refused",
            f"the game folder ({game}) is inside the {label} ({target})",
            hint=f"choose a {label} that does not hold the game",
        )


def _unowned(folder: Path, label: str) -> None:
    """No game path to compare with: a patched copy (a game that runs) is refused, and so is a
    folder holding files of its own that is no ViWo workspace (a game folder or the user's:
    ViWo cannot tell them apart). What this cannot catch: a new or empty folder inside a game,
    a folder above one, a game folder that carries a ViWo workspace marker."""
    try:
        own = folder.is_dir() and any(not ws.is_reserved(p.name) for p in folder.iterdir())
    except OSError:  # unreadable: the write that follows fails and says why
        own = False
    if (folder / PATCHED).is_dir():
        why = "is a ViWo patched copy: a game that runs"
    elif own and not ws.has_marker(folder):
        why = "holds files and is not a ViWo workspace: it may be a game folder"
    else:
        return
    raise ViwoError(
        "refused",
        f"the {label} ({folder}) {why}; nothing is written into it",
        hint="without the game's path ViWo cannot tell a game from your files: give an empty "
        "folder or a ViWo workspace (extract into it first, or convert it into one)",
    )


def snapshot(game: Path) -> Snapshot:
    """Cheap fingerprint of every file: relative path -> (size, mtime in ns)."""
    found: Snapshot = {}
    for dirpath, _, filenames in ws.walk(game):
        for name in filenames:
            path = Path(dirpath) / name
            try:
                st = path.stat()
            except OSError:
                continue
            found[path.relative_to(game).as_posix()] = (st.st_size, st.st_mtime_ns)
    return found


def changes(before: Snapshot, after: Snapshot) -> list[str]:
    keys = set(before) | set(after)
    return sorted(k for k in keys if before.get(k) != after.get(k))


def change_warning(before: Snapshot, after: Snapshot, during: str) -> str:
    """ "GAME FOLDER CHANGED during <x>: ..." naming what vanished (an antivirus quarantine
    removes files; ViWo never writes there), or "" when nothing changed."""
    touched = changes(before, after)
    if not touched:
        return ""
    gone = [t for t in touched if t in before and t not in after]
    text = f"GAME FOLDER CHANGED during {during}: {', '.join(touched[:10])}"
    if gone:
        text += f" ({len(gone)} removed by someone else, e.g. an antivirus: {', '.join(gone[:5])})"
    return text
