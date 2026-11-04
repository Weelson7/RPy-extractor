# Contract conformance (1.6.2)

Every normative item of the contract documents, by section, with its state against the code at
v1.6.2: **implemented** (with the module or function), **partial** (what is missing), **open**
(not implemented). Paths are relative to `viwo/` unless they start with `tests/`, `tools/` or a
top-level folder. Update a row in the commit that changes its state.

## Summary

| State | Rows |
|-------|------|
| implemented | 165 |
| partial | 5 |
| open | 16 |
| total | 186 |

**Partial**, by cause: no built-in plugin keeps an inventory (0.4, 2.2); no built-in plugin
ships sanitizer rules (5.1); no pinned QuickBMS script in the indexes (16.0b); coverage per file (17.5).

**Open:** the completeness contract per engine (16.0c); rung D4 (`hook.inject`, `hook.overlay`, `net.*`); sanitizer phases
2-3; `[slot_policy]`; `[hooks]`; `--plugin`/`--slot` CLI overrides; `memory_image` targets;
`keys.*` slots; asset converters for round trip; Unreal asset export and the engines of 13.7;
declarative (Kaitai) plugins; the indexes repository split.

## README (principles, layers, decisions)

| Item | State | Where / missing |
|------|-------|-----------------|
| P1 game folder read-only; copy, move only from staging | implemented | `core/pipeline/collect.py`, `core/pipeline/guard.py` |
| P2 authenticated local API | implemented | `api/server.py` |
| P3 OS code only in the OS layer | implemented | one exception recorded: `core/thirdparty.py` runs `msiexec`; the game's Oodle DLL loads through `OS.load_native` |
| P4 every engine behind a slot | implemented | `contracts/slots.py`, `core/wiring/binder.py` |
| P5 failures isolated per plugin/backend | implemented | `core/pipeline/export.py`, `core/pipeline/failover.py` |
| P6 plan, apply, undo for bulk actions | implemented | `core/sanitizer.py`, `core/curation/trash.py` |
| P7 reserved dot-folders | implemented | `contracts/workspace.py` `is_reserved` |
| P8 determinism and replay | implemented | `core/records.py`, `viwo replay`; `tests/test_pipeline.py` |
| P9 honest metrics | implemented | `contracts/pipeline.py` |
| P10 never silent | implemented | `Outcome.fallback` (`core/pipeline/failover.py`), `cli.py` warnings |
| layer import rule | implemented | `tests/test_l0_static.py` (no recorded debt) |
| D22 warnings, never refusals | implemented | `core/capture/policy.py`, `core/roundtrip.py` `_reminders`, plugin `REMINDER` |
| distros: 12 generated files | implemented | `core/wiring/distros.py`, `distros/`, `tests/test_config.py` |

## 00 Glossary

| Item | State | Where / missing |
|------|-------|-----------------|
| 0.2 OS layer, plugin, profile, distro, core, arm | implemented | `os/`, `contracts/plugin.py`, `core/wiring/distros.py`, `cli_arms.py` |
| 0.2 job, run record, stage, slot, backend, main/spare, promoted, fallback | implemented | `core/jobs.py`, `core/records.py`, `contracts/pipeline.py` `Stage`, `contracts/slots.py` |
| 0.2 features `extraction`, `sorting`, `merger` | implemented | `core/context.py` `require`: extraction (runner, `viwo unpack`), sorting and merger routes (`api/handlers.py` `gated`); `tests/test_switches.py` |
| 0.2 features `capture`, `analysis` | implemented | `core/capture/policy.py` `check`, `core/capture/runtime.py` `_enabled`, `core/analysis` `_check_enabled` |
| 0.2 pinned tool, worker tool, handoff, runtime agent | implemented | `core/thirdparty.py`, `core/workers.py`, `contracts/analysis.py` `Handoff`, `contracts/runtime.py` |
| 0.2 provenance, edit set, patched copy, patch set, mod | implemented | `core/provenance.py`, `core/roundtrip_edits.py`, `core/roundtrip.py`, `core/patchsets.py`, `core/mods.py` |
| 0.4 result keys and meanings | implemented | `contracts/pipeline.py` `to_legacy_dict` |
| 0.4 `inventoryItems`, `collectedFromInventory` | partial | computed from `inventory()`, which no built-in plugin implements, so both are 0 for built-ins |

## 01 OS layer

