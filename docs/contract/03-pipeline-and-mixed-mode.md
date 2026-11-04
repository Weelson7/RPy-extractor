# 3. Extraction pipeline, routing and mixed mode

## 3.1 Stages

`viwo/core/pipeline/runner.py` runs these in order (`contracts/pipeline.py` `Stage` names them).
Every stage sends progress events with its stage name and checks the cancel token between files.

| Stage | Owner | What happens |
|-------|-------|--------------|
| PREPARE | core | resolve the workspace by the ownership rule (doc 4.3); refuse a workspace or temp folder inside the game folder (`pipeline/guard.py`); snapshot the game folder; create staging and scratch |
| PROBE | core | build one `FolderProbe` |
| DETECT | core + plugins | `detect()` on every enabled plugin, then `select_plugins()` (3.3) |
| UNPACK | core + `unarchive.*` slots | identify each file (suffix, magic, head and tail, embedded chunks), unpack recursively to depth 10; each archive goes to its slot's main, then spare (doc 8.2) |
| EXPORT | plugins | each selected plugin's `export_slot()` into its own staging folder (`pipeline/export.py`). After a wrapper (`.asar`, `package.nw`) is unpacked, detection reruns once on its content; the strongest engine there (confidence >= `mixed_threshold`, not already selected) exports from it |
| CARVE | core | the signature carver over files nothing else recognized (`carve = unknown`, default) or every file (`all`), skipping suffixes an exporter claims; archives found inside are unpacked |
| COLLECT | core | **copy** from the game's source roots and **move** only from staging into the `<ext>/` layout, filtered by `selected_exts` on what ends up in the workspace (a source a bound decoder turns into a chosen type is collected and decoded first; the files of other types are then left out and counted in one warning); dedupe by size and content hash; collision names `name__N.ext`; write the provenance map. A file the OS refuses to read is skipped and named in a warning. DECODE runs inside COLLECT: `decode.*` slots write viewable copies next to the originals (`--option core.decode=off`, `core.decode_video=on` for Bink) |
| VERIFY | core + plugins | archive and game-folder checks (a changed game folder is a warning), then each plugin's `verify_report()` |
| REPORT | core | run record in `.extraction_metadata/runs/<job id>.json`, the result (3.5) |

Analysis is never a stage of an extraction (doc 6). The sanitizer is a separate tool (doc 5).

## 3.2 Request

```text
ExtractionRequest
  game_path, workspace
  selected_exts       frozenset[".png", ...] | None
  mode                auto | single | mixed
  plugins             (ids...)
  mixed_policy        selected | detected | all
  mixed_threshold     0.5
  plugin_options      { plugin_id: { key: value } }      CLI --option plugin.key=value
  on_existing         ask | new | replace | cancel       doc 4.3
  carve               unknown | all | off
```

The `/api/extract` payload maps onto it (`viwo/api/app.py`): `gamePath`, `selectedExts`,
`extractionType` (missing/`""`/`auto` = auto; a plugin id = single; `mixed` = mixed with
`plugins`), `mixedPolicy`, `pluginOptions`, `onExisting`, `carve`.

## 3.3 Plugin selection (`viwo/core/pipeline/select.py`, a pure function)

1. Run order: confidence (highest first), then priority (highest first), then plugin id.
2. By mode:
   - **auto:** the best plugin other than `generic` with confidence above 0;
   - **single:** the requested id;
   - **mixed / selected:** the requested ids, in run order;
   - **mixed / detected:** every plugin with confidence >= threshold;
   - **mixed / all:** every enabled plugin.
3. An unknown or disabled id in single or mixed mode is refused with `invalid_request` (exit 2).
4. If nothing was chosen: `generic` if enabled, else the best plugin. The result is never empty.

## 3.4 Mixed mode

- **Unpack:** the `unarchive.*` slots of all enabled plugins are combined. Two plugins claiming
  one suffix is a boot problem naming the winner (longest suffix, then registration order); the
  ini decides by switching one plugin off.
- **Export:** each plugin exports into its own `staging/<id>/`.
- **Collect:** once, from all source roots (overlaps removed with `os.fs.path_key`) and all
  staging folders.
- **Failure isolation:** a plugin failing in export or verify is recorded in `plugins[].error`
  and its warnings; the others still run. The run succeeds when COLLECT completes.
- **Result:** `extractorType: "mixed"`; `detection` from the first plugin in run order; one
  `plugins[]` entry per selected plugin.

## 3.5 Result payload

`result` of `/api/extract`, `viwo extract --json` and the run record (`ExtractionResult.to_legacy_dict`):

```text
success archivesFound archivesExtracted scannedFiles copiedFiles copiedByExt
checks{ok, warnings} logs extractorType detection{type, confidence, evidence}
mode byBackend runRecord workspace carvedFiles movedFiles inventoryItems
collectedFromInventory contractVersion manifestsPath error?
plugins[] { id detection exported exportedByKind exportedByTool inventoryCount
            verifyPassed backend warnings error }
```

Meanings in doc 0.4. The first ten keys are the v1 set (`LEGACY_RESULT_KEYS`) and are always
present.

## 3.6 Combination testing

| What | How | Where |
|------|-----|-------|
| Selection, every combination | every non-empty subset of the plugins x the three policies x synthetic detections, plus property tests with random confidences | `tests/test_mixed.py` |
| Pipeline, pairwise | real runs with fake backends for every pair of plugins and each single plugin | `tests/test_mixed.py` |
| OS layers | the suite runs on the Linux and Windows CI runners; tools are faked, the OS layer never is | `tests/test_os_layer.py` |

Invariants checked in pipeline runs: the selection is non-empty, has no duplicates and stays
inside the subset; run order does not depend on arrival order; writes happen only under staging
and the workspace and the game folder's hashes are unchanged; `result` holds every v1 key and one
`plugins[]` entry per selected plugin; a re-run gives an identical workspace.
