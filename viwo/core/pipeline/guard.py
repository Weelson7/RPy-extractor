"""Game-folder guard: extraction must never change the game (doc 0: the game folder is
read-only). ViWo writes only to staging, scratch and the workspace; this module refuses
layouts that would put those inside the game, and verifies the game afterwards.

`guarded` is the one way a writer gets the folder it writes into (doc 3.1 PREPARE): every
workspace, output folder and patched copy is handed out by it, after the guard ran. Without a
game path it compares the folder with the games it knows (`outside_games`): the games ViWo was
given (remembered in `viwo-data/games.json`), store installs by their own marks, patched copies."""

import json
import logging
from pathlib import Path

from viwo.contracts import workspace as ws
from viwo.contracts.errors import ViwoError

Snapshot = dict[str, tuple[int, int]]
PATCHED = ".viwo-patched"  # the marker of a patched copy (doc 18): a game one can run
KEEP = 1000  # games remembered, the most recent last
REGISTER: list[Path | None] = [None]  # where the games are remembered (set at boot)
STORE_MARKS = (".egstore", "goggame-*.info")  # an install's root: Epic, GOG
log = logging.getLogger("viwo.guard")


def guarded(game: Path | None, folder: Path, label: str = "workspace", temp=None) -> Path:
    """`folder`, once it is known not to put a write into the game. With the game known: not
    the game, not inside it, not holding it (`temp`, ViWo's temp folder, may hold it); the game
    is remembered for the runs that come without one. Without it (a run on a process id, a
    workspace tool): no game it knows (`outside_games`) and a folder that may be a game, as far
    as that can be told (see `_unowned`). No marker switches the guard off: a patched copy
    copied over the install, its marker included, is the game."""
    if game is None:
        outside_games(folder, label)
        _unowned(folder, label)
        return folder
    _contained(game, folder, label, holds=True)
    if temp is not None:
        _contained(game, temp, "temp folder", holds=False)
    _remember(game)
    return folder


def remember_in(path: Path | None) -> None:
    """Where the games ViWo is given are remembered (boot: `viwo-data/games.json`)."""
    REGISTER[0] = path


def known_games() -> list[Path]:
    """The game folders ViWo was given, as remembered; an unreadable record names none."""
    path = REGISTER[0]
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path else []
    except (OSError, ValueError):
        return []
    return [Path(p) for p in data if isinstance(p, str)] if isinstance(data, list) else []


def _remember(game: Path) -> None:
    """Add the game to the register. A "game" inside a ViWo workspace is ViWo's own output
    taken as a game (an analysis or a dump folder, doc 6.1): never remembered, or the
    workspace holding it would be refused."""
    from ..workspace import write_atomic

    path, key = REGISTER[0], str(game.resolve())
    if path is None or any(ws.has_marker(p) for p in game.resolve().parents):
        return
    known = [str(g) for g in known_games()]
    if key in known or not path.parent.is_dir():  # ViWo's data folder, made at boot, is gone
        return
    try:
        write_atomic(path, json.dumps((known + [key])[-KEEP:], indent=0))
    except OSError as exc:  # never silent; the run itself goes on
        log.warning("the game folder %s could not be remembered in %s: %s", game, path, exc)


def outside_games(folder: Path, label: str = "output folder") -> Path:
    """`folder`, once it is known to be no game the guard knows without being told, to lie in
    none and to hold none: a game ViWo was given (remembered), a store install (Steam's
    `steamapps`, an Epic or GOG install's root by its marks) or a patched copy among its
    parents. A game known by none of these cannot be told from the user's own folders."""
    register = REGISTER[0]
    for game in known_games():
        hint = f"choose a folder elsewhere; if {game} is no game, remove it from {register}"
        _contained(game, folder, label, holds=True, hint=hint)
    if why := _install(folder.resolve()):
        raise ViwoError(
            "refused",
            f"the {label} ({folder}) {why}; nothing is written there",
            hint="choose a location outside the game; ViWo never writes there",
        )
    return folder


def _install(folder: Path) -> str:
    """Why `folder` lies in a game install or holds one, "" when no mark says so."""
    if "steamapps" in (p.lower() for p in folder.parts) or (folder / "steamapps").is_dir():
        return "lies in or holds a Steam library (steamapps), where the games are installed"
    for at in (folder, *folder.parents):
        if (at / PATCHED).is_dir():
            where = "is" if at == folder else f"lies inside ({at})"
            return f"{where} a ViWo patched copy: a game that runs"
        try:
            marked = any(next(at.glob(mark), None) for mark in STORE_MARKS)
        except OSError:  # an unreadable parent says nothing either way
            marked = False
        if marked:
            return f"lies in a game install ({at} carries its store's marks)"
    return ""


def refuse_writes_inside(game: Path, **targets: Path) -> None:
    """Refuse a target inside the game, and one that holds the game: a workspace or copy that
    contains the game would have it in its groups, which "replace" clears."""
    for label, target in targets.items():
        _contained(game, target, label, holds=label != "temp_folder")


def _contained(game: Path, target: Path, label: str, holds: bool, hint: str = "") -> None:
    root, resolved = game.resolve(), target.resolve()
    where = "is the game folder" if resolved == root else "is inside the game folder"
    if resolved == root or root in resolved.parents:
        raise ViwoError(
            "refused",
            f"the {label} ({target}) {where} ({game})",
            hint=hint or "choose a location outside the game; ViWo never writes there",
        )
    if holds and resolved in root.parents:
        raise ViwoError(
            "refused",
            f"the game folder ({game}) is inside the {label} ({target})",
            hint=hint or f"choose a {label} that does not hold the game",
        )


def _unowned(folder: Path, label: str) -> None:
    """No game path to compare with, and no game the guard knows: a folder holding files of its
    own that is no ViWo workspace is refused (a game folder or the user's: ViWo cannot tell
    them apart)."""
    try:
        own = folder.is_dir() and any(not ws.is_reserved(p.name) for p in folder.iterdir())
    except OSError:  # unreadable: the write that follows fails and says why
        own = False
    if not own or ws.has_marker(folder):
        return
    raise ViwoError(
        "refused",
        f"the {label} ({folder}) holds files and is not a ViWo workspace: it may be a game "
        "folder; nothing is written into it",
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
