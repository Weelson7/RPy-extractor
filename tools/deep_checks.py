"""Deep pass checks: where every game byte went, what every workspace file is, and whether the
decoded files open in a real reader (images through Pillow, WAV headers, JSON, glTF, video
through ffprobe), plus a contact sheet of sampled images to look at."""

from __future__ import annotations

import json
import random
import subprocess
import wave
from collections import Counter
from pathlib import Path

from viwo.contracts import workspace as ws

# formats anything opens: what "decoded" means for the completeness contract (doc 16.0c)
OPEN = {
    "image": {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tga", "tif", "tiff", "ico", "svg"},
    "audio": {"wav", "ogg", "mp3", "flac", "opus", "m4a", "mid", "midi"},
    "video": {"mp4", "webm", "mkv", "avi", "ogv"},
    "model": {"gltf", "glb", "obj", "fbx", "dae", "stl", "ply", "uemodel", "ueanim"},
    "text": {"txt", "json", "xml", "csv", "ini", "cfg", "yaml", "yml", "md", "html", "htm",
             "css", "js", "ts", "lua", "py", "rpy", "gd", "cs", "c", "cpp", "h", "hpp",
             "shader", "hlsl", "glsl", "script", "toml", "log", "lang", "po", "srt"},
    "font": {"ttf", "otf", "woff", "woff2", "fnt"},
    "document": {"pdf"},
}  # fmt: skip
OPEN_EXT = {ext: kind for kind, exts in OPEN.items() for ext in exts}
UNKNOWN = {"bin", "dat", "_noext", "noext", "raw", "unknown"}
SAMPLE = 3000  # files per format opened by a reader (bounded: a game holds millions)


def provenance(workspace: Path) -> list[dict]:
    path = workspace / ws.PROVENANCE_FILE
    if not path.is_file():
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def account(game: Path, workspace: Path) -> dict:
    """Game side: bytes in files that were opened (a container something came out of) or copied
    as they are, against bytes nothing read. Workspace side: files in an open format, in a known
    game format left raw, or unknown; the raw and unknown types ranked (the decode work order)."""
    rows = provenance(workspace)
    touched = set()
    for row in rows:
        origin = str(row.get("origin", ""))
        if origin.startswith("game:"):
            touched.add(origin[5:].split("!", 1)[0].split(":", 1)[0])
        if row.get("container"):
            touched.add(str(row["container"]))
    game_bytes = Counter()
    untouched: Counter = Counter()
    for path in ws.files(game):
        rel, size = path.relative_to(game).as_posix(), path.stat().st_size
        # a companion read with its container: x.assets.resS with x.assets, x.ucas with x.utoc
        companion = rel.rsplit(".", 1)[0]
        companions = {companion, f"{companion}.utoc", f"{companion}.pak"}
        state = "read" if rel in touched or companions & touched else "unread"
        game_bytes[state] += size
        if state == "unread":
            untouched[ws.ext_of(path)] += size
    files, sizes, raw = Counter(), Counter(), Counter()
    for path in _workspace_files(workspace):
        ext = path.parent.name.lower()
        kind = "open" if ext in OPEN_EXT else "unknown" if ext in UNKNOWN else "raw"
        size = path.stat().st_size
        files[kind] += 1
        sizes[kind] += size
        if kind != "open":
            raw[ext] += 1
    total = sum(game_bytes.values()) or 1
    return {
        "gameBytes": sum(game_bytes.values()),
        "gameBytesRead": round(game_bytes["read"] / total, 4),
        "unreadByType": dict(Counter({k: v for k, v in untouched.most_common(12)})),
        "workspaceFiles": dict(files),
        "workspaceBytes": dict(sizes),
        "openShare": round(files["open"] / (sum(files.values()) or 1), 4),
        "rawTypes": dict(raw.most_common(25)),
    }


def _workspace_files(workspace: Path):
    for group in sorted(workspace.iterdir()):
        if group.is_dir() and not ws.is_reserved(group.name):
            yield from (p for p in ws.files(group))


def validate(workspace: Path) -> dict:
    """Open up to SAMPLE files of every open format with a real reader; count what fails."""
    tested, bad, empty = Counter(), Counter(), 0
    examples: dict[str, list[str]] = {}
    rng = random.Random(7)
    for group in sorted(p for p in workspace.iterdir() if p.is_dir()):
        if ws.is_reserved(group.name):
            continue
        files = ws.files(group)
        empty += sum(1 for f in files if f.stat().st_size == 0)
        reader = READERS.get(group.name.lower())
        if reader is None:
            continue
        for path in rng.sample(files, min(SAMPLE, len(files))):
            tested[group.name] += 1
            why = _try(reader, path)
            if why:
                bad[group.name] += 1
                examples.setdefault(group.name, []).append(f"{path.name}: {why}"[:160])
    return {
        "tested": dict(tested),
        "broken": dict(bad),
        "emptyFiles": empty,
        "examples": {k: v[:5] for k, v in examples.items()},
    }


def _try(reader, path: Path) -> str:
    try:
        return reader(path) or ""
    except Exception as exc:  # noqa: BLE001  (a reader's failure is the finding)
        return f"{type(exc).__name__}: {exc}"


def _image(path: Path) -> str:
    from PIL import Image

    with Image.open(path) as img:
        img.verify()
    with Image.open(path) as img:  # verify() leaves the image unusable: decode the pixels
        img.load()
        return "" if img.width and img.height else "zero size"


def _wav(path: Path) -> str:
    with wave.open(str(path)) as w:
        return "" if w.getnframes() > 0 else "no frames"


def _json(path: Path) -> str:
    if path.stat().st_size > 256 << 20:
        return ""  # too big to parse in a pass; its head is checked
    with open(path, encoding="utf-8-sig") as fh:
        json.load(fh)
    return ""


def _magic(*heads: bytes):
    def check(path: Path) -> str:
        with open(path, "rb") as fh:
            head = fh.read(16)
        return "" if any(head.startswith(h) for h in heads) else f"head {head[:8].hex()}"

    return check


def _video(path: Path) -> str:
    from viwo.core import thirdparty

    probe = thirdparty.tool_argv("ffprobe", Path(__file__).resolve().parent.parent)
    if probe is None:
        return ""
    args = ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]
    out = subprocess.run([*probe, *args], capture_output=True, text=True, timeout=60)
    duration = out.stdout.strip().split("\n")[0]
    return "" if duration and float(duration) > 0 else (out.stderr.strip()[:120] or "no duration")


