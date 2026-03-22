# RPy Extractor

RPy Extractor is a local-first, desktop-friendly asset extraction and curation tool for Ren'Py game content. It runs a Python HTTP server and serves a web UI for extraction, extension filtering, sorting/preview, trash management, and export flows.

This implementation is authored by Weelson and is part of the C.O.R.E. project.

## Ownership

- Author: Weelson
- Initiative: C.O.R.E.
- Repository root: this folder
- App runtime root: RPy-extrcactor (note the current folder name spelling)

## What It Does

RPy Extractor provides a 3-step pipeline:

1. Extract game archives from a selected game folder.
2. Scan and select extension groups to keep.
3. Continue in a sorting window for per-file preview and keyboard-driven triage.

Core capabilities include:

- Archive extraction from nested containers.
- Extension discovery and bulk curation.
- Per-asset preview for image/audio/video/text-like files.
- Keyboard-driven sort actions (keep/trash/undo).
- Saving remaining assets to a chosen destination.
- Activity log panel and file log folder integration.

## Current Runtime Model

- Launcher: Start.py (spawns the app server process).
- Server: RPy-extrcactor/extract.py
- Frontend: RPy-extrcactor/web/index.html + app.js + styles.css
- Config file: RPy-extrcactor/config.json

The server uses ThreadingHTTPServer and serves both static UI and JSON endpoints.

## Directory Structure

- Start.py: entrypoint script for launching the app server.
- RPy-extrcactor/config.json: host/port/path configuration.
- RPy-extrcactor/extract.py: HTTP routes and server lifecycle.
- RPy-extrcactor/handlers.py: API handler implementations.
- RPy-extrcactor/extraction.py: extraction and file movement pipeline.
- RPy-extrcactor/sorting.py: extension-level trash/restore/delete operations.
- RPy-extrcactor/startup.py: dependency preflight and installer checks.
- RPy-extrcactor/models.py: app/session state models and constants.
- RPy-extrcactor/logging_utils.py: shared console+file logging helper.
- RPy-extrcactor/web/: frontend application.
- RPy-extrcactor/logs/: runtime logs (generated).
- RPy-extrcactor/tmp/: runtime temporary and assets output path (generated).

## Configuration

Default config in RPy-extrcactor/config.json:

- host: 127.0.0.1
- port: 8080
- tempPath: ./tmp
- outputDir: ./assets
- webDir: web
- logDir: ./logs

Path behavior:

- Relative paths are resolved from RPy-extrcactor/.
- logDir is used for file-backed logs and explorer open actions.

## Dependency Preflight

At startup, the app checks:

- Required: unrpa module.
- Optional: 7z/7za/7zr CLI.
- Optional: unrar CLI.

Behavior notes:

- Missing unrpa blocks extraction requiring .rpa unpack.
- Missing unrar is non-fatal; 7zip may still handle most .rar files.

## Extraction and File Movement Semantics

Current behavior intentionally uses move semantics in extraction flow.

- Extracted/collected assets are moved into the output asset structure.
- Duplicate collisions are resolved with suffixing.
- Output is grouped by extension folder names.

This is not a copy-then-delete approach; it is direct movement where applicable.

## Sorting Window UX

Sorting and preview panel supports:

- Asset list + renderer workflow.
- Media preview controls:
  - Fullscreen
  - Speed selection
  - Additional quick action button (...)

Keyboard shortcuts:

- Arrow Up: previous asset
- Arrow Down: next asset
- Arrow Right: keep current asset
- Arrow Left: trash current asset
- Ctrl+Z: undo most recent keep/trash action
- S: save remaining assets to selected destination
- T: clear trash

## Activity Log Panel

- Toggleable with sorting panel in workspace accordion.
- Pulls from session logs endpoint.
- Includes controls:
  - Clear Log: clears in-memory session logs.
  - Load Log: opens configured logDir in system file explorer.

## API Surface (Current)

GET endpoints:

- /api/state
- /api/status
- /api/extensions
- /api/detected-extensions
- /api/logs
- /api/open-log-dir
- /api/open-folder?path=...
- /api/assets-window
- /api/assets-window-preview?path=...
- /api/session
- /api/browse-folder
- /preview/... (static media/content preview)

POST endpoints:

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
- /api/logs/clear
- /api/save-remaining-assets

## How to Run

From repository root:

1. Ensure Python 3.10+ is available.
2. Run:

   python Start.py

3. Open browser at:

   http://127.0.0.1:8080

If port/host is changed in config.json, use that value.

## Typical Workflow

1. Step 1 - Extract
   - Choose game folder.
   - Run extraction.
2. Step 2 - Scan and Select
   - Scan for extension types.
   - Keep selected extension groups.
3. Step 3 / Sorting Window
   - Preview and triage assets with shortcuts.
   - Save remaining assets when ready.

## Logging Model

Two log channels are used:

- Runtime file logs in logDir (daily file naming).
- Session/UI activity logs exposed via /api/logs.

The UI log panel is intended for operational feedback; file logs are for persisted diagnostics.

## Development Notes

- The app folder name is currently RPy-extrcactor in source paths.
- Backend and frontend are tightly coupled via explicit endpoints in extract.py and handlers.py.
- Most user actions are performed through API endpoints and reflected in session log stream.

## Troubleshooting

1. App exits immediately
   - Check startup preflight messages in terminal.
   - Ensure Python path is valid.
2. Extraction issues
   - Confirm unrpa installation was successful.
   - Verify game path exists and is readable.
3. Archive compatibility issues
   - Install 7zip and optionally unrar for wider archive support.
4. Logs not visible
   - Use Activity Log panel for session logs.
   - Use Load Log to open persisted log directory.

## C.O.R.E. Context

RPy Extractor is maintained as part of C.O.R.E. and should be treated as a production-oriented utility module in that ecosystem. Any changes to endpoint contracts, keyboard interactions, or movement semantics should be documented and versioned carefully because the current UI flow depends on those contracts.

## License

No license file yet, default to "All rights reserved" for now. Contact Weelson for permissions or contributions.
