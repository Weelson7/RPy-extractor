"""Unity verification phase."""
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from extraction_core import log_append
from extraction_types.unity.discovery import DiscoveryIndex
from extraction_types.unity.verify import CompletenessVerifier


def run_verification_phase(
    output_dir: Path,
    discovery_index: DiscoveryIndex | None,
    discovered_count: int,
    extracted_count: int,
    unity_exported_assets: list[dict],
    progress: Callable[[str], None] | None,
    logs: list[str],
) -> tuple[dict, dict, dict, dict, dict]:
    """Run completeness and quality verification."""
    if progress:
        progress("[UNITY:VERIFY] Performing completeness verification")

    verifier = CompletenessVerifier(progress)
    output_integrity: dict = {}
    comparison_result: dict = {}
    unresolved_classification: dict = {}
    completeness_report: dict = {}
    quality_gate: dict = {}

    try:
        comparison_result = verifier.compare_discovery_to_extraction(discovered_count, extracted_count)

        discovered_assets_as_dicts = [
            asdict(asset) for asset in (discovery_index.discovered_assets if discovery_index else [])
        ]
        unresolved_classification = verifier.classify_unresolved_assets(
            discovered_assets_as_dicts,
            unity_exported_assets,
        )

        output_integrity = verifier.verify_output_file_integrity(output_dir, progress)
        quality_gate = verifier.perform_strict_quality_gate(unresolved_classification)
        completeness_report = verifier.generate_completeness_report()

        log_append(
            logs,
            f"[VERIFY] Extraction ratio {comparison_result['extraction_ratio'] * 100:.1f}% - quality gate: {'PASS' if quality_gate['pass'] else 'FAIL'}",
            progress,
        )
    except Exception as exc:
        log_append(logs, f"[VERIFY] Failed: {exc}", progress)
        completeness_report = {"error": str(exc)}
        quality_gate = {"pass": False, "message": str(exc)}

    return output_integrity, comparison_result, unresolved_classification, completeness_report, quality_gate
