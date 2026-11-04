"""Extraction request/result contract (doc 3). v1 payload keys are kept."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .types import DetectionResult
from .workspace import METADATA_DIR

CONTRACT_VERSION = "1.2"  # mirrored in viwo/__init__.py (contracts import nothing from the app)

GENERIC_PLUGIN_ID = "generic"


class Stage(str, Enum):
    PREPARE = "prepare"
    PROBE = "probe"
    DETECT = "detect"
    UNPACK = "unpack"
    EXPORT = "export"
    CARVE = "carve"
    COLLECT = "collect"
    VERIFY = "verify"
    REPORT = "report"


class ExtractionMode(str, Enum):
    AUTO = "auto"
    SINGLE = "single"
    MIXED = "mixed"


class MixedPolicy(str, Enum):
    SELECTED = "selected"
    DETECTED = "detected"
    ALL = "all"


class OnExisting(str, Enum):
    """What to do when the target workspace already has content (doc 4.3)."""

    ASK = "ask"
    NEW = "new"
    REPLACE = "replace"
    CANCEL = "cancel"


class CarveMode(str, Enum):
    """Signature carving: off, files nothing else recognizes (default), or every file."""

    OFF = "off"
    UNKNOWN = "unknown"
    ALL = "all"


@dataclass(frozen=True)
class ExtractionRequest:
    game_path: str
    workspace: str = ""
    selected_exts: frozenset[str] | None = None
    mode: ExtractionMode = ExtractionMode.AUTO
    plugins: tuple[str, ...] = ()
    mixed_policy: MixedPolicy = MixedPolicy.SELECTED
    mixed_threshold: float = 0.5
    plugin_options: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    on_existing: OnExisting = OnExisting.ASK
    carve: CarveMode = CarveMode.UNKNOWN


@dataclass(frozen=True)
class PluginRun:
    plugin_id: str
    detection: DetectionResult
    exported: int = 0
    backend: str = ""
    warnings: tuple[str, ...] = ()
    error: str = ""
    exported_by_kind: Mapping[str, int] = field(default_factory=dict)  # doc 3.5 exportedByKind
    verify_passed: bool = True  # doc 3.5: false when the plugin's verify() returned warnings
    inventory_items: int = 0  # doc 0.4: items the plugin's inventory() listed (0 = no claim)
    inventory_found: int = 0

    def to_legacy_dict(self) -> dict[str, Any]:
        """One `plugins[]` entry of the v1 extract result (doc 0.4, doc 3.5)."""
        return {
            "id": self.plugin_id,
            "detection": self.detection.to_legacy_dict(),
            "exported": self.exported,
            "exportedByKind": dict(sorted(self.exported_by_kind.items())),
            "exportedByTool": self.backend,
            "inventoryCount": self.inventory_items or self.inventory_found,
            "verifyPassed": self.verify_passed,
            "backend": self.backend,
            "warnings": list(self.warnings),
            "error": self.error,
        }


@dataclass(frozen=True)
class ExtractionResult:
    success: bool
    mode: ExtractionMode
    runs: tuple[PluginRun, ...]
    workspace: str = ""
    archives_found: int = 0
    archives_extracted: int = 0
    scanned_files: int = 0
    copied_files: int = 0
    copied_by_ext: Mapping[str, int] = field(default_factory=dict)
    by_backend: Mapping[str, int] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    logs: tuple[str, ...] = ()
    run_record: str = ""
    error: str = ""
    carved_files: int = 0

    def to_legacy_dict(self) -> dict[str, Any]:
        """The v1 /api/extract `result` object; v1 keys always present (doc 3.5)."""
        primary = self.runs[0] if self.runs else None
        mixed = self.mode is ExtractionMode.MIXED
        payload: dict[str, Any] = {
            "success": self.success,
            "archivesFound": self.archives_found,
            "archivesExtracted": self.archives_extracted,
            "scannedFiles": self.scanned_files,
            "copiedFiles": self.copied_files,
            "copiedByExt": dict(sorted(self.copied_by_ext.items())),
            "checks": {"ok": not self.warnings, "warnings": list(self.warnings)},
            "logs": list(self.logs),
            "extractorType": "mixed" if mixed else (primary.plugin_id if primary else "generic"),
            "detection": primary.detection.to_legacy_dict() if primary else {},
            "mode": self.mode.value,
            "byBackend": dict(sorted(self.by_backend.items())),
            "runRecord": self.run_record,
            "workspace": self.workspace,
            "carvedFiles": self.carved_files,
            "movedFiles": 0,  # doc 0.4: nothing is ever moved out of a game (copiedFiles counts)
            "inventoryItems": sum(r.inventory_items for r in self.runs),
            "collectedFromInventory": sum(r.inventory_found for r in self.runs),
            "contractVersion": CONTRACT_VERSION,
            "manifestsPath": f"{self.workspace}/{METADATA_DIR}" if self.workspace else "",
            "plugins": [r.to_legacy_dict() for r in self.runs],
        }
        if self.error:
            payload["error"] = self.error
        return payload


LEGACY_RESULT_KEYS = frozenset(
    "success archivesFound archivesExtracted scannedFiles copiedFiles copiedByExt checks "
    "logs extractorType detection".split()
)
