# 7. Data-safety rules

The rules that protect the user's game and data, each with the v1 finding (`H*`, `F*`) it
answers; code cites these ids. The v1 application is gone; its findings stay as the reason for
each rule.

## 7.1 Rules

| Rule | Where | Answers |
|------|-------|---------|
| The game folder is never written by extraction: COLLECT copies from it and moves only from staging; every run snapshots it before and after and a difference is a warning | `core/pipeline/collect.py`, `core/pipeline/guard.py` | H1 (v1 moved files out of the game) |
| A workspace or temp folder inside the game folder is refused before anything is written | `core/pipeline/guard.py` `refuse_writes_inside` | H1 |
| Only a folder holding the `.viwo-workspace` marker is ever cleared or replaced | `core/workspace.py` | H2 (v1 deleted a user-chosen folder) |
| The HTTP API needs the per-start token, JSON bodies and an allowed Host; static and preview paths are contained | `api/server.py` (doc 4.1) | H3 (cross-site requests, static traversal) |
| Every write into a folder built from untrusted names goes through `contracts.workspace.safe_member` and `inside` (traversal, absolute paths, drive letters, links, devices); tar links are filtered | `contracts/workspace.py`, `backends/archives.py` | F17 (zip-slip) |
| Exports go to staging, never into the workspace PREPARE clears | `core/pipeline/export.py` | F1 |
| Reserved dot-folders are never listed, counted or trashed | `contracts/workspace.py` `is_reserved` | F3 |
| One tool locator serves the status check and the calls | `os/_shared.py` `Locator` | F4 |
| Collect dedupe compares size and content hash | `core/pipeline/collect.py` | F6 |
| Counts say what they count; no completeness gate without a real inventory | `contracts/pipeline.py` (doc 0.4) | F9, F11 |
| Engine knowledge lives in plugins, OS code in the OS layer | doc 2, doc 1 | F12, F13 |
| Three explicit trash areas; v1 trees migrated on first open | `core/curation/trash.py` | F18 |
| `/preview/` serves from the active workspace | `api/server.py` | F20 |
| Tools come from pinned, checksummed downloads, never unpinned installs at boot | `core/thirdparty.py` (doc 10) | F19 |
| Pickled data (Ren'Py RPA indexes, `.rpyc`) is never unpickled freely in the ViWo process: the RPA reader allows only `_codecs.encode` and `bytes`; `.rpyc` is decompiled by unrpyc in its own process | `plugins/renpy/rpa.py`, `plugins/renpy/decompile.py` | D11 |
| Archives are never forced open: no password or key guessing; 7-Zip runs with `-p`, unrar with `-p-`, so neither prompts; an encrypted archive ends as `needs_key` | `backends/archives.py` | D18, D22 |
| Secrets and found keys are never logged or written to disk; run records store `<secret>` | `core/pipeline/runner.py`, `plugins/unreal/keys.py` | D18 |

## 7.2 Finding index

| Id | v1 defect |
|----|-----------|
| H1 | extraction moved files out of the game folder |
| H2 | re-extraction deleted a user-chosen folder |
| H3 | cross-site requests could trigger H2; static files served from an unchecked path |
| F1 | Unity exports were written into the output folder, then wiped and still counted |
| F3 | `.extraction_metadata` leaked into extension lists and "keep selected" trashed it |
| F4 | preflight found 7-Zip where the archive code did not look |
| F6 | dedupe by name, size and mtime dropped different files |
| F9 | "Permanently deleted (N files)" always said 0 |
| F11 | the Unity completeness gate always passed |
| F12, F13 | engine knowledge in core; OS code spread over modules |
| F17 | `extractall` without filters (zip-slip) |
| F18 | three trash layouts collided in one `.trash/` |
| F19 | unpinned pip installs at boot |
| F20 | `/preview/` served from the wrong folder |
