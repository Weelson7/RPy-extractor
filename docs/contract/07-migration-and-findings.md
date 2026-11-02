# 7. v1 findings and migration map

## 7.1 Findings from reading v1

These come from reading the code, not from running it, and severities are my
estimate. Items marked *(to confirm)* follow logically from the code but
should be reproduced before anyone relies on them.

| # | Finding | Where | Severity | How the contract addresses it |
|---|---------|-------|----------|-------------------------------|
| F1 | Unity exports are written into the output folder, then `extract_assets` PHASE 0 runs `rmtree(output_dir)`. UnityPy/AssetRipper output is deleted before collection, yet still counted in `extractedCount`. | `unity_extractor.py` → `pipeline.extract_assets` | high | single writer; only PREPARE clears (README rule 1, doc 3.1) |
| F2 | The Unity marker `"mainData"` is compared with `name.lower()`, so it can never match. A `*_Data` folder on its own already gives 0.92 confidence. | `detector.py` | medium | GameProbe with case-insensitive matching; evidence-weighted confidence (doc 2.4) |
| F3 | Top-level folders other than `.trash` count as extension groups: `.extraction_metadata`, plus Unity's `images/`, `audio/`, `assetripper_export/`. The sorting window only filters `.trash`. | `sorting.list_kept_files`, `sorting_handlers` | medium | reserved dot-folders; Unity output goes into the extension layout (D3) |
| F4 | Preflight finds 7-Zip in Program Files, but the archive code only looks in PATH, so `.7z` shows as "available" and then fails. | `startup._check_7zip_installed` vs `archive.try_external_archive_extract` | medium | one ToolLocator (doc 1.2) |
| F5 | unrpa is required at boot for every game type; the app exits when it's missing, even for Unity. | `startup.startup_dependency_preflight` | medium | dependencies belong to plugins; `strict_preflight` (doc 9) |
| F6 | Collect dedupe compares name + size + mtime (seconds). Files from different archives with the same name, size and mtime, but different content, are silently dropped. Archives often store identical mtimes. | `file_ops.move_one` | medium *(to confirm with a real game)* | open question: compare content hashes when a file is a candidate duplicate |
| F7 | When Step 2 points at a custom folder, it becomes the session's assets path. A later Step 1 extraction would then `rmtree` **that** folder. | `scan_extensions` → `set_session_asset_path`; `extract_repo` → `assets_dir` → PREPARE | **high, data loss** *(to confirm in the app)* | PREPARE should only clear folders the app created; to be specified in the workspace contract |
| F8 | The UABEA call tries three guessed argument formats. I couldn't confirm UABEA has a command-line mode that accepts any of them. | `unity/exporters.export_with_external_tool` | low | doc 8.4 suggests dropping UABEA as a backend |
| F9 | "Permanently deleted X (N files)" counts files after deletion, so N is always 0. | `sorting.remove_from_trash` | low | — |
| F10 | The UI never sends `extractionType`, so users can't override a wrong detection. | `web/app.js` | low | `/api/detect` + selector (doc 4.1) |
| F11 | The Unity completeness ratio compares containers with files (see doc 0.4). The quality gate says nothing meaningful yet. | `unity/discovery`, `unity/verify` | medium | inventory semantics (doc 0.4) |
| F12 | Engine knowledge sits in core: `.rpa`, `.unitypackage` and the Ren'Py `game/` folder convention. | `extraction_core/*` | design | plugin-owned slots and source roots |
| F13 | OS-specific code is spread over 5 files (startup, common, two tkinter handlers, merger). | — | design | kernel layer |
| F14 | There are three different `tlog` functions; the one in `sorting.py` doesn't write to the log file. | `sorting.py` | low | one ProgressSink |
| F15 | Appending to the session log is a read-modify-write without a lock across the whole operation, under a threaded server. Lines could be lost. | `extract.Handler.progress_callback` | low *(possible)* | atomic append (doc 4.6) |
| F16 | The log line "SLICE6 … extractors scaled and optimized" describes work that doesn't exist. | `unity_extractor.py` | low | remove it |

## 7.2 Where each v1 file goes (proposed)

| v1 | Target |
|----|--------|
| `Start.py` | stays as the launcher; adds `--ini/--kernel/--profile` (doc 9) |
| `extract.py` (config, Handler, routes) | `api/server.py` + `api/routes.py`; config loading → `core/config.py` (config.json + ini) |
| `models.py` | contract value types → `contracts/`; state stores → `core/state.py`; extension sets → `core/media_types.py` |
| `startup.py` | split three ways: install/locate → `kernels/*`; dependency registry → `core/dependencies.py`; boot sequence → `core/boot.py` |
| `logging_utils.py` | `core/logging.py` (ProgressSink, file log) |
| `extraction_core/runtime.py` | `kernels/*/process.py` |
| `extraction_core/archive.py` | unpack loop → `core/unpack.py`; zip/tar/7z/rar → `backends/` (core slots); rpa → `plugins/renpy`; unitypackage → `plugins/unity` |
| `extraction_core/file_ops.py` | `core/workspace.py` (collect, layout, collisions) |
| `extraction_core/pipeline.py` | `core/pipeline.py` (stage runner) |
| `extraction_types/base.py`, `registry.py`, `orchestrator.py`, `detector.py` | `contracts/` + `core/registry.py` + `core/pipeline.py` (DETECT); markers move into each plugin |
| `extraction_types/renpy_extractor.py` | `plugins/renpy/` |
| `extraction_types/unity*` | `plugins/unity/` (discovery → inventory, exporters → backends, verify → verify) |
| `sorting.py`, `api/sorting_handlers.py` | `core/curation/` (group trash, item trash, sorting) + thin API |
| `media_merger/service.py` | `core/merger/`; ffprobe/ffmpeg via `media.*` slots |
| `api/common.py` | workspace resolution → `core/workspace.py`; explorer → kernel shell |
| `web/*` | unchanged for now |

## 7.3 Suggested order of work (each step leaves the app working)

1. **Agree on the semantics:** this document set, the glossary first. No code.
2. **Contracts package:** interfaces and value types only, plus contract self-tests with fakes. A draft exists outside the repository and is waiting on your review.
3. **Kernels:** move OS code from v1 into `linux` and `windows` kernels with no behavior change. Fixes F4 and F13 as a side effect.
4. **Workspace and stage runner:** core pipeline with the v1 behavior wrapped as the `generic` and `renpy` plugins. Characterization tests are captured against v1 first. Address F1, F3, F7.
5. **Slots and backends:** move the unarchive backends behind slots, with main and spare. Wire startup from the ini.
6. **Unity plugin port**, then the **mixed mode** matrix.
7. **New plugins:** Godot, then Unreal (Unreal needs the most research: IoStore, AES keys).
8. **Third-party vendoring** (doc 10), once its open problems are decided.
9. **Sanitizer phase 1**, then later phases. Analysis hooks last.

Before step 3, it would help to record **characterization tests** of v1
(the result payload and the workspace tree for small synthetic games), so the
migration can prove it didn't change behavior by accident.
