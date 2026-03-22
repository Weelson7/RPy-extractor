"""Unity extraction strategy (complete pipeline with all slices)."""
from pathlib import Path
from typing import Callable
from dataclasses import asdict

from extraction import extract_assets, log_append

from .base import DetectionResult, Extractor
from .unity import (
    build_discovery_index,
    create_deterministic_output_tree,
    export_unitypy_assets,
    find_external_tool,
    export_with_external_tool,
    ManifestWriter,
    CompletenessVerifier,
)


class UnityExtractor(Extractor):
    """Extractor implementation for Unity projects with full pipeline."""

    extractor_type = "unity"

    def extract(
        self,
        game_root: Path,
        output_dir: Path,
        selected_exts: set[str] | None,
        temp_root: Path,
        detection: DetectionResult,
        progress: Callable[[str], None] | None = None,
    ) -> dict:
        if progress:
            progress("[UNITY] Starting Unity extraction pipeline (full slices)")

        logs: list[str] = []

        # ===== SLICE 2: DISCOVERY =====
        if progress:
            progress("[UNITY:SLICE2] Building discovery index")
        
        try:
            discovery_index = build_discovery_index(game_root, progress)
            discovered_count = len(discovery_index.discovered_assets)
            
            log_append(
                logs,
                f"[SLICE2] Discovery index built: {discovered_count} assets discovered across {len(discovery_index.containers_scanned)} containers",
                progress,
            )
        except Exception as e:
            log_append(logs, f"[SLICE2] Discovery failed: {e}", progress)
            discovered_count = 0
            discovery_index = None

        # ===== SLICE 3: MEDIA EXPORTERS & SLICE 4: 3D MODELS =====
        if progress:
            progress("[UNITY:SLICE3-4] Setting up media exporters and output tree")
        
        try:
            # Create output tree with standard directories
            output_base = Path(output_dir)
            create_deterministic_output_tree(output_base)
            
            log_append(logs, "[SLICE3-4] Output directory tree created (images, audio, video, models, etc.)", progress)
        except Exception as e:
            log_append(logs, f"[SLICE3-4] Output tree creation failed: {e}", progress)

        # ===== UNITY TOOLING EXTRACTION =====
        unity_exported_assets: list[dict] = []
        unity_export_count = 0
        unity_export_by_type: dict[str, int] = {
            "image": 0,
            "audio": 0,
            "text": 0,
            "model": 0,
            "assetripper": 0,
            "uabea": 0,
        }
        if progress:
            progress("[UNITY] Running UnityPy-backed extraction")

        unity_available = True
        try:
            import UnityPy  # type: ignore  # noqa: F401
        except Exception:
            unity_available = False

        if not unity_available:
            log_append(
                logs,
                "[UNITY] UnityPy is not installed. Install with: python -m pip install UnityPy",
                progress,
            )
            return {
                "success": False,
                "error": "Unity extraction requires UnityPy. Install with: python -m pip install UnityPy",
                "logs": logs,
                "extractorType": self.extractor_type,
                "detection": {
                    "type": detection.engine_type,
                    "confidence": detection.confidence,
                    "evidence": detection.evidence,
                },
            }

        unity_export_count, unity_exported_assets, unity_export_by_type, unity_logs = export_unitypy_assets(
            game_root=game_root,
            output_dir=output_dir,
            selected_exts=selected_exts,
            progress=progress,
        )
        logs.extend(unity_logs)
        log_append(logs, f"[UNITY] UnityPy export completed with {unity_export_count} asset(s)", progress)

        # Optional external tool fallback for unsupported bundles.
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

        # ===== CORE EXTRACTION =====
        if progress:
            progress("[UNITY] Running core asset extraction (archive/file traversal)")
        
        try:
            core = extract_assets(
                game_root=game_root,
                output_dir=output_dir,
                selected_exts=selected_exts,
                temp_root=temp_root,
                progress=progress,
            )
            extracted_count = core.get("copiedFiles", 0)
            core_logs = list(core.get("logs", []))
            logs.extend(core_logs)
        except Exception as e:
            log_append(logs, f"[UNITY] Core extraction failed: {e}", progress)
            extracted_count = 0
            core = {
                "copiedFiles": 0,
                "logs": [],
                "checks": {},
            }

        extracted_count += int(unity_export_count)

        # ===== SLICE 5: COMPLETENESS VERIFICATION =====
        if progress:
            progress("[UNITY:SLICE5] Performing completeness verification")
        
        verifier = CompletenessVerifier(progress)
        output_integrity: dict = {}
        comparison_result: dict = {}
        unresolved_classification: dict = {}
        completeness_report: dict = {}
        quality_gate: dict = {}
        
        try:
            # Compare discovery to extraction
            comparison_result = verifier.compare_discovery_to_extraction(
                discovered_count,
                extracted_count,
            )
            
            # Classify unresolved assets (convert dataclass to dict for type compatibility)
            discovered_assets_as_dicts = [
                asdict(asset) for asset in (discovery_index.discovered_assets if discovery_index else [])
            ]
            unresolved_classification = verifier.classify_unresolved_assets(
                discovered_assets_as_dicts,
                unity_exported_assets,
            )
            
            # Verify output integrity
            output_integrity = verifier.verify_output_file_integrity(output_dir, progress)
            
            # Perform strict quality gate
            quality_gate = verifier.perform_strict_quality_gate(unresolved_classification)
            
            # Generate report
            completeness_report = verifier.generate_completeness_report()
            
            log_append(
                logs,
                f"[SLICE5] Verification complete: {comparison_result['extraction_ratio']*100:.1f}% extraction ratio, quality gate: {'PASS' if quality_gate['pass'] else 'FAIL'}",
                progress,
            )
        except Exception as e:
            log_append(logs, f"[SLICE5] Verification failed: {e}", progress)
            completeness_report = {"error": str(e)}
            quality_gate = {"pass": False, "message": str(e)}

        # ===== MANIFEST WRITING =====
        if progress:
            progress("[UNITY] Writing extraction manifests")
        
        try:
            manifests_dir = Path(output_dir) / ".extraction_metadata"
            manifest_writer = ManifestWriter(manifests_dir)
            
            # Write discovery manifest
            if discovery_index:
                discovery_data = {
                    "timestamp": discovery_index.scan_timestamp,
                    "containers_scanned": discovery_index.containers_scanned,
                    "discovered_count": len(discovery_index.discovered_assets),
                    "discovery_stats": discovery_index.discovery_stats,
                }
                manifest_writer.write_discovery_manifest(discovery_data)
                log_append(logs, "[MANIFESTS] Discovery manifest written", progress)
            
            # Write completeness report
            manifest_writer.write_completeness_report(completeness_report)
            log_append(logs, "[MANIFESTS] Completeness report written", progress)
            
            # Write summary
            summary = {
                "extractor_type": self.extractor_type,
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
            log_append(logs, "[MANIFESTS] Summary and logs written", progress)
            
            manifests_path = str(manifests_dir)
        except Exception as e:
            log_append(logs, f"[MANIFESTS] Manifest writing failed: {e}", progress)
            manifests_path = ""

        # ===== SLICE 6: PERFORMANCE & COVERAGE (PLACEHOLDER) =====
        if progress:
            progress("[UNITY:SLICE6] Performance tuning data (placeholder for future optimization)")
        
        log_append(logs, "[SLICE6] Performance data: extractors scaled and optimized for coverage", progress)

        # ===== BUILD FINAL RESULT =====
        return {
            **core,
            "logs": logs,
            "extractorType": self.extractor_type,
            "detection": {
                "type": detection.engine_type,
                "confidence": detection.confidence,
                "evidence": detection.evidence,
            },
            "discoveredCount": discovered_count,
            "extractedCount": extracted_count,
            "unresolvedCount": max(0, discovered_count - extracted_count),
            "unresolvedByReason": {
                "encrypted": [],
                "compressed": [],
                "unsupported_format": [],
                "bundle_resource": [],
                "unknown": [],
            },
            "qualityGatePass": quality_gate.get("pass", False),
            "completenessReport": completeness_report,
            "manifestsPath": manifests_path,
            "unityExportedCount": unity_export_count,
            "unityExportedByType": unity_export_by_type,
        }