| Item | State | Where / missing |
|------|-------|-----------------|
| OS object (`os_id`, `is_supported_host`, parts) | implemented | `contracts/os.py`, `os/linux.py`, `os/windows.py` |
| homes, scan exclusions, `pids_of`, `dump_process` | implemented | `os/_shared.py`, `os/windows.py`, `os/linux.py` |
| 1.1 run: UTF-8, pump threads, never raises on exit code, tree kill on timeout/cancel | implemented | `os/_shared.py` `SubprocessRunner` |
| 1.1 launch tracked children, killed at exit | implemented | `SubprocessRunner.launch`, `_reap_children` |
| 1.1 max_command_length used by long command lines | implemented | merger build (`core/merger/build.py`) |
| 1.2 locator search order and known dirs | implemented | `os/_shared.py` `Locator`, `os/*.py` `_install_roots`; `core/wiring/boot.py` merges `[tools]` over `third_party/` |
| 1.3 no installation in the OS layer | implemented | `core/thirdparty.py` |
| 1.4 open folder, pickers | implemented | `os/_shared.py` `TkShell`, `os/*.py` shells (tkinter only) |
| 1.5 filename policy, path keys, long paths | implemented | `os/windows.py` `WindowsFs`, `os/linux.py` `PosixFs` |
| 1.6 Toolhelp32 process list, minidump, `/proc` dump | implemented | `os/windows.py` `_processes`, `_minidump`; `os/linux.py` `_proc_dump` |
| 1.7 conformance checks | implemented | `tests/test_os_layer.py` |

## 02 Engine plugins

| Item | State | Where / missing |
|------|-------|-----------------|
| 2.1 manifest fields, option kinds, `option_bool`, secrets masked | implemented | `contracts/plugin.py`; masking in `core/pipeline/runner.py` `_masked_options` |
| 2.1 derived capabilities | implemented | `core/wiring/conformance.py` `capabilities_of` |
| 2.2 hooks with defaults | implemented | `contracts/plugin.py` `EnginePlugin` |
| 2.2 `inventory()` | partial | the hook exists; no built-in plugin implements it |
| 2.2 exceptions recorded against the plugin | implemented | `core/pipeline/export.py`, `core/pipeline/failover.py` |
| 2.3 shared probe, case-preserved paths, cache on size and mtime | implemented | `core/pipeline/probe.py` `FolderProbe` |
| 2.4 detection result and scale | implemented | `contracts/types.py` `DetectionResult` |
| 2.5 recursive unpack, depth 10, slot lookup, member safety | implemented | `core/pipeline/unpack.py`, `core/pipeline/identify.py`, `contracts/workspace.py` |
| 2.6 dependency spec, per-OS executables | implemented | `contracts/types.py` `DependencySpec` |
| 2.7 seventeen built-in plugins | implemented | `plugins/*/` |
| 2.8 built-in scan, drop-ins, entry points, opt-in, override | implemented | `core/wiring/registry.py`, `tests/test_registry.py` |
| 2.9 conformance checks and sandbox | implemented | `core/wiring/conformance.py`, `tests/test_conformance_kit.py` |

## 03 Pipeline

| Item | State | Where / missing |
|------|-------|-----------------|
| 3.1 stage order and events | implemented | `core/pipeline/runner.py` `_stages` (the `Stage` enum lists CARVE before EXPORT; the runner exports first) |
| 3.1 guard: no workspace or temp inside the game | implemented | `core/pipeline/guard.py` `refuse_writes_inside` |
| 3.1 wrapper re-detection | implemented | `core/pipeline/export.py` `rewrap`; `tests/test_formats.py::test_engine_inside_an_asar_is_redetected` |
| 3.1 carve modes and claimed suffixes | implemented | `core/pipeline/carving.py` |
| 3.1 COLLECT copy/move, dedupe by hash, unreadable files named | implemented | `core/pipeline/collect.py` |
| 3.1 DECODE inside COLLECT, `core.decode`, `core.decode_video` | implemented | `core/decode.py` |
| 3.1 run record | implemented | `core/pipeline/runner.py` `_report` |
| 3.2 request and payload mapping | implemented | `contracts/pipeline.py`, `api/app.py` |
| 3.3 selection, unknown ids refused, never empty | implemented | `core/pipeline/select.py` |
| 3.4 mixed mode, suffix clashes, failure isolation | implemented | `core/wiring/conformance.py` `suffix_clashes`, `core/pipeline/export.py` |
| 3.5 result payload | implemented | `contracts/pipeline.py` |
| 3.6 combination tests | implemented | `tests/test_mixed.py` |

