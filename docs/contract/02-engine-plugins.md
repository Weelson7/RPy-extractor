# 2. Engine plugin contract

A plugin describes **one engine**. It does not own the pipeline: core runs
the stages (doc 3) and calls the plugin's hooks. Only `manifest` and `detect`
are required. Every other hook does nothing by default, so the smallest
useful plugin is "detect, plus an unarchive slot and its backend".

## 2.1 Manifest

```text
PluginManifest
  plugin_id      lowercase slug [a-z][a-z0-9_-]{1,31}, unique
  name, version, description
  contract       "1.0"
  engine_type    value reported as detection.type / extractorType (v1 field)
  capabilities   {detect, unpack, export, inventory, verify, sanitize, analyze}
  priority       tie-breaker when detection confidence is equal
  dependencies   [DependencySpec]
  options        [PluginOption]     # the UI renders a form from these
  OS layers        {"*"} or a subset of {"linux","windows"}
  builtin        false for custom plugins

PluginOption { key, label, type: string|secret|bool|int|float|choice|path, default, choices, help }
```

Options of type `secret` (an Unreal AES key, a Godot encryption key) are never
logged and never written into manifests.

## 2.2 Hooks

```text
detect(probe: GameProbe) -> DetectionResult                      REQUIRED
slot_definitions() -> [SlotDefinition]                         default: []   (doc 8)
backends() -> [Backend]                                          default: []   (doc 8)
source_roots(game_root, probe) -> [Path]                         default: [game_root]
skip_dirs() -> [str]                                             default: []
inventory(ctx) -> Inventory | None                               default: None
export(ctx) -> ExportReport                                      default: empty
verify(ctx, inventory, export, collected) -> VerifyReport        default: passed
sanitizer_rules() -> [SanitizerRule]                             default: []   (doc 5)
analysis_targets(probe) -> [AnalysisTarget]                      default: []   (doc 6)
```

Rules:

- `detect` must be **fast and pure**: it only uses the probe, runs no tools and doesn't walk the folder tree itself. Calling it twice must give the same result.
- `export` writes **only** into `ctx.staging` (and temporary files into `ctx.scratch`). Core collects from staging afterwards.
- No hook deletes anything outside its own staging folder.
- Expected failures are reported through return values (`ExportReport.ok=false`, `fatal_error`). An exception means a bug; core catches it and turns it into a warning for that plugin.

## 2.3 Services core provides to plugins

```text
GameProbe            # built once per request, shared by all plugins
  root, truncated
  has_name(*names)              case-insensitive basename match
  find(pattern, limit)          case-insensitive glob ("**/*.pak", "*_Data")
  with_suffix(*suffixes)
  head(path, size=64)           cached first bytes, for magic checks
  tail(path, size=64)           cached last bytes (exe trailers: embedded Godot PCK, appended zips)
  # all reads are bounded; detect may read head/tail of a handful of files, never walk the tree

ExtractionContext    # per request and per plugin
  request_id, game_root, staging, scratch
  selected_exts (frozenset | None), options, detection
  probe, OS layer, progress, cancel
  log(message, level)
```

v1's `detect_engine` runs a full `rglob` (up to 50k files) for each set of
markers. The probe scans once with a file limit and every plugin reads from
it. That matters in mixed mode, where 5 or more plugins run detection.

## 2.4 DetectionResult (v1-compatible)

```text
DetectionResult { engine_type, confidence, evidence[], plugin_id }
to legacy JSON: { "type", "confidence", "evidence" }      # same as v1
```

Confidence scale (proposed):

| Range | Meaning |
|-------|---------|
| 0.00 | definitely not this engine |
| 0.01–0.49 | weak hints only |
| 0.50–0.74 | probable |
| 0.75–1.00 | strong (marker files or magic bytes) |

## 2.5 Unpacking: slots, not handlers

An earlier version of this draft had plugins return a priority-ordered list of
`ArchiveHandler` objects. Given the main + spare direction, unpacking now
follows the slot model in **doc 8**:

- A plugin **introduces slots** for its formats (`unarchive.rpa`, `unarchive.pck`, …) and **ships backends** for them. Core introduces the generic ones (`unarchive.zip`, `.tar`, `.7z`, `.rar`).
- Each slot has a main and an optional spare. Which backend fills each role comes from the ini (doc 9), with plugin defaults as the fallback.
- Core keeps v1's recursive unpack loop unchanged: a queue, a seen-set, an `archive_NNNNN_<uuid8>` subfolder per archive, nested-archive detection and the same log lines. For each file it looks up the matching slot (longest suffix first, then magic bytes) and asks that slot's backends.
- Every unarchive backend must prevent path traversal (zip-slip) in archive member names.

Which format belongs to whom (defaults in doc 8.4):

