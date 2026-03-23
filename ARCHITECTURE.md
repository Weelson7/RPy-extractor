# RPy Extractor Architecture

## Overview

RPy Extractor is a local-first desktop web application.

Runtime model:
- Python HTTP server provides API + static web UI.
- Browser frontend drives extraction, sorting, logging, and media-merger workflows.
- File operations happen on local paths only.

Repository entry points:
- [Start.py](Start.py): launcher.
- [RPy-extractor/extract.py](RPy-extractor/extract.py): server bootstrap + route dispatch.

## Runtime Components

### 1) Server + Transport

Main module:
- [RPy-extractor/extract.py](RPy-extractor/extract.py)

Responsibilities:
- Load configuration from [RPy-extractor/config.json](RPy-extractor/config.json).
- Resolve runtime directories (temp, logs, web, merger output).
- Run startup dependency preflight.
- Expose API routes and static file serving.

### 2) API Domains

Folder:
- [RPy-extractor/api](RPy-extractor/api)

Modules:
- [RPy-extractor/api/extraction_handlers.py](RPy-extractor/api/extraction_handlers.py)
: extraction, extension scanning, keep/trash extension set.
- [RPy-extractor/api/sorting_handlers.py](RPy-extractor/api/sorting_handlers.py)
: sorting window listing, preview, keep/trash/undo/rename/save.
- [RPy-extractor/api/log_handlers.py](RPy-extractor/api/log_handlers.py)
: in-memory and persisted log endpoints.
- [RPy-extractor/api/session_handlers.py](RPy-extractor/api/session_handlers.py)
: initial state, session state, resume, folder browsing.
- [RPy-extractor/api/media_merger_handlers.py](RPy-extractor/api/media_merger_handlers.py)
: media merger state, candidate listing, build, overlay-audio picker.
- [RPy-extractor/api/common.py](RPy-extractor/api/common.py)
: shared helpers (active assets dir resolution, explorer open, history/session helpers).

### 3) Extraction Core

Folder:
- [RPy-extractor/extraction_core](RPy-extractor/extraction_core)

Modules:
- [RPy-extractor/extraction_core/runtime.py](RPy-extractor/extraction_core/runtime.py)
: subprocess + logging helpers.
- [RPy-extractor/extraction_core/archive.py](RPy-extractor/extraction_core/archive.py)
: archive discovery and extraction (Python + external tools).
- [RPy-extractor/extraction_core/file_ops.py](RPy-extractor/extraction_core/file_ops.py)
: file walking, extension mapping, file moves.
- [RPy-extractor/extraction_core/pipeline.py](RPy-extractor/extraction_core/pipeline.py)
: orchestration of extraction phases.

### 4) Extraction Strategy Layer

Folder:
- [RPy-extractor/extraction_types](RPy-extractor/extraction_types)

Core strategy modules:
- [RPy-extractor/extraction_types/orchestrator.py](RPy-extractor/extraction_types/orchestrator.py)
- [RPy-extractor/extraction_types/registry.py](RPy-extractor/extraction_types/registry.py)
- [RPy-extractor/extraction_types/renpy_extractor.py](RPy-extractor/extraction_types/renpy_extractor.py)
- [RPy-extractor/extraction_types/unity_extractor.py](RPy-extractor/extraction_types/unity_extractor.py)

Unity phases:
- [RPy-extractor/extraction_types/unity/phases/discovery_phase.py](RPy-extractor/extraction_types/unity/phases/discovery_phase.py)
- [RPy-extractor/extraction_types/unity/phases/export_phase.py](RPy-extractor/extraction_types/unity/phases/export_phase.py)
- [RPy-extractor/extraction_types/unity/phases/verification_phase.py](RPy-extractor/extraction_types/unity/phases/verification_phase.py)
- [RPy-extractor/extraction_types/unity/phases/manifest_phase.py](RPy-extractor/extraction_types/unity/phases/manifest_phase.py)

### 5) Media Merger

Folder:
- [RPy-extractor/media_merger](RPy-extractor/media_merger)