## 04 HTTP API and workspace

| Item | State | Where / missing |
|------|-------|-----------------|
| 4.1 legacy and envelope route families, status codes | implemented | `api/handlers*.py`, `api/routes.py` |
| 4.1 route table | implemented | every route the web client calls is served (`api/handlers.py`; `tests/test_api_routes.py` checks `web/js/api.js` against the tables) |
| 4.1 detect dry run, plugins list | implemented | `api/routes.py` `_detect`, `_plugins` |
| 4.1 token, JSON only, size limit, Host check, binding, containment | implemented | `api/server.py`; `tests/test_server.py` |
| 4.2 dependency item | implemented | `core/wiring/boot.py` `dependency_report` |
| 4.3 layout, marker, ownership, re-extraction policy | implemented | `contracts/workspace.py`, `core/workspace.py` |
| 4.3 trash areas and migration, collision names | implemented | `core/curation/trash.py`, `core/curation/sorting.py` |
| 4.3 workspace lock across processes, new-folder lock | implemented | `core/workspace.py` `workspace_lock`, `LOCK_FILE` |
| 4.4 events, line format, daily log, masking | implemented | `contracts/types.py` `ProgressEvent`, `api/app.py`, `web/js/progress.js` |
| 4.5 configuration, secrets off disk | implemented | `core/wiring/ini.py`, `core/pipeline/runner.py` |
| 4.6 UI session, persisted stores | implemented | `api/app.py`, `core/surveys.py` |

## 05 Sanitizer

| Item | State | Where / missing |
|------|-------|-----------------|
| 5.1 phase 1 rules | implemented | `core/sanitizer_rules.py` |
| 5.1 phase 2 (lossless conversions, `.sanitizer/cache/`, `replace`) | open | - |
| 5.1 phase 3 (transcode presets, renumbering) | open | - |
| 5.1 plugin rule providers | partial | `EnginePlugin.sanitizer_rules()` and `collect_rules` work (tested with a test plugin); no built-in plugin ships a rule |
| 5.2 rule model, cost order, batch rule last | implemented | `core/sanitizer_rules.py` |
| 5.2 plan pages, stale plan refused, journal, undo, undoable cancel | implemented | `core/sanitizer.py` |
| 5.3 routes and CLI | implemented | `api/handlers_tools.py`, `cli_extra.py` |

## 06 Static analysis (rungs A1-A4)

| Item | State | Where / missing |
|------|-------|-----------------|
| `analysis` switch, refusal with hint | implemented | `core/analysis/__init__.py` `_check_enabled` |
| 6.1 target and analyzer contracts | implemented | `contracts/analysis.py` |
| 6.1 plugin proposals (generic, unity, unreal, godot, renpy) | implemented | `plugins/*/__init__.py` `analysis_targets` |
| 6.1 extras (`--slot`) | implemented | `core/analysis/__init__.py` `extras_for` |
| 6.2 A1 `analysis.native` Ghidra headless | implemented | `core/analysis/ghidra.py` `GhidraHeadless`, `data/ghidra/ViwoExport.java` |
| 6.2 A2 `analysis.dotnet`, `.il2cpp`, `.script` | implemented | `core/analysis/managed.py` |
| 6.2 A2 `analysis.python`, `.gdscript` | implemented | `plugins/renpy/decompile.py` `UnrpycAnalyzer`, `plugins/godot/gdscript.py` |
| 6.2 A3 `analysis.protector` | implemented | `core/analysis/identify.py` `DetectItEasy` |
| 6.2 A3 signatures | implemented | Ghidra FID inside the headless analysis; no separate slot |
| 6.2 A3 version diff | implemented | `core/analysis/diff.py`, `viwo diff`, `POST /api/analysis/diff`, 12.F VERSION DIFF in 12 ANALYSIS |
| 6.2 A4 `analysis.emulate`, `analysis.symbolic` workers | implemented | `core/analysis/emulate.py`, `core/workers.py`, `data/workers/emulate.py`, `data/workers/symbolic.py` |
| 6.2 `record.json` per run, output emptied before rerun | implemented | `core/analysis/__init__.py` `analyze` |
| 6.3 handoffs per kind | implemented | `core/analysis/__init__.py` `handoffs_for`, `open_in` |
| 6.4 Ghidra project beside the workspace, on-demand pin, first-run answers | implemented | `core/analysis/ghidra.py`, `data/tools.json` |
| 6.5 `memory_image` targets | open | the kind exists; no proposer and no analyzer |
| 6.6 API | implemented | `api/handlers_analysis.py` |

