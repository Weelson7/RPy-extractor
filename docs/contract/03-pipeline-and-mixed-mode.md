# 3. Pipeline, routing and mixed mode

## 3.1 Stages (normative since 1.1)

> **History.** Draft 3 proposed INVENTORY/CATALOG and an in-pipeline SANITIZE stage. Decision
> (D12, 1.1): there is no INVENTORY stage; UNPACK identification plus the EXPORT stage cover it,
> and `plugins[].inventoryCount` reports what each export saw. The sanitizer is a separate tool
> (doc 5: `viwo sanitize`, 08 CLEANUP), never a stage of an extraction. The table below is the
> implemented order (`contracts/pipeline.py` `Stage`).

| Stage | Owner | What happens | v1 equivalent |
|-------|-------|--------------|---------------|
| PREPARE | core | resolve the target workspace by the **ownership rule** (doc 4.3): never clear a folder without the workspace marker; create `staging/<plugin_id>/` and `scratch/` | PHASE 0 (v1 `rmtree`s whatever the session points at: H2) |
| PROBE | core | build one GameProbe | — (was an rglob per marker set) |
| DETECT | core + plugins | call `detect()` on every enabled plugin, then `select_plugins()` | `detector.detect_engine` + `orchestrator` |
| UNPACK | core + `unarchive.*` slots | identify (head + tail, carving embedded containers), then recursive unpack. After an outer *wrapper* (`.asar`, `.nw`) is unpacked, detection runs once more on its content and the strongest engine found there (confidence ≥ `mixed_threshold`, not already selected) exports from it (one pass, never nested); each file goes to the matching slot's main, then spare (doc 8) | PHASE 1 `extract_archives` |
| CARVE | core | signature carver over unknown blobs (D21), then the archives it finds are unpacked | — |
| EXPORT | plugins | `export()` for each selected plugin, into its own staging folder | Unity export phase |
| COLLECT | core | **copy** from game-folder source roots and **move** only from staging, into the `<ext>/` layout, filtered by `selected_exts`, with v1 collision naming. Dedupe: same size **and** same content hash → skip (fixes F6). Also writes the **provenance map** (doc 18.2). DECODE (viewable copies through the `decode.*` slots) runs inside COLLECT | PHASE 2 (v1 *moves* out of the game folder: H1) |
| VERIFY | core + plugins | `logic_check_summary` warnings, then `verify()` | PHASE 3 + Unity verification phase |
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
  on_existing         ask | new | replace | cancel   (doc 4.3)
  carve               unknown | all | off            (D21)
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
- **Collect:** core collects once from all source roots and all staging folders, de-duplicating source roots that overlap (using `os.fs.path_key`). Duplicate files are resolved by content: same size **and** same hash means skip; otherwise `name__N.ext` (doc 4.3, F6).
- **Failure isolation:** if one plugin fails during export or verify, it's recorded in `plugins[i].error` (and repeated in its `warnings`) and the other plugins still run; `plugins[i].verifyPassed` is false when its `verify()` returned warnings. The run counts as successful if COLLECT completes.
- **Result:** `extractorType: "mixed"`, `detection` comes from the first plugin in run order, and each plugin gets its own entry in `plugins[]`. There are no plugin-specific top-level keys (the v1 Unity extras were removed with the fake completeness gate, F11).

## 3.5 Result payload

`result` in `/api/extract` contains every v1 key plus some new ones:

```text
v1 (kept):    success archivesFound archivesExtracted scannedFiles copiedFiles
              copiedByExt checks{ok,warnings} logs extractorType detection{type,confidence,evidence}
removed (F11): the v1 Unity extras (discoveredCount, qualityGatePass, completenessReport, ...)
new:          contractVersion mode manifestsPath (= <workspace>/.extraction_metadata)
              workspace runRecord byBackend carvedFiles
              plugins[] { id detection exported exportedByKind exportedByTool backend
                          inventoryCount verifyPassed warnings error }
```

## 3.6 Combination testing ("testing every combination"), right-sized

Draft 2 proposed 2,268 full pipeline runs. The review pointed out that plugin
**selection is a pure function**, so every combination can be covered far
more cheaply:

| What | How | Size |
|------|-----|------|
| **Selection: every combination** | exhaustive over every non-empty subset of the enabled plugins × the 3 mixed policies × synthetic detection results. Pure function, no I/O; there are also property tests (with random confidences, the rules in 3.3 always hold) | 63 subsets × 3 policies × fixtures: milliseconds |
| **Pipeline: pairwise** | real pipeline runs (fake backends, temporary folders) for every **pair** of plugins plus each single plugin, on the mixed fixture and on each plugin's own fixture | about 21 runs per OS layer |
| **OS layers** | every selection and pipeline test runs on the Linux and Windows CI runners (real OS layers), plus a fake-OS run of the fast tests on each runner | 2 runners |

Invariants checked in every pipeline run:

1. The selection is not empty, has no duplicates, and stays inside the subset. With `selected`/`all` it equals the subset.
2. Run order doesn't depend on the order detections arrive in.
3. Slot and backend ids never clash within the selection.
4. Writes happen only under `staging/<id>/` and the workspace. **The game folder's file hashes are unchanged** (H1).
5. `result` contains every v1 key (3.5), and `plugins[]` has one entry per selected plugin.
6. A re-run gives an identical workspace (names, sizes, hashes).

The `sample-custom` plugin in these tests is a minimal test plugin loaded
through the custom-plugin loader. The real showcase plugin (doc 14) has its
own tests.
