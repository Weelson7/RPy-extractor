# RPy Extractor

RPy Extractor is a local-first desktop extraction and triage tool for game assets.

It provides a browser UI backed by a Python HTTP server and supports:

- Extraction and archive unpacking.
- Extension filtering.
- Asset-by-asset sorting and preview.
- Trash/undo/save workflows.
- Multi-engine routing (RenPy, Unity, generic fallback).

## Ownership

- Author: Weelson
- Initiative: C.O.R.E.
- Runtime app root: RPy-extractor

## High-Level Architecture

1. Launcher
- Start.py
- Starts the app process.

2. Server and transport
- RPy-extractor/extract.py
- HTTP server, static files, and route dispatch.

3. API handler domains
- RPy-extractor/api/session_handlers.py
- RPy-extractor/api/extraction_handlers.py
- RPy-extractor/api/sorting_handlers.py
- RPy-extractor/api/log_handlers.py
- RPy-extractor/api/common.py

4. Generic extraction core
- RPy-extractor/extraction_core/runtime.py
- RPy-extractor/extraction_core/archive.py
- RPy-extractor/extraction_core/file_ops.py
- RPy-extractor/extraction_core/pipeline.py

5. Strategy router
- RPy-extractor/extraction_types/orchestrator.py
- RPy-extractor/extraction_types/registry.py

6. Extractor implementations
- RPy-extractor/extraction_types/renpy_extractor.py
- RPy-extractor/extraction_types/unity_extractor.py

7. Unity internals
- RPy-extractor/extraction_types/unity/discovery.py
- RPy-extractor/extraction_types/unity/exporters.py
- RPy-extractor/extraction_types/unity/manifest.py
- RPy-extractor/extraction_types/unity/verify.py
- RPy-extractor/extraction_types/unity/phases/discovery_phase.py
- RPy-extractor/extraction_types/unity/phases/export_phase.py
- RPy-extractor/extraction_types/unity/phases/verification_phase.py
- RPy-extractor/extraction_types/unity/phases/manifest_phase.py

8. Frontend
- RPy-extractor/web/index.html
- RPy-extractor/web/app.js
- RPy-extractor/web/styles.css

9. Media merger module
- RPy-extractor/media_merger/service.py
- RPy-extractor/api/media_merger_handlers.py

10. Core models and startup
- RPy-extractor/models.py
- RPy-extractor/startup.py
- RPy-extractor/logging_utils.py

## Current Responsibility Boundaries

- extract.py: protocol and route dispatch only.
- api/*_handlers.py: endpoint logic grouped by domain.
- extraction_core/*: archive and file extraction primitives.
- unity_extractor.py: Unity pipeline coordinator only.
- unity/phases/*: Unity phase implementation details.
- media_merger/service.py: candidate grouping and ffmpeg merge orchestration.
- api/media_merger_handlers.py: media merger workspace endpoints.

## Configuration

Runtime config is loaded from RPy-extractor/config.json.

Required keys:
- host
- port
- tempPath
- outputDir
- mergerDir
- webDir
- logDir

`mergerDir` is the output folder for merged media files built from the Media Merger workspace panel.

## Dependency Preflight

Startup preflight runs before server start in RPy-extractor/extract.py.

Required:
- unrpa Python module.

Optional:
- 7z/7za/7zr
- unrar
- UnityPy
- AssetRipper CLI
- UABEA CLI

Implementation:
- RPy-extractor/startup.py

## Archive Support

Archive suffixes are defined in RPy-extractor/models.py.
Extraction logic is in RPy-extractor/extraction_core/archive.py and RPy-extractor/extraction_core/pipeline.py.

Supported inputs:
- .rpa
- .zip
- .tar
- .tar.gz / .tgz
- .tar.bz2 / .tbz / .tbz2
- .tar.xz / .txz
- .7z
- .rar
- .unitypackage

## Unity Pipeline

1. Discovery phase builds a container index.
2. Export phase runs UnityPy and optional external fallbacks.
3. Core extraction phase runs generic archive/file traversal.
4. Verification phase computes completeness and quality gate.
5. Manifest phase writes metadata and summaries.

Coordinator:
- RPy-extractor/extraction_types/unity_extractor.py

## API Reference

GET:
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

POST:
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
