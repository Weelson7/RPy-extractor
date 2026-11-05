# ViWo // Vidya Wormhole

**A community-owned, local-first orchestrator for game reverse engineering.**

Point ViWo at a game folder. It recognizes the engine, routes every container to the best
available tool (with a spare when that tool is missing or fails), collects everything into one
curated workspace and records where every file came from. From there it analyses the game's
code, works with the running game, and writes your changes into a patched copy. Your game folder
is never modified. Each job runs headless for batch work or hands off to a GUI tool ("Continue in
Ghidra / x64dbg / Cheat Engine") that ViWo opens pre-loaded as a tracked child process.

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
   information: warnings plus one opt-in (a feature switch and a confirmation), never a gate.
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

## What it does: three arms

`viwo -h` lists every command by arm; `viwo <arm>` lists one; `viwo <arm> <command>` equals
`viwo <command>`. Add `--json` to any command for a machine-readable envelope.

**Static: the game is not running.**

| Command | What it does |
|---------|--------------|
| `viwo survey <game or library> [--deep]` | read-only: per game, the engine, which files each tool can open, dense unknown blobs |
| `viwo detect <game>` | which engine a folder uses |
| `viwo extract <game> --workspace <ws>` | unpack, export, carve and decode into a workspace grouped by extension, with a provenance map and a run record |
| `viwo replay <run record> --workspace <ws>` | re-run an extraction |
| `viwo unpack <archive> --out <dir>` | one archive, nested ones too |
| `viwo sanitize <ws> [--apply] [--undo TOKEN]` | empty, junk, duplicate and mislabeled files; plan, apply, undo |
| `viwo analyze <game> --list`, `--target KEY --workspace <ws> [--slot ...] [--open]` | code analysis of a copy: Ghidra (native), ilspycmd (.NET), Cpp2IL (IL2CPP), unrpyc, GDRE Tools, unluac, Detect It Easy, Unicorn and angr on isolated routines; opt-in feature `analysis` |
| `viwo diff <old> <new>` | function-by-function diff of two Ghidra analyses (update-resilient offsets) |

Engines: Ren'Py, Unity, Godot, Unreal (pak and IoStore, AES keys from you or the game's own
files, verified), Doom, RPG Maker, KiriKiri, Electron/NW.js, Source, Bethesda, Age of Empires,
Total War, Cyberpunk 2077, Bannerlord, Overwatch (DataTool), QuickBMS scripts for any other
format, plus zip, tar, 7z, rar. Anything unrecognized goes through a signature carver and
zlib/gzip/zstd/LZ4 stream inflation; game audio, DDS, Bink, SLP and `.rpyc` are decoded into
files anything can open.

**Dynamic: the game is running.** Opt-in feature `capture`, warnings and one confirmation.

| Command | What it does |
|---------|--------------|
| `viwo capture <game> --exe <exe> --workspace <ws> --confirm [--auto SECONDS]` | GPU frames through RenderDoc: textures and shader disassembly, unattended by default |
| `viwo agent <game> --exe <exe> --workspace <ws>` | the engine's runtime agent in a patched copy: UE4SS (Unreal mappings, object dump), BepInEx (Unity IL2CPP interop assemblies) |
| `viwo dump --name <image> --workspace <ws>` | memory dump of a running game |
| `viwo trace --name <image> --workspace <ws> [--functions ...]` | API calls through Frida |
| `viwo record --workspace <ws> [--seconds S]` | the game's sound from the system output, to WAV |
| `viwo attach <game> --target <key> --workspace <ws> --confirm [--tool cheatengine-gui] [--pid N]` | continue in x64dbg on the game's own process (attached when it runs, started otherwise: live patching), or in Cheat Engine with a ViWo table; no `--target` lists the targets |

The same tools open from RUNTIME, DEBUGGER AND MEMORY.

**Patching: you change its content**, always in a marked patched copy.

| Command | What it does |
|---------|--------------|
| `viwo repack <ws> --plan`, `--out <dir>` | your edited workspace files repacked into a patched copy, verified by re-extraction |
| `viwo patch <game> <set.patch.json> --plan`, `--out <dir>` | byte patches by offset, RVA or AOB pattern, assembly through Keystone, with a byte diff and an AOB export |
| `viwo mod pack\|check\|apply <game> <mod.zip>...` | a patched copy's changes as a mod; check it against another game version; apply several in order |

## Install

Python 3.11 or newer, from the repository folder:

```bash
pip install -e ".[unity,sevenzip,renpy,lz4]"
viwo serve
```

`viwo serve` (or `python Start.py`) opens the web UI. On first start the landing screen runs the
preflight: every missing tool is downloaded from its pinned release (HTTPS, size and sha256
checked against `viwo/data/tools.json`) into `third_party/<tool>/` next to `startup.ini`. Nothing
is installed anywhere else, and nothing is asked of you. Ghidra and angr install only when asked
(`viwo install ghidra`). From the command line:

