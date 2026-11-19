# Contract conformance

Every normative item of the contract documents, by section, with its state against the code in
this tree: **implemented** (with the module or function), **partial** (what is missing), **open**
(not implemented). Paths are relative to `viwo/` unless they start with `tests/`, `tools/` or a
top-level folder. Update a row in the commit that changes its state.

## Summary

The row counts per state are not kept here by hand (they went stale): the technical PDF counts
them from the tables below (`tools/presentation/reference.py`, `conformance()`).

**Partial**, by cause: no pinned QuickBMS script in the indexes (16.0b); coverage per file (17.5).

**Open:** the completeness contract per engine (16.0c); rung D4 (`hook.overlay`); the way back
of premultiplied, signed and typeless block formats (DXT2/DXT4, signed BC4/BC5, typeless BC6H)
and of ETC, ASTC, PVRTC and Basis Godot textures (no decoder either); Unreal asset export and
the engines 13.7 still lists (GameMaker, TyranoScript, Wolf RPG), LZX-compressed XNB, Defold's
encrypted resources; declarative (Kaitai) plugins; the indexes repository split.

## Done, per engine and arm (owner)

What "done" means for an engine: **extract** (every file out, its formats decoded), **edit +
repack** (a change in the workspace written back into the engine's container or override),
**read back** (the repacked output read with the change in it), **game loads it** (the game
runs with the change). A cell reads `real` (proven on a real install, on Windows), `tests`
(covered by synthetic fixtures only) or `open` (not implemented). On Linux no real game has
run: `tests` means the suite covers the engine there. A row closes when every cell reads
`real` (doc 16.0c).

| Engine | Extract | Edit + repack | Read back | Game loads it | Linux |
|--------|---------|---------------|-----------|---------------|-------|
| REDengine (Cyberpunk 2077) | real | real | real | open | tests |
| Unity | real | real | real | real | tests |
| Unreal | real | real (pak) | real | real (pak) | tests |
| Godot | tests | tests | tests | open | tests |
| Ren'Py | real | real | real | real | tests |
| RPG Maker | real (MV, loose files) | real (MV: loose override) | real | real | tests |
| KiriKiri | real | real | real | real | tests |
| Source | real | real | real | open | tests |
| Bethesda | tests | tests | tests | open | tests |
| Doom | real | real | real | real | tests |
| Electron | tests | tests | tests | open | tests |
| Age of Empires (genie) | real | real | real | real | tests |
| Total War (warscape) | real | real | real | open | tests |
| Bannerlord (taleworlds) | real | tests (one real package by hand) | tests (one real package by hand) | open | tests |
| LÖVE (love2d) | tests (real data, below) | tests (real data) | tests (real data) | open | tests |
| XNA/FNA/MonoGame (xna) | tests (real data) | tests (real data) | tests (real data) | open | tests |
| AGS | tests (real data) | tests (real data) | tests (real data) | open | tests |
| Defold | tests (real data) | tests (real data) | tests (real data) | open | tests |
| QuickBMS | tests | open | open | open | tests |
| Overwatch (DataTool) | tests | - (read only) | - | - | Windows only |

What each `real` stands on (the passes' reports are in `viwo-data/`):

| Engine | Extract | Edit, repack and read back (deep passes at 1.20.56, 2026-11-10/11) |
|--------|---------|------|
| REDengine | Cyberpunk 2077: games pass 2026-11-03, 11 of 11 flags; demo subset at 1.20.56, 183,515 files | a changed byte in a `lang_en_text.archive` resource, packed as `archive/pc/mod/!viwo_lang_en_text.archive` and read back identical. WolvenKit drops bytes appended past a resource's own size; ViWo reports that member as failed |
| Unity | Schedule I: games pass 1.20.37, 12 of 12 flags. Approximately Up: 9 of 10 (the missing flag needs a file the antivirus holds) | a repainted texture in a `.assets` file: Schedule I, ULTRAKILL Prelude, Baldi's Basics, Burning Snow |
| Unreal | - (two UE5 test games meet their 5 flags each, free-games run 1.20.64; assets stay raw without UnrealAssetScout's export) | a repainted texture as a `_P.pak` patch, on both. An edited IoStore member has no packer; the plan says so |
| Ren'Py | a Ren'Py title: games pass 2026-11-04, 10 of 10 flags | a repainted image in `images.rpa` (Doki Doki Literature Club) |
| KiriKiri | - | a repainted image in `data.xp3` (a KiriKiri test game) |
| Source | Team Fortress 2: games pass 2026-11-04, 9 of 9 flags | an edited text as `tf/custom/!viwo_tf2_misc.vpk` |
| Doom | Freedoom: deep pass 1.16.1 | a repainted sprite, both WADs (first at 1.16.4) |
| Genie | AoE II HD: games pass 1.20.34, 13 of 13 flags | a changed member of `interfac.drs` |
| Warscape | Rome II: games pass 2026-11-04, 12 of 12 flags | a repainted image as the movie pack `data/viwo_data_rome2.pack` |
| TaleWorlds | Bannerlord: games pass 2026-11-03, 11 of 11 flags (textures 188 of 190) | not a repack run: a copy of one mod package (`ScarsExtra/AssetPackages/scar_nobl_g.tpac`, a BC7 and a DXT5 texture, raw and LZ4 segments) rewritten by `pack.tpac` with every member unchanged (byte for byte the same file) and with its BC7 texture repainted through PNG, `pillow-image` and the BC7 encoder (read back by the plugin's reader: the edit in place, the other texture unchanged, the mip-1 copy following the edit). The game was not run on it |

**The game loads the change** (1.20.72, 2026-11-18; the patched copy started, its own
window captured by `tools/game_shot.ps1`, screenshots in `sqc/proof/`): Ren'Py (Doki Doki
Literature Club: the menu background repacked into `images.rpa`), Unity (Baldi's Basics
Classic Remastered: a texture repacked into `sharedassets0.assets`), RPG Maker MV (a test
game: the title image as a loose override), KiriKiri (1.22.1, 2026-11-19, a test game: the
title background from `patch.xp3`; an image its scripts name with its folder, its logo, is
out of a patch's reach, doc 18.4), Unreal (1.22.1, a UE5 test game: the project title in
`DefaultGame.ini` from ViWo's `_P.pak`; the mark is the window's title, which the tool prints,
the game running full screen behind it), Age of Empires (1.25.3, Age of Empires II HD: the main
menu background as a loose file of the copy, which also held the rewritten `interfac.drs`; the
game started through a Steam Workshop dialog, dismissed by `-Keys`), Doom (1.27.1, Freedoom 2
in Chocolate Doom 3.1.0: the title picture repainted in the rewritten `freedoom2.wad`). A decoded file's way back (18.3) is shown too: on Ren'Py at
1.22.4, a line edited in the decompiled `splash.rpy` is on the game's first screen, the game
having compiled the script itself (`sqc/proof/renpy-ddlc-script.jpg`). Open on the other
engines.

**Real data, no game install** (NEXT, 2026-11-19; downloaded from the engines' official releases and sites, never run, deleted after): AGS, the five templates of the 3.6.3.17 release (CLIB version 30, 11 to 137 assets): every asset out, each rebuilt unchanged byte for byte, an edited asset read back with the others unchanged; Defold, the bundle of an official example (`defold.com/examples`, index version 6, 13 resources, 6 LZ4, 2 encrypted and named): every unencrypted resource out under its URL, the bundle rebuilt unchanged byte for byte, an edited resource read back; LÖVE, the official `love.exe` 11.5 fused with a test zip: recognised (`love.exe` alone is not), unpacked, rebuilt with an edit behind the executable's unchanged bytes; XNA, sixteen of MonoGame's own test XNB files (Color, Bgra4444, DXT1, DXT5 textures, PCM 8/16-bit, float and MS-ADPCM sounds, all uncompressed): each decoded, written back unchanged byte for byte (DXT re-encoded within 3 per channel), a SpriteFont and a TextureCube refused by name. Not verified on real data: LZ4 XNB, CLIB versions 6 to 21, Defold index versions 4 and 5, any `.locres`; no game of these engines ran with a change.

Not at hand: a game of LÖVE, XNA/FNA, AGS, Defold or with an Unreal `.locres` table, a Godot game that ships its data, a Bethesda game, an RPG Maker game with a
packed archive (the MV test game keeps its files loose), a real QuickBMS archive. Unity
MonoBehaviour fields come out for the scripts whose rebuilt layout fits; the others are
listed without fields and counted (1.20.41). Linux tools: WolvenKit, repak, retoc, GDRE,
GodotPckTool and QuickBMS have a Linux pin; Cpp2IL, BepInEx, UnrealAssetScout and DataTool
are Windows only.

The dynamic arm (capture, agents, dump, trace, attach) and the analysis arm are tracked in 11.2
and 6; `viwo attach` on a running game is still to be verified on real data (HANDOFF).

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
| 0.2 job, run record, stage, slot, backend, main/spare, promoted, fallback | implemented | `core/jobs.py`, `core/records.py`, `core/pipeline/runner.py` `_stages`, `contracts/slots.py` |
| 0.2 features `extraction`, `sorting`, `merger` | implemented | `core/context.py` `require`: extraction (runner, `viwo unpack`), sorting and merger routes (`api/handlers.py` `gated`); `tests/test_switches.py` |
| 0.2 features `capture`, `analysis` | implemented | `core/capture/policy.py` `check`, `core/capture/runtime.py` `_enabled`, `core/analysis` `_check_enabled` |
| 0.2 pinned tool, worker tool, handoff, runtime agent | implemented | `core/thirdparty.py`, `core/workers.py`, `contracts/analysis.py` `Handoff`, `contracts/runtime.py` |
| 0.2 provenance, edit set, patched copy, patch set, mod | implemented | `core/provenance.py`, `core/roundtrip_edits.py`, `core/roundtrip.py`, `core/patchsets.py`, `core/mods.py` |
| 0.4 result keys and meanings | implemented | `contracts/pipeline.py` `to_legacy_dict` |
| 0.4 `inventoryItems`, `collectedFromInventory` | implemented | core counts a plugin's `inventory()` against COLLECT's provenance (`pipeline/checks.py` `recorded`, `verify_one`); Source's VPK directories (`plugins/source/__init__.py` `listed`); `tests/test_plugin_providers.py`. 0 for the plugins that keep none |

## 01 OS layer

| Item | State | Where / missing |
|------|-------|-----------------|
| OS object (`os_id`, `is_supported_host`, parts) | implemented | `contracts/os.py`, `os/linux.py`, `os/windows.py` |
| homes, scan exclusions, `pids_of`, `dump_process` | implemented | `os/_shared.py`, `os/windows.py`, `os/linux.py` |
| 1.1 run: UTF-8, pump threads, never raises on exit code, tree kill on timeout/cancel | implemented | `os/_shared.py` `SubprocessRunner` |
| 1.1 launch tracked children, killed at exit | implemented | `SubprocessRunner.launch`, `_reap_children` |
| 1.1 max_command_length used by long command lines | implemented | merger build (`core/merger/build.py`) |
| 1.1 shell_command: a user's command line through the host's shell | implemented | `contracts/os.py` (`/bin/sh -c`), `os/windows.py` (`cmd /d /s /c`, the line as written) |
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
| 2.2 `inventory()` | implemented | Source: every member its VPK directories list; the missing ones named in a verify warning (`pipeline/checks.py`) |
| 2.2 exceptions recorded against the plugin | implemented | `core/pipeline/export.py`, `core/pipeline/failover.py` |
| 2.3 shared probe, case-preserved paths, cache on size and mtime | implemented | `core/pipeline/probe.py` `FolderProbe` |
| 2.4 detection result and scale | implemented | `contracts/types.py` `DetectionResult` |
| 2.5 recursive unpack, depth 10, slot lookup (fallback identifiers last), cancel, member safety, altered names recorded | implemented | `core/pipeline/unpack.py`, `core/pipeline/identify.py`, `contracts/workspace.py` (`Names`, `files`); `tests/test_skips_said.py`, `tests/test_review_fixes.py` |
| 2.6 dependency spec, per-OS executables, ViWo's own described once | implemented | `contracts/types.py` `DependencySpec`, `DependencySpec.of`; `data/dependencies.json`; `tests/test_dependencies_data.py` |
| 2.7 twenty-one built-in plugins (and two game plugins) | implemented | `plugins/*/` |
| 2.8 built-in scan, drop-ins, entry points, opt-in, override | implemented | `core/wiring/registry.py`, `tests/test_registry.py` |
| 2.9 conformance checks and sandbox | implemented | `core/wiring/conformance.py`, `tests/test_conformance_kit.py` |
| 2.10 game plugins: discovery under their engine, selection with it (never loaded without it), what they supply through the run context | implemented | `core/wiring/registry.py` `_without_orphans`, `core/pipeline/select.py` `with_games`, `contracts/plugin.py`; `plugins/redengine/games/cyberpunk2077`, `plugins/taleworlds/games/bannerlord`; `tests/test_game_plugins.py` |
| 2.10 engine plugins detect by the engine's signatures, never a title's executable | implemented | `genie` by DRS, `warscape` by PFH packs (1.20.6; their title executables dropped), `source` by VPK and the engine's own launcher; Warscape's per-title RPFM schema table is data (`warscape/db.py` `GAMES`) |

## 03 Pipeline

| Item | State | Where / missing |
|------|-------|-----------------|
| 3.1 stage order and events | implemented | `core/pipeline/runner.py` `_stages` |
| 3.1 guard: one guard hands every writer its folder (not the game, not inside it, not holding it; no marker exempts a folder), before any lock, claim or copy | implemented | `core/pipeline/guard.py` `guarded`: extraction, capture, attach, analysis, dynamic runs, patched copies (repack, patch, mod, agents), sanitizer, the API's claims and locks; `tests/test_game_guard.py` drives every CLI command that takes a game and a folder |
| 3.1 guard without a game path (dump, trace, hook, profile, record, sanitize, `unpack --out`, `diff --out`) | implemented | `pipeline/guard.py` `outside_games` (the remembered games of `viwo-data/games.json`, Steam libraries, Epic and GOG install marks, patched copies and their insides) then `_unowned`; `tests/test_game_guard.py`. A game ViWo was never given, from no store with marks, is still out of reach |
| 3.1 wrapper re-detection | implemented | `core/pipeline/export.py` `rewrap`; `tests/test_formats.py::test_engine_inside_an_asar_is_redetected` |
| 3.1 carve modes and claimed suffixes | implemented | `core/pipeline/carving.py` |
| 3.1 COLLECT copy/move, dedupe by hash, unreadable files named (also one held while it is copied) | implemented | `core/pipeline/collect.py`; `tests/test_collect_holds.py` |
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
| 4.1 token, JSON only, size limit, Host check, binding, containment, preview cookie for LAN peers | implemented | `api/server.py`; `tests/test_server.py`, `tests/test_review_fixes.py` |
| 4.2 dependency item | implemented | `core/wiring/boot.py` `dependency_report` |
| 4.3 layout, marker, ownership, re-extraction policy | implemented | `contracts/workspace.py`, `core/workspace.py` |
| 4.3 trash areas and migration, collision names | implemented | `core/curation/trash.py`, `core/curation/sorting.py` |
| 4.3 workspace lock across processes, new-folder lock | implemented | `core/workspace.py` `workspace_lock`, `LOCK_FILE` |
| 4.3 lock owner checked first (pid, its start time, host), refreshed while held, age only for an owner on another machine | implemented | `core/workspace.py` `_stale`, `_keep_fresh`; `os/_started.py` `pid_started`; `tests/test_lock_owner.py` |
| 4.4 events, line format, daily log, masking | implemented | `contracts/types.py` `ProgressEvent`, `api/app.py`, `web/js/progress.js` |
| 4.5 configuration, secrets off disk | implemented | `core/wiring/ini.py`, `core/pipeline/runner.py` |
| 4.6 UI session, persisted stores | implemented | `api/app.py`, `core/surveys.py` |

## 05 Sanitizer

| Item | State | Where / missing |
|------|-------|-----------------|
| 5.1 phase 1 rules | implemented | `core/sanitizer_rules.py` |
| 5.1 phase 2 (lossless open-format copies through the bound lossless `decode.*` slots, `.sanitizer/cache/`, `replace`, provenance for the way back, run-record gating of plugin slots) | implemented | `core/sanitizer_convert.py` `Convert`, `commit`; `Decoder.lossless` (`contracts/slots.py`); `tests/test_sanitizer_phases.py` (fake ffmpeg; no real decoder run through it yet) |
| 5.1 phase 3 (lossy transcode presets through `media.encode`, marked and never in `all-safe`; renumbering) | implemented | `core/sanitizer_convert.py` `Transcode`, `core/sanitizer_rules.py` `Renumber`; `tests/test_sanitizer_phases.py`. The presets (libopus, libx264) have not run on the pinned ffmpeg: tests use a stand-in |
| 5.1 plugin rule providers | implemented | the rule types in `contracts/sanitizer.py` (a plugin cannot import core), `collect_rules`; Ren'Py's `renpy.cache` (`plugins/renpy/__init__.py`); `tests/test_plugin_providers.py` |
| 5.2 rule model, cost order, batch rule last | implemented | `contracts/sanitizer.py` (the types), `core/sanitizer_rules.py` |
| 5.2 plan pages, stale plan refused, journal, undo, undoable cancel | implemented | `core/sanitizer.py` |
| 5.2 files made journaled; undo removes them while unchanged, keeps and names an edited one | implemented | `core/sanitizer_journal.py`, `core/provenance.py` `add`/`forget` |
| 5.3 routes and CLI (recipes with `unready`, `accept: all`, `--recipe`), CLEANUP's recipe picker with the LOSSY mark | implemented | `api/handlers_tools.py`, `cli_extra.py`, `cli_args.py`, `web/js/views/cleanup.js`, `web/js/views/cleanup-recipes.js` |

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
| 6.2 A3 version diff | implemented | `core/analysis/diff.py`, `viwo diff`, `POST /api/analysis/diff`, 12.F VERSION DIFF in ANALYSIS |
| 6.2 A4 `analysis.emulate`, `analysis.symbolic` workers | implemented | `core/analysis/emulate.py`, `core/workers.py`, `data/workers/emulate.py`, `data/workers/symbolic.py` |
| 6.2 `record.json` per run, output emptied before rerun | implemented | `core/analysis/__init__.py` `analyze` |
| 6.3 static handoffs per kind (`handoff.*`; nothing runs the game) | implemented | `core/analysis/__init__.py` `handoffs_for`, `open_in`; `core/handoff.py` |
| 6.4 Ghidra project beside the workspace, on-demand pin, first-run answers | implemented | `core/analysis/ghidra.py`, `data/tools.json` |
| 6.5 `memory_image` targets | implemented | Windows minidumps proposed by `plugins/generic/__init__.py` `dump_targets`; `analysis.memory` = `ghidra-headless` (`core/analysis/ghidra.py`, Ghidra 12.2's Dump File Loader); `tests/test_analysis.py` with a fake analyzeHeadless. Run once by hand with the pinned Ghidra on a real full-memory minidump of `ping.exe` (14.6 MB, the OS layer's `dump_process`): 21,859 functions, all four files, 47 min. The Linux `.mem` layout has no reader |
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
| 8.2 a fresh folder for every attempt (`into`, required), no spare after a cancel (`cancel`, required), in every stage | implemented | `core/pipeline/failover.py`; callers in `core/pipeline/`, `core/decode.py`, `core/analysis/`, `core/capture/`, `core/roundtrip.py`, `core/merger/`; `tests/test_failover_fresh.py` |
| 8.2 `main_only` policy | implemented | `core/wiring/binder.py` `bind_slot`; `tests/test_slot_policy.py` |
| 8.2 `supplement` policy | implemented | `pipeline/failover.py` `supplement`, `_merge`; `wiring/binder.py` `_policy` (folder-writing families only); carve and per-file decode say its notes; `tests/test_slot_policy.py` |
| 8.2 binding, promotion, unbound, bad ini entries | implemented | `core/wiring/binder.py` |
| 8.2 never silent: `Outcome.fallback` in every stage | implemented | `core/pipeline/failover.py`; stages in `core/pipeline/`, `core/analysis/`, `core/capture/` |
| 8.3 interfaces | implemented | `contracts/slots.py`, `contracts/analysis.py`, `contracts/runtime.py`, `core/patch_tools.py` |
| 8.3a Ghidra (`handoff.*`), x64dbg and Cheat Engine (`attach.*`) as tracked children | implemented | `core/handoff.py`, `core/analysis/ghidra.py` `GhidraGui`, `core/capture/handoffs.py` |
| 8.3a first-run answers off screen | implemented | `core/capture/handoffs.py`, `core/analysis/ghidra.py`, `core/capture/renderdoc.py` |
| 8.4 slot table | implemented | `backends/__init__.py`, `core/*` `SLOTS`, plugin `slot_definitions` (`viwo slots`) |
| 8.5 stage use | implemented | as listed |
| 8.5 `export.unity` meshes as `.glb` (all channels, sub-meshes, skin and bone tree, main texture; Unity's left-handed space mirrored) through the shared glTF writer | implemented | `plugins/unity/meshes.py`, `contracts/gltf.py` (also `plugins/overwatch/owmdl.py`); `tests/test_unity_glb.py`, `tests/test_owmdl.py`. Blend shapes, more than four weights a vertex and animations stay open (16.0c) |
| 8.5 `export.unreal` models as `.glb` beside UnrealAssetScout's UEFormat (LOD 0, all channels, sections, skeleton and weights; Y and Z swapped), option `models` | implemented (tests only) | `plugins/unreal/uemodel.py`; `tests/test_uemodel.py`, `tests/test_unreal_assets.py`. Not yet run on a real `.uemodel`: both free UE5 test games need mappings (`.usmap`) for every package, which only the RUNTIME agent dumps from the running game. Morph targets, sockets, collision and textures stay open |
| 8.5 `export.unreal` failures counted from the tool's log (compact progress hides them) | implemented | `plugins/unreal/assets.py` `_run`; real: Void's Cave (3622 packages) and The Basement (815) now name the missing mappings |
| 8.5 `decode.mdl` Source models as `.glb` (versions 44-49, LOD 0 of every body part's default model, rig, `$basetexture`; Z-up turned, triangles rewound) | implemented | `plugins/source/studio.py`, `plugins/source/models.py`; `tests/test_source_models.py`; real: Team Fortress 2 (v48; the misc VPK and part of the textures, 2.9 GB): 9,141 models, 9,092 `.glb`, 48 without a mesh, 1 refused (its `.vvd` in a part not copied); every index in range and every weight set summing to one; 8,697 of 9,087 enclose a positive volume (front faces out); 992 of 11,903 materials textured (the other textures were not in the copy). TF2's characters lie on their side, as their bind pose does; flexes and animations stay open |
| 8.5 `decode.rigid_model_v2` Total War rigid models as `.glb` (versions 5, 6 and 7, LOD 0; static, collision, weighted, cinematic and water groups, banners, bow waves, decal projection boxes; the skeleton from `.anim` and `.bone_inv_trans_mats`, the colour map; X mirrored, triangles rewound) | implemented (version 7: tests only) | `plugins/warscape/rigid.py`, `plugins/warscape/models.py`; `tests/test_rigid_models.py`, `tests/test_rigid_layouts.py`; real: Rome II (`models.pack` and `data.pack` copied, 1.1 GB; whole extraction 11 min 53 s, decode 4 min 07 s): 1,281 models, 1,243 `.glb` (958 at 1.25.0), 10 without a mesh, 28 refused, each by name: 6 of versions 1 and 3, 15 flag placements and 6 lights or effects (no vertex data), 1 debug capsule (material type 46, its layout not verified); no group left out of a converted model; 8,693 primitives (7,668 static, 196 weighted, 235 cinematic, 8 collision, 1 water, 17 banners, 42 bow waves, 526 decal boxes); every layout checked on the files: every position inside its group's bounding box (a type-87 decal box reaches past it in Y, its projection depth), normals agreeing with their triangles and U and V directions with the UV gradients as for version 6, every bow-wave triangle facing up; 166 skinned with their skeleton, 2 keep their links as data (one names no skeleton, a cloth test weighs on bone 132 of a 105-bone skeleton); every index in range, every position finite, every normal unit, every weight set summing to one; 1,022 enclose a positive volume, 176 none (decal boxes and sheets), 45 a negative one (37 open bow-wave sheets, 3 flat banners, the 5 of 1.25.0); 4,500 of 8,693 materials textured (version 5 names its colour maps `.tga`: none of the 157 is in the packs, 71 are there as `.dds` under the same path and are not substituted). Version 8 stays open |
| 8.5 `decode.nif` Bethesda NIF models as `.glb` (20.2.0.7, user version 12, streams 83, 100, 130; node tree, NiTriShape and BSTriShape, skins (from NiSkinData, the vertices or the NiSkinPartition) with Gamebryo's bind matrices, the colour map; Z-up turned) | implemented (tests only) | `plugins/bethesda/nif.py`, `plugins/bethesda/nifmodels.py`; `tests/test_nif_models.py`. No Bethesda game at hand: no real NIF has been read. Skinned Skyrim SE shapes whose vertices, triangles and weights are in the NiSkinPartition, and skins whose NiSkinData holds no weights, are read from the partition (`plugins/bethesda/partition.py`, `tests/test_nif_partition.py`, laid out as nif.xml describes it, never checked on a real file). NiTriStrips, BSDynamicTriShape, Fallout 4 `.bgsm` materials, collision and animations stay open |
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
| 9.2 `[slot_policy]` (`failover`, `main_only`) | implemented | `core/wiring/ini.py` `_read_policies`; shown by `viwo slots` and `viwo info` |
| 9.5 `[hooks]` lifecycle hooks: before/after each job, environment, output as events, warnings only, timeout | implemented | `core/hooks.py`, `core/jobs.py` `JobRunner._run`, `core/wiring/ini.py` `_read_hooks`, `api/app.py`, `cli.py` `_as_job`; `tests/test_job_hooks.py`. The CLI commands that are no job kind fire none (listed in 9.5) |
| 9.1 `--plugin <id>=on\|off`, `--slot <slot>=<main>[,<spare>]` for one run | implemented | `cli_boot.py`, `core/wiring/boot.py`; `tests/test_cli_overrides.py` |
| 9.6 `/api/distro`, SETTINGS writes and reloads | implemented | `api/routes.py`, `core/wiring/settings.py`, `api/app.py` `reload` |

## 10 Pinned tools

| Item | State | Where / missing |
|------|-------|-----------------|
| 10.1 pin file: tools, python, workers, on_demand, hidden | implemented | `data/tools.json`, `core/thirdparty.py` |
| 10.1 hash-locked Python pins | implemented | `data/locks/`, `tools/pin_python.py`, `core/thirdparty.py` `pip_install` |
| 10.2 install paths: CLI, SYSTEM, preflight | implemented | `cli_extra.py`, `api/handlers_tools.py`, `core/preflight.py` |
| 10.2 HTTPS, size and sha256, resumed drops, HTTP errors named (4xx at once), unknown sizes whole or failed, safe unpack, busy folder, antivirus hint | implemented | `core/thirdparty.py`, `core/downloads.py`; `tests/test_thirdparty_unpack.py` |
| 10.2 worker install into a fresh folder | implemented | `core/workers.py` |
| 10.3 every pin listed | implemented | `data/tools.json`; `THIRD_PARTY_NOTICES.md` (`tools/notices.py`, `tests/test_diag.py`) |
| 10.4 no prompts, no elevation | implemented | Cheat Engine from Scoop's unpacked build; first-run answers (8.3a) |
| 10.5 update check, indexes update | implemented | `core/diag.py`, `core/indexes.py`, `api/handlers_system.py` |

## 11 Dynamic arm (rungs D1-D4)

| Item | State | Where / missing |
|------|-------|-----------------|
| 11.1 `capture` switch for capture, dump, trace, hook, profile, agent, record, attach | implemented | `core/capture/policy.py` `check`, `core/capture/runtime.py` `_enabled` |
| 11.1 confirmation once per game | implemented | `core/capture/policy.py` `remember`, `confirmed_games` |
| 11.1 warnings: markers, services, online titles, sensitive plugins, network | implemented | `core/capture/policy.py` `warnings_for`, `data/capture_policy.json` |
| 11.1 debugger and memory attach tools as dynamic actions | implemented | `core/capture/attach.py` `attach`: only the `capture` switch (not `analysis`), one confirmation per game (`--confirm`, the UI's confirm box), the warnings (`tests/test_attach.py`) |
| 11.2 D1 unattended capture, shader disassembly | implemented | `core/capture/renderdoc.py`, `data/renderdoc/rd_trigger.py`, `data/renderdoc/rd_harvest.py` (`tests/test_rd_scripts.py`) |
| 11.2 D2 UE4SS and BepInEx agents | implemented | `plugins/unreal/agent.py`, `plugins/unity/agent.py`, `core/capture/agents.py` |
| 11.2 D2 audio loopback | implemented | `core/capture/audio.py` |
| 11.2 D3 memory dump | implemented | `core/capture/runtime.py` `dump`, `os/*` `dump_process` |
| 11.2 D3 API trace | implemented | `core/capture/runtime.py` `trace` |
| 11.2 D3 x64dbg on the game's own process (attached by pid, else its executable started), Cheat Engine table | implemented | `core/capture/handoffs.py`, `core/capture/attach.py`; `viwo attach`, `/api/runtime/attach`, RUNTIME |
| 11.3 agent contract and core flow | implemented | `contracts/runtime.py`, `core/capture/agents.py` |
| 11.4 job kinds and routes, capture steps, DIFF by hash | implemented | `api/handlers_capture.py`, `core/capture/__init__.py` |
| 11.4 temporary antivirus exclusions | implemented | `core/scan_exclusions.py` |
| 11.5 agents in a patched copy; pending-journal restore | implemented | `core/capture/agents.py`, `core/capture/journal.py` |
| 11.6 network declarations, `VIWO_OFFLINE` | implemented | backend `network`, `core/capture/renderdoc.py` |
| 11.7 D4 `hook.inject` (a user's hook script, hot reload) | implemented | `core/capture/hook.py`: the pinned Frida's own command line as a tracked child, its lines relayed live and kept in `.runtime/hook/`; `viwo hook`, `/api/runtime/hook`, RUNTIME (`tests/test_hook.py`, with a stand-in tool). Verified on a real process that is not a game (the pinned Frida 17.25.2 installed by `viwo install`, a script listing the modules of a sleeping Python process, saved again mid-run and reloaded; Windows, 2026-11-10); not run on a game, not run on Linux |
| 11.7 D4 `hook.overlay` | open | third-party only, and neither candidate fits the rules (11.7): Special K works around CAPCOM's copy protection by default (the owner's call) and shows its licence screen in the game; MangoHud's release tarball installs into `/usr` with `sudo`. Both downloads were checked (size, sha256), nothing is pinned |
| 11.7 D4 `net.*` (own-traffic proxy) | implemented | `attach.net` / `mitmproxy-gui`, `core/capture/nettools.py` (pinned mitmproxy as a tracked child, regular mode; `tests/test_nettools.py`; a real request passed through it at 1.20.43). Per-process capture and raw packet capture are not used: both need elevation |
| 11.7 D4 `profile.sample` | implemented | `os/_win_probe.py`, `os/_linux_probe.py` `sample_threads`; `core/capture/profile.py`; `viwo profile`, `/api/runtime/profile` |

## 12 Core, jobs, CLI

| Item | State | Where / missing |
|------|-------|-----------------|
| 12.2 runtime facade | implemented | `core/wiring/boot.py` `Runtime` |
| 12.3 jobs, states, events, bounded history | implemented | `core/jobs.py` |
| 12.3 job kinds | implemented | `api/handlers_jobs.py` `KINDS`, `api/handlers.py` (merge), `api/handlers_system.py` (indexes) |
| 12.3 JOBS view links each kind to its view | implemented | `web/js/views/jobs.js` `KIND`: patch and mod to 14, the runtime kinds to 13 |
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
| 13.7 GameMaker, TyranoScript, Wolf RPG, Unreal export (CUE4Parse) | open | - |
| 13.7 covered: Unreal `.locres`, LÖVE, XNA/FNA, AGS, Defold (first-party readers, their ways back) | implemented (tests; real data, no game install: see the engine matrix) | `plugins/unreal/locres.py`, `plugins/love2d`, `plugins/xna`, `plugins/ags`, `plugins/defold`; `tests/test_locres.py`, `tests/test_love2d.py`, `tests/test_xna.py`, `tests/test_ags.py`, `tests/test_defold.py` |

## 14 Scope

| Item | State | Where / missing |
|------|-------|-----------------|
| 14.2 #1, #2, #3, #5, #6, #7, #8, #9, #10 | implemented | docs 8, 3, 2, 11 |
| 14.2 #4 keys as `secret` options plus a verified key finder | implemented | `plugins/unreal/keys.py`, `plugins/unreal/aes.py`; the `keys.*` slot family: `contracts/slots.py` `KeyFinder`, `core/context.py` `candidate_keys` (`ctx.keys`), `keys.unreal` = `unreal-exe-keys`; `tests/test_unreal.py` |

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
| 17.5 98 % line / 95 % branch per file | partial | 98.6 % line, 95.3 % branch overall at 1.6.23 (child processes counted); 72 files under the per-file target |

## 18 Patching arm (rungs T1-T2)

| Item | State | Where / missing |
|------|-------|-----------------|
| 18.2 provenance map, edit set, `_added/` | implemented | `core/provenance.py`, `core/roundtrip_edits.py` |
| 18.3 repack steps, same-format rule, verification by re-extraction | implemented | `core/roundtrip.py` |
| 18.3 asset converters: the way back of decoded files (`Decoder.encode`, ENCODE, verify on the encoded bytes, every one-way file named) | implemented; real on Ren'Py scripts (1.22.4), the other ways back tests only | `core/roundtrip_encode.py`, `core/roundtrip_plan.py`; `tests/test_roundtrip_encode.py` |
| 18.3 mod or overwrite (`--mode`, API `mode`, default `mod`; the item says which form and why) | implemented; `mod` real on Ren'Py (1.22.4), the rest tests only | `core/roundtrip_plan.py`, `EnginePlugin.loose_root` (Ren'Py), `Packer.drops` (`pack.rpa`); `tests/test_roundtrip.py`, `tests/test_roundtrip_encode.py` |
| 18.3 way back of `decode.vtf` (PNG to uncompressed VTF) | implemented (tests only) | `plugins/source/vtf_write.py`; `tests/test_encoders.py` |
| 18.3 way back of `decode.slp` (PNG sheet to SLP, simplest valid encoding) | implemented; read back real (1.22.5, Age of Empires II HD: a marked icon sheet re-encoded into `interfac.drs` and its loose copy, decoded again: the mark is in every frame, in the palette's nearest colours; what was painted outside a frame is not kept; not started in the game) | `plugins/genie/slp_write.py`; `tests/test_encoders.py`, `tests/test_roundtrip_encode.py` (end to end through the DRS) |
| 18.3 way back of `decode.loc` (JSON to `.loc`) | implemented (tests only) | `plugins/warscape/loc.py`; `tests/test_encoders.py` |
| 18.3 way back of `decode.locres` (JSON to the table in its version, hashes and storage kept, byte for byte unchanged; a new key in version 3 refused) | implemented (tests only) | `plugins/unreal/locres.py`; `tests/test_locres.py` |
| 18.3 way back of `decode.xnb` (PNG to Texture2D, WAV to SoundEffect, compressed as it was) | implemented (tests; real MonoGame test files written back unchanged byte for byte) | `plugins/xna/content.py`, `plugins/xna/xnb.py`; `tests/test_xna.py` |
| 18.3 way back of `decode.rpyc` (the `.rpy`, the stale `.rpyc` removed) | implemented; real (1.22.4, Doki Doki Literature Club: the edited `.rpy` compiled by the game on start and shown, `sqc/proof/renpy-ddlc-script.jpg`) | `plugins/renpy/decompile.py`, `plugins/renpy/pack.py`; `tests/test_roundtrip_encode.py` |
| 18.3 way back of `decode.cr2w` (WolvenKit `import --keep`, `convert deserialize`) | implemented (fake tool only: the real WolvenKit not run on it yet) | `plugins/redengine/encode.py`; `tests/test_wolvenkit_import.py` |
| 18.3 way back of `decode.image` (PNG to uncompressed DDS, or BC1 to BC5 through ViWo's own range-fit encoder, BC7 in mode 6 and BC6H in mode 11 through its own BPTC encoder; premultiplied DXT2/DXT4, signed BC4/BC5 and typeless BC6H skipped with the reason); `pillow-image` the slot's spare (BC6H and BC7, which the pinned ffmpeg does not read) | implemented (tests: every format decoded again by ViWo's decoders and by Pillow; BC1 to BC4 blocks also checked byte for byte against the pinned ffmpeg's decoder by hand, not in the suite; BC7 written into a real Bannerlord texture and decoded again, by hand) | `core/encode_dds.py`, `core/decode_dds.py`, `backends/blocks/`; `tests/test_encoders.py`, `tests/test_encode_bc.py`, `tests/test_decode_bc.py` |
| 18.3 way back of `decode.ctex` (PNG to the Godot texture in its form: PNG or lossless WebP mipmaps, uncompressed 8-bit, or S3TC/RGTC/BPTC blocks decoded by ViWo's own block decoders; ETC, ETC2, ASTC, PVRTC and Basis skipped with the reason) | implemented (tests only: no Godot game with PCK data here) | `plugins/godot/ctex.py`, `plugins/godot/ctex_write.py`, `plugins/godot/vram.py`; `tests/test_godot_ctex.py` |
| 18.4 `pack.tpac` (TaleWorlds TPAC rewritten member by member, every other byte kept; a texture's tail segment follows its edit; LZ4 HC 12 and xxHash64 as the game's packages) | implemented (tests, and one Bannerlord package rewritten unchanged, byte for byte, and with one BC7 texture edited, read back by the plugin's reader, by hand; the game itself was not run on it) | `plugins/taleworlds/pack.py`, `plugins/taleworlds/xxh64.py`; `tests/test_tpac_pack.py` |
| 18.3 way back of `decode.redscripts` (the edited source as `r6/scripts/<path>.reds` beside `final.redscripts`; the plan says the copy needs the redscript compiler) | implemented (tests only: fake redscript, the compiler not run on it) | `plugins/redengine/games/cyberpunk2077/scripts.py`, `Decoder.adds`/`back_note`, `core/roundtrip_encode.py`; `tests/test_redscripts.py` |
| 18.3 way back of `decode.audio`, `decode.video`, `decode.bink2` | not possible under the rules (proprietary encoders): said per file | `Decoder.one_way` |
| 18.4 pack slots | implemented | `plugins/*`, `backends/packers.py` |
| 18.4 `pack.love`, `pack.clib`, `pack.arci` (LÖVE's zip behind its executable, AGS libraries in their own version, Defold's bundle with its hashes and manifest kept) | implemented (tests; real data: see the engine matrix) | `plugins/love2d`, `plugins/ags/pack.py`, `plugins/defold`; `tests/test_love2d.py`, `tests/test_ags.py`, `tests/test_defold.py` |
| 18.6 target rules (the guard first, also for a reused copy), no anti-tamper code | implemented | `core/roundtrip.py` `prepare_copy`, `core/pipeline/guard.py` `guarded` |
| 18.8 offset, RVA, AOB (overlapping matches counted), Keystone, capstone, bounded writes, overlapping patches refused, verify, export | implemented | `core/patchsets.py`, `core/patch_tools.py`; `tests/test_patchsets.py` |
| 18.8 API | implemented | `POST /api/patch` and job kind `patch` |
| 18.9 pack, check (adapts), ordered apply, conflicts, duplicate names | implemented | `core/mods.py`; `tests/test_mods.py` |
| 18.9 API | implemented | `POST /api/mod` and job kind `mod` |

## 19 Guides

| Item | State | Where / missing |
|------|-------|-----------------|
| 19.1 workbook files, validation, user override, stale marking | implemented | `core/guides.py`, `core/workbooks.py`, `data/workbooks/` (x64dbg, Ghidra x2, Cheat Engine, RenderDoc); `tests/test_workbooks.py` |
| 19.1 CLI, API, UI | implemented | `viwo workbook`, `GET /api/workbooks`, WORKBOOKS and the HOW TO buttons (`web/js/views/workbooks.js`) |
| 19.1 workbooks from the indexes repository | open | `docs/indexes.md` |
| 19.2 runbook files, validation, `{name}` values, save and delete of the user's copy | implemented | `core/guides.py`, `core/runbooks.py`, `data/runbooks/` (three); `tests/test_runbooks.py` |
| 19.2 one step at a time through the job handlers, stop on failure, resume from any step, pause for a step you do | implemented | `api/handlers_runbooks.py`, `cli_guides.py` (`viwo runbook`), `web/js/views/runbooks.js`, `runbook-step.js` (each step as a readable row, its JSON behind a toggle) |
| 19.2 a structured step editor (today: the runbook as JSON) | open | - |
| 19.3 the recorder: start, pause, continue, note, stop (saved as a runbook), discard; every action route recorded | implemented | `api/recording.py`; REC chip and RECORD A WORKFLOW (`web/js/views/recording.js`) |
| 19.3 portable parameters, secret options as secret inputs never written, expectations and replay that stops where an answer differs | implemented | `core/workflows.py`, `api/handlers_runbooks.py` `run_step`, `cli_guides.py`; `tests/test_workflows.py` |
| 19.3 what is done inside a child tool: a note the user writes (the tool stays native) | implemented | `api/recording.py` `note` |
| 19.4 embedded child GUIs | dropped | owner, 2026-11-05: native tools stay native |
