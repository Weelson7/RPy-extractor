"""ViWo contracts: interfaces and value types only (stdlib, no app imports)."""

from .errors import Envelope, ViwoError
from .os import OS, DesktopShell, FileSystemPolicy, ProcessRunner, ToolLocator
from .pipeline import (
    GENERIC_PLUGIN_ID,
    LEGACY_RESULT_KEYS,
    CarveMode,
    ExtractionMode,
    ExtractionRequest,
    ExtractionResult,
    MixedPolicy,
    OnExisting,
    PluginRun,
    Stage,
)
from .plugin import EnginePlugin, ExtractionContext, GameProbe, PluginManifest, PluginOption
from .slots import (
    Backend,
    Carver,
    Decoder,
    Exporter,
    Match,
    Packer,
    SlotBinding,
    SlotDefinition,
    Unarchiver,
)
from .types import (
    CancelToken,
    DependencySpec,
    DetectionResult,
    Outcome,
    OutcomeKind,
    ProcessResult,
    ProgressEvent,
    ProgressSink,
    Requirement,
    ToolLocation,
)

__all__ = [n for n in dir() if not n.startswith("_")]
