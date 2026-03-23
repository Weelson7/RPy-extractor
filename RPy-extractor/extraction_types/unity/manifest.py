"""Unity extraction manifest generation and management."""
import json
from pathlib import Path
from typing import Any
from datetime import datetime


class ManifestWriter:
    """Generates machine-readable extraction artifacts and manifests."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def write_discovery_manifest(self, discovery_index: dict) -> Path:
        """Write discovery index manifest (already implemented in discovery.py)."""
        manifest_path = self.output_dir / "discovery_manifest.json"
        
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(discovery_index, f, indent=2)
        
        return manifest_path
    
    def write_extraction_manifest(self, extraction_result: dict) -> Path:
        """Write extraction manifest documenting what was extracted."""
        manifest_path = self.output_dir / "extraction_manifest.json"
        
        extraction_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "extraction_result": extraction_result,
        }
        
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(extraction_data, f, indent=2)
        
        return manifest_path
    
    def write_completeness_report(self, report: dict) -> Path:
        """Write completeness verification report."""
        manifest_path = self.output_dir / "completeness_report.json"
        
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        
        return manifest_path
    
    def write_summary(self, summary: dict) -> Path:
        """Write extraction summary report."""
        manifest_path = self.output_dir / "extraction_summary.json"
        
        summary_data = {
            "timestamp": datetime.utcnow().isoformat(),
            **summary,
        }
        
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2)
        
        return manifest_path
    
    def write_logs(self, logs: list[str]) -> Path:
        """Write extraction logs in structured format."""
        logs_path = self.output_dir / "extraction_logs.jsonl"
        
        with open(logs_path, "w", encoding="utf-8") as f:
            for log_entry in logs:
                f.write(json.dumps({"message": log_entry}) + "\n")
        
        return logs_path
