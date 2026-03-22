# Branch Objective and Deliverables

Branch: RenPy_Unity

## Objective
Build a Unity extraction pipeline that can recover all extractable game assets with production-grade reliability.

Strict quality target:
- Extract absolutely all assets that are technically extractable from supported Unity builds.
- If any asset cannot be extracted, it must be explicitly reported with the exact technical reason.

## Scope (Phase 1: Unity)
- Unity-focused extraction only.
- Primary artifact classes:
  - Images and textures
  - Audio
  - Video
  - 3D models
  - Animation and material-related assets
  - Text and metadata assets that enable media reconstruction

## Deliverables
1. Unity extractor module
- New Unity-specific extraction entrypoint and strategy layer.
- Engine detection based on Unity signatures (for example UnityFS, globalgamemanagers, data folder conventions).

2. Unity container support matrix
- Parsing and extraction coverage for Unity asset containers and bundles used in target games.
- Explicit list of supported and partially supported container variants.

3. Normalized extraction manifest
- Per run, output a machine-readable manifest with:
  - discovered assets
  - extracted assets
  - failed assets
  - failure reasons
  - source container mapping

4. Media-first output organization
- Deterministic output tree for image, audio, video, and 3D model artifacts.
- Stable naming and collision policy.

5. Completeness verification tooling
- Validation pass that compares discovered entries vs extracted outputs.
- Completeness report with extraction ratio and unresolved items.

6. Logging and diagnostics
- Structured logs with enough detail to reproduce and debug misses.

## Draft Architecture

### Architecture Overview
The system will use a plugin-style extraction architecture with one extractor per game type.
Phase 1 activates Unity first while preserving existing RenPy behavior.

Core design principles:
- Engine-specific logic is isolated in extractor modules.
- API output contract stays stable across extractors.
- Extraction runs are fully traceable through manifests and deterministic output paths.
- Completeness validation is part of the runtime, not a separate manual step.

### Logical Components
1. Extraction Orchestrator
- Input: game path, optional game type, selected extensions.
- Responsibilities:
  - call engine detector
  - choose extractor via registry
  - coordinate discovery, extraction, export, and validation phases
  - return normalized result to existing API handlers

2. Extractor Registry
- Maps game type to extractor implementation.
- Initial entries:
  - renpy
  - unity
  - generic_fallback

3. Engine Detector
- Returns:
  - detected type
  - confidence score
  - evidence list (matched files/signatures)
- Unity detection signals:
  - globalgamemanagers
  - *_Data folder structure
  - UnityFS signature in bundle/header
  - level*/sharedassets*.assets patterns

4. Unity Discovery Indexer
- Scans Unity containers and creates a discovery index before extraction.
- Output:
  - discovered assets list
  - source container mapping
  - asset metadata (name/path/type/classID/container)

5. Unity Extractor Pipeline
- Stage A: Container enumeration
- Stage B: Asset object enumeration
- Stage C: Asset export by class/media family
- Stage D: Post-export integrity checks
- Stage E: Classification of all failures

6. Media Exporters
- Texture/Image exporter
- Audio exporter
- Video exporter
- 3D model exporter
- Shared responsibilities:
  - deterministic file naming
  - collision handling
  - source-to-output mapping

7. Completeness Verifier
- Compares discovery index vs extracted outputs.
- Emits strict completeness report:
  - extractable discovered count
  - extracted count
  - unresolved count
  - unresolved classifications
- Fails run quality gate if unclassified misses exist.

8. Manifest Writer
- Writes machine-readable run artifacts:
  - discovery_manifest.json
  - extraction_manifest.json
  - completeness_report.json
  - summary.json

### Proposed Module Layout
The exact filenames can be adjusted during implementation, but the structure target is:

- extraction_types/base.py
  - extractor interface and shared result schema
- extraction_types/registry.py
  - extractor registration and lookup
- extraction_types/detector.py
  - engine detection and confidence scoring
- extraction_types/renpy_extractor.py
  - wraps current RenPy extraction logic
- extraction_types/unity_extractor.py
  - Unity extraction orchestrator
- extraction_types/unity/discovery.py
  - Unity container and object indexing
- extraction_types/unity/exporters.py
  - media-specific export implementations
- extraction_types/unity/manifest.py
  - manifest generation for Unity runs
- extraction_types/unity/verify.py
  - completeness and integrity checks

### Runtime Flow (Unity)
1. Receive extraction request.
2. Detect engine and collect evidence.
3. Route to Unity extractor.
4. Build discovery index for all candidate assets.
5. Export assets by media family.
6. Validate exported artifacts.
7. Generate manifests and completeness report.
8. Return normalized response to API and UI.

### Normalized Result Contract
Every extractor returns the same top-level fields:
- extractorType
- detection (type, confidence, evidence)
- discoveredCount
- extractableCount
- extractedCount
- unresolvedCount
- unresolvedByReason
- exportedByMediaType
- checks
- logs
- manifestsPath

This allows the frontend and handlers to remain stable while adding engines.

### Quality Gate Policy (Strict)
A run is marked strict-pass only when:
- unresolvedCount is 0 for extractable assets
- unresolvedByReason has no unclassified entries
- integrity checks pass for exported media
- rerun on identical input produces identical manifest counts

Otherwise the run is strict-fail and must include actionable diagnostics.

### Unity Phase Implementation Slices
Slice 1: Detector + routing + registry integration.
Slice 2: Unity discovery index with container mapping.
Slice 3: Image/audio/video export.
Slice 4: 3D model export.
Slice 5: Completeness verifier + strict quality gates.
Slice 6: Performance tuning and sample coverage expansion.

## Strict Quality Requirements
The branch is accepted only if all requirements below are met:

1. Completeness
- For each supported Unity sample, extraction coverage must be 100 percent for all extractable assets.
- Every non-extracted asset must be classified as one of:
  - encrypted/protected
  - corrupted source
  - unsupported format variant
  - tool limitation with reproducible signature

2. Determinism
- Re-running extraction on the same input produces equivalent outputs and manifest counts.

3. Integrity
- Exported media is valid and openable by standard tools for each type.

4. Traceability
- Every output file is traceable to original container path and asset identifier in the manifest.

5. No silent failure
- Zero silent skips. Any skip must produce an explicit warning or error entry.

## Acceptance Metrics
- Discovery-to-extraction ratio: 100 percent for extractable assets.
- Unclassified failures: 0.
- Silent failures: 0.
- Deterministic rerun delta in manifest counts: 0.

## Definition of Done (Unity Phase)
- Unity extractor integrated into current flow without breaking existing RenPy behavior.
- At least one representative Unity sample set passes strict quality requirements.
- Objective evidence included: manifests, completeness reports, and logs.

## Planned Work Sequence
1. Add Unity engine detection and routing.
2. Implement Unity asset discovery index.
3. Implement extraction for media classes (image/audio/video/model).
4. Add manifest and completeness verifier.
5. Run validation suite and close all gaps.

## Non-Goals (Current Phase)
- Perfect handling of intentionally encrypted proprietary payloads without keys.
- Full support for non-Unity engines until Unity strict gates are green.
