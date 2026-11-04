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
| 5. Decoders | game audio to WAV (vgmstream), DDS to PNG, Bink to MP4 (opt-in), SLP to PNG, `.rpyc` to `.rpy` | shipped; meshes to glTF, fonts, localization tables open |
| 6. Script-driven unpackers | QuickBMS with one `<ext>.bms` per format, scripts from the per-game indexes | shipped; no index entry carries a pinned script yet |
| 7. Runtime | RenderDoc capture, runtime agents, audio loopback (16.2b D1-D2) | shipped |

ViWo authors no DRM defeat, anti-cheat evasion or key brute force (philosophy point 5); keys come
from the user or the game's own files and are verified (D18).

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
