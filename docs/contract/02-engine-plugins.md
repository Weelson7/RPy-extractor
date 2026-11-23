# 2. Engine plugin contract

A plugin describes one engine (`viwo/contracts/plugin.py`). Core runs the stages (doc 3) and
calls the plugin's hooks. Only `manifest` and `detect` are required; every other hook has a
no-op default, so the smallest useful plugin is "detect, plus an unarchive slot and its backend".

## 2.1 Manifest

```text
PluginManifest
  plugin_id      slug [a-z][a-z0-9_-]{1,31}, unique; not mixed | auto | core | none
  name, version, description
  engine_type    reported as detection.type / extractorType
  contract       major must equal CONTRACT_VERSION's major
  priority       tie-breaker when detection confidence is equal
  options        [PluginOption]       the UI renders a form from these
  tos_sensitive  true: every run, capture and repack carries a warning; real-data tests by the
                 independent operator (doc 17.4b); never a refusal
  builtin        false for drop-ins ("ADDED BY YOU" in the UI)
  capabilities   subset of detect unpack export pack decode inventory verify sanitize analyze;
                 derived from the hooks and slots when empty
  dependencies   dependency ids for people (backends declare the real DependencySpec)
  os_layers      empty = every OS layer; else a subset of linux, windows
  engine         a game plugin (2.10): the id of the engine plugin it belongs to; "" otherwise
  profile        a built-in's own distro profile (doc 9): `<os>-<profile>.ini` with only it
                 on; "" = it joins the shared `custom` profile

PluginOption { key, label, kind: string|secret|bool|int|float|choice|path, default, choices, help }
```

`option_bool(options, key)` is the one reading of a `bool` option (`on/true/1/yes`). Options of
kind `secret` (Unreal AES key, Godot encryption key) are never logged, never written to the ini,
and stored as `<secret>` in run records.

## 2.2 Hooks

```text
detect(probe) -> DetectionResult                                   REQUIRED
configure(options)                                                 [options.<id>] at boot
slot_definitions() -> [SlotDefinition]                             doc 8
backends() -> [Backend]                                            doc 8
source_roots(game_root, probe) -> [Path]                           default [game_root]
skip_dirs() -> [str]
claimed_suffixes() -> [str]                                        exported, so not carved
export_slot() -> str                                               slot run in EXPORT, "" none
pack_slot(unarchive_slot) -> str                                   round trip (doc 18)
inventory(ctx) -> [str]                                            empty = no completeness claim
verify_report(ctx, inventory, export, collected) -> VerifyReport   { ok, warnings, expected, found }
analysis_targets(probe) -> [AnalysisTarget]                        doc 6.1
sanitizer_rules() -> [SanitizerRule]                               ids start with "<plugin id>."
cli_commands() -> [CliCommand]                                     add-on subcommands
ui_module() -> Path | None                                         served as /plugins/<id>/ui.js
home                                                               the ViWo install folder, set at boot
```

Rules:

- `detect` is fast and pure: it reads only the probe, runs no tool, and returns the same result
  when called twice.
- Hooks write only into `ctx.staging` and `ctx.scratch`; tools run through `ctx.os`; no `print`.
- Expected failures are return values (an `Outcome` with a kind, `VerifyReport.warnings`). An
  exception is a bug; core catches it and records it against the plugin (`plugins[].error`).
- **Inventory items** name what COLLECT records (doc 0.4): `<container>/<member>` for a
  container's member (the container game-relative, the member as the container names it), the
  game-relative path for a loose file. When a plugin keeps one, core counts it in VERIFY
  (`pipeline/checks.py`): `expected` is the items of the extensions the run selected, `found`
  the ones COLLECT recorded, and every item that did not come out is one verify warning (how
  many, the first five by name). `VerifyReport.expected`/`found` count only for a plugin
  without an inventory. Source keeps one: every member its VPK directories list.
- Sanitizer rules subclass `SanitizerRule` or `BatchRule` of `viwo/contracts/sanitizer.py`
  (doc 5.2), so a plugin reaches them without importing core.

## 2.3 Services core provides

