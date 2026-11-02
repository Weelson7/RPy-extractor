# 8. Engine interfaces and backend slots (main + spare)

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
  available(kernel) -> Availability { ok, reason, location }
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
  max_inline_args: honors kernel.process.max_command_length

ImageCodec                     (family: image)
  decode(path) -> ok/kind ; convert(src, dst_format, ctx) -> Outcome

CodeAnalyzer                   (family: analysis)  — doc 6
```

## 8.4 Default slot table

**Unarchive** (the main reason for spares):

| Slot | Owner | Matches | Main | Spare | Notes |
|------|-------|---------|------|-------|-------|
| `unarchive.zip` | core | .zip | `py-zipfile` (stdlib) | `sevenzip-cli` | spare also handles odd compression methods (deflate64, …) |
| `unarchive.tar` | core | .tar .tar.gz .tgz .tar.bz2 .tbz .tbz2 .tar.xz .txz | `py-tarfile` (stdlib) | `sevenzip-cli` | |
| `unarchive.7z` | core | .7z | `sevenzip-cli` | `py7zr` (pip) | the pip spare means .7z works with no system install |
| `unarchive.rar` | core | .rar | `unrar-cli` | `sevenzip-cli` | same chain as v1 |
| `unarchive.rpa` | renpy | .rpa .rpi | `unrpa` (pip) | `rpa-builtin` | the RPA index is a pickled table, so the built-in reader **must** use a restricted unpickler that allows no globals |
| `unarchive.unitypackage` | unity | .unitypackage | `py-tarfile` (gz) | `sevenzip-cli` | |
| `unarchive.pck` | godot | .pck, plus a PCK embedded in the executable (magic `GDPC`) | `pck-builtin` | `godotpcktool` / `gdre-tools` | key option for encrypted PCKs |
| `unarchive.pak` | unreal | .pak | `repak` | `unrealpak` | AES key option |
| `unarchive.iostore` | unreal | .utoc + .ucas | `retoc` *(to confirm)* | — | needs research before locking |

**Export:**

| Slot | Owner | Main | Spare | Notes |
|------|-------|------|-------|-------|
| `export.unity` | unity | `unitypy` | `assetripper` | v1 also tries **UABEA**, but UABEA has no real command line (v1 guesses three argument formats). Proposal: drop it as a backend (F8). |
| `export.unreal` | unreal | `umodel` | *(to research)* | |
| `export.godot` | godot | `godot-builtin` (resource converters) | `gdre-tools` (`--headless --recover`) | |

**Media and images:**

| Slot | Owner | Main | Spare |
|------|-------|------|-------|
| `media.probe` | core | `ffprobe` | `pillow` (images only) |
| `media.encode` | core | `ffmpeg` | — |
| `image.convert` | core | `pillow` | `imagemagick` |

**Analysis** (doc 6):

| Slot | Main | Spare |
|------|------|-------|
| `analysis.native` | `ghidra-headless` | — (rizin later) |
| `analysis.dotnet` | `ilspycmd` | — |
| `analysis.il2cpp` | `il2cppdumper` | `cpp2il` |
| `analysis.python` (.rpyc/.pyc) | `unrpyc` | — |

**Kernel-internal fallbacks** are not slots, but they follow the same main and
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
