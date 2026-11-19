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
| declarative formats | Kaitai Struct `.ksy` | `kaitai` plugin: `.ksy` parsed to a JSON tree (13.2a) |

### 13.2a Declarative plugins (Kaitai `.ksy`): a second plugin form

A format may be described rather than coded. ViWo reads a Kaitai Struct `.ksy` definition
(bundled in a plugin under `defs/`) with its own first-party interpreter and surfaces each as a
`decode.kaitai_<id>` slot that parses a matching file into a structured JSON tree
(`viwo/plugins/kaitai/ksy.py`). The GPL `kaitai-struct-compiler` is never used, and the YAML is
read by a tiny stdlib subset reader, never PyYAML.

- **Subset interpreted:** `meta` (`id`, `endian` le/be, `file-extension`); `seq` fields with an
  `id` and one of `type` (`u1`-`u8`/`s1`-`s8`, an optional `le`/`be` suffix, or a user type in
  `types`), `size` (an int or an expression over the sibling fields already read), or `contents`
  (magic bytes to check); `repeat: expr` with `repeat-expr`, and `repeat: eos`; `enum` (an
  integer mapped through `enums`); `types` (named sub-structures). Anything outside the subset
  raises, so a definition ViWo cannot interpret fails by name rather than parsing wrongly.
- **Read only:** a parse tree has no general way back, so every Kaitai decoder is one way
  (`Decoder.one_way`).
- **Not an engine:** the `kaitai` plugin detects nothing (confidence 0); its decoders run only
  when it is selected for a run (`--plugin kaitai`), so no ordinary extraction is surprised by
  them. The bundled proof is `defs/wav.ksy` (WAV/RIFF), which exercises the whole subset.
- **Form:** an ordinary plugin (doc 2) whose slots and backends are built from the `.ksy` files
  it ships; a drop-in adds its own `defs/` the same way.

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
| LÖVE | the game is a zip, alone (`.love`) or appended to `love.exe`; PhysFS works out what lies before it | Python's zipfile reads both; the rebuild keeps the executable's bytes |
| AGS | CLIB packfiles, at a file's start or behind the executable (tail signature); versions 6 to 30, 20 and 21 obfuscated by the engine's public text key and generator | read and rewritten in their own version, offsets and sizes patched in place |
| Defold | the archive is found by content hash through the manifest; sizes come from the index | the rebuild keeps every hash and the manifest |

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

GameMaker (UndertaleModTool CLI, GPL-3.0), TyranoScript beyond the wrapper and zip paths;
Unreal asset export (a CUE4Parse wrapper). Covered by first-party readers (doc 2.7):
Unreal localization (`decode.locres`), LÖVE (`love2d`), XNA/FNA/MonoGame (`xna`, LZX read
through the first-party `lzx.py`), AGS (`ags`), Defold (`defold`), Wolf RPG (`wolfrpg`, DXArchive
version 6). Within them still open: XNB content other than Texture2D and SoundEffect, Wolf RPG's
DXA-compressed members (ViWo's DXA decoder is unverified against DxLib) and its archive versions
other than 6, Defold's encrypted Lua resources, new keys in a version 3 `.locres` table (their
CityHash64 is not computed).

## 13.8 Desktop-application frameworks (cold patching)

The same extract -> edit -> repack model, aimed at the applications the owner runs, not only
games. First-party readers where the format is a container (doc 2.7); the static view through a
pinned decompiler where it is code. Covered:

| Framework | Plugin | Reads | Way back |
|-----------|--------|-------|----------|
| Qt 5/6 | `qt` | `.rcc` resource collections (versions 1-3, zlib blobs; zstd reported), `.qm` translations (to JSON), QML/JS/QSS/SVG compiled into an exe or DLL (carved, `viwo qt-resources`) | `.rcc` rebuilt, name and node trees kept, data laid out again (unchanged comes back byte for byte); `.qm` one way |
| Chromium / CEF / Electron | `chromium` | `.pak` DataPack resources (versions 4 and 5, every id, version-5 aliases) | the pack rebuilt byte-faithfully with the edited ids |
| Frozen Python | `pyfrozen` | PyInstaller onefile (CArchive + inner PYZ: data, binaries, every module as `.pyc`); py2exe/cx_Freeze `library.zip` through the core zip; `.pyc` disassembly (`decode.pyc`, host-version) | the PyInstaller exe rebuilt (bootloader and cookie kept, unchanged byte for byte); `library.zip` through the core zip |
| .NET | `dotnet` | embedded managed resources (PE + ECMA-335 metadata to the ManifestResource table); C# as the static view via the pinned ILSpy handoff (doc 6) | an edited resource written back in place when its size is unchanged; a size change is refused by name (rewriting the metadata offsets and PE layout is not done) |
| Java | `java` | `.jar`/`.war`/`.ear` (zip: resources, `.properties`, `.class`, the manifest) through the core zip | the jar rebuilt; no class decompiler is pinned, so `.class` files stay bytecode (said) |

A value that lives only in native code is not a resource edit: it is a binary patch (doc 18.8).
Free Download Manager (Qt) is the worked example: its QML UI is compiled into `fdm.exe` and comes
out through `viwo qt-resources` (258 QML + 365 SVG on the installed build), but its connection cap
is enforced in native code (the setting key `MaxConnectionsPerServerLimit`), so raising it is a
binary patch on the copy, not a resource change. Open: the Qt embedded carve recovers textual
resources by content, not the resource tree's names (a stripped binary keeps none); rebuilding a
`.pak`/`.rcc`/CArchive in place assumes the edited data fits the container's layout.
