# 8. Slots and backends (main + spare)

Every tool ViWo drives is reached through an **interface** and bound into a **slot**. A slot has
one **main** backend and, where it makes sense, one **spare**. No stage calls a tool directly; it
asks its slot (`viwo/contracts/slots.py`, `viwo/core/wiring/binder.py`,
`viwo/core/pipeline/failover.py`). Wiring is resolved at boot from the slot defaults and the
ini's `[slots]` section (doc 9).

```
 Stage --uses--> Slot "unarchive.7z"  (interface: Unarchiver)
                   main : sevenzip-cli   (7z / 7z.exe)
                   spare: py7zr          (pip package)
```

## 8.1 Concepts

```text
SlotDefinition
  slot_id        "<family>.<name>", e.g. "unarchive.rpa"
  family         unarchive | export | carve | decode | probe | media.encode | pack | patch
                 | analysis | handoff | capture | runtime
  owner          "core" or the plugin id that introduces it
  default_main, default_spare
  suffixes, magic, identify(path, head, tail) -> Match    how UNPACK and DECODE pick the slot

Backend
  backend_id, owner, families
  license (SPDX), isolation inprocess|subprocess, network none|download|any,
  parses_untrusted_in_process, self_check_args, requires: [DependencySpec]
  available(os) -> (ok, reason)        side-effect free
  self_check(os) -> (ok, reason)       `viwo slots --check`: available() plus a real run of
                                       every CLI tool (answers within 8 s)

SlotBinding { slot_id, main, spare, promoted, source: default|ini, reasons }
```

A backend may serve no slot and exist only to declare a dependency so preflight, SYSTEM and
`viwo install` see it: `frida-trace` (`viwo trace`) and `soundcard-loopback` (`viwo record`),
each the one tool for its job.

## 8.2 Failover and resolution

Only the `failover` policy exists: run main; if the outcome is retryable, run the spare on the
same item. Outcome kinds (`OutcomeKind`): `ok`, `unavailable` (retry), `failed` (retry; a backend
exception counts as failed), `needs_key` (never retried). Cancellation is the job's concern.

Binding at boot:

1. An ini entry naming an unknown backend, or one that does not serve the slot's family, is a
   problem for that entry only; the default is used.
2. A default spare whose plugin is switched off is simply absent.
3. If the main is available it stays main; if not and the spare is, the spare is **promoted**
   (shown in `viwo slots` and SYSTEM); if neither is, the slot is **unbound** and stages that
   need it report `unavailable` with the install hint. The app does not crash.

