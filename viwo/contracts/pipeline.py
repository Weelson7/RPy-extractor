"""Extraction request/result contract (doc 3). v1 payload keys are kept."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .legacy import run_to_legacy
from .types import DetectionResult
from .workspace import METADATA_DIR

CONTRACT_VERSION = "1.0"  # mirrored in viwo/__init__.py (contracts import nothing from the app)

GENERIC_PLUGIN_ID = "generic"


class Stage(str, Enum):
    PREPARE = "prepare"
    PROBE = "probe"
    DETECT = "detect"
    UNPACK = "unpack"
    CARVE = "carve"
    EXPORT = "export"
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

    @classmethod
    def from_payload(cls, data: Mapping[str, Any], workspace: str = "") -> "ExtractionRequest":
        """Map a v1-style /api/extract payload (doc 3.2)."""
        raw = str(data.get("extractionType") or "auto").strip().lower()
        exts = data.get("selectedExts")
        selected = frozenset(str(e).lower() for e in exts) if isinstance(exts, list) else None
        plugins = tuple(str(p).strip().lower() for p in data.get("plugins") or ())
        policy = str(data.get("mixedPolicy") or "selected").lower()
        on_existing = str(data.get("onExisting") or "ask").lower()
        carve = str(data.get("carve") or "unknown").lower()
        mode = {"": ExtractionMode.AUTO, "auto": ExtractionMode.AUTO}.get(raw)
        if mode is None:
            mode = ExtractionMode.MIXED if raw == "mixed" else ExtractionMode.SINGLE
            plugins = plugins if raw == "mixed" else (raw,)
        return cls(
            game_path=str(data.get("gamePath", "")),
            workspace=workspace,
            selected_exts=selected or None,
            mode=mode,
            plugins=plugins,
            mixed_policy=MixedPolicy(policy)
            if policy in MixedPolicy._value2member_map_
            else MixedPolicy.SELECTED,
            plugin_options=dict(data.get("pluginOptions") or {}),
            on_existing=OnExisting(on_existing)
            if on_existing in OnExisting._value2member_map_
            else OnExisting.ASK,
            carve=CarveMode(carve) if carve in CarveMode._value2member_map_ else CarveMode.UNKNOWN,
        )


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
            "plugins": [run_to_legacy(r) for r in self.runs],
        }
        if self.error:
            payload["error"] = self.error
        return payload


LEGACY_RESULT_KEYS = frozenset(
    "success archivesFound archivesExtracted scannedFiles copiedFiles copiedByExt checks "
    "logs extractorType detection".split()
)
