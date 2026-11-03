# Contract conformance (audit of 2026-11-03, v1.1.0)

Read-only audit of the implementation against every document in `docs/contract/`, clause by
clause, by four parallel reviewers. Statuses: CONFORMS; DEVIATES (defect); DEVIATES
(intentional, documented: a prototype collapse, a 1.0 revision such as D22, or a decision the
doc predates); NOT IMPLEMENTED (deferred, documented); NOT IMPLEMENTED (undocumented gap: never
built and not recorded as deferred).

| Status | Clauses |
|---|---|
| CONFORMS | 374 |
| DEVIATES (intentional, documented) | 65 |
| NOT IMPLEMENTED (deferred, documented) | 36 |
| DEVIATES (defect) | 23 |
| NOT IMPLEMENTED (undocumented gap) | 34 |
| Total | 532 |

## Defects (DEVIATES)

| Clause | Evidence |
|---|---|
| 0.4 keep v1 metric keys, add correctly named metrics (`movedFiles`, `inventoryItems`, `collectedFromInventory`) | `viwo/contracts/pipeline.py:143-152` (`to_legacy_dict`) |
| 1.2 Windows known dirs: ProgramFiles, ProgramFiles(x86), scoop `apps/*/current`, chocolatey `lib/*/tools`, LOCALAPPDATA\Programs | `viwo/os/windows.py:73-77` |
| 1.2 Linux known dirs: /usr/bin, /usr/local/bin, /opt/*, ~/.local/bin, flatpak exports | `viwo/os/linux.py:62` |
| 1.7 `locate()` never installs; checked with a recording fake installer | no installer object exists, so no such test; `tests/test_os_layer.py:58` only checks order |
| 2.1 `plugin_id` slug `[a-z][a-z0-9_-]{1,31}`, unique | `viwo/core/wiring/registry.py:105` (drop-ins: no 32-char cap), built-ins not validated at all (`:63-71`) |
| 2.1 `PluginOption { key, label, type, default, choices, help }`, types string/secret/bool/int/float/choice/path | `viwo/contracts/plugin.py:21-27` |
| 2.2 `verify(ctx, inventory, export, collected) -> VerifyReport` | `viwo/contracts/plugin.py:149-151` (`verify(ctx, collected) -> warnings`) |
| 2.5 slot lookup: longest suffix first, then magic | `viwo/core/pipeline/identify.py:21-33` |
| 2.6 kind `runtime`; `executables` per OS; `packages` map | `viwo/contracts/types.py:77,80` |
| 2.9 slug/contract/engine_type/detect capability checks | no manifest validation for built-ins (`registry.py:63-71`) |
| 2.9 `detect()` never raises on fixtures, same result twice, ids match manifest | `tests/test_mixed.py:62` runs every plugin on every fixture (no raise, ids match); no idempotence assertion |
| 2.9 sandbox check: no change outside `staging/<plugin>` after `export()` | game-folder hashes only (`tests/test_formats.py:148`, `tests/test_capture.py:79-89`) |
| 8.4 unarchive.pak repak / quickbms spare | `viwo/plugins/unreal/__init__.py:40-46` (`unarchive.upak`, no spare) |
| 9.1 only one level of `base =` | `viwo/core/wiring/ini.py:13,116` (`MAX_LAYERS = 4`, so three `base` hops are accepted) |
| 9.1 effective configuration with the source of every value, logged and in `/api/distro` | `viwo/core/wiring/ini.py:151` (`source` = file chain only), `viwo/api/routes.py:29-31` |
| 9.2 `[startup] contract` | `ini.py:12` (`STARTUP_KEYS` lacks `contract`), `:128-132` |
| 9.4 unknown plugin/slot/backend id → error for that entry, default used instead | `binder.py:13-17,33-37`, `registry.py:188-191`, `binder.py:46` |
| 12.3 `JobHandle {id, kind, state, created, started, finished}` | `jobs.py:34-43` summary has `started`, `elapsed`, no `created`/`finished` fields |
| 12.3 run record: JobSpec, effective ini, slot bindings, tool versions, result → `.extraction_metadata/runs/<job>.json` | `runner.py:246-266` writes request, bindings, result, viwo version; capture record `capture/__init__.py:141` |
| 14.6 mitigations: pinned versions, spares, `viwo slots --check` | pins in `tools.json`; spares; no `--check` |
| 18.3 RESOLVE: reject edits whose format differs from the original member | `roundtrip.py:49-72` no format check; `plugins/unity/pack.py:2` converts PNG → Texture2D (declared converter) |
| 18.3 VERIFY: every untouched member keeps its original hash | `roundtrip.py:167-171` checks edited members only |
| L5 real-tool smoke: nightly on tool images; locally when present | CI real-tools job now runs `viwo install --all` but `tests/test_l5_tools.py:70-129` still locates tools through `VIWO_<ID>` env vars that nothing exports, so those tests `skipTest` on CI; only unrpa/UnityPy/7z-on-PATH/Freedoom actually run. No nightly schedule (owner's cost rule) |

## Undocumented gaps (never built, not recorded as deferred)

- OS: `display_name`
- 1.5 `long_path(path)` (`\\?\` prefix)
- 2.1 manifest: `description`, `capabilities`, `dependencies`, `OS layers`
- 2.2 `inventory(ctx)`
- 2.3 ExtractionContext `probe`
- 2.8 conformance checks against an empty probe at load
- 2.9 option keys and dependency ids unique
- 8.3 MediaProbe slot
- 8.4 export.godot gdre-tools --recover / godotdec
- 8.4 media.probe ffprobe / pillow; image.convert pillow / imagemagick
- 8.4 `network` and `parses_untrusted_in_process` declarations
- 9.4 `contract` major mismatch → exit 2
- 3.5 new keys `contractVersion`, `manifestsPath`; `plugins[]` fields `exportedByKind`, `exportedByTool`, `inventoryCount`, `verifyPassed`
- 3.6 Property tests with random confidences
- 5.2 `SanitizerRule` / `BatchRule` provider objects from core and plugins (`sanitizer_rules()`), `applies_to` / `inspect` / `fix`
- 11.1 precondition: anti-cheat service running (OS layer, best effort)
- 11.6 every backend declares its network use; offline flags on by default
- 12.4 `unpack --slot/--backend`
- 12.4 `slots --check` (backend self-tests)
- 12.5 `POST /api/jobs` generic submit
- 14.2 #3 wrapper plugins + one re-detection after unpacking an outer wrapper
- 14.2 #5 every backend declares network use; offline default
- 18.2 edit set: files the user adds with a target path ("added")
- D12 CATALOG → SELECT optional stage (Prototype B)
- 13.3 wrapper plugins: rerun detection after unwrapping
- 15.5 exceptions section, max 3, expiry milestone, CI fails after expiry
- doc 17 L0: ini schema validation of `loc_caps.ini`
- 16.0b ladder rung 4: zstd/LZ4 stream scan when modules present
- 16.4 risks: `viwo slots --check`
- L0 import-direction lint
- L0 every GPL/AGPL backend declares `isolation=subprocess`
- L0 every backend declares its network use
- L0 ini schema validation of `loc_caps.ini`
- 17.5 coverage floors (90/80/75 %)

---

# Conformance audit A: docs 00, 01, 02, 08, 09, 10 vs the implementation (v1.1.0, 2026-11-03)

Read-only. Status vocabulary: CONFORMS · DEVIATES (defect) · DEVIATES (intentional, documented) ·
NOT IMPLEMENTED (deferred, documented) · NOT IMPLEMENTED (undocumented gap). "Documented" means
a prototype-scope note, revision note (D22, 1.0) or decision in the contract docs, STATUS,
ARCHITECTURE or startup.ini; a comment in code alone does not count.

## 00 Glossary and semantic model

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 0.1 "engine" never used alone; game engine vs backend | CONFORMS | `viwo/contracts/slots.py:53` (`Backend`), `viwo/contracts/plugin.py:110` (`EnginePlugin`) | API field `engineType`/`extractorType` kept as v1 compatibility |
| 0.1 extractor → engine plugin; extract/unpack/export split | CONFORMS | `viwo/core/pipeline/unpack.py:1`, `viwo/contracts/slots.py:71,81` | stages named prepare/detect/unpack/export/carve/collect/decode/verify/report |
| 0.1 phase/slice → stage | CONFORMS | `viwo/contracts/types.py:12` (`ProgressEvent.stage`) | |
| 0.1 detect vs scan | CONFORMS | `viwo/core/pipeline/runner.py:71` (detect), survey "Scanning files" | |
| 0.1 three trash layouts `.trash/groups|items|merger` | CONFORMS | `viwo/core/curation/trash.py` (`migrate`), `tests/test_curation.py` | checked by name only; doc 4 is outside this audit |
| 0.1 "v1" = old app, contract written "contract 1.0" | CONFORMS | `viwo/__init__.py:4` `CONTRACT_VERSION = "1.0"`, `/api/distro` `contract` | |
| 0.1 manifest → report / plugin manifest / startup ini / tool lock | CONFORMS | `viwo/contracts/plugin.py:31` (`PluginManifest`), `viwo/data/tools.json` (tool lock) | |
| 0.1 assets dir → workspace | CONFORMS | `viwo/core/workspace.py`, `/api/workspace` | legacy `assetPath` kept in `/api/extract` (compat, documented in doc 4 mapping) |
| 0.1 session = UI session, explicit stores for persisted state | CONFORMS | `viwo/api/app.py:21-30` (memory), `viwo/core/surveys.py` (explicit store) | |
| 0.1 generic = plugin id; "undetected" outcome | CONFORMS | `viwo/plugins/generic/__init__.py:8`, `viwo/core/pipeline/select.py:46` | |
| 0.2 OS layer: package `viwo.os`, only place for OS code | CONFORMS | `viwo/os/__init__.py:1`, `viwo/os/windows.py`, `viwo/os/linux.py` | `subprocess`/`os.startfile` only there and in the installer (`thirdparty.py:211` msiexec, Windows-only branch) |
| 0.2 profile, distro = OS + profile in an ini | CONFORMS | `viwo/core/wiring/distros.py:27-28` (`OSES`, `PROFILES`), `distros/*.ini` | |
| 0.2 extraction run as a job; run record in `.extraction_metadata/runs/` | CONFORMS | `viwo/core/jobs.py`, `viwo/core/pipeline/runner.py:245-265` | |
| 0.2 feature switches (extraction, sorting, merger, sanitizer, analysis, capture) | DEVIATES (intentional, documented) | `viwo/core/wiring/ini.py:21`, `startup.ini` | features are extraction, sorting, merger, capture; sanitizer rides on sorting, analysis deferred (roadmap M13+) |
| 0.2 slot / backend / main / spare / tool / dependency | CONFORMS | `viwo/contracts/slots.py:42,53,124`, `viwo/contracts/types.py:72` | |
| 0.2 vendored tool = sparse submodule | DEVIATES (intentional, documented) | doc 10 sequencing note; `viwo/core/thirdparty.py:1-8` | pinned release binaries under `third_party/` instead (doc 10.4 option b) |
| 0.2 game folder never modified; COLLECT copies | CONFORMS | `viwo/core/pipeline/collect.py`, `tests/test_pipeline.py:36`, `tree_hashes(game)` in 7 test modules | |
| 0.2 workspace marker `.viwo-workspace` | CONFORMS | `viwo/core/workspace.py`, `tests/test_core_units.py:151` | |
| 0.2 staging / scratch / workspace / group / container / inventory | CONFORMS (inventory absent) | `viwo/contracts/plugin.py:76-79` | `inventory` is not a concept in code (see 02 hooks) |
| 0.2 round-trip terms (provenance map, edit set, patched copy, pack) | CONFORMS | `viwo/core/roundtrip.py`, `viwo/core/provenance.py`, `viwo/contracts/slots.py:105` | |
| 0.2 curation / sanitizer / merger terms | CONFORMS | `viwo/core/sanitizer.py` (rule, recipe, finding, plan, apply, journal), `viwo/core/merger/` | |
| 0.2 analysis target / analyzer | NOT IMPLEMENTED (deferred, documented) | roadmap doc 16 M13+ | |
| 0.4 keep v1 metric keys, add correctly named metrics (`movedFiles`, `inventoryItems`, `collectedFromInventory`) | DEVIATES (defect) | `viwo/contracts/pipeline.py:143-152` (`to_legacy_dict`) | v1 keys kept and files are now copied (so `copiedFiles` is true); the proposed extra metrics do not exist and the Unity quality-gate keys were dropped rather than renamed. Doc or code should state the final metric set |
| 0.5 questions | n/a | decided in `docs/contract/README.md` (D0 etc.) | |

Verdict: the vocabulary of the glossary is the vocabulary of the code; every structural term maps to one type or module.
Open: the 0.4 metric proposal was never closed (extra metric names absent), and "feature" switches differ from the list by design.

## 01 OS contract

| Clause | Status | Evidence | Note |
|---|---|---|---|
| OS: os_id, is_supported_host, process, tools, shell, fs | CONFORMS | `viwo/contracts/os.py:82-104`, `viwo/os/windows.py:80-108`, `viwo/os/linux.py:54-84` | |
| OS: `display_name` | NOT IMPLEMENTED (undocumented gap) | `viwo/contracts/os.py:85` | trivial; UI prints `os_id` upper-cased |
| OS: `installer : PackageInstaller` | NOT IMPLEMENTED (deferred, documented) | doc 1.3 prototype-scope note; `viwo/contracts/os.py:3-4` | replaced by the pinned installer (`viwo/core/thirdparty.py`), see doc 10 |
| 1.1 `max_command_length`, `python_executable`, `run(argv, cwd, env, timeout, cancel)` | CONFORMS | `viwo/contracts/os.py:16-38`, `viwo/os/_shared.py:21-63` | `on_line` added (streamed output), documented in the contract docstring |
| 1.1 `ProcessResult { returncode, stdout, stderr, timed_out, ok }` | CONFORMS | `viwo/contracts/types.py:96-105` | |
| 1.1 UTF-8 with errors=replace | CONFORMS | `viwo/os/_shared.py:44-45` | |
| 1.1 never raises on non-zero exit; FileNotFoundError only when it cannot start | CONFORMS | `viwo/os/_shared.py:49-63` (Popen raises, nothing else does), `tests/test_os_layer.py:81` | |
| 1.1 timeout/cancel kills the whole tree (taskkill /T on Windows, process group on Linux) | CONFORMS | `viwo/os/windows.py:20-27,84`, `viwo/os/linux.py:17-21,60`, `tests/test_os_layer.py:87,97,119` | |
| 1.1 `max_command_length` 32767 on Windows, ARG_MAX-derived on Linux; merger switches to file args | CONFORMS | `viwo/os/windows.py:85`, `viwo/os/linux.py:58-60`, `viwo/core/merger/build.py` (`-filter_complex_script`) | Linux uses ARG_MAX/2 with a 4096 floor |
| 1.2 `locate(spec)` side-effect free, `known_install_dirs(spec)` | CONFORMS | `viwo/os/_shared.py:99-154` | |
| 1.2 `status(spec, owner) -> DependencyStatus` | DEVIATES (intentional, documented) | `viwo/core/wiring/boot.py:44-65` (`dependency_report`) | status lives on the Runtime, not the locator; doc 4.2 shape |
| 1.2 `ToolLocation { dep_id, path, argv_prefix, source }` with the five sources | CONFORMS | `viwo/contracts/types.py:86-93` | |
| 1.2 argv_prefix examples (`python -m x`, `cmd /c x.bat`) | CONFORMS | `viwo/os/_shared.py:140`, `viwo/os/windows.py:30-33` | plus argv tuples for dotnet/qrenderdoc overrides (`_shared.py:130-132`) |
| 1.2 search order: ini `[tools]` → env var → PATH (names + .exe/.bat/.cmd) → known dirs | CONFORMS | `viwo/os/_shared.py:125-154`, `tests/test_os_layer.py:58` | a python-module step sits between env and PATH for `kind="python"` (documented in `contracts/os.py:44-45`); `third_party/` tools enter as config overrides (`boot.py:85`), i.e. before PATH |
| 1.2 Windows known dirs: ProgramFiles, ProgramFiles(x86), scoop `apps/*/current`, chocolatey `lib/*/tools`, LOCALAPPDATA\Programs | DEVIATES (defect) | `viwo/os/windows.py:73-77` | uses `scoop/shims` and `chocolatey/bin` (the shim folders, which is what PATH-less installs actually expose) and `LOCALAPPDATA` + `ProgramData` roots; doc should be updated to the shim folders or code extended |
| 1.2 Linux known dirs: /usr/bin, /usr/local/bin, /opt/*, ~/.local/bin, flatpak exports | DEVIATES (defect) | `viwo/os/linux.py:62` | `/opt/<install_dir>` only (no `/opt/*` glob), no flatpak exports |
| 1.2 one locator for status and calls (fixes F4) | CONFORMS | `viwo/contracts/slots.py:63-68`, `viwo/backends/archives.py:98` | |
| 1.3 PackageInstaller (pip → winget/choco/scoop; never elevates; only with auto_install) | NOT IMPLEMENTED (deferred, documented) | doc 1.3 note; replaced by `viwo/core/preflight.py:87-98` (pinned downloads, `auto_install` honoured at `:93`) | |
| 1.4 `open_folder`, `pick_folder`, `pick_file`; None on headless | CONFORMS | `viwo/contracts/os.py:67-79`, `viwo/os/_shared.py:174-207` | |
| 1.4 Linux fallback tkinter → zenity → kdialog | NOT IMPLEMENTED (deferred, documented) | doc 1.4 prototype note; `viwo/os/linux.py:47-51` | |
| 1.5 `case_sensitive`, `path_key`, `sanitize_filename`, `is_valid_filename` | CONFORMS | `viwo/os/windows.py:36-53`, `viwo/os/linux.py:24-38` | |
| 1.5 `long_path(path)` (`\\?\` prefix) | NOT IMPLEMENTED (undocumented gap) | `viwo/contracts/os.py:51-64` | no caller needs it yet; deep workspaces on Windows could |
| 1.5 Windows rules (forbidden chars, trailing dot/space, reserved names, 255) | CONFORMS | `viwo/os/windows.py:16-17,44-53`, `tests/test_os_layer.py:46` | |
| 1.5 Linux rules (no `/`, NUL, `.`, `..`) | CONFORMS | `viwo/os/linux.py:32-38` | |
| 1.5 one rule replaces Unity `_safe_name`, sort rename check, merger output name | CONFORMS | `viwo/core/curation/sorting.py` (rename uses `fs.is_valid_filename`), `viwo/core/merger/build.py` (`output_name`) | |
| 1.6 case-insensitive engine markers through the probe | CONFORMS | `viwo/core/pipeline/probe.py:19-20,31-32` | |
| 1.6 executable suffix handling / open folder per OS | CONFORMS | `viwo/os/windows.py:86`, `viwo/os/linux.py:63,45` | |
| 1.7 `max_command_length > 0` | CONFORMS | `tests/test_os_layer.py:85` | |
| 1.7 sanitize set (empty, `.`, `..`, CON, nul.txt, a/b, a\b, x:y, trailing dot/space, control, NUL, Unicode, 300 chars) | CONFORMS | `tests/test_os_layer.py:20-45` (`NASTY`, both policies) | |
| 1.7 `path_key` stable and case-folded on Windows | CONFORMS | `tests/test_os_layer.py:46-56` | |
| 1.7 `locate()` never installs; checked with a recording fake installer | DEVIATES (defect) | no installer object exists, so no such test; `tests/test_os_layer.py:58` only checks order | property holds by construction (`_shared.py:125-154` performs no writes); the conformance test is missing |

Verdict: the OS layer matches the contract in shape and behaviour; the installer and dialog fallbacks are documented deferrals.
Open: known-dir lists differ from the doc on both OSes, `long_path`/`display_name` are missing, and the "locate never installs" conformance test does not exist.

## 02 Engine plugin contract

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 2.1 manifest: `plugin_id`, `name`, `version`, `engine_type`, `contract`, `priority`, `options`, `builtin` | CONFORMS | `viwo/contracts/plugin.py:30-40` | |
| 2.1 manifest: `description`, `capabilities`, `dependencies`, `OS layers` | NOT IMPLEMENTED (undocumented gap) | `viwo/contracts/plugin.py:30-40` | capabilities are implied by slots/backends; dependencies are declared on backends (2.6 allows that); no OS-layer restriction per plugin |
| 2.1 `plugin_id` slug `[a-z][a-z0-9_-]{1,31}`, unique | DEVIATES (defect) | `viwo/core/wiring/registry.py:105` (drop-ins: no 32-char cap), built-ins not validated at all (`:63-71`) | uniqueness is enforced by the dict (`:71,179`) |
| 2.1 `PluginOption { key, label, type, default, choices, help }`, types string/secret/bool/int/float/choice/path | DEVIATES (defect) | `viwo/contracts/plugin.py:21-27` | no `help`, no `float`; harmless, doc or code to align |
| 2.1 secrets never logged nor written to manifests | CONFORMS | `viwo/core/pipeline/runner.py` (`SECRET` placeholder in run records), `viwo/contracts/plugin.py:92-105` (`mask`), `tests/test_godot.py` (record stores `<secret>`) | |
| 2.2 `detect(probe)` required; `manifest` required | CONFORMS | `viwo/contracts/plugin.py:114-119` | |
| 2.2 `slot_definitions()`, `backends()` default empty | CONFORMS | `viwo/contracts/plugin.py:124-128` | |
| 2.2 `source_roots(game_root, probe)` default `[game_root]`; `skip_dirs()` | CONFORMS | `viwo/contracts/plugin.py:130-135` | Ren'Py returns `<game>/game` (doc 2.7) |
| 2.2 `inventory(ctx)` | NOT IMPLEMENTED (undocumented gap) | `viwo/contracts/plugin.py` (no hook) | doc 0.4 ties completeness claims to inventory; none are made, so no wrong claim results |
| 2.2 `export(ctx) -> ExportReport` on the plugin | DEVIATES (intentional, documented) | `viwo/contracts/plugin.py:145-147` (`export_slot`), doc 8.5 (EXPORT goes through `export.<plugin>` slots) | plugin names its export slot; the Exporter backend does the work |
| 2.2 `verify(ctx, inventory, export, collected) -> VerifyReport` | DEVIATES (defect) | `viwo/contracts/plugin.py:149-151` (`verify(ctx, collected) -> warnings`) | simplified signature; doc to align |
| 2.2 `sanitizer_rules()`, `analysis_targets()` | NOT IMPLEMENTED (deferred, documented) | doc 5 sanitizer phase 1 is core-owned (STATUS M10); analysis M13+ | |
| 2.2 extra hooks not in doc: `configure`, `claimed_suffixes`, `pack_slot`, `cli_commands`, `ui_module` | CONFORMS (extensions) | `viwo/contracts/plugin.py:121,137,141,153,157` | `configure` is doc 9 `[options.*]`; add-ons documented in `docs/plugins.md` |
| 2.2 detect fast and pure; same result twice | CONFORMS (by construction, untested) | `viwo/plugins/*/__init__.py` detect bodies only read the probe (e.g. `renpy/__init__.py:40-43`, `unreal/__init__.py:63-71`) | no "called twice" test (see 2.9) |
| 2.2 export writes only into staging/scratch; nothing deleted outside staging | CONFORMS | `viwo/contracts/slots.py:81-86`, game-folder hash checks in `tests/test_formats.py:148-151`, `tests/test_doom.py:148-163` | staging-only boundary is not asserted directly (see 2.9 sandbox) |
| 2.2 exception in a hook → warning for that plugin, not a crash | CONFORMS | `viwo/core/pipeline/runner.py:71-74` (detect), `viwo/core/pipeline/failover.py:29-32` (backends) | |
| 2.3 GameProbe: root, truncated, has_name, find, with_suffix, head, tail; bounded, one scan | CONFORMS | `viwo/contracts/plugin.py:55-69`, `viwo/core/pipeline/probe.py:11-57` (50k limit, `truncated`) | |
| 2.3 ExtractionContext: request_id, game_root, staging, scratch, selected_exts, options, detection, OS, progress, cancel, log | CONFORMS | `viwo/contracts/plugin.py:72-90` | |
| 2.3 ExtractionContext `probe` | NOT IMPLEMENTED (undocumented gap) | `viwo/contracts/plugin.py:72-86` | backends rebuild what they need from `game_root`; harmless |
| 2.4 DetectionResult { engine_type, confidence, evidence[], plugin_id } and legacy JSON | CONFORMS | `viwo/contracts/types.py:44-62` | range 0..1 enforced |
| 2.4 confidence scale | CONFORMS | `viwo/plugins/renpy/__init__.py:40-43` (weighted hints), `unity/__init__.py:62-66`, `godot/__init__.py:42-47` (strong = magic ≥ 0.75) | generic fixed 0.4 (`generic/__init__.py`) |
| 2.5 plugins introduce slots and ship backends; core owns zip/tar/7z/rar | CONFORMS | `viwo/backends/__init__.py:12-46`, `viwo/plugins/*/__init__.py` | |
| 2.5 main/spare from ini with plugin defaults | CONFORMS | `viwo/core/wiring/binder.py:22-37` | |
| 2.5 recursive loop: queue, seen-set, `archive_NNNNN_<uuid8>`, nested detection | CONFORMS | `viwo/core/pipeline/unpack.py:48-64` | |
| 2.5 slot lookup: longest suffix first, then magic | DEVIATES (defect) | `viwo/core/pipeline/identify.py:21-33` | magic is consulted only for extension-less files (code comment: a `.docx` is a zip). Reasonable, but the contract says otherwise; doc to align |
| 2.5 every unarchive backend prevents traversal | CONFORMS | `viwo/backends/archives.py:36-45,55-58`, `viwo/contracts/workspace.py` (`safe_member`), `tests/test_pipeline.py:36` | |
| 2.5 ownership table (zip/tar/7z/rar core; rpa renpy; unitypackage unity; pck godot; pak/iostore unreal) | CONFORMS (ids differ) | `viwo/plugins/unreal/__init__.py:40-47` (`unarchive.upak`, `unarchive.utoc`) | slot ids `upak`/`utoc` instead of `pak`/`iostore`; `distros/*.ini` and the UI use the real ids |
| 2.6 DependencySpec { dep_id, label, kind, requirement, import_name, executables, env_var, hint } | CONFORMS | `viwo/contracts/types.py:72-83` | |
| 2.6 kind `runtime`; `executables` per OS; `packages` map | DEVIATES (defect) | `viwo/contracts/types.py:77,80` | flat executables tuple (OS adds suffixes, `types.py:73`), no `runtime` kind (the .NET runtime is a hidden tools.json entry instead), no package ids (installer is pinned downloads). Doc to align with the installer decision |
| 2.6 `/api/dependencies` combines all, `category` = owner | CONFORMS | `viwo/core/wiring/boot.py:44-65` | |
| 2.7 generic: always 0.4 | CONFORMS | `viwo/plugins/generic/__init__.py` | |
| 2.7 renpy markers; `source_roots` = `<game>/game` | CONFORMS | `viwo/plugins/renpy/__init__.py:40-43`, `source_roots` in the same file | |
| 2.7 unity markers | CONFORMS | `viwo/plugins/unity/__init__.py:62-66` (`STRONG`, il2cpp, Assembly-CSharp, `*_Data`) | |
| 2.7 unreal markers; options `aesKey` (secret), `engineVersion` | CONFORMS (names differ) | `viwo/plugins/unreal/__init__.py:30-31,63-71` | options are `aes_key` (secret) and a second non-secret option |
| 2.7 godot markers; option `encryptionKey` secret; `.ctex` conversion as sanitizer rule | CONFORMS / NOT IMPLEMENTED | `viwo/plugins/godot/__init__.py:17,42-47` | option is `encryption_key` (secret); `.ctex/.stex → .png` rule is not implemented (sanitizer phase 1 scope, documented in STATUS M10) |
| 2.7 "tools column defers to 8.4" | CONFORMS | see 08 | |
| 2.8 custom plugins: discovery, `plugin.json`, `entry` form, opt-in, trust model | CONFORMS | revision note in doc 2.8; `viwo/core/wiring/registry.py:97-192`, `tests/test_registry.py:76-160`, `docs/plugins.md` | |
| 2.8 reserved ids (`generic renpy unity unreal godot mixed auto`) | CONFORMS (revised) | `registry.py:30,179-182` | built-in names need `override`; `mixed/auto/core/none` reserved |
| 2.8 contract-version check at load | DEVIATES (intentional, documented) | `registry.py:107-109` (`requires.viwo`) | the revision note replaces `contract` with `requires`; `plugin.json` `contract` key is ignored |
| 2.8 conformance checks against an empty probe at load | NOT IMPLEMENTED (undocumented gap) | `registry.py:116-136` | only type and id checks run at load |
| 2.9 slug/contract/engine_type/detect capability checks | DEVIATES (defect) | no manifest validation for built-ins (`registry.py:63-71`) | built-ins are trusted code; still, the doc promises the check |
| 2.9 option keys and dependency ids unique | NOT IMPLEMENTED (undocumented gap) | no check in `registry.py` / `boot.py` | `dependency_report` dedups by id silently (`boot.py:64`) |
| 2.9 slot and backend ids unique; owner is the plugin id; suffixes lowercase dotted | CONFORMS (partially) | `registry.py:230-241` (uniqueness with problems) | owner/suffix form not validated; every built-in satisfies it by inspection (`SlotDefinition` literals listed in the plugin `__init__` files) |
| 2.9 `detect()` never raises on fixtures, same result twice, ids match manifest | DEVIATES (defect) | `tests/test_mixed.py:62` runs every plugin on every fixture (no raise, ids match); no idempotence assertion | add a "detect twice" conformance test |
| 2.9 sandbox check: no change outside `staging/<plugin>` after `export()` | DEVIATES (defect) | game-folder hashes only (`tests/test_formats.py:148`, `tests/test_capture.py:79-89`) | the stronger "nothing outside staging" assertion is absent |

Verdict: the plugin model (manifest, detect, slots, backends, probe, context, failure handling) is implemented as described, and the 1.0 revision of 2.8 is honoured with tests.
Open: the automated conformance kit of 2.9 is mostly missing, and several manifest/option/dependency fields of 2.1/2.6 were simplified without a doc update.

## 08 Pipeline backends and slots

| Clause | Status | Evidence | Note |
|---|---|---|---|
| Every tool is reached through a slot; no stage calls a tool directly | CONFORMS (one exception) | `viwo/core/pipeline/unpack.py` (failover), `viwo/core/decode.py`, `viwo/core/roundtrip.py` | the merger calls `ffprobe` through the dependency locator, not a `media.probe` slot (`viwo/core/merger/ffmpeg.py:54`) |
| 8.1 SlotDefinition: slot_id, family, owner, matches, default_main, default_spare | CONFORMS | `viwo/contracts/slots.py:41-50` (`suffixes`/`magic`/`identify` = matches) | |
| 8.1 SlotDefinition `interface`, `policy` | NOT IMPLEMENTED (deferred, documented) | doc 8.2 prototype note (failover only) | interface is implied by family |
| 8.1 Backend: backend_id, owner, families, dependencies(), available() | CONFORMS | `viwo/contracts/slots.py:53-68` | `available()` returns `(ok, reason)`; no `location` field |
| 8.1 SlotBinding: slot_id, main, spare, promoted, source default|ini|cli | CONFORMS | `viwo/contracts/slots.py:123-134` | `cli` source deferred with CLI overrides (doc 9 note) |
| 8.2 policies failover / main_only / supplement | NOT IMPLEMENTED (deferred, documented) | doc 8.2 prototype note; `viwo/core/pipeline/failover.py` implements failover | |
| 8.2 outcome kinds collapsed to ok/unavailable/failed/needs_key | CONFORMS | `viwo/contracts/types.py:108-114`, doc 8.2 note | |
| 8.2 retry table: unavailable/failed retry; needs_key only with a key-capable spare | DEVIATES (intentional, documented) | `viwo/contracts/types.py:128-131` (needs_key never retried), `tests/test_core_units.py:67-85`, `ARCHITECTURE.md:48` | the spare is never tried for needs_key even when `supports_keys=True` (gdre-tools, repak declare it). Documented as an invariant in ARCHITECTURE, not in doc 8 |
| 8.2 startup resolution: main stays; missing main → spare promoted with a warning; neither → unbound, stages skip with the install hint, no crash | CONFORMS | `viwo/core/wiring/binder.py:22-37`, `viwo/core/pipeline/failover.py:18-20`, `tests/test_core_units.py:53` | reasons flow into `rt.problems` (`boot.py:107-108`) |
| 8.2 every result records its backend; `by_backend` counts in reports | CONFORMS | `viwo/contracts/pipeline.py:104,120,143,152` | |
| 8.3 Unarchiver: extract, supports_keys; core loop unchanged | CONFORMS | `viwo/contracts/slots.py:71-78`, `viwo/core/pipeline/unpack.py` | `sniff(path, head)` replaced by slot-level identification (doc 8.4 "Identify, then extract") |
| 8.3 Exporter.export(ctx) | CONFORMS | `viwo/contracts/slots.py:81-86` | returns `Outcome`, not `ExportReport` |
| 8.3 MediaProbe slot | NOT IMPLEMENTED (undocumented gap) | `viwo/core/merger/ffmpeg.py:54` (direct `FFPROBE` locate) | the merger works; the probe is not swappable through the ini |
| 8.3 MediaEncoder (`media.encode`, honours max_command_length) | CONFORMS | `viwo/backends/__init__.py:13`, `viwo/core/merger/build.py` (`max_command_length // 2` switch) | |
| 8.3 ImageCodec (`image`) | DEVIATES (intentional, documented) | `viwo/core/decode.py:30` (`decode.image`, ffmpeg DDS → PNG), STATUS D21 ladder | decoders family instead of image codec; pillow not used |
| 8.3 CodeAnalyzer (`analysis`) | NOT IMPLEMENTED (deferred, documented) | roadmap M13+ | |
| 8.4 "Identify, then extract": identifier sees head and tail, reports embedded chunks, core carves | CONFORMS | `viwo/contracts/slots.py:24-38`, `viwo/core/pipeline/identify.py:13-52`, `viwo/plugins/godot/__init__.py:44` (exe trailer), `tests/test_core_units.py:121` | |
| 8.4 unarchive.zip py-zipfile / sevenzip-cli; .zip (+ zip appended to exe) | CONFORMS | `viwo/backends/__init__.py:16-24` | exe-appended zips are found by the carver rather than the zip identifier; `.nw` added |
| 8.4 unarchive.tar, .7z (sevenzip-cli/py7zr), .rar (unrar-cli/sevenzip-cli) | CONFORMS | `viwo/backends/__init__.py:25-45` | |
| 8.4 unarchive.rpa rpa-safe / unrpa (restricted unpickler, subprocess) | CONFORMS | `viwo/plugins/renpy/__init__.py:23-25`, `renpy/rpa.py:31,81,106` | D11 resolved as proposed |
| 8.4 unarchive.unitypackage py-tarfile / sevenzip-cli | CONFORMS | `viwo/plugins/unity/__init__.py:29-36` | |
| 8.4 unarchive.unity-bundle (unitypy / uabea-cli), unarchive.unity-webgl | DEVIATES (intentional, documented) | `viwo/plugins/unity/__init__.py:37-39` (`CLAIMED` suffixes go to `export.unity`) | bundles are handled by the exporter, not a separate unarchive slot; STATUS M5/D7 |
| 8.4 unarchive.pck gdre-tools / godotpcktool | CONFORMS | `viwo/plugins/godot/__init__.py:19-26`, `godot/pck.py:96-105` | |
| 8.4 unarchive.pak repak / quickbms spare | DEVIATES (defect) | `viwo/plugins/unreal/__init__.py:40-46` (`unarchive.upak`, no spare) | QuickBMS is a separate plugin slot (`unarchive.bms`) rather than the pak spare; doc to align or a spare to add |
| 8.4 unarchive.iostore retoc / CUE4Parse wrapper | DEVIATES (intentional, documented) | `viwo/plugins/unreal/__init__.py:47`, STATUS M7 ("retoc to legacy, raw as spare") | |
| 8.4 unarchive.casc datatool / casclib | DEVIATES (intentional, documented) | `viwo/plugins/overwatch/__init__.py:99` (`export.overwatch`), STATUS M8 | export slot instead of an unarchive slot; no casclib spare |
| 8.4 export.unity unitypy / assetstudiomod-cli (D7) | CONFORMS | `viwo/plugins/unity/__init__.py:37` | |
| 8.4 export.unity-project (assetripper), export.unreal (CUE4Parse/umodel) | NOT IMPLEMENTED (deferred, documented) | doc 8.4 "optional" / "deferred after the prototype" | |
| 8.4 export.godot gdre-tools --recover / godotdec | NOT IMPLEMENTED (undocumented gap) | `viwo/plugins/godot/__init__.py:53` (unarchive + pack only) | GDRE's `--extract` is used; `--recover` (project recovery) is not offered |
| 8.4 export.overwatch datatool | CONFORMS | `viwo/plugins/overwatch/__init__.py:55,99` | |
| 8.4 keys slots (user key / aesdumpster / keyring) | DEVIATES (intentional, documented) | D18 (`docs/contract/README.md`), `viwo/plugins/unreal/pak.py` (key from the user or found in the game's executables, verified) | keys are options plus a finder, not slots |
| 8.4 media.probe ffprobe / pillow; image.convert pillow / imagemagick | NOT IMPLEMENTED (undocumented gap) | see 8.3 | |
| 8.4 audio.decode vgmstream | CONFORMS (renamed) | `viwo/core/decode.py:27` (`decode.audio`, spare `ffmpeg-decode`) | |
| 8.4 analysis.* slots | NOT IMPLEMENTED (deferred, documented) | roadmap M13+ | `analysis.python` (unrpyc) exists as `decode.rpyc` (`viwo/plugins/renpy/decompile.py:21`) |
| 8.4 capture.gpu; capture.memory, capture.audio, runtime.<engine> | CONFORMS / NOT IMPLEMENTED (deferred, documented) | `viwo/core/capture/__init__.py:29`, STATUS M11 (pilot = RenderDoc only) | |
| 8.4 backend declarations: `license` (SPDX), GPL/AGPL → subprocess | CONFORMS | `viwo/contracts/slots.py:57-58`; unrpa `renpy/rpa.py:106`, quickbms `:46`, ffmpeg `merger/ffmpeg.py:33`, decoders `decode.py:49`, renderdoc, datatool, gdre: all `subprocess` | every GPL backend is a subprocess; no test enforces the rule (doc 17 L0 lint listed, not present) |
| 8.4 `network` and `parses_untrusted_in_process` declarations | NOT IMPLEMENTED (undocumented gap) | `viwo/contracts/slots.py:53-58` | |
| 8.5 UNPACK: `unarchive.*` by matches (longest suffix, then magic) | CONFORMS (see 2.5 note on magic) | `viwo/core/pipeline/identify.py` | |
| 8.5 EXPORT: `export.<plugin_id>` | CONFORMS | `viwo/contracts/plugin.py:145`, `viwo/plugins/unity/__init__.py:37`, `rpgmaker/__init__.py:22`, `overwatch/__init__.py:99` | |
| 8.5 VERIFY: plugin.verify + optional media.probe health | CONFORMS (health through the sanitizer instead) | `viwo/contracts/plugin.py:149`, `viwo/core/sanitizer.py` (`core.health`) | |
| 8.5 SANITIZE by rule; REPORT core; merger build probe+encode | CONFORMS | `viwo/core/sanitizer.py`, `viwo/core/pipeline/runner.py:245-265`, `viwo/core/merger/build.py` | |
| 8.6 `slot_definitions()` / `backends()` replace `archive_handlers()` | CONFORMS | `viwo/contracts/plugin.py:124-128` | |
| 8.6 a plugin may add a backend to a slot it does not own; ini binds it | CONFORMS | `viwo/core/wiring/binder.py:9-19` (family check only) | |
| 8.6 slot ids unique across plugins | CONFORMS | `viwo/core/wiring/registry.py:230-235` | |
| 8.6 default main/spare name a known backend serving the family | CONFORMS | `viwo/core/wiring/binder.py:13-17`, `viwo/core/wiring/distros.py:118-125`, `tests/test_config.py:65` | |
| 8.6 `available()` has no side effects | CONFORMS (by construction) | `viwo/contracts/slots.py:63-68` → `locate` | no recording test |
| 8.6 spare with `supports_keys=false` never called for needs_key | CONFORMS | `viwo/contracts/types.py:128-131`, `tests/test_core_units.py:67-85` | stronger than required (no spare at all for needs_key) |
| 8.6 matrix {main up, down} × {spare up, down}; promotion, failover, unbound | CONFORMS | `tests/test_core_units.py:53-66,67-85` | |

Verdict: slots, binding, promotion, failover and the ownership of formats follow doc 8 with the documented prototype collapses; GPL isolation is declared everywhere it must be.
Open: the needs_key policy is stricter than doc 8.2 (documented only in ARCHITECTURE), `media.probe` and a pak spare are missing, and the `network`/untrusted-parser declarations were never added.

## 09 Startup wiring from an ini file

| Clause | Status | Evidence | Note |
|---|---|---|---|
| configparser, `[startup]`, `[plugins]`, `[slots]`, `[tools]`, `[server]` | CONFORMS | `viwo/core/wiring/ini.py:11,107-108` | |
| 9.1 `startup.ini` + 12 shipped distros | CONFORMS | `distros/*.ini`, `viwo/core/wiring/distros.py:27-28`, `tests/test_config.py:17,47` | implemented beyond the prototype note |
| 9.1 precedence defaults < base < ini < cli | CONFORMS (cli partial) | `viwo/core/wiring/ini.py:111-125,140-146` (base first, later files override), `viwo/cli.py` `--os` → `boot(os_id)` | `--profile`, `--plugin`, `--slot` flags deferred (doc 9 prototype note) |
| 9.1 only one level of `base =` | DEVIATES (defect) | `viwo/core/wiring/ini.py:13,116` (`MAX_LAYERS = 4`, so three `base` hops are accepted) | lenient; `tests/test_config.py:81` only covers one level |
| 9.1 effective configuration with the source of every value, logged and in `/api/distro` | DEVIATES (defect) | `viwo/core/wiring/ini.py:151` (`source` = file chain only), `viwo/api/routes.py:29-31` | bindings carry `source: default|ini`; other values do not; nothing logs the effective ini at boot |
| 9.2 encoding UTF-8 with BOM, `;`/`#` comments, booleans, case-insensitive keys | CONFORMS | `ini.py:108,120,143`, configparser semantics | |
| 9.2 `[startup] contract` | DEVIATES (defect) | `ini.py:12` (`STARTUP_KEYS` lacks `contract`), `:128-132` | a `contract = 1.0` line is reported as "unknown key ignored"; the major-version check → exit 2 (9.4) is missing |
| 9.2 `[startup] os`, `profile`, `features`, `auto_install`, `strict_preflight`, `base` | CONFORMS | `ini.py:12,57-65` | key is `os`, the doc's prose says "OS layer" |
| 9.2 `auto_install` default off | DEVIATES (intentional, documented) | `ini.py:22` (default on), `startup.ini`, HANDOFF item 1 (owner: fully automated installs) | F19 concern answered by pinned, checksummed downloads |
| 9.2 `[plugins]` ids, `generic` forced on, `custom_dirs`, `custom.<id>` | CONFORMS | `ini.py:69-74`, `registry.py:28,155-170` | |
| 9.2 `[slots] <slot> = <main>[, <spare>]`, `none` | CONFORMS | `ini.py:75-78` | |
| 9.2 `[slot_policy]` | NOT IMPLEMENTED (deferred, documented) | doc 8.2 note; `ini.py:92-93` reports it as an unknown section | the warning text could point at the deferral |
| 9.2 `[tools]` keyed by dependency id, paths relative to the ini | CONFORMS | `ini.py:79-80`, `boot.py:85` | doc 1.2 says "keyed by backend id": doc 1 to align with doc 9 |
| 9.2 `[options.<plugin>]`, secrets refused | CONFORMS | `ini.py:83-91`, `tests/test_config.py:65` | |
| 9.2 `[hooks]` | NOT IMPLEMENTED (deferred, documented) | doc 9 prototype note | |
| 9.3 step 1 usage error → exit 2 | CONFORMS | argparse (`viwo/cli.py:233`), `tests/test_cli.py` | |
| 9.3 step 2 syntax error → exit 2 with file:line | CONFORMS | `ini.py:149-150` (`invalid_request` with configparser's message, which carries the line), `viwo/cli.py:33` | |
| 9.3 step 3 `[server]` defaults under `viwo-data/` | CONFORMS | `ini.py:34-50,96-104` | |
| 9.3 step 4 OS select, unsupported host → exit 3 | CONFORMS | `viwo/os/__init__.py:21-30` (`refused`), `viwo/cli.py:33` | |
| 9.3 steps 5, 7, 10, 12 hooks | NOT IMPLEMENTED (deferred, documented) | | |
| 9.3 step 6 register built-ins, discover/validate/register custom; bad plugin disabled and shown | CONFORMS | `registry.py:162-192`, `/api/distro` problems | shown under `/api/distro.problems` (doc says `/api/plugins`) |
| 9.3 step 8 bind: defaults + `[slots]` + `[tools]`, auto-install, promote spares | CONFORMS | `boot.py:85,106-108`, `preflight.py:87-98` (install after bind, then `App.reload()` rebinds) | |
| 9.3 step 9 strict_preflight → exit 4 | DEVIATES (intentional, documented) | `viwo/api/server.py:217-234`, `preflight.py:101-109`, `startup.ini` comment | condition is "an enabled plugin's slot has no backend" instead of "a REQUIRED dependency is missing" (no dependency is marked required: `boot.py:56`) |
| 9.3 step 11 port in use → clear error | CONFORMS | `viwo/api/server.py:236-244` (exit 2) | |
| 9.3 exit codes 0/2/3/4 | CONFORMS | `viwo/cli.py:33,41`, `server.py:234,244` | plus 1 (failed), 130 (cancelled), documented in `viwo -h` |
| 9.4 unknown sections/keys → warning, ignored | CONFORMS (partial) | `ini.py:92-93,128-132` | `[startup]` keys and sections are checked; unknown keys inside `[server]` are ignored silently |
| 9.4 unknown plugin/slot/backend id → error for that entry, default used instead | DEVIATES (defect) | `binder.py:13-17,33-37`, `registry.py:188-191`, `binder.py:46` | problems are reported, but an unknown or wrong-family backend in `[slots]` leaves the slot unbound (or on the spare) rather than falling back to the plugin default |
| 9.4 `contract` major mismatch → exit 2 | NOT IMPLEMENTED (undocumented gap) | see 9.2 `contract` | |
| 9.4 secret-looking option keys refused with a warning | CONFORMS | `ini.py:14,88-90` | `token` added to the word list |
| 9.4 paths relative to the ini folder | CONFORMS | `ini.py:72,80,103` | |
| 9.5 lifecycle hooks | NOT IMPLEMENTED (deferred, documented) | | |
| 9.6 `GET /api/distro` returns effective ini, bindings, problems | CONFORMS (partial, see 9.1) | `viwo/api/routes.py:29-31`, `boot.py:67-74` | bindings and problems yes; per-value sources no |
| 9.6 UI editing later, takes effect after restart; nothing re-wired while running | DEVIATES (intentional, documented) | `viwo/core/wiring/settings.py`, `viwo/api/handlers_settings.py` (`App.reload()`), HANDOFF 1.0 | owner's decision: apply by reload, no restart |

Verdict: the flat ini, layering, validation of ids and secrets, and the boot exit codes match doc 9; hooks, slot policies and CLI overrides are documented deferrals.
Open: `contract` in `[startup]` is treated as an unknown key, more than one base level is accepted, bad `[slots]` entries do not fall back to defaults, and per-value provenance of the effective config is absent.

## 10 Third-party tools (sparse submodules proposal)

| Clause | Status | Evidence | Note |
|---|---|---|---|
| Direction: sparse submodules at M11; until then a tool lock file (name, version, URL, checksum) | CONFORMS (interim design) | `viwo/data/tools.json` (version, license, url, size, sha256, kind, find per OS), `viwo/core/thirdparty.py:31-38` | the lock file is the shipped design; submodules remain a roadmap item (M12) |
| 10.1 pinned versions, provenance, licenses next to the tool, fewer install surprises, locator knows the place | CONFORMS | `tools.json` `license` per entry, `THIRD_PARTY_NOTICES.md` (generated by `tools/notices.py`), `boot.py:85` (`found_tools` first) | |
| 10.2 `third_party/vendor.ini` + submodule folders + `_build/` | NOT IMPLEMENTED (deferred, documented) | doc 10 sequencing note; roadmap M12 | `third_party/<id>/` folders exist with release binaries instead |
| 10.2 sync script for sparse checkout | NOT IMPLEMENTED (deferred, documented) | | |
| 10.2 locator order: config → env → vendored → PATH → known dirs; vendored first ❓ | CONFORMS (decided: vendored first) | `boot.py:85` (`{**found_tools, **config.tools}` feeds the config step), `_shared.py:125-132` | ini still wins over `third_party/`, PATH comes after; README "Precedence" states it |
| 10.3 pure-Python tools from source on sys.path | CONFORMS (variant) | `thirdparty.py:47-54` (`third_party/python` on `sys.path`, pip `--target`), unrpyc from a tagged source zip run with `{python}` (`thirdparty.py:99-100`) | |
| 10.3 UnityPy native deps need wheels | CONFORMS | `thirdparty.py:273-290` (pip install of the pin, wheels included) | |
| 10.3 compiled tools: release binaries | CONFORMS | `tools.json` (repak, retoc, vgmstream, gdre, godotpcktool, assetstudiomod, 7-Zip, ffmpeg, quickbms, datatool, renderdoc, dotnet) | 10.4 option (b) in practice |
| 10.3 unrar / 7-Zip do not fit git | CONFORMS | `tools.json` `unrar` (RARLAB self-extractor opened by 7-Zip: `thirdparty.py:216-222`), `sevenzip` (MSI administrative unpack: `:209-215`) | |
| 10.4.1 source vs runnable → (b) binaries verified by checksum | CONFORMS | `thirdparty.py:140-166,245-249` (sha256 + size, 3 attempts, HTTPS only) | ❓ answered by the implementation |
| 10.4.2 licenses before vendoring | CONFORMS | `LICENSE` (MIT), `tools.json` license per tool, GPL tools as subprocesses (see 08) | |
| 10.4.3 repository size | CONFORMS (moot) | nothing vendored in git; `third_party/` is gitignored | |
| 10.4.4 bumping a pin reruns the matrix | CONFORMS (by policy) | `tests/test_thirdparty.py:186` (manifest complete and HTTPS), CI real-tool job installs the pins (`.github/workflows/ci.yml`) | |
| 10.4.5 vendor list vs `[tools]` split | CONFORMS (decided) | `tools.json` (what is pinned) vs `[tools]` (what is forced) | |
| 10.5 `DependencySpec.vendored`; `[tools] x = vendored:<name>`; `auto_install` as fallback | DEVIATES (intentional, documented) | `boot.py:85` makes every installed pin a config override automatically; `preflight.py:92-94` installs only what is missing when `auto_install` is on | the explicit `vendored:` syntax is unnecessary under the lock-file design |
| Owner's 1.0 rules (HANDOFF item 1): every tool under `third_party/`, pinned, checksummed, HTTPS, no manual step | CONFORMS | `thirdparty.py:142-143,248`, `tests/test_thirdparty.py:163,186`, STATUS "1.0 evidence" (Windows and Linux installs) | `installable()` refuses Python pins in the frozen build (`thirdparty.py:133-137`) |

Verdict: doc 10 was a proposal; the owner chose its option (b) and the interim lock-file design, and the implementation follows that choice completely.
Open: sparse submodules, `vendor.ini` and the `vendored:` ini syntax stay deferred (M12); the doc itself still reads as an open proposal and should record the decision.

## Counts per status

| Doc | CONFORMS | DEVIATES (defect) | DEVIATES (intentional, documented) | NOT IMPL. (deferred, documented) | NOT IMPL. (undocumented gap) |
|---|---|---|---|---|---|
| 00 | 17 | 1 | 2 | 1 | 0 |
| 01 | 20 | 4 | 1 | 3 | 2 |
| 02 | 23 | 8 | 2 | 1 | 5 |
| 08 | 24 | 1 | 6 | 6 | 4 |
| 09 | 20 | 5 | 3 | 5 | 1 |
| 10 | 13 | 0 | 1 | 2 | 0 |

Defects worth fixing first (small, concrete): `[startup] contract` handling and the major-version
check (09), `[slots]` fallback to defaults on a bad backend id (09), the 2.9 conformance kit
(detect twice, staging sandbox, manifest validation for built-ins), and a doc pass to align 2.1,
2.5 (magic rule), 2.6, 8.2 (needs_key), 8.4 (pak spare, slot ids) with what ships.


---

# Conformance audit B: contract docs 03-07 vs implementation (v1.1.0, 2026-11-03)

Read-only. Status values: CONFORMS · DEVIATES (defect) · DEVIATES (intentional, documented) ·
NOT IMPLEMENTED (deferred, documented) · NOT IMPLEMENTED (undocumented gap).
Evidence is `file:line` at commit v1.1.0 or a test name.

## Doc 03: pipeline, routing and mixed mode

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 3.1 PREPARE: ownership rule, never clear without marker, `staging/<plugin>/` + `scratch/` | CONFORMS | `viwo/core/pipeline/runner.py:95-108`, `viwo/core/workspace.py:71-99`, `Run.ctx` staging per owner `runner.py:54-66`; `tests/test_core_units.py::WorkspaceTests.test_ownership_and_policies` | Staging lives under a temp work dir, not under the workspace (fine: it is moved in by COLLECT). |
| 3.1 PROBE: one GameProbe | CONFORMS | `runner.py:118` (`FolderProbe(run.game)`), `sources.py:149` second probe with `limit=1` | A second cheap probe is built for source roots; no observable deviation. |
| 3.1 DETECT: every enabled plugin, then `select_plugins()` | CONFORMS | `runner.py:69-78,116-122` | Detection exceptions become 0.0 results (D2 spirit). |
| 3.1 INVENTORY / CATALOG stage (D12) | NOT IMPLEMENTED (deferred, documented) | `contracts/pipeline.py:14-23` has no INVENTORY stage; doc 3.1 marks it "optionally… ❓ D12" | Open decision in the contract itself. |
| 3.1 UNPACK: identify by head+tail, carve embedded containers, recursive, main then spare | CONFORMS | `pipeline/unpack.py:40-95`, `identify.py` (via `IdentifyTests.test_suffix_magic_custom_and_carve`), `failover.py:11-35` | Depth cap 10 (`unpack.py:17`), failures recorded per archive. |
| 3.1 UNPACK: after an outer wrapper (Electron/NW.js) is unpacked, detection runs once more | DEVIATES (intentional, documented) | `plugins/electron/__init__.py:1-4` (wrapper members flow through the same unpack queue; no re-detection); no code path re-runs `detect_all` after unpack | Documented only in the plugin docstring; the contract sentence has no implementation. Low impact: nested archives still unpack through slots; plugin selection for inner engines (e.g. RPG Maker MV inside NW.js) relies on the mixed-game markers being visible at the top level. |
| 3.1 EXPORT per plugin into its own staging | CONFORMS | `runner.py:205-217`, `Run.ctx` staging = `work/staging/<owner>` | |
| 3.1 COLLECT: copy from game, move from staging, `<ext>/` layout, `selected_exts` filter, v1 collision naming, dedupe size+hash, provenance map | CONFORMS | `collect.py:112-121` (`_place`: size + sha256), `:124-157`, `:169-185` (provenance), `sources.py:109-127` (`move=False` for game roots); `tests/test_pipeline.py::test_selected_extensions_and_cancel`, `test_game_integrity.py::test_every_plugin_leaves_the_game_untouched` | |
| 3.1 VERIFY: `logic_check_summary` warnings, then plugin `verify()` | CONFORMS | `runner.py:140-146,220-228` | Plus a game-folder snapshot diff (`guard.py:192-207`), beyond the contract. |
| 3.1 SANITIZE stage inside extraction (optional recipe) | NOT IMPLEMENTED (deferred, documented) | No SANITIZE stage in `contracts/pipeline.py`; `ExtractionRequest` has no `sanitize_recipe`/`sanitize_auto_apply` (`pipeline.py:55-66`) | Sanitizer exists only as a separate workspace tool (doc 5). The deferral is implied by roadmap M10 "report-only sanitizer", not stated against 3.1. |
| 3.1 REPORT: manifests in `.extraction_metadata/`, result built | CONFORMS | `runner.py:241-269` (run record `runs/<job>.json`, `provenance.jsonl`, atomic writes) | |
| 3.1 ANALYZE never part of extraction | CONFORMS | no analysis code anywhere (`grep -rl analysis viwo` is empty) | |
| 3.1 Every stage sends events with `stage` set; cancel checked between files | CONFORMS | `runner.py:48-49`, `collect.py:138,145`, `unpack.py` via ctx; `test_pipeline.py::test_selected_extensions_and_cancel` | CARVE and DECODE stages were added (D21) and are not in doc 3.1. |
| 3.2 Request fields | DEVIATES (intentional, documented) | `contracts/pipeline.py:55-66`: `sanitize_recipe`/`sanitize_auto_apply` absent; `on_existing` (doc 4.3) and `carve` (D21) added | Same root cause as the SANITIZE stage. |
| 3.2 v1 payload mapping (`extractionType` missing/""/auto → auto; id → single; mixed → plugins + `mixedPolicy` default selected) | CONFORMS | `contracts/pipeline.py:68-96` | |
| 3.3 Run order: confidence desc, priority desc, id | CONFORMS | `select.py:23-26`; `SelectionTests.test_every_combination` asserts order independence | |
| 3.3 auto / single / mixed-selected / detected / all; never empty; generic fallback | CONFORMS | `select.py:35-50`; `SelectionTests.test_auto_and_fallback` (Unity 0.92 beats Ren'Py 0.78; generic when nothing matches) | Unknown/disabled requested ids now raise `invalid_request` (`select.py:28-34`, added 1.0.1); the contract says "if it's enabled" (silent drop). Stricter, user-facing improvement; note it. |
| 3.4 Unpack: suffix clash between plugins → ini decides, else boot problem | CONFORMS | `wiring/registry.py` `collect()` reports "slot … clashes; ignored" (seen at `registry.py` collect, test `test_registry.py`) | Magic sniffing tie-break (open ❓) not implemented; still open in the doc. |
| 3.4 Export into own staging; no overwrite between plugins | CONFORMS | `runner.py:54-57,210-211` | |
| 3.4 Collect once from all roots, overlapping roots deduped with `path_key` | CONFORMS (with doc inconsistency) | `sources.py:148-165` (nested roots dropped by `parents`), `collect.py:112-121` dedupe by size + hash | Doc 3.4 says "same size and mtime"; doc 4.3 and F6 say size + hash. Code follows 4.3. Doc 3.4 sentence is stale. |
| 3.4 Failure isolation: plugin error in `plugins[i].error`, others still run, success if COLLECT completes | DEVIATES (defect, low) | `runner.py:213-217`: an export failure is recorded in `PluginRun.warnings` as `"<slot>: <kind>: <error>"` and `error` stays `""`; other plugins still run; `success=True` set at `runner.py:147-148` | The isolation holds; only the field differs from the contract (`error` is always empty). |
| 3.4 Result: `extractorType: "mixed"`, detection from first plugin in run order, one `plugins[]` entry each; plugin-specific top-level keys only in single/auto | CONFORMS | `contracts/pipeline.py:127-161`; `test_mixed.py::test_pairs_and_singles` | No plugin-specific top-level keys exist any more (Unity gate removed, see 3.5). |
| 3.5 v1 keys kept | CONFORMS | `contracts/pipeline.py:164-177` `LEGACY_RESULT_KEYS`, `to_legacy_dict` | |
| 3.5 v1 Unity extras (`discoveredCount`, `qualityGatePass`, `completenessReport`, …) | DEVIATES (intentional, documented) | not produced anywhere; roadmap doc 16 M5: "placeholder slices and the fake completeness gate removed" (F11) | |
| 3.5 new keys `contractVersion`, `manifestsPath`; `plugins[]` fields `exportedByKind`, `exportedByTool`, `inventoryCount`, `verifyPassed` | NOT IMPLEMENTED (undocumented gap) | `contracts/pipeline.py:131-158`: new keys present are `mode`, `byBackend`, `runRecord`, `workspace`, `carvedFiles`, `plugins[]{id,detection,exported,backend,warnings,error}` | `/api/distro` carries `contract`; the run record carries the version. The result shape itself never got these keys and no doc records the trim. |
| 3.6 Selection exhaustive over subsets × policies | CONFORMS | `test_core_units.py::SelectionTests.test_every_combination` (31 subsets of 5 ids × 3 policies, plus order independence) | Uses 5 synthetic ids rather than the 13 enabled plugins (63 subsets); the function is id-agnostic. |
| 3.6 Property tests with random confidences | NOT IMPLEMENTED (undocumented gap) | no randomized test in `tests/test_core_units.py` | Low value given the fixed-confidence exhaustive test. |
| 3.6 Pipeline pairwise over every pair + singles on the mixed fixture | CONFORMS | `test_mixed.py::test_pairs_and_singles` (13 singles + 78 pairs on `make_mixed_game`) | Each plugin's own fixture is covered by its own module, not by this test. |
| 3.6 invariants 1-3 (selection non-empty, inside subset, no clashes), 4 (writes only under staging + workspace; game hashes unchanged), 5 (v1 keys, one `plugins[]` entry per plugin), 6 (re-run identical) | CONFORMS | `test_mixed.py:76-91` (sets equal, hashes unchanged, re-run equal), `test_game_integrity.py` (every plugin), `LEGACY_RESULT_KEYS` | Invariant 6 is checked for the generic single run only. |
| 3.6 `sample-custom` plugin via the custom loader | CONFORMS | `examples/plugins/hello/` + `tests/test_registry.py` end-to-end extract through a drop-in | |

Verdict: the stage runner, selection, mixed mode, COLLECT and the game-folder guarantee conform, with stronger behaviour than written in two places (unknown plugin ids refused, game snapshot diff). Two documented deferrals (INVENTORY, in-pipeline SANITIZE), one stale doc sentence (3.4 mtime), one low defect (`plugins[i].error` never set) and one undocumented trim of the 3.5 "new keys".

## Doc 04: HTTP API, workspace layout and configuration

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 4.1 Frozen GET routes kept (`/api/status`, `/api/logs`, `/api/dependencies`, `/api/assets-window`, `/api/assets-window-preview`, `/api/browse-folder`, `/api/media-merger/state`, `/preview/<path>`, static) | CONFORMS | `viwo/api/handlers.py:257-266`, `server.py:103-116` | |
| 4.1 Dropped v1 routes (`/api/state`, `/api/session`, `/api/resume`, `/api/scan`, `/api/extensions`, `/api/detected-extensions`, `/api/assets-preview`, `/api/open-log-dir`, `/api/logs/load`) | DEVIATES (intentional, documented) | doc 04 header "Update (Prototype A)" lists them as dropped; not in `handlers.py` | |
| 4.1 Frozen POST routes kept (extract, keep-selected, trash, restore, delete, clear-trash, sort-*, logs/clear, save-remaining-assets, open-folder, media-merger/*) | CONFORMS | `handlers.py:269-286` | `/api/open-folder` is token-checked (stronger than "origin-checked"); it accepts any existing directory by design (backend audit). |
| 4.1 Error conventions: expected failures `{"success": false, "error"}` HTTP 200; uncaught → 500 `{"error"}`; invalid JSON → 400; unknown POST → 404 | CONFORMS | `server.py:90-101,133-137`; `tests/test_server.py::test_game_folder_and_unknown_routes` | Expected failures also carry `code`/`hint` (additive). |
| 4.1 New routes: `/api/distro`, `/api/plugins`, `/api/detect`, sanitizer plan/apply/undo/recipes, jobs (`POST /api/jobs`, `GET /api/jobs/<id>`, events, cancel) | CONFORMS (minus two) | `routes.py:96-117`, `handlers_tools.py:154-166`; `test_api_routes.py`, `test_sanitizer.py::test_routes` | `POST /api/jobs` (generic submit) does not exist: jobs are created by their own routes. `/api/detect` returns every plugin's detection plus the auto selection only, not "the selection for each mode" (`routes.py:54-62`). Both undocumented. |
| 4.1 `/api/analysis/*` | NOT IMPLEMENTED (deferred, documented) | doc 6 "contract hook only" | |
| 4.1 Optional `/api/extract` fields `extractionType`, `plugins`, `mixedPolicy`, `pluginOptions` | CONFORMS | `contracts/pipeline.py:68-96` | `sanitizeRecipe`, `sanitizeAutoApply` absent (see 3.2). `onExisting`, `carve` added. |
| 4.1 Security 1: per-start token, injected into index.html, `X-VIWO-Token` on every `/api/*` | CONFORMS | `server.py:58-60,71-75,108-110,122-123`, `make_server` token; `test_server.py::test_security_model` | Custom header forces a CORS preflight; no CORS headers are ever sent, so the preflight fails. |
| 4.1 Security 2: JSON only, 415 otherwise | CONFORMS | `server.py:124-126`; same test | Body size cap 16 MiB (413) added. |
| 4.1 Security 3: Host header check | CONFORMS | `server.py:53-56`; same test | |
| 4.1 Security 4: path containment for static and `/preview/` relative to the active workspace | CONFORMS | `server.py` `_static` (WEB_ROOT parents check), `_preview` → `curation/sorting.py:215-224` (`resolve`, reserved dot folders refused); plugin assets `api/plugin_assets.py` containment; `test_security_model` traversal cases | |
| 4.1 Security 5: UI `api()` helper sends the token | CONFORMS | `viwo/web/js/api.js` (`X-VIWO-Token` from the meta tag) | |
| 4.1 Mapping: `/api/extract` submits an `extract` job and waits | CONFORMS | `api/app.py` `extract()` (`submit_with_listener(..., background=False)`) | |
| 4.1 Mapping: merger build as a `merge` job and waits | CONFORMS | `handlers.py:229` `merger_build` via `locked_job("merge", …)` (seen in `KIND` on the web side and `handlers.py`) | |
| 4.1 Mapping: curation routes synchronous under the workspace lock, 409 `busy` during a job | CONFORMS (shape note) | `app.py` `locked()` + `workspace.py:170-185`; `tests/test_curation.py::LockTests.test_curation_is_busy_during_a_job` | Legacy routes answer HTTP 200 with `code: "busy"` (doc 4.1 error convention), while envelope routes map busy → 409 (`routes.py:19-26`). Consistent with "expected failures are 200" for v1 shapes. |
| 4.1 Mapping: `/api/logs` ring buffer; `/api/logs/clear` clears the view only | CONFORMS | `api/app.py` `_log` deque(2000), `clear_logs()`; job histories untouched | |
| 4.2 `/api/dependencies` item shape: five v1 keys + `requirement`, `location`, `hint`; `category` = owner id | CONFORMS | `core/wiring/boot.py` `dependency_report()` | Additive `installable`, `version`. |
| 4.3 Layout: marker, `<ext>/`, `noext/`, `.trash/{groups,items,merger}`, `.extraction_metadata/` + `runs/`, `.sanitizer/` | CONFORMS | `contracts/workspace.py:8-16,24-29`, `curation/trash.py:1-6`, `sanitizer.py:28,143,219` | `.analysis/` absent (deferred with doc 6). |
| 4.3 Marker content: JSON with workspace id, created by, contract version | DEVIATES (defect, low) | `workspace.py:39-42` writes `{"app": "viwo"}` only | Presence is what every check uses (`has_marker`); the documented fields are not written. |
| 4.3 Ownership: clear/replace only inside a marked folder; arbitrary folder with files refused unless empty | CONFORMS (one exception) | `workspace.py:45-52,71-99`, `_replace_groups` keeps reserved dot folders; `test_core_units.py::test_ownership_and_policies` | The configured default workspace folder is exempt from the marker check (`precheck` `is_default`, `workspace.py:77-78`): the app owns that folder by configuration. Not written in the doc. |
| 4.3 Re-extraction policy new/replace/cancel; `needsDecision` + `options` over HTTP; CLI exit 2 without `--on-existing` | CONFORMS | `workspace.py:84-99`, `api/app.py` extract response (`needsDecision`, `options`), `cli.py` `EXIT["needs_decision"] = 2`; `test_pipeline.py::test_rerun_needs_decision_and_replace_is_deterministic` | |
| 4.3 Three trash layouts explicit; v1 trees migrated on first open | CONFORMS | `trash.py:16-49`, `app.py` `locked()` calls `migrate()`; `test_curation.py::test_migrate_and_clear`, `test_trash_restore_delete_exact_names` (F18 exact names) | |
| 4.3 Top-level dot folders reserved everywhere (list, count, sort, merge, keep-selected) | CONFORMS | `trash.py:57-63` (`kept`), `sorting.py:227-232` (`asset_files`), `resolve` refuses reserved, `merger/media.py:93`, `handlers.py:120-134` (`keep_selected` over `kept()`) | |
| 4.3 Collision naming `name__N.ext`, undo `__undoN`, group trash `<ext>_N`, restored `<ext>__N` | CONFORMS | `contracts/workspace.py:15,36-46`, `sorting.py:300-307`, `trash.py:107-113,122-126` | |
| 4.3 COLLECT dedupe size + hash | CONFORMS | `collect.py:112-121` | |
| 4.3 Active workspace = session `assetPath`, fallback `<tempPath>/<outputDir>` | DEVIATES (intentional, documented) | `api/app.py` `App.workspace` defaults to `[server] workspace`; doc 4.5 "Configuration: one file" documents the ini-based default | v1's temp fallback is gone with v1. |
| 4.4 `ProgressEvent { message, level, source, stage, current, total }` | DEVIATES (intentional, documented in code only) | `contracts/types.py:12-24` has no `current`/`total`; counts travel inside the message ("X / Y") and the UI parses them (`web/js/progress.js` header comment) | The contract was not updated; the web side documents the convention. |
| 4.4 Rendered as `[SOURCE:STAGE] message` | CONFORMS | `contracts/types.py:20-24` `legacy_line()` | |
| 4.4 Lines go to the session log and the daily log file | CONFORMS (name changed) | `api/app.py` `log()` → ring buffer + `viwo-YYYY-MM-DD.log` | File name is `viwo-…` not `rpy-extractor-…`; follows the v1 removal, not written in the doc. |
| 4.4 `secret` option values masked before anything is sent | CONFORMS | `runner.py:231-238` (run records), `contracts/plugin.py:92-104` (`tool_output(mask=…)`), `plugins/unreal/pak.py` masks the AES key in streamed output; `tests/test_unreal.py` (`<secret>` in the run record) | |
| 4.5 One ini: `[server]` host/port/workspace/merged/logs/temp relative to the ini; secrets never in the ini | CONFORMS | `core/wiring/ini.py` (`ServerConfig`, secret-looking option keys refused), `core/wiring/settings.py` refuses secret keys from the GUI | |
| 4.6 One global session: `assetPath`, sorting history, logs; log append is a single locked operation | CONFORMS | `api/app.py` (`self.workspace`, `self.history`, `_lock` around append), `set_workspace` clears history on switch | History is cleared when the workspace changes (reasonable; not in the doc). |

Verdict: every security lock, the route set (with the documented drops), the workspace layout, trash layouts, ownership and re-extraction policy conform and are tested. Open points: `POST /api/jobs` and the per-mode `/api/detect` answer were never built and are not documented as dropped; the marker JSON lacks its documented fields; `ProgressEvent` lost `current/total` without a contract note.

## Doc 05: asset sanitizer

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 5.1 Phase 1 scope: zero-byte, extension from magic, exact duplicates by hash, junk, decode health (report only) | CONFORMS | `core/sanitizer.py:28-38,77-122` (`core.zero_byte`, `core.extension`, `core.duplicate`, `core.junk`, `core.health` action `none`) | Health check is a header/structure walk, not a decode through ffprobe/Pillow (doc 5.1 "cheap header check" is one of the two allowed forms). |
| 5.1 Phase 2 lossless conversions, Phase 3 transcode presets | NOT IMPLEMENTED (deferred, documented) | roadmap doc 16.2 M13+ "sanitizer P2–3" | |
| 5.1 Lossy actions never in a default recipe, opt-in per rule | CONFORMS (vacuously) | no lossy rule exists; `handlers_tools.py` `RECIPES` single recipe `lossy: False` | |
| 5.1 Plan first (read-only), apply only accepted actions, one undo token per batch | CONFORMS | `sanitizer.py:125-145` (plan writes only `.sanitizer/plans/`), `:186-232` (`accept` list or `"all-safe"`, `undoToken`), `:235-252`; `tests/test_sanitizer.py::test_plan_apply_undo` | Stale plans refused when a file's size changed (`:186-199`, added 1.0.1). |
| 5.1 Rules declare `cost`, run in cost order, check cancel | DEVIATES (intentional, implicit) | no cost model; fixed order scan → hash; cancel checked per file (`steps.py` `Step.tick`); `test_sanitizer.py::test_cancel_stops_the_scan` | Cost ordering is moot with one cheap recipe; not documented as dropped. |
| 5.1 Undo saved to disk, survives a restart | CONFORMS | `sanitizer.py:219-223` (`.sanitizer/journal/<plan>.json`, atomic), `undo` reads it back | |
| 5.2 `SanitizerRule` / `BatchRule` provider objects from core and plugins (`sanitizer_rules()`), `applies_to` / `inspect` / `fix` | NOT IMPLEMENTED (undocumented gap) | rules are module functions in `sanitizer.py`; `contracts/plugin.py` has no `sanitizer_rules()`; no `Recipe`/`SanitizePlan` types in `contracts/` | The doc calls 5.2 "proposed"; STATUS M10 only claims "sanitizer phase 1 (plan / apply safe / undo)". The plugin extension point is the real gap for the "engine-specific formats" goal of 5.1(3). |
| 5.2 `inspect` never writes | CONFORMS | `sanitizer.py:77-93` read-only (mmap read) | |
| 5.2 `fix` writes only to `.sanitizer/cache/`; core commits: `replace` → original to `.trash`, `rename` with `__N`, `trash` → `.trash` | CONFORMS for `rename` and `trash`; `replace` NOT IMPLEMENTED (deferred, documented) | `sanitizer.py:171-183` (`trash` → `.trash/items/<rel>`, `rename` via `next_free` = `__N`); no `replace`/cache path (phase 2) | |
| 5.2 Lossy recipe cannot be default nor auto-run after extraction | CONFORMS (vacuously) | no auto-run exists (see 3.1 SANITIZE) | |
| 5.2 Journal per apply at `.sanitizer/journal/<plan_id>.json`, undo in reverse | CONFORMS | `sanitizer.py:219-223,242` (`reversed(entries)`) | Several applies of one plan append to one journal (documented in code). |
| 5.2 Rules use media/image backends through slots | CONFORMS (vacuously) | no rule calls a tool; `sniff` uses the carver's sizers | |
| 5.3 `GET /api/sanitizer/recipes` lists recipes with rules and lossy flag | CONFORMS | `handlers_tools.py:66-75,155` | Saved custom recipes: none (no persistence of recipes). |
| 5.3 `POST /api/sanitizer/plan {recipeId, path?}` → paged `SanitizePlan` | DEVIATES (intentional, undocumented) | `handlers_tools.py:77-93`: `recipeId` and `path` ignored (always the active workspace, the one recipe); findings not paged; shape `{planId, scanned, findings}` | Single recipe makes `recipeId` moot; `path?` (any folder) is a real missing feature. |
| 5.3 `POST /api/sanitizer/apply {planId, accept}` → `SanitizeReport {plan_id, applied, failed[], trashed, undo_token}` | CONFORMS (field names differ) | `sanitizer.py:225-232`: `planId, applied, moved[], failed, undoToken` | `trashed` count replaced by the `moved` list (richer); camelCase like the rest of the v1 API. |
| 5.3 `POST /api/sanitizer/undo {undoToken}` | CONFORMS | `handlers_tools.py:87-88`, `sanitizer.py:235-252` | |
| 5.3 UI: a workspace panel (plan → accept → apply) next to sorting and merger | CONFORMS | 08 CLEANUP view (`web/js/views/cleanup.js`), now a visible job (1.1) | |

Verdict: phase 1 is implemented as specified (plan, accept, apply safe, journaled undo, nothing lossy) and tested. The rule/recipe object model and the plugin-provided rules of 5.2, `path?` on plan, paging and the `replace`/cache commit are not built; only phases 2-3 are documented as deferred.

## Doc 06: code analysis hook

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 6.1 `AnalysisTarget` / `CodeAnalyzer` / `AnalysisContext` shapes in `contracts/` | NOT IMPLEMENTED (deferred, documented) | doc 6 header: "contract hook only… no analyzer ships in contract 1.0 or in the prototype"; no `analysis` symbol in `viwo/` | The shapes are not even declared as types; "fixes the shape now" is satisfied by the doc, not by code. |
| 6.1 `EnginePlugin.analysis_targets(probe)` | NOT IMPLEMENTED (deferred, documented) | `contracts/plugin.py` has no such method | |
| 6.2 Ghidra backend, JDK dependency, IL2CPP chain | NOT IMPLEMENTED (deferred, documented) | roadmap M13+ "analysis backends" | |
| 6.3 Analysis never part of extraction; `Stage.ANALYZE`; `analysis` feature flag off by default; output under `.analysis/`; one-time notice | NOT IMPLEMENTED (deferred, documented) | `contracts/pipeline.py:14-23` no ANALYZE stage; `core/wiring/ini.py` features default `(extraction, sorting, merger)` with no `analysis` value validated | Unrpyc ships today as a DECODE-stage slot (`plugins/renpy/decompile.py`, `decode.rpyc`), not as an analyzer: doc 6 said unrpyc "comes with the first analysis milestone". Intentional (owner's 1.0 decision) but doc 6 was not annotated. |
| 6.4 `/api/analysis/*` routes | NOT IMPLEMENTED (deferred, documented) | — | |

Verdict: nothing of doc 6 exists, exactly as its status line says. One note: unrpyc landed early through the decode path rather than the analysis hook; add a revision note to doc 6 so the hook's first milestone is not read as "unrpyc".

## Doc 07: v1 findings and migration map

| Clause | Status | Evidence | Note |
|---|---|---|---|
| H1 extraction moves files out of the game folder → COLLECT copies, moves only from staging | CONFORMS (closed) | `collect.py:174` (`copy2` when `move=False`), `sources.py:155-165`; `test_game_integrity.py` hashes before/after for every plugin; `guard.py` snapshot diff warning | |
| H2 re-extraction deletes a user-chosen folder → ownership marker | CONFORMS (closed) | `workspace.py:71-99`; `test_core_units.py::test_ownership_and_policies` | |
| H3 cross-site requests, text/plain POSTs, static traversal → security model | CONFORMS (closed) | `server.py:53-60,103-137`; `test_server.py::test_security_model` | |
| F1 Unity exports rmtree'd then counted | CONFORMS (closed) | exports go to `work/staging/unity` and are moved by COLLECT (`sources.py:117-127`); nothing is rmtree'd after export | |
| F17 extractall without filters (zip-slip) | CONFORMS (closed) | `backends/archives.py` zip via `safe_member` (1.0.1), tar via `safe_tar_members`; `core/thirdparty.py:_unzip/_untar` `safe_member`; `test_pipeline.py::test_extract_keeps_game_untouched_and_blocks_traversal`, `test_thirdparty.py` | `requires-python >= 3.11` declared (`pyproject.toml`). |
| F11 Unity completeness gate always passes | CONFORMS (closed by removal) | `plugins/unity/__init__.py:88-89` `verify` warns only when nothing was collected; no gate; roadmap M5 | |
| F2 `"mainData"` marker never matched | CONFORMS (closed) | `plugins/unity/__init__.py:46` `"maindata"` (lowercase) in the marker list | |
| F3 only `.trash` filtered; metadata leaks into lists | CONFORMS (closed) | `contracts/workspace.py:19-21` `is_reserved`; used in `trash.kept`, `sorting.asset_files`, `resolve`, merger `media.py:93` | |
| F18 three trash layouts share `.trash/`; prefix matching | CONFORMS (closed) | `trash.py:85-91` exact-name regex; `test_curation.py::test_trash_restore_delete_exact_names` | |
| F4 7-Zip in Program Files not found by the archive code | CONFORMS (closed) | `backends/archives.py` `SEVENZIP` `install_dirs=("7-Zip",)`, `os/windows.py` `_install_roots`; plus the pinned installer | |
| F5 unrpa required at boot | CONFORMS (closed) | `unarchive.rpa` main `rpa-safe` (built-in), unrpa spare only (`viwo slots`) | |
| F19 unpinned pip installs at boot | CONFORMS (closed) | `viwo/data/tools.json` python pins, `pyproject.toml` pinned extras, `test_thirdparty.py::test_manifest_pins_match_pyproject`; `auto_install` installs only pinned entries | |
| F6 dedupe by name+size+mtime | CONFORMS (closed) | `collect.py:112-121` size + sha256 | |
| F20 `/preview/` served from temp path | CONFORMS (closed) | `server.py` `_preview` → `resolve(self.app.workspace, …)` | |
| F8 guessed UABEA/AssetRipper invocations | CONFORMS (closed) | no UABEA/AssetRipper backend; AssetStudioModCLI flags checked against the real `--help` (1.0) | |
| F9 "Permanently deleted (0 files)" | CONFORMS (closed) | `trash.py:136` count before `rmtree` | |
| F10 UI never sends `extractionType` | CONFORMS (closed) | `web/js/views/extract.js:227` | |
| F12 engine knowledge in core (`.rpa`, `.unitypackage`, Ren'Py `game/`) | CONFORMS (closed) | `.rpa` slot in `plugins/renpy`, `.unitypackage` slot in `plugins/unity/__init__.py:30-35`, source roots via `plugin.source_roots()` (`sources.py:150-152`) | |
| F13 OS-specific code spread across modules | CONFORMS (closed) | `viwo/os/{linux,windows,_shared}.py` behind `contracts/os.py` | |
| F14 three `tlog` definitions | CONFORMS (closed, n/a) | single `App.log` + `ProgressEvent` | |
| F15 read-modify-write session log | CONFORMS (closed) | `api/app.py` `log()` under `self._lock` | |
| F16 bogus "SLICE6 optimized" line | CONFORMS (closed, n/a) | v1 code removed | |
| 7.2 file mapping (`core/state.py`, `core/media_types.py`, `core/logging.py`, `core/workspace/curation/`, `os/*/process.py`) | DEVIATES (intentional, documented as "proposed") | actual: `api/app.py` (state + log), `core/curation/sorting.py` (media types), `core/workspace.py`, `core/curation/`, `os/_shared.py` (process runner); the `extract.py` row is marked "done" with the real targets | Module names differ from the proposal; the layer split it describes holds (`ARCHITECTURE.md`). |
| 7.3 order of work (hotfix → characterization → core → engines) | CONFORMS | roadmap doc 16, STATUS A/B | |

Verdict: every finding H1-H3 and F1-F20 is closed in code with a test or a structural guarantee behind it. The 7.2 file map was a proposal and the final module names differ; nothing in it points at a missing capability.

## Counts per doc

| Doc | CONFORMS | DEVIATES (defect) | DEVIATES (intentional, documented) | NOT IMPLEMENTED (deferred, documented) | NOT IMPLEMENTED (undocumented gap) |
|---|---|---|---|---|---|
| 03 | 20 | 1 | 4 | 2 | 2 |
| 04 | 23 | 1 | 4 | 1 | 0 (two sub-items inside the "new routes" row: `POST /api/jobs`, per-mode `/api/detect`) |
| 05 | 11 | 0 | 2 | 2 | 1 |
| 06 | 0 | 0 | 0 | 5 | 0 |
| 07 | 25 | 0 | 1 | 0 | 0 |

## Defects and undocumented gaps worth a ticket (in priority order)

1. `plugins[i].error` is never set; export failures land in `warnings` (doc 3.4). One-line fix in `runner.py:213-217` plus a test assertion in `test_mixed.py`.
2. `.viwo-workspace` content is `{"app": "viwo"}`; doc 4.3 promises workspace id, created-by and contract version. Cheap to add in `workspace.py:39-42`.
3. Doc 3.5 "new keys" (`contractVersion`, `manifestsPath`, `plugins[].exportedByKind/exportedByTool/inventoryCount/verifyPassed`) were never produced and no doc says so: either add them to `to_legacy_dict` or strike them in doc 3.5.
4. `POST /api/jobs` and the per-mode selection in `/api/detect` (doc 4.1 new routes) do not exist; annotate doc 4.1.
5. Sanitizer 5.2 object model and plugin `sanitizer_rules()` hook, `path?` on plan, paging: not built; annotate doc 5 as "phase 1 shipped as core rules; provider model with phase 2".
6. Doc 3.4 "same size and mtime" contradicts doc 4.3 and the code (size + hash): fix the sentence.
7. `ProgressEvent` has no `current`/`total` (doc 4.4): add a contract note that counts travel in the message.
8. Doc 6: add a note that unrpyc shipped as a DECODE slot in 1.0, not through the analysis hook.
9. Wrapper re-detection after Electron/NW.js unpack (doc 3.1): either implement a second detect pass over unpacked wrappers or strike the sentence; today inner engines are selected only from top-level markers.


---

# Conformance audit C: docs 11, 12, 14, 18 against the implementation (v1.1.0, 2026-11-03)

Read-only audit. Status vocabulary: CONFORMS · DEVIATES (defect) · DEVIATES (intentional, documented) ·
NOT IMPLEMENTED (deferred, documented) · NOT IMPLEMENTED (undocumented gap).
"Documented" means a revision note in the doc, STATUS.md, README/CLAUDE.md, or a module docstring says so.

## Doc 11: Runtime capture

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 11.1 revision: anti-cheat markers, online titles, tos-sensitive plugins are warnings + one confirmation, never refusals | CONFORMS | `viwo/core/capture/policy.py:35-70`; `tests/test_capture.py:49` | Warnings list carried into the report (`capture/__init__.py:138`). |
| 11.1 "capture only from a game the user launches through the framework, on their own machine" | CONFORMS | `renderdoc.py:42-58` (renderdoccmd launches the exe); `capture/__init__.py:121` (exe must be inside the game) | |
| 11.1 "prefer static extraction; capture only what static did not produce" | CONFORMS | `capture/__init__.py:110-112` (files already in static provenance are dropped) | |
| 11.1 provenance records that a file came from a capture | CONFORMS | `capture/__init__.py:113` origin `capture:<backend>:<job>` | |
| 11.1 no global hooks, no attaching to foreign processes, no drivers | CONFORMS | `renderdoc.py:42-58` uses `renderdoccmd capture` on a process it starts | |
| 11.1 no game-folder modification without a reversible journal | CONFORMS | `journal.py:36-83`; `tests/test_capture.py:73,93` | RenderDoc path never writes to the game folder; the journal is exercised by tests only. |
| 11.1 precondition: `capture` feature flag off → refuse | CONFORMS | `policy.py:57-60`; `tests/test_capture.py:49` | |
| 11.1 precondition: user confirmation "once per game" | DEVIATES (intentional, documented) | `policy.py:62-67` asks on every run (`needs_decision`) | Confirmation is per call, not persisted per game; docstring says "the user confirms once". |
| 11.1 precondition: anti-cheat service running (OS layer, best effort) | NOT IMPLEMENTED (undocumented gap) | no process scan in `policy.py` or `viwo/os/*` | Only folder markers are checked; no warning for a running service. |
| 11.1 precondition: network reachable → warn, suggest offline | DEVIATES (intentional, documented) | `policy.py:68-70` static advice line, no reachability check | Doc marks it best effort. |
| 11.1 marker list is data, versioned in the repo | CONFORMS | `viwo/data/capture_policy.json` | Comment states "warnings, never refusals". |
| 11.2 graphics-API capture via RenderDoc | CONFORMS | `renderdoc.py` | |
| 11.2 engine runtime agents (BepInEx, UE4SS, Ren'Py hook, Godot override.cfg), Frida, audio loopback | NOT IMPLEMENTED (deferred, documented) | doc 11.6 "prototype scope: one path only"; STATUS M11 | |
| 11.3 capture is a job of kind `capture` | CONFORMS | `viwo/api/handlers_capture.py` (`locked_job("capture")`); `tests/test_api_capture.py` | CLI runs it synchronously through the same function. |
| 11.3 POLICY → SETUP → LAUNCH → CAPTURE → HARVEST → GATHER → DIFF → RESTORE → REPORT | CONFORMS | `capture/__init__.py:119-151` (POLICY, RESTORE-pending, CAPTURE, HARVEST, GATHER, DIFF, REPORT) | SETUP is empty (no agents); RESTORE runs before the session (pending journals) rather than after, which is equivalent while nothing writes to the game folder. |
| 11.3 DIFF by content hash against the latest static extraction | CONFORMS | `capture/__init__.py:36-39,110`; `tests/test_capture.py:117` | Perceptual hashing left open (doc ❓). |
| 11.3 interfaces `launch/trigger/stop/harvest`, `RuntimeAgent`, `LaunchSpec`, `os.launch` | DEVIATES (intentional, documented) | `renderdoc.py:35` single `capture(spec, staging, ctx)`; no `os.launch` | Pilot collapses launch+wait+harvest into one call; interactive trigger is the in-game hotkey (`renderdoc.py:51-55`). Doc 11.3 is a sketch; STATUS calls it a pilot. |
| 11.3 Proton/Wine launch on Linux | NOT IMPLEMENTED (deferred, documented) | doc 11.3 ❓, doc 14.6 "Wine out of scope" | |
| 11.4 journaled overlay: hash-recorded writes, restore in reverse, verify hashes, unfinished restore at next start | CONFORMS | `journal.py:36-83,117-127`; `capture/__init__.py:57-68`; `tests/test_capture.py:73` | Atomic JSON-lines journal, damaged lines skipped with warnings (`tests/test_capture.py:93`). |
| 11.4 copy-the-game mode as an ini option | NOT IMPLEMENTED (deferred, documented) | doc 11.4 ❓ (D13) | |
| 11.5 `capture.gpu` main RenderDoc, spare apitrace | DEVIATES (intentional, documented) | `capture/__init__.py:29` (no spare) | Spare deferred with the other 11.5 slots; STATUS "not verified" lists RenderDoc only. |
| 11.5 RenderDoc Python module as a separate helper process | CONFORMS | `renderdoc.py:63-72`, `rd_harvest.py`; `tools.json` `rdpython` = `qrenderdoc --py` | |
| 11.5 other slots (`capture.gpu-d3d12`, `runtime.*`, `capture.memory`, `capture.audio`) | NOT IMPLEMENTED (deferred, documented) | doc 11.6 | |
| 11.6 every backend declares its network use; offline flags on by default | NOT IMPLEMENTED (undocumented gap) | no `network` attribute in `contracts/slots.py` / `contracts/plugin.py` | Also doc 14.2 #5 and doc 17 L0 lint; no code or test references it. |
| 11.6 copyleft tools run as separate components | CONFORMS | `renderdoc.py:29` isolation subprocess (MIT anyway); GPL backends subprocess everywhere | |
| 11.6 terms of service stay the user's responsibility, stated plainly | CONFORMS | `policy.py:16-19` CONFIRMATION; README "Legal and disclaimer" | |

Verdict: the one path the doc scopes for the prototype (RenderDoc capture, journal, diff, report) is implemented and tested, and the 1.0 revision (warnings instead of refusals) is applied consistently in code, data and tests.
Gaps: no running-anti-cheat-service check, no backend network declaration, confirmation is per run rather than per game; agents, spares and Wine are deferred as the doc says.

## Doc 12: Headless core, CLI and jobs

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 12.1 core boots from the ini without a server; server is one front end | CONFORMS | `viwo/core/wiring/boot.py`; `viwo/api/app.py:get_app` | |
| 12.1 long work runs as jobs with an event stream; `/api/logs` is an adapter | CONFORMS | `viwo/core/jobs.py`; `api/app.py:83-90` (extract job), `handlers_tools.py` (survey, cleanup, repack, preflight, install) | |
| 12.1 every capability reachable from the CLI with `--json` | DEVIATES (intentional, documented) | `cli.py:66-130`; no `merge` CLI | Media merger is UI/API only; doc 14.5 scopes the merger as the v1 job adapter. Documented in `cli_format.WELCOME`/README command table (merger listed under web UI). |
| 12.2 facade: `boot`, `info`, `detect`, `submit`, `jobs.get/list/cancel`, `workspace`, `shutdown` | DEVIATES (intentional, documented) | `boot.py:Runtime.info`; jobs through `JobRunner` (`jobs.py:46-100`) and `App`; no `submit(JobSpec)`, no `shutdown()` | Names provisional per doc; `App` plays the facade role for the server, functions for the CLI. |
| 12.3 job kinds `extract, unpack, sanitize.plan, sanitize.apply, merge, analyze, capture` | DEVIATES (intentional, documented) | kinds in use: extract, survey, merge, repack, preflight, install, cleanup, capture, indexes (`handlers*.py`) | `unpack` is synchronous (`cli_extra.py:81`); sanitizer plan/apply/undo share kind `cleanup`; `analyze` deferred (doc 14.5). |
| 12.3 `JobSpec {kind, params, ini_digest}` serializable and replayable | DEVIATES (intentional, documented) | no JobSpec type; replay works from the extraction run record (`cli_extra.py:28-58`; `tests/test_pipeline.py:126`) | Replay exists for `extract` only; other kinds are not replayable. |
| 12.3 states `queued → running → succeeded | failed | cancelled` | CONFORMS | `jobs.py:22,77-90` | |
| 12.3 `JobHandle {id, kind, state, created, started, finished}` | DEVIATES (defect) | `jobs.py:34-43` summary has `started`, `elapsed`, no `created`/`finished` fields | `started` is set at construction (queued time), so "created" is conflated with "started"; minor. |
| 12.3 events replayable from offset N | CONFORMS | `routes.py:71-78`; `tests/test_api_routes.py:41` | |
| 12.3 result kind-specific | CONFORMS | `routes.py:65-68` | |
| 12.3 run record: JobSpec, effective ini, slot bindings, tool versions, result → `.extraction_metadata/runs/<job>.json` | DEVIATES (defect) | `runner.py:246-266` writes request, bindings, result, viwo version; capture record `capture/__init__.py:141` | Missing: the effective ini and each tool's version/commit. Replay identity is covered by the request + bindings, but the doc's reproducibility record is incomplete. |
| 12.3 "same record + same tools → same output" | CONFORMS | `tests/test_pipeline.py:126` (replay reproduces names, sizes, hashes) | |
| 12.3 concurrency: one lock per workspace; writing jobs hold it; curation takes it with a short timeout → 409 busy; read-only work does not take it | DEVIATES (intentional, documented) | `workspace.py:171-177` (non-blocking, `busy`); `app.py:109-139`; sanitizer plan now runs under `locked_job("cleanup")` (`handlers_tools.py:91`) | Sanitizer *plan* (read-only per doc) takes the lock since it became a visible job (1.1 feedback batch). Timeout is 0 rather than "short". |
| 12.3 cross-process lock | CONFORMS | `workspace.py:140-150` lock file with pid/time, stale takeover; `tests/test_workspace_lock.py` | Beyond the doc. |
| 12.3 cancellation through CancelToken, process tree killed | CONFORMS | `os/_shared.py:49-88` `_kill_tree`; `jobs.py:81-84`; `tests/test_pipeline.py:61` | |
| 12.3b envelope `{ok, data, error, warnings}`, error `{code, message, owner, hint}` | CONFORMS | `contracts/errors.py:36-52` | |
| 12.3b code set | DEVIATES (intentional, documented) | `errors.py:8-20` adds `not_found`, `needs_decision`, `offline` | Additions only; each is mapped to an HTTP status and documented in the CLI epilog. |
| 12.3b outcome mapping `unavailable/failed/needs_key`; refusals use `refused`; programming errors `internal` with trace to the log only | CONFORMS | `jobs.py:82-87`; `server.py:_api` logs and returns `internal`; `cli.py:250-257` | |
| 12.3b HTTP: expected failures 200 `ok:false`; busy 409, invalid_request 400, refused 403, internal 500 | CONFORMS | `routes.py:19-26,87-93` | Plus not_found 404, offline 503. |
| 12.4 commands `info, detect, extract, unpack, slots, sanitize, merge, analyze, capture, serve` | DEVIATES (intentional, documented) | `cli.py:66-130` has info, slots, detect, extract, replay, unpack, survey, repack, capture, sanitize, config, install, diag, indexes, serve | `merge` and `analyze` absent (merger UI-only; analysis deferred, doc 14.5). Extra commands are additions. |
| 12.4 `extract` flags `--plugin/--mixed/--policy/--exts/--workspace/--option` | CONFORMS | `cli.py:132-156` | Plus `--on-existing`, `--carve`. |
| 12.4 `unpack --slot/--backend` | NOT IMPLEMENTED (undocumented gap) | `cli.py:77-80` only `--out/--option` | Slot/backend selection per archive is not exposed. |
| 12.4 `slots --check` (backend self-tests) | NOT IMPLEMENTED (undocumented gap) | `cli.py:67`; doc 14.6 relies on it | Dependency versions are shown (`_query` slots), no self-test run. |
| 12.4 `sanitize plan|apply|undo` | DEVIATES (intentional, documented) | `cli.py:113-116` as `--apply/--undo TOKEN` flags | Same operations, flag form; documented in `viwo sanitize -h`. |
| 12.4 globals `--ini --os --profile --json --quiet --verbose` | DEVIATES (intentional, documented) | `cli.py:54-56` has `--ini --os --json` | `--profile` deferred by doc 9 prototype scope; `--quiet/--verbose` never implemented (no documentation note). Borderline: treat the last two as an undocumented gap. |
| 12.4 exit codes 0/1/2/3/4/130 | CONFORMS | `cli.py:33,41-43,264`; `server.py` strict preflight returns 4; `tests/test_cli.py:63,69`, `tests/test_pipeline.py:81` | 3 covers both "unsupported OS" (`select_os` raises `refused`) and containment refusals, as the epilog states. |
| 12.4 `Start.py` = `viwo serve` with the default ini | CONFORMS | `Start.py` | |
| 12.5 v1 routes as adapters; `/api/extract` waits for the job | CONFORMS | `app.py:83-90` `background=False` | |
| 12.5 `GET /api/jobs/<id>`, `/events?from=N`, `POST /api/jobs/<id>/cancel` | CONFORMS | `routes.py:96-118`; `tests/test_api_routes.py:41` | |
| 12.5 `POST /api/jobs` generic submit | NOT IMPLEMENTED (undocumented gap) | `routes.py:112-118` | Jobs are started only through their own routes. |
| 12.5 curation actions synchronous, not jobs | CONFORMS | `handlers.py:99-151` | |
| 12.5b Python 3.11+, pyproject console entry point | CONFORMS | `pyproject.toml` | |
| 12.5b runtime dependencies pinned in a lock file; tool lock file for CI | CONFORMS | `pyproject.toml` extras pinned; `viwo/data/tools.json`; `ci.yml` `viwo install --all` | |
| 12.5b `pytest` dev-only | DEVIATES (intentional, documented) | `unittest` + `ruff` (CLAUDE.md commands) | |
| 12.6 threads for jobs | CONFORMS | `jobs.py:59-62` | Process isolation per backend not offered. |

Verdict: envelope, codes, job model, events, cancellation, locking and exit codes match the doc; the CLI covers the contract plus 1.0 additions.
Gaps: no generic `POST /api/jobs`, no `unpack --slot/--backend`, no `slots --check`, no `--quiet/--verbose`, run records lack the effective ini and tool versions, and the JobHandle has no `created` field.

## Doc 14: Prototype proposal

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 14.1 orchestration + curation layer, not a format library; every file traceable | CONFORMS | README "Philosophy"; `collect.py` provenance; `ARCHITECTURE.md` | |
| 14.2 #1 identify then extract, head+tail access, carving of embedded containers | CONFORMS | `contracts/slots.py:Identifier`, `Match.embedded`; `tests/test_core_units.py:121` | |
| 14.2 #2 CATALOG → SELECT stage | NOT IMPLEMENTED (deferred, documented) | doc 14.7 D12 open; `rt`-level filtering only via `--exts` and plugin options (DataTool modes) | |
| 14.2 #3 wrapper plugins + one re-detection after unpacking an outer wrapper | NOT IMPLEMENTED (undocumented gap) | no re-detection in `core/pipeline/*.py`; electron plugin unpacks `.asar`/`.nw` but detection is not rerun on the contents | RPG Maker MV inside NW.js is still handled because the MV plugin detects on the game root; TyranoScript/Construct inside a wrapper would not be. |
| 14.2 #4 `keys.*` slot family (user key first, finders as spares) | DEVIATES (intentional, documented) | Unreal: user option, else key found in executables and verified (`plugins/unreal/keys.py`); Godot: user option; STATUS D18 | Implemented as plugin logic, not a slot family. |
| 14.2 #5 every backend declares network use; offline default | NOT IMPLEMENTED (undocumented gap) | see doc 11.6 row | |
| 14.2 #6 GPL backends always subprocess | CONFORMS | `isolation = "subprocess"` on unrpa, QuickBMS, unrpyc, DataTool… | No lint enforces it (doc 17 L0 lists one); not in scope here. |
| 14.2 #7 never unpickle game data in-process | CONFORMS | `plugins/renpy` safe RPA index reader with allow-list (ARCHITECTURE invariants) | |
| 14.2 #8 hard capture refusal policy | DEVIATES (intentional, documented) | doc 11.1 revision; D22 in `docs/contract/README.md` | Warnings since 1.0. |
| 14.3 S-1 hotfix (copy-not-move, marker, token/JSON/Host, safe extraction) | CONFORMS | `collect.py`, `workspace.py`, `server.py:_host_ok/_token_ok`, `safe_member` | |
| 14.3 S0 lean core (contracts, OS layers, ini, binder failover, stage runner, lock, jobs, run records, CLI, generic plugin) | CONFORMS | `viwo/contracts`, `viwo/os`, `core/wiring`, `core/pipeline`, `cli.py` | |
| 14.3 S1–S3 Ren'Py, Unity, Godot with main/spare | CONFORMS | `tests/test_renpy.py`, `test_unity.py`, `test_godot.py`; STATUS evidence | |
| 14.3 S4 Unreal: repak → QuickBMS spare; retoc; AES option | DEVIATES (intentional, documented) | `plugins/unreal/__init__.py` repak main, no QuickBMS spare; retoc raw as spare for IoStore | STATUS M7 states the delivered spares. |
| 14.3 S5 custom plugin loader, open-source showcase (Freedoom), Overwatch optional | CONFORMS | `core/wiring/registry.py` (drop-ins, entry points); `plugins/doom`, `plugins/overwatch`; `examples/plugins/hello` | Overwatch is now auto-selectable with a reminder (D22). |
| 14.3 S6 mixed mode + report-only sanitizer | CONFORMS (exceeded) | `tests/test_mixed.py`; `core/sanitizer.py` has apply/undo (beyond "report-only") | |
| 14.3 S6b round trip into a patched copy, verified | CONFORMS | doc 18 section below | |
| 14.3 S7 capture pilot: policy + journal + RenderDoc + DIFF | CONFORMS | doc 11 section above | Spare apitrace not implemented. |
| 14.4 A1 CLI and HTTP extraction of Ren'Py/Unity/Godot fixtures on Linux and Windows CI, game hashes unchanged | CONFORMS | `ci.yml` matrix; `tests/test_game_integrity.py:33` | CI runs only on major tags (owner's policy); last tag run: Windows green, Linux green after v1.0.1 (WSL verified). |
| 14.4 A2 failover cases main up/down × spare up/down with fakes; L5 with real tools | CONFORMS | `tests/test_core_units.py:53,67`; `ci.yml` real-tools job, `tests/test_l5_tools.py` | |
| 14.4 A3 v1 web UI kept working, characterization tests | DEVIATES (intentional, documented) | v1 UI removed; new UI (`viwo/web`) with lint + headless smoke tests (`tests/test_ui_lint.py`, `test_ui_smoke.py`); roadmap 16.0 "legacy app removed, new UI" | |
| 14.4 A4 replay gives an identical workspace | CONFORMS | `tests/test_pipeline.py:126` | |
| 14.4 A5 product LoC ≤ 5,500 (A) / B ≤ 9,000 | DEVIATES (intentional, documented) | `tools/loc_count.py --report`: viwo 9584 / 9800 | Budget raised with reasons in `loc_caps.ini` (installer, indexes, capture/settings API, add-ons); doc 18.7's total cap of 10,000 still holds. |
| 14.4 B: round-trip tests for Ren'Py, Godot, Unreal, Unity | CONFORMS | `tests/test_roundtrip.py`, `test_godot.py`, `test_unreal.py`, `test_unity.py`, `test_rpgmaker.py` (pack paths) | |
| 14.4 B: capture pilot refusal and restore tests | DEVIATES (intentional, documented) | `tests/test_capture.py:49` tests warnings + feature switch; `:73,93` restore | "Refusal" tests became warning tests under D22. |
| 14.5 not in the prototypes: UI redesign, Wine, decompiler backends, sanitizer apply, Unreal export, RPG Maker/Electron/GameMaker | DEVIATES (intentional, documented) | UI redesigned; sanitizer apply/undo; RPG Maker, Electron, KiriKiri, Source, Bethesda, QuickBMS added; Ren'Py decompile (unrpyc) | All recorded in STATUS (D21 coverage ladder) and release notes; Wine, Unreal export and GameMaker remain out. |
| 14.6 mitigations: pinned versions, spares, `viwo slots --check` | DEVIATES (defect) | pins in `tools.json`; spares; no `--check` | Same gap as doc 12.4. |
| 14.6 Linux parity: tools with native Linux builds | CONFORMS | `tools.json` linux entries; WSL install evidence in STATUS | DataTool Windows-only by design. |

Verdict: every slice S-1 through S7 is delivered and the exit criteria hold or are exceeded, with the owner's documented departures (new UI, more engines, warnings instead of refusals, higher LoC budget).
Gaps: wrapper re-detection (14.2 #3) and backend network declaration (14.2 #5) were never built and are not recorded as deferred; `slots --check` is missing.

## Doc 18: Round trip

| Clause | Status | Evidence | Note |
|---|---|---|---|
| Decisions: output is a patched copy; original read-only; strategy per plugin; same-format first | CONFORMS | `roundtrip.py:1-6,133-148,235-295`; `tests/test_roundtrip.py:59` (original hashes unchanged) | |
| 18.2 provenance map written by COLLECT (`.extraction_metadata/provenance.jsonl`) | CONFORMS | `contracts/workspace.py:PROVENANCE_FILE`; `runner.py:243-245`; `core/provenance.py` rewrite on moves | Rewrite on sort/sanitizer moves goes beyond the doc. |
| 18.2 edit set: modified files by hash | CONFORMS | `roundtrip.py:49-72` | Moved/renamed files are reported as skipped. |
| 18.2 edit set: files the user adds with a target path ("added") | NOT IMPLEMENTED (undocumented gap) | `roundtrip.py:49-72` only iterates provenance entries | Workspace files without provenance are ignored silently; only deletions are marked ❓ in the doc. |
| 18.2 strategies override / rebuild | CONFORMS | `roundtrip.py:85-106` (`override` item, `pack.*` items) | |
| 18.3 POLICY: refusals for online/anti-cheat; tos-sensitive operator-only | DEVIATES (intentional, documented) | `roundtrip.py:124-130` `_reminders` | D22: reminder, never refusal. |
| 18.3 RESOLVE: reject edits whose format differs from the original member | DEVIATES (defect) | `roundtrip.py:49-72` no format check; `plugins/unity/pack.py:2` converts PNG → Texture2D (declared converter) | Raw members are replaced without checking the format; a wrong-format file is only caught, if at all, by VERIFY. Minor: VERIFY re-extraction masks most cases. |
| 18.3 PLAN by plugin `repack_plan(edit_set, provenance)`; shown before writing | DEVIATES (intentional, documented) | `contracts/plugin.py:141` `pack_slot(unarchive_slot)` instead; `--plan` and `POST /api/repack {plan:true}` | Core builds the plan from `pack_slot`; `mod_strategies()`/`repack_plan()` hooks never materialised; roundtrip docstring documents the mechanism. |
| 18.3 COPY: full copy or reflink, never hardlinks | CONFORMS | `roundtrip.py:137-147` `copy2` via `copytree(copy_function=copy)` | Reflinks (❓) not attempted; `symlinks=True` keeps links as links and `_override`/`_container` refuse writing through them (`:182,192-195`). |
| 18.3 PACK through `pack.*` slots inside the copy only | CONFORMS | `roundtrip.py:198-232`; packers write to `container` under `target` | |
| 18.3 VERIFY: re-extract; every edited member has the edited hash | CONFORMS | `roundtrip.py:158-173`; packer `verify` hook (`contracts/slots.py:114`) | |
| 18.3 VERIFY: every untouched member keeps its original hash | DEVIATES (defect) | `roundtrip.py:167-171` checks edited members only | Untouched members are covered by `tests/test_roundtrip.py:57` for the Ren'Py writer, not by the core verify. |
| 18.3 REPORT: run record with plan, edits, backends, verification | CONFORMS | `roundtrip.py:243-252,282-286` → `<target>/.viwo-patched/report.json`, `verified` flag | Written atomically; not copied into the workspace runs folder. |
| 18.3 repack is a job kind `repack` | CONFORMS | `handlers_tools.py:113` `locked_job("repack")`; `tests/test_roundtrip.py:83` | |
| 18.4 `Packer.pack(original, members, out, ctx)`, `supports_rebuild/override` | DEVIATES (intentional, documented) | `contracts/slots.py:105-119` `pack(container, members, ctx)`, `output_for`, `verify`; no `supports_*` flags | Strategy is implied by the slot (override is core-owned); contract docstring states it. |
| 18.5 `pack.renpy-override` core copy into `game/` | CONFORMS | `roundtrip.py:176-189` generic loose override for every engine | |
| 18.5 `pack.rpa` rpa-writer main (own index writer), rpatool spare | DEVIATES (intentional, documented) | `plugins/renpy/pack.py:57`; no spare | Spares for pack slots were not pinned; STATUS M9 lists the delivered packers. |
| 18.5 `pack.pck` godotpcktool main, gdre spare; encrypted needs key | DEVIATES (intentional, documented) | `plugins/godot/pck.py:127`; no spare | Note: the Windows GodotPckTool binary is quarantined by Defender (STATUS), so `pack.pck` is unbound on this machine. |
| 18.5 `pack.pak` override `_P.pak` via repak; signed paks reported, not bypassed | CONFORMS | `plugins/unreal/pak.py:154-200` (`pack.upak`, `.sig` note) | Slot named `pack.upak`; QuickBMS reimport spare not implemented. |
| 18.5 `pack.unity-bundle` unitypy rebuild, uabea spare | DEVIATES (intentional, documented) | `plugins/unity/pack.py:50` (`pack.unity`, TextAsset/Texture2D); no spare | |
| 18.5 `pack.zip` stdlib, `pack.tar` | DEVIATES (intentional, documented) | `backends/packers.py:12` zip only; `roundtrip.py:30` CORE_PACK maps zip only | tar rebuild never added (doc says "later"). |
| 18.5 Overwatch not supported | CONFORMS | no pack slot in `plugins/overwatch`; `_reminders` for sensitive owners | |
| 18.5 extra: `pack.rpgmaker` (MV/MZ) | CONFORMS (beyond doc) | `plugins/rpgmaker/mv.py:90` | |
| 18.6 rule 1: never write the original; target empty or marked | CONFORMS | `roundtrip.py:134,141-148`; `tests/test_roundtrip.py:63,79-81`; `tests/test_game_integrity.py` | Plus a game-folder snapshot diff after the build (`:283-285`). |
| 18.6 rule 2: no signature/anti-tamper bypass; report says the copy may not load | CONFORMS | `plugins/unreal/pak.py:199-200` | |
| 18.6 rule 3: same format only unless a declared converter | CONFORMS | Unity PNG → Texture2D is the declared converter (`unity/pack.py:2`); others raw | No explicit format check (see RESOLVE row). |
| 18.6 rule 4: verified by re-extraction before reported successful | CONFORMS | `roundtrip.py:220-226,282` `verified` flag on the report and in the final event | |
| 18.7 caps: `core/roundtrip` ≤ 450, +150 per plugin, total ≤ 10,000 | CONFORMS | `roundtrip.py` ≤ 250 file cap; viwo 9584 | |
| 18.7 testing: extract → edit → repack → re-extract → hashes match; original untouched; untouched members identical | CONFORMS | `tests/test_roundtrip.py:32-61,63-81` | |

Verdict: the round trip works as the doc decided it (patched copy, per-plugin packers, re-extraction verify, original untouched) and is tested per engine.
Gaps: "added" files are not part of the edit set, untouched members are not re-verified by the core, no same-format check before packing, and no pack spares or `pack.tar`.

## Counts

| Doc | CONFORMS | DEVIATES (defect) | DEVIATES (intentional, documented) | NOT IMPLEMENTED (deferred, documented) | NOT IMPLEMENTED (undocumented gap) |
|---|---|---|---|---|---|
| 11 | 13 | 0 | 5 | 5 | 2 |
| 12 | 17 | 2 | 10 | 0 | 4 |
| 14 | 13 | 1 | 8 | 1 | 2 |
| 18 | 17 | 3 | 7 | 0 | 1 |

Defects worth a tweak: JobHandle `created` field (12.3); run record without effective ini and tool versions (12.3); `slots --check` (12.4/14.6); untouched-member verify and same-format check in repack (18.3).
Undocumented gaps worth a line in STATUS or a feature: running anti-cheat service check (11.1), backend network declaration (11.6/14.2), wrapper re-detection (14.2 #3), `POST /api/jobs`, `unpack --slot/--backend`, `--quiet/--verbose`, "added" files in the edit set (18.2).


---

# Conformance audit: contract README (D0..D22, principles), docs 13, 15, 16, 17

Read-only audit of the working tree at v1.1.0 (2026-11-03). Evidence is `file:line` or a test name.
Status vocabulary: CONFORMS · DEVIATES (defect) · DEVIATES (intentional, documented) ·
NOT IMPLEMENTED (deferred, documented) · NOT IMPLEMENTED (undocumented gap).

## 1. docs/contract/README.md: decisions D0..D22 and principles

| Clause | Status | Evidence | Note |
|---|---|---|---|
| D0 terminology: OS layer `viwo/os/`, `LinuxOS`/`WindowsOS`, backend/main/spare, three trash layouts | CONFORMS | `viwo/os/linux.py:57`, `viwo/os/windows.py:83`; `viwo/contracts/slots.py` SlotBinding main/spare; `viwo/core/curation/trash.py:3` (groups/items/merger) | |
| D1 mixed mode: any plugin set at runtime + combination tests | CONFORMS | `ExtractionMode.MIXED` + `MixedPolicy` in `viwo/contracts/pipeline.py:26`; `tests/test_mixed.py::test_pairs_and_singles` (91 runs) | |
| D2 missing dependency disables the plugin; `strict_preflight` opt-in | CONFORMS | `viwo/core/wiring/registry.py:67,147,174,187` ("disabled: ..."); `viwo/api/server.py:217-231` exit 4; `tests/test_thirdparty.py::test_strict_problems_name_unbound_plugin_slots` | binder also keeps unbound slots as problems |
| D3 Unity per-extension layout | CONFORMS | collect groups every output by extension (`viwo/core/pipeline/collect.py`); Unity meshes land in `obj/` per the agent's tests in `tests/test_unity.py` | |
| D4 sanitizer: health/identity, report-only, nothing lossy by default | CONFORMS | `viwo/api/handlers_tools.py:67-72` single recipe `lossy: False`; plan/apply/undo journaled (`viwo/core/sanitizer.py`) | |
| D5 custom plugins Python first, declarative later | CONFORMS | drop-in `plugin.json` + Python module, entry points (`viwo/core/wiring/registry.py:3-5,29,139-150`); declarative (.ksy/.bms) not done | QuickBMS scripts per game exist through indexes, which is the declarative half |
| D6 macOS later | CONFORMS (deferred) | only linux/windows OS layers; `thirdparty.PLATFORM` is windows/linux | |
| D7 `export.unity` failover: UnityPy main, AssetStudioModCLI spare | CONFORMS | `viwo/plugins/unity/__init__.py:37` | |
| D8 pinned versions + fetched release binaries | CONFORMS | `viwo/data/tools.json` (19 pins, sha256, size), `viwo/core/thirdparty.py` installer | supersedes the sparse-submodule plan of doc 10 (documented in README/STATUS) |
| D9 MIT core; GPL/AGPL only as subprocesses | CONFORMS | `LICENSE`; `isolation="subprocess"` on quickbms-cli (`viwo/plugins/quickbms/__init__.py:46`), unrpa (`viwo/plugins/renpy/rpa.py:106`), sevenzip-cli, ffmpeg; THIRD_PARTY_NOTICES.md | no L0 lint enforces "GPL ⇒ subprocess" (see doc 17) |
| D10 v1 hotfix merged | CONFORMS | v1 removed entirely (prototype-a STATUS "A+") | |
| D11 Ren'Py: safe reader main, unrpa spare | CONFORMS | `viwo/plugins/renpy/__init__.py:24`; `tests/test_renpy.py::test_malicious_index_never_runs` | |
| D12 CATALOG → SELECT optional stage (Prototype B) | NOT IMPLEMENTED (undocumented gap) | no `catalog` anywhere in `viwo/`; stages are prepare/detect/unpack/export/carve/collect/decode/verify/report | STATUS.md does not list it as open; the survey + per-game indexes cover part of the intent |
| D13 journaled overlay + crash recovery | CONFORMS | `viwo/core/capture/journal.py:3,54,66,117`; `tests/test_capture.py::test_restore_and_crash_recovery`, `::test_damaged_journal_restores_what_it_can` | |
| D14 open-source showcase in CI; Overwatch `tos_sensitive`, operator-tested | CONFORMS | Doom/Freedoom L5 (`tests/test_l5_data.py:15-24`, CI Freedoom step); `viwo/plugins/overwatch/__init__.py:29` `tos_sensitive=True`; sqc OPERATOR marks | |
| D15 name ViWo, CLI `viwo` | CONFORMS | `pyproject.toml [project.scripts]` | |
| D16 Doom WAD + Overwatch plugin | CONFORMS | `viwo/plugins/doom/`, `viwo/plugins/overwatch/` | |
| D17 round trip for Ren'Py, Godot, Unreal, Unity | CONFORMS | `pack.rpa`, `pack.pck`, `pack.upak`, `pack.unity` slots (`viwo/plugins/*/__init__.py`); `tests/test_roundtrip.py` | plus RPG Maker and zip (beyond contract) |
| D18 Unreal AES: user key wins, finder verifies against the encrypted index, never stored | CONFORMS | `viwo/plugins/unreal/keys.py:2,75-111`; run records store `<secret>` (`tests/test_overwatch.py`, `tests/test_unreal.py`) | |
| D19 capture pilot in B (policy, journal, RenderDoc harvest, diff) | DEVIATES (intentional, documented) | policy became warnings (`viwo/core/capture/policy.py`), journal/harvest/diff as specified (`viwo/core/capture/__init__.py`) | D22 revision note in doc 11.1 and README |
| D20 real-game check after B | CONFORMS (pending the owner) | `sqc/games.md`, `tools/integration_games.py`, STATUS "not verified" list | |
| D21 coverage ladder; limits: no DRM/anti-cheat circumvention, no key guessing | DEVIATES (intentional, documented) | ladder present: plugins, unpackers (`MAX_DEPTH = 10`, `viwo/core/pipeline/unpack.py:17`), carver (`viwo/core/carve/formats*.py`), zlib/gzip streams (`streams.py`), decoders (`decode.py`), QuickBMS, capture, `survey.py` | the "limits" sentence is superseded by D22: no code for circumvention is authored, but nothing is refused; zstd/LZ4 stream scan from doc 16.0b not present (lz4 only for BSA) |
| D22 no policy boundaries, disclaimer instead | CONFORMS | `viwo/core/capture/policy.py` warnings only; `viwo/core/pipeline/runner.py` no tos filter; `viwo/core/roundtrip.py:124` `_reminders`; `tests/test_capture.py::test_feature_switch_confirmation_and_warnings`; README "Legal and disclaimer" | |
| Principle 1 game folder read-only, single writer, marker-guarded clears | CONFORMS | `tests/test_pipeline.py::test_extract_keeps_game_untouched_and_blocks_traversal`, `tests/test_game_integrity.py`, `viwo/contracts/workspace.py` marker | |
| Principle 2 authenticated local API (token, JSON-only, Host, containment) | CONFORMS | `viwo/api/server.py` `_token_ok/_host_ok`, 415 on non-JSON, `MAX_BODY`; `tests/test_server.py` | |
| Principle 3 OS-specific code only in OS layers | DEVIATES (defect, minor) | `viwo/core/thirdparty.py` runs `msiexec` through `subprocess.run` directly and reads `sys.platform`; `viwo/core/workspace.py` `pid_alive` uses OpenProcess on Windows | small, localized; the OS layer has no "unpack installer" primitive to delegate to |
| Principle 4 every engine behind a slot; stages never call tools directly | CONFORMS | `viwo/contracts/slots.py`, binder; decoders/capture/pack are slots | |
| Principle 5 failures isolated per owner | CONFORMS | `tests/test_core_units.py::test_failover_outcomes`; plugin load errors become problems | |
| Principle 6 plan → apply → undo for destructive bulk actions | CONFORMS | sanitizer (plan ids, stale-plan refusal, undo token), trash groups with restore | |
| Principle 7 reserved dot-folders (`.trash`, `.extraction_metadata`, `.sanitizer`, `.analysis`) | CONFORMS (partial naming) | `.trash`, `.extraction_metadata` used; sanitizer journal lives under `.extraction_metadata`; no `.analysis` yet | |
| Principle 8 determinism (same input + ini → same output) | CONFORMS | `tests/test_pipeline.py::test_replay_reproduces_the_workspace`, `::test_rerun_needs_decision_and_replace_is_deterministic`; distros generator deterministic | |
| Principle 9 honest metrics | CONFORMS | progress rails from real events; survey counts per step; no completeness ratio | |
| Principle 10 versioning `MAJOR.MINOR` | DEVIATES (intentional, documented) | product version is `va.b.c` (`tools/version.py`, CLAUDE.md); contract version stays `1.0` (`viwo/__init__.py:4`) | owner's rule replaced the principle; README table under "Scope decisions" not updated |
| Goal 2: adding an engine needs no core/API/UI change | CONFORMS | registry scan + drop-ins + CLI/UI add-ons (`viwo/api/plugin_assets.py`, `viwo/web/js/registry.js`) | |
| Goal 6: third-party tools vendored as sparse submodules | DEVIATES (intentional, documented) | pinned downloads into `third_party/` instead; doc 10 states the lock-file interim; README/STATUS describe the installer | the README "Goals" list itself still says submodules |
| Layer rule: contracts import nothing from the app; plugins never import each other; direction respected | CONFORMS | grep: no `viwo.core/api/cli` imports under `os/`, `plugins/`, `backends/`, `contracts/`; no cross-plugin imports | not enforced by a lint (doc 17 L0) |
| Distro model: 2 OS × 6 profiles, custom profile from manifests | CONFORMS | `viwo/core/wiring/distros.py`, 12 files in `distros/`, `tests/test_config.py` | |

**Verdict:** 29 clauses: CONFORMS 22 · DEVIATES (intentional, documented) 4 · DEVIATES (defect) 1 (minor, principle 3) · NOT IMPLEMENTED (undocumented gap) 1 (D12 CATALOG) · pending-owner 1 (D20).
The README's own prose (Goals list "sparse submodules", principle 10 "MAJOR.MINOR", D21 "limits") lags the decisions it records; D12 should be either implemented or struck.

## 2. doc 13: landscape coverage

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 13.1 archive breadth through QuickBMS as a bridge | CONFORMS | `viwo/plugins/quickbms/`, pinned 0.12.0, scripts via indexes | GARbro / Game Extractor not wrapped (not required) |
| 13.1 unblob/binwalk-style carving | CONFORMS (own implementation) | `viwo/core/carve/formats.py`, `formats2.py`, `streams.py` | neither tool is wrapped; a native carver was chosen (documented in doc 16.0b) |
| 13.2 #1 identify separate from extract | CONFORMS | `SlotDefinition.identify`, `Match` with offset/size (`viwo/contracts/slots.py`) | |
| 13.2 #2 carving embedded containers, tail reads, depth limit, JSON report | CONFORMS | embedded PCK carving (`viwo/plugins/godot`), `MAX_DEPTH`, run records | entropy check is a density estimate in survey only |
| 13.2 #3 declarative custom formats (Kaitai + QuickBMS) | NOT IMPLEMENTED (deferred, documented) | QuickBMS yes; Kaitai no (D5 "later") | |
| 13.2 #4 sanitizer recipes with typed outputs, version gating, worker pools | NOT IMPLEMENTED (deferred, documented) | one recipe, phase 1 only (doc 5 phase 2-3 deferred in roadmap M13+) | |
| 13.2 #5 plugin discovery through entry points | CONFORMS | `registry.py:29,150` (`viwo.plugins` group) | |
| 13.3 Ren'Py: no in-process unpickling; unrpyc for `.rpyc` | CONFORMS | restricted unpickler in `viwo/plugins/renpy/rpa.py`; `decode.rpyc` via unrpyc subprocess (`viwo/plugins/renpy/decompile.py`) | rpycdec spare not added |
| 13.3 Unity slots (bundle, webgl, export, project, il2cpp) | CONFORMS (partial, documented) | `export.unity` (UnityPy/AssetStudio); UnityWebData/WebGL, AssetRipper project rebuild, Cpp2IL/Il2CppDumper not present | analysis rung is M13+ |
| 13.3 Unreal: repak, retoc, `keys.unreal-aes` user-first, CUE4Parse export wrapper | CONFORMS (partial, documented) | repak/retoc slots, key finder verified (D18); no CUE4Parse wrapper, no locres/json export | "export explicitly out of scope" in roadmap M7 |
| 13.3 Godot: GDRE main, GodotPckTool spare, embedded PCK carving | CONFORMS | `viwo/plugins/godot/`, `tests/test_godot.py` | GodotPckTool build is quarantined by Defender on Windows (STATUS) |
| 13.3 engines ranked after the prototype: RPG Maker, Electron/NW.js, GameMaker, TyranoScript/Love2D, KiriKiri, Wolf/XNA/AGS/Defold/Source | CONFORMS (partial) | RPG Maker, Electron/NW.js (+ `.nw` as zip), KiriKiri, Source, Bethesda delivered; GameMaker, TyranoScript, Love2D, Wolf, XNA, AGS, Defold absent | gaps listed only in the roadmap table ("GameMaker" under M13+) |
| 13.3 wrapper plugins: rerun detection after unwrapping | NOT IMPLEMENTED (undocumented gap) | unpack loop recurses on archives but detection is not rerun on unwrapped app folders | affects Electron/NW.js-wrapped RPG Maker MV: the MV plugin still detects by markers, so the practical impact is low |
| 13.4 code RE tools (Ghidra, ilspycmd, Cpp2IL) | NOT IMPLEMENTED (deferred, documented) | no `analysis.*` slot; roadmap M13+, README "next rungs" | |
| 13.5 vendoring facts (GPL as subprocess, heavy runtimes) | CONFORMS | subprocess isolation flags; .NET runtime pinned under `third_party/dotnet` | JDK not needed yet |

**Verdict:** 15 clauses: CONFORMS 9 (3 partial) · NOT IMPLEMENTED (deferred, documented) 4 · NOT IMPLEMENTED (undocumented gap) 1 (wrapper re-detection) · none defective.
Coverage matches what doc 16 promised for B plus five extra engines; the analysis rung and declarative formats remain roadmap items.

## 3. doc 15: LoC caps

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 15.1 format first (`ruff format`, 100 cols), tokenize-based count, docstrings excluded | CONFORMS | `tools/loc_count.py:_docstring_lines`, `counted_lines`; CI step "L0 format, lint, LoC caps" | |
| 15.1 JS/CSS/HTML counting rule | CONFORMS | `_web_lines` | |
| 15.1 excluded: third_party, generated, fixtures, docs | CONFORMS | only `viwo`, `tests`, `tools` walked | `sqc/fixtures/build_fixtures.py`, `indexes/tools/validate.py`, `examples/` are not counted at all (neither capped nor budgeted) |
| 15.1 the counter itself ≤ 120 counted lines | CONFORMS | `tools/loc_count.py` ≈ 105 counted | |
| 15.3 granularity caps: function 40, class 200, file 250, contracts file 150, params 6 | CONFORMS | `loc_caps.ini [caps]`; enforced in `check_python` | params cap skipped for tests (reasonable, undocumented) |
| 15.3 package budgets as listed (contracts 900, os/_shared 300, os/linux 500, ... total 10,000) | DEVIATES (intentional, documented) | `loc_caps.ini [budgets]` uses coarser prefixes (`viwo/os = 900`, `viwo/core = 4700`, `viwo = 9800`); each raise carries a reason comment | the doc's per-subpackage budgets (core/pipeline 900, core/wiring 700, api 700, backends 1,200/150 per backend) are not represented; `viwo/api` has no budget line at all |
| 15.3 total product hard cap 10,000 | CONFORMS | `viwo = 9800`, currently 9,584 | 2 % headroom |
| 15.3 Prototype B target ≤ 9,000 | DEVIATES (intentional, documented) | 9,584 after 1.0/1.1 scope (installer, indexes, capture/settings views, add-ons); reasons in `loc_caps.ini` | |
| 15.3 web: ratchets on app.js/styles.css/index.html; new modules ≤ 300; total new web 900 | DEVIATES (intentional, documented) | v1 UI removed; `[web] js_file = 300`, `viwo/web = 5400` | ratchet mechanism never implemented (nothing left to ratchet) |
| 15.3 other languages (C# wrappers) | NOT IMPLEMENTED (deferred, documented) | no C# code | |
| 15.4 test caps: file 400, function 60 | CONFORMS | `[caps] test_file/test_function`; enforced | fixture builder 150 / fake 120 caps not distinguished (fixtures live inside test files under the 400 cap) |
| 15.4 test floor ≥ 0.6 × (contracts + core) | CONFORMS (not enforced) | measured 4,850 / 5,612 = 0.86 | no check in the counter |
| 15.5 exceptions section, max 3, expiry milestone, CI fails after expiry | NOT IMPLEMENTED (undocumented gap) | `[exceptions]` exists in the ini but `loc_count.py` never reads it (no `exceptions` in the file) | budget raises were used instead of exceptions |
| 15.5 ratchets only move down, auto-lowered per PR | NOT IMPLEMENTED (deferred, documented) | no `[ratchet]` section; nothing to ratchet since v1 removal | |
| 15.5 raising a budget needs its own commit with the reason | DEVIATES (defect, process) | reasons are in the ini comments, but raises were folded into feature commits (v0.3.0, v1.1.0) | |
| doc 17 L0: ini schema validation of `loc_caps.ini` | NOT IMPLEMENTED (undocumented gap) | unknown keys in `loc_caps.ini` are silently ignored | |

**Verdict:** 16 clauses: CONFORMS 7 · DEVIATES (intentional, documented) 3 · DEVIATES (defect) 1 (process) · NOT IMPLEMENTED (deferred, documented) 2 · NOT IMPLEMENTED (undocumented gap) 2 (exceptions enforcement, caps-ini schema).
The hard caps are real and green; the budget layout is coarser than the doc and the exceptions/ratchet machinery was never built.

## 4. doc 16: roadmap exit criteria

| Clause | Status | Evidence | Note |
|---|---|---|---|
| M0 decisions, glossary, caps agreed | CONFORMS | README decision table closed; D22 added | |
| M1 hotfix + L2 characterization + counter + CI | DEVIATES (intentional, documented) | hotfix done, counter and CI done; L2 golden files never produced (v1 removed instead, prototype-a STATUS "A+") | |
| M2 contracts + OS layers, conformance kit, F4/F13 gone | CONFORMS (partial) | `viwo/contracts`, `viwo/os`; `tests/test_os_layer.py` is the only "conformance" test; no generic kit that a third-party OS layer/plugin can run | kit is an undocumented gap |
| M3 lean core + CLI (ini, binder, stage runner, workspace, jobs, run records, envelope, CLI, generic, core backends) | CONFORMS | prototype-a STATUS; `tests/test_pipeline.py`, `test_core_units.py` | `.7z` failover shown (`test_failover_outcomes`) |
| M4 Ren'Py (safe RPA main, unrpa spare, malicious-RPA test, L5 unrpa) | CONFORMS | `tests/test_renpy.py`, `tests/test_l5_tools.py` | |
| M5 Unity (UnityPy/AssetStudio per D7, placeholders removed, L5) | CONFORMS | `viwo/plugins/unity`, L5 AssetStudio test | real-file round trip still unverified (STATUS) |
| M6 Godot (PCK v1-v4, carving, GDRE → GodotPckTool, key option) ★A | CONFORMS | `tests/test_godot.py`, L5 | |
| M7 Unreal unpack (repak → QuickBMS spare, retoc, AES option) | CONFORMS (partial) | repak main, no QuickBMS spare for `.pak`; retoc; AES per D18 | spare omission undocumented |
| M8 custom plugins: out-of-tree loader, entry points, showcase, Overwatch, CATALOG if D12 | CONFORMS (partial) | loader + entry points (`registry.py`), Doom, Overwatch; CATALOG absent (see D12) | |
| M9 round trip (provenance edit set, per-plugin plan, patched copy, pack slots, verification) | CONFORMS | `viwo/core/roundtrip.py`, `tests/test_roundtrip.py`, provenance rewrite on moves | "copy-on-write clones where supported" not done (documented as plain copy) |
| M10 mixed + sanitizer P1, product ≤ 9,000 ★B | DEVIATES (intentional, documented) | mixed/sanitizer done; LoC 9,584 > 9,000 after 1.x scope (reasons in `loc_caps.ini`) | |
| M11 capture pilot: policy + refusal list, journal, RenderDoc → harvest → DIFF | DEVIATES (intentional, documented) | refusal list became warnings (D22); rest delivered | RenderDoc never run on a real GPU (STATUS) |
| M12 vendoring: tool lock → sparse submodules, bootstrap, nightly L5 on vendored tools | DEVIATES (intentional, documented) | tool lock + automatic installer instead of submodules (`tools.json`, `thirdparty.py`); indexes to become a submodule (`docs/indexes.md`); no nightly | `viwo slots --check` not implemented as such (`viwo slots` + `strict_preflight`) |
| M13+ distro layering + 12 ini + hooks; installer abstraction; RPG Maker/Electron/GameMaker; Unreal export; sanitizer P2-3; analysis backends; UI option forms/run history/sanitizer panel; Wine | CONFORMS (partial) | 12 distro files + `base =` layering (`tests/test_config.py::test_base_layering`); RPG Maker, Electron delivered; UI option forms, run history (04 JOBS), sanitizer panel (08) delivered | `[hooks]`, GameMaker, Unreal export, sanitizer P2-3, analysis, Wine not done (all listed as "next" in README/HANDOFF) |
| 16.0b ladder rung 4: zstd/LZ4 stream scan when modules present | NOT IMPLEMENTED (undocumented gap) | `viwo/core/carve/streams.py` handles zlib/gzip only | the table says "zlib + gzip done", so the gap is visible but the "when present" half is silently absent |
| 16.3 decision gates G0-G6 | CONFORMS | all decisions recorded | |
| 16.4 risks: `viwo slots --check` | NOT IMPLEMENTED (undocumented gap) | no `--check` flag; `strict_preflight` covers the serve path only | |

**Verdict:** 17 clauses: CONFORMS 10 (4 partial) · DEVIATES (intentional, documented) 4 · NOT IMPLEMENTED (undocumented gap) 3 (conformance kit, zstd/LZ4 rung, `slots --check`).
Every milestone through M12 is delivered or consciously replaced; the undocumented gaps are small tooling items.

## 5. doc 17: testing model

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 17.1 no real game data in repo/CI; synthetic fixtures | CONFORMS | `tests/helpers.py` builders; Freedoom (BSD) downloaded in CI only | |
| 17.1 fakes before real tools; real tools skip when absent with a reason | CONFORMS | `fake_tools` pattern; `skipUnless(VIWO_L5)` | |
| 17.1 characterize v1 before changing it | DEVIATES (intentional, documented) | v1 deleted; no characterization suite (prototype-a STATUS) | |
| 17.1 every contract rule has a test | CONFORMS (mostly) | single writer, marker, routing, failover, determinism, warnings policy all tested | import direction and GPL-isolation rules have no test |
| L0 formatter check + LoC caps | CONFORMS | CI "L0" step; `tests/test_pipeline.py::test_loc_caps` | |
| L0 import-direction lint | NOT IMPLEMENTED (undocumented gap) | no lint; direction currently holds by inspection | |
| L0 every GPL/AGPL backend declares `isolation=subprocess` | NOT IMPLEMENTED (undocumented gap) | flags exist (`viwo/contracts/slots.py:58`) but nothing checks license ⇒ isolation | |
| L0 every backend declares its network use | NOT IMPLEMENTED (undocumented gap) | no `network` attribute on `Backend` | the only network code is the installer and update checks (core), which are not backends |
| L0 ini schema validation of `distros/*.ini` | CONFORMS | `viwo config check`, `tests/test_config.py::test_strict_rules`, drift test | |
| L0 ini schema validation of `loc_caps.ini` | NOT IMPLEMENTED (undocumented gap) | see doc 15 | |
| L1 conformance kit (OS layers, plugins, slots, backends) with fakes | CONFORMS (partial) | `tests/test_os_layer.py`, `tests/test_registry.py` (drop-in end to end), `test_core_units.py` | not packaged as a reusable kit for third-party plugins (docs/plugins.md tells authors to copy the fake-tool pattern) |
| L1 routing, ini precedence, identify/carve, value types, journal | CONFORMS | `test_mixed.py`, `test_config.py`, `test_carve.py`, `test_capture.py` | |
| L2 characterization golden files + intended-differences list | NOT IMPLEMENTED (deferred, documented) | no golden files; v1 removed | the doc still describes it as blocking |
| L3 component: each plugin on synthetic fixtures with fakes | CONFORMS | one `test_<engine>.py` per plugin incl. doom, rpgmaker, formats (xp3/asar/vpk/bsa/ba2), quickbms, overwatch | |
| L4 (a) exhaustive selection × policy + pairwise pipeline runs | CONFORMS | `tests/test_mixed.py::test_pairs_and_singles` (91 runs) | |
| L4 (b) slot failover matrix {main up/down} × {spare up/down} × outcomes | CONFORMS (partial) | `test_core_units.py::test_failover_outcomes` covers outcome kinds; the full 2×2×5 matrix per slot is not enumerated | |
| L5 real-tool smoke: nightly on tool images; locally when present | DEVIATES (defect) | CI real-tools job now runs `viwo install --all` but `tests/test_l5_tools.py:70-129` still locates tools through `VIWO_<ID>` env vars that nothing exports, so those tests `skipTest` on CI; only unrpa/UnityPy/7z-on-PATH/Freedoom actually run. No nightly schedule (owner's cost rule) | fix: resolve tools from `thirdparty.found_tools(home)` (or export the env vars after install) so the real-tools job exercises repak/retoc/GDRE/GodotPckTool/AssetStudio/vgmstream again |
| L6 CLI: info/detect/extract → run record → identical re-run | CONFORMS | `tests/test_pipeline.py::test_replay_reproduces_the_workspace`, `::test_info_extract_and_exit_codes` | |
| L6 HTTP: v1 routes through the job adapter | CONFORMS | `tests/test_server.py`, `test_api_routes.py`, `test_api_capture.py`, `test_settings.py` | |
| L6 web UI smoke with Playwright (load, extract, sort, undo, trash, merger list), nightly | CONFORMS (partial, different tool) | `tests/test_ui_smoke.py` + `tests/ui/smoke.mjs` (headless Edge/Chromium over CDP): load every view, extract, cleanup, theme, SORT keys; skipped without a browser | sort undo/trash and merger list flows not in the smoke; CI runners have Chrome, so it would run there, but Node is required and present |
| L7 manual acceptance checklist at milestone exit | CONFORMS (pending the owner) | `sqc/` 147 checks, P0 subset, `sqc/games.md`, `tools/integration_games.py` | not yet executed by hand |
| 17.3 safety catalogue: traversal, symlink, malicious RPA, `.rpyc` pickle, depth bomb, decompression bomb, hook writes outside staging, marker-less PREPARE, hashes unchanged, token/Host/JSON, tar devices/links, capture crash restore, anti-cheat refusal, `/preview` traversal | CONFORMS (mostly) | traversal (`test_pipeline`, `test_formats`, `test_thirdparty`), malicious RPA (`test_renpy`), depth (`MAX_DEPTH`), marker (`test_game_integrity`), hashes, server checks (`test_server`), journal crash (`test_capture`), preview containment (`test_server`); decompression-bomb limit exists for streams (`MAX_STREAMS`, `TOTAL`) and BSA (`max_length`) | no explicit symlink-in-zip test (tar links are filtered: `safe_tar_members`; zip symlinks are extracted as files, which is safe); `.rpyc` pickle analysis slot is now unrpyc in a subprocess (safe by isolation, untested); "anti-cheat ⇒ refused" is reversed by D22 and the doc row is stale; the "plugin hook writes outside staging" sandbox test does not exist |
| 17.4 fixture builders (zip/tar/7z, rpa, pck, pak, unity bundle, game trees, mixed) | CONFORMS | `tests/helpers.py`, `test_renpy.make_rpa`, `test_godot.make_pck`, `test_unreal.make_pak`, `make_game`, mixed trees in `test_mixed.py` | `make_unity_bundle` via UnityPy writer not done (fake UnityPy instead, documented in STATUS) |
| 17.4b tos-sensitive: independent operator, CI fake-only | CONFORMS | `tests/test_overwatch.py` fake DataTool; sqc OPERATOR | the row "operator can't override hard policies / capture stays refused" is superseded by D22 and not revised |
| 17.5 Python 3.11 minimum, test 3.11 and 3.13 | CONFORMS | `requires-python >= 3.11`; CI matrix 3.11/3.13 | |
| 17.5 pytest with l0..l6 markers and `needs_tool` | DEVIATES (intentional, documented) | stdlib `unittest`, env-var gates (`VIWO_L5`, `VIWO_UI`) | CLAUDE.md documents unittest |
| 17.5 CI per push, Linux + Windows, nightly tool image | DEVIATES (intentional, documented) | CI only on `vN.0.0` tags or by hand (`.github/workflows/ci.yml:3-9`, CLAUDE.md) | doc 17.5/17.6 still say "every push" and "nightly"; not revised |
| 17.5 coverage floors (90/80/75 %) | NOT IMPLEMENTED (undocumented gap) | no coverage tooling in CI or pyproject | |
| 17.5 speed budget L0-L4 < 3 min per OS | CONFORMS | full suite 236 s on Windows incl. the browser smoke; 55-80 s without it | |
| 17.6 definition of done (green on both OSes, caps, safety tests, L7 per engine, docs) | CONFORMS (partial) | Windows green at v1.0.0, Linux green at v1.0.1 locally (WSL), CI Linux unverified since; L7 pending | |

**Verdict:** 31 clauses: CONFORMS 19 (6 partial) · DEVIATES (intentional, documented) 4 · DEVIATES (defect) 1 (L5 tool lookup on CI) · NOT IMPLEMENTED (deferred, documented) 1 · NOT IMPLEMENTED (undocumented gap) 6.
The pyramid exists at every level except L2; the one real defect is that the CI real-tools job no longer finds the tools the installer just installed, and doc 17 itself still describes per-push CI, nightly runs, Playwright, pytest and refusal-based capture.

## Totals

| Doc | CONFORMS | DEVIATES (intentional, documented) | DEVIATES (defect) | NOT IMPLEMENTED (deferred, documented) | NOT IMPLEMENTED (undocumented gap) |
|---|---|---|---|---|---|
| README (D0-D22, principles, goals) | 22 | 4 | 1 | 0 | 1 (+1 pending owner) |
| 13 landscape | 9 | 0 | 0 | 4 | 1 |
| 15 LoC caps | 7 | 3 | 1 | 2 | 2 |
| 16 roadmap | 10 | 4 | 0 | 0 | 3 |
| 17 testing model | 19 | 4 | 1 | 1 | 6 |

Defects worth fixing first: (1) L5 tests resolve tools through `VIWO_*` env vars the CI job no longer sets; (2) `loc_caps.ini [exceptions]` is parsed by nobody; (3) budget raises folded into feature commits. Docs to revise to match decisions: README goals/principle 10/D21 wording, doc 17 (CI cadence, Playwright, pytest, capture refusal rows), doc 15 budget layout, D12 CATALOG (implement or strike).

