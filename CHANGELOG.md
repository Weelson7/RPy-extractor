# Changelog

Versions follow `va.b.c` (`tools/version.py`): `a` product release, `b` feature, `c` every
commit. Each tag's commit message carries the full list; this file keeps what changed for a user
or a maintainer. Newest first.

## 1.6.5 (2026-11-04)
- Fix: the RenderDoc helpers (`rd_trigger.py`, `rd_harvest.py`) moved to `viwo/data/renderdoc/`:
  next to ViWo's own `core/capture/renderdoc.py`, `import renderdoc` found ViWo's module in any
  Python where RenderDoc's module is not built in (the documented `[tools] rdpython` path).
- Fix: a GDRE recovery that stops with an error after writing files is said as a note (it was
  an unexplained OK).
- Property tests: the RenderDoc helpers run as real processes against a fake `renderdoc` module
  (one PNG per texture, one disassembly per shader object of draws and dispatches, the newest
  target, every exit code); the RenderDoc backend's endings; Godot recover and pack over random
  folders and edit sets, PCK trailers and PE headers fuzzed; the Linux OS layer on any host
  against a fake `/proc` (memory dump layout, process list, module spans, perf).

## 1.6.4 (2026-11-04)
- The completeness contract (owner): ViWo gets everything out of every game, decoded, with the
  three arms on every engine (doc 16.0c, with the per-engine table of what is decoded today and
  what is open; CONFORMANCE row 16.0c, HANDOFF item 7).
- Never silent in text mode, as a property over real runs: unpack, survey, sanitize (plan,
  apply, undo), repack (plan, build), slots --check, config check/generate, install, replay,
  diag and indexes update say in text what the --json envelope carries, with the same exit code.
- An extraction replays into the same files whatever the mode and extension filter; a replay
  without its secret is refused and names the option to pass.
- The server: every UI file is served byte for byte, index.html carries the token and is never
  cached, nothing outside viwo/web is served; malformed bodies and a crashing route answer and
  the server keeps serving; `viwo serve` ends with its own code for strict preflight (4), a port
  in use (2) and Ctrl+C (0).

