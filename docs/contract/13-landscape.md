# 13. Landscape: the tools ViWo wraps and what it covers

## 13.1 Positioning

Formats are covered by existing tools: QuickBMS, GARbro and Game Extractor for archives; UnityPy,
AssetStudioMod and AssetRipper for Unity; CUE4Parse, FModel, repak and retoc for Unreal; GDRE
Tools for Godot; unrpa and unrpyc for Ren'Py; unblob and binwalk for carving. What none of them
provides is one cross-platform orchestrator that recognizes a game, routes each container to the
right tool with a fallback, curates the output and records its provenance, then carries on into
analysis, runtime work and patching. ViWo is that glue; it does not reimplement a parser that a
maintained tool already has, and writes its own reader where none is safe or available
(Ren'Py RPA, the container plugins of 13.3).

## 13.2 Ideas ViWo uses

| Idea | From | In ViWo |
|------|------|---------|
| identify, then extract (head and tail, embedded chunks) | unblob | slot identifiers (doc 8.1), embedded Godot PCKs |
| carving with a depth limit and bounded streams | unblob, binwalk | `carve.signatures`, `viwo/core/carve/` |
| plugin discovery through entry points | unblob | `viwo.plugins` entry points (doc 2.8) |
| plan, accept, apply, undo over a library | Tdarr | the sanitizer (doc 5) |
| community scripts per format | QuickBMS | `unarchive.bms`, scripts from the per-game indexes |

Open: declarative formats (Kaitai `.ksy`) as a second plugin form.

## 13.3 Per-engine facts that shape the plugins

| Engine | Fact | Consequence |
|--------|------|-------------|
| Ren'Py | RPA indexes and `.rpyc` files are Python pickles; unrpa and rpatool call plain `pickle.loads` | `rpa-safe` (restricted unpickler) is main, unrpa a subprocess spare (D11); `.rpyc` goes to unrpyc in its own process |
| Unity | UnityPy exports in process; AssetStudioModCLI is a real CLI with a native Linux build; AssetRipper's headless mode is a local HTTP server (GPL) | UnityPy main, AssetStudioModCLI spare (D7); AssetRipper not wrapped |
| Unity IL2CPP | Cpp2IL reads the Unity version from the player executable | the `il2cpp` target carries the exe |
| Unreal | repak handles `.pak` with `--aes-key`; retoc handles IoStore (`to-legacy`, `unpack`); UnrealPak may not be redistributed (Epic EULA) | repak and retoc pinned; UnrealPak never; UE5 unversioned assets need `.usmap` mappings (UE4SS agent, doc 11) |
| Godot | PCK magic `GDPC`, versions v1-v4, encrypted-directory flag; an embedded PCK is found by the executable trailer; GodotPckTool refuses encrypted PCKs | GDRE Tools main, GodotPckTool spare on a carved, unencrypted PCK |
| Electron / NW.js | `app.asar` and `package.nw` (a zip) wrap other engines | wrapper re-detection (doc 3.1) |
| Cyberpunk 2077 | RDAR members are Kraken-compressed and named by hash | inflated through the game's own Oodle DLL; names from WolvenKit's path list (`cp77-hashes`) |
| Bannerlord | TPAC textures carry format and shape in their metadata | rebuilt as DDS |
| Age of Empires | SLP sprites use the game palette | `decode.slp` writes PNG sheets |

## 13.4 Code RE and runtime tools

| Tool | License | Notes |
|------|---------|-------|
| Ghidra 12.2 | Apache-2.0 | needs JDK 25 (Temurin pinned); `analyzeHeadless` plus a ViWo export script |
| ilspycmd | MIT | runs on the pinned .NET runtime |
| Cpp2IL | MIT | pre-release builds only; Windows pin |
| Detect It Easy | MIT | `diec` |
| Unicorn | GPL-2.0 | worker process only |
| angr | BSD-2 (Unicorn inside) | worker process; 9.2.223 (angr 10's solver crashes on Windows) |
| RenderDoc | MIT | D3D11/12, Vulkan, GL 3.2+; no D3D9/10 |
| UE4SS, BepInEx | MIT, LGPL-2.1 | runtime agents in a patched copy |
| frida-tools | wxWindows | separate process |
| x64dbg | GPL-3.0 | separate process |
| Cheat Engine | its own license (freeware, source available) | Scoop's unpacked build |
| Keystone / capstone | GPL-2.0 / BSD | `kstool` as a process; capstone in process |
| BinDiff | - | no pinnable HTTPS release with a checksum: ViWo's own diff instead (doc 6.2) |

## 13.5 Licensing facts

- GPL/AGPL tools (QuickBMS, unrpa, x64dbg, Unicorn, Keystone, and any future AssetRipper or
  FModel) run only as separate processes, never imported (D9).
- unrar is freeware, not open source; 7-Zip is LGPL-2.1 except its RAR code.
- `THIRD_PARTY_NOTICES.md` lists every pinned tool's license.

## 13.6 Risks

- **Windows-only tools** (DataTool, Cpp2IL pin, UE4SS, BepInEx, x64dbg, Cheat Engine, Keystone):
  no Linux pin; Wine is not supported.
- **Stale upstreams:** unrpa (dormant since 2019); prefer active forks.
- **Untrusted input:** game files are untrusted; in-process parsers declare
  `parses_untrusted_in_process`; pickles are never unpickled freely.
- **Antivirus false positives:** Windows Defender quarantines GodotPckTool 2.3 (ML heuristic);
  the installer reports it with a hint; GDRE Tools covers `.pck` extraction; `pack.pck` needs the
  folder allowed.
- **Legal and terms-of-service exposure** grows with each engine and the dynamic arm; the
  disclaimer and the user's responsibility cover it (README).

## 13.7 Engines not covered (open)

GameMaker (UndertaleModTool CLI, GPL-3.0), TyranoScript and Love2D beyond the wrapper and zip
paths, Wolf RPG, XNA/FNA, AGS, Defold; Unreal asset export (a CUE4Parse wrapper); Unreal
localization (`.locres`).
