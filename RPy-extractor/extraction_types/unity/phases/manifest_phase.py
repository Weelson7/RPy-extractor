"""Unity manifest writing phase."""
from pathlib import Path

from extraction_core import log_append
from extraction_types.unity.discovery import DiscoveryIndex
from extraction_types.unity.manifest import ManifestWriter


def run_manifest_phase(
    output_dir: Path,
    logs: list[str],
    discovery_index: DiscoveryIndex | None,
    discovered_count: int,
    extracted_count: int,
    quality_gate: dict,
    output_integrity: dict,
    unity_export_count: int,
    unity_export_by_type: dict[str, int],
    completeness_report: dict,
    progress,
) -> str:
    """Write discovery/completeness/summary manifests."""
    if progress:
        progress("[UNITY:MANIFEST] Writing extraction manifests")

    try:
        manifests_dir = Path(output_dir) / ".extraction_metadata"
        manifest_writer = ManifestWriter(manifests_dir)

        if discovery_index:
            discovery_data = {
                "timestamp": discovery_index.scan_timestamp,
                "containers_scanned": discovery_index.containers_scanned,
                "discovered_count": len(discovery_index.discovered_assets),
                "discovery_stats": discovery_index.discovery_stats,
            }
            manifest_writer.write_discovery_manifest(discovery_data)
            log_append(logs, "[MANIFEST] Discovery manifest written", progress)

        manifest_writer.write_completeness_report(completeness_report)
        log_append(logs, "[MANIFEST] Completeness report written", progress)

        summary = {
            "extractor_type": "unity",
            "discovered_count": discovered_count,
            "extracted_count": extracted_count,
            "extraction_ratio": extracted_count / discovered_count if discovered_count > 0 else 0,
            "quality_gate_pass": quality_gate.get("pass", False),
            "output_file_count": output_integrity.get("file_count", 0),
            "output_total_size": output_integrity.get("total_size", 0),
            "unity_exported_count": unity_export_count,
            "unity_exported_by_type": unity_export_by_type,
        }
        manifest_writer.write_summary(summary)
        manifest_writer.write_logs(logs)
        log_append(logs, "[MANIFEST] Summary and logs written", progress)

        return str(manifests_dir)
    except Exception as exc:
        log_append(logs, f"[MANIFEST] Failed: {exc}", progress)
        return ""
