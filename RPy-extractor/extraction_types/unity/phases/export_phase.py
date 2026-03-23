"""Unity export phase."""
from pathlib import Path
from typing import Callable

from extraction_core import log_append
from extraction_types.unity.exporters import (
    create_deterministic_output_tree,
    export_unitypy_assets,
    find_external_tool,
    export_with_external_tool,
)


def run_export_phase(
    game_root: Path,
    output_dir: Path,
    selected_exts: set[str] | None,
    progress: Callable[[str], None] | None,
    logs: list[str],
) -> tuple[int, list[dict], dict[str, int], bool, str | None]:
    """Run Unity-specific exporters and optional external fallbacks."""
    if progress:
        progress("[UNITY:EXPORT] Creating deterministic output tree")

    try:
        create_deterministic_output_tree(Path(output_dir))
        log_append(logs, "[EXPORT] Output tree created", progress)
    except Exception as exc:
        log_append(logs, f"[EXPORT] Output tree creation failed: {exc}", progress)

    if progress:
        progress("[UNITY:EXPORT] Running UnityPy extraction")

    unity_available = True
    try:
        import UnityPy  # type: ignore  # noqa: F401
    except Exception:
        unity_available = False

    if not unity_available:
        log_append(logs, "[EXPORT] UnityPy is not installed", progress)
        return 0, [], {"image": 0, "audio": 0, "text": 0, "model": 0, "assetripper": 0, "uabea": 0}, False, "Unity extraction requires UnityPy. Install with: python -m pip install UnityPy"

    unity_export_count, unity_exported_assets, unity_export_by_type, unity_logs = export_unitypy_assets(
        game_root=game_root,
        output_dir=output_dir,
        selected_exts=selected_exts,
        progress=progress,
    )
    logs.extend(unity_logs)
    log_append(logs, f"[EXPORT] UnityPy exported {unity_export_count} asset(s)", progress)

    unity_export_by_type["assetripper"] = 0
    unity_export_by_type["uabea"] = 0

    assetripper_exe = find_external_tool(("AssetRipper.Console", "AssetRipper.Console.exe", "AssetRipper"))
    if assetripper_exe:
        ripper_count, ripper_logs, ripper_output = export_with_external_tool(
            tool_label="ASSETRIPPER",
            executable=assetripper_exe,
            game_root=game_root,
            output_dir=Path(output_dir),
            progress=progress,
        )
        logs.extend(ripper_logs)
        unity_export_by_type["assetripper"] = ripper_count
        if ripper_count > 0:
            unity_export_count += ripper_count
            unity_exported_assets.append({"name": Path(ripper_output).name, "class_name": "AssetRipperExport"})
    else:
        log_append(logs, "[ASSETRIPPER] Not found in PATH (optional fallback)", progress)

    uabea_exe = find_external_tool(("UABEAvalonia", "UABEAvalonia.exe", "UABEA", "UABEA.exe", "uabea-cli"))
    if uabea_exe:
        uabea_count, uabea_logs, uabea_output = export_with_external_tool(
            tool_label="UABEA",
            executable=uabea_exe,
            game_root=game_root,
            output_dir=Path(output_dir),
            progress=progress,
        )
        logs.extend(uabea_logs)
        unity_export_by_type["uabea"] = uabea_count
        if uabea_count > 0:
            unity_export_count += uabea_count
            unity_exported_assets.append({"name": Path(uabea_output).name, "class_name": "UABEAExport"})
    else:
        log_append(logs, "[UABEA] Not found in PATH (optional fallback)", progress)

    return unity_export_count, unity_exported_assets, unity_export_by_type, True, None