## 1.6.3 (2026-11-04)
- Coverage work (owner's target 98 % line / 95 % branch per file): child processes are measured
  (`[tool.coverage.run] patch = ["subprocess"]`, CI combines); property tests for `viwo slots
  --check`, `unpack --slot/--backend`, `patch`, `mod`, `trace`, `capture`, the indexes
  (validator faults, `indexes update`) and the third_party installer (every archive kind).
- Fixes they found: reinstalling a tool whose folder is locked (Windows: it is running) no
  longer half deletes it (the old folder moves aside and comes back); a build whose `find` file
  is missing leaves the installed tool in place; an unknown archive kind in tools.json is named;
  the RPA reader reads at most 80 bytes of a header (it read any non-RPA file up to its first
  newline) and quotes 16; `viwo trace` with an empty function list is refused (it traced
  nothing), `--functions ""` is no longer replaced by the default.
- `core/downloads.py`: the verified download, safe unzip/untar and folder swap the installer and
  the indexes share (the indexes' own swap removed).

## 1.6.2 (2026-11-04)
- Docs: current state only (CHANGELOG holds history; HANDOFF is the handover and the open work;
  CONFORMANCE regenerated: 165 implemented, 5 partial, 15 open).
- Fixes found by the docs pass: `POST /api/patch` and `POST /api/mod` are routed (the 14 view
  called them; a test now checks every route `api.js` calls); the `extraction`, `sorting` and
  `merger` switches gate what they name (`require`, `gated`); x64dbg and Cheat Engine handoffs
  are dynamic actions (the `capture` switch, one confirmation per game, the warnings; x64dbg
  runs a patched copy); 12.F VERSION DIFF in 12 ANALYSIS; 04 JOBS links patch and mod to 14;
  the game's Oodle DLL loads through `OS.load_native`; the never-written journal removed.

## 1.6.1 (2026-11-04)
- Rung D4, part: `viwo profile` (and `/api/runtime/profile`, PROFILE CPU in 13 RUNTIME): every
  thread of a running game sampled through the OS layer (Windows thread contexts without
  administrator rights, Linux perf); hot spots by module and nearest export, per thread.

## 1.6.0 (2026-11-04)
- Full audit (46 findings) fixed, each with a property test: the wheel ships `viwo/data/**` and
  the portable build adds every script module; a file an antivirus or a lock refuses, or a game
  file removed mid-run, is named and never fails an extraction; a reused agent copy never looks
  finished from the last run; patch offsets are bounded; duplicate mod names refused; a mod's AOB
  adaptation reads every patch back; a cancel anywhere in sanitize apply stays undoable;
  antivirus exclusions shared by concurrent jobs; new workspace folders get a cross-process lock;
  the probe cache keys on size and mtime; the API binds to this machine unless a LAN address is
  chosen; save-remaining needs an absolute destination; finished jobs bounded in memory; a failed
  dump leaves no file; backends no longer import core; the CLI prints every envelope warning.
- Typed decoders: `decode.slp` (Age of Empires SLP sprites to PNG with the game palette),
  Bannerlord TPAC textures to DDS (format and shape from the item metadata), Cyberpunk 2077
  archive members at their real paths from WolvenKit's path list (pin `cp77-hashes`).
- LoC reclaim: one patched-copy helper (repack, patch, mod, agent), one `RuntimeRequest` table
  for every runtime kind, the dead journal-overlay path and the `image.convert` slot removed,
  process listing through Toolhelp32. Budget `viwo = 13900`.
- Python pins hash-locked (`tools/pin_python.py`, `viwo/data/locks/`, `pip install
  --require-hashes`); a platform/version without wheels says why instead of installing unpinned.
- Rung D2 closed: the BepInEx IL2CPP agent verified on Among Us (120 interop assemblies).
- Developed as 1.5.2 (some test docstrings still say so).

## 1.5.1 (2026-11-04)
- Rung A4: `analysis.emulate` (`unicorn-emulate`) and `analysis.symbolic` (`angr-symbolic`) as
  worker tools (`tools.json` `workers`, `viwo/core/workers.py`): pip pins in `third_party/<id>/`,
  never imported, run as `python -I viwo/data/workers/<script>`; `viwo analyze --set KEY=VALUE`;
  routine options in 12 ANALYSIS. angr pinned at 9.2.223 (angr 10 crashes on Windows).
- A file an antivirus removes mid-copy is a named warning; preflight survives a dependency that
  cannot run alone.

## 1.5.0 (2026-11-04)
- Never silent: `Outcome.fallback` names the main backend's failure whenever the spare runs; an
  export that wrote nothing or left notes says so; progress stays on stderr with `--json`.
- Three arms in the UI and CLI: views declare an `arm` (static, dynamic, patching, global); arm
  homes with their end-to-end path; global strip (SYSTEM, JOBS, SETTINGS, game selector,
  workspace); new views 13 RUNTIME and 14 PATCHES + MODS; `viwo <arm>` lists one arm and `viwo
  <arm> <command>` runs a command (`viwo/cli_arms.py`).
- Games passes run against a committed version in a separate worktree.

## 1.4.7 (2026-11-04)
- Rung D3: `handoff.debug` (x64dbg, x32dbg for 32-bit PEs) and `handoff.memory` (Cheat Engine 7.6
  from Scoop's unpacked build, a ViWo table that attaches to the game); `viwo dump` (Windows
  `MiniDumpWriteDump`, Linux `/proc/<pid>/mem`) and `viwo trace` (frida-trace), job kinds `dump`
  and `trace`, routes `/api/runtime/*`.
- Rung D2: runtime agents (`viwo/contracts/runtime.py`): `runtime.unreal` = UE4SS 3.0.1 (writes
  `Mappings.usmap` and the object dump; verified on Void's Cave), `runtime.unity` = BepInEx 6
  be.785 for IL2CPP; `viwo agent`, job kind `agent`; `viwo record` (system loopback to WAV).
- First-run rule: every first-run dialog of a pinned tool is pre-answered off screen (x64dbg
  release notes, Cheat Engine CEShare and table-Lua prompt).
- Global `--features a,b`; plugin commands honour `--profile` and `--features`.
- Patched copies skip files the OS refuses to read and report them. Games pass fixes: VPK subsets
  with absent parts, PFH timestamp bit 0x40, UTF-8-safe integration report.

## 1.4.6 (2026-11-03)
- T1 complete: `rva` addresses (PE sections), `asm` edits assembled by Keystone's `kstool` (a
  pinned process, GPL-2), capstone disassembly in plans, whole-file verification, export of
  `<set>.diff.txt` and `<set>.aob.patch.json` into the copy's `.viwo-patched/`; core slot
  `patch.bytes` (`viwo-patcher`).
- T2 complete: mods carry their AOB patch sets, `requires` and `after`; `mod check` reports
  `adapts` for another game version; `mod apply` orders several mods and refuses conflicts.

## 1.4.5 (2026-11-03)
- Rung A3 version diff: the Ghidra export writes a mnemonic fingerprint per function; `viwo diff
  OLD NEW` and `POST /api/analysis/diff` pair functions by name, then by fingerprint.
- Rung T1 patch sets (`viwo/core/patchsets.py`, `viwo patch`, job kind `patch`): offset and AOB
  patches into a marked patched copy, read back, stackable.
- Rung T2 mod packages (`viwo/core/mods.py`, `viwo mod pack|check|apply`, job kind `mod`).
- Patching-arm CLI handlers in `viwo/cli_patch.py`; the CLI dispatcher is one table.

## 1.4.4 (2026-11-03)
- Temporary antivirus exclusions (`viwo/core/scan_exclusions.py`, `[startup] av_exclusions`):
  workspace, source and temp skip the real-time scan during a job (Defender, elevated only),
  journaled and undone at the next job after a crash.
- A2 complete: `analysis.python` (unrpyc, Ren'Py plugin) and `analysis.gdscript` (GDRE Tools,
  Godot plugin). Detect It Easy pinned for Linux.
- Review batch 5 (13 findings): analysis reruns start empty, `captureAfter` validated, OS-layer
  `config_home` / `data_home`, one `run_tool` for analyzers, `run()` pumps join after 1 s.

## 1.4.3 (2026-11-03)
- The game index holds 23 entries (one per verified title, the library games, Team Fortress 2,
  `unity-generic`, `rpgmaker-mv-generic`). TF2 joins the games pass with a VPK subset.

## 1.4.2 (2026-11-03)
- CTF flags for the library games (`sqc/ctf.json`): three shared baselines plus game-specific
  objectives; analysis flags run `viwo analyze` per target in the integration runner. The generic
  plugin proposes executables up to two folders down.

## 1.4.1 (2026-11-03)
- Rung A3 protector identification: `analysis.protector` = Detect It Easy 3.21 (`identify.json`,
  `identify.txt`). A second analyzer per target kind: `AnalysisRequest.slot`, `extras` in the
  listings, `viwo analyze --slot`.

## 1.4.0 (2026-11-03)
- Rung A2: `analysis.dotnet` (ilspycmd 11.2), `analysis.il2cpp` (Cpp2IL 2022.1 pre-release 21),
  `analysis.script` (unluac on the pinned JDK); `{java}` argv prefix. Verified on Baldi's
  Basics (646 C# files) and an IL2CPP title (80 stub assemblies).

## 1.3.7 (2026-11-03)
- Capture is unattended by default (30 s, `--auto 0` = attended with F12). A file the OS refuses
  to open is a run warning (`CollectReport.unreadable`), never a crash.

## 1.3.6 (2026-11-03)
- Rung D1: unattended RenderDoc capture (`--auto SECONDS`, API `captureAfter`): the game runs as a
  tracked child of `renderdoccmd capture -w`, `rd_trigger.py` takes one frame, the tree is
  stopped; the harvest also writes every shader's disassembly. Verified on ULTRAKILL.
- Minimal-prompt rule: qrenderdoc and Ghidra GUI first-run prompts pre-answered. OS `run()` reads
  through pump threads so a grandchild holding the pipes cannot hang it.

## 1.3.5 (2026-11-03)
- `tools/status_pdf.py` builds the status presentation (`tools/status_template.html`, Edge
  headless print) from the runs, the sqc suite, the CTF flags and the commit log.

## 1.3.4 (2026-11-03)
- Review batch 4: one media-type table (`viwo/core/media.py`), one progress `teller`, the
  sanitizer sink as a context field, one plugin-info loop, the pid check in the OS layer.

## 1.3.3 (2026-11-03)
- `taleworlds` plugin (Bannerlord TPAC, LZ4 blocks through the `lz4` pin). The Ghidra GUI
  handoff starts the JVM directly so the window is a tracked child. CTF flags sized five basic
  plus one per GB, with subsets for large games (`tools/games_pass.ps1`).

## 1.3.2 (2026-11-03)
- Container plugins from the owner's library: `genie` (Age of Empires DRS), `warscape` (Total
  War PFH4/PFH5 packs), `redengine` (Cyberpunk 2077 RDAR, Kraken inflated through the game's own
  Oodle DLL). Verified on real archives.

## 1.3.1 (2026-11-03)
- Review batch 2: one core context factory, `option_bool`, `count_files` in
  `contracts.workspace`, backends' `self_check_args` as the version table, the v1 payload parser
  in the API, plugins receive their `home` (no QuickBMS special case in boot).

## 1.3.0 (2026-11-03)
- Static analysis arm, rung A1: `viwo/contracts/analysis.py` (`AnalysisTarget`, `Analyzer`,
  `Handoff`, `LaunchSpec`), `EnginePlugin.analysis_targets(probe)`, `analysis.native` (Ghidra 12.2
  headless with `viwo/data/ghidra/ViwoExport.java`), `handoff.native` (Continue in Ghidra as a
  tracked child, `ProcessRunner.launch`), `viwo analyze`, `/api/analysis/*`, job kind `analyze`,
  12 ANALYSIS, the `analysis` feature. Ghidra and Temurin JDK 25 pinned; Ghidra on demand.
- `FolderProbe` returns case-preserved paths.

## 1.2.1 (2026-11-03)
- Conformance closure of all 592 clauses: inventory metrics from `verify_report`, the shared
  probe on plugin contexts, merger probe through `media.probe`, suffix-clash boot problem,
  derived capabilities, `--profile`, `GET /api/plugins` fields, `POST /api/jobs` wired, run-record
  context on extractions, process list through the OS layer, missing safety tests.

## 1.2.0 (2026-11-03)
- Contract 1.1 conformance batch: backend `network` and `parses_untrusted_in_process`,
  `self_check`, per-OS executables, manifest fields and option types, ini `contract` key with
  the major check, one `base =` level, value sources, `unarchive.upak` spare, `media.probe`,
  `export.godot`, conformance kit, L0 static tests, zstd/LZ4 stream rung, coverage floors, caps
  `[exceptions]` with expiry, run-record context (`viwo/core/records.py`), `viwo slots --check`,
  `unpack --slot/--backend`, `--quiet/--verbose`, `POST /api/jobs`.

## 1.1.1 (2026-11-03)
- Contract conformance audit (532 clauses, 23 defects, 34 gaps) recorded.

## 1.1.0 (2026-11-03)
- UI component library and functional/style boundary (`viwo/web/js/ui/`, `css/base.css`,
  themes `wormhole` and `plain`), lint and headless-browser smoke tests.
- Plugin add-ons: CLI commands (`cli_commands()`) and UI modules (`/plugins/<id>/ui.js`).
- Survey step events and numbered reports; cleanup as a visible job; `sqc/games.md` and
  `tools/integration_games.py`.

## 1.0.2 (2026-11-03)
- Handoff notes only.

## 1.0.1 (2026-11-03)
- Fixes from the first sqc run and the real-browser smoke: zip member names, stale sanitizer
  plans refused, unknown plugin ids refused (exit 2), `.nw` as zip, installer antivirus failure
  reported; Linux fake-tool shebang.

## 1.0.0 (2026-11-03): first product release
- Philosophy: no policy boundaries in code, a disclaimer instead; every refusal based on what a
  game is became a warning plus one confirmation.
- Startup installer: every tool pinned in `viwo/data/tools.json` (HTTPS, size, sha256) installs
  into `third_party/`; landing screen driven by the preflight job; 05 SYSTEM install and
  maintenance; 10 CAPTURE and 11 SETTINGS; per-game indexes (`indexes/`, `viwo install --game`,
  `viwo indexes update`); drop-in plugins; Ren'Py `.rpyc` decompile; Unity meshes to OBJ;
  `viwo diag`; the `sqc/` manual suite. Released as wheel, sdist and portable Windows zip.

## 0.3.0, 0.2.1, 0.2.0 (2026-11-02)
- 0.3.0: the 1.0 feature batch above. 0.2.1: `tools/version.py` and the pre-commit guard; LF
  line endings. 0.2.0: plan to automate unrar, QuickBMS, DataTool and RenderDoc.

## Before 0.2.0
- The v1 application (RPy Extractor) was hotfixed (game files copied, never moved; workspace
  marker; API token, JSON-only, Host check; safe archive extraction), then replaced. Prototype A
  built the core (contracts, OS layers, ini wiring, slots with failover, stage runner, workspace,
  jobs, CLI, web UI; Ren'Py, Unity, Godot). Prototype B added Unreal, Doom, RPG Maker, KiriKiri,
  Electron, Source, Bethesda, Overwatch and QuickBMS, round trip into a patched copy, mixed mode,
  the sanitizer, the RenderDoc capture pilot and the coverage ladder (carver, streams, decoders,
  survey).
