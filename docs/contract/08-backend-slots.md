# 8. Pipeline backends and slots (main + spare)

(Your term "pipeline engine" = **backend** here, per the glossary.)

**Proposed rule:** every engine the pipeline uses (each unarchiver, exporter,
media tool, image codec and decompiler) is reached through an **interface**
and bound into a **slot**. A slot has one **main** backend and, where it makes
sense, one **spare**. No stage calls a tool directly; it asks its slot.

```
 Stage ──uses──▶ Slot "unarchive.7z"  (interface: Unarchiver)
                   ├─ main : sevenzip-cli   (7z.exe / 7z)
                   └─ spare: py7zr          (pip package)
```

Wiring is decided at startup from the `.ini` file (doc 9). The defaults below
apply when the ini doesn't say otherwise.

## 8.1 Concepts

```text
SlotDefinition
  slot_id        "<family>.<name>"          e.g. "unarchive.rpa", "export.unity"
  family         unarchive | export | media.probe | media.encode | image | analysis
                 | capture | runtime | debug | trace | memory | hook | net | profile   (dynamic arm, doc 11)
                 | pack | patch | mod                                                   (authoring arm, doc 18)
  interface      the interface every backend in this slot implements
  owner          "core" or plugin id that introduces the slot
  matches        how the stage decides the slot applies (suffixes / magic / target kind)
  default_main   backend_id
  default_spare  backend_id | none
  policy         failover | main_only | supplement      (default failover)

Backend
  backend_id     unique, e.g. "sevenzip-cli", "py7zr", "unitypy", "assetripper"
  owner          "core" or plugin id
  families       slot families it can serve
  dependencies() -> [DependencySpec]
  available(OS layer) -> Availability { ok, reason, location }
  ...the interface methods of its family (8.3)

SlotBinding     (result of startup resolution)
  slot_id, main: backend_id | none, spare: backend_id | none
  promoted: bool          # the main was unavailable, so the spare now acts as main
  source: default | ini | cli
```

## 8.2 Policies and failover (proposed)

| Policy | Behavior |
|--------|----------|
| `failover` (default) | Run main. If the outcome is *retryable* (below), run spare on **the same item**. |
| `main_only` | Never run the spare automatically. It is shown in the UI as available. |
| `supplement` | Run main **and** spare, and collect both outputs. Used where extra coverage matters more than duplicates (for example `export.unity`, if decision D7 keeps v1 behavior). |

**Prototype scope:** only `failover` is implemented. `supplement` and `main_only` are kept in the contract for later. Outcome kinds are collapsed to **ok · unavailable · failed · needs_key** (cancellation is handled by the job, not by outcomes); the finer kinds below come back when the sanitizer and capture need them.