## 07 Data-safety rules

| Item | State | Where / missing |
|------|-------|-----------------|
| every rule of 7.1 | implemented | modules named in 7.1; `tests/test_game_integrity.py`, `tests/test_pipeline.py`, `tests/test_server.py`, `tests/test_renpy.py` |

## 08 Slots and backends

| Item | State | Where / missing |
|------|-------|-----------------|
| 8.1 definitions, declarations, self-check | implemented | `contracts/slots.py` |
| 8.1 dependency-only backends | implemented | `core/capture/runtime.py` `FridaTrace`, `core/capture/audio.py` `LoopbackRecorder` |
| 8.2 failover, outcome kinds, `needs_key` not retried | implemented | `core/pipeline/failover.py`, `contracts/types.py` |
| 8.2 policies other than failover | open | `[slot_policy]` (`main_only`, `supplement`) |
| 8.2 binding, promotion, unbound, bad ini entries | implemented | `core/wiring/binder.py` |
| 8.2 never silent: `Outcome.fallback` in every stage | implemented | `core/pipeline/failover.py`; stages in `core/pipeline/`, `core/analysis/`, `core/capture/` |
| 8.3 interfaces | implemented | `contracts/slots.py`, `contracts/analysis.py`, `contracts/runtime.py`, `core/patch_tools.py` |
| 8.3a handoffs Ghidra, x64dbg, Cheat Engine as tracked children | implemented | `core/analysis/ghidra.py` `GhidraGui`, `core/analysis/handoffs.py` |
| 8.3a first-run answers off screen | implemented | `core/analysis/handoffs.py`, `core/analysis/ghidra.py`, `core/capture/renderdoc.py` |
| 8.4 slot table | implemented | `backends/__init__.py`, `core/*` `SLOTS`, plugin `slot_definitions` (`viwo slots`) |
| 8.5 stage use | implemented | as listed |
| 8.6 slot conformance | implemented | `core/wiring/conformance.py`, `tests/test_core_units.py`, `tests/test_config.py` |

## 09 Startup ini

| Item | State | Where / missing |
|------|-------|-----------------|
| 9.1 one base level, precedence, value sources | implemented | `core/wiring/ini.py` `layers`, `_sources` |
| 9.1 `--os`, `--profile`, `--features` | implemented | `core/wiring/boot.py` `boot`, `_apply_profile` |
| 9.2 sections and keys | implemented | `core/wiring/ini.py` |
| 9.2 `extraction`, `sorting`, `merger` switches | implemented | checked (see 0.2) |
| 9.3 boot sequence, exit codes 2/3/4 | implemented | `core/wiring/boot.py`, `cli.py`, `api/server.py` |
| 9.4 validation, secrets refused, `viwo config check` | implemented | `core/wiring/ini.py`, `core/wiring/distros.py` |
| 9.5 `[slot_policy]` | open | - |
| 9.5 `[hooks]` lifecycle hooks | open | - |
| 9.5 `--plugin <id>=on\|off`, `--slot` CLI overrides | open | - |
| 9.6 `/api/distro`, 11 SETTINGS writes and reloads | implemented | `api/routes.py`, `core/wiring/settings.py`, `api/app.py` `reload` |

## 10 Pinned tools

| Item | State | Where / missing |
|------|-------|-----------------|
| 10.1 pin file: tools, python, workers, on_demand, hidden | implemented | `data/tools.json`, `core/thirdparty.py` |
| 10.1 hash-locked Python pins | implemented | `data/locks/`, `tools/pin_python.py`, `core/thirdparty.py` `pip_install` |
| 10.2 install paths: CLI, 05 SYSTEM, preflight | implemented | `cli_extra.py`, `api/handlers_tools.py`, `core/preflight.py` |
| 10.2 HTTPS, size and sha256, retries, safe unpack, busy folder, antivirus hint | implemented | `core/thirdparty.py` |
| 10.2 worker install into a fresh folder | implemented | `core/workers.py` |
| 10.3 every pin listed | implemented | `data/tools.json`; `THIRD_PARTY_NOTICES.md` (`tools/notices.py`, `tests/test_diag.py`) |
| 10.4 no prompts, no elevation | implemented | Cheat Engine from Scoop's unpacked build; first-run answers (8.3a) |
| 10.5 update check, indexes update | implemented | `core/diag.py`, `core/indexes.py`, `api/handlers_system.py` |

