# ViWo // Vidya Wormhole

**A community-owned, local-first orchestrator for game reverse engineering.**

Point ViWo at a game folder. It recognizes the engine, routes every container to the best
available tool (with a spare when that tool is missing or fails), collects everything into one
curated workspace, and records where every file came from. Your game is never modified. Asset
extraction is the mature arm; the orchestrator spans three (see "What a reverse engineer can do"):
**static** (extraction + code/data analysis), **dynamic/runtime** (capture, debugging,
instrumentation, memory, hooking, own-traffic networking, profiling), and **authoring** (round trip,
binary patching, mod packaging). Each arm runs headless for batch work or hands off to a GUI tool
with a **"continue in &lt;tool&gt;"** button that opens Ghidra, x64dbg, RenderDoc or the like,
pre-loaded, as a child process.

- **Engines:** Ren'Py, Unity, Godot, Unreal, Doom engine, plain archives (zip, tar, 7z, rar), and a
  carver that pulls standard files (images, audio, video, archives) out of anything unrecognized.
- **Never touches the game:** files are copied, never moved; a workspace or temp folder inside the
  game folder is refused; every run compares the game folder before and after.
- **Main + spare tools:** each job (unpack `.rpa`, export Unity assets, unpack a Godot PCK...) has a
  main backend and a spare; a missing tool disables only what needs it.
- **Curation built in:** extension groups, a keyboard-driven sorting view with previews, undo,
  and a media merger that turns frames and clips into one video.
- **Reproducible:** every run leaves a run record and a provenance map; `viwo replay` re-runs it.
- **Safe by default:** traversal-safe unpacking, Ren'Py archive indexes read with a pickle
  allow-list, a per-start API token for the local web UI, secrets never written to disk.

## Philosophy

1. **What ViWo is.** A community-owned, open-source orchestrator for game reverse engineering.
   ViWo itself stays small: wiring, provenance, curation, round trip, and care for your own data.
   Capability comes from pinned third-party tools and from community data: per-game indexes and
   scripts (`indexes/`). MIT, forkable; the community decides what it becomes.
2. **Who it is for.** Everyone who wants to look inside a game: reverse engineers, modders,
   artists (fan art, references, texture and model study), translators, data miners, researchers,
   preservationists, competitive players, crackers, cheaters, the curious. The tool does not judge
   the user or the purpose.
3. **No boundaries, no safeguards in the tool.** ViWo refuses nothing because of what a game is,
   which plugin runs, or what you intend. No blocking lists, no plugin that detection may not
   pick, no refusals for anti-cheat or online titles. Anti-cheat and online detection stay as
   information: warnings plus one opt-in (the capture feature switch and a confirmation), never a
   gate.
