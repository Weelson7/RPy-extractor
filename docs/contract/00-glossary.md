# 0. Glossary and metrics

Every term has one meaning. Code, UI and docs use these words.

## 0.1 Words that are not used alone

| Word | Use instead |
|------|-------------|
| engine | **game engine** (Unity, Ren'Py) or **backend** (a processing unit behind a slot) |
| extract | **extraction run** (the whole request), **unpack** (one archive), **export** (engine-native decoding) |
| phase / slice / step | **stage** (pipeline); **step** only in UI paths |
| detect | **detect** (engine detection); listing extensions is **scan** |
| keep | **retain groups** (trash every unselected group); **mark kept** (sorting, recorded for undo) |
| trash | **group trash**, **item trash**, **merger trash** (`.trash/groups/`, `.trash/items/`, `.trash/merger/`) |
| assets dir | **workspace** |
| manifest | **plugin manifest** (`PluginManifest`); reports in `.extraction_metadata/` are **reports** |
| v1 | the removed RPy Extractor application only; the contract version is written "contract 1.1" |

## 0.2 Terms

### Structure

- **OS layer:** the adapter for the host OS (`viwo.os`, `LinuxOS`, `WindowsOS`): processes, tool
  location, filesystem rules, desktop shell, per-user homes, scan exclusions, process listing and
  memory dumps. The only place for OS-specific code (exceptions: contract README principle 3).
- **Engine plugin:** code that knows one game engine: detects it, declares slots and backends,
  and may propose analysis targets, sanitizer rules, a runtime agent, CLI commands and a UI module.
- **Profile:** a named set of plugins (`renpy`, `unity`, `unreal`, `godot`, `custom`, `mixed`).
- **Distro:** one OS layer plus one profile, written as an ini file (doc 9).
- **Core:** the engine- and OS-independent services: pipeline, wiring, jobs, workspace, curation,
  merger, sanitizer, analysis, capture, round trip, patch sets, mods, installer, indexes.
- **Arm:** one of the three groups of work: **static** (the game is not running), **dynamic**
  (it runs), **patching** (its content changes, in a copy). Every CLI command and UI view belongs
  to one arm or to **system**/**global**.

### Processing

- **Extraction run:** one request from a game folder to a filled workspace; it runs as a job.
- **Job:** a long-running unit of work with a kind, a state, an event stream and a result (doc 12).
- **Run record:** the JSON a finished extraction (`<job id>.json`) or capture
  (`capture-<stamp>.json`) leaves in `.extraction_metadata/runs/`, with the request, the effective
  ini, bindings and tool versions. A repack writes its report into the patched copy instead
  (`.viwo-patched/report.json`).
- **Feature:** a switch in `[startup] features` (`extraction`, `sorting`, `merger`, `capture`,
  `analysis`).
- **Stage:** one step of an extraction run, in a fixed order (doc 3.1).
- **Interface:** the contract one kind of work satisfies (`Unarchiver`, `Exporter`, `Analyzer`...).
- **Slot:** a named job with one interface, e.g. `unarchive.7z`; it has a main and an optional
  spare backend.
- **Backend:** an implementation that fills a slot (`sevenzip-cli`, `py7zr`). A backend may also
  serve no slot and only declare a dependency (`frida-trace`, `soundcard-loopback`).
- **Main / spare:** a slot's first choice and its fallback (doc 8.2). **Promoted:** the spare acts
  as main because the main is unavailable.
- **Fallback:** the record that the spare ran and why (`Outcome.fallback`).
- **Tool:** the third-party program or package a backend wraps (7-Zip, UnityPy).
- **Dependency:** a backend's declared need for a tool (`DependencySpec`).
- **Pinned tool:** a tool with a version, HTTPS URL, size and sha256 in `viwo/data/tools.json`,
  installed into `third_party/<id>/` (doc 10). **Worker tool:** a pinned pip package ViWo never
  imports and runs as its own process (`analysis.emulate`, `analysis.symbolic`).
- **Handoff:** "Continue in &lt;tool&gt;": ViWo prepares a target and opens a GUI tool as a tracked
  child (doc 8.3a).
- **Runtime agent:** a pinned tool that runs inside a patched copy of the game (UE4SS, BepInEx).

### Data

- **Game folder:** the folder the user points at. It is never written (doc 7).
- **Workspace marker:** `.viwo-workspace`; only folders that carry it may be cleared (doc 4.3).
- **Staging:** a private temporary folder per plugin; unpack and export write there first.
- **Scratch:** temporary files that are never collected.
- **Workspace:** the organized output folder the user curates.
- **Asset:** a file in the workspace, outside the reserved dot-folders.
- **Group:** the folder for one extension (`png/`, `noext/`).
- **Container:** a file that holds other data (archive, Unity bundle, `.pak`).
- **Inventory:** what a plugin expects to produce, as opposed to what was collected.

### Patching (doc 18)

- **Provenance map:** per workspace file, its container chain, member path, producing backend and
  original hash (`.extraction_metadata/provenance.jsonl`).
- **Edit set:** workspace files whose hash differs from the provenance hash, plus files added
  with a target path.
- **Mod strategy:** **override** (loose files or patch containers) or **rebuild** (a new
  container).
- **Patched copy:** a copy of the game folder marked by a `.viwo-patched/` folder; repack, patch
  sets, mods and runtime agents write only there.
- **Patch set:** a JSON list of byte patches (`*.patch.json`) addressed by offset, RVA or AOB
  pattern. **Mod:** a zip of a patched copy's changed files with `viwo-mod.json`.

### Curation

- **Sorting:** going through assets one at a time (mark kept, item trash, rename, undo).
- **Retain groups:** the bulk action that trashes every unselected group.
- **Sanitizer:** **rule** (inspects one thing), **recipe** (ordered rules), **finding** (one
  problem), **plan** (findings with proposed actions), **apply**, **journal** (for undo).
- **Merger:** **candidate** (files sharing a name pattern), **index** (the number in a name),
  **conflict** (two media types at one index), **timeline** (the ordered build input).

### Analysis (doc 6)

- **Analysis target:** a binary or bytecode worth analysing, proposed by a plugin.
- **Analyzer:** a backend in an `analysis.*` slot.

## 0.3 How the terms relate

```
Distro = OS layer + Profile -> Profile enables Engine plugins
Engine plugin --declares--> Slots --bound to--> main Backend [+ spare Backend]
Backend --wraps--> Tool --located by--> OS layer (ini [tools], third_party/, env, PATH, known dirs)
Extraction run = ordered Stages, each using Interfaces through Slots
game folder --unpack/export--> Staging --collect--> Workspace (Groups of Assets)
Workspace --curated by--> Sorting, Retain groups, Sanitizer, Merger
Workspace + provenance --repack--> Patched copy <-- Patch sets, Mods, Runtime agents
```

## 0.4 Metrics: what each count means

The `/api/extract` result keeps the v1 key names; their meaning is fixed here.

| Key | Counts |
|-----|--------|
| `archivesFound` | archives identified, nested ones included |
| `archivesExtracted` | archives unpacked successfully |
| `scannedFiles` | files walked in the source roots, including ones later filtered out |
| `copiedFiles` | files copied into the workspace (nothing is moved out of a game) |
| `copiedByExt` | `copiedFiles` per extension group |
| `movedFiles` | always 0: nothing is ever moved out of a game folder |
| `carvedFiles` | files the signature carver wrote |
| `inventoryItems` | items the plugins' `inventory()` listed (0 = no completeness claim) |
| `collectedFromInventory` | inventory items found after COLLECT |
| `plugins[].exported` | files the plugin's export wrote into staging |
| `plugins[].inventoryCount` | the plugin's inventory size (or what it found) |

A completeness claim holds only when a plugin's inventory counts the same kind of item as
COLLECT does; a plugin with an empty inventory makes none.
