"""Unity extraction completeness verifier and integrity checker."""
from pathlib import Path
from typing import Callable
from collections import defaultdict
import json


class CompletenessVerifier:
    """Validates extraction completeness against discovery index."""
    
    def __init__(self, progress: Callable[[str], None] | None = None):
        self.progress = progress or (lambda x: None)
        self.checks_performed = []
        self.failures = []
        self.warnings = []
    
    def compare_discovery_to_extraction(
        self,
        discovery_count: int,
        extracted_count: int,
    ) -> dict:
        """Compare discovered assets vs extracted assets."""
        self.progress(f"[VERIFY] Comparing discovery ({discovery_count}) to extraction ({extracted_count})")
        
        result = {
            "discovered_count": discovery_count,
            "extracted_count": extracted_count,
            "extraction_ratio": extracted_count / discovery_count if discovery_count > 0 else 0,
            "unresolved_count": discovery_count - extracted_count,
            "pass": extracted_count >= discovery_count,
        }
        
        self.checks_performed.append(("discovery_extraction_comparison", result))
        
        if result["pass"]:
            self.progress("[VERIFY] Extraction ratio: 100% - PASS")
        else:
            self.progress(f"[VERIFY] Extraction ratio: {result['extraction_ratio']*100:.1f}% - FAIL")
            self.failures.append(
                f"Unresolved assets: {result['unresolved_count']} of {discovery_count}"
            )
        
        return result
    
    def classify_unresolved_assets(
        self,
        discovered_assets: list[dict],
        exported_assets: list[dict],
        progress: Callable[[str], None] | None = None,
    ) -> dict:
        """Classify unresolved assets by reason.
        
        Classification categories:
        - encrypted: Asset is encrypted or DRM-protected
        - unsupported_format: Format not yet supported by exporters
        - compressed: Asset uses unsupported compression
        - corrupted: Asset data is corrupted or invalid
        - bundle_resource: External bundle not included in export set
        - unknown: Unable to classify (strict quality gate failure)
        """
        progress = progress or self.progress
        progress("[VERIFY] Classifying unresolved assets")
        
        exported_names = set(a.get("name", "") for a in exported_assets)
        
        classifications = defaultdict(list)
        unclassified = []
        
        for discovered in discovered_assets:
            name = discovered.get("name", "")
            if name not in exported_names:
                # For Slice 5, default classification based on asset type
                class_name = discovered.get("class_name", "Unknown")
                
                if "Protected" in class_name:
                    classifications["encrypted"].append(name)
                elif "Compressed" in class_name:
                    classifications["compressed"].append(name)
                elif "Bundle" in class_name:
                    classifications["bundle_resource"].append(name)
                else:
                    unclassified.append(name)
        
        result = {
            "encrypted": classifications["encrypted"],
            "compressed": classifications["compressed"],
            "bundle_resource": classifications["bundle_resource"],
            "unsupported_format": classifications["unsupported_format"],
            "corrupted": classifications["corrupted"],
            "unclassified": unclassified,
            "total_unresolved": len(unclassified) + sum(len(v) for v in classifications.values()),
        }
        
        self.checks_performed.append(("unresolved_classification", result))
        
        if unclassified:
            self.failures.append(f"Unclassified unresolved assets: {len(unclassified)}")
        
        return result
    
    def verify_output_file_integrity(
        self,
        output_dir: Path,
        progress: Callable[[str], None] | None = None,
    ) -> dict:
        """Verify integrity of exported files."""
        progress = progress or self.progress
        progress("[VERIFY] Checking output file integrity")
        
        output_dir = Path(output_dir)
        
        result = {
            "output_dir": str(output_dir),
            "exists": output_dir.exists(),
            "is_directory": output_dir.is_dir(),
            "file_count": 0,
            "total_size": 0,
            "media_type_counts": defaultdict(int),
            "pass": False,
        }
        
        if output_dir.exists() and output_dir.is_dir():
            for file_path in output_dir.rglob("*"):
                if file_path.is_file():
                    result["file_count"] += 1
                    result["total_size"] += file_path.stat().st_size
                    
                    suffix = file_path.suffix.lower()
                    result["media_type_counts"][suffix] += 1
            
            result["media_type_counts"] = dict(result["media_type_counts"])
            result["pass"] = result["file_count"] > 0
            progress(f"[VERIFY] Found {result['file_count']} files ({result['total_size']} bytes)")
        else:
            progress("[VERIFY] Output directory does not exist")
        
        self.checks_performed.append(("output_file_integrity", result))
        return result
    
    def check_deterministic_reproducibility(
        self,
        manifest1: dict,
        manifest2: dict,
    ) -> dict:
        """Verify that re-running extraction produces identical results."""
        result = {
            "discovered_count_match": manifest1.get("discovered_count") == manifest2.get("discovered_count"),
            "extracted_count_match": manifest1.get("extracted_count") == manifest2.get("extracted_count"),
            "asset_list_match": manifest1.get("assets", []) == manifest2.get("assets", []),
            "pass": False,
        }
        
        result["pass"] = all([
            result["discovered_count_match"],
            result["extracted_count_match"],
            result["asset_list_match"],
        ])
        
        self.checks_performed.append(("reproducibility", result))
        return result
    
    def perform_strict_quality_gate(
        self,
        unresolved_classification: dict,
    ) -> dict:
        """Perform strict quality gate: fail if any unclassified assets exist."""
        self.progress("[VERIFY] Performing strict quality gate check")
        
        unclassified_count = len(unresolved_classification.get("unclassified", []))
        
        result = {
            "unclassified_assets": unclassified_count,
            "pass": unclassified_count == 0,
            "message": (
                "PASS: All unresolved assets classified"
                if unclassified_count == 0
                else f"FAIL: {unclassified_count} unclassified assets"
            ),
        }
        
        self.checks_performed.append(("strict_quality_gate", result))
        
        if not result["pass"]:
            self.failures.append(result["message"])
        
        self.progress(f"[VERIFY] {result['message']}")
        return result
    
    def generate_completeness_report(self) -> dict:
        """Generate comprehensive completeness report."""
        report = {
            "checks_performed": self.checks_performed,
            "failures": self.failures,
            "warnings": self.warnings,
            "overall_pass": len(self.failures) == 0,
        }
        
        self.progress(f"[VERIFY] Report: {len(self.checks_performed)} checks, {len(self.failures)} failures")
        
        return report
