"""Legacy group-trash API, now served by viwo.core.curation (three trash layouts)."""
from pathlib import Path
from typing import Callable

from viwo.api.legacy import locked
from viwo.core.curation import trash

Progress = Callable[[str], None] | None


def list_kept_files(assets_dir: Path) -> dict[str, int]:
    return trash.kept(assets_dir)


def list_all_extensions(assets_dir: Path) -> list[str]:
    return trash.all_extensions(assets_dir)


def get_summary(assets_dir: Path) -> dict:
    return trash.summary(assets_dir)


def _group_op(kind: str, op, assets_dir: Path, ext_folder: str, progress: Progress) -> dict:
    def run() -> dict:
        ok, message = op(assets_dir, ext_folder)
        if progress:
            progress(message)
        result = {"success": ok, "message": message, "type": kind, "folder": ext_folder,
                  "logs": [message]}
        if ok:
            result["summary"] = trash.summary(assets_dir)
        return result

    return locked(assets_dir, run)


def move_extension_to_trash(assets_dir: Path, ext_folder: str, progress: Progress = None) -> dict:
    return _group_op("move_to_trash", trash.trash_group, assets_dir, ext_folder, progress)


def restore_extension_from_trash(assets_dir: Path, ext_folder: str, progress: Progress = None) -> dict:
    return _group_op("restore_from_trash", trash.restore_group, assets_dir, ext_folder, progress)


def delete_extension_from_trash(assets_dir: Path, ext_folder: str, progress: Progress = None) -> dict:
    return _group_op("delete_from_trash", trash.delete_group, assets_dir, ext_folder, progress)


def clear_all_trash(assets_dir: Path, progress: Progress = None) -> dict:
    def run() -> dict:
        count, logs = trash.clear(assets_dir)
        for line in logs:
            if progress:
                progress(line)
        return {"success": True, "type": "clear_all_trash", "cleared": count, "logs": logs,
                "summary": trash.summary(assets_dir)}

    return locked(assets_dir, run)