**Never silent (owner's rule, 1.5.0):** when the spare runs, the outcome carries `fallback`
("<main> <kind>: <error>; used <spare>"); when both fail, the error names both. Every stage turns
it into a warn event (CLI stderr, also with `--json`; the GUI's job log) and, where the stage
keeps warnings, into the result. An export that is ok but wrote nothing, or that returned notes,
says so too.

Every backend outcome carries an error kind:

| Kind | Retry with spare? |
|------|-------------------|
| `ok` | — |
| `unavailable` (tool missing at call time) | yes |
| `unsupported` (format variant or version not handled) | yes |
| `failed` (tool error, non-zero exit) | yes |
| `corrupt` (data is damaged) | yes, once; if both fail, it's reported as corrupt |
| `encrypted` / `needs_key` | only if the spare declares it supports keys |
| `cancelled` / `timeout` | no |

Resolution at startup:

1. If main is available, it stays main.
2. If main is missing and the spare is available, the spare is **promoted** to main and a warning is shown in the UI and logs.
3. If neither is available, the slot is marked **unbound**. Stages that need it skip those items and report `unavailable` with the install hint. The app does not crash.

Every result records which backend produced it: `by_backend` counts appear in
the unpack and export reports and in `plugins[].exportedByTool`.

## 8.3 Interface families

```text
Unarchiver                     (family: unarchive)
  sniff(path, head) -> bool
  extract(archive, dest, ctx) -> Outcome { kind, files_written, error, notes }
  supports_keys: bool
  # core's recursive loop (queue, seen-set, nested archives, per-archive subdir) is unchanged from v1

Exporter                       (family: export)
  export(ctx) -> ExportReport           # engine-native decode into ctx.staging

MediaProbe                     (family: media.probe)
  probe(path) -> MediaInfo { kind, duration, has_audio, width, height, codec }

MediaEncoder                   (family: media.encode)
  build(timeline, out_path, ctx) -> Outcome     # media merger
  max_inline_args: honors os.process.max_command_length

ImageCodec                     (family: image)
  decode(path) -> ok/kind ; convert(src, dst_format, ctx) -> Outcome

CodeAnalyzer                   (family: analysis)  — doc 6
DynamicBackend                 (families capture/runtime/debug/trace/memory/hook/net/profile)  — doc 11
Packer                         (family: pack)  — doc 18
BinaryPatcher                  (families patch.bytes, patch.sig)  — doc 18.8
```

Backends in the dynamic families (doc 11) additionally carry `touches_running_game: true`, so the
core routes them through the capture journal (`core/capture/journal.py`) and the `dynamic.policy`
warnings-and-opt-in step before they run.

## 8.3a Interactive handoff: "continue in &lt;tool&gt;"

> **1.3:** implemented as `contracts/analysis.py` `Handoff` (a backend of family `handoff`,
> `prepare(target, ctx) -> LaunchSpec | Outcome`) and `ProcessRunner.launch(argv, cwd, env)`
> (doc 1.1): the tool starts as a child in ViWo's process tree, is tracked (`Child.alive`,
> `Child.kill`) and torn down at exit. First handoff: `ghidra-gui` on the project of a headless run.

Much of the real work in reverse engineering happens in GUI tools (Ghidra's listing, x64dbg,
ReClass.NET, RenderDoc's viewer, dnSpyEx, FModel, a hex editor). ViWo does not reimplement them and
cannot drive them headless, but it is the right place to **prepare the target and hand off**. Any
slot, backend or `AnalysisTarget`/capture artifact may offer a **handoff**: a "continue in Ghidra",
"open in x64dbg", "inspect in RenderDoc" action in the UI and CLI.

```text
Handoff
  handoff_id     "ghidra-gui", "x64dbg", "reclass", "renderdoc-ui", "dnspy", "fmodel", "hex"
  label          "Continue in Ghidra"
  accepts        the target kinds / artifact kinds it opens
  prepare(target, ctx) -> PreparedSession    # import the project, build a launch-suspended spec,
                                             # point the tool at the capture file — the glue ViWo owns
  launch_spec                                # handed to os.launch; the tool runs as a tracked child
```

Rules:
- The GUI tool runs as a **child subprocess** launched by the OS layer, inside ViWo's process tree,
  so `os.process` tree-kill and timeouts still reach it (doc 1); closing ViWo or cancelling the job
  tears down the child.
- `prepare()` is the only part ViWo writes: create/import the Ghidra project from a prior
  `analysis.native` run, assemble the launch-suspended `LaunchSpec` for a debugger (doc 11.4), copy
  the target to the patched-copy/scratch area a tool may write to, or just resolve the artifact path.
- A handoff that runs code in the game (a debugger, an injector) is a **dynamic** action: it goes
  through `dynamic.policy` (doc 11.1) and the journal exactly like a backend. A handoff that only
  opens a static file (Ghidra on a copy, a hex editor, FModel on an extracted archive) is a static
  action with no opt-in.
- Handoffs are declared, discoverable and overridable like backends; a plugin or the ini can add
  one (open this engine's files in that engine's community GUI) or repoint the tool path.

This keeps ViWo the orchestrator: headless backends for batch and automation (docs 6, 11, 18),
handoffs for the interactive work, both over the same pinned-tool and OS-layer plumbing.

## 8.4 Default slot table (revised with research, doc 13)

The tool facts behind this table are in doc 13 (checked 2026-11-02). Items
marked ❓ are decisions still open.

**Identify, then extract.** Following unblob, a slot's `matches` is an
**Identifier**. It sees the file's head *and* tail and can report an embedded
chunk (offset, size, format), which core carves out before unpacking. Godot
PCKs embedded in executables, AGS, Love2D and NW.js need this.

**Unarchive:**

| Slot | Owner | Matches | Main | Spare | Notes |
|------|-------|---------|------|-------|-------|
| `unarchive.zip` | core | .zip, zip appended to exe | `py-zipfile` | `sevenzip-cli` | |
| `unarchive.tar` | core | .tar* | `py-tarfile` | `sevenzip-cli` | |
| `unarchive.7z` | core | .7z | `sevenzip-cli` | `py7zr` (LGPL-2.1) | |
| `unarchive.rar` | core | .rar | `unrar-cli` (freeware, non-OSS) | `sevenzip-cli` | |
| `unarchive.rpa` | renpy | .rpa .rpi, `RPA-` header | `rpa-safe` (ours: restricted unpickler) ❓ D11 | `unrpa` (GPL-3.0, subprocess, dormant) | RPA indexes are pickles; never unpickled in-process |
| `unarchive.unitypackage` | unity | .unitypackage | `py-tarfile` | `sevenzip-cli` | |
| `unarchive.unity-bundle` | unity | UnityFS magic | `unitypy` (MIT) | `uabea-cli` (`batchexportbundle`) | |
| `unarchive.unity-webgl` | unity | `.data`, `.unityweb` | `unitypy` | `assetripper` | |
| `unarchive.pck` | godot | `GDPC` at the head, or in the exe trailer | `gdre-tools` (MIT, `--extract`, keys) | `godotpcktool` (unencrypted, carved PCK) | |
| `unarchive.pak` | unreal | .pak | `repak` (MIT/Apache) | `quickbms` (GPL-2.0, subprocess) | never vendor UnrealPak (Epic EULA) |
| `unarchive.iostore` | unreal | .utoc + .ucas | `retoc` (MIT) | our CUE4Parse wrapper | |
| `unarchive.casc` | overwatch (custom) | `.build.info` + `data/casc/` | `datatool` (MIT, .NET 10) | `casclib` (raw files only) | doc 14, S5 |

**Export:**

| Slot | Owner | Main | Spare | Notes |
|------|-------|------|-------|-------|
| `export.unity` | unity | `unitypy` (v1 parity) or `assetstudiomod-cli` ❓ D7 | the other one | AssetStudioModCLI has a real CLI and native Linux build |
| `export.unity-project` | unity | `assetripper` (GPL-3.0, driven over its local HTTP API) | `assetstudiomod-cli` | full project rebuild; optional |
| `export.unreal` | unreal | our CUE4Parse .NET wrapper (Apache-2.0 lib) | `umodel` (UE4 only, dormant) | deferred after the prototype |
| `export.godot` | godot | `gdre-tools --recover` (opt-in `recover` option, 1.2) | none (`godotdec` is Godot 3 only; deferred) | |
| `export.overwatch` | overwatch | `datatool extract-*` | — | catalog → select first |

**Keys:**

| Slot | Main | Spare |
|------|------|-------|
| `keys.unreal-aes` | user-supplied | `aesdumpster` (Windows, license unverified) ❓ |
| `keys.godot` | user-supplied | — |
| `keys.tact` (Overwatch) | pinned bundled keyring, offline | CascLib built-in table |

**Media and images:**

| Slot | Main | Spare |
|------|------|-------|
| `media.probe` | `ffprobe` | `pillow` (images only) |
| `media.encode` | `ffmpeg` | — |
| `audio.decode` (game codecs) | `vgmstream` | — |

**Analysis** (doc 6):

| Slot | Main | Spare |
|------|------|-------|
| `analysis.native` | `ghidra-headless` (JDK 25 for 12.2) | — |
| `analysis.dotnet` | `ilspycmd` | — |
| `analysis.il2cpp` | `cpp2il` | `il2cppdumper` (≤ Unity 2022.2) |
| `analysis.python` (.rpyc) | `unrpyc` v2 | `rpycdec` (isolated environment) |
| `analysis.gdscript` | `gdre-tools --decompile` | — |

**Capture and runtime** (doc 11): `capture.gpu`, `capture.memory`,
`capture.audio`, `runtime.<engine>`. (Frida tracing and the audio loopback recorder, one tool each,
serve no slot: their backends only declare the dependencies.)

**Backend declarations, added after the research:**
- `license` (SPDX). A GPL or AGPL backend must use `isolation: subprocess`.
- `network: none | optional | required`, together with the offline flags used by default.
- `parses_untrusted_in_process: bool`, so risky in-process parsers can be isolated.

**OS-layer-internal fallbacks** are not slots, but they follow the same main and
spare idea (doc 1): on Linux the folder dialog tries tkinter and then
zenity/kdialog; on Windows it tries tkinter and then a PowerShell dialog.

## 8.5 How the stages use slots

| Stage | Interface used | Slot lookup |
|-------|----------------|-------------|
| PROBE / DETECT | GameProbe, `EnginePlugin.detect` | — (plugins are the interface) |
| INVENTORY | `EnginePlugin.inventory` | — |
| UNPACK | Unarchiver | `unarchive.*` slot whose `matches` accepts the file (longest suffix first, then magic) |
| EXPORT | Exporter | `export.<plugin_id>` |
| COLLECT | Workspace (core) | — |
| VERIFY | `EnginePlugin.verify` + MediaProbe (optional health) | `media.probe` |
| SANITIZE | SanitizerRule, which uses `media.*` and `image.*` | by rule |
| REPORT | ManifestWriter (core) | — |
| merger build | MediaProbe + MediaEncoder | `media.probe`, `media.encode` |
| ANALYZE | CodeAnalyzer | `analysis.*` by target kind |

## 8.6 Changes to the plugin contract (doc 2)

The plugin hook `archive_handlers()` is replaced by two hooks:

```text
slot_definitions() -> [SlotDefinition]     # slots this plugin introduces
backends() -> [Backend]                    # implementations it ships
```

A plugin can also add a backend to a slot it doesn't own. For example, a
custom plugin could ship a better `.7z` backend, and the ini can then make it
the main or spare for `unarchive.7z`.

Conformance checks for slots:

- Slot ids are unique across all plugins.
- Every default main and spare names a known backend whose `families` include the slot's family.
- `available()` has no side effects.
- A spare that declares `supports_keys=false` is never called for `needs_key` outcomes.
- The test matrix (doc 3.6) gains one more dimension: for each slot, cases where {main up, main down} × {spare up, spare down}. Fake backends test promotion, failover and the unbound state.
