# Changelog

Versions follow `va.b.c` (`tools/version.py`): `a` product release, `b` feature, `c` every
commit. Each tag's commit message carries the full list; this file keeps what changed for a user
or a maintainer. Newest first.

## 1.16.5 (2026-11-05)
- Unity IL2CPP builds: MonoBehaviour data comes out with its fields. The export runs Cpp2IL
  (pinned, its own process) once to rebuild stand-in assemblies from GameAssembly and the
  metadata, and gives them to UnityPy's layout generator; on Schedule I's resources.assets 270
  of 745 MonoBehaviours carry their fields (6 before). A missing Cpp2IL or an empty run is said.

## 1.16.4 (2026-11-05)
- `pack.wad`: Doom WADs are written back (found missing by the deep pass on Freedoom): edited
  pictures and flats go back through the game's palette (grAb offsets kept), sounds to DMX, every
  other lump as it was; verified on Freedoom (a repainted sprite comes back).
- `decode.vtf`: Source textures to PNG in process (the largest mipmap of the first frame; DXT1,
  DXT3, DXT5 and the 8-bit formats; VTF 7.0-7.5).

## 1.16.3 (2026-11-05)
The patching arm for the engines ViWo reads itself (from the deep pass: Doom had no packer,
nor had most of these): `pack.asar` (rebuilt, integrity hashes recomputed), `pack.vpk` (an
override VPK in `custom/`), `pack.xp3` (the next KiriKiri patch archive), `pack.bsa`/`pack.ba2`
(loose files in `Data/`), `pack.pack` (a Warscape movie pack; PFH5+ refused by name),
`pack.rgssad` (XP/VX/VX Ace rebuilt under their keys), `pack.drs` (rebuilt). Each override is
written where its engine loads changes over its own archives and read back.
- Fix: a DRS table with a four-letter type (`anib`, AoE's `bina`) lost a letter.
- Fix: headless Ghidra ran with its 2 GB default heap and died on a large executable
  (`OutOfMemoryError`, found by the deep pass on a Godot game); it now gets half the machine's
  memory (2 to 16 GB) unless the user set `GHIDRA_MAXMEM`. The OS layer says the machine's
  memory (`memory_bytes`).
- Deep pass: ViWo's own warnings are read from the envelope; emulate/symbolic, which need a
  routine address, are skipped and said.
- Fix: `viwo agent` lent Unity's agent (BepInEx) to any game whose engine has none (a Godot game
  got "a Mono build"); only a plugin that detected the game gives its agent, a game plugin's
  first, and the error names the engines found.

## 1.16.2 (2026-11-05)
- The presentation tooling (`tools/presentation/`): frames of every view driven through
  headless Edge on a real game; the technical PDF (architecture, the three arms and failover in
  mermaid charts, every view with its screenshot, reference tables generated from the code:
  plugins, slots, pinned tools, CLI, HTTP routes, conformance); the demo video (MP4, captions
  in a band under the frame, no voice) through the pinned ffmpeg. mermaid 12.3.0 is pinned
  (on demand). Deep pass: a companion read with its container (`.resS`, `.ucas`) counts as read.

## 1.16.1 (2026-11-05)
- `tools/deep_pass.py`: every capability on one real game, judged on its output (the accounting
  of every game byte and workspace file, decoded files opened by real readers, a contact sheet,
  cleanup undo, every analysis target, a real edit repacked and read back, an AOB patch set, a
  mod, and the dynamic arm with `--dynamic`). Verified on Freedoom: every byte read, 80 % of the
  workspace in open formats, every sampled PNG, WAV and text opens. Found there: Doom WADs have
  no packer yet (the patching arm does not reach them). `tools/status_pdf.py` is retired (the
  technical PDF replaces it).