| Slot | Owner | v1 location |
|------|-------|-------------|
| `unarchive.zip`, `unarchive.tar` | core | `archive.try_python_archive_extract` |
| `unarchive.7z`, `unarchive.rar` | core | `archive.try_external_archive_extract` |
| `unarchive.rpa` | renpy | `archive.extract_single_archive` (**moved out of core**) |
| `unarchive.unitypackage` | unity | `archive.try_python_archive_extract` (**moved out of core**) |
| `unarchive.pck` | godot | new |
| `unarchive.pak`, `unarchive.iostore` | unreal | new |

## 2.6 Dependencies

```text
DependencySpec
  dep_id, label
  kind          python_module | executable | runtime
  requirement   required | recommended | optional
  import_name                       (python_module)
  executables   { os_id | "*": (names...) }
  packages      { "pip"|"winget"|"choco"|"scoop"|"apt"|...: package id }
  env_var, hint
```

Dependencies belong to whoever declares them: a plugin, a backend, a
sanitizer rule or an analyzer. `/api/dependencies` combines them all, and
`category` becomes the owner id. v1's hard-coded list in `startup.py` turns
into these declarations, so the tool-name lists that v1 duplicates between
`startup.py` and `unity/exporters.py` exist in only one place.

## 2.7 Built-in plugin specs (detection markers)

> Backend choices (main/spare) for every plugin live in **one place only: doc 8.4**. The "tools" column below is informational and defers to it.

| Plugin | Strong markers | Probable markers | Export tools | Notes |
|--------|----------------|------------------|--------------|-------|
| generic | — | always 0.4 (v1) | — | fallback; collects loose files and plain archives |
| renpy | `renpy/` folder, `*.rpa`, `script_version.txt`, `*.rpyc` | `renpy.exe`, `*.sh` + `lib/` | unrpa (required for .rpa), unrpyc (optional) | `source_roots`: `<game>/game` if it exists, else `<game>` (v1 `collect_source_roots`) |
| unity | `UnityPlayer.dll`/`.so`, `globalgamemanagers`, `data.unity3d`, `*_Data/level0`, UnityFS magic | `*_Data/` folder, `Managed/Assembly-CSharp.dll`, `il2cpp_data/` | UnityPy (required for export), AssetRipper, UABEA (optional) | v1 phases are kept as hooks: discovery → `inventory`, UnityPy/AssetRipper/UABEA → `export`, completeness → `verify` |
| unreal | `*/Content/Paks/*.pak`, `*.utoc`+`*.ucas`, `*-Win64-Shipping.exe`, `Engine/Binaries/` | `UE4PrereqSetup*`, `Engine/` folder | repak / UnrealPak (unpack), umodel (export textures/meshes/sounds) | options: `aesKey` (secret), `engineVersion` (choice) |
| godot | `*.pck` with `GDPC` magic, PCK embedded in the executable, `project.godot` | `.import/` or `.godot/imported/` | built-in PCK reader, godotpcktool, GDRE tools | turning `.ctex`/`.stex` into `.png` is a **sanitizer rule** (doc 5); option: `encryptionKey` (secret) |

## 2.8 Custom plugins

```text
<custom_dir>/<name>/plugin.json        # custom_dirs from the startup ini, e.g. user_plugins/ (not plugins/, which is the built-in layer)
{
  "id": "mygame", "name": "My Game Engine", "version": "0.1.0",
  "contract": "1.0", "entry": "mygame_plugin:MyGamePlugin"
}
```

- The `id` must not be one of `generic renpy unity unreal godot mixed auto`.
- `entry` has the form `module:ClassName`. The module is imported from the plugin's own folder, and the class's `manifest.plugin_id` must equal `id`.
- At load time, core validates the manifest, checks the contract version, runs the conformance checks (2.9) against an empty probe, and only then registers the plugin. If any step fails, the UI shows a load error for that plugin and the rest of the app carries on.
- **Trust model:** custom plugins run inside the app with the user's own permissions. They are loaded only from local folders listed in the startup ini (`custom_dirs`), never downloaded, and shown in the UI as non-builtin.

## 2.9 Plugin conformance checks

- The id matches the slug format, the contract version is compatible, `engine_type` is set, and `detect` is declared as a capability.
- Option keys and dependency ids are unique.
- A plugin that introduces `unarchive.*` slots declares the `unpack` capability. Slot and backend ids are unique, their `owner` is the plugin id, and suffixes are lowercase and dotted (more slot checks in doc 8.6).
- `detect()` never raises on any fixture, returns the same result when called twice, and its `plugin_id` and `engine_type` match the manifest.
- **Sandbox check:** the files under the test root are recorded before and after `export()`. Any change outside `staging/<plugin_id>` fails the test.