**Never silent (owner's rule):** when the spare runs, the outcome carries `fallback` ("<main>
<kind>: <error>; used <spare>"); when both fail, the error names both. Every stage turns it into
a warn event (CLI stderr, also with `--json`; the GUI job log) and, where it keeps warnings, into
the result. An export that is `ok` but wrote nothing, or returned notes, says so too.
An unpacker counts every entry it skips by reason (an unsafe name, a missing part file, an
archive cut short) and returns the counts as notes; the unpack stage logs each note as a warning
and lists it among the run's warnings. A declared size of 0 never means "inflate without a
limit", and a stored segment past the end of its archive fails rather than writing a stub.

Every result records which backend produced it: `byBackend` (unpack) and
`plugins[].exportedByTool` (export).

## 8.3 Interfaces

```text
Unarchiver   (unarchive)    extract(archive, dest, ctx) -> Outcome; supports_keys
Exporter     (export)       export(ctx) -> Outcome                  into ctx.staging
Carver       (carve)        carve(path, dest, ctx) -> Outcome       never decrypts
Decoder      (decode)       decode(path, dest, ctx) -> Outcome      viewable copies
Prober       (probe)        probe(path, ctx) -> Outcome             facts in notes ("format=png")
MediaEncoder (media.encode) the merger's ffmpeg builds; honours max_command_length
Packer       (pack)         pack(container, members, ctx); output_for(container); verify(...)
Patcher      (patch)        byte writes, Keystone assembly, capstone disassembly (doc 18.8)
Analyzer     (analysis)     analyze(target, ctx)                    doc 6
Handoff      (handoff)      prepare(target, ctx) -> LaunchSpec | Outcome      8.3a
capture      (capture)      RenderDoc capture and harvest           doc 11
RuntimeAgent (runtime)      accepts, install, finished, outputs     doc 11.2
```

## 8.3a Interactive handoff: "continue in &lt;tool&gt;"

GUI-first tools are not driven headless; ViWo prepares the target and hands off
(`viwo/contracts/analysis.py` `Handoff`, `LaunchSpec { argv, cwd, env }`).

| Slot | Backend | Label | Accepts | What `prepare` does |
|------|---------|-------|---------|---------------------|
| `handoff.native` | `ghidra-gui` | Continue in Ghidra | `native_binary` | opens the project of the headless run, JVM started directly |
| `handoff.debug` | `x64dbg-gui` | Continue in x64dbg | `native_binary` | starts the executable under x64dbg (x32dbg for 32-bit PEs), stopping at the system breakpoint |
| `handoff.memory` | `cheatengine-gui` | Continue in Cheat Engine | `native_binary` | writes a ViWo table that attaches to the game's process when it runs, then opens Cheat Engine |

Rules:

- The tool runs as a **tracked child** (`ProcessRunner.launch`): it is killed when ViWo exits; the
  CLI waits for it (`viwo analyze --open`).
- Every first-run question of the tool is pre-answered off screen before launch (Ghidra user
  agreement and tips, x64dbg release notes, Cheat Engine CEShare and table-Lua prompts), only when
  the user has not answered it; a value that cannot be written is said.
- A handoff that runs the game (debugger, memory editor) is a dynamic action. Handoffs are
  declared and overridable like any backend.

## 8.4 Default slot table

`viwo slots` prints the effective table; `viwo config generate` writes it into the distros.

**Unarchive** (UNPACK picks by longest suffix, then magic, then the identifier):

| Slot | Owner | Main | Spare | Notes |
|------|-------|------|-------|-------|
| `unarchive.zip` | core | `py-zipfile` | `sevenzip-cli` | `.zip`, `.nw` |
| `unarchive.tar` | core | `py-tarfile` | `sevenzip-cli` | `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz`, `.tbz2`, `.tar.xz`, `.txz` |
| `unarchive.7z` | core | `sevenzip-cli` | `py7zr` | |
| `unarchive.rar` | core | `unrar-cli` | `sevenzip-cli` | |
| `unarchive.rpa` | renpy | `rpa-safe` | `unrpa` (GPL-3.0, subprocess) | restricted unpickler (D11) |
| `unarchive.unitypackage` | unity | `py-tarfile` | `sevenzip-cli` | |
| `unarchive.pck` | godot | `gdre-tools` | `godotpcktool` | `GDPC` head or exe trailer; embedded PCKs carved first |
| `unarchive.upak` | unreal | `repak-cli` | `quickbms-cli` (when the quickbms plugin is on and a `.pak` script exists) | AES per D18 |
| `unarchive.utoc` | unreal | `retoc-legacy` | `retoc-unpack` | IoStore `.utoc`/`.ucas` |
| `unarchive.wad` | doom | `wad-builtin` | - | |
| `unarchive.rgssad` | rpgmaker | `rgssad-builtin` | - | `.rgssad`, `.rgss2a`, `.rgss3a` |
| `unarchive.xp3` | kirikiri | `xp3-builtin` | - | |
| `unarchive.asar` | electron | `asar-builtin` | - | |
| `unarchive.vpk` | source | `vpk-builtin` | - | identifier for `_dir.vpk` sets |
| `unarchive.bsa`, `unarchive.ba2` | bethesda | `bsa-builtin`, `ba2-builtin` | - | LZ4 through the `lz4` pin |
| `unarchive.drs` | genie | `drs-builtin` | - | |
| `unarchive.pack` | warscape | `pack-builtin` | - | |
| `unarchive.archive` | redengine | `rdar-builtin` | - | |
| `unarchive.tpac` | taleworlds | `tpac-builtin` | - | |
| `unarchive.bms` | quickbms | `quickbms-cli` (GPL-2.0, subprocess) | - | suffixes from the scripts folder |

**Export:** `export.unity` (`unitypy`, spare `assetstudiomod-cli`, D7), `export.godot`
(`gdre-recover`, opt-in option `recover`), `export.rpgmaker` (`rpgmv-builtin`),
`export.overwatch` (`datatool`, declares `network = "download"`), `export.warscape` (`db-builtin`: every `db/` member of every pack to JSON with the
game's RPFM schema `rpfm-schema-<game>`; a table the schema lacks or misreads is counted and
named), `decode.loc` (`loc-builtin`, Total War localisation to JSON), `export.unreal` (`uas-export`:
UnrealAssetScout as its own process, every mode over every Paks folder with the engine version
read from the game's binaries, the AES key per D18 and the `.usmap` the RUNTIME agent wrote into
the workspace; packages that need mappings are counted and the way to get them named).

**Carve and decode:** `carve.signatures` (`signature-carver`); `decode.audio` (`vgmstream-cli`,
spare `ffmpeg-decode`; Wwise, FMOD, CRI, XACT and console audio to WAV); `decode.image`
(`ffmpeg-image`, DDS to PNG); `decode.video` (`ffmpeg-video`, Bink to MP4, opt-in); `decode.bink2` (`bink-game`: Bink 2 to MP4
through the game's own `bink2w64.dll` in a helper process, frames piped into ffmpeg, opt-in with
video); `decode.cr2w` (`wolvenkit-export`, redengine: WolvenKit's console, GPL-3.0 as its own
process, one run per batch of 150 files: `export` turns textures into PNG and meshes, morph
targets, cubemaps and animations into glTF, `convert serialize` turns every CR2W resource into
JSON; ViWo writes the export settings it needs into WolvenKit's `appsettings.json` off screen and
every file WolvenKit could not convert is counted in one warning); `decode.redscripts` (`redscript-decompile`, redengine, option `decompile`:
redscript's console, MIT, Windows build, decompiles `final.redscripts` into one `.script` file per
stored script); `decode.rpyc`
(`unrpyc-cli`, renpy, option `decompile`); `decode.slp` (`slp-builtin`, genie).

**Media:** `media.probe` (`ffprobe-probe`, spare `pillow-probe`), `media.encode` (`ffmpeg`).

**Pack (doc 18):** `pack.zip` (`zip-packer`), `pack.rpa` (`rpa-writer`), `pack.pck`
(`godotpcktool-pack`), `pack.upak` (`repak-patch`, `_P.pak`), `pack.archive` (`wolvenkit-pack`, override archive in `archive/pc/mod`), `pack.unity` (`unitypy-pack`),
`pack.rpgmaker` (`rpgmv-pack`). **Patch:** `patch.bytes` (`viwo-patcher`, owns the Keystone and
capstone dependencies).

**Analysis (doc 6):** `analysis.native`, `.dotnet`, `.il2cpp`, `.script`, `.python`,
`.gdscript`, `.protector`, `.emulate`, `.symbolic`. **Handoff:** `handoff.native`, `.debug`,
`.memory` (8.3a).

**Dynamic (doc 11):** `capture.gpu` (`renderdoc`), `runtime.unreal` (`ue4ss-agent`),
`runtime.unity` (`bepinex-agent`).

**Declarations:** every backend declares `license`; a GPL/AGPL backend has `isolation =
"subprocess"`; `network` is `none` unless the tool fetches (`datatool`, `bepinex-agent`:
`download`); in-process parsers of game bytes set `parses_untrusted_in_process` (L0 test).

## 8.5 How the stages use slots

| Stage or job | Interface | Slot lookup |
|--------------|-----------|-------------|
| DETECT | `EnginePlugin.detect` | - |
| UNPACK | Unarchiver | `unarchive.*` whose suffix, magic or identifier matches |
| EXPORT | Exporter | the plugin's `export_slot()` |
| CARVE | Carver | `carve.signatures` |
| COLLECT / DECODE | Decoder | `decode.*` by suffix: core slots on every game, a plugin's slots only when that plugin was chosen for the game |
| VERIFY | `EnginePlugin.verify_report` | - |
| merger | Prober, MediaEncoder | `media.probe`, `media.encode` |
| repack | Packer | the plugin's `pack_slot(unarchive slot)` |
| patch set | Patcher | `patch.bytes` |
| analyze | Analyzer | `analysis.<kind>` or the requested `--slot` |
| handoff | Handoff | every bound `handoff.*` accepting the kind |
| capture | capture | `capture.gpu` |
| agent | RuntimeAgent | `runtime.<engine>` of the detected plugin |

## 8.6 Slot conformance

- Slot ids are unique across core and plugins; a plugin owns the slots it introduces.
- Every default main and spare names a known backend whose `families` include the slot's family
  (a missing spare of a switched-off plugin is allowed).
- `available()` has no side effects; `self_check()` runs each CLI tool once.
- `needs_key` never reaches the spare.
- Binder states main up/down x spare up/down, promotion and unbound slots are tested with fakes
  (`tests/test_core_units.py`, `tests/test_config.py`).
- A plugin may add a backend to a slot it does not own; the ini then makes it main or spare.