## 1.16.0 (2026-11-05)
Game plugins (doc 2.10, owner's decision: plugins per engine, each engine with game plugins):
- An engine plugin keeps what holds for every game on its engine and detects by the engine's own
  file signatures; what one title adds lives in a game plugin under the engine
  (`viwo/plugins/<engine>/games/<game>/`), discovered with it, run only with it (a chosen game
  plugin brings its engine; a chosen engine brings the game plugins that detect their game),
  supplying the engine's backends through `ExtractionContext.games`.
- REDengine 4 is now engine-only (RDAR archives, CR2W through WolvenKit, the override pack, mod
  conflicts) and detects by its RDAR archives; the Cyberpunk 2077 game plugin holds the path list
  (`cp77-hashes`, read by the engine's reader through `name_lists`), redscript decompilation and
  its `decompile` option (now `[options.cyberpunk2077]`), and the title's executables.
- TaleWorlds detects by its TPAC packages; the Bannerlord game plugin names the title.
- SETTINGS shows a game plugin as "game plugin of <engine>". Contract 1.2 (optional fields).

## 1.15.6 (2026-11-04)
A backend quality review and a UX/UI review (independent, every finding verified):
- Member names Windows cannot write (`< > " | ? * :`, control characters, device names, a
  trailing dot or space) are no longer lost: every in-process unpacker (zip, tar, RPA, VPK, XP3,
  BSA, BA2, RGSSAD, ASAR, TPAC, PFH, RDAR) writes them under an altered name and records the
  original beside the files; provenance gives the original, so a repack writes the member back
  under it. One such name used to fail a whole archive.
- Fix: junctions were still followed by the UNPACK walk, the patched copy and plugin scans
  (Unreal keys and assets, RPG Maker MV, Total War DB, Godot, Doom, Bink, Unity): one walker
  (`contracts.workspace.files`) never enters a linked folder; the copy names the ones it skips.
- Fix: repack took its lock inside the game folder before refusing it; a mod zip could be
  written into the game folder. Both are refused first.
- Fix: a LAN peer could stream workspace files through `/preview/` without the token; it now
  needs the token's cookie. Attended capture (0 seconds) became a 30 s auto capture.
- Fix: a key cut across the 200-character output limit could show its first half; masking runs
  first. Godot's errors are masked; GDRE recovery gets the key and the game's main pack.
- Fix: QuickBMS scripts claimed formats a built-in reader knows; they are now a fallback.
- Fix: cancel was not honoured during UNPACK and EXPORT and a killed main started the spare.
- Fix: a file repeated across archives was decoded once per copy; decode and capture dropped the
  files the OS refused in their second collect; the probe's entry bound and the 500-script cap
  of Ren'Py and Godot analysis cut silently (bound raised and said; caps removed).
- Fix: the x64dbg and Cheat Engine handoffs edited the user's own installs; they pre-answer
  prompts only in ViWo's copy now. The job table is guarded by a lock.
- UX: EXTRACT's "replace" dialog defaults to NEW FOLDER and says REPLACE deletes edits too;
  the extension filter applies to what ends up in the workspace (IMAGES keeps the textures a
  decoder makes) and says what it left out; RESULT is brought into view after a run.
- UX: SURVEY no longer splits one game whose files sit in folders (Cyberpunk) into several;
  SORT keeps its progress across TRASH and remembers KEEP per workspace; SETTINGS keeps pending
  changes when you come back; EXTRACT, ANALYSIS and SURVEY follow the top bar's game.
- UX: tab codes in JOBS and MERGER come from the live numbering; the arm homes start with
  PICK A GAME FOLDER when none is set, drop roadmap codes and say when a step opens in another
  arm; PATCHES asks for the copy folder before APPLY and labels the mod fields per action;
  turning on ANALYSIS or CAPTURE installs what they need in the background (JOBS), and a CLI
  install hint points to SYSTEM.

## 1.15.5 (2026-11-04)
Third audit (hostile input, completeness, the walk; an independent review, every finding verified):
- Fix: unpackers skipped entries silently. VPK, XP3, BSA, BA2, RGSSAD, ASAR, TPAC and RPA now
  count every skip by reason (unsafe name, missing part file, cut short) and say it; the unpack
  stage logs every note as a warning and lists it among the run's warnings.
- Fix: a declared size of 0 let zlib and LZ4 inflate without a limit (XP3, BSA): bounded to 1.
- Fix: RPA member names went through a resolve check only; now `safe_member` + `inside` (NTFS
  streams, device names, links). A member shorter than its index says is written and said.
- Fix: a crafted SLP row or Doom column could replay one long command stream for every row:
  both are bounded by their width or height.
- Fix: RPG Maker MV took System.json's key unchecked; a key that does not open the images is
  replaced by the one the PNG signature gives (said), the packer checks the game's images, and
  a file without the RPGMV header is kept as it is (said) instead of dropped.
- Fix: a junction in a game folder was walked into (survey, probe, collect, the game snapshot,
  the capture policy): link-like folders are never entered.
- Fix: what the game writes into its own folder during a capture is said as a warning.
- Fix: an engine found inside a wrapper (an MV game in an Electron asar) mapped its exports to
  paths of the unpacked wrapper; they are now derived, never written back to a wrong container.
- Fix: unluac gave `main.lua` and `main.luac` one output name; both are kept.

## 1.15.4 (2026-11-04)
Second audit (writes, the API, installs; an independent review, every finding verified):
- Fix: a game folder (or any folder of the user's) opened as the workspace could be curated:
  KEEP ONLY SELECTED moved the game's folders to a `.trash` inside it and CLEAR TRASH deleted
  them; cleanup could rename game files. Every write into a folder that is neither a ViWo
  workspace nor a patched copy is now refused, and read-only calls there take no lock.
- Fix: "replace" could delete the game being extracted when the game sat inside the workspace,
  and could clear a default workspace folder holding the user's files. Both are refused.
- Fix: a merger build wrote a lock into the folder it read (a game folder, or a read-only one
  that answered 500); a mistyped working folder silently became the workspace; two candidates
  whose names reduce alike overwrote one video. Outputs now take a free name, a wrong folder is
  said, and a read-only error is named.
- Fix: repack and the analysis diff took relative paths (doc 4.1 rule 6); now absolute only.
- Fix: Python pins installed with `--upgrade`, and a pin bumped after a ViWo install is
  installed again (a marker records what ViWo installed; packages found elsewhere are left).
- Fix: a patch whose file the copy step could not copy failed the whole job; it now fails alone.
- Fix: on a LAN bind every peer could read the API token from the page; it goes to this
  machine, or to a LAN peer with the `?key=` link `viwo serve` prints (doc 4.1 rule 1).

## 1.15.3 (2026-11-04)
Audit of the 1.7-1.15 work (an independent review, every finding verified and fixed):
- Unity: the MonoBehaviour layout generator reached only the first group of files; later
  bundles were counted as "layout not in the build". It is now made once and given to every
  environment. A string UnityPy kept as escaped bytes broke the whole `.objects.json` (the
  separator was written before the entry failed); entries are serialised first and such
  strings written with JSON escapes. Dump files are closed after each group and reopened to
  append (thousands of bundles no longer exhaust the descriptors), and closed on any error.
- Unreal: the AES key on UnrealAssetScout's command line is masked in whatever the tool says
  (it could have reached the run record); retoc's per-container staging folder is removed once
  the tool ran (a copy across volumes kept every `.ucas` until the run ended).
- Cyberpunk: an edited REDmod archive (`mods/<name>/archives/`) gets its override in
  `archive/pc/mod`, where the game loads it; an archive under neither layout is refused with
  the reason instead of an override the game never reads, or one written outside the copy.
  WolvenKit's settings are only written into ViWo's own copy, never a user's install.
- Total War: a DB header whose row count cannot fit in the table is refused (a crafted pack
  could build billions of empty rows).
- Decode: the empty-file filter is linear. UI: hints name panels by title (BEFORE YOU START,
  TARGET FOLDER...), no longer by the fixed codes the live numbering replaced.

## 1.15.2 (2026-11-04)
- Tests: the mixed-mode pairwise test runs every plugin alone and 13 groups of six that cover
  every pair of the 17 plugins (a covering design, checked by its own test), instead of all 136
  pairs one by one: 257 s to 50 s with the same pairwise property.
- HANDOFF: the completeness findings kept for the open rows (Unity IL2CPP fields, Unreal glTF,
  REDengine TweakDB), the games this machine can verify, and the UX/UI review done at 1.12.0.

## 1.15.1 (2026-11-04)
- Fix: vgmstream (`decode.audio`) wrote nothing: its `?f` output wildcard is the whole input
  path, so `<dest>/?f_?s.wav` named a file inside a folder that does not exist, and the audio
  fell to ffmpeg (which cannot read Wwise, FMOD or Bink Audio) or failed. The output name is now
  the file's own stem (`<name>_<n>.wav`). FMOD Studio banks (`.bank`) join the audio decoded:
  verified on a Bannerlord bank, 344 streams to WAV in 4 s.
- Fix: a request the server refused before reading its body (403, 413, 415) could reach the
  client as a connection reset instead of the answer (Windows resets over unread data, about one
  run in eight): the server now answers with `Connection: close` and takes in what was sent.
- The decode stage skips empty files with one line (CLEANUP lists them; Rome II ships three
  empty `.dds`), and a decoder's failure is said by the tool's telling line ("Invalid data
  found...") instead of the end of a path it echoed. The Bink 2 decoder moved to
  `core/decode_bink.py`.

## 1.15.0 (2026-11-04)
- Completeness contract (doc 16.0c) on Total War, valid for every Warscape game: `.loc`
  localisation tables decode to JSON in ViWo's own code (`decode.loc`), and DB tables to JSON
  (`export.warscape`, one file per table under `db/`) read by ViWo with the game's RPFM schema
  (pinned per game, 14 games, MIT, installed when asked: `viwo install rpfm-schema-<game>`). A
  table whose version the schema lacks is tried against its other definitions (reading to the
  last byte is the check); tables the schema lacks or misreads are counted and named. Detection
  now knows every one of those games' executables. Verified on Rome II: 191 `.loc` tables
  (122,423 entries) and 611 DB tables with JSON out of the real packs.

## 1.14.0 (2026-11-04)
- Completeness contract (doc 16.0c) on Unreal, valid for every UE4/UE5 game: the new
  `export.unreal` slot runs UnrealAssetScout (pinned `uas` 0.5.0, MIT, CUE4Parse inside,
  self-contained Windows build): textures to PNG, models and animations (UEFormat), sounds and
  every package as JSON. The engine version is read from the game's own binaries (the
  `++UE5+Release-5.x` build string; option `engine` overrides); cooked UE5 assets need the
  game's mappings, taken from the `.usmap` the RUNTIME agent (UE4SS) wrote into the workspace
  (option `usmap`); without them the packages that need them are counted and the way to get
  them is named. Verified on a UE5.1 game: the agent's mappings, then 695 PNG, 122 models,
  3 animations, 23 sounds, 513 packages as JSON. Open: models to glTF; a Linux exporter.
- Bink Audio (`.binka`, Unreal) decodes to WAV through vgmstream. Fix: vgmstream's
  all-subsongs pass writes nothing for a file without subsongs and exits 0; such a file is now
  decoded as one stream (before, it fell to ffmpeg, which fails on Bink Audio).
- Fix: retoc converted one IoStore container at a time without `global.utoc`, so every package
  failed and the raw Zen packages came out instead (815 of 815 on the test game); a container
  now converts in a folder beside `global.utoc` (hard links, a copy across volumes): 815/815.
- Fix: an empty (or `auto`) tool path in `[tools]` pointed at the ini's own folder; it means
  automatic, as SETTINGS says. With it, the UE4SS agent copied a whole folder into itself.
  The agent now refuses a UE4SS folder that holds the copy.
- Fix: a workspace the dynamic arm had written to (`.runtime/` only) was refused as "not
  created by ViWo", then treated as "already holds an extraction". The dynamic arm claims a new
  or ViWo-only folder (never one with the user's files), and the other arms' dot-folders are no
  extraction to replace. Exporters get the run's workspace (`ExtractionContext.workspace`).

## 1.13.0 (2026-11-04)
- Completeness contract (doc 16.0c) on Unity, valid for every Unity game: besides textures,
  audio, text and meshes, the export now writes video clips in their own format, fonts
  (.ttf/.otf/.ttc) and shaders, and every other object (scenes, prefabs, materials, animations,
  game objects and their components, MonoBehaviour data) as JSON from its type tree, one file per
  serialized file (`data/<file>.objects.json`, streamed). MonoBehaviour layouts come from the
  game's managed assemblies (pinned `TypeTreeGeneratorAPI` 0.0.10, MIT, with UnityPy); one that
  has no layout is listed with the reason and counted. Unity option `objects` (default on).
  Verified on ULTRAKILL Prelude: 307,864 objects to JSON in 28 files, 89 shaders, 2 fonts and a
  video in 90 s. Open: MonoBehaviour fields on IL2CPP builds.

## 1.12.0 (2026-11-04)
- UI numbering is computed, never written (owner): `S0`… STATIC, `D0`… DYNAMIC, `P0`…
  PATCHING (each arm's home is 0), `00`, `01`, `02` for SYSTEM, JOBS, SETTINGS, from the arm and
  the place in it, so plugin views renumber everything by themselves. Panels are lettered A, B,
  C… in reading order over the visible ones. Home steps and NEXT buttons show the code of the
  tab they open; every message names a tab by its title only.
- UX pass from frames captured at the owner's window and zoom, and on a real extraction (DDLC):
  - the top bar no longer drops chips: OS and PLUGINS moved to SYSTEM, the game and workspace
    paths shorten first; FORMATS opens SYSTEM at its formats list (`#system@formats`, kept in
    place while the tables load);
  - toasts sit at the top right, no longer over the action bar's button;
  - ANALYSIS and CAPTURE named "–" as the active workspace although one was open;
  - an off feature (ANALYSIS, RUNTIME CAPTURE) says so with a TURN ON button that writes it to
    startup.ini at once; a notice's text no longer runs into its title;
  - a two-column view with nothing on the right yet uses the whole width; field labels have
    room above them; SETTINGS tool paths have BROWSE beside the field;
  - WORKSPACE: OPEN per file type, "(no extension)" for `noext`; SORT opens on what can be
    previewed (images, audio, video, text first); JOBS opens the latest job; PATCHED COPY
    proposes a target beside the workspace (`<data>/patched/<game>`);
  - SYSTEM says what every tool serves from the server's own data (the slots it backs, else
    its arm), not from a hand-kept list.

## 1.11.1 (2026-11-04)
- Fix: a plugin's decoders ran on every game. `decode.cr2w` claims `.json`, `.mesh`, `.ent` and
  the other CR2W suffixes, so with WolvenKit installed an RPG Maker MV game's data JSON or a
  Unity game's meshes were handed to WolvenKit and reported as failures. A plugin's decode
  slots now apply only when that plugin was chosen for the game (core decoders, such as audio
  and images, still run everywhere).

## 1.11.0 (2026-11-04)
- Completeness contract (doc 16.0c): every Cyberpunk 2077 extraction reports the installed mods'
  conflicts from the archive indexes alone: how many members of the game's archives the mods
  replace, how many members a later mod loses to an earlier one (first by name in
  `archive/pc/mod`, then REDmod's `mods/*/archives`; named from the path list when it loads),
  and any archive that cannot be read. Verified on a real install: 15 mod archives replace 63
  members, in 1.5 s.

## 1.10.0 (2026-11-04)
- Completeness contract (doc 16.0c), patching arm on Cyberpunk 2077: `repack` packs edited
  members into an override archive, `archive/pc/mod/!viwo_<archive>.archive` in the patched copy,
  through WolvenKit's console (new `pack.archive` slot, `wolvenkit-pack`). The game loads it over
  its own archives; the name sorts before other mods, so ViWo's edits come first. A member known
  only by its hash keeps that hash. The packer reads the archive back through the game's Oodle and
  compares every edited member. Verified: a texture of a real mod archive edited, packed by
  WolvenKit 9.1.0 and read back byte for byte.
- Fix: an Unreal repack of a pak with members left as they were reported those members as
  FAILED: the `_P.pak` override holds the edits only and the verify looked for every member in
  it. A packer now says it writes an override (`Packer.override`); its file is verified on the
  edits, and the untouched members stay in the pak it loads over (reproduced with the real repak
  on a two-member pak).

## 1.9.0 (2026-11-04)
- Completeness contract (doc 16.0c): Cyberpunk 2077's game scripts are decompiled. The new
  `decode.redscripts` slot (`redscript-decompile`) runs redscript's console (pinned `redscript`
  0.5.32, MIT, Windows; the 1.0 previews dropped the decompiler) on `r6/cache/final.redscripts`
  and writes one `.script` file per stored script (`[options.redengine] decompile = off` keeps
  the cache as shipped only). Verified on the game's own file: 1786 scripts in about a second.
- The `decode.cr2w` warning quotes WolvenKit's failure line from "Failed to" on.

## 1.8.0 (2026-11-04)
- Completeness contract (doc 16.0c): Cyberpunk 2077 resources are decoded. The new
  `decode.cr2w` slot (`wolvenkit-export`) runs WolvenKit's console (pinned `wolvenkit` 9.1.0,
  GPL-3.0, its own process on the pinned .NET runtime) once per batch of 150 extracted files:
  textures to PNG, meshes, morph targets, cubemaps and animations to glTF, and every CR2W
  resource to JSON (embedded buffers included). The settings ViWo needs (PNG, meshes without
  materials, which need an uncooked depot) are written into WolvenKit's own `appsettings.json`
  off screen. Every file WolvenKit could not convert is counted in one warning that names the
  first. Verified on four real mod archives: 345 resources, 51 PNG, 52 glTF, 336 JSON; 15
  animations WolvenKit itself cannot read are reported.
- Decode stage: a backend that takes a whole batch (`decode_many`) gets every file of its slot in
  one call; a partial batch is a warning in the run.

## 1.7.1 (2026-11-04)
- Fix: a Cyberpunk 2077 member comes out as the game's own file: the main segment inflated, then
  its buffer segments exactly as stored (the CR2W buffer table gives their on-disk sizes and the
  reader inflates them). The buffers were split off inflated into `<name>.<n>.buffer`, which no
  tool can read (WolvenKit failed on every texture with a buffer; verified: 8/8 textures of
  `basegame_1_engine.archive` now export to PNG). Buffer segments need no Oodle.

## 1.7.0 (2026-11-04)
- Completeness contract (doc 16.0c), first gap closed: Bink 2 video (`.bk2`, Cyberpunk 2077 and
  many other games) decodes to MP4 in the new `decode.bink2` slot (`bink-game`). ffmpeg has no
  Bink 2 decoder; the game ships one: a helper process (`viwo/data/bink/decode_bink.py`) decodes
  every frame with the game's own `bink2w64.dll` and pipes it into the pinned ffmpeg, so the
  game's code never runs inside ViWo. Opt-in with the other video (`core.decode_video=on`).
  Verified on Cyberpunk 2077's video archive (500x500, 299 frames at 30 fps). Video only: the
  audio track is not decoded yet (said in every note).
- `viwo` LoC budget 14200 -> 14600 for the completeness work (reason in `loc_caps.ini`).

## 1.6.24 (2026-11-04)
- Property tests: a settings change that would break the ini is refused and the ini stays as it
  was (no draft left); a file that is not a patch set is named, and an export without a unique
  signature says so per patch; TaleWorlds LZ4 segments inflate, or are skipped without the module
  or on bad data; DataTool names a missing tool and failed modes; the protector check names output
  it cannot read; a damaged export map is ignored; a capture names anti-cheat services running
  now; an unreachable network is reported as such.
- Coverage: 98.6 % line, 95.3 % branch overall (doc 17.5); 72 files still under 98/95 alone.

## 1.6.23 (2026-11-04)
- Property tests: mod load order over random dependency graphs puts every mod after what it
  requires or loads after, names a cycle with its path and a missing requirement, and every
  conflict it reports is real and undeclared; the plugin conformance check names a capability
  list without detect or unpack and a dependency declared twice; a raising detect scores zero
  with its reason; an extraction that needs a decision says so; GitHub's answers, missing
  releases and errors; a workspace that is a file, a taken sibling name and the process's own
  lock.

## 1.6.22 (2026-11-04)
- Property tests: duplicate cleaning never trashes the last copy of any content (random
  workspaces full of duplicates keep every content after plan and apply); damaged SLP sprites
  and palettes are named failures of the in-process decoder; plugin sanitizer rules count only
  under their own plugin id; QuickBMS names a missing scripts folder, tool or script and a run
  that wrote nothing; survey reports are found by id inside their folder only, damaged ones
  skipped; a backend that raises is a named failure and its spare runs; the carve stage says its
  failures, fallbacks and big files, and stops on cancel.

## 1.6.21 (2026-11-04)
- Property tests: a sanitizer plan acts only on the files it saw (a file changed since the scan
  refuses the plan, a bad id or a missing plan is named, a finding that cannot be carried out is
  listed while the rest go on, an undo that cannot bring a file back keeps it for a later
  undo); analysis names an unbound slot, a failed run, a fallback and a plugin whose target
  hook crashes, and stops waiting on a GUI tool on cancel; Skyrim SE BSAs (LZ4 frames, embedded
  names) read back byte for byte and are counted without lz4; the carver splits a stream of
  several files; `viwo analyze` names a missing game or workspace and waits for the tool it
  opened.

## 1.6.20 (2026-11-04)
- Property tests: the round trip plans every edit or names why not (no packer, an unbound pack
  slot, a plugin that is not loaded), takes the newest extraction run as the game (never a
  capture record or a damaged one), reports a container behind a link, a failed packer and a
  crashing verify per container, refuses traversal in loose files, reminds about terms-sensitive
  plugins and needs a target to build; small core edges: an unknown or foreign OS layer, a patch
  address outside every section, asm without Keystone or that it cannot assemble, a file with no
  unique signature, stale antivirus journals, a crashing job, the capture routes' bad input.

## 1.6.19 (2026-11-04)
- Property tests: any sequence of one-by-one keep, trash and rename, undone step by step, gives
  back the exact workspace (a refused rename records nothing; an undo with nothing left or of a
  vanished file is named; a restore never overwrites a newer file); every malformed drop-in
  plugin.json (no id, a bad or reserved slug, a missing module, a ui path outside, a too-new
  requirement, a class that is not a plugin or carries another id) disables only that plugin,
  with its reason, and the built-ins boot as before; slot and backend clashes are named.

## 1.6.18 (2026-11-04)
- Fix: "Continue in x64dbg" on a 32-bit game names a missing x32dbg (an x64dbg of the user's own
  may ship without it) instead of failing on its config file.
- Property tests: the carver finds samples of every format at their exact offset and size in
  noise, and damaged ones never crash it, overlap or run past the buffer; every analyzer and
  handoff names a missing tool and a run that wrote nothing; the first-run answers of x64dbg,
  Ghidra and Cheat Engine land once, keep every value the user set, change nothing the second
  time and say when they cannot be written.

## 1.6.17 (2026-11-04)
- Property tests: any RPA-2.0/3.0 archive (any key, prefixed chunks, byte or text names) reads
  back byte for byte and a repack keeps every member and carries every edit, a malformed index
  is named; a [slots] entry never binds a backend that cannot serve the slot and every bad entry
  is named; the 7-Zip, unrar and py7zr backends name a password, a failure and a missing tool;
  unsafe zip names are counted in a note; RPG Maker MV media decrypts with the game's key or
  one recovered from its images and repacks to what the game reads; the settings routes name an
  unreadable ini and a broken plugin; the unrpa and unrpyc processes name a run that wrote
  nothing.

## 1.6.16 (2026-11-04)
- Property tests for the Unity exporters' sources: containers found by name or by signature
  behind a custom header (a file an antivirus holds is skipped), the game's cache folders only
  from app.info and only when they exist, the source map follows an object through a bundle to
  its file on disk, the extension filter writes only what was selected, the cache is read only
  when asked for, a cancel stops; the AssetStudioModCLI spare names a missing tool and a failed
  run and asks for meshes only when they are on.

## 1.6.15 (2026-11-04)
- Fix: the XP3 reader (KiriKiri) bounds its index: a stored index past 256 MiB (a damaged
  64-bit size raised OverflowError) and a compressed one that inflates past it (a
  decompression bomb) are named "bad XP3" failures. XP3 joins the mutation fuzzer.
- Property tests: XP3 archives in every layout (version 1 and 2 headers, stored or compressed
  index and segments, files over several segments, foreign chunks) give back every plain file
  byte for byte; encrypted entries are counted and named, never guessed; traversal names are
  never written; a cancel stops.

## 1.6.14 (2026-11-04)
- Fix: `viwo survey` classifies encrypted or compressed blobs under 128 KiB as dense. Their
  "middle" sample started at offset 0, the same bytes twice compressed well, and they were
  reported as structured data ("try --deep") instead of needing a key or a decoder.
- Property tests: a survey of random games counts every file in exactly one category, reports
  the coverage its categories give, names every missing tool and exporter, counts a file an
  antivirus holds as unreadable, and stops on cancel; a decoder that reports success without
  output is a named failure; the probes report exactly the facts of the file.

## 1.6.13 (2026-11-04)
- Property tests: GDScript decompilation (the bytecode option wins, then the engine version, then
  GDRE's own listing for the header number; files in batches of at most 100; every failure
  named); the Unity packer writes TextAsset and Texture2D edits back, verifies them, and names a
  missing object or a type it cannot write; an OS layer without a capability says it cannot;
  the zip packer changes exactly the edited members and leaves a broken container untouched;
  one plugin's verify crash stays on its own entry; provenance keeps damaged lines.

## 1.6.12 (2026-11-04)
- Fix: every dump, trace and profile run gets a new folder and every recording a new WAV. Two
  runs on one process within one second shared `<pid>-<stamp>`, and a trace that wrote nothing
  reported the earlier run's log as its own; two recordings in one second overwrote each other.
- Fix: an Unreal patch pak counts the members it packed (an unsafe member name was skipped but
  counted).
- Property tests: the round-trip edit set over random provenance maps and user actions (every
  edit in the set or named with its reason); pak footers fuzzed; unpack failures classified
  (key or not) and the AES key never shown back; patch paks take the game's pak version; AES
  key spellings round-trip and every reason a key is missing is said; trace, dump, profile and
  agent waits over a faked OS layer.

## 1.6.11 (2026-11-04)
- Fix: `POST /api/open-folder` and the merger's `workingDir` take absolute paths only (a
  relative merger folder that existed beside the server was used as the merger's source).
- Property tests for the workspace routes over random workspaces: group trash, restore, delete
  and keep-selected never lose or invent a file and give the bytes back on restore; the asset
  window pages through every file once; save-remaining moves every remaining asset out byte
  for byte; the patch and mod routes do what the core does; the preflight and install jobs
  rebind what they installed.

## 1.6.10 (2026-11-04)
- Fix: a worker pin (Unicorn, angr) swaps in through `core/downloads.py` like every tool: a
  locked worker folder (Windows: a worker still running) is never half deleted.
- Fix: `POST /api/diag` takes an absolute `out` only (a relative one wrote into the server's
  folder), like every request path since 1.6.6.
- Contracts: `RuntimeAgent.install/finished/outputs`, `Analyzer.analyze` and `Handoff.prepare`
  are abstract (a backend missing one fails when it is built, not mid-run); the base classes
  of the CLI unpackers, decoders and Unreal unpackers lost their never-run `argv` stubs.
- Property tests: the loopback recorder writes exactly the clipped samples it heard; a worker
  pin swaps in whole or leaves the old one; the BepInEx agent (IL2CPP only, never a stale log,
  what it wrote); `python -m viwo`; the system routes; both A4 workers name every unusable
  request (unsupported PE or ELF machine, not a binary, a symbolic argument to the emulator, a
  heap overflow, a bad dump index, an unknown export, nothing to solve) and take every
  argument kind and address form.

## 1.6.9 (2026-11-04)
- Fix: damaged archives are named failures in every in-process reader. The Ren'Py reader
  raised on a cut-short header or a malformed index entry and inflated its index without a
  bound (a decompression bomb: now at most 256 MiB); the zip and tar readers raised on a damaged
  member name, a cut-short gzip stream or bad deflate data; TPAC raised when cut short.
- Hostile input: valid archives of ten formats, randomly damaged (bytes, runs, cuts), through
  their readers, as a property (`tests/test_untrusted_input.py`).
- `viwo` LoC budget 14100 -> 14200 for the 1.6.x hardening (reason in `loc_caps.ini`).

## 1.6.8 (2026-11-04)
- Fix: a damaged 64-bit offset in an RDAR index (Cyberpunk 2077) or a BA2/BSA (Bethesda) is a
  named "bad RDAR/BA2/BSA" failure; it reached `seek()` or an mmap slice and surfaced as a
  Python OverflowError.
- Hostile input as one property (doc 17.3): every built-in in-process reader, handed its own
  magic followed by random bytes, answers with an Outcome and never raises, and writes nothing
  outside its destination (`tests/test_untrusted_input.py`); corrupt RDAR archives fuzzed.
- REDengine tests: Kraken members inflate through the game's decompressor (faked) and are
  skipped and named without it; the Oodle bridge; every reason members keep their hashes is
  said (no path list, no Oodle, a list that is not KARK or does not inflate); a cancel stops
  before the first member.

## 1.6.7 (2026-11-04)
- Property tests: merger builds over random candidate sets with the encoder faked (one output
  per candidate, every failure named, partial flagged, settings clamped, long graphs to a file,
  overlay and refusals); the Windows OS layer (produced file names always legal, the long-path
  form exactly past the limit, PowerShell lists quote any path, Defender exclusions leave the
  user's own alone and say why when skipped, a failed dump leaves no file); the shared OS base
  (output lines in order whatever the relay does, timeout and cancel kill and say so, GUI
  children tracked and reaped, the locator's search order, pickers without a display).

## 1.6.6 (2026-11-04)
- Fix: no API request can name the server's own folder. An empty or relative game, folder,
  executable, patch set, mod, copy or workspace path resolved against the server's working
  directory (an empty `gamePath` detected, surveyed or analysed ViWo's folder; `/api/mod` without
  `copy` defaulted to "."); every route now takes absolute paths only (`api/app.py` `path_param`,
  `existing`; doc 4.1 security rule 6), checked as one property over every path-taking route.
- Property tests: the startup preflight over random dependency reports (exactly the missing
  self-installing tools, never on-demand ones, nothing with auto_install off, every failure a
  warning, an honest ready count); the 12 ANALYSIS API answers what the core answers.
- Doc 4.1 lists `/api/patch`, `/api/mod` and `/api/runtime/profile`.

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