4. **Disclaimer instead of safeguards.** ViWo and the third-party tools and scripts it ships could
   be misused: piracy, cheating, circumventing protections. The project neither condones nor
   suggests it, is conscious of it, and places the responsibility entirely on you (see "Legal and
   disclaimer").
5. **Borderline code is third-party, never first-party.** ViWo does not author DRM-defeating,
   key-brute-forcing or anti-cheat-evading code. If such things exist, they are third-party tools
   or community scripts, pinned like everything else and covered by the disclaimer.
6. **Engineering properties are not boundaries.** Copy-not-move, traversal checks on archive
   names, secrets kept out of logs, a localhost-only server, checksummed pinned downloads: these
   are how the features work and protect your data and machine, not your reach. Any of them that
   blocks a wanted capability becomes an option.
7. **Reach.** Everything on disk and at runtime comes out, through a ladder of rungs, and
   coverage grows with community indexes per game and game version.

## What a reverse engineer can do with it

Today and as it grows:

- **Survey and discovery:** engine, version and packaging of each game; which files each tool
  can open; density estimates that flag encrypted or compressed blobs; reports over a library.
- **Unpacking:** engine archives (Ren'Py, Unity, Godot, Unreal with verified keys, Doom, RPG
  Maker, KiriKiri, Electron, Source, Bethesda, Age of Empires DRS, Total War packs, Cyberpunk 2077
  archives, Overwatch via DataTool), generic containers, nested
  archives, and QuickBMS scripts for every format without a plugin, supplied per game by the
  indexes.
- **Carving and stream inflation:** standard files hidden inside unknown data; zlib and gzip
  streams inflated and carved.
- **Decoding:** textures to PNG, game audio to WAV, Bink video to MP4; next: meshes to glTF,
  fonts, script decompilation, localization tables.
- **Runtime capture:** GPU frames through RenderDoc for content that only exists at runtime,
  then a diff against static extraction.
- **Static code analysis (opt-in, 1.3):** the plugins name the binaries (the player executable,
  Unreal's shipping exe, Unity's IL2CPP and managed assemblies, script bytecode); Ghidra analyses
  a copy headless into the workspace (functions, decompiled C, strings, symbols) and CONTINUE IN
  GHIDRA opens the same project in the GUI. Next rungs, same slot system: ilspycmd and Cpp2IL for
  managed code, library/middleware signatures, protector identification, version diffing for
  update-resilient offsets, emulation of isolated routines. Everything reads a copy; the game is
  never run.
- **Dynamic and runtime (opt-in, journaled):** GPU frame capture through RenderDoc for content that
  only exists at runtime, engine agents (BepInEx, UE4SS) that dump live objects or feed the static
  arm, plus debugging, instrumentation and tracing, memory inspection, runtime hooking, your-own-
  traffic networking and profiling. Off by default behind the `runtime` flag, with warnings and one
  confirmation; ViWo authors no anti-cheat evasion or copy-protection defeat.
- **Continue in &lt;tool&gt;:** any target hands off to its GUI tool pre-loaded — Ghidra on an
  imported project, x64dbg launched suspended, RenderDoc on a capture, ReClass.NET on a live struct
  — as a child process ViWo tracks and tears down with the job.
- **Curation:** sort, deduplicate, rename, sanitize and trash with undo; provenance per file.
- **Modding, round trip and patching:** edit assets and repack into a verified patched copy; author
  byte- and assembly-level binary patch sets with AOB signatures and portable patch export; package
  mods with a loader, a stable hook API, a crash handler and an update checker.
- **Reproducibility and automation:** run records and replay, a pinned toolchain, per-game
  indexes the community can extend, a CLI with JSON envelopes and a local API.

## Quick start (test it locally)

1. Python 3.11 or newer.
2. From the repository folder:

   ```bash
   pip install -e ".[unity,sevenzip,renpy]"
   ```

3. Start the web UI (it opens your browser; `--no-browser` to skip):

   ```bash
   viwo serve
   ```

   Data goes to `viwo-data/` next to `startup.ini` (workspace, merger output, logs, temp). Plain
   `viwo` prints a short guide; `python Start.py` does the same as `viwo serve`.

4. Tools install themselves. On the first start the landing screen runs the preflight: every
   optional tool that is missing is downloaded from its pinned release (HTTPS, size and sha256
   checked against `viwo/data/tools.json`) into `third_party/<tool>/` next to `startup.ini`.
   Nothing is installed anywhere else, and nothing is asked of you. From the command line:

   ```bash
   viwo slots            # what is found, and where
   viwo install --all    # install everything missing that has a pin
   viwo install unrar    # one tool
   ```

   Pinned tools (version, license and checksum live in `tools.json`): 7-Zip, unrar, ffmpeg and
   ffprobe, vgmstream, GDRE Tools, GodotPckTool, AssetStudioModCLI (on a ViWo-owned .NET runtime
   under `third_party/dotnet`), repak, retoc, QuickBMS, DataTool (Windows), RenderDoc
   (`renderdoccmd` and its embedded Python for harvesting), plus the Python packages UnityPy,
   py7zr, unrpa and lz4. Precedence: a path set in `[tools]` wins over `third_party/`, which wins over PATH.

Every tool is optional: a missing one disables only what needs it, and `viwo slots` / 05 SYSTEM
say what to install. The engine tools can also be set with environment variables
(`VIWO_REPAK`, `VIWO_GDRE`, `VIWO_VGMSTREAM`, ...).

Command line:

```bash
python -m viwo.cli detect "/path/to/game"
```

```bash
python -m viwo.cli extract "/path/to/game" --workspace ./ws
```

```bash
python -m viwo.cli replay ./ws/.extraction_metadata/runs/<job>.json --workspace ./ws-again
```

More commands (add `--json` to any of them for machine-readable output):

| Command | What it does |
|---------|--------------|
| `viwo survey <library or game>` | read-only: per game, what ViWo can pull and what it cannot (`--deep` also tries the carver) |
| `viwo sanitize <workspace>` | find empty, junk, duplicate, mislabeled or broken files; `--apply` the safe fixes, `--undo TOKEN` |
| `viwo repack <workspace> --out DIR` | build a patched copy of the game with the files you edited (`--plan` first); verified by re-extraction |
| `viwo capture <game> --exe EXE --workspace WS --confirm` | runtime capture with RenderDoc for what static extraction cannot reach (off by default, policy-checked) |
| `viwo analyze <game> --list`, `--target KEY --workspace WS [--open]` | static analysis: list the binaries the plugins propose, run Ghidra headless on one into `WS/.analysis/`, or open the project in Ghidra (feature `analysis`, off by default) |
| `viwo unpack <archive> --out DIR`, `viwo info`, `viwo slots` | single archive, configuration, tool status |

## How far it reaches

Anything stored on your disk should come out, through a ladder of fallbacks: engine plugins with
real names, container unpackers, a carver that finds standard files (images, audio, video,
archives) inside unknown data, zlib/gzip stream inflation, decoders that turn game audio and
textures into WAV/PNG, QuickBMS scripts for custom formats, and runtime capture as the last rung.
`viwo survey` shows where each of your games stands. Not shipped: code for defeating copy
protection or brute-forcing keys; content that only exists on a server is out of reach.

## Supported engines and tools

| Engine | Unpack / export | Main | Spare |
|--------|-----------------|------|-------|
| any | zip, tar | Python standard library | 7-Zip |
| any | 7z / rar | 7-Zip / unrar | py7zr / 7-Zip |
| Ren'Py | `.rpa` archives; `.rpyc` scripts decompiled to `.rpy` (option `decompile`) | built-in safe reader; unrpyc | unrpa |
| Unity | assets, meshes to OBJ (option `meshes`) | UnityPy | AssetStudioModCLI |
| Godot | `.pck`, PCK embedded in the executable | GDRE Tools | GodotPckTool |
| Unreal | `.pak` (any version, AES per user key or found in the game executable) | repak | — |
| Unreal 5 | IoStore `.utoc`/`.ucas` | retoc (to legacy assets) | retoc (raw packages) |
| Doom engine | IWAD/PWAD: PNG, WAV, MIDI, maps | built-in reader | — |
| RPG Maker | XP/VX/VX Ace archives; MV/MZ encrypted images and audio (key from System.json) | built-in | — |
| KiriKiri | `.xp3` (unencrypted entries; per-title ciphers are reported) | built-in | — |
| Electron / NW.js | `app.asar` (`package.nw` is a zip) | built-in | — |
| Source engine | `.vpk` (v1/v2, multi-part) | built-in | — |
| Bethesda | `.bsa` (103–105; LZ4 needs `lz4`), `.ba2` (files, textures rebuilt as DDS) | built-in | — |
| anything else | files hidden inside unknown data, zlib/gzip streams | built-in carver | — |
| any custom format | your `.bms` script per extension | QuickBMS | — |
| decoders | Wwise / FMOD / CRI / XACT / console audio to WAV; DDS to PNG; Bink to MP4 (opt-in) | vgmstream / ffmpeg | ffmpeg |
| media merger | video build | ffmpeg | — |

From a checkout, `pip install -e ".[unity,sevenzip,renpy,lz4]"` installs the `viwo` command and
the optional Python tools; every other tool installs itself into `third_party/` (see Quick start),
or is found on PATH, or is set in the `[tools]` section of `startup.ini`.

## Configuration

Everything lives in [`startup.ini`](startup.ini): enabled plugins, which tool is main or spare for
each job, tool locations, and the `[server]` section (host, port, default workspace, merger output,
logs, temp folders).

Ready-made configurations ("distros") live in [`distros/`](distros/): one per OS layer and
profile, named `<os>-<profile>.ini` (`linux|windows` x `renpy|unity|unreal|godot|custom|mixed`).
Point `startup.ini` at one with `[startup] base = distros/windows-unity.ini`; anything in
`startup.ini` overrides it.

```bash
viwo config generate
```

```bash
viwo config check startup.ini distros/*.ini
```

`generate` rewrites the 12 files from the plugin and slot registry (it never overwrites a file it did
not generate); `check` enforces the rules strictly (file names, known sections, plugins, slots and
backends, no secrets) and exits with code 2 on any problem.

## Development

```bash
python -m unittest discover -s tests -t .
```

```bash
python tools/loc_count.py --report
```

Real-tool tests run with `VIWO_L5=1`; CI runs everything on Linux and Windows. Code size is capped
(non-blank, non-comment lines: 40 per function, 250 per file; budgets per package in
[`loc_caps.ini`](loc_caps.ini)).

## Documentation

- Architecture contract: [docs/contract/](docs/contract/README.md)
- Prototype A status and decisions log: [docs/prototype-a/STATUS.md](docs/prototype-a/STATUS.md)
- Prototype B status, evidence and open items: [docs/prototype-b/STATUS.md](docs/prototype-b/STATUS.md)
- Per-game indexes (schema, contribution, updates): [docs/indexes.md](docs/indexes.md)
- Drop-in plugins: [docs/plugins.md](docs/plugins.md); contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Manual check suite: [sqc/00-README.md](sqc/00-README.md); third-party licenses: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- Handoff and open work: [docs/HANDOFF.md](docs/HANDOFF.md)

## Legal and disclaimer

ViWo is a community tool under the MIT license. Fork it, change it, ship it; the community, not
one author, decides what it becomes.

**Use and misuse.** ViWo extracts files from games on your own machine and fits every use listed
under Philosophy, including ones nobody here intends: piracy, cheating, circumventing protections.
The project neither condones nor suggests such use. It is conscious that the tool could reasonably
be used that way, and the person using it is responsible for how they use it, for what they do
with what comes out, and for the license and terms of the games they work with. Distributing
extracted assets is a separate matter from extracting them. The authors accept no responsibility
for misuse.

**Third-party tools and scripts.** ViWo downloads, pins and runs third-party tools (7-Zip, unrar,
ffmpeg, vgmstream, GDRE Tools, GodotPckTool, AssetStudioModCLI, repak, retoc, QuickBMS, DataTool,
RenderDoc, a .NET runtime, UnityPy, py7zr, unrpa, lz4) and community data (QuickBMS scripts and
per-game indexes). Each keeps its own license and its own authors; ViWo's authors are not theirs.
Some of these tools and scripts can be misused: a script that opens an encrypted format, a
capture tool run next to a protected game, an unpacker pointed at an archive you have no right
to. We do not condone or suggest that, and we are conscious of it. ViWo itself ships no code
whose purpose is defeating copy protection, brute-forcing keys or evading anti-cheat; anything
of that kind is, and stays, third-party, and the responsibility for using it is the user's.

**No boundaries in the code.** ViWo refuses nothing because of what a game is. Anti-cheat,
online titles and terms-of-service-sensitive plugins produce warnings, you confirm once, and the
tool runs; what follows (blocked captures, banned accounts, broken terms) is yours. What the code
does guarantee is engineering, not policy: the game folder is copied from and never written to;
writes from untrusted archive names are traversal-checked; secrets are never written to disk; the
local server binds to localhost with a token; downloads are pinned, checksummed and HTTPS only,
into `third_party/` and nowhere else.

GPL tools only run as separate processes.

Original author of ViWo: Weelson. 

Special thanks: the **currently non-existent** community.