```text
GameProbe (FolderProbe)     built once per request, shared by all plugins; bounded file count
  root
  has_name(*names)          case-insensitive basename match
  find(pattern, limit)      case-insensitive glob ("**/*.pak", "*_Data")
  with_suffix(*suffixes)
  head(path, size=64) / tail(path, size=64)    cached, for magic bytes and exe trailers
  paths are case-preserved; the cache keys on size and mtime

ExtractionContext           per request and per plugin
  request_id, game_root, staging, scratch, os, detection, selected_exts, options,
  progress, cancel, source, probe, workspace (the run's workspace: what other arms left there),
  games (the run's game plugins of this engine, 2.10)
  keys(slot) -> [bytes]     the candidates of a keys.* slot (doc 14.2 #4), in memory only; None
                            in a context core did not build
  log(message, level, stage);  tool_output(stage, every, mask) -> on_line relay (masks a secret)
```

## 2.4 DetectionResult

`DetectionResult { engine_type, confidence, evidence[], plugin_id }`, serialized as
`{type, confidence, evidence}`. `generic` always answers 0.4.

| Confidence | Meaning |
|------------|---------|
| 0.00 | not this engine |
| 0.01-0.49 | weak hints only |
| 0.50-0.74 | probable |
| 0.75-1.00 | strong (marker files or magic bytes) |

## 2.5 Unpacking through slots

A plugin introduces `unarchive.*` slots for its formats and ships their backends; core owns
`unarchive.zip`, `.tar`, `.7z`, `.rar`. Core runs the recursive unpack loop (queue, seen-set, one
`archive_NNNNN_<uuid8>` folder per archive, depth limit 10) and picks the slot for each file by
the slots' own identifiers (head and tail bytes, embedded chunks), then the longest suffix, then
magic bytes, then the identifiers of `fallback` slots (QuickBMS scripts never take a format a
reader already claims). The queue and every stage stop on cancel; a cancelled main never starts
the spare. Every in-process unarchive backend writes members through
`contracts.workspace.Names`: a name that leads out (absolute, `..`, a link inside the
destination) is skipped and counted; a name Windows cannot write (`< > " | ? * :`, control
characters, device names, a trailing dot or space) is altered to a writable one and recorded in
`.viwo-names.json` beside the files, so COLLECT gives provenance the archive's own name and the
round trip writes the member back under it. Every skip, alteration and short read is a note the
unpack stage says.

## 2.6 Dependencies

```text
DependencySpec
  dep_id, label
  kind          executable | python | runtime
  requirement   required | recommended | optional
  import_name   (python)
  executables   (names...) or { os_id: (names...) }    bare names; the OS layer adds suffixes
  install_dirs  folder names searched under the known install roots
  env_var, hint
```

Dependencies belong to the backend that declares them. `/api/dependencies`, `viwo slots` and 05
SYSTEM combine them; `category` is the owner id. The tools ViWo's own backends need are
described once, in `viwo/data/dependencies.json` (`DependencySpec.of(id)`; their pins, versions
and checksums are in `tools.json`, doc 10); a plugin of others builds its own `DependencySpec`.

## 2.7 Built-in plugins

Detection markers live in each plugin's `detect()`; slot defaults in doc 8.4.

