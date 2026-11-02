# 7. v1 findings and migration map (draft 3)

## 7.1 Findings from reading v1

Every finding below was checked against the code twice: once while drafting,
and once by an independent review (file:line given). Severity is an estimate.
The table is ordered by severity. **H1–H3 are serious enough to fix in v1
right away (roadmap M1), before any refactor.**

| # | Finding | Evidence | Severity | Status |
|---|---------|----------|----------|--------|
| **H1** | **Extraction moves files out of the user's game folder.** COLLECT walks `<game>/game` (or `<game>` itself) and calls `shutil.move` on every selected file. One extraction empties a Ren'Py `game/` folder. | `file_ops.collect_source_roots` (`file_ops.py:124-132`), `move_one` → `shutil.move` (`file_ops.py:64`), `pipeline.py:83-100`; real game path from `extraction_handlers.py:29,40` | **critical, data loss** | confirmed |
| **H2** (was F7) | **Re-extraction deletes a user-chosen folder.** Step 2 `/api/scan {assetPath}` makes any folder the session workspace; Step 1 then runs `rmtree` on it in PREPARE. The UI does send `assetPath`. | `extraction_handlers.py:73-74` → `common.py:15-21,37` → `pipeline.py:58`; `app.js:1466` | **critical, data loss** | confirmed |
| **H3** | **Cross-site requests can trigger H2.** Only `/api/open-folder` checks Origin. Request bodies are parsed as JSON whatever the Content-Type, so another website can send a "simple" `text/plain` POST without a CORS preflight. Static files are served from an unchecked joined path (`..` traversal through raw requests). | `extract.py:312,321` (origin), `extract.py:294` (static path) | **high, security** | confirmed (exploitability through a browser: likely for the POSTs; for the static traversal, local requests only) |
| F1 | Unity exports are written into the output folder, then PREPARE `rmtree`s it. The deleted exports are still counted. | `exporters.py:85-92,201`; `pipeline.py:58`; `unity_extractor.py:81` | high | confirmed |
| F17 | `tarfile.extractall` / `zipfile.extractall` without filters, so path traversal (zip-slip) is possible on Python < 3.14. No Python version is declared anywhere. | `archive.py:79,94,97` | high, security | confirmed |
| F11 | The Unity completeness check counts containers as "discovered", and the gate passes when `extracted >= discovered`, so it **effectively always passes**. | `discovery.py:232`; `verify.py:30` | medium | confirmed (understated before) |
| F2 | The Unity marker `"mainData"` can never match (lowercased comparison). A `*_Data` folder alone gives 0.92. | `detector.py:12,29,35-40` | medium | confirmed |
| F3 | Only `.trash` is filtered, so `.extraction_metadata` leaks into the extension lists, and "keep selected" would trash it. (Unity's `images/` and `*_export/` would leak too once F1 is fixed.) | `sorting.py:182`; `sorting_handlers.py:69`; merger `service.py:124`; `extraction_handlers.py:188-209` | medium | confirmed (corrected) |
| F18 | **Three** trash layouts share `.trash/`: groups (`<ext>_N`), sorting items (`<ext>/<file>`) and the merger (`media-merger/`). Group restore matches names by prefix, so it can pick up item-trashed files. | `sorting.py:36`; `media_merger/service.py:350` | medium | confirmed |
| F4 | Preflight finds 7-Zip in Program Files, but the archive code only looks in PATH. | `startup.py:90-119` vs `archive.py:44-55` | medium | confirmed |
| F5 | unrpa is required at boot for every game type. | `startup.py:253`; `extract.py:329-331` | medium | confirmed |
| F19 | Boot pip-installs **unpinned** packages (supply-chain and reproducibility risk). | `startup.py:50-57` | medium | confirmed |
| F6 | Collect dedupe uses name + size + mtime (seconds); same-looking files with different content are dropped. | `file_ops.py:48-57` | medium | confirmed in code; real-world impact unclear |
| F20 | `/preview/` always serves from `tempPath/outputDir`, never the session workspace. | `extract.py:385` | low | confirmed |
| F8 | v1's three guessed UABEA/AssetRipper invocations can't work: UABEA's CLI uses `batchexportbundle`…, and AssetRipper's headless mode is an HTTP server. | `exporters.py:204-208`; doc 13 | low | confirmed |
| F9 | "Permanently deleted (N files)" counts files after deletion, so N is always 0. | `sorting.py:165-166` | low | confirmed |
| F10 | The UI never sends `extractionType`. | `app.js:1396` | low | confirmed |
| F12 | Engine knowledge sits in core (`.rpa`, `.unitypackage`, Ren'Py `game/`). | `archive.py:16,77,106`; `file_ops.py:127`; `pipeline.py:61-65` | design | confirmed |
| F13 | OS-specific code is spread across modules: `common.py:112`, tkinter dialogs (`session_handlers.py:12`, `media_merger_handlers.py:53`), `startup.py:99-106`, `.exe` names in `export_phase.py:56,73`. (The merger has **no** OS branching, despite what draft 1 said.) | as listed | design | corrected |
| F14 | Three `tlog` definitions with two behaviors (`sorting.py:9` only prints). | `startup.py:11`, `runtime.py:9`, `sorting.py:9` | low | confirmed |
| F15 | Session log append is read-modify-write. Lines can only be lost if the session is replaced at the same moment. | `extract.py:417-427` | low | plausible, narrow |
| F16 | The "SLICE6 … optimized" log line describes nothing real. | `unity_extractor.py:111` | low | confirmed |

**What this means for the contract:**
- H1: COLLECT **copies** from the game folder and only **moves** from staging (doc 3.1).
- H2: the workspace needs an ownership marker (doc 4.3).
- H3: the HTTP API needs a security model (doc 4.1).
- F17: every unarchive backend gets a traversal test (doc 17.3).
- F18: the three trash layouts become explicit (doc 0, doc 4.3).

## 7.2 Where each v1 file goes (proposed)

| v1 | Target |
|----|--------|
| `Start.py` | thin wrapper for `viwo serve`, passing its flags through (doc 12.4) |
| `extract.py` (config, Handler, routes) | `api/server.py` + `api/routes.py`; config loading → `core/wiring/` (config.json for server/paths + the startup ini) |
| `models.py` | value types → `contracts/`; state → `core/state.py`; extension sets → `core/media_types.py` |
| `startup.py` | tool location → `os/*`; dependency registry and boot → `core/wiring/` |
| `logging_utils.py` | `core/logging.py` |
| `extraction_core/runtime.py` | `os/*/process.py` |
| `extraction_core/archive.py` | unpack loop → `core/pipeline/unpack.py`; zip/tar/7z/rar → `backends/`; rpa → `plugins/renpy`; unitypackage → `plugins/unity` |
| `extraction_core/file_ops.py` | `core/pipeline/collect.py` (copy from game, move from staging) + `core/workspace/` |
| `extraction_core/pipeline.py`, `extraction_types/{base,registry,orchestrator,detector}.py` | `contracts/` + `core/pipeline/` + `core/wiring/registry.py`; markers move into plugins |
| `extraction_types/renpy_extractor.py` | `plugins/renpy/` |
| `extraction_types/unity*` | `plugins/unity/` |
| `sorting.py`, `api/sorting_handlers.py` | `core/workspace/curation/` + thin API |
| `media_merger/*` | `core/merger/` + thin API; ffmpeg via `media.*` slots; merger build becomes a job |
| `api/common.py` | `core/workspace/`; explorer → OS layer shell |
| — (new) | `cli/`, `core/jobs/`, later `core/sanitizer/`, `core/capture/` |
| `web/*` | unchanged, except the security token (doc 4.1) |

## 7.3 Order of work

See **doc 16 (roadmap)**. In short: hotfix H1–H3/F17 in v1 → characterization
tests against the *intended* behavior → lean core → one engine at a time.
