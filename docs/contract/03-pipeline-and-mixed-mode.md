# 3. Pipeline, routing and mixed mode

## 3.1 Stages (proposed order)

| Stage | Owner | What happens | v1 equivalent |
|-------|-------|--------------|---------------|
| PREPARE | core | clear and create the output dir, create `staging/<plugin_id>/` and `scratch/` | `pipeline.extract_assets` PHASE 0 |
| PROBE | core | build one GameProbe | — (was an rglob per marker set) |
| DETECT | core + plugins | call `detect()` on every enabled plugin, then `select_plugins()` | `detector.detect_engine` + `orchestrator` |
| INVENTORY / CATALOG | plugins | `inventory()` for the selected plugins. Draft 2: optionally a browsable **catalog** the user or CLI selects from, for huge games (CASC, big Unreal) ❓ D12 | Unity discovery phase |
| UNPACK | core + `unarchive.*` slots | identify (head + tail, carving embedded containers), then recursive unpack. After an outer *wrapper* (Electron/NW.js) is unpacked, detection runs once more; each file goes to the matching slot's main, then spare (doc 8) | PHASE 1 `extract_archives` |
| EXPORT | plugins | `export()` for each selected plugin, into its own staging folder | Unity export phase |
| COLLECT | core | move files from the source roots and staging folders into the `<ext>/` layout, filtered by `selected_exts`, with the v1 dedupe and collision rules | PHASE 2 scan + `move_one` |
| VERIFY | core + plugins | `logic_check_summary` warnings, then `verify()` | PHASE 3 + Unity verification phase |
| SANITIZE | core + rules | optional recipe; only plans, unless the request asks to apply automatically | — (doc 5) |
| REPORT | core | write manifests to `.extraction_metadata/` and build the result | Unity manifest phase |

ANALYZE (decompilers) is **never** part of an extraction. It runs as a
separate job (doc 6).

Every stage sends progress events with `stage` set, and checks the cancel
token between files. The v1 progress line format is kept (doc 4).

## 3.2 Request

```text
ExtractionRequest
  game_path
  selected_exts       frozenset[".png", ...] | None
  mode                auto | single | mixed
  plugins             (ids...)
  mixed_policy        selected | detected | all
  mixed_threshold     default 0.50
  plugin_options      { plugin_id: { key: value } }
  sanitize_recipe     "" = skip
  sanitize_auto_apply false
```

How the v1 payload maps onto it (v1 always sends `{gamePath, selectedExts: null}`):

| Payload `extractionType` | Mode | Plugins |
|--------------------------|------|---------|
| missing, `""`, `"auto"` | auto | — |
| `"<plugin id>"` | single | that id |
| `"mixed"` | mixed | from the new `plugins` field; `mixedPolicy` defaults to `selected` |

## 3.3 Plugin selection (proposed)

Input: one DetectionResult per **enabled** plugin, plus each plugin's priority.

1. Sort all detections by confidence (highest first), then priority (highest first), then plugin id (alphabetical). This is the run order and doesn't depend on the order plugins were registered.
2. Choose plugins by mode:
   - **auto**: the best plugin other than `generic`, if its confidence is above 0.
   - **single**: the requested id, if it's enabled.
   - **mixed / selected**: the requested ids, in run order.
   - **mixed / detected**: every plugin with confidence ≥ threshold.
   - **mixed / all**: every enabled plugin.
3. If nothing was chosen: use `generic` if it's enabled, otherwise the best plugin. **The result is never empty.**

The v1 behavior is kept: Unity at 0.92 beats RenPy at 0.78, and when nothing
matches, generic runs.

## 3.4 Mixed mode semantics

- **Unpack:** the `unarchive.*` slots of all chosen plugins are combined. If two plugins claim the same suffix, the ini decides; if the ini says nothing, it's reported as a configuration problem at boot ❓ (open: should magic-byte sniffing break the tie instead?).
- **Export:** each plugin exports into its own `staging/<id>/`, so plugins can't overwrite each other's output.
- **Collect:** core collects once from all source roots and all staging folders, de-duplicating source roots that overlap (using `kernel.fs.path_key`). Duplicate files are resolved with the v1 rule (same size and mtime means skip; otherwise `name__N.ext`).
- **Failure isolation:** if one plugin fails during export or verify, it's recorded in `plugins[i].error` and the other plugins still run. The run counts as successful if COLLECT completes.
- **Result:** `extractorType: "mixed"`, `detection` comes from the first plugin in run order, and each plugin gets its own entry in `plugins[]`. Plugin-specific top-level keys (such as Unity's `qualityGatePass`) are **only** merged into the top level in single or auto mode.

## 3.5 Result payload

`result` in `/api/extract` contains every v1 key plus some new ones:

```text
v1 (kept):    success archivesFound archivesExtracted scannedFiles copiedFiles
              copiedByExt checks{ok,warnings} logs extractorType detection{type,confidence,evidence}
v1 Unity extras (single/auto only): discoveredCount extractedCount unresolvedCount
              unresolvedByReason qualityGatePass completenessReport manifestsPath
              unityExportedCount unityExportedByType
new:          contractVersion mode manifestsPath
              plugins[] { id detection exported exportedByKind exportedByTool
                          inventoryCount verifyPassed warnings error }
```

## 3.6 Combination test matrix ("testing every combination")

The conformance suite runs:

```
kernels   (linux, windows fakes)                                   2
x fixtures (renpy, unity, unreal, godot, empty, + mixed-folder)    6
x plugin subsets: every non-empty subset of
  {generic, renpy, unity, unreal, godot, sample-custom}            63
x mixed policies (selected, detected, all)                         3
                                                         = 2268 cases
```

Checked for every case:

1. The selection is not empty, has no duplicates, and only contains plugins from the subset.
2. With `selected` and `all`, the selection equals the whole subset.
3. Run order doesn't change when detections arrive in a different order.
4. Slot and backend ids never clash within the selected set.
5. The pipeline, run with fake backends on a temporary folder, only writes to `staging/<id>/` and the output dir. This is checked with a before/after record of the files.
6. `result` contains every v1 key (3.5), and `plugins[]` has one entry per selected plugin.
7. Running the same request twice gives the same output tree (names and sizes).

Fixtures are small synthetic folders that contain only the marker files and
tiny archives. No real game data goes into the repository.