| Plugin | Formats and work | Options |
|--------|------------------|---------|
| generic | loose files and plain archives; proposes executables (two folders down) and Lua bytecode for analysis | - |
| renpy | `unarchive.rpa` (safe reader, unrpa spare), `decode.rpyc`, `analysis.python`, `pack.rpa`; source root `game/`; sanitizer rule `renpy.cache` (the `.rpyb` caches Ren'Py rebuilds, to the trash) | `decompile` (bool) |
| unity | `export.unity` (UnityPy, AssetStudioModCLI spare), `unarchive.unitypackage`, `pack.unity`, `runtime.unity` (BepInEx); IL2CPP and managed targets | `include_cache`, `meshes`, `objects` (bool; `objects`: videos, fonts, shaders and every other object as JSON) |
| godot | `unarchive.pck` (embedded PCK carving), `export.godot`, `pack.pck`, `analysis.gdscript`, `decode.ctex` (imported `.ctex`/`.stex` textures to PNG and back) | `encryption_key` (secret), `recover` (bool) |
| unreal | `unarchive.upak` (repak, QuickBMS spare), `unarchive.utoc` (retoc), `pack.upak` (`_P.pak`), `runtime.unreal` (UE4SS), `export.unreal` (UnrealAssetScout: textures, models, animations, sounds, JSON; mappings from the agent), `decode.locres` (localization tables to JSON and back, versions 0-3); AES per D18, its finder the `keys.unreal` slot | `aes_key` (secret), `find_key` (bool), `usmap` (path), `engine` (string) |
| doom | `unarchive.wad` (PNG, WAV, MIDI, maps), `pack.wad` (edits converted back through the palette) | `raw_lumps` (bool) |
| rpgmaker | `unarchive.rgssad`, `export.rpgmaker` (MV/MZ decryption), `pack.rpgmaker`, `pack.rgssad` | - |
| kirikiri | `unarchive.xp3` (unencrypted entries; per-title ciphers reported), `pack.xp3` (the next patch archive) | - |
| love2d | `unarchive.love` (the game's zip: `.love`, or appended to the executable with `love.dll` beside it), `pack.love` (the zip rebuilt, behind the executable's bytes when fused) | - |
| xna | XNA, FNA and MonoGame: `decode.xnb` (Texture2D to PNG, SoundEffect to WAV, and back; uncompressed, LZ4 and LZX files (XNA's XMemCompress through the first-party `lzx.py`; an edited LZX file is rewritten uncompressed); XNA 3.x files and other content refused by name); the `.xnb` files themselves are loose | - |
| wolfrpg | Wolf RPG Editor games: `unarchive.wolf` (`Data.wolf` / `*.wolf`, DxLib's DXArchive version 6; every raw member, DXA-compressed members and a wrong key refused by name), `pack.wolf` (the archive rebuilt with the edits, stored raw); the format is implemented from its public description, not verified against a real game | `decryption_key` (secret) |
| kaitai | a second plugin form (13.2a): bundled Kaitai `.ksy` definitions interpreted first-party (never the GPL compiler) and surfaced as `decode.kaitai_<id>` slots that parse a format into a JSON tree (one way); detects nothing, runs only when selected; proof `defs/wav.ksy` | - |
| ags | `unarchive.clib` (CLIB packfiles, versions 6 to 30, alone or behind the executable, with their other parts), `pack.clib` (rebuilt in its own version) | - |
| defold | `unarchive.arci` (`game.arci` + `game.arcd`, named by `game.dmanifest`; LZ4 through the `lz4` package; encrypted resources decrypted (XTEA-CTR) when a key verifies, else refused by name), `pack.arci` (data and index rewritten, hashes and manifest kept; an edited encrypted resource re-encrypted) | `decryption_key` (secret) |
| electron | `unarchive.asar` (`package.nw` is a zip), `pack.asar`; wrapper re-detection (doc 3.1) | - |
| source | `unarchive.vpk` (v1/v2, multi-part, absent parts skipped), `pack.vpk` (override VPK in `custom/`), `decode.vtf` (VTF textures to PNG); inventory: every member the VPK directories list | - |
| bethesda | `unarchive.bsa`, `unarchive.ba2` (textures rebuilt as DDS), `pack.bsa`/`pack.ba2` (loose files in `Data/`) | - |
| genie | `unarchive.drs`, `decode.slp` (SLP sprites to PNG with the game palette), `pack.drs` | - |
| warscape | `unarchive.pack` (Total War PFH4/PFH5), `pack.pack` (a movie pack in `data/`), `decode.loc` (localisation to JSON), `export.warscape` (DB tables to JSON with the game's RPFM schema) | - |
| redengine | REDengine 4, detected by its RDAR archives: `unarchive.archive` (RDAR; Kraken through the game's Oodle DLL; names from the path list a game plugin supplies), `decode.cr2w` (WolvenKit: textures to PNG, meshes and animations to glTF, every resource to JSON), `pack.archive` (WolvenKit: override archive in `archive/pc/mod`); its verify reports the installed mods' conflicts (`archive/pc/mod` by name, then REDmod `mods/*/archives`; first wins) | - |
| cyberpunk2077 | game plugin of redengine: the path list `cp77-hashes` (`name_lists`), `decode.redscripts` (redscript: `final.redscripts` to source); detected by the game's executables | `decompile` (bool) |
| taleworlds | TaleWorlds engine, detected by its TPAC packages: `unarchive.tpac` (textures to DDS), `pack.tpac` (the package rewritten member by member, every other byte kept) | - |
| bannerlord | game plugin of taleworlds: the title, by its executables | - |
| quickbms | `unarchive.bms`: one `<ext>.bms` script per format from `[options.quickbms] scripts` (default `third_party/quickbms/scripts/`) | - |
| overwatch | `export.overwatch` (DataTool, Windows); `tos_sensitive`: a reminder in every run's warnings | `modes` (string); `query` (string, `;` between entries, each one DataTool argument: `mode: words` goes to that extract mode, `--flag` to every extract mode, any other entry to `extract-unlocks`; an entry no running mode takes is said in the notes); `models` (`glb` or `owmdl`) |
| qt | Qt apps (doc 13.8): `unarchive.rcc` (resource collections, versions 1-3), `decode.qm` (translations to JSON, one way), `pack.rcc` (rebuilt, name and node trees kept); `viwo qt-resources` carves QML/JS/QSS/SVG compiled into an exe or DLL (names not recovered from a stripped binary) | - |
| chromium | Chrome/CEF/Electron `.pak` resource packs: `unarchive.pak` (DataPack versions 4 and 5, every id and version-5 alias), `pack.pak` (rebuilt byte-faithfully with the edited ids) | - |
| pyfrozen | frozen Python: `unarchive.pyi` (PyInstaller CArchive + inner PYZ: data, binaries, every module as `.pyc`), `pack.pyi` (the exe rebuilt, bootloader and cookie kept), `decode.pyc` (disassembly, host version only); py2exe/cx_Freeze `library.zip` through the core zip | - |
| dotnet | .NET assemblies: `unarchive.dotnet` (embedded managed resources through the ECMA-335 metadata), `pack.resources` (same-size write back, a size change refused by name), and `dotnet_assembly` analysis targets for the C# static view via the pinned ILSpy handoff | - |
| java | Java `unarchive.jar` / `pack.jar` (`.jar`/`.war`/`.ear`, a zip, through the core zip path); no class decompiler is pinned, so `.class` files stay bytecode | - |
| gamemaker | GameMaker Studio `FORM` data files (`data.win`, `game.unx`, `.ios`, `.droid`, audiogroup `.dat`): `unarchive.gamemaker` surfaces every chunk (`chunks/<NAME>.bin`), the TXTR texture PNGs, the AUDO audio and the STRG strings (`strings.json`, a read-only view); `pack.gamemaker` writes an edited member back in place when its size is unchanged and refuses a size change, and the read-only `strings.json`, by name (no re-chunk). UndertaleModTool (GPL) is never imported | - |
| android | Android packages, static arm only (doc 13.9; no device, emulator or adb): `unarchive.apk` (a zip whose root holds a binary `AndroidManifest.xml`, whatever its name), `unarchive.apks` (`.xapk`/`.apks`/`.apkm` bundles: their APKs and OBBs, opened in turn by the unpack loop; an encrypted bundle needs its key), `unarchive.obb` (an expansion file that is a zip); `decode.axml` (binary XML to text XML and back), `decode.arsc` (`resources.arsc` to JSON, values back in place); `pack.apk` (rebuilt member-faithful and zipaligned, the old signature dropped, re-signed by the pinned `uber-apk-signer` or left unsigned and said), `pack.apks`, `pack.obb`. Engines inside are re-detected (doc 3.1). `classes.dex` is extracted, not decompiled | `keystore` (path), `key_alias` (string), `keystore_password`, `key_password` (secret): the key that signs a rebuilt APK; empty: the tool's debug key |
| tyranoscript | TyranoScript / TyranoBuilder games: loose HTML5/JS (`tyrano/` engine, `data/scenario/*.ks`, `data/system/Config.tjs`, assets as plain files). Detection by the `tyrano/` folder plus scenario/config (not the shell or the `.ks`/`.tjs` names alone); the scenario scripts are its inventory; the engine packs nothing, so the round trip is loose files in the patched copy. A shell (`app.asar`, `package.nw`) is unpacked by `electron` first | - |

## 2.8 Discovery and drop-ins

Nothing is hardcoded (`viwo/core/wiring/registry.py`, guide in `docs/plugins.md`):

- **Built-ins:** every package under `viwo/plugins/`; the class is named by `PLUGIN = "ClassName"`
  or is the module's single `EnginePlugin` subclass; the id is `manifest.plugin_id`. On by
  default; `[plugins] <id> = off` disables one. `generic` is always on.
- **Drop-ins:** each folder with a `plugin.json` under `[plugins] custom_dirs`: `id`, `module` +
  `class` (or `entry = "module:Class"`), `requires` (`{"viwo": ">=1.0"}`), `enabled`, `override`,
  `cli` (opt-in for CLI add-ons), `ui`. Opt-in: `[plugins] <id> = on` or `custom.<id> = on`, else
  `enabled` from the manifest.
- **Installed packages:** the `viwo.plugins` entry-point group, treated like drop-ins.

A drop-in runs inside ViWo with the user's permissions. Loading validates the manifest, the
contract major and the conformance checks (2.9); a failure disables only that plugin and is listed
in the startup problems (`viwo info`, SYSTEM).

## 2.9 Plugin conformance (`viwo/core/wiring/conformance.py`, `tests/test_conformance_kit.py`)

- The id is a valid slug; the contract major matches; `engine_type` is set; option keys are
  unique and of known kinds; `os_layers` are known and include the host.
- Capabilities are known and include `detect`; a plugin with `unarchive.*` slots has `unpack`.
- `detect()` on an empty probe does not raise, is stable, and names this plugin.
- Slot ids are unique and owned by the plugin; suffixes are lowercase and dotted; two plugins
  claiming one suffix is a boot problem naming the winner (`suffix_clashes`).
- A dependency id is declared with one label.
- Sandbox: the conformance kit records the files under the test root before and after `export`;
  any change outside the plugin's staging fails.

The kit runs over the built-ins, `examples/plugins/hello/` and every folder in
`VIWO_PLUGIN_DIRS`, so a third-party plugin runs the same checks against its own folder.

## 2.10 Game plugins

Plugins are per engine, and each engine has game plugins: what one title adds on top of its
engine (owner's decision). An engine plugin keeps only what holds for every game on that engine
and detects by the engine's own file signatures, never by a game's executable name (an engine's
own launcher, such as Source's `hl2.exe` and `srcds.exe`, is the engine's, not a title's). Data
the engine's format needs per title, with no per-title code, may sit in the engine plugin as a
table (Warscape's RPFM schema per title: `warscape/db.py` `GAMES`); a game
plugin holds the title's own tooling and data (Cyberpunk 2077: its path list, redscript; later
its runtime frameworks such as Cyber Engine Tweaks). Overwatch stays one plugin of its own
(DataTool works for that title only).

- **Form:** an ordinary plugin (2.1-2.3) whose manifest names its engine (`engine`). Built-ins
  live in `viwo/plugins/<engine>/games/<game>/` and are discovered with their engine; a game
  plugin found under another engine, or naming another one, is a discovery problem. A game
  plugin may import its own engine's package, never another plugin.
- **Selection:** a game plugin never runs alone: one whose engine plugin is off is not loaded
  (named in the problems). A chosen game plugin (SINGLE, MIXED) brings its engine first; the game plugins of the chosen engines whose own detection names their game
  (confidence >= 0.5) run after them (`core/pipeline/select.py` `with_games`).
- **What it supplies:** its own slots and backends (a decoder runs only for the plugins chosen
  for the game, doc 8), options under `[options.<game id>]`, analysis targets, CLI commands; the
  engine's backends read what the run's game plugins of their engine offer through
  `ExtractionContext.games` (REDengine: `name_lists`, the path lists that name archive members).
  Data with no backend of its own (a path list) is declared by a slot-less backend so the
  preflight installs it and SYSTEM lists it.
