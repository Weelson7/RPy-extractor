# Contract conformance (re-audit at v1.2.0, closure in v1.2.1, 2026-11-03)

Clause-by-clause audit of the implementation against every document in `docs/contract/`, by
four independent reviewers (one per document group), each row re-read against the current code
and the current doc text; then every defect and undocumented gap was closed in 1.2.1 (code,
tests or a doc revision with a History line) and its row rewritten with the new evidence.
Statuses: CONFORMS; DEVIATES (defect); DEVIATES (intentional, documented); NOT IMPLEMENTED
(deferred, documented); NOT IMPLEMENTED (undocumented gap). "Documented" means the contract doc
itself, `docs/prototype-b/STATUS.md`, README.md or ARCHITECTURE.md says so.

History: the v1.1.0 audit found 532 clauses (374 conform, 23 defects, 34 undocumented gaps); the
1.2 batch implemented the list; this re-audit counts 592 rows (the revised docs added
clauses) and closes the rest.

> **1.3.x note (2026-11-04):** the review batches of 1.3.1-1.3.4 moved symbols (the runner's
> export and re-detection live in `pipeline/export.py`, `detect_all` with the probe, the pid
> check in `viwo/os`, the payload parser in `viwo/api/app.py`, one media table in
> `viwo/core/media.py`, one `core_context`, one `teller`, one `failure`); evidence below names
> the current symbols, line numbers are those of the v1.2.1 audit. Rung A1 of the static arm
> (doc 6) shipped in 1.3.0 and its rows read CONFORMS; four engine plugins were added in 1.3.3.

| Status | Rows |
|---|---|
| CONFORMS | 501 |
| DEVIATES (defect) | 0 |
| DEVIATES (intentional, documented) | 53 |
| NOT IMPLEMENTED (deferred, documented) | 38 |
| NOT IMPLEMENTED (undocumented gap) | 0 |
| Total | 592 |

## Still open as a defect or undocumented gap

None.

## Not covered by this pass

Docs 06 (analysis hook), 11 (runtime capture) and 18 (round trip) were rewritten by the
capabilities respec (three arms: static, dynamic, authoring) in the same commit as this
closure; their sections below audit the v1.2.0 text. The next audit re-reads them against
the new text.

---

# Conformance audit A (re-run): contract docs 00, 01, 02, 08, 09, 10 vs implementation (v1.2.0, contract 1.1, 2026-11-03)

Scope note: `git diff v1.1.0..HEAD -- docs/contract/` shows that none of these six documents changed in the 1.2 batch (only 03-07, 13, 15-17 and README were revised). "Documented" below therefore comes from the clause text itself, `docs/contract/README.md` (History lines, decisions), `docs/contract/16-roadmap.md`, `docs/prototype-b/STATUS.md`, `README.md` or `ARCHITECTURE.md`. Every CONFORMS row names code opened at the current tree; test names exist in the current suite.

## 00 Glossary and semantic model

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 0.1 assets dir → workspace | CONFORMS | `viwo/contracts/pipeline.py:61-62,153` (`workspace` field and key), `viwo/core/workspace.py` | legacy `assetPath` kept for `/api/extract` compatibility (doc 4) |
| 0.1 session = UI session (memory only); persisted state has an explicit store | CONFORMS | `viwo/api/app.py:37` (`reload`, in-memory app), `viwo/core/records.py:12-35` and `viwo/core/pipeline/runner.py:257-282` (run records as the explicit store) | |
| 0.1 generic = plugin id; "no engine" = undetected outcome | CONFORMS | `viwo/plugins/generic/__init__.py:8`, `viwo/core/pipeline/select.py:46-49` | generic is chosen when no other plugin scores above 0 |
| 0.1 copied = moved; v1 key names stay, meaning documented | CONFORMS | `viwo/contracts/pipeline.py:144,155` | `copiedFiles` now counts real copies (nothing is moved out of the game); `movedFiles` is fixed at 0 |
| 0.2 OS layer: package `viwo.os`, the only place for OS code | CONFORMS | `viwo/os/__init__.py:14-30`, `viwo/os/_shared.py:9,37-48` | one recorded exception: `viwo/core/thirdparty.py:211` (msiexec), listed in contract README principle 3 |
| 0.2 profile; distro = OS + profile in an ini | CONFORMS | `viwo/core/wiring/distros.py:27-31`, `distros/*.ini` (12 files) | |
| 0.2 extraction run as a job; run record in `.extraction_metadata/runs/` | CONFORMS | `viwo/core/pipeline/runner.py:257-282`, `viwo/core/records.py:12-35`, `viwo/cli.py:116-118` (`JobRunner`) | |
| 0.2 feature switches (extraction, sorting, merger, sanitizer, analysis, capture) | DEVIATES (intentional, documented) | `viwo/core/wiring/ini.py:23`, `startup.ini:9` | features are extraction, sorting, merger, capture; the sanitizer rides on sorting; analysis is open (doc 16 M13+) |
| 0.2 slot / backend / main / spare / tool / dependency | CONFORMS | `viwo/contracts/slots.py:41-50,53-71,160-171`, `viwo/contracts/types.py:72-94` | |
| 0.2 vendored tool = sparse submodule | DEVIATES (intentional, documented) | `viwo/core/thirdparty.py:1-8`, contract README goal 6 History ("the lock file plus installer replaced them") | pinned release binaries under `third_party/` |
| 0.2 game folder never modified; COLLECT copies | CONFORMS | `viwo/core/pipeline/runner.py:99,132,146-148` (`refuse_writes_inside`, before/after snapshot), `viwo/contracts/plugin.py:153-155`, `tests/test_conformance_kit.py` `test_export_writes_only_inside_staging_and_scratch` | |
| 0.2 workspace marker `.viwo-workspace` | CONFORMS | `viwo/contracts/workspace.py:8`, `tests/test_core_units.py` `test_ownership_and_policies` | |
| 0.2 staging / scratch / workspace / group / container / inventory | CONFORMS | `viwo/contracts/plugin.py:98-109,172-175` | `inventory` is now a plugin hook (2.2) |
| 0.2 round-trip terms (provenance map, edit set, patched copy, pack) | CONFORMS | `viwo/contracts/slots.py:142-157` (`Packer`), `viwo/core/roundtrip.py:125` (patched-copy context), `viwo/core/pipeline/runner.py:260-261` (provenance file) | |
| 0.2 curation / sanitizer / merger terms | CONFORMS | `viwo/core/sanitizer.py:5,22,63`, `viwo/core/sanitizer_rules.py:183-186`, `viwo/core/merger/ffmpeg.py:40-49` (`Timeline`) | |
| 0.2 analysis target / analyzer | NOT IMPLEMENTED (deferred, documented) | doc 16 M13+ ("open: analysis backends"), `README.md:66-68` ("next rungs") | |
| 0.4 keep v1 metric keys and add `movedFiles`, `inventoryItems`, `collectedFromInventory` | CONFORMS | `viwo/core/pipeline/checks.py:22` (`verify_one`: `inventory()` + `verify_report()` feed `inventory_items`/`inventory_found`), `viwo/contracts/pipeline.py:155-157` | a plugin without an inventory reports 0 (no completeness claim, doc 0.4); a plugin that overrides the 1.0 `verify()` keeps that path |
| 0.4 a completeness claim holds only when inventory counts the same kind of item as collection | CONFORMS | `viwo/contracts/plugin.py:55-62,172-175` (0 = no claim), `viwo/contracts/pipeline.py` (`PluginRun.to_legacy_dict`) | no plugin claims completeness today |
| 0.5 questions (OS name, backend/main/spare, trash split, metric names) | CONFORMS | contract README D0 (OS, backend/main/spare, three trash layouts), `viwo/contracts/pipeline.py:141-157` (v1 keys frozen, new keys beside them) | all four answered |

