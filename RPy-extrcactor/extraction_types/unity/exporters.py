"""Unity media exporters for standardized asset extraction and output organization."""
import json
import shutil
from pathlib import Path
from typing import Callable
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class ExportJob:
    """Represents a single asset export task."""
    source_path: Path
    output_path: Path
    asset_name: str
    media_type: str  # "image", "audio", "video", "model", etc.
    source_container: str


@dataclass
class ExportResult:
    """Result of a single export operation."""
    job: ExportJob
    success: bool
    output_path: Path | None = None
    error_reason: str | None = None
    file_size: int = 0


class MediaExporter:
    """Unified interface for exporting media assets."""
    
    def __init__(self, output_base: Path, progress: Callable[[str], None] | None = None):
        self.output_base = Path(output_base)
        self.progress = progress or (lambda x: None)
        self.export_results: list[ExportResult] = []
        self.export_stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "by_type": defaultdict(int),
            "failures_by_reason": defaultdict(int),
        }
    
    def export_image(self, job: ExportJob) -> ExportResult:
        """Export image asset (Texture2D, Sprite, etc.)."""
        try:
            self.progress(f"[EXPORT] Preparing image export: {job.asset_name}")
            
            # Ensure output directory exists
            output_dir = self.output_base / "images"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # For now, placeholder: actual extraction uses specialized parsers in Slice 3
            # This documents the export path and can be validated by checking directories
            output_path = output_dir / f"{job.asset_name}.placeholder"
            
            self.progress(f"[EXPORT] Image export placeholder: {output_path}")
            
            return ExportResult(
                job=job,
                success=True,
                output_path=output_path,
                file_size=0,
            )
        except Exception as e:
            self.progress(f"[EXPORT] Image export failed: {e}")
            return ExportResult(
                job=job,
                success=False,
                error_reason=str(e),
            )
    
    def export_audio(self, job: ExportJob) -> ExportResult:
        """Export audio asset (AudioClip, etc.)."""
        try:
            self.progress(f"[EXPORT] Preparing audio export: {job.asset_name}")
            
            output_dir = self.output_base / "audio"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Placeholder for Slice 3 implementation
            output_path = output_dir / f"{job.asset_name}.placeholder"
            
            self.progress(f"[EXPORT] Audio export placeholder: {output_path}")
            
            return ExportResult(
                job=job,
                success=True,
                output_path=output_path,
                file_size=0,
            )
        except Exception as e:
            self.progress(f"[EXPORT] Audio export failed: {e}")
            return ExportResult(
                job=job,
                success=False,
                error_reason=str(e),
            )
    
    def export_video(self, job: ExportJob) -> ExportResult:
        """Export video asset (VideoClip, etc.)."""
        try:
            self.progress(f"[EXPORT] Preparing video export: {job.asset_name}")
            
            output_dir = self.output_base / "video"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Placeholder for Slice 3 implementation
            output_path = output_dir / f"{job.asset_name}.placeholder"
            
            self.progress(f"[EXPORT] Video export placeholder: {output_path}")
            
            return ExportResult(
                job=job,
                success=True,
                output_path=output_path,
                file_size=0,
            )
        except Exception as e:
            self.progress(f"[EXPORT] Video export failed: {e}")
            return ExportResult(
                job=job,
                success=False,
                error_reason=str(e),
            )
    
    def export_model(self, job: ExportJob) -> ExportResult:
        """Export 3D model asset (Mesh, SkinnedMeshRenderer, etc.)."""
        try:
            self.progress(f"[EXPORT] Preparing model export: {job.asset_name}")
            
            output_dir = self.output_base / "models"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Placeholder for Slice 4 implementation
            output_path = output_dir / f"{job.asset_name}.placeholder"
            
            self.progress(f"[EXPORT] Model export placeholder: {output_path}")
            
            return ExportResult(
                job=job,
                success=True,
                output_path=output_path,
                file_size=0,
            )
        except Exception as e:
            self.progress(f"[EXPORT] Model export failed: {e}")
            return ExportResult(
                job=job,
                success=False,
                error_reason=str(e),
            )
    
    def export_asset(self, job: ExportJob) -> ExportResult:
        """Route asset to appropriate exporter based on media type."""
        self.export_stats["total"] += 1
        self.export_stats["by_type"][job.media_type] += 1
        
        try:
            if job.media_type == "image":
                result = self.export_image(job)
            elif job.media_type == "audio":
                result = self.export_audio(job)
            elif job.media_type == "video":
                result = self.export_video(job)
            elif job.media_type == "model":
                result = self.export_model(job)
            else:
                result = ExportResult(
                    job=job,
                    success=False,
                    error_reason=f"Unknown media type: {job.media_type}",
                )
            
            if result.success:
                self.export_stats["success"] += 1
            else:
                self.export_stats["failed"] += 1
                self.export_stats["failures_by_reason"][result.error_reason or "Unknown"] += 1
            
            self.export_results.append(result)
            return result
        
        except Exception as e:
            result = ExportResult(
                job=job,
                success=False,
                error_reason=str(e),
            )
            self.export_stats["failed"] += 1
            self.export_stats["failures_by_reason"][str(e)] += 1
            self.export_results.append(result)
            return result
    
    def get_export_summary(self) -> dict:
        """Get summary of all exports."""
        return {
            "total_attempted": self.export_stats["total"],
            "successful": self.export_stats["success"],
            "failed": self.export_stats["failed"],
            "by_media_type": dict(self.export_stats["by_type"]),
            "failure_reasons": dict(self.export_stats["failures_by_reason"]),
        }
    
    def write_export_manifest(self, output_dir: Path) -> Path:
        """Write export manifest documenting all export attempts."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        manifest_path = output_dir / "export_manifest.json"
        
        manifest_data = {
            "summary": self.get_export_summary(),
            "results": [
                {
                    "asset_name": result.job.asset_name,
                    "media_type": result.job.media_type,
                    "source_container": result.job.source_container,
                    "success": result.success,
                    "output_path": str(result.output_path) if result.output_path else None,
                    "file_size": result.file_size,
                    "error_reason": result.error_reason,
                }
                for result in self.export_results
            ],
        }
        
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)
        
        return manifest_path


def create_deterministic_output_tree(base_dir: Path) -> None:
    """Create standardized output directory tree for all media types."""
    media_dirs = ["images", "audio", "video", "models", "animations", "materials", "text"]
    
    for media_dir in media_dirs:
        (base_dir / media_dir).mkdir(parents=True, exist_ok=True)
