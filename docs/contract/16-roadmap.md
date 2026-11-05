# 16. Roadmap: what ships and what is open

The 1.x roadmap is the extraction ladder (16.0b) plus the orchestrator rungs of the three arms
(16.2b). Every shipped rung is listed with its version; every open item says so. The 2.0.0 tag
(product release) needs the owner's approval (`docs/HANDOFF.md`).

## 16.0b Coverage ladder (D21)

Any asset stored on the local disk comes out, whatever the engine. Each rung catches what the
ones above missed and reports what it could not handle; `viwo survey` shows per game which rung
covers which files and flags dense unknown blobs (likely encrypted or compressed).

| Rung | What it does | State |
|------|--------------|-------|
| 1. Engine plugins | native decoding with real names: Ren'Py, Unity, Godot, Unreal, Doom, RPG Maker, KiriKiri, Electron/NW.js, Source, Bethesda, Age of Empires, Total War, Cyberpunk 2077, Bannerlord, Overwatch | shipped; GameMaker and the engines of doc 13.7 open |
| 2. Container unpackers | zip, tar, 7z, rar and every plugin container, recursive to depth 10 | shipped |
| 3. Signature carver | complete standard files inside unknown blobs (PNG, JPEG, GIF, WAV/WEM, Ogg, MIDI, MP4, Bink, FSB5, BNK, DDS, glTF, zip, 7z) | shipped |
| 4. Compressed-stream scan | zlib and gzip streams inflated (bounded) and carved; zstd and LZ4 when `zstandard` / `lz4` import | shipped |
| 5. Decoders | game audio to WAV (vgmstream), DDS to PNG, Bink to MP4 (opt-in; Bink 2 through the game's own DLL), SLP to PNG, `.rpyc` to `.rpy` | shipped; meshes to glTF, fonts, localization tables open |
| 6. Script-driven unpackers | QuickBMS with one `<ext>.bms` per format, scripts from the per-game indexes | shipped; no index entry carries a pinned script yet |
| 7. Runtime | RenderDoc capture, runtime agents, audio loopback (16.2b D1-D2) | shipped |

ViWo authors no DRM defeat, anti-cheat evasion or key brute force (philosophy point 5); keys come
from the user or the game's own files and are verified (D18).

## 16.0c Completeness contract (owner, 2026-11-04)

ViWo gets **everything** out of every game it covers: every file of the install comes out, and
every engine format is decoded into a form a person or a standard tool can use (textures to
DDS/PNG, meshes, rigs and animations to glTF, audio to WAV, video to MP4 or frames, compiled
scripts decompiled, game databases and localization to JSON/YAML/TSV, everything else to
readable JSON). On every engine the three arms apply where the engine allows: static (extract,
decode, analyse its executables and scripts), dynamic (capture, agent, dump, trace, profile,
record) and patching (repack into its own containers, patch sets, mod packages). A format that
is not decoded yet is an open row below and is reported in the run (never silent); it is never
skipped quietly. Decoding uses, in this order of preference: ViWo's own code; the game's own
libraries (Oodle, Bink), as for Kraken today; a pinned community tool run as a separate process.

| Engine | Comes out and is decoded today | Open (decode, arm) |
|--------|-------------------------------|--------------------|
| REDengine 4 (Cyberpunk 2077) | RDAR members with names, each the game's own file; Wwise audio to WAV (vgmstream); Bink 2 video to MP4 through the game's `bink2w64.dll`; CR2W through WolvenKit (`decode.cr2w`): textures to PNG, meshes, morph targets and animations to glTF, every resource to JSON; the game scripts (`r6/cache/final.redscripts`) decompiled to redscript source (`decode.redscripts`); edits packed into an override archive (`pack.archive`); the installed mods' conflicts in every run (members they replace, members a later mod loses) | mesh materials (need an uncooked depot); TweakDB to JSON; Ghidra names from `cyberpunk2077_addresses.json`; runtime agent (Cyber Engine Tweaks) |
| Unity | textures, audio, text, meshes (OBJ), IL2CPP and managed code; video clips in their own format, fonts, shaders; every other object (scenes, prefabs, materials, animations, components, MonoBehaviour data) to JSON, one file per serialized file; MonoBehaviour layouts from the game's managed assemblies (Mono) or, on IL2CPP builds, from Cpp2IL's stand-in assemblies (270 of 745 on a Schedule I file, against 6) | the IL2CPP MonoBehaviours the layout generator cannot build (generic and nested types); meshes and animations to glTF |
| Unreal | pak and IoStore members (legacy `.uasset`/`.uexp`, IoStore converted with `global.utoc`); `export.unreal` (UnrealAssetScout): textures to PNG, models and animations (UEFormat), sounds (Bink Audio and Wwise to WAV through vgmstream), every package as JSON; engine version from the game's binaries; mappings from the RUNTIME agent (UE4SS) or given | models and animations to glTF (UEFormat today); Linux build of the exporter |
| Godot | PCK members, resources (GDRE), GDScript | - (verify `.ctex`/`.stex` to PNG without GDRE) |
| Ren'Py | RPA members, `.rpyc` to `.rpy` | - |
| RPG Maker | RGSSAD, MV/MZ decrypted assets, data JSON | XP/VX/VX Ace `.rxdata`/`.rvdata2` (Ruby Marshal) to JSON |
| KiriKiri | unencrypted XP3 entries | TLG images to PNG, PSB/SCN scripts to JSON |
| Source | VPK members; VTF textures to PNG (DXT1/3/5 and the 8-bit formats) | MDL to glTF, BSP maps, VCS shaders, the 16-bit and HDR VTF formats |
| Bethesda | BSA/BA2 members, BA2 textures to DDS | NIF to glTF, ESP/ESM/ESL records to JSON, FUZ/XWM audio to WAV |
| Age of Empires (genie) | DRS members, SLP to PNG | SMX (Definitive Edition) to PNG |
| Total War (warscape) | PFH4/PFH5 members; `.loc` localisation to JSON (`decode.loc`); DB tables to JSON with the game's RPFM schema (`export.warscape`, 14 games) | RigidModel to glTF; DB tables with binary fields (`models_*`); the game's schema installed by itself on first use |
| Bannerlord (taleworlds) | TPAC members, textures to DDS; FMOD sound banks to WAV (vgmstream) | meshes and skeletons to glTF |
| Doom, Electron, Overwatch (DataTool) | everything their formats hold | - |
| GameMaker, the engines of doc 13.7 | loose files and carving only | engine plugins |

## 16.2b Orchestrator rungs

Each rung is a slot family or a job kind, pinned tools, a UI view and CLI commands, behind a
feature switch where it is heavy. Sequencing by owner's call.

| Arm | Rung | Content | Tools | State |
|-----|------|---------|-------|-------|
| static | A1 | `analysis.native` headless + Continue in Ghidra | Ghidra 12.2, JDK 25 | shipped 1.3.0 |
| static | A2 | `analysis.dotnet`, `.il2cpp`, `.script`, `.python`, `.gdscript` | ilspycmd, Cpp2IL, unluac, unrpyc, GDRE Tools | shipped 1.4.0-1.4.4 |
| static | A3 | `analysis.protector`, signatures inside the Ghidra pass, version diff (`viwo diff`) | Detect It Easy, Ghidra FID | shipped 1.4.1-1.4.5 |
| static | A4 | `analysis.emulate`, `analysis.symbolic` on isolated routines | Unicorn, angr (workers) | shipped 1.5.1 |
| dynamic | D1 | unattended GPU capture, shader disassembly | RenderDoc | shipped 1.3.6 |
| dynamic | D2 | `runtime.unreal`, `runtime.unity` agents; audio loopback | UE4SS, BepInEx, soundcard | shipped 1.4.7 (BepInEx verified 1.6.0) |
| dynamic | D3 | `handoff.debug`, `handoff.memory`; memory dump; API trace | x64dbg, Cheat Engine, OS layer, Frida | shipped 1.4.7 |
| dynamic | D4 | `hook.inject` (hook loader with hot reload), `hook.overlay`, `net.*` (own-traffic capture and proxy), `profile.sample` (CPU sampling) | OS layer (profile) | `profile.sample` shipped 1.6.1; the rest **open**; the plaintext network capture and the DLL injection loader are the owner's call and are not authored by the assistant |
| patching | T1 | patch sets: offset, RVA and AOB addresses, Keystone assembly, capstone plans, whole-file verify, diff and AOB export | Keystone (`kstool`), capstone | shipped 1.4.5-1.4.6 |
| patching | T2 | mod packages: pack, check (with the AOB update check), ordered and conflict-checked apply | - | shipped 1.4.5-1.4.6; the in-game half (loader, hook API, overlay, crash handler) is what the pinned runtime loaders do |
| patching | T3 | **interactive / live patching** | x64dbg, Ghidra | **the child does it natively, ViWo does not reimplement it** (owner's principle: what a child can do natively, let it do natively). x64dbg patches live memory and writes to the file (Patches dialog); Ghidra edits bytes and exports. ViWo's role is the handoff that opens the child pre-loaded (D3 `handoff.debug`, A1 Continue in Ghidra). ViWo's own patch sets (T1) stay for scripted, reproducible patches. Verified by hand on real software (Free Download Manager: lifted a hardcoded 20-connection per-server cap via one `cmp` byte, found through ViWo's Ghidra analysis). Note: the x64dbg handoff is today gated behind the `capture` feature; interactive patching should also be reachable from the patching arm. |

The arm homes of the UI (`viwo/web/js/views/home.js`) show the same rungs as SHIPPED or ROADMAP.

## 16.3 Open items outside the rungs

| Item | Doc |
|------|-----|
| sanitizer phases 2-3 (lossless conversions, transcode presets) | 5.1 |
| `[slot_policy]`, `[hooks]`, `--plugin`/`--slot` CLI overrides | 9.5 |
| `memory_image` analysis targets | 6.5 |
| Unreal asset export (CUE4Parse wrapper), GameMaker and the engines of 13.7 | 13.7 |
| `keys.*` as a slot family (keys stay plugin options) | 14.2 #4 |
| coverage per file at 98 % line / 95 % branch (owner's target) | 17.5 |
| the `vidya_wormhole_indexes` repository split and its first release | `docs/indexes.md` |
| **managed vs unmanaged tools** distinction in the indexes and plugins: *managed* = ViWo pins (version/size/sha256) and installs into `third_party/`; *unmanaged* = user-supplied (a `[tools]` path), on PATH, or a third-party/community tool ViWo deliberately does not pin (including borderline tools, never first-party). ViWo uses an unmanaged tool but does not own its lifecycle; an index or plugin that references a tool says which it is (owner, 2026-11-05) | 10, `docs/indexes.md` |

## 16.4 UI capabilities (owner, planned 2026-11-05)

Planned web-UI features, in the order the owner wants them, to be introduced later. All of them
are **OS-agnostic** (Windows and Linux alike): nothing may assume one OS. They build on the
principle **"what a child can do natively, let it do natively"** — ViWo orchestrates and does not
reimplement a child tool's capability.

1. **Workbooks** — in the UI, explain how to do something in a child's own interface (a guided,
   step-by-step how-to for a child tool: e.g. how to patch a byte in x64dbg, how to export a
   program in Ghidra). Teaching overlays/text, not automation.
2. **Runbooks** — default or saved workflows, editable. A named sequence of steps a user can run,
   tweak and save (ViWo's own actions and/or child steps).
3. **Workflows** — record what the user does, with pause/continue. On replay, when a step's
   output is identical it proceeds to the next automatically; when it differs it prompts whether
   to continue, then proceeds if yes, and so on. Useful for automated/repeatable patching.
4. **Embedded child GUIs** — wrap the child GUIs (x64dbg, Ghidra, Cheat Engine, qrenderdoc, ...)
   inside the ViWo web UI, each resizable and fullscreen, instead of a separate OS window. Input
   must be done properly: the cursor, mouse and keyboard are forwarded to the embedded native
   window faithfully. This is the natural end of "let the child do it natively" — the native tool
   runs inside ViWo's surface. Comes after workflows. OS-agnostic (an X11/Wayland embed on Linux,
   the matching mechanism on Windows).