## 11 Dynamic arm (rungs D1-D4)

| Item | State | Where / missing |
|------|-------|-----------------|
| 11.1 `capture` switch for capture, dump, trace, agent, record | implemented | `core/capture/policy.py` `check`, `core/capture/runtime.py` `_enabled` |
| 11.1 confirmation once per game | implemented | `core/capture/policy.py` `remember`, `confirmed_games` |
| 11.1 warnings: markers, services, online titles, sensitive plugins, network | implemented | `core/capture/policy.py` `warnings_for`, `data/capture_policy.json` |
| 11.1 debugger and memory handoffs as dynamic actions | implemented | `core/analysis` `_dynamic`: the `capture` switch, one confirmation per game (`--confirm`, the UI's confirm box), the warnings; x64dbg runs a patched copy |
| 11.2 D1 unattended capture, shader disassembly | implemented | `core/capture/renderdoc.py`, `core/capture/rd_trigger.py`, `core/capture/rd_harvest.py` |
| 11.2 D2 UE4SS and BepInEx agents | implemented | `plugins/unreal/agent.py`, `plugins/unity/agent.py`, `core/capture/agents.py` |
| 11.2 D2 audio loopback | implemented | `core/capture/audio.py` |
| 11.2 D3 memory dump | implemented | `core/capture/runtime.py` `dump`, `os/*` `dump_process` |
| 11.2 D3 API trace | implemented | `core/capture/runtime.py` `trace` |
| 11.2 D3 x64dbg and Cheat Engine handoffs | implemented | `core/analysis/handoffs.py` |
| 11.3 agent contract and core flow | implemented | `contracts/runtime.py`, `core/capture/agents.py` |
| 11.4 job kinds and routes, capture steps, DIFF by hash | implemented | `api/handlers_capture.py`, `core/capture/__init__.py` |
| 11.4 temporary antivirus exclusions | implemented | `core/scan_exclusions.py` |
| 11.5 agents in a patched copy; pending-journal restore | implemented | `core/capture/agents.py`, `core/capture/journal.py` |
| 11.6 network declarations, `VIWO_OFFLINE` | implemented | backend `network`, `core/capture/renderdoc.py` |
| 11.7 D4 `hook.inject` (hook loader, hot reload) | open | - |
| 11.7 D4 `hook.overlay` | open | - |
| 11.7 D4 `net.*` (own-traffic capture, proxy) | open | the plaintext capture is the owner's call |
| 11.7 D4 `profile.sample` | implemented | `os/_win_probe.py`, `os/_linux_probe.py` `sample_threads`; `core/capture/profile.py`; `viwo profile`, `/api/runtime/profile` |

## 12 Core, jobs, CLI

| Item | State | Where / missing |
|------|-------|-----------------|
| 12.2 runtime facade | implemented | `core/wiring/boot.py` `Runtime` |
| 12.3 jobs, states, events, bounded history | implemented | `core/jobs.py` |
| 12.3 job kinds | implemented | `api/handlers_jobs.py` `KINDS`, `api/handlers.py` (merge), `api/handlers_system.py` (indexes) |
| 12.3 04 JOBS view links each kind to its view | implemented | `web/js/views/jobs.js` `KIND`: patch and mod to 14, the runtime kinds to 13 |
| 12.3 run records, replay | implemented | `core/records.py`, `cli.py` |
| 12.3 workspace lock for writing jobs, `busy` | implemented | `core/workspace.py`, `api/app.py` `locked_job` |
| 12.3b envelope and codes | implemented | `contracts/errors.py` |
| 12.4 commands grouped by arm, `viwo <arm>` | implemented | `cli_arms.py`, `cli_args.py`; `tests/test_cli.py` |
| 12.4 every command of the table | implemented | `cli.py`, `cli_check.py`, `cli_extra.py`, `cli_dynamic.py`, `cli_patch.py` |
| 12.4 global flags, exit codes, warnings in text mode | implemented | `cli.py` `EXIT`, `cli_format.py` |
| 12.4 plugin commands | implemented | `core/wiring/registry.py` `cli_commands` |
| 12.5 generic job submit, events, cancel | implemented | `api/handlers_jobs.py`, `api/routes.py` |
| 12.6 packaging, portable bundle | implemented | `pyproject.toml`, `packaging/build_portable.py`, `.github/workflows/release.yml` |

## 13 Landscape

| Item | State | Where / missing |
|------|-------|-----------------|
| 13.2 identify/extract, carving, entry points, plan/apply | implemented | docs 8, 2, 5 |
| 13.2 declarative formats (Kaitai) | open | - |
| 13.3 per-engine consequences | implemented | `plugins/*` |
| 13.5 GPL tools as processes | implemented | `tests/test_l0_static.py` |
| 13.7 GameMaker, Unreal export, locres and the other listed engines | open | - |

## 14 Scope

| Item | State | Where / missing |
|------|-------|-----------------|
| 14.2 #1, #2, #3, #5, #6, #7, #8, #9, #10 | implemented | docs 8, 3, 2, 11 |
| 14.2 #4 keys as `secret` options plus a verified key finder | implemented | `plugins/unreal/keys.py`, `plugins/unreal/aes.py`; a `keys.*` slot family is open |

## 15 LoC caps

| Item | State | Where / missing |
|------|-------|-----------------|
| 15.1 counting rules | implemented | `tools/loc_count.py` |
| 15.3 granularity caps and budgets | implemented | `loc_caps.ini`, `tests/test_pipeline.py::test_loc_caps` |
| 15.4 test caps and floor | implemented | `tools/loc_count.py` |
| 15.5 exceptions with expiry, schema validation | implemented | `tools/caps_ini.py`, `tests/test_l0_static.py` |

## 16 Roadmap

| Item | State | Where / missing |
|------|-------|-----------------|
| 16.0b rungs 1-5, 7 | implemented | doc 16.0b |
| 16.0b rung 6 QuickBMS | partial | the bridge works; no index entry carries a pinned script |
| 16.0c everything decoded, all three arms per engine | open | the open column of doc 16.0c |
| 16.2b A1-A4, D1-D3, T1-T2 | implemented | doc 16.2b |
| 16.2b D4 | open | see 11.7 |
| indexes repository split and first release | open | `docs/indexes.md` |

## 17 Testing

| Item | State | Where / missing |
|------|-------|-----------------|
| 17.1 synthetic fixtures, fakes first, property tests | implemented | `tests/` |
| 17.2 levels L0-L6 | implemented | `tests/` |
| 17.2 L7 games pass and CTF flags | implemented | `tools/integration_games.py`, `tools/games_pass.ps1`, `sqc/ctf.json` |
| 17.3 safety catalogue | implemented | tests named in 17.3 |
| 17.4b operator rules | implemented | `plugins/overwatch`, `sqc/04-extraction-per-engine.md` OPERATOR checks |
| 17.5 CI cost rule, coverage floors | implemented | `.github/workflows/ci.yml`, `tools/coverage_check.py` |
| 17.5 98 % line / 95 % branch per file | partial | 86.1 % line, 74.2 % branch at 1.6.2 (child processes counted) |

## 18 Patching arm (rungs T1-T2)

| Item | State | Where / missing |
|------|-------|-----------------|
| 18.2 provenance map, edit set, `_added/` | implemented | `core/provenance.py`, `core/roundtrip_edits.py` |
| 18.3 repack steps, same-format rule, verification by re-extraction | implemented | `core/roundtrip.py` |
| 18.3 asset converters (PNG back to Texture2D, `.ctex`) | open | - |
| 18.4 pack slots | implemented | `plugins/*`, `backends/packers.py` |
| 18.6 target rules, no anti-tamper code | implemented | `core/roundtrip.py` `prepare_copy` |
| 18.8 offset, RVA, AOB, Keystone, capstone, bounded writes, verify, export | implemented | `core/patchsets.py`, `core/patch_tools.py`; `tests/test_patchsets.py` |
| 18.8 API | implemented | `POST /api/patch` and job kind `patch` |
| 18.9 pack, check (adapts), ordered apply, conflicts, duplicate names | implemented | `core/mods.py`; `tests/test_mods.py` |
| 18.9 API | implemented | `POST /api/mod` and job kind `mod` |