Module:
- [RPy-extractor/media_merger/service.py](RPy-extractor/media_merger/service.py)

Responsibilities:
- Discover media entries from working directory.
- Group candidates by naming pattern.
- Detect mixed-type same-index conflicts.
- Build merged video timeline via ffmpeg.
- Preserve native video audio + optional looped overlay audio.
- Support diapo/fade transitions, end controls (fadeout + frozen last frame), and post-build trash option.

## Frontend Architecture

UI files:
- [RPy-extractor/web/index.html](RPy-extractor/web/index.html)
- [RPy-extractor/web/app.js](RPy-extractor/web/app.js)
- [RPy-extractor/web/styles.css](RPy-extractor/web/styles.css)

Key sections:
- 3-step extraction workflow accordion.
- Workspace panels:
  - Sorting Window.
  - Media Merger.
  - Activity Log.

Media Merger frontend flow:
- Request merger state.
- List candidates with extension filtering + naming pattern.
- Browse candidates with paged windows (offset/limit, Prev/Next).
- Order same-index mixed-media conflicts through Up/Down controls (applied automatically to build order).
- Configure per-candidate loops:
  - loop entirety (times)
  - loop parts (indexes + times), auto-append blank row + explicit add-row button.
- Configure timeline end behavior:
  - fadeout time (video + audio fade at end)
  - last image time (freeze final frame before ending)
- Build via API with selected/expanded path order.

## Configuration Model

File:
- [RPy-extractor/config.json](RPy-extractor/config.json)

Fields:
- host
- port
- tempPath
- outputDir
- mergerDir
- webDir
- logDir

Resolved in:
- [RPy-extractor/extract.py](RPy-extractor/extract.py)

## Dependency Preflight

Implemented in:
- [RPy-extractor/startup.py](RPy-extractor/startup.py)

Required:
- unrpa Python module.

Optional checks:
- 7zip family (7z/7za/7zr), including common Windows install paths.
- unrar.
- ffmpeg + ffprobe (required for media merger build).
- UnityPy.
- AssetRipper.
- UABEA.

Dependency status endpoint:
- GET /api/dependencies

## API Surface

### GET

- /api/state
- /api/status
- /api/extensions
- /api/detected-extensions
- /api/logs
- /api/open-log-dir
- /api/logs/load
- /api/dependencies
- /api/assets-window?offset=...&limit=...
- /api/assets-window-preview?path=...
- /api/session
- /api/browse-folder
- /api/media-merger/state
- /preview/...

### POST

- /api/extract
- /api/scan
- /api/keep-selected
- /api/trash
- /api/restore
- /api/delete
- /api/clear-trash
- /api/resume
- /api/assets-preview
- /api/sort-keep
- /api/sort-trash
- /api/sort-undo
- /api/sort-rename
- /api/logs/clear
- /api/save-remaining-assets
- /api/open-folder
- /api/media-merger/list
- /api/media-merger/build
- /api/media-merger/browse-overlay

`/api/media-merger/build` payload supports:
- `endFadeoutTime`
- `endLastImageTime`

## Data + State Notes

Persistent/shared runtime state lives in:
- [RPy-extractor/models.py](RPy-extractor/models.py)

Important structures:
- AppConfig
- SortState
- ExtractJobState
- PersistentSessions (SESSIONS)

Session data stores:
- Current asset path.
- Sorting history for undo.
- In-memory logs.

## Performance Considerations

Current mitigations:
- Windowed sorting endpoint with offset/limit.
- Windowed media-merger candidates endpoint with offset/limit.
- Preview response caching on frontend.
- Media-merger candidate render batching via DocumentFragment.
- Activity log DOM cap to avoid unbounded node growth.

Potential next optimizations:
- Incremental candidate rendering in chunks for very large sets.
- On-demand rendering for conflict-heavy candidate details.

## Known External Constraints

- ffmpeg/ffprobe availability controls media merger build capability.
- Unity extraction quality depends on UnityPy and optional external tools.
- Archive extraction capability varies when 7zip/unrar are unavailable.
