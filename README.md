# RPy Extractor

RPy Extractor is a local-first desktop extractor and triage tool for game assets.

It provides a browser UI backed by a Python HTTP server and supports:

- Extraction and archive unpacking.
- Extension filtering.
- Asset-by-asset sorting and preview.
- Trash/undo/save workflows.
- Multi-engine routing (RenPy, Unity, generic fallback).

This implementation is authored by Weelson and is part of the C.O.R.E. initiative.

## Ownership

- Author: Weelson
- Initiative: C.O.R.E.
- Runtime app root: RPy-extrcactor

## High-Level Architecture

Runtime layers:

1. Launcher layer
- [Start.py](Start.py)
- Starts the app process with logging and path setup.

2. Server/API layer
- [RPy-extrcactor/extract.py](RPy-extrcactor/extract.py)
- Hosts static UI and HTTP JSON API routes.
- Delegates business logic to handlers.

3. Application services
- [RPy-extrcactor/handlers.py](RPy-extrcactor/handlers.py)
- Request-level orchestration, path validation, and response shaping.

4. Extraction engine
- [RPy-extrcactor/extraction.py](RPy-extrcactor/extraction.py)
- Archive detection/unpack, file walk, extension grouping, and output moves.
- Shared extraction primitives used by engine-specific strategies.

5. Strategy router
- [RPy-extrcactor/extraction_types/orchestrator.py](RPy-extrcactor/extraction_types/orchestrator.py)
- Detects engine and dispatches to the registered extractor.

6. Extractor strategies
- [RPy-extrcactor/extraction_types/renpy_extractor.py](RPy-extrcactor/extraction_types/renpy_extractor.py)
- [RPy-extrcactor/extraction_types/unity_extractor.py](RPy-extrcactor/extraction_types/unity_extractor.py)
- [RPy-extrcactor/extraction_types/registry.py](RPy-extrcactor/extraction_types/registry.py)

7. Unity tooling module
- [RPy-extrcactor/extraction_types/unity/discovery.py](RPy-extrcactor/extraction_types/unity/discovery.py)
- [RPy-extrcactor/extraction_types/unity/exporters.py](RPy-extrcactor/extraction_types/unity/exporters.py)
- [RPy-extrcactor/extraction_types/unity/manifest.py](RPy-extrcactor/extraction_types/unity/manifest.py)
- [RPy-extrcactor/extraction_types/unity/verify.py](RPy-extrcactor/extraction_types/unity/verify.py)

8. Frontend
- [RPy-extrcactor/web/index.html](RPy-extrcactor/web/index.html)
- [RPy-extrcactor/web/app.js](RPy-extrcactor/web/app.js)
- [RPy-extrcactor/web/styles.css](RPy-extrcactor/web/styles.css)

9. Core models/config/logging
- [RPy-extrcactor/models.py](RPy-extrcactor/models.py)
- [RPy-extrcactor/startup.py](RPy-extrcactor/startup.py)
- [RPy-extrcactor/logging_utils.py](RPy-extrcactor/logging_utils.py)

## Streamlined Module Responsibilities

This repo is now organized by responsibility boundaries:

- [RPy-extrcactor/extract.py](RPy-extrcactor/extract.py)
Purpose: protocol and route wiring only.

- [RPy-extrcactor/handlers.py](RPy-extrcactor/handlers.py)
Purpose: endpoint business logic and request validation.

- [RPy-extrcactor/extraction.py](RPy-extrcactor/extraction.py)
Purpose: generic archive/file extraction utilities, independent of UI.

- [RPy-extrcactor/extraction_types/unity_extractor.py](RPy-extrcactor/extraction_types/unity_extractor.py)
Purpose: Unity flow orchestration only (discovery, exporter calls, manifests, verification).

- [RPy-extrcactor/extraction_types/unity/exporters.py](RPy-extrcactor/extraction_types/unity/exporters.py)
Purpose: Unity tooling integration and export backends:
  - UnityPy export path.
  - External tool adapters (AssetRipper/UABEA).

- [RPy-extrcactor/startup.py](RPy-extrcactor/startup.py)
Purpose: startup dependency preflight checks and best-effort installers.

## Dependency Preflight

Startup preflight is executed before server start in [RPy-extrcactor/extract.py](RPy-extrcactor/extract.py).

Required:

- `unrpa` Python module.

Optional (recommended):

- `7z`/`7za`/`7zr`.
- `unrar`.
- `UnityPy` Python module (for native Unity object export).
- `AssetRipper` CLI (fallback/expanded Unity extraction path).
- `UABEA` CLI (fallback/advanced Unity handling path).

Implementation:

- [RPy-extrcactor/startup.py](RPy-extrcactor/startup.py)

## Archive Support

