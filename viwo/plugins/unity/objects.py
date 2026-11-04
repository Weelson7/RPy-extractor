"""Everything else a Unity game holds (doc 16.0c): video clips, fonts and shaders in their own
formats, and every other object (scenes, prefabs, materials, animations, game objects and their
components, MonoBehaviour data) as JSON from its type tree, one file per serialized file. A
MonoBehaviour whose script layout the build stripped is listed with its script and counted; the
layouts come from the game's managed assemblies when they ship (Mono) or are given."""

from __future__ import annotations

import json
from pathlib import Path

from viwo.contracts import workspace as ws

FONT_EXT = {b"OTTO": ".otf", b"true": ".ttf", b"\x00\x01\x00\x00": ".ttf", b"ttcf": ".ttc"}
BLOB = 4096  # raw byte fields above this size are summarised, not inlined as hex


def _plain(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return raw.hex() if len(raw) <= BLOB else f"<{len(raw)} bytes>"
    return str(value)


def media(ctx, kind: str, data, obj, name: str) -> Path | None:
    """VideoClip -> its original file, Font -> .ttf/.otf, Shader -> readable source; None when
    the object holds nothing to write."""
    folder = ctx.staging / {"VideoClip": "video", "Font": "font", "Shader": "shader"}[kind]
    if kind == "VideoClip":
        from UnityPy.helpers.ResourceReader import get_resource_data

        res = data.m_ExternalResources
        if not res.m_Size:
            return None
        payload = get_resource_data(res.m_Source, obj.assets_file, res.m_Offset, res.m_Size)
        ext = Path(str(data.m_OriginalPath or "")).suffix.lower() or ".mp4"
    elif kind == "Font":
        payload = bytes(data.m_FontData or b"")
        if not payload:
            return None
        ext = FONT_EXT.get(payload[:4], ".ttf")
    else:
        payload, ext = data.export().encode("utf-8"), ".shader"
    folder.mkdir(parents=True, exist_ok=True)
    target = ws.next_free(folder / f"{name}{ext}")
    target.write_bytes(bytes(payload))
    return target


class Dump:
    """One JSON array per serialized file, written as the objects come (a scene holds hundreds
    of thousands): `data/<file>.objects.json`. Counts what had no layout."""

    def __init__(self, staging: Path) -> None:
        self.folder = staging / "data"
        self.files: dict[str, object] = {}
        self.written = 0
        self.no_layout: dict[str, int] = {}

    def add(self, obj, kind: str) -> None:
        source = Path(str(getattr(obj.assets_file, "name", "") or "unknown")).name
        try:
            entry = {"path_id": obj.path_id, "type": kind, "data": obj.read_typetree()}
        except Exception as exc:  # noqa: BLE001  (a stripped layout, or damage: listed, counted)
            self.no_layout[kind] = self.no_layout.get(kind, 0) + 1
            entry = {"path_id": obj.path_id, "type": kind, "unread": str(exc)[:160]}
        fh = self.files.get(source)
        if fh is None:
            self.folder.mkdir(parents=True, exist_ok=True)
            fh = open(ws.next_free(self.folder / f"{source}.objects.json"), "w", encoding="utf-8")
            fh.write("[\n")
            self.files[source] = fh
        else:
            fh.write(",\n")
        fh.write(json.dumps(entry, default=_plain, ensure_ascii=False))
        self.written += 1

    def close(self) -> tuple[str, list[str]]:
        """Finish every file: (what was dumped, for the log; the objects without a layout)."""
        for fh in self.files.values():
            fh.write("\n]\n")
            fh.close()
        summary = f"{self.written} object(s) as JSON in {len(self.files)} file(s) (data/)"
        notes = []
        for kind, n in sorted(self.no_layout.items()):
            mono = kind == "MonoBehaviour"
            why = "their script layout is not in the build" if mono else "unreadable"
            notes.append(f"{n} {kind}(s) listed without their fields: {why}")
        return (summary if self.written else ""), notes


def layouts(env, game_root: Path) -> str:
    """Give UnityPy the MonoBehaviour layouts from the game's managed assemblies (Mono builds),
    or from stand-in assemblies beside them; "" when set, else why not."""
    managed = next(iter(sorted(game_root.glob("*_Data/Managed"))), None)
    if managed is None or not any(managed.glob("*.dll")):
        return "no managed assemblies (IL2CPP): MonoBehaviour fields need Cpp2IL's stand-ins"
    try:
        from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

        versions = (str(getattr(o.assets_file, "unity_version", "") or "") for o in env.objects)
        version = next((v for v in versions if v and v[0].isdigit()), "")
        if not version:
            return "MonoBehaviour layouts unavailable: no Unity version in these files"
        generator = TypeTreeGenerator(version)
        generator.load_local_dll_folder(str(managed))
    except Exception as exc:  # noqa: BLE001  (the generator is optional; say why it is absent)
        return f"MonoBehaviour layouts unavailable: {str(exc)[:120]}"
    env.typetree_generator = generator
    return ""