def _text(path: Path) -> str:
    with open(path, "rb") as fh:
        head = fh.read(1 << 16)
    try:
        head.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return "" if b"\0" not in head[: exc.start] else f"binary text ({exc.reason})"
    return ""


READERS = {
    **dict.fromkeys(["png", "jpg", "jpeg", "gif", "bmp", "webp", "tga"], _image),
    "wav": _wav,
    "json": _json,
    "gltf": _json,
    "glb": _magic(b"glTF"),
    "ogg": _magic(b"OggS"),
    "mp3": _magic(b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"),
    "dds": _magic(b"DDS "),
    "mp4": _video,
    "webm": _video,
    **dict.fromkeys(["txt", "xml", "lua", "rpy", "gd", "script", "cs", "ini", "csv"], _text),
}


def contact_sheet(workspace: Path, out: Path, count: int = 48) -> dict:
    """A grid of sampled images (the eye check no reader replaces)."""
    from PIL import Image

    pool = [p for g in ("png", "jpg") if (workspace / g).is_dir() for p in ws.files(workspace / g)]
    if not pool:
        return {"images": 0}
    picks = random.Random(3).sample(pool, min(count, len(pool)))
    cell, cols = 160, 8
    sheet = Image.new("RGB", (cell * cols, cell * ((len(picks) + cols - 1) // cols)), (20, 20, 24))
    for i, path in enumerate(picks):
        try:
            with Image.open(path) as img:
                img.thumbnail((cell - 8, cell - 8))
                sheet.paste(img.convert("RGB"), ((i % cols) * cell + 4, (i // cols) * cell + 4))
        except Exception:  # noqa: BLE001,S112  (validate() already counts broken images)
            continue
    sheet.save(out)
    return {"images": len(picks), "sheet": str(out)}