Verdict: the glossary vocabulary is the code vocabulary; the only open point is that the new inventory metrics exist as keys but are never fed.
Open: 0.2 feature switches (extraction, sorting, merger, sanitizer, analysis,  (intentional) · 0.2 vendored tool = sparse submodule (intentional) · 0.2 analysis target / analyzer (deferred).

## 01 OS contract

| Clause | Status | Evidence | Note |
|---|---|---|---|
| OS: os_id, is_supported_host, process, tools, shell, fs | CONFORMS | `viwo/contracts/os.py:87-110`, `viwo/os/windows.py:104-133`, `viwo/os/linux.py:68-100` | |
| OS: `display_name` | CONFORMS | `viwo/contracts/os.py:91`, `viwo/os/windows.py:106`, `viwo/os/linux.py:70`, `viwo/core/wiring/boot.py:70` (`osName`) | |
| OS: `installer : PackageInstaller` | NOT IMPLEMENTED (deferred, documented) | doc 1.3 note; `viwo/contracts/os.py:3-4` ("not an OS-layer concern"); replaced by `viwo/core/thirdparty.py` (contract README goal 6) | |
| 1.1 `max_command_length`, `python_executable`, `run(argv, cwd, env, timeout, cancel)` | CONFORMS | `viwo/contracts/os.py:16-38`, `viwo/os/_shared.py:22-64` | `on_line` streaming added, documented in the contract docstring |
| 1.1 `ProcessResult { returncode, stdout, stderr, timed_out, ok }` | CONFORMS | `viwo/contracts/types.py:107-116` | |
| 1.1 UTF-8 with errors=replace | CONFORMS | `viwo/os/_shared.py:44-46` | |
| 1.1 never raises on non-zero exit; FileNotFoundError only when it cannot start | CONFORMS | `viwo/os/_shared.py:50-64` (only `Popen` raises), `tests/test_os_layer.py` `test_run_and_exit_code` | |
| 1.1 timeout/cancel kills the whole tree (taskkill /T, process group) | CONFORMS | `viwo/os/windows.py:20-27,109-110`, `viwo/os/linux.py:17-21,74-76`, `test_timeout_kills_tree`, `test_cancel`, `test_streaming_respects_cancel` | |
| 1.1 `max_command_length` 32767 / ARG_MAX-derived; merger switches to file args | CONFORMS | `viwo/os/windows.py:110`, `viwo/os/linux.py:73-75` (ARG_MAX/2, floor 4096), `viwo/core/merger/build.py:158-164` (`-filter_complex_script`) | |
| 1.2 `locate(spec)` side-effect free, `known_install_dirs(spec)` | CONFORMS | `viwo/os/_shared.py:127-168`, `tests/test_conformance_kit.py` `test_locate_never_installs_or_writes` | |
| 1.2 `status(spec, owner) -> DependencyStatus` | DEVIATES (intentional, documented) | `viwo/core/wiring/boot.py:44-65` (`dependency_report`) | status lives on the Runtime in the doc 4.2 item shape, not on the locator |
| 1.2 `ToolLocation { dep_id, path, argv_prefix, source }` with the five sources | CONFORMS | `viwo/contracts/types.py:97-104` | |
| 1.2 argv_prefix examples (`python -m x`, `cmd /c x.bat`) | CONFORMS | `viwo/os/_shared.py:153`, `viwo/os/windows.py:30-33`, `viwo/os/_shared.py:143-145` (argv-tuple overrides for dotnet/qrenderdoc) | |
| 1.2 search order: ini `[tools]` → env var → PATH (+ .exe/.bat/.cmd) → known dirs | CONFORMS | `viwo/os/_shared.py:138-168`, `viwo/os/windows.py:111`, `tests/test_os_layer.py` `test_search_order` | a python-module step sits between env and PATH (`contracts/os.py:44-45`); `third_party/` tools enter as config overrides (`boot.py:99`); doc 1.2 says `[tools]` is keyed by backend id while doc 9 and the code key by dependency id |
| 1.2 Windows known dirs: ProgramFiles, ProgramFiles(x86), scoop `apps/*/current`, chocolatey `lib/*/tools`, LOCALAPPDATA\Programs | CONFORMS | `viwo/os/windows.py:85-101`, `viwo/os/_shared.py:117-125` (glob roots expanded) | superset: LOCALAPPDATA, ProgramData, scoop shims and choco bin are also searched |
| 1.2 Linux known dirs: /usr/bin, /usr/local/bin, /opt/*, ~/.local/bin, flatpak exports | CONFORMS | `viwo/os/linux.py:54-65` | system and user flatpak exports |
| 1.2 one locator for status and calls (fixes F4) | CONFORMS | `viwo/contracts/slots.py:66-71` (`available` → `locate`), `viwo/core/decode.py:73`, `viwo/core/wiring/boot.py:49` | |
| 1.3 PackageInstaller (pip → winget/choco/scoop; never elevates; only with auto_install) | NOT IMPLEMENTED (deferred, documented) | doc 1.3 note; `viwo/core/preflight.py:87-98` (pinned downloads, `auto_install` honoured at `:93`) | |
| 1.4 `open_folder`, `pick_folder`, `pick_file`; None on headless | CONFORMS | `viwo/contracts/os.py:72-84`, `viwo/os/_shared.py:180-221` | |
| 1.4 Linux fallback tkinter → zenity → kdialog | NOT IMPLEMENTED (deferred, documented) | doc 1.4 prototype note; `viwo/os/linux.py:47-51` | |
| 1.5 `case_sensitive`, `path_key`, `sanitize_filename`, `is_valid_filename` | CONFORMS | `viwo/os/windows.py:36-53`, `viwo/os/linux.py:24-38` | |
| 1.5 `long_path(path)` (`\\?\` prefix) | CONFORMS | `viwo/contracts/os.py:66-69`, `viwo/os/windows.py:55-62,82` | no core caller and no test yet |
| 1.5 Windows rules (forbidden chars, trailing dot/space, reserved names, 255) | CONFORMS | `viwo/os/windows.py:16-17,44-53`, `tests/test_os_layer.py` `test_windows_rules` | |
| 1.5 Linux rules (no `/`, NUL, `.`, `..`) | CONFORMS | `viwo/os/linux.py:32-38` | |
| 1.5 one rule replaces Unity `_safe_name`, sort rename check, merger output name | CONFORMS | `viwo/core/curation/sorting.py` (`fs.is_valid_filename`), `viwo/cli_extra.py` (`fs.sanitize_filename`), `viwo/core/merger/build.py:68` (`output_name(raw, fs)` through `fs.sanitize_filename`); `tests/test_merger.py::ProbeSlotTests` | the merger's private regex is gone (1.2.1) |
| 1.6 case-insensitive engine markers through the probe | CONFORMS | `viwo/core/pipeline/probe.py:19-20,31-32,36-41` | |
| 1.6 executable suffix handling / open folder per OS | CONFORMS | `viwo/os/windows.py:66-73,111`, `viwo/os/linux.py:42-45,78` | |
| 1.6 installers column (pip, winget, choco, scoop / pip + hints) | NOT IMPLEMENTED (deferred, documented) | as 1.3; `viwo/core/thirdparty.py:225-262` installs pins instead | |
| 1.7 `max_command_length > 0` | CONFORMS | `tests/test_os_layer.py:85` | |
| 1.7 sanitize set (empty, `.`, `..`, CON, nul.txt, a/b, a\b, x:y, trailing, control, NUL, Unicode, 300) | CONFORMS | `tests/test_os_layer.py:18-44` (`NASTY`, both policies) | |
| 1.7 `path_key` stable and case-folded on Windows | CONFORMS | `tests/test_os_layer.py:46-55` | |
| 1.7 `locate()` never installs; checked with a recording fake | CONFORMS | `tests/test_conformance_kit.py:134-159` `test_locate_never_installs_or_writes` (spied `open`, `makedirs`, `copy2`, `urlopen`) | |

Verdict: the OS layer now matches doc 1 in shape, search order, known dirs, `long_path` and `display_name`, with the conformance test the previous audit found missing; the installer and dialog fallbacks remain documented deferrals.
Open: OS: `installer : PackageInstaller` (deferred) · 1.2 `status(spec, owner) -> DependencyStatus` (intentional) · 1.3 PackageInstaller (pip → winget/choco/scoop; never elevates; only wit (deferred) · 1.4 Linux fallback tkinter → zenity → kdialog (deferred) · 1.6 installers column (pip, winget, choco, scoop / pip + hints) (deferred).

## 02 Engine plugin contract

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 2.1 manifest: `plugin_id`, `name`, `version`, `engine_type`, `contract`, `priority`, `options`, `builtin` | CONFORMS | `viwo/contracts/plugin.py:33-51` | |
| 2.1 manifest: `description`, `capabilities`, `dependencies`, `OS layers` | CONFORMS | `viwo/contracts/plugin.py:48-51`, `viwo/core/wiring/registry.py:72-75` (`os_layers` validated), `viwo/plugins/godot/__init__.py:35-37` | capability vocabulary in code is detect/unpack/export/pack/decode; most built-ins leave it empty; `dependencies` lists ids for people, backends carry the specs |
| 2.1 `plugin_id` slug `[a-z][a-z0-9_-]{1,31}`, unique | CONFORMS | `viwo/core/wiring/registry.py:31,60-61,170-171,306-314`, `tests/test_conformance_kit.py` `test_every_builtin_passes_validate_plugin` | built-ins and drop-ins validated alike |
| 2.1 `PluginOption { key, label, type, default, choices, help }`, types string/secret/bool/int/float/choice/path | CONFORMS | `viwo/contracts/plugin.py:20-30`, `viwo/core/wiring/registry.py:69-71` | the field is named `kind` |
| 2.1 secrets never logged nor written to manifests | CONFORMS | `viwo/core/pipeline/runner.py:29,247-254` (`<secret>` in run records), `viwo/contracts/plugin.py:115-128` (mask in tool output), `viwo/core/wiring/ini.py:99-101` | |
| 2.2 `detect(probe)` and `manifest` required | CONFORMS | `viwo/contracts/plugin.py:137-142` | |
| 2.2 `slot_definitions()`, `backends()` default empty | CONFORMS | `viwo/contracts/plugin.py:147-151` | |
| 2.2 `source_roots(game_root, probe)` default `[game_root]`; `skip_dirs()` | CONFORMS | `viwo/contracts/plugin.py:153-158`, `viwo/plugins/renpy/__init__.py:58-60` | |
| 2.2 `inventory(ctx)` | CONFORMS | `viwo/contracts/plugin.py:172-175`, called from the `verify` shim at `:187` | the counts it yields are discarded (see 0.4) |
| 2.2 `export(ctx) -> ExportReport` on the plugin | DEVIATES (intentional, documented) | `viwo/contracts/plugin.py:168-170` (`export_slot`), doc 8.5 (`export.<plugin_id>`), `viwo/core/pipeline/runner.py:209-229` | the plugin names its export slot; the Exporter backend does the work |
| 2.2 `verify(ctx, inventory, export, collected) -> VerifyReport` | CONFORMS | `viwo/contracts/plugin.py:54-62,177-190` (`verify_report` with that signature, `verify` as the 1.0 shim), `viwo/plugins/unity/__init__.py:94-97` | the runner (`runner.py:238`) still calls the 2-arg shim |
| 2.2 `sanitizer_rules()` | CONFORMS | `viwo/contracts/plugin.py:192-194`, `viwo/core/sanitizer_rules.py:183-186` | |
| 2.2 `analysis_targets(probe)` | NOT IMPLEMENTED (deferred, documented) | doc 16 M13+ ("open: analysis backends") | |
| 2.2 extra hooks (`configure`, `claimed_suffixes`, `pack_slot`, `cli_commands`, `ui_module`) | CONFORMS | `viwo/contracts/plugin.py:144,160,164,196,200` | extensions; add-ons documented in `docs/plugins.md` |
| 2.2 detect fast and pure; same result twice | CONFORMS | `viwo/core/wiring/registry.py:76-81` (checked at load), `tests/test_conformance_kit.py` `test_detect_is_pure_on_empty_and_fixture_probes` | |
| 2.2 export writes only into staging/scratch; nothing deleted outside staging | CONFORMS | `viwo/contracts/slots.py:103-104`, `tests/test_conformance_kit.py` `test_export_writes_only_inside_staging_and_scratch` | |
| 2.2 exception in a hook → warning for that plugin, not a crash | CONFORMS | `viwo/core/pipeline/runner.py:76-81,240-242`, `viwo/core/pipeline/failover.py:29-32` | |
| 2.3 GameProbe: root, truncated, has_name, find, with_suffix, head, tail; bounded, one scan | CONFORMS | `viwo/contracts/plugin.py:77-91`, `viwo/core/pipeline/probe.py:11-57` (50k limit, `truncated`) | |
| 2.3 ExtractionContext: request_id, game_root, staging, scratch, selected_exts, options, detection, OS, progress, cancel, log | CONFORMS | `viwo/contracts/plugin.py:94-113` | |
| 2.3 ExtractionContext `probe` | CONFORMS | `viwo/contracts/plugin.py:109`, `viwo/core/pipeline/runner.py:67` (`Run.probe` built once by DETECT, handed to every plugin context of the game root) | tool contexts (`unpack`, repack, capture) pass None, as the field comment says |
| 2.4 DetectionResult { engine_type, confidence, evidence[], plugin_id } and legacy JSON | CONFORMS | `viwo/contracts/types.py:44-62` | range 0..1 enforced |
| 2.4 confidence scale | CONFORMS | `viwo/plugins/renpy/__init__.py:39-46`, `unity/__init__.py:66-77`, `godot/__init__.py:70-80`, `unreal/__init__.py:62-75`, `generic/__init__.py:19-22` | |
| 2.5 plugins introduce slots and ship backends; core owns zip/tar/7z/rar | CONFORMS | `viwo/backends/__init__.py:12-46`, `viwo/plugins/*/__init__.py` `slot_definitions` | |
| 2.5 main/spare from ini with plugin defaults | CONFORMS | `viwo/core/wiring/binder.py:26-44` | |
| 2.5 recursive loop: queue, seen-set, `archive_NNNNN_<uuid8>`, nested detection | CONFORMS | `viwo/core/pipeline/unpack.py:40-65` | |
| 2.5 slot lookup: longest suffix first, then magic | CONFORMS | `viwo/core/pipeline/identify.py:13-32`, `tests/test_core_units.py` `test_suffix_magic_custom_and_carve` | custom identifiers (exe trailers) run before both |
| 2.5 every unarchive backend prevents traversal | CONFORMS | `viwo/backends/archives.py:12,36-45,57`, `viwo/contracts/slots.py:95-96` | |
| 2.5 ownership table (zip/tar/7z/rar core; rpa renpy; unitypackage unity; pck godot; pak/iostore unreal) | DEVIATES (intentional, documented) | `viwo/plugins/unreal/__init__.py:39-48` (`unarchive.upak`, `unarchive.utoc`), doc 16 M7 note names `unarchive.upak` | ids `upak`/`utoc` instead of `pak`/`iostore` (".pak is used by many engines"); docs 2.5 and 8.4 tables not updated |
| 2.6 DependencySpec { dep_id, label, kind, requirement, import_name, executables, env_var, hint } | CONFORMS | `viwo/contracts/types.py:71-94` | |
| 2.6 kind `runtime`; `executables` per OS; `packages` map | CONFORMS | `viwo/contracts/types.py:79,82,86-94`, `viwo/core/decode.py:38-47` (per-OS executables) | `packages` is informational (pins install) |
| 2.6 `/api/dependencies` combines all, `category` = owner | CONFORMS | `viwo/core/wiring/boot.py:44-65` | |
| 2.7 generic: always 0.4 | CONFORMS | `viwo/plugins/generic/__init__.py:19-22` | |
| 2.7 renpy markers; `source_roots` = `<game>/game` | CONFORMS | `viwo/plugins/renpy/__init__.py:38-47,58-60` | |
| 2.7 unity markers | CONFORMS | `viwo/plugins/unity/__init__.py:47-55,66-77` | |
| 2.7 unreal markers; options `aesKey` (secret), `engineVersion` | CONFORMS | `viwo/plugins/unreal/__init__.py:29-37,62-75` | options are `aes_key` (secret) and `find_key` (bool) |
| 2.7 godot markers; option `encryptionKey` secret | CONFORMS | `viwo/plugins/godot/__init__.py:25-33,70-80` | option is `encryption_key` |
| 2.7 godot `.ctex`/`.stex` → `.png` as a sanitizer rule | NOT IMPLEMENTED (deferred, documented) | doc 5 line 33 ("Phase 2 (1.x, not shipped in 1.1)"); `viwo/plugins/godot/__init__.py` has no `sanitizer_rules` | |
| 2.7 "tools column defers to 8.4" | CONFORMS | see 08 | |
| 2.8 custom plugins: discovery, `plugin.json`, `entry` form, opt-in, trust model | CONFORMS | `viwo/core/wiring/registry.py:162-266`, `tests/test_registry.py` `test_opt_in_override_and_errors`, `docs/plugins.md` | |
| 2.8 reserved ids (`generic renpy unity unreal godot mixed auto`) | CONFORMS | `viwo/core/wiring/registry.py:30,253-257` | revised form: built-in ids need `override`; `mixed/auto/core/none` reserved |
| 2.8 contract-version check at load | CONFORMS | `viwo/core/wiring/registry.py:62-63` (manifest major vs `CONTRACT_VERSION`), `:172-174` (`requires.viwo`) | the `plugin.json` `contract` key itself is informational |
| 2.8 conformance checks against an empty probe at load | CONFORMS | `viwo/core/wiring/registry.py:35-53,76-81,227-232` (`EmptyProbe`, `_accept`) | |
| 2.9 slug / contract / engine_type checks | CONFORMS | `viwo/core/wiring/registry.py:56-82`, `tests/test_conformance_kit.py` `test_validate_plugin_rejects_bad_manifests` | |
| 2.9 `detect` declared as a capability; `unarchive.*` slots imply the `unpack` capability | CONFORMS | `viwo/core/wiring/conformance.py:80` (`_capability_problems`: known set, `detect` required, `unarchive.*` slots need `unpack`), `viwo/core/wiring/conformance.py:93` (`capabilities_of` derives them when a manifest declares none); `GET /api/plugins` `capabilities` | built-ins without a declaration get `detect` plus what their slots imply |
| 2.9 option keys and dependency ids unique | CONFORMS | `viwo/core/wiring/registry.py:66-68,85-93` | |
| 2.9 slot and backend ids unique; owner is the plugin id; suffixes lowercase dotted | CONFORMS | `viwo/core/wiring/registry.py:304-314`, `tests/test_conformance_kit.py` `test_slots_and_backends_belong_to_their_plugin` | |
| 2.9 `detect()` never raises on fixtures, same result twice, ids match manifest | CONFORMS | `tests/test_conformance_kit.py` `test_detect_is_pure_on_empty_and_fixture_probes`, `tests/test_mixed.py` `test_pairs_and_singles` | |
| 2.9 sandbox check: no change outside `staging/<plugin>` after `export()` | CONFORMS | `tests/test_conformance_kit.py:112-131` | diffs the game folder, a sibling folder and `<root>/<plugin>`; the job's own work folder is not diffed |

Verdict: the plugin model is implemented as described, and the 2.9 kit the previous audit found missing now exists and runs on every plugin at load and in tests.
Open: 2.2 `export(ctx) -> ExportReport` on the plugin (intentional) · 2.2 `analysis_targets(probe)` (deferred) · 2.5 ownership table (zip/tar/7z/rar core; rpa renpy; unitypackage unity; (intentional) · 2.7 godot `.ctex`/`.stex` → `.png` as a sanitizer rule (deferred).

## 08 Pipeline backends and slots

| Clause | Status | Evidence | Note |
|---|---|---|---|
| Every tool is reached through a slot; no stage calls a tool directly | CONFORMS | `viwo/core/merger/ffmpeg.py:53` (`probe()` through the `media.probe` binding with failover), `viwo/core/merger/build.py` (`media.encode` binding checked, ffmpeg argv built by its backend module) | the last direct locate (ffprobe) is gone (1.2.1) |
| 8.1 SlotDefinition: slot_id, family, owner, matches, default_main, default_spare | CONFORMS | `viwo/contracts/slots.py:41-50` (`suffixes`/`magic`/`identify` = matches) | |
| 8.1 SlotDefinition `interface`, `policy` | NOT IMPLEMENTED (deferred, documented) | doc 8.2 prototype note; the family implies the interface (`viwo/contracts/slots.py:89-157`) | |
| 8.1 Backend: backend_id, owner, families, dependencies(), available() | CONFORMS | `viwo/contracts/slots.py:53-71` | `available()` returns `(ok, reason)` without `location`; `self_check` added for `viwo slots --check` |
| 8.1 SlotBinding: slot_id, main, spare, promoted, source default/ini/cli | CONFORMS | `viwo/contracts/slots.py:160-171` | `cli` source deferred with the CLI overrides (doc 9 note) |
| 8.2 policies failover / main_only / supplement | NOT IMPLEMENTED (deferred, documented) | doc 8.2 note; `viwo/core/pipeline/failover.py:11-35` (failover only) | |
| 8.2 outcome kinds collapsed to ok/unavailable/failed/needs_key | CONFORMS | `viwo/contracts/types.py:119-125` | |
| 8.2 retry table: unavailable/failed retry; needs_key only with a key-capable spare | DEVIATES (intentional, documented) | `viwo/contracts/types.py:139-142`, `tests/test_core_units.py:67-86`, `ARCHITECTURE.md:47-48` | the spare is never tried for needs_key even when `supports_keys=True` (`godot/pck.py:97`, `unreal/pak.py:88`) |
| 8.2 startup resolution: main stays; missing main → spare promoted with a warning; neither → unbound, stages skip | CONFORMS | `viwo/core/wiring/binder.py:55-70`, `viwo/core/pipeline/failover.py:18-20`, `tests/test_core_units.py` `test_four_availability_cases` | reasons flow into `rt.problems` (`boot.py:123-124`) |
| 8.2 every result records its backend; `by_backend` counts | CONFORMS | `viwo/contracts/pipeline.py:108,128,151`, `viwo/contracts/pipeline.py` (`PluginRun.to_legacy_dict`), `viwo/core/pipeline/unpack.py:92` | |
| 8.3 Unarchiver: extract, supports_keys; core loop unchanged | CONFORMS | `viwo/contracts/slots.py:89-96`, `viwo/core/pipeline/unpack.py:40-65` | `sniff(path, head)` replaced by slot identifiers (8.4) |
| 8.3 Exporter.export(ctx) | CONFORMS | `viwo/contracts/slots.py:99-104` | returns `Outcome` |
| 8.3 MediaProbe `probe(path) -> MediaInfo` | CONFORMS | `viwo/contracts/slots.py:123-130`, `viwo/core/decode.py:32,113-150` | facts travel as `Outcome.notes` (format, duration, width, height); no `has_audio`/`codec` |
| 8.3 MediaEncoder (`media.encode`, honours max_command_length) | CONFORMS | `viwo/backends/__init__.py:13`, `viwo/core/merger/ffmpeg.py:32-37`, `viwo/core/merger/build.py:158-164` | |
| 8.3 ImageCodec (`image`: decode, convert) | CONFORMS | `viwo/core/decode.py` (`decode.image`) | `decode.image` (DDS → PNG, ffmpeg); the `image.convert` slot (Pillow / ImageMagick) was removed in 1.5.2: no stage called it |
| 8.3 CodeAnalyzer (`analysis`) | NOT IMPLEMENTED (deferred, documented) | doc 16 M13+ | |
| 8.4 "Identify, then extract": head and tail, embedded chunks carved by core | CONFORMS | `viwo/contracts/slots.py:24-38`, `viwo/core/pipeline/identify.py:13-50`, `viwo/plugins/godot/__init__.py:40-49`, `viwo/plugins/unreal/__init__.py:39-47`, `tests/test_core_units.py` `test_suffix_magic_custom_and_carve` | |
| 8.4 unarchive.zip py-zipfile / sevenzip-cli; .zip (+ zip appended to exe) | CONFORMS | `viwo/backends/__init__.py:16-24` | `.nw` added; exe-appended zips found by the carver |
| 8.4 unarchive.tar, .7z (sevenzip-cli/py7zr), .rar (unrar-cli/sevenzip-cli) | CONFORMS | `viwo/backends/__init__.py:25-45` | |
| 8.4 unarchive.rpa rpa-safe / unrpa (restricted unpickler, subprocess) | CONFORMS | `viwo/plugins/renpy/__init__.py:23-25`, `viwo/plugins/renpy/rpa.py:36,80-82,106-107` | |
| 8.4 unarchive.unitypackage py-tarfile / sevenzip-cli | CONFORMS | `viwo/plugins/unity/__init__.py:35-42` | |
| 8.4 unarchive.unity-bundle (unitypy / uabea-cli), unarchive.unity-webgl | DEVIATES (intentional, documented) | `viwo/plugins/unity/__init__.py:43,46,88-92` (`CLAIMED` suffixes go to `export.unity`), contract README D7 | bundles are decoded by the exporter, not an unarchive slot |
| 8.4 unarchive.pck gdre-tools / godotpcktool | CONFORMS | `viwo/plugins/godot/__init__.py:40-49`, `viwo/plugins/godot/pck.py:95-101,145-146` | |
| 8.4 unarchive.pak repak / quickbms spare | CONFORMS | `viwo/plugins/unreal/__init__.py:40-47` (spare `quickbms-cli`), `viwo/core/wiring/distros.py:85` (distros name a spare only when its plugin is on), `viwo/core/wiring/binder.py:5` (a default spare whose plugin is off is simply absent); `tests/test_config.py::test_engine_distros_boot_without_spare_problems` | engine distros bind repak alone without a problem line; mixed distros bind both |
| 8.4 unarchive.iostore retoc / CUE4Parse wrapper | DEVIATES (intentional, documented) | `viwo/plugins/unreal/__init__.py:48` (`unarchive.utoc`: retoc-legacy / retoc-unpack), STATUS M7 | |
| 8.4 unarchive.casc datatool / casclib | DEVIATES (intentional, documented) | `viwo/plugins/overwatch/__init__.py:61,105,111` (`export.overwatch`), STATUS M8 | export slot instead of an unarchive slot; no casclib spare |
| 8.4 export.unity unitypy / assetstudiomod-cli (D7) | CONFORMS | `viwo/plugins/unity/__init__.py:43`, `viwo/plugins/unity/exporters.py:182-184,210-211`, contract README D7 | |
| 8.4 export.unity-project (assetripper), export.unreal (CUE4Parse/umodel) | NOT IMPLEMENTED (deferred, documented) | doc 8.4 "optional" / "deferred after the prototype"; doc 16 M13+ "Unreal export" | |
| 8.4 export.godot gdre-tools --recover / godotdec | DEVIATES (intentional, documented) | `viwo/plugins/godot/__init__.py:39,64-68,90`, `viwo/plugins/godot/pck.py:104-120` (`gdre-recover`, opt-in `recover` option); doc 8.4 row revised | `godotdec` (Godot 3 only) deferred, said in the doc row |
| 8.4 export.overwatch datatool | CONFORMS | `viwo/plugins/overwatch/__init__.py:61,105` | |
| 8.4 keys slots (user key / aesdumpster / keyring) | DEVIATES (intentional, documented) | contract README D18, `viwo/plugins/unreal/__init__.py:30-36` (`aes_key`, `find_key`) | keys are options plus a verified finder, not slots |
| 8.4 media.probe ffprobe / pillow | CONFORMS | `viwo/core/decode.py`, `distros/windows-unreal.ini` `[slots]` (bound in every distro) | the merger probes through it (8.5); `image.convert` removed in 1.5.2 (no caller) |
| 8.4 audio.decode vgmstream | CONFORMS | `viwo/core/decode.py:26-29` (`decode.audio`, spare `ffmpeg-decode`) | renamed |
| 8.4 analysis.* slots | NOT IMPLEMENTED (deferred, documented) | doc 16 M13+ | `analysis.python` exists as `decode.rpyc` (`viwo/plugins/renpy/decompile.py:21`) |
| 8.4 capture.gpu | CONFORMS | `viwo/core/capture/__init__.py:30` | |
| 8.4 capture.memory, capture.audio, runtime.<engine> | NOT IMPLEMENTED (deferred, documented) | STATUS M11 (pilot = RenderDoc only) | |
| 8.4 backend declarations: `license` (SPDX), GPL/AGPL → subprocess | CONFORMS | `viwo/contracts/slots.py:57-58`, `tests/test_l0_static.py` `test_gpl_backends_run_as_subprocesses`, `viwo/plugins/renpy/rpa.py:107`, `viwo/plugins/quickbms/__init__.py:46` | |
| 8.4 `network` and `parses_untrusted_in_process` declarations | CONFORMS | `viwo/contracts/slots.py:59-60`, `tests/test_l0_static.py` `test_every_backend_declares_network_and_untrusted_parsing`, `viwo/backends/archives.py:50,72,131`, `viwo/core/decode.py:137,156` | |
| 8.4 OS-layer-internal dialog fallbacks (zenity/kdialog, PowerShell) | NOT IMPLEMENTED (deferred, documented) | doc 1.4 prototype note; `viwo/os/linux.py:47-51`, `viwo/os/windows.py:75-79` (tkinter only) | |
| 8.5 UNPACK: `unarchive.*` by matches (longest suffix, then magic) | CONFORMS | `viwo/core/pipeline/identify.py:13-32`, `viwo/core/pipeline/unpack.py:52` | |
| 8.5 EXPORT: `export.<plugin_id>` | CONFORMS | `viwo/core/pipeline/runner.py:209-219`, `viwo/contracts/plugin.py:168-170` | |
| 8.5 VERIFY: plugin.verify + optional media.probe health | CONFORMS | `viwo/core/pipeline/runner.py:232-244`, `viwo/core/sanitizer.py:5` (health as a sanitizer rule) | the optional probe is not used in VERIFY |
| 8.5 SANITIZE by rule; REPORT core | CONFORMS | `viwo/core/sanitizer_rules.py:183-186`, `viwo/core/pipeline/runner.py:257-282` | |
| 8.5 merger build: MediaProbe + MediaEncoder (`media.probe`, `media.encode`) | CONFORMS | `viwo/core/merger/ffmpeg.py:53`, `viwo/core/merger/build.py:74` (`_probe_ctx`), `viwo/core/decode.py:131` (ffprobe reports `codec_type` per stream); `tests/test_merger.py::ProbeSlotTests` | the ini can swap the prober (`media.probe = pillow-probe` gives no duration: the merger falls back to the slide delay) |
| 8.6 `slot_definitions()` / `backends()` replace `archive_handlers()` | CONFORMS | `viwo/contracts/plugin.py:147-151` | |
| 8.6 a plugin may add a backend to a slot it does not own; ini binds it | CONFORMS | `viwo/core/wiring/binder.py:14-23` (family check only) | |
| 8.6 slot ids unique across plugins | CONFORMS | `viwo/core/wiring/registry.py:304-309` | |
| 8.6 default main/spare name a known backend serving the family | CONFORMS | `viwo/core/wiring/binder.py:30-35`, `viwo/core/wiring/distros.py:6-13`, `tests/test_config.py` `test_strict_rules` | a default spare owned by a disabled plugin is dropped silently only when no `[slots]` entry names it (see 8.4 pak spare) |
| 8.6 `available()` has no side effects | CONFORMS | `viwo/contracts/slots.py:66-71` (delegates to `locate`), `tests/test_conformance_kit.py` `test_locate_never_installs_or_writes` | |
| 8.6 spare with `supports_keys=false` never called for needs_key | CONFORMS | `viwo/contracts/types.py:139-142`, `tests/test_core_units.py` `test_failover_outcomes` | stronger than required (no spare at all for needs_key) |
| 8.6 matrix {main up, down} × {spare up, down}; promotion, failover, unbound | CONFORMS | `tests/test_core_units.py` `test_four_availability_cases`, `test_failover_outcomes` | |

Verdict: slots, binding, promotion, failover, the declarations (`license`, `network`, `parses_untrusted_in_process`) and the new `media.probe` / `image.convert` / `export.godot` slots follow doc 8; what remains is wiring the merger's probe through its slot and tidying the two new spares.
Open: 8.1 SlotDefinition `interface`, `policy` (deferred) · 8.2 policies failover / main_only / supplement (deferred) · 8.2 retry table: unavailable/failed retry; needs_key only with a key-cap (intentional) · 8.3 CodeAnalyzer (`analysis`) (deferred) · 8.4 unarchive.unity-bundle (unitypy / uabea-cli), unarchive.unity-webgl (intentional) · 8.4 unarchive.iostore retoc / CUE4Parse wrapper (intentional) · 8.4 unarchive.casc datatool / casclib (intentional) · 8.4 export.unity-project (assetripper), export.unreal (CUE4Parse/umodel) (deferred) · 8.4 export.godot gdre-tools --recover / godotdec (intentional) · 8.4 keys slots (user key / aesdumpster / keyring) (intentional) · 8.4 analysis.* slots (deferred) · 8.4 capture.memory, capture.audio, runtime.<engine> (deferred) · 8.4 OS-layer-internal dialog fallbacks (zenity/kdialog, PowerShell) (deferred).

## 09 Startup wiring from an ini file

| Clause | Status | Evidence | Note |
|---|---|---|---|
| configparser, `[startup]`, `[plugins]`, `[slots]`, `[tools]`, `[server]` | CONFORMS | `viwo/core/wiring/ini.py:12,118-119` | |
| 9.1 `startup.ini` + 12 shipped distros | CONFORMS | `distros/` (12 files), `viwo/core/wiring/distros.py:27-31`, `tests/test_config.py` `test_twelve_files_named_and_written_strictly`, `test_shipped_distros_match_the_generator` | |
| 9.1 precedence defaults < base < ini < cli | CONFORMS | `viwo/core/wiring/ini.py:122-138,171` (base first, later files override), `viwo/core/wiring/boot.py:103-105` (`--os` recorded as `cli`) | only `--os` exists as a cli layer |
| 9.1 cli flags `--profile`, `--plugin <id>=on/off`, `--slot <slot>=<main>[,<spare>]` | NOT IMPLEMENTED (deferred, documented) | `viwo/cli.py:42` (`--profile`), `viwo/core/wiring/boot.py:92` (`_apply_profile`: that distro's plugin set, source `cli`); `tests/test_config.py::test_suffix_clash_is_reported_and_profile_flag_selects_plugins` | `--os/--profile` implemented; `--plugin/--slot` deferred by the doc 9 prototype note |
| 9.1 only one level of `base =` | CONFORMS | `viwo/core/wiring/ini.py:15,122-138` (`MAX_LAYERS = 2`), `tests/test_config.py` `test_base_layering` | |
| 9.1 effective configuration with the source of every value, logged at boot and in `/api/distro` | CONFORMS | `viwo/core/wiring/ini.py:33,149-160`, `viwo/core/wiring/boot.py:73,105`, `viwo/api/routes.py:29-31`, `viwo/core/records.py:25-29` (also in run records) | `--verbose` prints the ini chain and bindings (`viwo/cli.py:86-90`), not the per-value sources; `sources` has no test |
| 9.2 encoding UTF-8 with BOM, `;`/`#` comments, booleans, case-insensitive keys | CONFORMS | `viwo/core/wiring/ini.py:119,133,171,76,85` | |
| 9.2 `[startup] contract` | CONFORMS | `viwo/core/wiring/ini.py:13,63-69` | no test exercises the mismatch |
| 9.2 `[startup] os`, `profile`, `features`, `auto_install`, `strict_preflight`, `base` | CONFORMS | `viwo/core/wiring/ini.py:13,70-76` | key is `os` where the doc prose says "OS layer" |
| 9.2 `auto_install` default off | DEVIATES (intentional, documented) | `viwo/core/wiring/ini.py:24` (default on), `startup.ini:10`, `README.md:93-94` | owner's rule: fully automated pinned, checksummed installs |
| 9.2 `[plugins]` ids, `generic` forced on, `custom_dirs`, `custom.<id>` | CONFORMS | `viwo/core/wiring/ini.py:80-85`, `viwo/core/wiring/registry.py:28,220-224,243` | |
| 9.2 `[slots] <slot> = <main>[, <spare>]`, `none` | CONFORMS | `viwo/core/wiring/ini.py:86-89` | |
| 9.2 `[slot_policy]` | NOT IMPLEMENTED (deferred, documented) | doc 8.2 note; `viwo/core/wiring/ini.py:103-104` reports it as an unknown section | |
| 9.2 `[tools]` keyed by dependency id, paths relative to the ini | CONFORMS | `viwo/core/wiring/ini.py:90-91`, `viwo/core/wiring/boot.py:99` | |
| 9.2 `[options.<plugin>]`, secrets refused | CONFORMS | `viwo/core/wiring/ini.py:94-102`, `tests/test_core_units.py:48` | |
| 9.2 `[hooks]` | NOT IMPLEMENTED (deferred, documented) | doc 9 prototype note; doc 16 M13+ ("open: `[hooks]`") | |
| 9.3 step 1 usage error → exit 2 | CONFORMS | `viwo/cli.py:33-47,127` (argparse) | |
| 9.3 step 2 syntax error → exit 2 with file:line | CONFORMS | `viwo/core/wiring/ini.py:178-179` (configparser message carries the line), `viwo/cli.py:27,155` | |
| 9.3 step 3 `[server]` defaults under `viwo-data/` | CONFORMS | `viwo/core/wiring/ini.py:38-54,107-115` | |
| 9.3 step 4 OS select, unsupported host → exit 3 | CONFORMS | `viwo/os/__init__.py:21-30` (`refused`), `viwo/cli.py:27` | |
| 9.3 steps 5, 7, 10, 12 hooks | NOT IMPLEMENTED (deferred, documented) | as `[hooks]` | |
| 9.3 step 6 register built-ins, discover/validate/register custom; bad plugin disabled and shown | CONFORMS | `viwo/core/wiring/registry.py:235-266`, `viwo/core/wiring/boot.py:106-111,127`, `viwo/api/routes.py:29-31` | shown under `/api/distro.problems`; `/api/plugins` (`routes.py:34-51`) lists only loaded plugins |
| 9.3 step 8 bind: defaults + `[slots]` + `[tools]`, auto-install, promote spares | CONFORMS | `viwo/core/wiring/boot.py:99,117-124`, `viwo/api/server.py:217-224` (install, then `App.reload()` rebinds), `viwo/core/preflight.py:87-98` | |
| 9.3 step 9 strict_preflight → exit 4 | DEVIATES (intentional, documented) | `viwo/api/server.py:231-234`, `viwo/core/preflight.py:101-109`, `startup.ini:11` | condition is "an enabled plugin's slot has no backend"; no dependency is marked required (`boot.py:56`) |
| 9.3 step 11 port in use → clear error | CONFORMS | `viwo/api/server.py:236-244` (exit 2) | |
| 9.3 exit codes 0/2/3/4 | CONFORMS | `viwo/cli.py:27,155`, `viwo/api/server.py:234,244`, `viwo/cli_args.py:28` | plus 1 (failed) and 130 (Ctrl+C) |
| 9.4 unknown sections/keys → warning, ignored | CONFORMS | `viwo/core/wiring/ini.py:103-104,141-146` (`[startup]` and `[server]` keys checked) | |
| 9.4 unknown plugin/slot/backend id → error for that entry, default used instead | CONFORMS | `viwo/core/wiring/binder.py:26-44,79`, `viwo/core/wiring/registry.py:262-265`, live boot of `distros/windows-unreal.ini` | no unit test for the fallback; the rule also fires on the generated `unarchive.upak` spare (8.4) |
| 9.4 wrong-family backend → same | CONFORMS | `viwo/core/wiring/binder.py:21-22,38-42` | |
| 9.4 `contract` major mismatch → exit 2 | CONFORMS | `viwo/core/wiring/ini.py:63-69` (`invalid_request`) → `viwo/cli.py:27` (2) | untested |
| 9.4 secret-looking option keys refused with a warning | CONFORMS | `viwo/core/wiring/ini.py:16,99-101` | `token` added to the word list |
| 9.4 paths relative to the ini folder | CONFORMS | `viwo/core/wiring/ini.py:83,91,114` | |
| 9.5 lifecycle hooks | NOT IMPLEMENTED (deferred, documented) | as `[hooks]` | |
| 9.6 `GET /api/distro` returns effective ini, bindings, problems | CONFORMS | `viwo/api/routes.py:29-31`, `viwo/core/wiring/boot.py:67-77` | |
| 9.6 UI editing later; takes effect after restart; nothing re-wired while running | CONFORMS | doc 9.6 revised (apply by reloading, no restart); `viwo/api/app.py:37` (`reload`), `viwo/api/handlers_settings.py` | the owner's apply-by-reload decision is now in the contract |

Verdict: the ini model is complete for the prototype scope: one base level, the `contract` key with its major check, per-value sources, default fallback on bad ids and the four exit codes all match doc 9; hooks and slot policies stay documented deferrals.
Open: 9.1 cli flags `--profile`, `--plugin <id>=on/off`, `--slot <slot>=<main> (deferred) · 9.2 `auto_install` default off (intentional) · 9.2 `[slot_policy]` (deferred) · 9.2 `[hooks]` (deferred) · 9.3 steps 5, 7, 10, 12 hooks (deferred) · 9.3 step 9 strict_preflight → exit 4 (intentional) · 9.5 lifecycle hooks (deferred).

## 10 Third-party tools (sparse submodules proposal)

| Clause | Status | Evidence | Note |
|---|---|---|---|
| Direction: sparse submodules at M11; until then a tool lock file (name, version, URL, checksum) | CONFORMS | `viwo/data/tools.json` (version, license, per-OS url/size/sha256/kind/find), `viwo/core/thirdparty.py:1-8,37-38`, contract README goal 6 History, doc 16 M12 | the lock file is the shipped and recorded design |
| 10.1 pinned versions, provenance, licenses next to the tool, fewer install surprises, locator knows the place | CONFORMS | `tools.json` `license` per entry, `viwo/core/wiring/boot.py:99` (`found_tools` first), `viwo/core/records.py:19` (`installed_version` in run records), `THIRD_PARTY_NOTICES.md` | |
| 10.2 `third_party/vendor.ini` + submodule folders + `_build/` | DEVIATES (intentional, documented) | contract README goal 6 History; doc 16 M12 ("done as the pinned installer ... replaced submodules") | `third_party/<id>/` folders hold release binaries |
| 10.2 sync script for sparse checkout | DEVIATES (intentional, documented) | same; `viwo install --all` (`viwo/cli_args.py:84-85`) | |
| 10.2 locator order: config → env → vendored → PATH → known dirs; vendored first ❓ | CONFORMS | `viwo/core/wiring/boot.py:99` (`{**found_tools, **config.tools}`), `viwo/os/_shared.py:138-145`, `README.md:107` | decided: ini over `third_party/` over PATH |
| 10.3 pure-Python tools from source on sys.path | CONFORMS | `viwo/core/thirdparty.py:47-55,273-290` (`third_party/python` on `sys.path`, pinned pip `--target`) | variant: pinned wheels, not submodule source |
| 10.3 UnityPy native deps need wheels | CONFORMS | `viwo/core/thirdparty.py:273-290`, `tests/test_thirdparty.py` `test_manifest_pins_match_pyproject` | |
| 10.3 compiled tools: release binaries | CONFORMS | `tools.json` (repak, retoc, vgmstream, gdre, godotpcktool, assetstudiomod, sevenzip, ffmpeg, ffprobe, dotnet, unrar, quickbms, datatool, renderdoccmd, rdpython, unrpyc), `viwo/core/thirdparty.py:225-262` | option (b) in practice |
| 10.3 unrar / 7-Zip do not fit git | CONFORMS | `viwo/core/thirdparty.py:209-215` (MSI administrative unpack), `tests/test_thirdparty.py:214` (kinds `sfx`, `msi`) | |
| 10.4.1 source vs runnable → (b) binaries verified by checksum | CONFORMS | `viwo/core/thirdparty.py:140-153,245-249` (HTTPS only, sha256 + size, 3 attempts), contract README D8 | |
| 10.4.2 licenses before vendoring | CONFORMS | `LICENSE` (MIT), contract README D9, `tools.json` license per tool, `tests/test_l0_static.py` `test_gpl_backends_run_as_subprocesses` | |
| 10.4.3 repository size | CONFORMS | nothing vendored in git (`viwo/core/thirdparty.py:8`, contract README layers: `third_party/` gitignored) | moot |
| 10.4.4 bumping a pin reruns the matrix | CONFORMS | `tests/test_thirdparty.py` `test_manifest_is_complete_and_https`, doc 17 real-tools job (`17-testing-model.md:80`) | by policy (CI only on major tags) |
| 10.4.5 vendor list vs `[tools]` split | CONFORMS | `tools.json` (what is pinned) vs `viwo/core/wiring/ini.py:90-91` (what is forced) | decided |
| 10.5 `DependencySpec.vendored`; `[tools] x = vendored:<name>`; `auto_install` as fallback | DEVIATES (intentional, documented) | `viwo/core/wiring/boot.py:99` (every installed pin becomes a config override), `viwo/core/preflight.py:92-94`, contract README goal 6 History | the `vendored:` syntax is unnecessary under the lock-file design |
| Owner's 1.0 rules: every tool under `third_party/`, pinned, checksummed, HTTPS, no manual step | CONFORMS | `viwo/core/thirdparty.py:142-143,248`, `tests/test_thirdparty.py` `test_http_download_is_refused`, `test_manifest_is_complete_and_https`, `README.md:93-94,247-248` | `installable()` refuses Python pins in the frozen build (`thirdparty.py:133-137`) |

Verdict: doc 10 was a proposal; the owner chose option (b) with the lock file, the README History line records it, and the implementation follows that choice completely.
Open: 10.2 `third_party/vendor.ini` + submodule folders + `_build/` (intentional) · 10.2 sync script for sparse checkout (intentional) · 10.5 `DependencySpec.vendored`; `[tools] x = vendored:<name>`; `auto_ins (intentional).

## Counts per status

| Doc | CONFORMS | DEVIATES (defect) | DEVIATES (intentional, documented) | NOT IMPLEMENTED (deferred, documented) | NOT IMPLEMENTED (undocumented gap) |
|---|---|---|---|---|---|
| 00 Glossary and semantic model | 16 | 0 | 2 | 1 | 0 |
| 01 OS contract | 27 | 0 | 1 | 4 | 0 |
| 02 Engine plugin contract | 44 | 0 | 2 | 2 | 0 |
| 08 Pipeline backends and slots | 38 | 0 | 6 | 7 | 0 |
| 09 Startup wiring from an ini file | 28 | 0 | 2 | 5 | 0 |
| 10 Third-party tools (sparse submodules proposal) | 13 | 0 | 3 | 0 | 0 |
| Total | 166 | 0 | 16 | 19 | 0 |


---

# Conformance re-audit B: docs 03, 04, 05, 06, 07 against the implementation (v1.2.0, branch `makeover`, contract 1.1, 2026-11-03)

Read-only. Status values: CONFORMS · DEVIATES (defect) · DEVIATES (intentional, documented) ·
NOT IMPLEMENTED (deferred, documented) · NOT IMPLEMENTED (undocumented gap).
Evidence is `file:line` at the current tree (v1.2.0) or a test method that exists now.

## Doc 03: pipeline, routing and mixed mode

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 3.1 history (D12): no INVENTORY stage, sanitizer never a stage of an extraction; table is the implemented `Stage` order | CONFORMS | `viwo/contracts/pipeline.py:18-27` (PREPARE, PROBE, DETECT, UNPACK, CARVE, EXPORT, COLLECT, VERIFY, REPORT; no INVENTORY, no SANITIZE, no ANALYZE) | Doc revised to the implemented design. |
| 3.1 history (D12): `plugins[].inventoryCount` reports what each export saw | CONFORMS | `viwo/core/pipeline/checks.py:22` (`verify_one`), `viwo/contracts/pipeline.py` (`PluginRun.to_legacy_dict`) (`inventoryCount`) | 0 for plugins without an inventory (no claim); no built-in keeps one yet |
| 3.1 PREPARE: ownership rule, never clear without marker, `staging/<plugin_id>/` + `scratch/` | CONFORMS | `viwo/core/pipeline/runner.py:99-117` (precheck, `resolve_target`, temp work dir), `viwo/core/workspace.py:92-120`, staging per owner `runner.py:51-66`; `tests/test_core_units.py::WorkspaceTests.test_ownership_and_policies` | Staging/scratch live under a temp work dir (`runner.py:112`), moved into the workspace by COLLECT. |
| 3.1 PROBE: build one GameProbe | CONFORMS | `viwo/core/pipeline/runner.py:122` (`FolderProbe(run.game)`); a second `limit=1` probe for source roots at `viwo/core/pipeline/sources.py:54` | No observable deviation. |
| 3.1 DETECT: `detect()` on every enabled plugin, then `select_plugins()` | CONFORMS | `viwo/core/pipeline/runner.py:73-82,120-126` | Detection exceptions become 0.0 results (`runner.py:78-81`). |
| 3.1 UNPACK: identify (head + tail, carving embedded containers), recursive unpack, main then spare | CONFORMS | `viwo/core/pipeline/identify.py:13-32` (custom identifier with head and tail bytes, longest suffix, then magic), `:35-45` (carve), `viwo/core/pipeline/unpack.py:17,46-64` (queue, depth cap 10), `viwo/core/pipeline/failover.py:23-35`; `tests/test_core_units.py::IdentifyTests.test_suffix_magic_custom_and_carve`, `tests/test_pipeline.py::ReplayAndUnpackTests.test_unpack_one_archive` | |
| 3.1 UNPACK: after an outer wrapper (`.asar`, `.nw`) is unpacked, detection runs once more and the strongest engine (≥ `mixed_threshold`, not already selected) exports from it, one pass, never nested | CONFORMS | `viwo/core/pipeline/export.py:27-51` (`WRAPPERS`, nested origins skipped by `"!" in origin` at `:37`, `taken` set, threshold at `:45`, `_export(run, best.plugin_id, dest)` at `:50`), called from `viwo/core/pipeline/runner.py:139` | No test exercises the re-detection path (`grep -rn "Re-detected\|rewrap" tests` is empty). |
| 3.1 CARVE: signature carver over unknown blobs (D21), archives found are unpacked | CONFORMS | `viwo/core/pipeline/runner.py:140,191-206` (`carve_all`, nested `unpack_all` into `unpack-carved`), `viwo/contracts/pipeline.py:51-56` (`CarveMode`) | |
| 3.1 EXPORT: `export()` for each selected plugin into its own staging folder | CONFORMS | `viwo/core/pipeline/runner.py:138,209-229`, staging `work/staging/<owner>` at `runner.py:57` | |
| 3.1 COLLECT: copy from game roots, move from staging, `<ext>/` layout, `selected_exts` filter, v1 collision naming, dedupe size + hash, provenance map, DECODE inside COLLECT | CONFORMS | `viwo/core/pipeline/collect.py:62-71` (`_place`: size + sha256), `:99-106` (selected exts), `:119-135` (`copy2` when `move=False`, provenance rows), `viwo/core/pipeline/sources.py:14-32,53-70` (game roots `move=False`), `viwo/core/pipeline/runner.py:169-188` (`_decode` inside `_collect`); `tests/test_pipeline.py::PipelineTests.test_selected_extensions_and_cancel`, `tests/test_game_integrity.py::GameIntegrityTests.test_every_plugin_leaves_the_game_untouched` | |
| 3.1 VERIFY: `logic_check_summary` warnings, then plugin `verify()` | CONFORMS | `viwo/core/pipeline/checks.py:6-14`, `viwo/core/pipeline/runner.py:145,149-150,232-244` | Plus a game-folder snapshot diff warning (`runner.py:132,146-148`, `viwo/core/pipeline/guard.py:27-41`), beyond the contract. |
| 3.1 REPORT: manifests to `.extraction_metadata/`, result built | CONFORMS | `viwo/core/pipeline/runner.py:257-285` (`provenance.jsonl`, `runs/<job_id>.json`, atomic writes) | |
| 3.1 ANALYZE never part of an extraction | CONFORMS | no `Stage.ANALYZE` (`viwo/contracts/pipeline.py:18-27`); `grep -rln analysis viwo` is empty | |
| 3.1 every stage sends events with `stage` set, cancel checked between files, v1 line format kept | CONFORMS | `viwo/core/pipeline/runner.py:44-49`, `viwo/core/pipeline/collect.py:88-96`, `viwo/contracts/types.py:20-24` (`legacy_line`); `tests/test_pipeline.py::PipelineTests.test_selected_extensions_and_cancel` | |
| 3.2 request fields (`game_path`, `selected_exts`, `mode`, `plugins`, `mixed_policy`, `mixed_threshold`, `plugin_options`, `on_existing`, `carve`) | CONFORMS | `viwo/contracts/pipeline.py:59-70` | Additive `workspace` field (`:62`). |
| 3.2 v1 payload mapping (`extractionType` missing/""/auto → auto; id → single; mixed → `plugins` + `mixedPolicy` default selected) | CONFORMS | `viwo/contracts/pipeline.py:72-100` | |
| 3.3 run order: confidence desc, priority desc, id; independent of registration order | CONFORMS | `viwo/core/pipeline/select.py:23-26`; `tests/test_core_units.py::SelectionTests.test_every_combination` (`:109` reversed input gives the same order) | |
| 3.3 auto / mixed selected / detected / all; never empty; generic fallback; Unity 0.92 beats Ren'Py 0.78 | CONFORMS | `viwo/core/pipeline/select.py:35-50`; `tests/test_core_units.py::SelectionTests.test_auto_and_fallback` | |
| 3.3 single: "the requested id, if it's enabled" (silent fall-through to step 3) | CONFORMS | doc 3.3 revised (unknown or disabled id refused with `invalid_request` since 1.0.1); `viwo/core/pipeline/select.py:28-34` |  |
| 3.4 Unpack: slots of all chosen plugins combined; same suffix claimed by two plugins → the ini decides, else a boot configuration problem (❓ magic tie-break open) | CONFORMS | `viwo/core/wiring/conformance.py:119` (`suffix_clashes`: boot problem naming the winner), `viwo/core/wiring/registry.py` (`collect` appends it); doc 3.4 revised (ini decides by switching a plugin off; magic never breaks ties); `tests/test_config.py::test_suffix_clash_is_reported_and_profile_flag_selects_plugins` | no built-in pair clashes today |
| 3.4 Export: each plugin into its own `staging/<id>/` | CONFORMS | `viwo/core/pipeline/runner.py:57,214-215` | |
| 3.4 Collect once from all roots and staging folders; overlapping source roots deduped; duplicates by content (size + hash → skip, else `name__N.ext`) | CONFORMS | `viwo/core/pipeline/sources.py:55-59` (resolved roots, nested roots dropped by `parents`), `viwo/core/pipeline/collect.py:62-71` | Overlap uses `Path.resolve()` + `parents`, not `os.fs.path_key`; same effect. Doc 3.4 now says size + hash (the old mtime sentence is gone). |
| 3.4 Failure isolation: export/verify failure in `plugins[i].error` and repeated in `warnings`; `verifyPassed` false on verify warnings; others still run; success if COLLECT completes | CONFORMS | `viwo/core/pipeline/runner.py:220-229` (`error` and `warnings` set together), `:232-244` (`verify_passed=not found`, verify exception lands in `error`), `:151-152` (`success=True` after COLLECT); `viwo/contracts/pipeline.py` (`PluginRun.to_legacy_dict`) | No test asserts `plugins[].error` or `verifyPassed` (`grep -rn "verifyPassed\|exportedByKind" tests` is empty). |
| 3.4 Result: `extractorType: "mixed"`, `detection` from the first plugin in run order, one `plugins[]` entry each, no plugin-specific top-level keys | CONFORMS | `viwo/contracts/pipeline.py:137-161`; `tests/test_mixed.py::MixedPairwiseTests.test_pairs_and_singles` (`:78-79`) | |
| 3.5 v1 keys kept | CONFORMS | `viwo/contracts/pipeline.py:139-149,167-170` (`LEGACY_RESULT_KEYS`); `tests/test_pipeline.py:46` | |
| 3.5 removed (F11): v1 Unity extras | CONFORMS | not produced anywhere; `viwo/plugins/unity/__init__.py:94-97` only warns when nothing was collected | |
| 3.5 new keys `contractVersion mode manifestsPath workspace runRecord byBackend carvedFiles` and `plugins[] { id detection exported exportedByKind exportedByTool backend inventoryCount verifyPassed warnings error }` present | CONFORMS | `viwo/contracts/pipeline.py:150-160`, `viwo/contracts/pipeline.py` (`PluginRun.to_legacy_dict`), `viwo/core/pipeline/export.py:17-24` (`exportedByKind`) | Additive keys `movedFiles`, `inventoryItems`, `collectedFromInventory` (doc 0.4) are not listed in 3.5. |
| 3.5 `contractVersion` value is the contract version (1.1) | CONFORMS | `viwo/contracts/pipeline.py:13`; `tests/test_l0_static.py::ContractVersionTests` keeps the mirror equal to `viwo.CONTRACT_VERSION` |  |
| 3.6 selection: exhaustive over every non-empty subset × 3 policies × synthetic detections | CONFORMS | `tests/test_core_units.py::SelectionTests.test_every_combination` (`:95-111`: 31 subsets of 5 ids × 3 policies) | 5 synthetic ids rather than the enabled plugin set (63 subsets); the function is id-agnostic. |
| 3.6 selection: property tests with random confidences | CONFORMS | `tests/test_core_units.py::test_random_confidences_keep_the_invariants` (300 random confidence sets: auto picks the strongest non-generic plugin, DETECTED is the set above the threshold, order independence) |  |
| 3.6 pipeline: real runs for every pair of plugins plus each single, on the mixed fixture and on each plugin's own fixture | CONFORMS | `tests/test_mixed.py::MixedPairwiseTests.test_pairs_and_singles` (`:63`: 13 singles + 78 pairs on `make_mixed_game`) | Each plugin's own fixture is covered by its own test module. |
| 3.6 OS layers: every selection and pipeline test runs on the Linux and Windows CI runners | CONFORMS | `.github/workflows/ci.yml:21-23` (`ubuntu-latest`, `windows-latest`), `:35-41` (full `unittest discover`) | CI runs only on major release tags or by hand (CLAUDE.md policy). |
| 3.6 OS layers: plus a fake-OS run of the fast tests on each runner | DEVIATES (intentional, documented) | doc 3.6 revised: the OS layer has its own conformance tests (`tests/test_os_layer.py`); tools are faked, the OS layer never is | the fake-OS run of draft 3 was dropped, now said in the doc |
| 3.6 invariants 1-6 (selection non-empty, no duplicates, inside the subset; order independence; no slot/backend clash; writes only under staging and the workspace, game hashes unchanged; v1 keys and one `plugins[]` entry per plugin; re-run identical) | CONFORMS | `tests/test_core_units.py:103-109` (1, 2), `tests/test_registry.py::DropinTests.test_clash_with_a_builtin_needs_override` (3), `tests/test_conformance_kit.py::SandboxTests.test_export_writes_only_inside_staging_and_scratch` and `tests/test_mixed.py:81` (4), `tests/test_pipeline.py:46` and `tests/test_mixed.py:78` (5), `tests/test_mixed.py:82-92` (6) | Invariant 6 is checked for the generic single run only. |
| 3.6 `sample-custom` plugin through the custom-plugin loader | CONFORMS | `tests/test_registry.py:22-29` (`copy_hello` from `examples/plugins/hello/`), `tests/test_registry.py::DropinTests.test_end_to_end_extraction_through_a_dropin` | |

Verdict: the stage runner, wrapper re-detection, selection, mixed mode, COLLECT, failure isolation and the 3.5 key set now conform; the doc was revised to the implemented design. Open: `inventoryCount` is emitted but never filled, the result's `contractVersion` still says 1.0, the 3.3 "single" sentence and the 3.4 suffix-clash sentence do not describe the code, and the two 3.6 test promises (property test, fake-OS run) do not exist.
Open: 3.6 OS layers: plus a fake-OS run of the fast tests on each runner (intentional).

## Doc 04: HTTP API, workspace layout and configuration

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 4.1 frozen GET routes kept (`/api/status`, `/api/logs`, `/api/dependencies`, `/api/assets-window`, `/api/assets-window-preview`, `/api/browse-folder`, `/api/media-merger/state`, `/preview/<path>`, static) | CONFORMS | `viwo/api/handlers.py:257-266`, `viwo/api/server.py:112-116,145-150,179-186` | Additive `GET /api/workspace` (`handlers.py:259`). |
| 4.1 dropped v1 routes (`/api/state`, `/api/session`, `/api/resume`, `/api/scan`, `/api/extensions`, `/api/detected-extensions`, `/api/assets-preview`, `/api/open-log-dir`, `/api/logs/load`) | DEVIATES (intentional, documented) | doc 04 header `:3-8` ("normative: they do not come back"); none in `viwo/api/handlers.py:257-287` | |
| 4.1 frozen POST routes kept (extract, keep-selected, trash, restore, delete, clear-trash, sort-*, logs/clear, save-remaining-assets, open-folder, media-merger/*) | CONFORMS | `viwo/api/handlers.py:269-287` | `/api/open-folder` is token-checked like every POST (`server.py:122-123`) rather than origin-checked: stronger. |
| 4.1 error conventions: expected failures `{"success": false, "error"}` HTTP 200; uncaught → 500 `{"error"}`; invalid JSON → 400; unknown POST → 404 | CONFORMS | `viwo/api/server.py:96-101,133-137`; `tests/test_server.py::ServerTests.test_game_folder_and_unknown_routes` | Expected failures also carry `code`/`hint` (`handlers.py:17-21`). |
| 4.1 `GET /api/distro`: effective configuration, OS layer, contract version, features | CONFORMS | `viwo/api/routes.py:29-31,118`; `tests/test_api_routes.py::RouteTests.test_distro_plugins_detect` | |
| 4.1 `GET /api/plugins`: manifest, options schema, capabilities, load errors, dependency status | CONFORMS | `viwo/api/routes.py:38` (`_plugin_entry`: description, capabilities, options, slots, per-dependency availability, load error; disabled plugins listed with `loaded: false`); `tests/test_api_routes.py::test_distro_plugins_detect` |  |
| 4.1 `POST /api/detect`: `detections`, `auto`, `modes.auto`, `modes.single` candidates, `modes.mixed.{detected,all,selected}` | CONFORMS | `viwo/api/routes.py:54-82`; `tests/test_api_routes.py::RouteTests.test_distro_plugins_detect` | Doc revised to the per-mode answer; implemented in 1.2. |
| 4.1 `/api/analysis/*` | NOT IMPLEMENTED (deferred, documented) | doc 04 `:44` "not served in 1.1"; doc 06 `:3-5` | |
| 4.1 `POST /api/jobs {kind, params}` generic submit onto the kind's own handler | CONFORMS | `viwo/api/handlers.py:291` (`JOBS_POST` merged into the POST table), `viwo/api/handlers_jobs.py:18-42`; `tests/test_api_routes.py::test_generic_job_submit_runs_the_kind_handler` |  |
| 4.1 `GET /api/jobs`, `GET /api/jobs/<id>`, `GET /api/jobs/<id>/events?from=N`, `POST /api/jobs/<id>/cancel` (the only cancellation route) | CONFORMS | `viwo/api/routes.py:85-104,116-138`; `tests/test_api_routes.py::RouteTests.test_jobs_events_and_cancel`, `tests/test_server.py::ServerTests.test_extract_curate_and_jobs`; no other cancel route (`grep -rn cancel viwo/api/handlers_*.py` shows none) | |
| 4.1 optional `/api/extract` fields `extractionType`, `plugins`, `mixedPolicy`, `pluginOptions`, `onExisting`, `carve` | CONFORMS | `viwo/contracts/pipeline.py:75-81`; sent by the UI `viwo/web/js/views/extract.js:226-229` | |
| 4.1 curated error convention: legacy routes HTTP 200 + `code`; envelope routes map the code (`busy` → 409) | CONFORMS | `viwo/api/routes.py:19-26,107-113`, `viwo/api/handlers.py:17-21`, `viwo/api/app.py:116-117`; `tests/test_curation.py::LockTests.test_curation_is_busy_during_a_job` | |
| 4.1 security 1: per-start token injected into `index.html`, `X-VIWO-Token` on every `/api/*`, preflight refused | CONFORMS | `viwo/api/server.py:25,58-60,71-75,108-110,122-123,211`; no CORS headers anywhere so a preflight fails; `tests/test_server.py::ServerTests.test_security_model` | |
| 4.1 security 2: JSON only, 415 otherwise | CONFORMS | `viwo/api/server.py:124-126`; same test | Body cap 16 MiB → 413 (`server.py:29,131-132`), additive. |
| 4.1 security 3: Host header check | CONFORMS | `viwo/api/server.py:53-56,106-107,120-121`; same test | |
| 4.1 security 4: path containment for static and `/preview/` relative to the active workspace | CONFORMS | `viwo/api/server.py:179-186` (static, `WEB_ROOT` parents), `:145-150` → `viwo/core/curation/sorting.py:54-59` (`resolve`, reserved refused), `viwo/api/plugin_assets.py:26-42`; `test_security_model` traversal cases | |
| 4.1 security 5: the UI `api()` helper sends the token | CONFORMS | `viwo/web/js/api.js:2,17` | |
| 4.1 mapping: `/api/extract` submits an `extract` job and waits | CONFORMS | `viwo/api/app.py:82-87` (`background=False`) | |
| 4.1 mapping: merger build as a `merge` job and waits | CONFORMS | `viwo/api/handlers.py:229-233`, `viwo/api/app.py:119-139` | |
| 4.1 mapping: curation routes synchronous under the workspace lock, 409 `busy` during a job | CONFORMS | `viwo/api/app.py:109-117`, `viwo/core/workspace.py:191-206`; `tests/test_curation.py::LockTests.test_curation_is_busy_during_a_job` | Legacy-shaped routes answer 200 + `code: "busy"` per the curated convention above. |
| 4.1 mapping: `/api/logs` ring buffer; `/api/logs/clear` clears the view only | CONFORMS | `viwo/api/app.py:27,43-60`, `viwo/api/handlers.py:265,283` | |
| 4.1 mapping: read-only core queries and OS-layer shell routes | CONFORMS | `viwo/api/handlers.py:31-80,169-174,236-254` | |
| 4.2 `/api/dependencies` item: five v1 keys + `requirement`, `location`, `hint`; `category` = owner id | CONFORMS | `viwo/core/wiring/boot.py:44-65` | Additive `kind`, `installable`. |
| 4.3 layout: marker, `<ext>/`, `noext/`, `.trash/{groups,items,merger}`, `.extraction_metadata/` + `runs/`, `.sanitizer/` (plans, cache, journal), `.analysis/` | CONFORMS | `viwo/contracts/workspace.py:8-16`, `viwo/core/curation/trash.py:1-6,20`, `viwo/core/sanitizer.py:26,98,177`, `viwo/core/pipeline/runner.py:258-262` | `.analysis/` and `.sanitizer/cache/` are not created: deferred by doc 06 and doc 05 phase 2. |
| 4.3 marker content: JSON `app, id, created_by, created, contract`; older empty or `{"app": "viwo"}` markers still count | CONFORMS | `viwo/core/workspace.py:41-63` (`marker_data`, `claim` keeps id/created_by/created across re-claims), `viwo/contracts/workspace.py:32-33` (`has_marker` by presence) | No test reads the marker fields back. |
| 4.3 ownership: clear/replace only inside a marked folder; arbitrary non-empty folder refused; default workspace claimed without the check | CONFORMS | `viwo/core/workspace.py:92-120` (`:98-99` `is_default`), `:83-89` (`_replace_groups` keeps dot folders); `tests/test_core_units.py::WorkspaceTests.test_ownership_and_policies` | |
| 4.3 re-extraction policy new/replace/cancel; replace keeps `runs/`, `.sanitizer/journal/`, `.trash/`; HTTP `needsDecision` + `options`; CLI exit 2 without `--on-existing` | CONFORMS | `viwo/core/workspace.py:76-89,105-120`, `viwo/api/app.py:71-81,88-97`, `viwo/cli.py:27`; `tests/test_pipeline.py::PipelineTests.test_rerun_needs_decision_and_replace_is_deterministic`, `tests/test_pipeline.py:94` | |
| 4.3 three trash layouts explicit; v1 trees migrated on first open | CONFORMS | `viwo/core/curation/trash.py:28-50`, `viwo/api/app.py:113-114` (`migrate` under the lock); `tests/test_curation.py::GroupTrashTests.test_migrate_and_clear` | |
| 4.3 top-level dot folders reserved everywhere (list, count, sort, merge, keep-selected) | CONFORMS | `viwo/contracts/workspace.py:19-21`; `viwo/core/curation/trash.py:61`, `viwo/core/curation/sorting.py:59,70`, `viwo/core/merger/media.py:93`, `viwo/api/handlers.py:125`, `viwo/core/sanitizer.py:49` | |
| 4.3 collision naming `name__N.ext`, undo `name__undoN.ext`, group trash `<ext>_N`, restored `<ext>__N` | CONFORMS | `viwo/contracts/workspace.py:15,36-46`, `viwo/core/curation/sorting.py:143`, `viwo/core/curation/trash.py:89,125`, `viwo/core/pipeline/collect.py:69` | |
| 4.3 COLLECT dedupe: same size and same content hash → skip | CONFORMS | `viwo/core/pipeline/collect.py:62-71` | |
| 4.3 active workspace starts as `[server] workspace`, follows `POST /api/workspace` and the last extraction | CONFORMS | `viwo/api/app.py:25,62-66,99`, `viwo/api/handlers.py:51-58,271` | Sort history is cleared on a switch (`app.py:64-65`), not in the doc. |
| 4.4 `ProgressEvent { message, level, source, stage }`; counts travel in the message; `progress.js` parses both forms | CONFORMS | `viwo/contracts/types.py:11-18`, `viwo/web/js/progress.js:13-16` (`FRAC`, `COUNT`) | Doc revised (no `current`/`total`). |
| 4.4 rendered as `[SOURCE:STAGE] message` | CONFORMS | `viwo/contracts/types.py:20-24` | |
| 4.4 lines go to the session log and the daily `viwo-YYYY-MM-DD.log` under `[server] logs` | CONFORMS | `viwo/api/app.py:43-52` | |
| 4.4 `secret` option values masked before anything is sent | CONFORMS | `viwo/core/pipeline/runner.py:29,247-254`, `viwo/contracts/plugin.py:115-127` (`tool_output(mask=)`), `viwo/plugins/unreal/pak.py:105-111`; `tests/test_pipeline.py:144-148` | |
| 4.5 one ini: `[server]` host/port/workspace/merged/logs/temp relative to the ini; wiring sections | CONFORMS | `viwo/core/wiring/ini.py:39-47` (`ServerConfig`), `viwo/api/app.py:23,29-35` | |
| 4.5 secrets never in the ini or on disk; run records store `<secret>` | CONFORMS | `viwo/core/wiring/ini.py:16,99-100`, `viwo/core/wiring/settings.py:65-66`, `viwo/core/pipeline/runner.py:247-254`; `tests/test_pipeline.py:147` | |
| 4.6 one global session (`assetPath`, sorting history, logs); log append a single locked operation; one local user | CONFORMS | `viwo/api/app.py:25-28,43-52,62-66` (`self.workspace`, `self.history`, `_lock`) | The v1 `SESSIONS` store name is history; one `App` object plays that role. |

Verdict: every security lock, the route set with the documented drops, the per-mode `/api/detect`, the jobs read/cancel routes, the workspace layout, marker fields, ownership, re-extraction policy, trash layouts and logging conform and are tested. Two defects: `POST /api/jobs` was written but never wired into the route tables (404 today), and `/api/plugins` lacks the load-error and dependency-status fields the row promises.
Open: 4.1 dropped v1 routes (`/api/state`, `/api/session`, `/api/resume`, `/ap (intentional) · 4.1 `/api/analysis/*` (deferred).

## Doc 05: asset sanitizer

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 5.1 phase 1 scope: zero-byte, extension from magic, exact duplicates by hash, junk, decode health (report only) | CONFORMS | `viwo/core/sanitizer_rules.py:99-175` (`ZeroByte`, `Junk`, `Identity` → `core.extension`/`core.health` action `none`, `Duplicates`), `viwo/core/sanitizer.py:27-34`; `tests/test_sanitizer.py::SanitizerTests.test_plan_apply_undo` | Health is a header/structure walk through the carver's sizers (`sanitizer_rules.py:78-96`), one of the two forms 5.1 allows. |
| 5.1 phase 2 (lossless conversions, `fix` → cache, `replace`) and phase 3 (transcode presets) | NOT IMPLEMENTED (deferred, documented) | doc 05 `:33-34` "1.x, not shipped in 1.1"; no cache path or `replace` action in `viwo/core/sanitizer.py:129-141,170` | |
| 5.1 Tdarr table: any folder as library, cache-then-swap with original to `.trash`, bounded worker count (default 2), re-scan any time | NOT IMPLEMENTED (deferred, documented) | doc 05 `:5` "Not a decision"; cache/swap deferred to phase 2 (`:33,:56`); `plan()` takes a sub-folder of the workspace only (`viwo/core/sanitizer.py:67-71`, `viwo/core/sanitizer_rules.py:198-201`); no worker pool; re-scan works (`handlers_tools.py:82-83`) | Review text, not the normative scope. |
| 5.1 lossy actions never in a default recipe, opt-in per rule | CONFORMS | `viwo/core/sanitizer_rules.py:55` (`lossy` flag), `viwo/core/sanitizer.py:40,59` (`not r.lossy` filter) | Vacuous: no lossy rule exists. |
| 5.1 plan first (read-only), apply only accepted actions, one undo token per batch | CONFORMS | `viwo/core/sanitizer.py:62-103` (plan writes only `.sanitizer/plans/`), `:144-157` (`accept` list or `"all-safe"`), `:160-191` (`undoToken`); `tests/test_sanitizer.py::SanitizerTests.test_plan_apply_undo` | |
| 5.1 rules declare `cost`, plans run in cost order, every rule checks the cancel token | CONFORMS | `viwo/core/sanitizer_rules.py:56,182-189` (sorted by `(cost, rule_id)`), `viwo/core/sanitizer.py:75-83,159` (`Step.tick(cancel)`); `tests/test_sanitizer.py::SanitizerTests.test_cancel_stops_the_scan` | |
| 5.1 undo saved to disk, survives a restart | CONFORMS | `viwo/core/sanitizer.py:177-181` (`.sanitizer/journal/<plan>.json`, atomic), `:194-211` | |
| 5.2 `SanitizerRule` / `BatchRule` provider objects from core and plugins via `sanitizer_rules()`; `rule_id`, `owner`, `category`, `default_enabled`, `lossy`, `cost`, `dependencies()`, `applies_to`, `inspect`, `fix`, `inspect_all` | CONFORMS | `viwo/core/sanitizer_rules.py:48-75,178-189` (`collect_rules(rt)` accepts plugin rules whose id starts with `<plugin id>.`), `viwo/contracts/plugin.py:192-194` | No plugin ships a rule yet (`grep -rn "def sanitizer_rules" viwo/plugins` is empty); engine rules are phase 2 examples. |
| 5.2 plugin rules reach the planner ("provider: core or plugin") | CONFORMS | `viwo/api/handlers_tools.py:85` (`collect_rules(app.rt)` on the route), `viwo/cli_extra.py` (same on the CLI); `tests/test_sanitizer.py::test_plan_request_fields_and_plugin_rules` (a plugin rule's finding reaches the plan) |  |
| 5.2 `AssetRef { path, rel, ext, size, head }` handed to `applies_to` / `inspect` | CONFORMS | doc 5.2 revised: rules receive the file's `Path` and derive ext, size and head themselves |  |
| 5.2 `Finding`, `Recipe`, `SanitizePlan` (page, total, offset, limit), `SanitizeReport` (planId, applied, moved[], trashed, failed[], undoToken); camelCase on the wire | CONFORMS | `viwo/core/sanitizer_rules.py:42-45` + size `viwo/core/sanitizer.py:92-94` (finding), `sanitizer.py:27-34,38-41` (recipe), `:97,103` (plan with `total`, `offset`, `limit`), `:184-191` (report) | |
| 5.2 `inspect` never writes | CONFORMS | `viwo/core/sanitizer_rules.py:78-96,102-140` (read-only, mmap read) | |
| 5.2 `fix` writes only into `.sanitizer/cache/` (phase 2); core commits `rename` (`__N`) and `trash` (`.trash/items/<rel>`); `replace` phase 2 | CONFORMS | `viwo/core/sanitizer.py:106-110` (`next_free`), `:129-141` (`trash.area(..., "items")`), `viwo/core/sanitizer_rules.py:67-68`; `tests/test_sanitizer.py:57-63` | `replace` deferred per the clause itself. |
| 5.2 cost order; per-file rules stop at the first verdict; batch rules last and see earlier findings so the last copy is never trashed; cancel through the scan step | CONFORMS | `viwo/core/sanitizer.py:76-87`, `viwo/core/sanitizer_rules.py:151,166-167`; `tests/test_sanitizer.py:52-54` | |
| 5.2 plan remembers each file's size; `apply` refuses a stale plan | CONFORMS | `viwo/core/sanitizer.py:92-94,151-156` | |
| 5.2 lossy recipe cannot be default nor run automatically after extraction | CONFORMS | `viwo/core/sanitizer.py:40,59`; no SANITIZE stage (`viwo/contracts/pipeline.py:18-27`) | Vacuous. |
| 5.2 journal per apply at `.sanitizer/journal/<plan_id>.json`; undo in reverse | CONFORMS | `viwo/core/sanitizer.py:177-181,199-201` | Several applies of one plan append to one journal (`:179`). |
| 5.2 rules use media/image backends through slots, never direct tool calls | CONFORMS | no rule invokes a tool; `dependencies()` hook at `viwo/core/sanitizer_rules.py:58-59`; `sniff` uses the carver's sizers (`:84-93`) | Vacuous until phase 2. |
| 5.3 `GET /api/sanitizer/recipes`: built-in + saved custom recipes with rules and lossy flag | CONFORMS | `viwo/api/handlers_tools.py:67-74,155` | Serves a hard-coded copy of `RECIPES` rather than `sanitizer.recipes()` (`viwo/core/sanitizer.py:38-41`), so plugin rules would not be listed; custom recipes: none, documented as "one built-in recipe" (doc 05 `:52`). |
| 5.3 `POST /api/sanitizer/plan {recipeId?, path?, offset?, limit?}` → paged `SanitizePlan` | CONFORMS | `viwo/api/handlers_tools.py:85` (`recipeId`, `path`, `offset`, `limit` passed through), `viwo/core/sanitizer.py:103` (each page item carries its absolute `index` for `accept[]`); `tests/test_sanitizer.py::test_plan_request_fields_and_plugin_rules` | an unknown recipe or a path outside the workspace is an `invalid_request` |
| 5.3 `POST /api/sanitizer/apply {planId, accept}` → `SanitizeReport` | CONFORMS | `viwo/api/handlers_tools.py:84-87`, `viwo/core/sanitizer.py:160-191`; `tests/test_sanitizer.py::SanitizerTests.test_routes` | |
| 5.3 `POST /api/sanitizer/undo {undoToken}` | CONFORMS | `viwo/api/handlers_tools.py:88-89`, `viwo/core/sanitizer.py:194-211`; same test | |
| 5.3 UI: 08 CLEANUP (plan → accept → apply → undo) as a `cleanup` job | CONFORMS | `viwo/web/js/views/cleanup.js`, `viwo/api/handlers_tools.py:81,91`; `tests/test_sanitizer.py:87-88` | |

Verdict: phase 1 and the 5.2 provider model (cost order, batch rules, stale plans, journaled undo) are implemented and tested, and the doc now describes that design. The gaps are at the edges: the HTTP route drops the plan request fields the doc lists, no caller passes the runtime so plugin rules can never run, and the `AssetRef` line was not revised to the `Path` the rules receive.
Open: 5.1 phase 2 (lossless conversions, `fix` → cache, `replace`) and phase 3 (deferred) · 5.1 Tdarr table: any folder as library, cache-then-swap with original to (deferred).

## Doc 06: code analysis hook

| Clause | Status | Evidence | Note |
|---|---|---|---|
| Status (normative 1.1): no `analysis.*` slot, hook, stage, feature value or route in 1.1; unrpyc ships as `decode.rpyc` inside extraction | CONFORMS | `grep -rln analysis viwo` is empty; `viwo/contracts/pipeline.py:18-27`; `viwo/core/wiring/ini.py:23`; `viwo/plugins/renpy/decompile.py:1-2`, `viwo/plugins/renpy/__init__.py:21` | The status clause describes the tree exactly. |
| 6.1 `AnalysisTarget` / `CodeAnalyzer` / `AnalysisContext` shapes | CONFORMS (A1) | `viwo/contracts/analysis.py` (`AnalysisTarget`, `Analyzer`, `Handoff`, `LaunchSpec`); the context is the `ExtractionContext` (doc 6 status line) | 1.3 |
| 6.1 `EnginePlugin.analysis_targets(probe)` and the per-plugin target table | CONFORMS | `viwo/contracts/plugin.py` (`analysis_targets`), generic/unity/unreal/godot/renpy plugins; `tests/test_analysis.py::TargetTests` | 1.3 |
| 6.2 Ghidra backend, JDK dependency, IL2CPP chain | CONFORMS (A1 + A2: `analysis.native`, `analysis.dotnet`, `analysis.il2cpp`, `analysis.script`) | `viwo/core/analysis/__init__.py`, `viwo/core/analysis/ghidra.py`, `viwo/core/analysis/managed.py`, `viwo/contracts/analysis.py`; `tests/test_analysis.py`; real runs on ULTRAKILL.exe, Baldi's Assembly-CSharp.dll and an IL2CPP GameAssembly.dll (STATUS) | A3-A4 slots stay normative (doc 16.2b); the IL2CPP chain is two runs (Cpp2IL output, then ilspycmd) |
| 6.3 analysis never part of extraction; `Stage.ANALYZE`; `analysis` feature flag off by default; output under `.analysis/`; one-time notice | CONFORMS | job kind `analyze` (`viwo/api/handlers_analysis.py`), `analysis` feature value off by default (`viwo/core/analysis/__init__.py` `_check_enabled`), output under `.analysis/` | no `Stage.ANALYZE`: a job kind, as doc 6 now says |
| 6.4 `/api/analysis/targets`, `/run`, `/jobs` | CONFORMS | `viwo/api/handlers_analysis.py` (`/api/analysis/targets`, `/run`, `/open`); `tests/test_api_routes.py` | 1.3 |

Verdict: exactly as the status clause says: nothing of the hook exists, and the doc now records both the deferral and the unrpyc-as-DECODE decision.
Open: 6.1 `AnalysisTarget` / `CodeAnalyzer` / `AnalysisContext` shapes (deferred) · 6.1 `EnginePlugin.analysis_targets(probe)` and the per-plugin target tab (deferred) · 6.2 Ghidra backend, JDK dependency, IL2CPP chain (deferred) · 6.3 analysis never part of extraction; `Stage.ANALYZE`; `analysis` featu (deferred) · 6.4 `/api/analysis/targets`, `/run`, `/jobs` (deferred).

## Doc 07: v1 findings and migration map

| Clause | Status | Evidence | Note |
|---|---|---|---|
| H1 extraction moves files out of the game folder → COLLECT copies, moves only from staging | CONFORMS (closed) | `viwo/core/pipeline/collect.py:124` (`copy2` when `move=False`), `viwo/core/pipeline/sources.py:60-70`; `tests/test_game_integrity.py::GameIntegrityTests.test_every_plugin_leaves_the_game_untouched`; snapshot diff `viwo/core/pipeline/guard.py:27-41`, `runner.py:146-148` | |
| H2 re-extraction deletes a user-chosen folder → ownership marker | CONFORMS (closed) | `viwo/core/workspace.py:92-120`; `tests/test_core_units.py::WorkspaceTests.test_ownership_and_policies` | |
| H3 cross-site requests, text/plain POSTs, static traversal → security model | CONFORMS (closed) | `viwo/api/server.py:53-60,106-137,179-186`; `tests/test_server.py::ServerTests.test_security_model` | |
| F1 Unity exports rmtree'd then counted | CONFORMS (closed) | exports go to `work/staging/unity` and are moved by COLLECT (`viwo/core/pipeline/sources.py:21-32`); the work dir is removed only after the result is built (`viwo/core/pipeline/runner.py:113-117`) | |
| F17 extractall without filters (zip-slip); no Python version declared | CONFORMS (closed) | `viwo/backends/archives.py:12,36-43,57,77` (`safe_member`, `safe_tar_members`), `viwo/core/thirdparty.py:27,180,190`; `tests/test_pipeline.py::PipelineTests.test_extract_keeps_game_untouched_and_blocks_traversal`; `pyproject.toml:10` (`>=3.11`) | |
| F11 Unity completeness gate always passes | CONFORMS (closed by removal) | `viwo/plugins/unity/__init__.py:94-97` (warn only when nothing collected); no gate | |
| F2 `"mainData"` marker never matched | CONFORMS (closed) | `viwo/plugins/unity/__init__.py:52` (`"maindata"`, lowercase) | |
| F3 only `.trash` filtered; metadata leaks | CONFORMS (closed) | `viwo/contracts/workspace.py:19-21`; `viwo/core/curation/trash.py:61`, `viwo/core/curation/sorting.py:59,70`, `viwo/core/merger/media.py:93` | |
| F18 three trash layouts share `.trash/`; prefix matching | CONFORMS (closed) | `viwo/core/curation/trash.py:85-91` (exact-name regex); `tests/test_curation.py::GroupTrashTests.test_trash_restore_delete_exact_names` | |
| F4 7-Zip in Program Files not found by the archive code | CONFORMS (closed) | `viwo/backends/archives.py:16-19` (`install_dirs=("7-Zip",)`), `viwo/os/windows.py:85-86,112` (`_install_roots`) | |
| F5 unrpa required at boot | CONFORMS (closed) | `viwo/plugins/renpy/__init__.py:24` (`unarchive.rpa` main `rpa-safe`, spare `unrpa`) | |
| F19 unpinned pip installs at boot | CONFORMS (closed) | `viwo/data/tools.json` pins; `tests/test_thirdparty.py::InstallerTests.test_manifest_pins_match_pyproject`, `test_manifest_is_complete_and_https`; `viwo/core/thirdparty.py:142-143` (https only) | |
| F6 dedupe by name + size + mtime | CONFORMS (closed) | `viwo/core/pipeline/collect.py:62-71` (size + sha256) | |
| F20 `/preview/` served from the temp path | CONFORMS (closed) | `viwo/api/server.py:145-150` (`resolve(self.app.workspace, rel)`) | |
| F8 guessed UABEA/AssetRipper invocations | CONFORMS (closed) | `grep -rli "uabea\|assetripper" viwo --include=*.py` is empty | |
| F9 "Permanently deleted (0 files)" | CONFORMS (closed) | `viwo/core/curation/trash.py:136-138` (count before `rmtree`) | |
| F10 UI never sends `extractionType` | CONFORMS (closed) | `viwo/web/js/views/extract.js:227` | |
| F12 engine knowledge in core (`.rpa`, `.unitypackage`, Ren'Py `game/`) | CONFORMS (closed) | `.rpa` slot `viwo/plugins/renpy/__init__.py:24`, `.unitypackage` slot `viwo/plugins/unity/__init__.py:36-41`, source roots from `plugin.source_roots()` (`viwo/core/pipeline/sources.py:55-57`) | |
| F13 OS-specific code spread across modules | CONFORMS (closed) | `viwo/os/_shared.py`, `viwo/os/windows.py`, `viwo/os/linux.py` behind the OS contract; `viwo/api/handlers.py:72,171,239` call `app.rt.os.shell` | |
| F14 three `tlog` definitions | CONFORMS (closed, n/a) | single `App.log` (`viwo/api/app.py:43-52`) + `ProgressEvent` | |
| F15 read-modify-write session log | CONFORMS (closed) | `viwo/api/app.py:46-52` (append under `self._lock`) | |
| F16 bogus "SLICE6 optimized" line | CONFORMS (closed, n/a) | v1 code removed; `grep -rn SLICE6 viwo` is empty | |
| 7.2 "Where each v1 file went (as built)" | CONFORMS | doc 07 `:42-61` revised to the real targets; files present: `viwo/api/server.py`, `handlers.py`, `routes.py`, `app.py`, `viwo/core/wiring/`, `viwo/os/_shared.py`, `viwo/core/pipeline/unpack.py`, `collect.py`, `viwo/core/workspace.py`, `viwo/core/curation/`, `viwo/core/merger/`, `viwo/cli_extra.py`, `viwo/cli_format.py`, `viwo/core/jobs.py`, `viwo/core/sanitizer.py`, `viwo/core/sanitizer_rules.py`, `viwo/core/capture/`, `docs/ui.md` | Was "proposed" at 1.1; now a record of what exists. |
| 7.3 order of work (hotfix → characterization → core → engines) | CONFORMS | `docs/prototype-b/STATUS.md:13` (M10 done), doc 16 roadmap | |

Verdict: every finding H1-H3 and F1-F20 stays closed in code with a test or a structural guarantee behind it, and the 7.2 map now records the modules as built.
Open: none.

## Counts per status

| Doc | CONFORMS | DEVIATES (defect) | DEVIATES (intentional, documented) | NOT IMPLEMENTED (deferred, documented) | NOT IMPLEMENTED (undocumented gap) |
|---|---|---|---|---|---|
| Doc 03: pipeline, routing and mixed mode | 34 | 0 | 1 | 0 | 0 |
| Doc 04: HTTP API, workspace layout and configuration | 37 | 0 | 1 | 1 | 0 |
| Doc 05: asset sanitizer | 21 | 0 | 0 | 2 | 0 |
| Doc 06: code analysis hook | 1 | 0 | 0 | 5 | 0 |
| Doc 07: v1 findings and migration map | 24 | 0 | 0 | 0 | 0 |
| Total | 117 | 0 | 2 | 8 | 0 |


---

# Conformance re-audit (v1.2.0, contract 1.1): docs 11, 12, 14, 18

Read-only audit of branch `makeover` at tag v1.2.0 (commit fb82623) against the current contract docs. Status vocabulary: CONFORMS · DEVIATES (defect) · DEVIATES (intentional, documented) · NOT IMPLEMENTED (deferred, documented) · NOT IMPLEMENTED (undocumented gap). "Documented" means the current contract doc (clause, revision or History note), `docs/prototype-b/STATUS.md`, `README.md` or `ARCHITECTURE.md` says so. Every `path:line` is the current tree; test names exist now. Docs 11, 12, 14 and 18 themselves were not revised in the 1.2 batch (`git diff v1.1.0 HEAD -- docs/contract/` touches 03-07, 13, 15-17, README); the revisions that document deviations for these docs live in README (decisions D12, D18, D22, principle 6), doc 03:16, doc 05:78, doc 15:4-6,47, doc 16:3,18,62-68,88 and doc 17:3,19,79-80.

## 11. Runtime capture

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 11.1 revision (1.0): anti-cheat markers, online titles and tos-sensitive plugins produce warnings and one confirmation, never refusals; no evasion code authored | CONFORMS | `viwo/core/capture/policy.py:1-5,66-89,112-130`; `viwo/data/capture_policy.json:2`; `tests/test_capture.py::PolicyTests::test_feature_switch_confirmation_and_warnings`; `tests/test_api_capture.py::CaptureApiTests::test_warnings_confirmation_and_capture` | Warnings are carried into the run record (`viwo/core/capture/__init__.py:139`) and printed before launch by the CLI (`viwo/cli_extra.py:163-165`). |
| 11.1 capture only from a game the user launches through the framework, on their own machine | CONFORMS | `viwo/core/capture/renderdoc.py:48-67` (`renderdoccmd capture` starts the exe); `viwo/core/capture/__init__.py:122-123` (exe must be a file inside the game folder); `tests/test_api_capture.py:70-74` | |
| 11.1 prefer static extraction; capture offered for what static could not produce | CONFORMS | `viwo/core/capture/__init__.py:37-40,111-113` (files whose hash is in the static provenance are dropped) | |
| 11.1 provenance records that each output came from a capture | CONFORMS | `viwo/core/capture/__init__.py:114,129-131` (origin `capture:<backend>:<job>` appended to `provenance.jsonl`) | |
| 11.1 no global hooks, no attaching to foreign processes, no drivers | CONFORMS | `viwo/core/capture/renderdoc.py:48-67` (per-process launch under `renderdoccmd`, no global hook flag) | |
| 11.1 no game-folder modification without an exact, reversible journal (11.4) | CONFORMS | `viwo/core/capture/journal.py:36-56,66-83`; `tests/test_capture.py::JournalTests::test_restore_and_crash_recovery`, `::test_damaged_journal_restores_what_it_can` | The RenderDoc path never writes into the game folder; the journal is exercised by tests only (no runtime agent yet). |
| 11.1 precondition: `capture` feature flag off → refuse | CONFORMS | `viwo/core/capture/policy.py:115-118`; `tests/test_capture.py:56-58` | The only gate that remains. |
| 11.1 precondition: the user confirmed once per game → ask | CONFORMS | `viwo/core/capture/policy.py:92-109,119-127` (`confirmed.json` next to the capture journals, keyed by resolved game path); `tests/test_capture.py:60-62`; `tests/test_api_capture.py:58-62` | Closed in 1.2 (was per call). The persistence itself has no test: both tests pass `confirmed=True` on every call. |
| 11.1 precondition: anti-cheat markers in the game folder → (revised) warn | CONFORMS | `viwo/core/capture/policy.py:31-37,70-75`; `viwo/data/capture_policy.json:3-15`; `tests/test_capture.py:66-67` | Warning, not refusal, per the 11.1 revision note. |
| 11.1 precondition: an anti-cheat service running (best effort, OS layer) → (revised) warn | CONFORMS | `viwo/core/capture/policy.py:40-54,76-79`; `viwo/data/capture_policy.json:16-27` | Closed in 1.2. Windows goes through `rt.os.process.run(["tasklist", ...])`; Linux reads `/proc/*/comm` directly rather than through the OS layer. No test covers the service branch. |
| 11.1 precondition: built-in online/competitive list (data file) → (revised) warn | CONFORMS | `viwo/core/capture/policy.py:80-84`; `viwo/data/capture_policy.json:28-39`; `tests/test_capture.py:68-73` | Matched on the game folder name. |
| 11.1 precondition: network reachable → warn and suggest going offline (best effort) | CONFORMS | `viwo/core/capture/policy.py:57-63,87-88,128-130` | Closed in 1.2: one 0.8 s connection attempt; tests filter the network line (`tests/test_capture.py:62,69`). |
| 11.1 marker list is data, shipped and versioned in the repo; verified vs unverified names | CONFORMS | `viwo/data/capture_policy.json:2-4,26` | |
| 11.1 example: Overwatch capture "would always be refused"; its plugin static-only | DEVIATES (intentional, documented) | `viwo/core/capture/policy.py:80-86` (online title + tos-sensitive plugin = two warnings); `viwo/plugins/overwatch/__init__.py:3,54-57` | Superseded by the 11.1 revision note and README D22 (`docs/contract/README.md:146`). |
| 11.2 graphics-API capture via RenderDoc | CONFORMS | `viwo/core/capture/renderdoc.py:32-72` | |
| 11.2 engine runtime agents (BepInEx, UE4SS, Ren'Py hook, Godot override.cfg), Frida, audio loopback | NOT IMPLEMENTED (deferred, documented) | doc 11.6 last bullet ("one path only"); `docs/prototype-b/STATUS.md:14`; doc 16:66 (M11 row) | |
| 11.3 a capture is a job of kind `capture` | CONFORMS | `viwo/api/handlers_capture.py:57-73` (`locked_job("capture")`); `viwo/api/handlers_jobs.py:24`; `tests/test_api_capture.py:63-66` (`jobId`) | The CLI runs the same function synchronously (`viwo/cli_extra.py:155-167`). |
| 11.3 steps POLICY → SETUP → LAUNCH → CAPTURE → HARVEST → GATHER → DIFF → RESTORE → REPORT | CONFORMS | `viwo/core/capture/__init__.py:1-2,120-153` (POLICY :124, pending RESTORE :125, LAUNCH+CAPTURE+HARVEST `renderdoc.py:41-88`, GATHER :114-115, DIFF :111-113, REPORT :132-144) | SETUP is empty (no agents); RESTORE runs before the session (pending journals), which is equivalent while nothing writes to the game folder. |
| 11.3 DIFF against the latest static extraction by content hash | CONFORMS | `viwo/core/capture/__init__.py:37-40,111-113`; `tests/test_capture.py::CaptureRunTests::test_capture_harvest_gather_diff` | Perceptual hashing stays an open ❓ in the doc. |
| 11.3 interfaces `launch/trigger/stop/harvest`, `RuntimeAgent`, `LaunchSpec`, `os.launch` | DEVIATES (intentional, documented) | `viwo/core/capture/renderdoc.py:41` (one `capture(spec, staging, ctx)`), `viwo/core/capture/__init__.py:104` (spec dict `{exe, workdir, args}`); no `os.launch` in `viwo/contracts/os.py` | Doc 11.3 is headed "Proposed structure"; STATUS M11 and doc 16:66 call the delivery a pilot. The interactive trigger is RenderDoc's in-game hotkey; since 1.3.6 `capture_after` triggers one frame through RenderDoc's target control (`rd_trigger.py`) with the game as a tracked child. |
| 11.3 LAUNCH on Linux through Proton/Wine | NOT IMPLEMENTED (deferred, documented) | doc 11.3 ❓; doc 14.6:80 ("Wine is out of scope for now"); doc 16:68 (M13+ open: Wine) | |
| 11.4 journaled overlay: hash-recorded writes, restore in reverse, verify hashes, unfinished restore at the next start | CONFORMS | `viwo/core/capture/journal.py:36-64,66-83,117-127`; `viwo/core/capture/__init__.py:58-69`; `tests/test_capture.py::JournalTests` | JSON-lines journal written atomically; damaged lines skipped with a warning (`journal.py:86-114`). |
| 11.4 copy-the-game mode as an ini option ❓ | NOT IMPLEMENTED (deferred, documented) | doc 11.4 ❓; `docs/contract/README.md:131` (D13: journaled overlay + crash recovery) | Overlay chosen; copy mode stays an open option. |
| 11.5 `capture.gpu`: main RenderDoc, spare apitrace | DEVIATES (intentional, documented) | `viwo/core/capture/__init__.py:30` (no spare) | Doc 11.6: "Prototype scope: one path only"; doc 16:66 and STATUS M11 list RenderDoc alone. |
| 11.5 RenderDoc Python module runs as a separate helper process | CONFORMS | `viwo/core/capture/renderdoc.py:19-25,74-88` (`rd_harvest.py` under the `rdpython` interpreter); `viwo/data/tools.json:274-289`; `docs/prototype-b/STATUS.md:42` | |
| 11.5 other slots (`capture.gpu-d3d12`, `runtime.*`, `capture.memory`, `capture.audio`) | NOT IMPLEMENTED (deferred, documented) | doc 11.6 last bullet; doc 16:68 | |
| 11.6 every backend declares its network use; offline flags on by default | CONFORMS | `viwo/contracts/slots.py:59` (`network`), `viwo/plugins/overwatch/__init__.py:65` (DataTool declares `download`, docstring says why), `viwo/core/capture/renderdoc.py` (`none`, `VIWO_OFFLINE=1`); `tests/test_l0_static.py::test_every_backend_declares_network_and_untrusted_parsing` | doc 11 was rewritten by the capabilities respec in this commit (not re-audited here) |
| 11.6 copyleft tools run as separate components, never linked into the core | CONFORMS | `tests/test_l0_static.py::BackendDeclarationTests::test_gpl_backends_run_as_subprocesses`; `viwo/core/capture/renderdoc.py:33` | |
| 11.6 terms of service stay the user's responsibility, stated plainly | CONFORMS | `viwo/core/capture/policy.py:21-24`; `viwo/cli_args.py:70-78`; `README.md:36-42,219` | |

Verdict: the pilot path (RenderDoc capture, journal, diff, report) and the 1.0 warnings policy are implemented and tested; 1.2 closed the per-game confirmation, the running-service warning and the network warning. The one defect is the network declaration: the attribute exists but only RenderDoc sets it, so DataTool carries a false `none`.
Open: 11.1 example: Overwatch capture "would always be refused"; its plugin st (intentional) · 11.2 engine runtime agents (BepInEx, UE4SS, Ren'Py hook, Godot override. (deferred) · 11.3 interfaces `launch/trigger/stop/harvest`, `RuntimeAgent`, `LaunchSp (intentional) · 11.3 LAUNCH on Linux through Proton/Wine (deferred) · 11.4 copy-the-game mode as an ini option ❓ (deferred) · 11.5 `capture.gpu`: main RenderDoc, spare apitrace (intentional) · 11.5 other slots (`capture.gpu-d3d12`, `runtime.*`, `capture.memory`, `c (deferred).

## 12. Headless core, CLI and jobs

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 12.1 core boots from the ini without a server; the server is one front end | CONFORMS | `viwo/core/wiring/boot.py:91-95`; `viwo/api/app.py:146-152` | |
| 12.1 long work runs as jobs with an event stream; `/api/logs` is an adapter over the latest events | CONFORMS | `viwo/core/jobs.py:51-95`; `viwo/api/app.py:82-87,119-139`; `viwo/api/handlers_tools.py:39,91,113,139-141`; `viwo/api/handlers.py:229-234` | |
| 12.1 every capability reachable from the CLI, with `--json` | DEVIATES (intentional, documented) | `viwo/cli_args.py:33-95` (no `merge`); `viwo/cli.py:41,149-150` (`--json`) | The media merger is UI/API only (`README.md:16,166` lists it as a web UI feature; doc 14.3 S0 scopes "merger build as job adapter"). |
| 12.2 facade `boot`, `info`, `detect`, `submit`, `jobs.get/list/cancel`, `workspace`, `shutdown` | DEVIATES (intentional, documented) | `viwo/core/wiring/boot.py:31-95` (`Runtime.info/dependency_report/self_checks`, `boot()`); jobs through `JobRunner` (`viwo/core/jobs.py:51-105`) and `App` (`viwo/api/app.py:20-139`); no `submit(JobSpec)`, no `shutdown()` | Doc 12:5 "All names are provisional". |
| 12.3 job kinds `extract, unpack, sanitize.plan, sanitize.apply, merge, analyze, capture` | DEVIATES (intentional, documented) | `viwo/api/handlers_jobs.py:18-26` (extract, survey, repack, preflight, install, capture, cleanup); `viwo/api/handlers.py:232` (merge); `viwo/cli.py:104-109` (`unpack` synchronous) | Sanitizer plan/apply/undo share kind `cleanup` (doc 05:78); `analyze` is open in doc 16:68 ("analysis backends") and doc 06 6.4 ("later"). |
| 12.3 `JobSpec {kind, params, ini_digest}` serializable and replayable | DEVIATES (intentional, documented) | `viwo/api/handlers_jobs.py:29-31` (`{kind, params}`); `viwo/cli_extra.py:28-58` (replay rebuilds the request from the run record; `extract` only); `viwo/core/records.py:28-29` (ini path and values instead of a digest) | Doc 12:5 provisional names; `viwo replay` is documented as re-running "the extraction stored in a run record" (`viwo/cli_args.py:43`). |
| 12.3 states `queued → running → succeeded / failed / cancelled` | CONFORMS | `viwo/core/jobs.py:22,83-95` | |
| 12.3 `JobHandle {id, kind, state, created, started, finished}` | CONFORMS | `viwo/core/jobs.py:28-30,35-48` | Closed in 1.2. No test asserts the three timestamps (`tests/test_api_routes.py:44-62` checks `state` and `result` only). |
| 12.3 events: ordered stream, replayable from offset N | CONFORMS | `viwo/api/routes.py:91-98`; `tests/test_api_routes.py::RouteTests::test_jobs_events_and_cancel` | |
| 12.3 result kind-specific | CONFORMS | `viwo/api/routes.py:85-88` | |
| 12.3 run record: JobSpec, effective ini, slot bindings, each tool's version, result → `.extraction_metadata/runs/<job>.json` | CONFORMS | `viwo/core/pipeline/runner.py:268` (`context`: ini path, per-value sources, bindings, tool versions and locations), `viwo/core/records.py:12-35` | capture and repack records carried it since 1.2; extraction since 1.2.1 |
| 12.3 "same record + same tools → same output" (principle 7) | CONFORMS | `tests/test_pipeline.py::ReplayAndUnpackTests::test_replay_reproduces_the_workspace` | |
| 12.3 concurrency: one lock per workspace; writing jobs hold it; curation takes it with a short timeout → 409 busy; read-only work does not take it | DEVIATES (intentional, documented) | `viwo/core/workspace.py:192-198` (non-blocking, `busy`); `viwo/api/app.py:109-139`; `viwo/api/handlers_tools.py:77-91` (sanitizer plan runs as a `cleanup` job under the lock) | The plan taking the lock is documented in doc 05:78 (plan/apply/undo are one job kind so 04 JOBS shows them). Timeout is 0 rather than "short". |
| 12.3 lock across processes (lock file, stale takeover) | CONFORMS | `viwo/core/workspace.py:4-5,123-136,144-180`; `tests/test_workspace_lock.py::LockFileTests` | Beyond the doc. |
| 12.3 cancellation through CancelToken; the process tree is killed | CONFORMS | `viwo/core/jobs.py:26,86-88`; `viwo/api/routes.py:101-104`; `viwo/os/_shared.py:26,62,89` (`_kill_tree`); `tests/test_pipeline.py::PipelineTests::test_selected_extensions_and_cancel` | |
| 12.3b envelope `{ok, data, error, warnings}`; `Error {code, message, owner, hint}` | CONFORMS | `viwo/contracts/errors.py:23-52` | |
| 12.3b code set | DEVIATES (intentional, documented) | `viwo/contracts/errors.py:8-20` adds `needs_decision` and `offline` (`not_found` is in the doc) | `needs_decision` is documented in doc 04:97 (`needsDecision`, exit 2); `offline` (503, `viwo/api/routes.py:24`) is documented only in code. Additions only. |
| 12.3b outcome → code mapping; refusals `refused`; programming errors `internal` with the trace in the log only | CONFORMS | `viwo/core/jobs.py:87-92`; `viwo/api/server.py:99-101`; `viwo/cli.py:141-148`; `tests/test_cli.py::ErrorSurfaceTests::test_unexpected_exception_is_an_internal_error_not_a_traceback` | |
| 12.3b HTTP: expected failures 200 `ok:false`; busy 409, invalid_request 400, refused 403, internal 500 | CONFORMS | `viwo/api/routes.py:19-26,107-113`; `tests/test_api_routes.py:60-61` (404 for not_found) | Plus not_found 404, offline 503. |
| 12.4 commands `info, detect, extract, unpack, slots, sanitize, merge, analyze, capture, serve` | DEVIATES (intentional, documented) | `viwo/cli_args.py:33-95` and `viwo/cli.py:52-56` (info, slots, detect, extract, replay, unpack, config, survey, repack, capture, sanitize, install, diag, indexes, serve) | `merge` absent (`README.md:166` web UI); `analyze` open (doc 16:68). Extra commands are additions. |
| 12.4 `extract` flags `--plugin / --mixed / --policy / --exts / --workspace / --option` | CONFORMS | `viwo/cli_args.py:98-122` | Plus `--on-existing`, `--carve`. |
| 12.4 `unpack <archive> [--slot] [--backend main/spare/ID]` | CONFORMS | `viwo/cli_args.py:48-53`; `viwo/cli_check.py:47-93`; `viwo/cli.py:104-109` | Closed in 1.2. No test exercises `--slot/--backend` (`tests/test_pipeline.py::test_unpack_one_archive` covers the plain path only). |
| 12.4 `slots [--check]` runs each backend's self-test | CONFORMS | `viwo/cli_args.py:36-38`; `viwo/cli_check.py:15-44`; `viwo/contracts/slots.py:73-86` (`self_check`); `viwo/cli.py:66-68,162-163` | Closed in 1.2 (doc 16:88 names it). No test; exit 1 when a bound main fails. |
| 12.4 `sanitize plan / apply / undo` | DEVIATES (intentional, documented) | `viwo/cli_args.py:79-82` (`--apply`, `--undo TOKEN`); `viwo/cli_extra.py:115-125` | Same operations in flag form; `README.md:132` documents the flags. |
| 12.4 globals `--ini --os --json --quiet --verbose` | CONFORMS | `viwo/cli.py:39-46,79-90`; `viwo/cli_extra.py:148-152` | `--quiet/--verbose` closed in 1.2; accepted before and after the subcommand. No test. |
| 12.4 global `--profile` | CONFORMS | `viwo/cli.py:42`, `viwo/core/wiring/boot.py:92`; `tests/test_config.py::test_suffix_clash_is_reported_and_profile_flag_selects_plugins` | an unknown profile is an `invalid_request` (exit 2) |
| 12.4 exit codes 0 / 1 / 2 / 3 / 4 / 130 | CONFORMS | `viwo/cli.py:27,155`; `viwo/api/server.py:231-234` (strict preflight → 4); `viwo/cli_args.py:28-29`; `tests/test_cli.py::ErrorSurfaceTests::test_ctrl_c_is_a_clean_cancel`, `::test_missing_folders_are_not_found_without_traceback`; `tests/test_pipeline.py::CliTests::test_info_extract_and_exit_codes` | 3 covers "unsupported OS layer" and containment refusals, as the epilog states. |
| 12.4 `Start.py` keeps working as `viwo serve` with the default ini | CONFORMS | `Start.py:8` | |
| 12.5 v1 routes as thin adapters; `/api/extract` submits a job and waits | CONFORMS | `viwo/api/app.py:68-107` (`background=False`) | |
| 12.5 `GET /api/jobs/<id>`, `GET /api/jobs/<id>/events?from=N`, `POST /api/jobs/<id>/cancel` | CONFORMS | `viwo/api/routes.py:116-138`; `tests/test_api_routes.py::RouteTests::test_jobs_events_and_cancel` | SSE "later" per the doc. |
| 12.5 `POST /api/jobs` (generic submit) | CONFORMS | `viwo/api/handlers.py:291`; `tests/test_api_routes.py::test_generic_job_submit_runs_the_kind_handler` |  |
| 12.5 curation actions synchronous, not jobs | CONFORMS | `viwo/api/handlers.py:83-151` through `App.locked` (`viwo/api/app.py:109-117`) | |
| 12.5b Python 3.11+, `pyproject.toml` with a `viwo` console entry point | CONFORMS | `pyproject.toml:10,22-23` | |
| 12.5b runtime dependencies pinned; tool lock file (name, version, URL, checksum) used by CI | CONFORMS | `pyproject.toml:16-20`; `viwo/data/tools.json`; `.github/workflows/ci.yml:59-63` (`viwo install --all`) | |
| 12.5b `pytest` as the dev-only dependency | DEVIATES (intentional, documented) | `pyproject.toml:20` (ruff only); doc 17:3,79 (History: stdlib `unittest`, no framework installed) | |
| 12.5b no installer or packaged desktop app in the prototype | DEVIATES (intentional, documented) | `viwo/core/thirdparty.py` (pinned installer), `packaging/build_portable.py` (portable `viwo.exe`); `docs/contract/README.md:59` (principle 6 History) and `docs/prototype-b/STATUS.md:53-56` | Both shipped in 1.0 with the owner's decision recorded. |
| 12.6 jobs run in threads (process isolation per backend later) | CONFORMS | `viwo/core/jobs.py:64-67` | Process isolation per backend is not offered; GPL tools are subprocesses anyway. |

Verdict: envelope, codes, job model, events, cancellation, locking, exit codes and the CLI surface match the doc; 1.2 closed JobHandle fields, `slots --check`, `unpack --slot/--backend` and `--quiet/--verbose`. Two defects remain, both half-done 1.2 work: the extraction run record never receives the new `record_context`, and `POST /api/jobs` was written but never registered. `--profile` is the one global the doc (and doc 09) still promises.
Open: 12.1 every capability reachable from the CLI, with `--json` (intentional) · 12.2 facade `boot`, `info`, `detect`, `submit`, `jobs.get/list/cancel`,  (intentional) · 12.3 job kinds `extract, unpack, sanitize.plan, sanitize.apply, merge, a (intentional) · 12.3 `JobSpec {kind, params, ini_digest}` serializable and replayable (intentional) · 12.3 concurrency: one lock per workspace; writing jobs hold it; curation (intentional) · 12.3b code set (intentional) · 12.4 commands `info, detect, extract, unpack, slots, sanitize, merge, an (intentional) · 12.4 `sanitize plan / apply / undo` (intentional) · 12.5b `pytest` as the dev-only dependency (intentional) · 12.5b no installer or packaged desktop app in the prototype (intentional).

## 14. Prototype proposal

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 14.1 orchestration + curation layer, not a format library; every file traceable | CONFORMS | `viwo/core/pipeline/collect.py:1,114-131` (provenance per collected file); `ARCHITECTURE.md` invariants; `README.md:36-42` | |
| 14.2 #1 identify, then extract; head and tail access; carving of embedded containers | CONFORMS | `viwo/contracts/slots.py:24-38,50` (`Match.embedded`, `Identifier(path, head, tail)`); `tests/test_core_units.py::test_suffix_magic_custom_and_carve` | |
| 14.2 #2 optional CATALOG → SELECT step | DEVIATES (intentional, documented) | `docs/contract/README.md:130` (D12 "closed, not built": SELECT + `viwo survey` + indexes cover it); doc 03:5 History | A decision not to build, not a deferral. |
| 14.2 #3 wrapper plugins + one re-detection after unpacking an outer wrapper | CONFORMS | `viwo/core/pipeline/export.py:27-51`; `viwo/core/pipeline/runner.py:139`; doc 03:16 | Closed in 1.2 (`.asar`, `.nw`; one pass, never nested; threshold `mixed_threshold`). No test asserts the re-detection (`tests/test_mixed.py:55` only places an `app.asar` fixture). |
| 14.2 #4 `keys.*` slot family (user key first, finders as spares) | DEVIATES (intentional, documented) | `viwo/plugins/unreal/keys.py:1-2,91-108` (user option wins, else candidates from the executables, each verified on the pak index); Godot: user option; `docs/contract/README.md:136` (D18) | Implemented as plugin logic, not a slot family; doc 08:143-145 still lists `keys.*` slots (not this audit's doc). |
| 14.2 #5 every backend declares its network use; offline is the default | CONFORMS | same as 11.6: `viwo/contracts/slots.py:59`, `viwo/plugins/overwatch/__init__.py:65`, L0 lint |  |
| 14.2 #6 GPL backends are always subprocess backends | CONFORMS | `tests/test_l0_static.py::BackendDeclarationTests::test_gpl_backends_run_as_subprocesses`; `viwo/contracts/slots.py:58` | The L0 lint doc 17 asked for exists since 1.2. |
| 14.2 #7 never unpickle game data in-process; risky parsers isolated | CONFORMS | `viwo/plugins/renpy/rpa.py:36-37,60` (`_SafeUnpickler.find_class` allow-list); `viwo/contracts/slots.py:60` (`parses_untrusted_in_process` declared, linted by `tests/test_l0_static.py:117-121`) | |
| 14.2 #8 runtime capture has a hard refusal policy and a journaled overlay | DEVIATES (intentional, documented) | `docs/contract/README.md:146` (D22); doc 11.1 revision note; `viwo/core/capture/policy.py:1-5` | Overlay holds (`viwo/core/capture/journal.py`); refusals became warnings in 1.0. |
| 14.3 S-1 v1 hotfix: copy-not-move, marker before rmtree, token / JSON-only / Host check, safe extraction filters, exports into staging, dot-folder filter | CONFORMS | `viwo/core/pipeline/collect.py:1`; `viwo/core/workspace.py:41-64`; `viwo/api/server.py:53-58,106-122`; `viwo/contracts/workspace.py` (`safe_member`, `inside`); `tests/test_game_integrity.py::GameIntegrityTests` | |
| 14.3 S0 lean core: contracts, OS layers, flat ini, failover binder, stage runner, lock, jobs + run records, CLI, generic plugin, `.7z` 7z → py7zr | CONFORMS | `viwo/contracts/`, `viwo/os/linux.py`, `viwo/os/windows.py`, `viwo/core/wiring/ini.py`, `viwo/core/wiring/binder.py`, `viwo/core/pipeline/runner.py:85-166`, `viwo/core/workspace.py:192-198`, `viwo/core/jobs.py`, `viwo/cli.py`, `viwo/plugins/generic/`, `viwo/backends/__init__.py:15-40` | |
| 14.3 S1–S3 Ren'Py, Unity, Godot with main / spare | CONFORMS | `viwo/plugins/renpy/__init__.py:23-27`; `viwo/plugins/unity/__init__.py:35-44`; `viwo/plugins/godot/__init__.py:39-45`; `tests/test_renpy.py`, `tests/test_unity.py`, `tests/test_godot.py` | |
| 14.3 S4 Unreal: repak → QuickBMS spare; retoc; AES key as an option | CONFORMS | `viwo/plugins/unreal/__init__.py:40-48` (`unarchive.upak` main `repak-cli`, spare `quickbms-cli`; `unarchive.utoc` retoc main, raw spare); `viwo/plugins/unreal/keys.py:91-108` | The upak spare landed in 1.2; doc 16:62 (M7 row) still says "no spare", which is now stale (doc 16 is outside this audit). |
| 14.3 S5 custom plugin loader, open-source showcase in CI, Overwatch optional and local-only | CONFORMS | `viwo/core/wiring/registry.py:4,162-210` (drop-ins with `plugin.json`, entry points); `examples/plugins/hello/`; `viwo/plugins/doom/`, `.github/workflows/ci.yml:64-71` (Freedoom); `viwo/plugins/overwatch/__init__.py:3,54-57` | Overwatch is auto-selectable with a reminder (D22). |
| 14.3 S6 mixed mode + report-only sanitizer | CONFORMS | `tests/test_mixed.py`; `viwo/api/handlers_tools.py:77-91` (plan, apply, undo) | Exceeds "report-only" (apply/undo shipped, STATUS M10). |
| 14.3 S6b round trip into a patched copy, per-plugin strategy, same-format, verified by re-extraction | CONFORMS | doc 18 section below | |
| 14.3 S7 capture pilot: policy + journal + RenderDoc + DIFF | CONFORMS | doc 11 section above | No apitrace spare (11.5 row). |
| 14.4 A1 CLI and HTTP extraction of the Ren'Py/Unity/Godot fixtures on Linux and Windows CI, game hashes unchanged | CONFORMS | `.github/workflows/ci.yml:17-43` (ubuntu + windows × 3.11/3.13); `tests/test_game_integrity.py::test_every_plugin_leaves_the_game_untouched`; `tests/test_pipeline.py::CliTests`; `tests/test_api_routes.py` | CI runs only on major tags or by hand (doc 17:80, `ci.yml:3-10`). |
| 14.4 A2 failover cases main up/down × spare up/down with fakes; L5 with real tools | CONFORMS | `tests/test_core_units.py::test_four_availability_cases`, `::test_failover_outcomes`; `.github/workflows/ci.yml:45-75`; `tests/test_l5_tools.py` | |
| 14.4 A3 the v1 web UI keeps working (characterization tests) | DEVIATES (intentional, documented) | doc 16:18 ("legacy app removed, everything ported to ViWo, new UI"); `tests/test_ui_lint.py`, `tests/test_ui_smoke.py` | |
| 14.4 A4 re-running from a run record gives an identical workspace | CONFORMS | `tests/test_pipeline.py::ReplayAndUnpackTests::test_replay_reproduces_the_workspace` | |
| 14.4 A5 product LoC ≤ 5,500 (A); each profile ini boots on its runner | DEVIATES (intentional, documented) | `tools/loc_count.py --report`: viwo 10,499 / budget 10,800; doc 15:4-6,47 (History: the 1.0/1.1 scope raised the target with the owner's approval); `loc_caps.ini:16` | The further raise to 10,800 in 1.2 is recorded on the `loc_caps.ini` line only; doc 15's table (9,800, ceiling 10,000, core 4,700) was not updated. See 18.7. |
| 14.4 B: round-trip tests pass for Ren'Py, Godot, Unreal and Unity | CONFORMS | `tests/test_roundtrip.py::RoundTripTests::test_renpy_archive_member_and_loose_file`; `tests/test_unreal.py::test_fips_197_vector_and_round_trip`; `tests/test_unity.py::test_text_asset_edit_is_written_back_and_verified`; `tests/test_l5_tools.py::RealRoundTripTest::test_unreal_patch_pak`, `::test_godot_pck_rebuild`; `tests/test_rpgmaker.py::test_v1_and_v3_round_trip` | Godot is covered by the L5 real-tool test only (fake-free); Unity with a stateful fake UnityPy (STATUS "not verified" row). |
| 14.4 B: product LoC ≤ 9,000 | DEVIATES (intentional, documented) | as 14.4 A5; doc 15:47 | |
| 14.4 B: the capture pilot's refusal and restore tests pass | DEVIATES (intentional, documented) | `tests/test_capture.py::PolicyTests` (warnings + feature switch), `::JournalTests` (restore); doc 16:66 (M11: "the refusal list became a warnings list per D22") | |
| 14.5 not in either prototype: UI redesign, Wine, decompiler backends, sanitizer apply, Unreal export, RPG Maker / Electron / GameMaker | DEVIATES (intentional, documented) | doc 16:68 (M13+ shipped: RPG Maker, Electron/NW.js, new UI, sanitizer panel; open: GameMaker, Unreal export, Wine); `docs/prototype-b/STATUS.md:12,17-18` | Wine, Unreal export and GameMaker remain out. |
| 14.6 mitigations: pinned versions, spares, `viwo slots --check` | CONFORMS | `viwo/data/tools.json`; `viwo/cli_check.py:25-44`; doc 16:88 | Closed in 1.2. |
| 14.6 Linux parity: tools with native Linux builds; Wine out of scope | CONFORMS | `viwo/data/tools.json` (15 `linux` entries); `docs/prototype-b/STATUS.md:57-59` | DataTool Windows-only by design. |
| 14.7 open decisions D11–D15 | CONFORMS | `docs/contract/README.md:129-133` (all closed: safe RPA reader main; CATALOG closed; overlay; open-source showcase + Overwatch tos-sensitive; ViWo) | |

Verdict: every slice S-1 through S7 is delivered; 1.2 added the wrapper re-detection, the Unreal upak spare, the GPL and network lints and `slots --check`. The remaining defect is the network declaration (shared with 11.6); the LoC departures are documented in doc 15 except for the 1.2 raise, which only `loc_caps.ini` records.
Open: 14.2 #2 optional CATALOG → SELECT step (intentional) · 14.2 #4 `keys.*` slot family (user key first, finders as spares) (intentional) · 14.2 #8 runtime capture has a hard refusal policy and a journaled overla (intentional) · 14.4 A3 the v1 web UI keeps working (characterization tests) (intentional) · 14.4 A5 product LoC ≤ 5,500 (A); each profile ini boots on its runner (intentional) · 14.4 B: product LoC ≤ 9,000 (intentional) · 14.4 B: the capture pilot's refusal and restore tests pass (intentional) · 14.5 not in either prototype: UI redesign, Wine, decompiler backends, sa (intentional).

## 18. Round trip

| Clause | Status | Evidence | Note |
|---|---|---|---|
| Decisions: full round trip in B; output is a patched copy; original read-only; strategy per plugin; same-format first | CONFORMS | `viwo/core/roundtrip.py:1-6,105-120,211-235`; `viwo/core/roundtrip_edits.py:43-55`; `tests/test_roundtrip.py:59` (original hashes unchanged) | |
| 18.2 provenance map written by COLLECT to `.extraction_metadata/provenance.jsonl` (containers, member path, backend, original hash) | CONFORMS | `viwo/contracts/workspace.py:10-12`; `viwo/core/pipeline/collect.py:114-131`; `viwo/core/pipeline/runner.py:260-261`; `viwo/core/provenance.py:22,47` (rewritten on moves) | |
| 18.2 edit set: modified files by hash against the provenance map | CONFORMS | `viwo/core/roundtrip_edits.py:86-112` | Moved, renamed or trashed files are reported as skipped (`:107-111`). |
| 18.2 edit set: files the user explicitly adds with a target path ("added") | CONFORMS | `viwo/core/roundtrip_edits.py:15,73-83,112` (`<workspace>/_added/<game-relative path>`); `viwo/core/roundtrip.py:56-58` (added files join the loose override item) | Closed in 1.2. No test; the `_added/` convention is stated only in the module docstring, not in doc 18.2 or README. |
| 18.2 deletions out of scope at first ❓ | NOT IMPLEMENTED (deferred, documented) | doc 18.2 ❓; `viwo/core/roundtrip_edits.py:92-94,107-111` (missing files are listed as skipped, never deleted from the copy) | |
| 18.2 strategies override / rebuild per plugin per container | CONFORMS | `viwo/core/roundtrip.py:53-78` (`override` item for loose files, `pack.*` item per container), `:150-163`, `:172-208` | |
| 18.3 POLICY: same hard refusals as capture; tos-sensitive plugins operator-tested only | DEVIATES (intentional, documented) | `viwo/core/roundtrip.py:96-102` (reminder, never refusal); `docs/contract/README.md:146` (D22) | Doc 16:64 (M9 exit criterion) still says "repack refused for policy-listed games"; stale wording outside this audit. |
| 18.3 RESOLVE: build the edit set; reject edits whose format differs from the original member unless the plugin declares a converter | CONFORMS | `viwo/core/roundtrip_edits.py:16-31,43-55,101-102` (magic check; `exported` members, the converter path, are exempt) | Closed in 1.2. Detection is magic-based over a fixed list (`MAGIC`); unknown bytes are accepted. No test. |
| 18.3 PLAN by plugin `repack_plan(edit_set, provenance)`; shown before writing | DEVIATES (intentional, documented) | `viwo/contracts/plugin.py:164-166` (`pack_slot(unarchive_slot)` instead); `viwo/core/roundtrip.py:53-78` (core builds the plan); `viwo/cli_args.py:68` (`--plan`); `viwo/api/handlers_tools.py:99-102` (`plan:true`); `ARCHITECTURE.md` ("roundtrip.py edit set -> plan -> patched copy -> pack.* slots -> verify -> report") | The plan is shown before writing. Doc 18 carries no History line stating the shipped interface (README:3 says every proposal-sounding doc should). |
| 18.3 COPY: full copy or reflink; never hardlinks | CONFORMS | `viwo/core/roundtrip.py:105-120` (`copytree(copy_function=copy2, symlinks=True)`); doc 16:64 ("copy-on-write clones were not pursued") | Links are kept as links and `_override`/`_container` refuse to write through them (`:156,166-169`). |
| 18.3 PACK through `pack.*` slots inside the copy only | CONFORMS | `viwo/core/roundtrip.py:166-208` (container resolved inside `target`, packer writes there) | |
| 18.3 VERIFY: re-extract with the matching `unarchive.*` slot; every edited member has the edited hash | CONFORMS | `viwo/core/roundtrip.py:130-147,193-198` | |
| 18.3 VERIFY: every untouched member keeps its original hash | DEVIATES (intentional, documented) | `viwo/core/roundtrip.py:40,74-77,140` (untouched hashes planned and checked by the generic re-extraction verify), `viwo/core/roundtrip.py:31` (a packer with its own `verify` adds the note "untouched members were not re-verified" to its result); doc 18.3 VERIFY row and `docs/prototype-b/STATUS.md` "Known limits" | Unity bundles and RPG Maker MV have no `unarchive.*` route back: edited objects verified, the in-place save keeps the rest, the report says so |
| 18.3 REPORT: run record with plan, edits, backends, verification | CONFORMS | `viwo/core/roundtrip.py:219-229,259-263` (`<target>/.viwo-patched/report.json`, `verified` flag, `context` with ini/bindings/tool versions) | Written atomically; not copied into the workspace runs folder (see doc 12.3 row). |
| 18.3 repack is a job of kind `repack` | CONFORMS | `viwo/api/handlers_tools.py:96-113`; `viwo/api/handlers_jobs.py:21`; `tests/test_roundtrip.py::RoundTripTests::test_http_plan_and_build` | |
| 18.4 `Packer.pack(original, members, out, ctx)`, `supports_rebuild/override`; plugin `mod_strategies()`, `repack_plan()` | DEVIATES (intentional, documented) | `viwo/contracts/slots.py:142-157` (`pack(container, members, ctx)`, `output_for`, `verify`); `viwo/contracts/plugin.py:164-166`; `ARCHITECTURE.md` round-trip line | Strategy is implied by the slot: override is core-owned (`roundtrip.py:150-163`), rebuild is the packer's. Doc 18 lacks a History line (same note as PLAN). |
| 18.5 `pack.renpy-override`: core copy into `game/` | CONFORMS | `viwo/core/roundtrip.py:150-163` (generic loose override for every engine) | |
| 18.5 `pack.rpa`: `rpa-writer` main (own index writer), `rpatool` spare | DEVIATES (intentional, documented) | `viwo/plugins/renpy/__init__.py:27` (no spare); `viwo/plugins/renpy/pack.py:57-59` | Pack spares were not pinned; doc 16:64 and STATUS M9 list the delivered packers. |
| 18.5 `pack.pck`: `godotpcktool` main, `gdre-tools` spare; encrypted PCKs need the key | DEVIATES (intentional, documented) | `viwo/plugins/godot/__init__.py:86` (no spare); `viwo/plugins/godot/pck.py:168-171` | `docs/prototype-b/STATUS.md:60-64`: the Windows GodotPckTool binary is quarantined by Defender, so `pack.pck` is unbound on that machine. |
| 18.5 `pack.pak`: override `_P.pak` via `repak pack`; signed paks reported, not bypassed; `quickbms` reimport spare ❓ | CONFORMS | `viwo/plugins/unreal/__init__.py:50` (`pack.upak`); `viwo/plugins/unreal/pak.py:154-160,168,196-201` (`.sig` note) | Slot named `pack.upak`; the ❓ reimport spare is not implemented. |
| 18.5 `pack.unity-bundle`: `unitypy` rebuild, `uabea` spare | DEVIATES (intentional, documented) | `viwo/plugins/unity/__init__.py:44` (`pack.unity`, no spare); `viwo/plugins/unity/pack.py:50-52` | TextAsset and Texture2D only (STATUS M9). |
| 18.5 `pack.zip` / `pack.tar`: stdlib, `sevenzip-cli` spare | DEVIATES (intentional, documented) | `viwo/backends/__init__.py:15`; `viwo/backends/packers.py:12-33`; `viwo/core/roundtrip.py:32` (`CORE_PACK` maps zip only) | No tar packer and no spare; STATUS M9 and doc 16:64 list what shipped. |
| 18.5 Overwatch: not supported | CONFORMS | `viwo/plugins/overwatch/__init__.py` (no pack slot); `viwo/core/roundtrip.py:96-102` (reminder for sensitive owners) | "refused by policy" became a reminder (D22). |
| 18.5 extra: `pack.rpgmaker` (MV/MZ re-encryption) | CONFORMS | `viwo/plugins/rpgmaker/__init__.py:23`; `viwo/plugins/rpgmaker/mv.py:91-104` | Beyond the doc. |
| 18.6 rule 1: never write the original; target empty or carrying the patched-copy marker | CONFORMS | `viwo/core/roundtrip.py:106,113-120`; `tests/test_roundtrip.py:59,78-82`; `tests/test_game_integrity.py` | Plus a game-folder snapshot diff after the build (`roundtrip.py:242,260-262`). |
| 18.6 rule 2: no signature / anti-tamper bypass; the report says the copy may not load | CONFORMS | `viwo/plugins/unreal/pak.py:196-201` | |
| 18.6 rule 3: same format only unless a declared converter | CONFORMS | `viwo/core/roundtrip_edits.py:43-55,101`; `viwo/plugins/unity/pack.py:1-2` (PNG → Texture2D is the declared converter) | Closed in 1.2. |
| 18.6 rule 4: verified by re-extraction before reported successful | CONFORMS | `viwo/core/roundtrip.py:193-202,259,264-270` (`verified` flag on the report and in the final event) | |
| 18.7 caps: `core/roundtrip` ≤ 450; +150 per plugin for packing; total cap unchanged at 10,000 | CONFORMS | `loc_caps.ini:9,16` (file cap 250 bounds `roundtrip.py` + `roundtrip_edits.py` under 450; `viwo = 10800`); doc 15.3 and doc 18.7 revised: the `viwo` budget line is the ceiling (10,800 since 1.2) |  |
| 18.7 testing: extract → edit → repack → re-extract → hashes match; original untouched; untouched members byte-identical | CONFORMS | `tests/test_roundtrip.py:32-61,63-81`; `tests/test_l5_tools.py::RealRoundTripTest` | |

Verdict: the round trip works as decided (patched copy, per-plugin packers, re-extraction verify, original untouched) and 1.2 closed the same-format rule, the `_added/` files and the untouched-hash check for every container except Unity, whose own verifier bypasses it. The caps clause is contradicted by the 1.2 budget raise that only `loc_caps.ini` records.
Open: 18.2 deletions out of scope at first ❓ (deferred) · 18.3 POLICY: same hard refusals as capture; tos-sensitive plugins operat (intentional) · 18.3 PLAN by plugin `repack_plan(edit_set, provenance)`; shown before wr (intentional) · 18.3 VERIFY: every untouched member keeps its original hash (intentional) · 18.4 `Packer.pack(original, members, out, ctx)`, `supports_rebuild/overr (intentional) · 18.5 `pack.rpa`: `rpa-writer` main (own index writer), `rpatool` spare (intentional) · 18.5 `pack.pck`: `godotpcktool` main, `gdre-tools` spare; encrypted PCKs (intentional) · 18.5 `pack.unity-bundle`: `unitypy` rebuild, `uabea` spare (intentional) · 18.5 `pack.zip` / `pack.tar`: stdlib, `sevenzip-cli` spare (intentional).

## Counts per status

| Doc | CONFORMS | DEVIATES (defect) | DEVIATES (intentional, documented) | NOT IMPLEMENTED (deferred, documented) | NOT IMPLEMENTED (undocumented gap) |
|---|---|---|---|---|---|
| 11. Runtime capture | 22 | 0 | 3 | 4 | 0 |
| 12. Headless core, CLI and jobs | 27 | 0 | 10 | 0 | 0 |
| 14. Prototype proposal | 21 | 0 | 8 | 0 | 0 |
| 18. Round trip | 21 | 0 | 8 | 1 | 0 |
| Total | 91 | 0 | 29 | 5 | 0 |


---

Read-only re-audit of the working tree at v1.2.0 (branch `makeover`, contract 1.1, 2026-11-03), rows redone against the current docs and the current code. Evidence is `file:line` at the current tree or a test method that exists now.
Status vocabulary: CONFORMS · DEVIATES (defect) · DEVIATES (intentional, documented) · NOT IMPLEMENTED (deferred, documented) · NOT IMPLEMENTED (undocumented gap).

## 1. docs/contract/README.md: decisions D0..D22, principles, goals, layer rule, distro model

| Clause | Status | Evidence | Note |
|---|---|---|---|
| D0 terminology: OS layer `viwo/os/`, `LinuxOS`/`WindowsOS`, backend/main/spare, three trash layouts | CONFORMS | `viwo/os/linux.py:68`, `viwo/os/windows.py:104`; `viwo/contracts/slots.py:160-167` (SlotBinding main/spare); `viwo/core/curation/trash.py:1-6` (groups/items/merger) | |
| D1 mixed mode: any plugin set at runtime + combination tests | CONFORMS | `viwo/contracts/pipeline.py:30-36` (`ExtractionMode.MIXED`, `MixedPolicy`); `tests/test_mixed.py::test_pairs_and_singles` (13 singles + 78 pairs) | |
| D2 missing dependency disables the plugin and shows why; `strict_preflight` opt-in | CONFORMS | `viwo/core/wiring/registry.py:230,248,261` ("disabled: ..."); `viwo/core/preflight.py:101-109`; `viwo/api/server.py:231-234` (exit 4); `tests/test_thirdparty.py::test_strict_problems_name_unbound_plugin_slots` | |
| D3 Unity per-extension layout | CONFORMS | `viwo/core/pipeline/collect.py:62-72` (one folder per extension); `tests/test_unity.py::test_export_into_extension_layout` | |
| D4 sanitizer: health/identity, report-only, nothing lossy by default | CONFORMS | `viwo/core/sanitizer.py:26-40` (`lossy: False`, only non-lossy rules in the safe recipe); `viwo/api/handlers_tools.py:71`; `tests/test_provenance.py::test_sanitizer_apply_and_undo` | |
| D5 custom plugins Python first; declarative form later | CONFORMS | `viwo/core/wiring/registry.py:3-5,163-169,204-215` (plugin.json drop-ins, entry points); declarative `.ksy` absent, which the clause itself defers | |
| D6 macOS later | CONFORMS | only `viwo/os/linux.py` and `viwo/os/windows.py`; `viwo/core/thirdparty.py:32` (`PLATFORM` windows/linux) | deferred by the clause |
| D7 `export.unity` failover: UnityPy main, AssetStudioModCLI spare | CONFORMS | `viwo/plugins/unity/__init__.py:43` | |
| D8 pinned versions + fetched release binaries | CONFORMS | `viwo/data/tools.json` (16 entries with version, HTTPS url, size, sha256); `tests/test_thirdparty.py::test_manifest_is_complete_and_https` | |
| D9 MIT core; GPL/AGPL only as subprocesses | CONFORMS | `viwo/plugins/quickbms/__init__.py:46`, `viwo/plugins/renpy/rpa.py:107` (`GPL`, `isolation = "subprocess"`); enforced by `tests/test_l0_static.py::BackendDeclarationTests::test_gpl_backends_run_as_subprocesses` | the L0 lint missing at 1.1 now exists |
| D10 v1 hotfix merged | CONFORMS | v1 removed entirely (doc 17.1 #3; `docs/prototype-a/STATUS.md`) | |
| D11 Ren'Py: safe reader main, unrpa spare | CONFORMS | `viwo/plugins/renpy/__init__.py:23-27`; `viwo/plugins/renpy/rpa.py:36-40` (`_SafeUnpickler`); `tests/test_renpy.py::test_malicious_index_never_runs` | |
| D12 CATALOG → SELECT: closed, not built; SELECT + survey + indexes cover it | CONFORMS | `viwo/core/pipeline/select.py:1` (pure selection), `viwo/core/survey.py:171-197`, `viwo/core/indexes.py` | doc revised to the implemented design (was an undocumented gap at 1.1) |
| D13 journaled overlay + crash recovery | CONFORMS | `viwo/core/capture/journal.py:1-6,22,117`; `tests/test_capture.py::test_restore_and_crash_recovery`, `::test_damaged_journal_restores_what_it_can` | |
| D14 open-source showcase in CI; Overwatch `tos_sensitive`, operator-tested | CONFORMS | `.github/workflows/ci.yml:62-69` (Freedoom in the real-tools job); `tests/test_l5_data.py:34-51`; `viwo/plugins/overwatch/__init__.py:54` (`tos_sensitive=True`); `sqc/04-extraction-per-engine.md` OPERATOR marks | |
| D15 name ViWo, CLI `viwo` | CONFORMS | `pyproject.toml:22-23` (`viwo = "viwo.cli:main"`) | |
| D16 Doom WAD (Freedoom) + Overwatch plugin | CONFORMS | `viwo/plugins/doom/`, `viwo/plugins/overwatch/`; `tests/test_doom.py`, `tests/test_overwatch.py`, `tests/test_l5_data.py` | |
| D17 round trip for Ren'Py, Godot, Unreal, Unity | CONFORMS | `pack.rpa` `viwo/plugins/renpy/__init__.py:27`, `pack.pck` `viwo/plugins/godot/__init__.py:86`, `pack.upak` `viwo/plugins/unreal/__init__.py:50`, `pack.unity` `viwo/plugins/unity/__init__.py:44`; `tests/test_roundtrip.py`, `tests/test_l5_tools.py::RealRoundTripTest` | plus RPG Maker and zip |
| D18 Unreal AES: user key wins, finder verified on the encrypted index, never stored | CONFORMS | `viwo/plugins/unreal/keys.py:1-2,74-108`; masking `viwo/plugins/unreal/pak.py:105-115`; `tests/test_unreal.py::test_missing_key_is_needs_key_and_user_key_wins`, `tests/test_diag.py:45-47` (`<secret>`) | |
| D19 capture pilot in B (refusal policy, journal, RenderDoc harvest, diff) | DEVIATES (intentional, documented) | refusal policy became warnings: `viwo/core/capture/policy.py:1-6,66-67`; journal/harvest/diff: `tests/test_capture.py::test_capture_harvest_gather_diff` | D22 note in README and doc 11.1 |
| D20 real-game check after B, pending the owner | NOT IMPLEMENTED (deferred, documented) | tooling in place: `sqc/games.md`, `tools/integration_games.py`, `tests/test_integration_games.py`; `docs/prototype-b/STATUS.md` "Not verified yet" table still open | owner's action, the clause says so |
| D21 coverage ladder, survey measures coverage; limits sentence superseded by D22 | CONFORMS | rungs: `viwo/core/pipeline/unpack.py:17` (`MAX_DEPTH = 10`), `viwo/core/carve/formats.py`, `viwo/core/carve/streams.py:14-17,54-57` (zlib/gzip/zstd/LZ4), `viwo/core/decode.py:26-31`, `viwo/plugins/quickbms/__init__.py:42-46`, `viwo/core/capture/`, `viwo/core/survey.py:61,197`; no key guessing: `viwo/plugins/unreal/keys.py:2` | the zstd/LZ4 half missing at 1.1 is now present (`tests/test_carve.py::OptionalStreamTests`) |
| D22 no policy boundaries, disclaimer instead | CONFORMS | `viwo/core/capture/policy.py:66-67,113-128` (warnings, one confirmation); `viwo/core/roundtrip.py:96-99` (`_reminders`); `tests/test_capture.py::test_feature_switch_confirmation_and_warnings`; `README.md:21` Philosophy, `README.md:219` Legal and disclaimer | |
| Principle 1 game folder read-only, single writer, marker-guarded clears | CONFORMS | `viwo/contracts/workspace.py:8` (`MARKER`), `viwo/core/workspace.py:62-68,101-109`; `tests/test_pipeline.py::test_extract_keeps_game_untouched_and_blocks_traversal`, `tests/test_game_integrity.py::test_every_plugin_leaves_the_game_untouched`, `tests/test_core_units.py::test_ownership_and_policies` | |
| Principle 2 authenticated local API (token, JSON-only, Host, containment) | CONFORMS | `viwo/api/server.py:29,53-58,106-132,141`; `tests/test_server.py::test_security_model`, `::test_game_folder_and_unknown_routes` | |
| Principle 3 OS-specific code only in OS layers; two recorded exceptions (msiexec, OpenProcess) | CONFORMS | `viwo/contracts/os.py:40` (`ProcessRunner.running_images`), `viwo/os/windows.py:85`, `viwo/os/linux.py:54`, `viwo/core/capture/policy.py:41` (the capture policy asks the OS layer); `tests/test_os_layer.py::test_running_images_lists_this_interpreter` | the two recorded exceptions (msiexec, OpenProcess) remain the only ones |
| Principle 4 every engine behind a slot; stages never call tools directly | CONFORMS | `viwo/contracts/slots.py:41-50,53-61`; `viwo/core/wiring/` binder; decoders/capture/pack/probe/convert are slots (`viwo/core/decode.py:26-31`, `viwo/contracts/slots.py:123-157`) | |
| Principle 5 failures isolated per owner | CONFORMS | `tests/test_core_units.py::test_failover_outcomes`; `viwo/core/wiring/registry.py:230,248` (load errors become problems); `tests/test_registry.py::test_requirement_mismatch_disables_only_that_plugin` | |
| Principle 6 plan → apply → undo for destructive bulk actions | CONFORMS | `viwo/core/sanitizer.py:92-100,150-164,177-195` (plan ids, stale-plan refusal, journal, undo); `tests/test_provenance.py::test_sanitizer_apply_and_undo`, `::test_sort_rename_trash_and_undo` | |
| Principle 7 reserved dot-folders: `.trash`, `.extraction_metadata`, sanitizer journal under `.extraction_metadata`, `.analysis` reserved | CONFORMS | README principle 7 revised: `.sanitizer` listed for plans and journals; `viwo/core/sanitizer.py:26` |  |
| Principle 8 determinism (same input + ini → same output) | CONFORMS | `tests/test_pipeline.py::test_replay_reproduces_the_workspace`, `::test_rerun_needs_decision_and_replace_is_deterministic`; `tests/test_config.py::test_shipped_distros_match_the_generator` | |
| Principle 9 honest metrics | CONFORMS | `viwo/core/pipeline/collect.py:34-40` (`by_ext`, `skipped_by_ext` counters named for what they count); `viwo/core/survey.py:41-45`; no completeness ratio anywhere | |
| Principle 10 contract `CONTRACT_VERSION = "1.0"` (MAJOR.MINOR); product `va.b.c` | CONFORMS | README principle 10 revised (`"1.1"` since the 1.2 batch); `viwo/__init__.py:4`, `viwo/contracts/pipeline.py:13` |  |
| Goal 2 adding an engine needs no core/API/UI change | CONFORMS | `viwo/core/wiring/registry.py:119-132,204-215` (scan + drop-ins + entry points); `viwo/api/plugin_assets.py`, `viwo/web/js/registry.js`; `tests/test_registry.py::test_end_to_end_extraction_through_a_dropin`, `::test_ui_modules_and_asset_containment` | |
| Goal 6 third-party tools pinned and installed automatically (History: submodules replaced) | CONFORMS | `viwo/data/tools.json`, `viwo/core/thirdparty.py`; `tests/test_thirdparty.py::test_install_pinned_tools_into_a_temp_home` | doc revised (was "sparse submodules" at 1.1) |
| Goal 7 the v1 UI keeps working; new API alongside existing routes | DEVIATES (intentional, documented) | v1 UI removed; `viwo/web/` is the new UI (`ARCHITECTURE.md` "landing + 11 views"); doc 17.1 #3 and doc 16 M1 note record the removal | the README Goals list and "Layers" block (`web/ UI (v1 kept)`) still carry the draft wording |
| Layer rule: contracts import nothing from the app; plugins never import each other; direction respected | CONFORMS | `tests/test_l0_static.py::ImportDirectionTests::test_layers_only_import_downwards`, `::test_plugins_never_import_each_other`, `::test_contracts_import_nothing_from_the_app` | two recorded debts (`viwo/backends/__init__.py` → `viwo.core.carve`, `viwo.core.merger.ffmpeg`) listed at `tests/test_l0_static.py:26-30` |
| Distro model: 2 OS × 6 profiles, custom profile from manifests, generic everywhere | CONFORMS | `distros/` 12 files; `viwo/core/wiring/distros.py`; `tests/test_config.py::test_twelve_files_named_and_written_strictly`, `tests/test_registry.py::test_custom_profile_is_derived_from_the_manifests` | the custom profile enables the built-in custom-engine plugins by manifest, not only `custom_dirs` (`distros/windows-custom.ini:9-22`) |

Verdict: 38 clauses: CONFORMS 32 · DEVIATES (intentional, documented) 2 (D19, Goal 7) · DEVIATES (defect) 3 (principle 3 unrecorded OS branch in capture policy, principle 7 `.sanitizer` folder, principle 10 contract version 1.0 vs 1.1) · NOT IMPLEMENTED (deferred, documented) 1 (D20, owner) · undocumented gaps 0. The 1.1 defects and gaps (D12, GPL lint, submodules wording) are closed.
Open: D19 capture pilot in B (refusal policy, journal, RenderDoc harvest, diff (intentional) · D20 real-game check after B, pending the owner (deferred) · Goal 7 the v1 UI keeps working; new API alongside existing routes (intentional).

## 2. doc 13: landscape coverage

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 13.1 archive breadth through QuickBMS as a bridge | CONFORMS | `viwo/plugins/quickbms/__init__.py:23-46` (pinned, GPL-2.0, subprocess, `<ext>.bms` scripts); `tests/test_quickbms.py` | GARbro / Game Extractor not wrapped (not required) |
| 13.1 unblob/binwalk-style recursive carving | CONFORMS | own carver: `viwo/core/carve/formats.py`, `formats2.py`, `streams.py:79-101`; `tests/test_carve.py::ScanTests`, `::StreamTests` | native carver chosen (doc 16.0b rungs 3-4) |
| 13.2 #1 identify separate from extract (pattern, offset, size) | CONFORMS | `viwo/contracts/slots.py:24-50` (`Match` offset/size, `SlotDefinition.identify`); `tests/test_core_units.py::test_suffix_magic_custom_and_carve` | |
| 13.2 #2 carving embedded containers, tail reads, depth limit, JSON report | CONFORMS | `viwo/plugins/godot/pck.py:30` (`embedded_chunk` from the tail), `viwo/plugins/godot/__init__.py:74`; `viwo/core/pipeline/unpack.py:17,58-60`; run records per run; `tests/test_godot.py::test_standalone_and_embedded` | entropy check is the survey density estimate (`viwo/core/survey.py:61`) |
| 13.2 #3 declarative custom formats (Kaitai `.ksy` + QuickBMS) | NOT IMPLEMENTED (deferred, documented) | QuickBMS yes (`viwo/plugins/quickbms/`); no Kaitai anywhere in `viwo/`; doc 13.3 coverage table lists "Kaitai declarative formats" as not shipped, D5 "declarative form later" | |
| 13.2 #4 sanitizer flows with typed outputs, version gating, worker pools | NOT IMPLEMENTED (deferred, documented) | one recipe `viwo/core/sanitizer.py:27-33`; rule providers `viwo/core/sanitizer_rules.py`; doc 16 M13+ lists "sanitizer P2-3" as open | |
| 13.2 #5 plugin discovery through entry points | CONFORMS | `viwo/core/wiring/registry.py:29,215` (`viwo.plugins` group) | |
| 13.3 Ren'Py: no in-process unpickling of untrusted pickles; unrpyc for `.rpyc`; unrpa spare pinned | CONFORMS | `viwo/plugins/renpy/rpa.py:36-40,107`; `viwo/plugins/renpy/decompile.py:21-25` (`decode.rpyc`, unrpyc subprocess); `tests/test_renpy.py::test_rpyc_files_are_decompiled_with_provenance` | rpycdec spare listed as not shipped in the coverage table |
| 13.3 Unity slots (bundle, webgl, export, project, il2cpp) | CONFORMS | shipped per the coverage table: `viwo/plugins/unity/__init__.py:35-44` (`export.unity` UnityPy/AssetStudioModCLI, `pack.unity`); UABEA, AssetRipper, Cpp2IL listed as not shipped | partial by design, documented in the 1.1 coverage table |
| 13.3 Unreal: repak main with QuickBMS spare, retoc, `keys.unreal-aes` user-first | CONFORMS | `viwo/plugins/unreal/__init__.py:40-48` (`unarchive.upak` repak-cli / quickbms-cli spare; `unarchive.utoc` retoc); `viwo/plugins/unreal/keys.py:91-108` | CUE4Parse wrapper, UAssetGUI, locres listed as not shipped |
| 13.3 Godot: GDRE main, GodotPckTool spare, embedded PCK carving, `.stex/.ctex` | CONFORMS | `viwo/plugins/godot/__init__.py:48,86`; `tests/test_godot.py::test_embedded_and_failover`, `::test_encrypted_needs_key_and_spare_is_not_tried`; `tests/test_l5_tools.py::RealGodotToolsTest` | GodotPckTool Windows build quarantined by Defender (STATUS) |
| 13.3 engines ranked after the prototype | CONFORMS | delivered: `viwo/plugins/rpgmaker`, `electron` (`.nw` as zip: `viwo/plugins/electron/__init__.py:3`), `kirikiri`, `source`, `bethesda`; the coverage table names GameMaker, TyranoScript, Love2D, Wolf, XNA, AGS, Defold as not shipped | partial by design, documented |
| 13.3 wrapper plugins: detection reruns once inside an unpacked wrapper (1.1 note: tested in `tests/test_conformance_kit.py`, `tests/test_mixed.py`) | CONFORMS | `viwo/core/pipeline/export.py:27-51`, `viwo/core/pipeline/runner.py` (`rewrap` after UNPACK); `tests/test_formats.py::test_engine_inside_an_asar_is_redetected` (RPG Maker MV inside an asar is re-detected and exported); doc 13.3 note points at that test |  |
| 13.3 "Coverage shipped in 1.1" table (per-row claims) | CONFORMS | unrpyc `viwo/plugins/renpy/decompile.py:15-25`; meshes to OBJ `tests/test_unity.py::test_meshes_option_off_skips_obj_everywhere`; retoc `viwo/plugins/unreal/__init__.py:48`; lz4 pin `pyproject.toml:19`; DataTool, RenderDoc, QuickBMS pins in `viwo/data/tools.json`; streams `viwo/core/carve/streams.py:14-17` | |
| 13.4 code RE tools (Ghidra, ilspycmd, Cpp2IL) | NOT IMPLEMENTED (deferred, documented) | no `analysis.*` slot in `viwo/`; coverage table "Code RE: Ghidra, ilspycmd (analysis rung)"; doc 16 M13+ "analysis backends" open; `docs/HANDOFF.md:89` | |
| 13.5 vendoring facts: GPL backend is always a subprocess; heavy runtimes pinned | CONFORMS | `tests/test_l0_static.py:112-115`; `tests/test_conformance_kit.py:61-62`; .NET runtime `viwo/data/tools.json:193-210` | JDK not needed yet |
| 13.6 Windows-only tools through Wine on Linux (out of scope for the prototype) | NOT IMPLEMENTED (deferred, documented) | no Wine handling in `viwo/os/linux.py`; doc 16 M13+ lists "Wine" as open | |

Verdict: 17 clauses: CONFORMS 12 · NOT IMPLEMENTED (deferred, documented) 4 (Kaitai, sanitizer P2-3, analysis rung, Wine) · DEVIATES (defect) 1 (wrapper re-detection has code but not the tests the doc names) · undocumented gaps 0.
Open: 13.2 #3 declarative custom formats (Kaitai `.ksy` + QuickBMS) (deferred) · 13.2 #4 sanitizer flows with typed outputs, version gating, worker pools (deferred) · 13.4 code RE tools (Ghidra, ilspycmd, Cpp2IL) (deferred) · 13.6 Windows-only tools through Wine on Linux (out of scope for the prot (deferred).

## 3. doc 15: LoC caps

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 15.1 #1 format first (`ruff format`, 100 cols); a line over 100 is itself a cap failure | CONFORMS | `tools/loc_count.py:75-77`; `.github/workflows/ci.yml:27-32`; `tools/version.py:26-30` (format before the counter) | |
| 15.1 #2 tokenize-based count, multi-line strings count, docstrings excluded | CONFORMS | `tools/loc_count.py:20-21,25-43` | |
| 15.1 #3 JS/CSS/HTML non-blank non-comment lines | CONFORMS | `tools/loc_count.py:81-83` | |
| 15.1 #4 other glue languages: none exist | CONFORMS | no `.cs` or other wrapper sources in the tree; CUE4Parse wrapper deferred (doc 13) | |
| 15.1 #5 counted trees `viwo/`, `tests/`, `tools/`; excluded third_party, indexes, examples, sqc/fixtures, packaging, docs, data | CONFORMS | `tools/loc_count.py:115-116` (only the three trees walked) | |
| 15.1 #6 counter split: `loc_count.py` ≤ 120, `caps_ini.py` ≤ 120, both under `tools` | CONFORMS | measured with the counter's own rule: `tools/loc_count.py` 113, `tools/caps_ini.py` 88; `loc_caps.ini:24` (`tools = 600`, 571 used) | |
| 15.3 granularity caps: function 40, class 200, file 250, contracts file 150, params 6 (not for tests), line 100 | CONFORMS | `loc_caps.ini:4-12`; `tools/loc_count.py:57-77` (`params` skipped when `test`); `tests/test_pipeline.py::test_loc_caps` | |
| 15.3 budget table: `viwo` 9,800, `viwo/contracts` 900, `viwo/os` 900, `viwo/core` 4,700, `viwo/backends` 600 | CONFORMS | doc 15.3 revised to the `loc_caps.ini` values (`viwo` 10,800, `viwo/core` 5,400) with the 1.2 reasons |  |
| 15.3 hard ceiling 10,000 for the whole product (also 15.6 "total cap (10k)") | CONFORMS | doc 15.3 and 15.6 revised: the `viwo` budget line is the ceiling (10,800 since 1.2; draft 3 said 10,000) | the product counts 10,499 (`tools/loc_count.py --report`) |
| 15.3 per-plugin budgets: generic 100, unity 700, renpy/godot/unreal 500, the rest 200-300 | CONFORMS | `loc_caps.ini:21-33`; all within budget in the report (largest: doom 280/300, unreal 371/500) | |
| 15.3 `viwo/cli.py` 400, `tools` 600; `viwo/api` bounded by the product total | CONFORMS | `loc_caps.ini:34-35`; report 140/400 and 571/600; no `viwo/api` line | |
| 15.3 web: JS module ≤ 300, `viwo/web` 5,400, nothing ratcheted | CONFORMS | `loc_caps.ini:41-43`; `tools/loc_count.py:86-102`; report 4,664/5,400 | |
| 15.4 test caps: file 400, function 60; fixtures inside test files | CONFORMS | `loc_caps.ini:11-12`; `tools/loc_count.py:57,65`; builders live in `tests/helpers.py`, `tests/test_formats.py:20-117` etc. | |
| 15.4 floor enforced: tests ≥ 0.6 × (contracts + core), about 0.9 | CONFORMS | `tools/loc_count.py:22,127-129`; report 5,060 / 3,505 (ratio 0.87) | |
| 15.5 exceptions in `loc_caps.ini`: raise the file cap of one path, max 3 active, version expiry vs `viwo.__version__`, milestone names reviewed | CONFORMS | `tools/caps_ini.py:23-25,44-46,57-61,74-79,109-113`; `tools/loc_count.py:60,106-108`; `tests/test_l0_static.py::CapsIniSchemaTests::test_schema_problems_and_exception_expiry` | was an undocumented gap at 1.1 |
| 15.5 caps file validated: unknown sections/keys, non-integers, malformed exception line, missing cap are L0 failures | CONFORMS | `tools/caps_ini.py:88-102`; `tests/test_l0_static.py::CapsIniSchemaTests::test_repository_caps_file_is_valid` | |
| 15.5 ratchets: none; `[web]` and `[budgets]` are hard caps | CONFORMS | `tools/loc_count.py:100-101,124-126` (hard failures, no ratchet code) | |
| 15.5 raising a budget: reason on the line, and the commit that raises it names the budget in its message | CONFORMS | doc 15.5 revised: the reason on the budget line is the record; a commit whose point is the raise names it |  |

Verdict: 18 clauses: CONFORMS 15 · DEVIATES (defect) 3 (budget table lags the 1.2 raise, 10,000 ceiling exceeded, raise not named in the commit) · intentional 0 · deferred 0 · undocumented gaps 0. The exceptions/expiry/schema machinery missing at 1.1 is built and tested; the counter is 113 lines.
Open: none.

## 4. doc 16: roadmap exit criteria

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 16.0 Prototype B composition (M7-M11 inside B; A extended first) | CONFORMS | `docs/prototype-b/STATUS.md` milestone table; plugins in `viwo/plugins/`, `viwo/core/roundtrip.py`, `viwo/core/capture/` | |
| 16.0b rungs 1-3, 5-7 and the survey | CONFORMS | rung 2 `viwo/core/pipeline/unpack.py:17,58`; rung 3 `viwo/core/carve/formats.py`; rung 5 `viwo/core/decode.py:26-31`; rung 6 `viwo/plugins/quickbms/__init__.py:42`; rung 7 `viwo/core/capture/`; survey `viwo/core/survey.py:197`; `tests/test_carve.py`, `tests/test_decode.py`, `tests/test_survey.py` | QuickBMS flags unverified on a binary (STATUS) |
| 16.0b rung 4: zlib/gzip always; zstd/LZ4 when the modules are present | CONFORMS | `viwo/core/carve/streams.py:14-17,37-57`; `tests/test_carve.py::OptionalStreamTests::test_lz4_frame_is_inflated_when_the_module_is_present`, `::test_zstd_frame_is_inflated_when_the_module_is_present`, `::test_missing_optional_module_only_drops_that_kind` | was an undocumented gap at 1.1 |
| 16.0b out of scope by design: DRM/anti-cheat circumvention, guessing keys, server content | CONFORMS | `viwo/plugins/unreal/keys.py:1-2` ("Nothing is guessed"); `viwo/plugins/kirikiri` leaves ciphered entries (`tests/test_formats.py:190-191`); no circumvention code in `viwo/` | consistent with D21/D22 |
| M0 decisions, glossary, caps agreed | CONFORMS | README decision table closed (D0-D22) | |
| M1 hotfix + L2 characterization + counter ≤ 120 + CI | DEVIATES (intentional, documented) | counter 113 lines; CI `.github/workflows/ci.yml`; L2 golden files never produced, replaced by removing v1 (clause note, doc 17.1 #3) | exit criterion "golden files committed" consciously dropped |
| M2 contracts + OS layers, conformance kit, F4/F13 gone | CONFORMS | `viwo/contracts/` (672 LoC), `viwo/os/`; `tests/test_conformance_kit.py` (manifest, detect purity, ownership, sandbox, locate), `tests/test_os_layer.py` | the kit covers built-ins only (see doc 17 L1) |
| M3 lean core + CLI (ini, binder, stage runner, workspace, jobs, run records, envelope, CLI, generic, core backends) | CONFORMS | `viwo/core/wiring/`, `viwo/core/pipeline/runner.py`, `viwo/core/workspace.py`, `viwo/core/jobs.py`, `viwo/cli.py`; `tests/test_pipeline.py::test_info_extract_and_exit_codes`, `tests/test_core_units.py::test_failover_outcomes` (`.7z` failover) | |
| M4 Ren'Py (safe RPA main, unrpa spare, malicious-RPA test, L5 unrpa) | CONFORMS | `viwo/plugins/renpy/`; `tests/test_renpy.py::test_malicious_index_never_runs`, `::test_unrpa_extracts_fixture` | |
| M5 Unity (UnityPy ↔ AssetStudioModCLI per D7, placeholders gone, L5) | CONFORMS | `viwo/plugins/unity/__init__.py:43`; `tests/test_unity.py`; `tests/test_l5_tools.py::AssetStudioModTest`, `::UnityPyRobustnessTest` | real-file round trip is an L7 item (clause note, STATUS) |
| M6 Godot (PCK v1-v4, carving, GDRE → GodotPckTool, key option) ★A | CONFORMS | `viwo/plugins/godot/pck.py:12,30`; `tests/test_godot.py`; `tests/test_l5_tools.py::RealGodotToolsTest` | |
| M7 Unreal unpack: repak → QuickBMS spare, retoc, AES option (State note: "repak as main and no spare") | CONFORMS | doc 16 M7 note revised: repak main, `quickbms-cli` spare when the quickbms plugin is on; `viwo/plugins/unreal/__init__.py:40-47` |  |
| M8 custom plugins: out-of-tree loader, entry points, showcase, Overwatch, CATALOG per D12 | CONFORMS | `viwo/core/wiring/registry.py:204-215`; `examples/plugins/hello/`; `tests/test_registry.py::test_end_to_end_extraction_through_a_dropin` (conformance from outside the tree); Doom/Overwatch plugins; CATALOG closed (D12) | |
| M9 round trip: provenance edit set, per-plugin plan, patched copy, pack slots, verification, untouched hashes | CONFORMS | `viwo/core/roundtrip.py:28,40,54,132-140,197` (edit set, untouched member hashes, verification); `pack.*` slots in each plugin; `tests/test_roundtrip.py`, `tests/test_l5_tools.py::RealRoundTripTest` | plain copy instead of copy-on-write clones (clause note) |
| M10 mixed + sanitizer P1, product ≤ 9,000 ★B (note: became the 9,800 budget) | DEVIATES (intentional, documented) | mixed `tests/test_mixed.py`; sanitizer `viwo/core/sanitizer.py`; product 10,499 against `loc_caps.ini:16` 10,800 | the note's "9,800" is itself stale after 1.2 (see doc 15 rows) |
| M11 capture pilot: policy + refusal list, journal, RenderDoc → harvest → DIFF | DEVIATES (intentional, documented) | refusal list became warnings (`viwo/core/capture/policy.py:1-6`); journal and diff `tests/test_capture.py::test_restore_and_crash_recovery`, `::test_capture_harvest_gather_diff` | RenderDoc on a real GPU is an L7 item (STATUS) |
| M12 vendoring: tool lock → sparse submodules, bootstrap, nightly L5; exit `viwo install --all` → `viwo slots --check` green | DEVIATES (intentional, documented) | installer instead of submodules: `viwo/data/tools.json`, `viwo/core/thirdparty.py`; `viwo slots --check`: `viwo/cli.py:68`, `viwo/cli_check.py:25-44`; CI real-tools job `.github/workflows/ci.yml:46-78` (no nightly, cost rule) | indexes as a submodule per `docs/indexes.md` |
| M13+ shipped: distro layering + 12 ini, RPG Maker, Electron, UI option forms, run history, sanitizer panel, add-ons; open: `[hooks]`, GameMaker, Unreal export, sanitizer P2-3, analysis, Wine | CONFORMS | `distros/` (12), `tests/test_config.py::test_base_layering`; `viwo/plugins/rpgmaker`, `electron`; `viwo/api/plugin_assets.py`; `[hooks]` absent from `viwo/core/wiring/ini.py:13` (`STARTUP_KEYS`) as the clause states | open items named in the clause |
| 16.3 decision gates G0-G6 | CONFORMS | every gate's decision recorded in the README table | |
| 16.4 risks: pins + spares + `viwo slots --check` (backend self-tests) | CONFORMS | `viwo/contracts/slots.py:73-86` (`self_check`), `viwo/cli_check.py:15-44`, `viwo/cli.py:68,163`; pins `viwo/data/tools.json` | no unit test calls `slots_check` or `self_check` (grep: none under `tests/`); covered only by `viwo slots` in the CI real-tools job (`ci.yml:60`) |

Verdict: 20 clauses: CONFORMS 15 · DEVIATES (intentional, documented) 4 (M1, M10, M11, M12) · DEVIATES (defect) 1 (M7 note contradicts the shipped QuickBMS spare) · deferred 0 · undocumented gaps 0. The three 1.1 gaps (conformance kit, zstd/LZ4 rung, `slots --check`) are closed.
Open: M1 hotfix + L2 characterization + counter ≤ 120 + CI (intentional) · M10 mixed + sanitizer P1, product ≤ 9,000 ★B (note: became the 9,800 bud (intentional) · M11 capture pilot: policy + refusal list, journal, RenderDoc → harvest → (intentional) · M12 vendoring: tool lock → sparse submodules, bootstrap, nightly L5; exi (intentional).

## 5. doc 17: testing model

| Clause | Status | Evidence | Note |
|---|---|---|---|
| 17.1 #1 no real game data in repo/CI; synthetic fixtures; Freedoom only in the real-tools job | CONFORMS | `tests/helpers.py:44-82`; `.github/workflows/ci.yml:62-69`; `git ls-files tests` holds only `.py`/`.mjs` | |
| 17.1 #2 fakes before real tools; real tools from `third_party/` or `VIWO_<ID>`, skip with the tool named | CONFORMS | `tests/test_l5_tools.py:33-47` (`tool()`, `need()`); `tests/test_godot.py` `fake_tools` pattern | |
| 17.1 #3 v1 removed, not characterized; L1-L4 cover the intended behaviour | CONFORMS | no `RPy-extractor/` in the tree; `docs/prototype-a/STATUS.md` | doc revised (was an intentional deviation at 1.1) |
| 17.1 #4 every contract rule has a test (single writer, reserved dot-folders, routing, failover, determinism, warnings policy, import direction, licence isolation, declared network use) | CONFORMS | `tests/test_game_integrity.py`, `tests/test_core_units.py::test_ownership_and_policies`, `tests/test_mixed.py`, `tests/test_core_units.py::test_failover_outcomes`, `tests/test_pipeline.py::test_replay_reproduces_the_workspace`, `tests/test_capture.py::test_feature_switch_confirmation_and_warnings`, `tests/test_l0_static.py` (all three new rules) | |
| 17.1 #5 safety tested, not assumed | CONFORMS | 17.3 rows below; three catalogue rows lack their test (see those rows) | |
| L0 `ruff format --check`, `ruff check`, LoC caps on every CI run, Linux + Windows, blocking | CONFORMS | `.github/workflows/ci.yml:17-32`; `tests/test_pipeline.py::test_loc_caps`; `tools/version.py:26-31` locally | |
| L0 import-direction lint | CONFORMS | `tests/test_l0_static.py:23-30,77-108` | two recorded debts (`viwo/backends/__init__.py` → core carver/ffmpeg) are listed in the test, not in doc 17.2 |
| L0 GPL/AGPL ⇒ `isolation="subprocess"` | CONFORMS | `tests/test_l0_static.py:112-115`; `viwo/contracts/slots.py:58` | |
| L0 every backend declares `network` and `parses_untrusted_in_process` | CONFORMS | `viwo/contracts/slots.py:59-60`; `tests/test_l0_static.py:117-121`; `tests/test_conformance_kit.py:60` | |
| L0 schema validation of `distros/*.ini` | CONFORMS | `tests/test_config.py::test_strict_rules`, `::test_shipped_distros_match_the_generator`; `viwo config check` | |
| L0 schema validation of `loc_caps.ini` | CONFORMS | `tests/test_l0_static.py::CapsIniSchemaTests` | |
| L1 conformance kit for plugins, slots and backends, runnable by third-party plugins through `custom_dirs` | CONFORMS | `tests/test_conformance_kit.py:26` (`every_plugin`: built-ins, `examples/plugins`, every folder in `VIWO_PLUGIN_DIRS`); doc 17 L1 row revised | a third-party plugin runs the kit against its own folder |
| L1 OS layers, routing, ini precedence, identify/carve rules, value types, journal | CONFORMS | `tests/test_os_layer.py`, `tests/test_mixed.py`, `tests/test_config.py`, `tests/test_core_units.py::test_suffix_magic_custom_and_carve`, `tests/test_capture.py::JournalTests` | |
| L2 characterization: dropped | CONFORMS | no golden files; doc revised (17.1 #3) | was deferred at 1.1 |
| L3 component: one `test_<engine>.py` per plugin, `test_formats.py` for single-container engines | CONFORMS | `tests/test_renpy.py`, `test_unity.py`, `test_godot.py`, `test_unreal.py`, `test_doom.py`, `test_rpgmaker.py`, `test_quickbms.py`, `test_overwatch.py`, `test_formats.py` (asar, VPK, XP3, BSA, BA2) | |
| L4 (a) exhaustive selection × policy + pairwise pipeline runs | CONFORMS | `tests/test_core_units.py::test_every_combination`; `tests/test_mixed.py::test_pairs_and_singles` | |
| L4 (b) slot failover: every outcome kind through main and spare; binder states main-up/down × spare-up/down | CONFORMS | `tests/test_core_units.py::test_failover_outcomes`, `::test_four_availability_cases`; `tests/test_godot.py::test_encrypted_needs_key_and_spare_is_not_tried` | doc revised to the implemented matrix |
| L5 real-tool smoke: tools from `third_party/` (CI runs `viwo install --all`) or `VIWO_<ID>`; skip names the install command | CONFORMS | `tests/test_l5_tools.py:27-47` (`thirdparty.found_tools(HOME)` + env override); `.github/workflows/ci.yml:53-60,70-74`; `tests/test_l5_data.py:21-34` | the 1.1 defect (env vars nothing exported) is fixed |
| L6 CLI: `info`/`detect`/`extract` → run record → identical re-run | CONFORMS | `tests/test_pipeline.py::test_replay_reproduces_the_workspace`, `::test_info_extract_and_exit_codes`; `tests/test_cli.py` | |
| L6 HTTP routes through the job adapter | CONFORMS | `tests/test_server.py::test_extract_curate_and_jobs`, `tests/test_api_routes.py`, `tests/test_api_capture.py`, `tests/test_settings.py` | |
| L6 web UI smoke in a real browser (every view, extraction, cleanup, settings apply, SORT keys, theme) + UI style lint | CONFORMS | `tests/test_ui_smoke.py:41` (`VIWO_UI=0` skip), `tests/ui/smoke.mjs:56-122` (steps landing, view:*, toast, system, settings, extract, sort, cleanup); `tests/test_ui_lint.py` | |
| L7 manual acceptance: `sqc/` 147 checks, P0 subset, `tools/integration_games.py`, at each milestone exit by the owner | NOT IMPLEMENTED (deferred, documented) | `sqc/01..15-*.md` (11+9+8+22+10+8+11+6+8+7+7+12+13+9+6 = 147 checks, 88 P0 marks), `sqc/games.md`, `tools/integration_games.py`; STATUS "Not verified yet" table still open | owner's sign-off, not run yet (same as D20) |
| 17.3 zip/tar member with `../` or absolute path | CONFORMS | `tests/helpers.py:62-69` (`../escape.txt` in the tar), `tests/test_pipeline.py::test_extract_keeps_game_untouched_and_blocks_traversal`; `tests/test_formats.py:161,169` (asar `../x.txt`); `tests/test_renpy.py::test_versions_prefix_and_traversal` | |
| 17.3 symlink inside an archive pointing outside (Where: `test_pipeline.py`, `test_conformance_kit.py`) | CONFORMS | `tests/test_pipeline.py::test_tar_links_and_devices_are_never_written` (symlink, hard link and device members filtered; `viwo/backends/archives.py:36-46`); zip entries are always written as plain files |  |
| 17.3 RPA with a `__reduce__` payload: no code runs | CONFORMS | `tests/test_renpy.py::test_malicious_index_never_runs`; `viwo/plugins/renpy/rpa.py:36-40` | |
| 17.3 `.rpyc` never unpickled in process (unrpyc subprocess) | CONFORMS | `viwo/plugins/renpy/decompile.py:1-2,25`; `tests/test_renpy.py:141-147` (`fake_unrpyc`), `::test_rpyc_files_are_decompiled_with_provenance` | |
| 17.3 nesting depth bomb stops at 10, reported (Where: `test_pipeline.py`) | CONFORMS | `tests/test_pipeline.py::test_nesting_deeper_than_ten_is_reported` (13 nested zips: "nesting deeper than 10" reported, run succeeds); `viwo/core/pipeline/unpack.py:17,58-60` |  |
| 17.3 decompression bomb bounded (`LIMIT`, `TOTAL`, `max_length`) (Where: `test_carve.py`) | CONFORMS | `tests/test_carve.py::StreamBoundTests` (a stream inflating past `LIMIT` is dropped); `viwo/core/carve/streams.py:19-22,66,73` |  |
| 17.3 a plugin hook writing outside its staging folder fails the kit's sandbox check | CONFORMS | `tests/test_conformance_kit.py::SandboxTests::test_export_writes_only_inside_staging_and_scratch`; `tests/test_game_integrity.py::test_a_backend_writing_into_the_game_is_reported` | |
| 17.3 PREPARE on a folder without the marker: refused, nothing deleted (Where: `test_game_integrity.py`) | CONFORMS | `viwo/core/workspace.py:101-109`; `tests/test_core_units.py::test_ownership_and_policies` (`keep.txt` survives, code `refused`) | the Where column should name `tests/test_core_units.py`; `test_game_integrity.py` tests the workspace-inside-game refusal instead |
| 17.3 game folder hashes unchanged before vs after | CONFORMS | `tests/test_game_integrity.py::test_every_plugin_leaves_the_game_untouched`; `tree_hashes` assertions in every plugin test (`tests/test_formats.py:151`, `tests/test_mixed.py:85`) | |
| 17.3 cross-origin POST, missing token, non-JSON, foreign Host, oversized body → 403/415/413 | CONFORMS | `viwo/api/server.py:106-132`; `tests/test_server.py::test_security_model` | |
| 17.3 tar member with `..`, absolute path, device file, or link outside (Where: `test_pipeline.py`) | CONFORMS | `tests/test_pipeline.py::test_tar_links_and_devices_are_never_written`, `tests/test_pipeline.py::test_extract_keeps_game_untouched_and_blocks_traversal` (`..` member) |  |
| 17.3 capture session killed midway: next start restores; damaged journal restores what it can | CONFORMS | `tests/test_capture.py::test_restore_and_crash_recovery`, `::test_damaged_journal_restores_what_it_can` | |
| 17.3 anti-cheat markers / online title / sensitive plugin: warnings + one confirmation, never a refusal | CONFORMS | `tests/test_capture.py::test_feature_switch_confirmation_and_warnings` (`tests/test_capture.py:49-73`) | |
| 17.3 `/preview/` and `/api/*` traversal → 404 | CONFORMS | `tests/test_server.py:126` (`/preview/..%2f..%2fstartup.ini` → 404), `::test_game_folder_and_unknown_routes`; `viwo/api/server.py:141` | |
| 17.4 fixture builders as listed | CONFORMS | `tests/helpers.py:44,52,62,82` (`make_zip/tar/game/rar`); `tests/test_renpy.py:26` (`make_rpa`); `tests/test_godot.py:40,44` (`make_pck`, `embed`); `tests/test_unreal.py:44,55` (`make_pak`, `key_exe`); `tests/test_unity.py:43` (`fake_unitypy`); `tests/test_doom.py:23`, `tests/test_rpgmaker.py:22,37,51`, `tests/test_formats.py:20,35,49,75,94`; `tests/test_mixed.py:40-58` | |
| 17.4 fixtures generated at test time; no binary fixture committed | CONFORMS | `git ls-files tests` lists only `.py` and `.mjs` files | |
| 17.4b tos-sensitive: `tos_sensitive=True` manifest, CI fake-only, operator receives/returns, no policies in code, evidence under `docs/evidence/` | CONFORMS | `viwo/contracts/plugin.py:46`, `viwo/plugins/overwatch/__init__.py:54`; `tests/test_overwatch.py` (fake DataTool); `sqc/00-README.md`, `sqc/04-extraction-per-engine.md` OPERATOR marks; `viwo/core/roundtrip.py:96-99` reminder only | `docs/evidence/` does not exist yet because no operator report has been returned |
| 17.5 Python 3.11 minimum; CI 3.11 and 3.13 | CONFORMS | `pyproject.toml:10`; `.github/workflows/ci.yml:19-22` | |
| 17.5 runner: stdlib `unittest`; levels by env vars (`VIWO_L5`, `VIWO_UI`, `VIWO_FREEDOOM`) | CONFORMS | `tests/test_l5_tools.py:23`, `tests/test_ui_smoke.py:41`, `tests/test_l5_data.py:23`; `tools/version.py:30` | doc revised (pytest/markers dropped) |
| 17.5 CI: two OSes × 3.11/3.13 for L0-L4/L6; real-tools job with `viwo install --all` and `VIWO_L5=1`; only on `vN.0.0` tags or by hand; no nightly | CONFORMS | `.github/workflows/ci.yml:7-9,17-22,46-78` | doc revised to the cost rule |
| 17.5 coverage floors: `coverage` on the L0-L4 suite in CI, `tools/coverage_check.py` fails below the floor, floors only move up | CONFORMS | `.github/workflows/ci.yml:33-42`; `tools/coverage_check.py:15-21,35-44` (contracts 90, core 86, plugins 80, os 60, viwo 75) | was an undocumented gap at 1.1; the floors cannot be re-measured in a read-only audit |
| 17.5 speed budget: L0-L4 + CLI/HTTP under 3 min per OS; browser smoke about 2 min | CONFORMS | 1.1 measurement 55-80 s without the browser smoke, 236 s with it (CONFORMANCE.md 1.1 row); `CLAUDE.md` "~30 s" for the non-browser suite | not re-measured (the full suite was not run in this audit) |
| 17.6 definition of done #1-#4 (green on both OSes, caps, safety tests, L7 per engine) | CONFORMS | Windows green locally before every commit (`tools/version.py:26-31,96-100`); Linux CI last proven at run 41426550274 (STATUS "Evidence"); caps green (`tools/loc_count.py --report`); L7 pending (see L7 row) | partial: Linux not re-run on CI since 1.0 (cost rule), L7 pending the owner |
| 17.6 definition of done #5: contract changes with a History line; `docs/contract/CONFORMANCE.md` regenerated | CONFORMS | this file regenerated from the v1.2.0 re-audit plus the 1.2.1 closure; every revised doc carries a History line |  |

Verdict: 46 clauses: CONFORMS 39 · DEVIATES (defect) 6 (conformance kit built-ins only; no symlink/link/device archive test; no depth-bomb test; no decompression-bound test; CONFORMANCE.md not regenerated; the tar device/link row shares the symlink fix) · intentional 0 · NOT IMPLEMENTED (deferred, documented) 1 (L7, owner) · undocumented gaps 0. The six 1.1 gaps (import lint, GPL lint, network declarations, caps-ini schema, coverage floors) and the L5 tool-lookup defect are closed; what remains is three catalogue rows whose named tests do not exist, the kit's third-party claim, and the stale conformance record.
Open: L7 manual acceptance: `sqc/` 147 checks, P0 subset, `tools/integration_g (deferred).

## Counts per status

| Doc | CONFORMS | DEVIATES (defect) | DEVIATES (intentional, documented) | NOT IMPLEMENTED (deferred, documented) | NOT IMPLEMENTED (undocumented gap) |
|---|---|---|---|---|---|
| 1. docs/contract/README.md: decisions D0..D22, principles, goals, layer rule, distro model | 35 | 0 | 2 | 1 | 0 |
| 2. doc 13: landscape coverage | 13 | 0 | 0 | 4 | 0 |
| 3. doc 15: LoC caps | 18 | 0 | 0 | 0 | 0 |
| 4. doc 16: roadmap exit criteria | 16 | 0 | 4 | 0 | 0 |
| 5. doc 17: testing model | 45 | 0 | 0 | 1 | 0 |
| Total | 127 | 0 | 6 | 6 | 0 |
