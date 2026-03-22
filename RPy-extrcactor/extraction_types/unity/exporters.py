"""Unity export backends and tool adapters."""
import re
import shutil
from pathlib import Path
from typing import Callable

from extraction import run

from .discovery import scan_unity_containers


def create_deterministic_output_tree(base_dir: Path) -> None:
    """Create standardized output directory tree for all media types."""
    media_dirs = ["images", "audio", "video", "models", "animations", "materials", "text"]

    for media_dir in media_dirs:
        (base_dir / media_dir).mkdir(parents=True, exist_ok=True)


def _safe_name(raw_name: str, fallback: str) -> str:
    candidate = (raw_name or "").strip()
    if not candidate:
        candidate = fallback
    candidate = re.sub(r"[\\/:*?\"<>|]+", "_", candidate)
    candidate = candidate.replace("\x00", "").strip(" .")
    return candidate or fallback


def _next_available(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    idx = 1
    while True:
        candidate = path.with_name(f"{stem}__{idx}{suffix}")
        if not candidate.exists():
            return candidate
        idx += 1


def _ext_selected(selected_exts: set[str] | None, ext: str) -> bool:
    if selected_exts is None:
        return True
    return ext.lower() in selected_exts


def find_external_tool(candidates: tuple[str, ...]) -> str | None:
    """Return first available executable path in PATH."""
    for name in candidates:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


def export_unitypy_assets(
    game_root: Path,
    output_dir: Path,
    selected_exts: set[str] | None,
    progress: Callable[[str], None] | None,
) -> tuple[int, list[dict], dict[str, int], list[str]]:
    """Export Unity assets using UnityPy when available."""
    exported_assets: list[dict] = []
    logs: list[str] = []
    by_type = {
        "image": 0,
        "audio": 0,
        "text": 0,
        "model": 0,
    }

    try:
        import UnityPy  # type: ignore
    except Exception as exc:
        logs.append(f"[UNITY] UnityPy unavailable: {exc}")
        return 0, exported_assets, by_type, logs

    containers = scan_unity_containers(game_root, progress)
    if progress:
        progress(f"[UNITY] UnityPy export scanning {len(containers)} container(s)")

    exported_count = 0
    output_base = Path(output_dir)
    images_dir = output_base / "images"
    audio_dir = output_base / "audio"
    text_dir = output_base / "text"
    models_dir = output_base / "models"
    images_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    for container in containers:
        try:
            env = UnityPy.load(str(container))
        except Exception as exc:
            logs.append(f"[UNITY] Failed to load container {container.name}: {exc}")
            continue

        for obj in env.objects:
            try:
                obj_type = getattr(getattr(obj, "type", None), "name", str(getattr(obj, "type", "Unknown")))
                data = obj.read()
                base_name = _safe_name(
                    str(getattr(data, "name", "") or ""),
                    f"{container.stem}_{getattr(obj, 'path_id', 'obj')}",
                )

                if obj_type in {"Texture2D", "Sprite"}:
                    image = getattr(data, "image", None)
                    if image is None:
                        continue
                    ext = ".png"
                    if not _ext_selected(selected_exts, ext):
                        continue
                    out_path = _next_available(images_dir / f"{base_name}{ext}")
                    image.save(out_path)
                    exported_assets.append({"name": out_path.name, "class_name": obj_type})
                    by_type["image"] += 1
                    exported_count += 1
                    continue

                if obj_type == "AudioClip":
                    samples = getattr(data, "samples", None)
                    wrote_audio = False
                    if isinstance(samples, dict):
                        for sample_name, sample_bytes in samples.items():
                            sample_ext = Path(sample_name).suffix.lower() or ".wav"
                            if not _ext_selected(selected_exts, sample_ext):
                                continue
                            out_name = _safe_name(Path(sample_name).stem, base_name)
                            out_path = _next_available(audio_dir / f"{out_name}{sample_ext}")
                            out_path.write_bytes(sample_bytes)
                            exported_assets.append({"name": out_path.name, "class_name": obj_type})
                            by_type["audio"] += 1
                            exported_count += 1
                            wrote_audio = True

                    if not wrote_audio:
                        raw_audio = getattr(data, "m_AudioData", b"") or b""
                        if raw_audio:
                            ext = ".bytes"
                            if _ext_selected(selected_exts, ext):
                                out_path = _next_available(audio_dir / f"{base_name}{ext}")
                                out_path.write_bytes(raw_audio)
                                exported_assets.append({"name": out_path.name, "class_name": obj_type})
                                by_type["audio"] += 1
                                exported_count += 1
                    continue

                if obj_type == "TextAsset":
                    script = getattr(data, "script", b"")
                    ext = ".txt"
                    if not _ext_selected(selected_exts, ext):
                        continue
                    out_path = _next_available(text_dir / f"{base_name}{ext}")
                    if isinstance(script, str):
                        out_path.write_text(script, encoding="utf-8", errors="replace")
                    else:
                        out_path.write_bytes(bytes(script))
                    exported_assets.append({"name": out_path.name, "class_name": obj_type})
                    by_type["text"] += 1
                    exported_count += 1
                    continue

                if obj_type == "Mesh":
                    ext = ".obj"
                    if not _ext_selected(selected_exts, ext):
                        continue
                    exporter = getattr(data, "export", None)
                    if not callable(exporter):
                        continue
                    exported_mesh = exporter()
                    if isinstance(exported_mesh, str) and exported_mesh.strip():
                        out_path = _next_available(models_dir / f"{base_name}{ext}")
                        out_path.write_text(exported_mesh, encoding="utf-8", errors="replace")
                        exported_assets.append({"name": out_path.name, "class_name": obj_type})
                        by_type["model"] += 1
                        exported_count += 1
                    continue
            except Exception as exc:
                logs.append(f"[UNITY] Object export failure in {container.name}: {exc}")

    logs.append(
        "[UNITY] UnityPy export summary: "
        f"images={by_type['image']}, audio={by_type['audio']}, text={by_type['text']}, models={by_type['model']}"
    )
    return exported_count, exported_assets, by_type, logs


def export_with_external_tool(
    tool_label: str,
    executable: str,
    game_root: Path,
    output_dir: Path,
    progress: Callable[[str], None] | None,
) -> tuple[int, list[str], str]:
    """Run external Unity extraction tool and count produced files."""
    logs: list[str] = []
    export_dir = output_dir / f"{tool_label.lower()}_export"
    export_dir.mkdir(parents=True, exist_ok=True)

    command_variants = [
        [executable, str(game_root), str(export_dir)],
        [executable, "--input", str(game_root), "--output", str(export_dir)],
        [executable, "-i", str(game_root), "-o", str(export_dir)],
    ]

    for cmd in command_variants:
        code, _, _ = run(cmd)
        if code != 0:
            logs.append(f"[{tool_label}] command failed ({code}): {' '.join(cmd)}")
            continue

        exported_count = sum(1 for p in export_dir.rglob("*") if p.is_file())
        if exported_count > 0:
            if progress:
                progress(f"[{tool_label}] Exported {exported_count} file(s) to {export_dir}")
            logs.append(f"[{tool_label}] export succeeded with {exported_count} file(s)")
            return exported_count, logs, str(export_dir)

        logs.append(f"[{tool_label}] command returned success but no files were exported")

    return 0, logs, str(export_dir)
