# 13. Landscape: existing tools, where this framework fits, what to borrow

Research done on 2026-11-02, mostly by reading the tools' repositories
directly (README, LICENSE, source, release pages). The GitHub API and some
project sites were blocked from the research session, so a few items are
marked **UNVERIFIED**. Licenses should be double-checked before vendoring
(doc 10). Runtime capture and Blizzard CASC are covered in doc 11.

## 13.1 Honest positioning

What existing tools already cover well:

| Need | Already covered by |
|------|--------------------|
| Many archive formats | QuickBMS (GPL-2.0, CLI, cross-platform), Game Extractor (GPL-2.0 basic, Java), GARbro (MIT, Windows/.NET, strong on visual-novel formats) |
| Deep engine support | AssetRipper / AssetStudioMod / UnityPy (Unity); CUE4Parse / FModel / repak / retoc (Unreal); GDRE Tools (Godot); unrpa / unrpyc / rpycdec (Ren'Py) |
| Recursive carving of unknown blobs | unblob (MIT, Python+Rust), binwalk v3 (MIT, Rust) |
| Declarative format descriptions | Kaitai Struct (`.ksy`; runtimes MIT), ImHex patterns, 010 templates, QuickBMS scripts |
| Media health checks and transcode flows | Tdarr (server closed-source; plugins GPL-3.0) |

What none of them seems to provide:
- one **cross-platform orchestrator** that recognizes a game and routes it to the right engine tool, with a fallback when that tool fails;
- that **normalizes, checks, de-duplicates and curates** the output;
- that records **one provenance report** per run.

The only general-purpose orchestrator found, UniExtract2, is Windows-only,
installer-oriented, and effectively abandoned since 2020.

**So the gap is integration and curation, not formats.** That matches your
"orchestrate tools, write glue" answer: the framework shouldn't reimplement
parsers that QuickBMS, GARbro or the engine-specific tools already have.

## 13.2 Ideas worth borrowing

| # | Idea | From | Where it lands in this contract |
|---|------|------|---------------------------------|
| 1 | **Identification kept separate from extraction.** In unblob, a *handler* finds a chunk (by pattern, offset and size) and a separate *extractor* unpacks it, with its own dependency list | unblob | Slot matching becomes an explicit **identify** step (doc 8 revision below). It's also what makes main/spare swaps clean |
| 2 | **Carving embedded containers** (data appended to an executable, data found by trailer or offset), with a recursion depth limit, entropy checks on unknown chunks, and a JSON report per file | unblob, binwalk | Needed for Godot PCKs embedded in executables, AGS, Love2D, NW.js. The identify step must be able to read a file's **tail**, not only its head |
| 3 | **Declarative custom formats.** Kaitai `.ksy` files compiled to Python (the runtime is MIT, so it can ship), plus QuickBMS scripts as a second dialect | Kaitai, QuickBMS | A future answer to D5: custom plugins in Python **or** declarative (an ini + `.ksy`/`.bms` file) |
| 4 | **Flows with typed inputs and numbered outputs**, version gating, and separate worker pools for health checks and transcodes | Tdarr | Sanitizer recipes (doc 5): typed rule outputs, `requires_version`, separate cheap and expensive worker pools |
| 5 | **Plugin discovery through entry points** rather than hard-coded imports | unblob (pluggy) | Custom plugin loading (doc 2.8): Python entry points as an alternative to folder scanning |

## 13.3 Per-engine findings and how they change the slot table

Slot ids keep the convention from doc 8 (`<family>.<name>`). The research
agents used different names; this table maps them onto that convention.

### Ren'Py

| Fact | Consequence |
|------|-------------|
| RPA indexes (all versions) and `.rpyc` files are **Python pickles**. Ren'Py's own loader unpickles them. **unrpa and rpatool call plain `pickle.loads`**, so a malicious archive can run code | `unarchive.rpa` must never unpickle in our process. Options: (a) run unrpa as a subprocess, ideally sandboxed; (b) our own reader with a restricted unpickler that allows no globals. ❓ The safety argument favors (b) as **main**, with unrpa as the spare for exotic variants; that's a small departure from "wrap only" |
| unrpa: widest coverage of variants (RPA-1/2/3/3.2/4, ALT-1.0, ZiX), but GPL-3.0 and **dormant since 2019** | fine as a subprocess spare; pin it |
| unrpyc v2 (MIT, active, Ren'Py 6.18–8.x) and rpycdec (MIT, active, Ren'Py 7/8, round-trip verification) both use safer unpicklers | `analysis.python`: unrpyc main, rpycdec spare. rpycdec installs fake `renpy` packages, so it should run in an isolated environment |

### Unity

| Slot | Main | Spare | Notes |
|------|------|-------|-------|
| `unarchive.unity-bundle` | UnityPy (MIT, library) | UABEA `batchexportbundle` (MIT CLI; running without a display is UNVERIFIED) | |
| `unarchive.unity-webgl` | UnityPy (`UnityWebData`, gzip/brotli) | AssetRipper | |
| `export.unity` | **AssetStudioModCLI** (MIT, real CLI, native Linux build, filter by type) | UnityPy script (what v1 does today) | ❓ This is a change from v1, where UnityPy is the main exporter |
| `export.unity-project` (full project rebuild) | AssetRipper (GPL-3.0). Its "headless" mode is a **local HTTP server** (`--headless --port`) that we would have to drive with POST calls | AssetStudioModCLI (assets only) | subprocess only (GPL); some features are behind a paid tier |
| `analysis.il2cpp` | Cpp2IL (MIT; pre-release builds only) | Il2CppDumper (MIT; supports up to Unity 2022.2) | |

Correction to doc 7, F8: UABEA **does** have command-line commands
(`batchexportbundle`, `batchimportbundle`, `applyemip`). The problem in v1 is
that the three argument forms it tries match none of them.

### Unreal

| Slot | Main | Spare | Notes |
|------|------|-------|-------|
| `unarchive.pak` | repak (Rust, MIT/Apache; binaries for both OSes; `--aes-key`) | QuickBMS + an Unreal script | UnrealPak can't be redistributed (Epic EULA): never vendor it |
| `unarchive.iostore` | retoc (Rust, MIT; `unpack`, `to-legacy`) | our CUE4Parse wrapper | retoc works best on UE 5.3+; older versions need override flags |
| `export.unreal` | **a small .NET wrapper around CUE4Parse** (Apache-2.0), which we would write and maintain | umodel (MIT; dormant; **UE4 only**) | the one place "glue" means real code |
| `export.unreal-json` (.uasset → JSON) | UAssetGUI `tojson` (MIT; Windows, so Wine on Linux) | CUE4Parse wrapper | |
| `keys.unreal-aes` | key supplied by the user | AESDumpster (license UNVERIFIED, Windows, unreliable) | ❓ new family: **keys**. Automatic key extraction from executables is a grey zone; the user-supplied key comes first |
| `export.unreal-locres` | UnrealLocres (stale; license UNVERIFIED) | CUE4Parse wrapper | |

FModel (GPL-3.0, Windows only) is GUI-only: users can open it by hand, but
it can't be a backend.

### Godot

| Fact | Consequence |
|------|-------------|
| PCK magic is `GDPC`, with format versions v1 (Godot 3), v2 (4.0–4.4), v3 (4.5) and v4 (4.7). It has an encrypted-directory flag. An **embedded** PCK is found through an executable section or a trailer (the last 4 bytes are `GDPC`, preceded by its size) | identify needs **tail** access; the core can carve the PCK out of the executable before unpacking |
| GDRE Tools (MIT, active, headless CLI, Godot 2/3/4, supports keys) | main for `unarchive.pck` (`--extract`) and for project recovery (`--recover`, `.gdc` decompile, texture and audio conversion) |
| GodotPckTool (MIT, active) refuses encrypted PCKs and only reads the magic at offset 0 | spare for `unarchive.pck`, given an unencrypted PCK the core has already carved out |
| `.stex` (`GDST`), `.ctex` (`GST2`/`GSTL`) | identification rules for the sanitizer; conversion through GDRE |

### Engines worth adding after the prototype (ranked)

Ranked by popularity among indie and visual-novel games × tool maturity × low effort:

1. **RPG Maker**, all versions (RPGMakerDecrypter: MIT, .NET 8 CLI, self-contained binaries).
2. **Electron / NW.js wrapper** (`@electron/asar`, MIT; `package.nw` is a zip). This one also unlocks TyranoScript, Construct and RPG Maker MV/MZ.
3. **GameMaker** (UndertaleModTool CLI, GPL-3.0).
4. **TyranoScript** and **Love2D** (almost free once item 2 and plain zip carving exist).
5. **KiriKiri** (big visual-novel catalogue, but Windows-only or dormant tools and per-game encryption).
6. Wolf RPG, XNA/FNA, AGS, Defold, Source.

This suggests one more structural point: **wrapper plugins**. A wrapper
plugin such as Electron/NW.js unwraps the outer container, and then
detection runs again on what's inside. That fits the recursive unpack loop:
after unpacking, the probe should be rebuilt and detection rerun at most
once ❓.

## 13.4 Code RE tools (doc 6 updates)

| Tool | License | Notes |
|------|---------|-------|
| Ghidra 12.2 | Apache-2.0 | `analyzeHeadless`. **Needs JDK 25** for the 12.2 line, not "Java 17+" as doc 6 said. The JDK requirement should follow the pinned Ghidra version |
| ilspycmd | MIT | installing it needs the .NET 10 SDK; native AOT builds exist for win-x64 and linux-x64 |
| Cpp2IL / Il2CppDumper | MIT | see Unity |
| dnSpyEx | GPL-3.0 | Windows, GUI debugger first; not a backend |

## 13.5 Vendoring facts (doc 10 updates)

| Item | Finding |
|------|---------|
| `.gitmodules` and sparse paths | **Confirmed: it can't store them.** Its keys are path, url, update, branch, fetchRecurseSubmodules, ignore and shallow. Sparse rules live in `.git/modules/<name>/info/` and aren't versioned. So a bootstrap script has to reapply them from our own manifest; `third_party/manifest.ini` fits the ini direction |
| 7-Zip | `github.com/ip7z/7zip` looks official (commits by the author), but the link from 7-zip.org couldn't be confirmed. LGPL-2.1+, **except** the RAR code, which carries the unRAR restriction |
| unrar | **No official git repository** (RARLAB ships tarballs). Freeware license, not open source. Can't be a plain submodule |
| FFmpeg | canonical repo `git.ffmpeg.org/ffmpeg.git` (the GitHub one is a mirror). LGPL-2.1+, or GPL with `--enable-gpl` |
| Licenses overall | GPL tools (QuickBMS, Game Extractor, AssetRipper, FModel, UndertaleModTool, unrpa…) are fine **as subprocesses**. They must not be imported or linked into a core with a different license. **Proposed rule: a GPL backend is always a subprocess backend.** This is one more reason to settle the project license (D9) |
| Heavy runtimes | JDK 25 (Ghidra), .NET 10 (ilspycmd, FModel, AssetStudioMod), Java 8 (Game Extractor). The kernel's ToolLocator would need a `runtime` dependency kind (already in doc 2.6) and clear hints |

## 13.6 Risks

- **Windows-only tools** (GARbro, UAssetGUI, Wolf tools, FModel, Noesis) need Wine on the Linux kernel. That would be a kernel concern (`kernel.process` running `.exe` through Wine) ❓. Out of scope for the prototype.
- **Stale upstreams:** unrpa (2019), umodel (UE4 only), the original GARbro, Il2CppDumper (2022.2), UniExtract2. Prefer active forks or alternatives.
- **Untrusted-input safety:** pickle in Ren'Py, plus the general rule that game files are untrusted. Backends that parse in-process (UnityPy, our readers) are attack surface; risky formats can be isolated in a subprocess.
- **Legal and terms-of-service exposure** grows with each engine and with runtime capture (doc 11).