```bash
viwo slots            # slot bindings and what is found where
viwo install --all    # everything missing that has a pin
viwo install --game skyrim-se    # what a per-game index entry needs
```

A path in `[tools]` of `startup.ini` wins over `third_party/`, which wins over `PATH`. Every tool
is optional: a missing one disables only what needs it, and `viwo slots` / SYSTEM say what to
install. Data goes to `viwo-data/` next to `startup.ini`. A portable Windows build
(`viwo.exe`, no Python needed) ships with each release.

## Web UI

Plain HTML and ES modules served by `viwo serve` on `127.0.0.1:8081`, with a per-start token.
The top bar holds SYSTEM (tools, install, diagnostics, updates), JOBS, WORKBOOKS (step-by-step
how-tos for x64dbg, Ghidra and Cheat Engine's own interfaces; `viwo workbook`), RUNBOOKS (named
step sequences: ViWo's actions run as jobs, the steps you do pause the run; edit and save your
own; `viwo runbook ID --run`), SETTINGS, the shared game selector and the workspace. The rail shows one arm at a time, each opening on its end-to-end
path: STATIC (SURVEY, EXTRACT, WORKSPACE, SORT, CLEANUP, MERGER, ANALYSIS),
DYNAMIC (CAPTURE, RUNTIME), PATCHING (PATCHED COPY, PATCHES + MODS). Two themes
(`wormhole`, `plain`). Details: [docs/ui.md](docs/ui.md).

## Configuration

Everything lives in [`startup.ini`](startup.ini): features, plugins, which tool is main or spare
for each slot, tool locations, plugin options and the `[server]` section. Ready-made
configurations live in [`distros/`](distros/) (`<linux|windows>-<renpy|unity|unreal|godot|custom|mixed>.ini`);
point `startup.ini` at one with `[startup] base = distros/windows-unity.ini`.

```bash
viwo config generate                       # rewrite distros/ from the registry
viwo config check startup.ini distros/*.ini
```

## Development

```bash
python -m unittest discover -s tests -t .
python tools/loc_count.py --report
```

Real-tool tests run with `VIWO_L5=1`. Code size is capped (40 lines per function, 250 per file,
budgets per package in [`loc_caps.ini`](loc_caps.ini)). Commits go through `tools/version.py`
(see [CONTRIBUTING.md](CONTRIBUTING.md)).

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md): module map and layer rule.
- [docs/contract/](docs/contract/README.md): the normative design; [CONFORMANCE.md](docs/contract/CONFORMANCE.md): what is implemented, partial or open.
- [docs/HANDOFF.md](docs/HANDOFF.md): current state, how to work, open work.
- [CHANGELOG.md](CHANGELOG.md): what changed per version.
- [docs/plugins.md](docs/plugins.md) (drop-in plugins and add-ons), [docs/ui.md](docs/ui.md), [docs/indexes.md](docs/indexes.md).
- [sqc/00-README.md](sqc/00-README.md): manual check suite. [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md): third-party licenses.

## Legal and disclaimer

ViWo is a community tool under the MIT license. Fork it, change it, ship it; the community, not
one author, decides what it becomes.

**Use and misuse.** ViWo extracts, analyses and patches games on your own machine and fits every
use listed under Philosophy, including ones nobody here intends: piracy, cheating, circumventing
protections. The project neither condones nor suggests such use. It is conscious that the tool
could reasonably be used that way, and the person using it is responsible for how they use it,
for what they do with what comes out, and for the license and terms of the games they work with.
Distributing extracted assets is a separate matter from extracting them. The authors accept no
responsibility for misuse.

**Third-party tools and scripts.** ViWo downloads, pins and runs third-party tools (archive
tools, engine unpackers and exporters, media tools, decompilers and disassemblers, debuggers and
memory editors, capture tools, runtime agents and tracers; the full list with licenses is in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)) and community data (QuickBMS scripts and
per-game indexes). Each keeps its own license and its own authors; ViWo's authors are not theirs.
Some of these tools and scripts can be misused: a script that opens an encrypted format, a
capture tool or a debugger run next to a protected game, an unpacker pointed at an archive you
have no right to. We do not condone or suggest that, and we are conscious of it. ViWo itself
ships no code whose purpose is defeating copy protection, brute-forcing keys or evading
anti-cheat; anything of that kind is, and stays, third-party, and the responsibility for using
it is the user's.

**No boundaries in the code.** ViWo refuses nothing because of what a game is. Anti-cheat,
online titles and terms-of-service-sensitive plugins produce warnings, you confirm once, and the
tool runs; what follows (blocked captures, banned accounts, broken terms) is yours. What the code
does guarantee is engineering, not policy: the game folder is copied from and never written to;
writes from untrusted archive names are traversal-checked; secrets are never written to disk; the
local server binds to this machine with a token; downloads are pinned, checksummed and HTTPS
only, into `third_party/` and nowhere else.

GPL tools only run as separate processes.

Original author of ViWo: Weelson.

Special thanks: the **currently non-existent** community.