Archive suffixes and extraction support live in [RPy-extrcactor/models.py](RPy-extrcactor/models.py) and [RPy-extrcactor/extraction.py](RPy-extrcactor/extraction.py).

Supported archive inputs include:

- `.rpa`
- `.zip`
- `.tar`
- `.tar.gz` / `.tgz`
- `.tar.bz2` / `.tbz` / `.tbz2`
- `.tar.xz` / `.txz`
- `.7z`
- `.rar`
- `.unitypackage`

Notes:

- `.unitypackage` is handled as a gzipped tar archive.
- `.7z` and `.rar` rely on external tools where needed.

## Unity Extraction Pipeline

Primary flow:

1. Detect Unity project markers.
2. Build discovery index of Unity containers.
3. Export assets with UnityPy when available.
4. Attempt fallback exports via AssetRipper/UABEA if available.
5. Run core generic extraction flow for archive/file traversal.
6. Emit manifests and completeness reports.

Key files:

- [RPy-extrcactor/extraction_types/unity_extractor.py](RPy-extrcactor/extraction_types/unity_extractor.py)
- [RPy-extrcactor/extraction_types/unity/discovery.py](RPy-extrcactor/extraction_types/unity/discovery.py)
- [RPy-extrcactor/extraction_types/unity/exporters.py](RPy-extrcactor/extraction_types/unity/exporters.py)
- [RPy-extrcactor/extraction_types/unity/verify.py](RPy-extrcactor/extraction_types/unity/verify.py)

Current UnityPy export targets:

- Images (`Texture2D`, `Sprite`) to `.png`.
- Audio (`AudioClip`) to sample-provided extension or fallback bytes.
- Text (`TextAsset`) to `.txt`.
- Mesh (`Mesh`) to `.obj` when supported by object exporter.

## API Reference (Current)

GET:

- `/api/state`
- `/api/status`
- `/api/extensions`
- `/api/detected-extensions`
- `/api/logs`
- `/api/open-log-dir`
- `/api/logs/load`
- `/api/open-folder?path=...`
- `/api/assets-window?offset=...&limit=...`
- `/api/assets-window-preview?path=...`
- `/api/session`
- `/api/browse-folder`
- `/preview/...`

POST:

- `/api/extract`
- `/api/scan`
- `/api/keep-selected`
- `/api/trash`
- `/api/restore`
- `/api/delete`
- `/api/clear-trash`
- `/api/resume`
- `/api/assets-preview`
- `/api/sort-keep`
- `/api/sort-trash`
- `/api/sort-undo`
- `/api/sort-rename`
- `/api/logs/clear`
- `/api/save-remaining-assets`

## Frontend UX Summary

Three-step accordion flow:

1. Extract game archives.
2. Scan and select extensions.
3. Continue in sorting window.

Sorting window highlights:

- Fast list navigation and media preview.
- Keep/trash/undo operations.
- In-place rename of selected file name with Enter-to-apply.
- Local-state interaction optimizations to reduce latency after actions.

Keyboard shortcuts:

- Up/Down: navigate
- Right: keep
- Left: trash
- Ctrl+Z: undo
- S: save remaining
- T: clear trash
- Space: media play/pause

## Configuration

Config file:

- [RPy-extrcactor/config.json](RPy-extrcactor/config.json)

Fields:

- `host`
- `port`
- `tempPath`
- `outputDir`
- `webDir`
- `logDir`

Rules:

- Relative paths are resolved from `RPy-extrcactor`.
- Log directory is created automatically.

## Run Instructions

From repository root:

1. Ensure Python 3.10+ is installed.
2. Start app:

```bash
python Start.py
```

3. Open configured URL (default `http://127.0.0.1:8080`).

## Development Guidelines

- Keep protocol wiring in [RPy-extrcactor/extract.py](RPy-extrcactor/extract.py), not in strategy modules.
- Keep Unity tool invocation details in [RPy-extrcactor/extraction_types/unity/exporters.py](RPy-extrcactor/extraction_types/unity/exporters.py).
- Keep startup dependency behavior in [RPy-extrcactor/startup.py](RPy-extrcactor/startup.py).
- Prefer additive extractor strategies over branching endpoint logic.

## Troubleshooting

1. Startup exits before server boot
- Check terminal preflight output.
- Validate Python executable and pip availability.

2. Unity extraction reports missing UnityPy
- Install manually: `python -m pip install UnityPy`
- Re-launch app to rerun preflight.

3. AssetRipper/UABEA not detected
- Ensure executables are in PATH.
- Use exact CLI binary names or add a wrapper script in PATH.

4. Archive extraction failures
- Install/verify 7zip and unrar.
- Confirm source files are not locked by another process.

## License

No repository license file is currently present.
Default assumption remains all rights reserved unless stated otherwise by the author.
