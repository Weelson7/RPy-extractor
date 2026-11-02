# 0. Glossary and semantic model (draft, read this first)

The other documents only work if every word in them means one thing. While
reading v1, I found many words that carry two or three meanings, plus some
metrics whose names don't match what they count. If we build interfaces on
those concepts as they are, we lock the confusion in. This doc proposes one
meaning per term. **Every term below is open for discussion**; the ones I'm
least sure about are marked ❓.

## 0.1 The overloaded words in v1

| Word in v1 | Meanings found in the code | Proposal |
|------------|---------------------------|----------|
| **engine** | (a) the game engine (Unity, Ren'Py…); (b) in your last message, a processing unit of the pipeline | (a) → **game engine**; (b) → **backend** (0.2). The word "engine" is never used alone. ❓ |
| **extractor / extraction type** | `RenPyExtractor`, `extractionType`, `extractorType`: code that knows a game engine | → **engine plugin** |
| **extract** | (a) the whole Step 1 request; (b) unpacking one archive (`extract_single_archive`); (c) decoding engine assets (UnityPy) | (a) **extraction run**; (b) **unpack**; (c) **export** |
| **phase / slice / step** | core `[PHASE 0-3]`, Unity `SLICE 1-6`, UI `step1-3` | pipeline → **stage**; UI accordion → **step** (UI only) |
| **detect** | (a) engine detection; (b) `detect_extensions` / `/api/detected-extensions` (listing extensions) | (a) **detect**; (b) **scan** (extensions) |
| **keep** | (a) Step 3 "keep selected" = trash every *other* extension folder; (b) sorting "keep" = a no-op that only records history for undo | (a) **retain groups**; (b) **mark kept** ❓ |
| **trash** | (a) whole extension folder → `.trash/<ext>_N`; (b) single file from sorting → `.trash/<rel path>`. Same folder, two layouts, and `list_trash` counts both | **group trash** and **item trash**, as two explicit layouts under `.trash/` ❓ (or two separate folders) |
| **assets dir** | `assets_dir()`, `output_dir`, `assetPath`, `workingDir` (merger), `step2Path` (UI), `outputDir` (config, but only its *name* is used) | → **workspace** |
| **session** | `SESSIONS` / `PersistentSessions` holds in-memory UI state, logs and undo history. Nothing is actually saved, despite the name | → **UI session** (memory only). Anything that has to survive a restart gets its own explicit store |
| **generic** | (a) the fallback plugin id; (b) "no engine detected" | (a) plugin id `generic`; (b) detection outcome **undetected** |
| **discovered** | Unity "discovered assets" are actually *containers* (one record per container file) | → **inventory** (expected items) vs **containers** (files scanned) |
| **copied** | `copiedFiles` / `copiedByExt` count files that were **moved** | v1 key names stay (compatibility); the meaning is documented as "moved into the workspace" |

## 0.2 Proposed terms

### Structure

- **Kernel** ❓: the adapter for the host operating system (Linux or Windows). It is the only place for OS-specific behavior. *Naming concern:* "kernel" already means the OS kernel, so "host" or "platform" might be clearer. I've kept your word for now.
- **Engine plugin:** code that knows one game engine. It detects the engine, declares slots and backends, and can export, verify, and propose sanitizer rules and analysis targets.
- **Profile:** a named set of engine plugins plus features (renpy, unity, unreal, godot, custom, mixed).
- **Distro:** one kernel plus one profile, declared in an `.ini` file (doc 9).
- **Core:** the services that don't depend on any game engine or OS: the pipeline runner, workspace, sorting, merger, sanitizer runner, registries and logging.

### Processing

- **Extraction run:** one request from a game folder to a filled workspace.
- **Stage:** one step of the run (prepare, probe, detect, …). The order is fixed (doc 3).
- **Interface:** the contract one kind of work must satisfy (Unarchiver, Exporter, MediaProbe, …).
- **Slot:** a named job inside a stage, with one interface. For example, `unarchive.7z` means "unpack .7z files with the Unarchiver interface".
- **Backend:** an implementation that fills a slot (`sevenzip-cli`, `py7zr`). This is what your message called a pipeline "engine".
- **Main / spare:** the roles a backend can have in a slot. Main is tried first; spare is the fallback (doc 8).
- **Tool:** the third-party program or library a backend wraps (7-Zip, UnityPy). One tool can back several slots; for example, 7-Zip serves zip, tar, rar and 7z.
- **Dependency:** a backend's declared need for a tool or runtime (for example Java).
- **Vendored tool:** a tool that lives in the repository as a sparse submodule (doc 10).

### Data

- **Game folder:** the folder the user points at. It is never modified.
- **Staging:** a private temporary folder for each plugin. Unpack and export results go here first.
- **Scratch:** temporary files that are never collected into the workspace.
- **Workspace:** the organized output folder that the user curates.
- **Asset:** a file in the workspace, outside the reserved dot-folders.
- **Group:** the folder for one extension (`png/`, `noext/`). v1 calls this an "ext folder".
- **Container:** a file that holds other data (an archive, a Unity bundle, a `.pak`).
- **Inventory:** what a plugin expects to find (expected items), as opposed to what was actually **collected**.
- **Manifest:** a machine-readable report in `.extraction_metadata/`.

### Curation

- **Sorting:** going through assets one at a time (mark kept, item trash, rename, undo).
- **Retain groups:** the Step 3 bulk action, which moves every unselected group to trash.
- **Sanitizer terms:** a **rule** inspects and maybe fixes one thing; a **recipe** is an ordered list of rules; a **finding** is one problem a rule found; a **plan** is the findings plus proposed actions; **apply** executes the accepted actions; the **journal** records an apply for undo.
- **Merger terms:** a **candidate** is a set of files that share a name pattern; an **index** is the number in a file name; a **conflict** is two media types with the same index; the **timeline** is the ordered build input.

### Analysis

- **Analysis target:** a binary or bytecode worth decompiling, proposed by a plugin.
- **Analyzer:** a backend in an `analysis.*` slot (Ghidra, ILSpy, …).

## 0.3 How the terms relate

```
Distro ──= Kernel + Profile ──▶ Profile enables Engine plugins
Engine plugin ──declares──▶ Slots ──bound to──▶ main Backend [+ spare Backend]
Backend ──wraps──▶ Tool ──located by──▶ Kernel (or vendored submodule)
Extraction run ──= ordered Stages ──each uses──▶ Interfaces via Slots
Stages: game folder ─unpack/export─▶ Staging ─collect─▶ Workspace (Groups of Assets)
Workspace ──curated by──▶ Sorting · Retain groups · Sanitizer · Merger
```

## 0.4 Metrics: what they actually count

Interfaces will pass these numbers around, so their meaning has to be pinned
down. These are v1's numbers as they behave today:

| v1 key | What the code actually counts | Concern |
|--------|-------------------------------|---------|
| `archivesFound` | archives found, including nested ones | fine |
| `archivesExtracted` | archives unpacked successfully | fine |
| `scannedFiles` | files walked in the source roots | it includes files that were later filtered out, which is fine but should be documented |
| `copiedFiles` | files moved into the workspace | "copied" is the wrong word |
| `discoveredCount` (Unity) | number of **container files** | it is compared with `extractedCount` (number of **files**), so the ratio and the "quality gate" compare two different things |
| `extractedCount` (Unity) | core-moved files plus Unity exports | the Unity exports get deleted by PREPARE (finding F1), so the number overcounts |
| `unresolvedByReason` (Unity) | hard-coded empty lists | carries no information |
| `qualityGatePass` (Unity) | based on the ratio above | meaningless until inventory counts real items |

**Proposal:** keep the v1 keys for UI compatibility, document their real
meaning, and add correctly named metrics alongside them: `movedFiles`,
`inventoryItems`, `collectedFromInventory`. Any "completeness" claim only
holds when a plugin's inventory counts the same kind of item as collection
does. Better data can't be produced from wrong counts, so this matters more
than any interface.

## 0.5 Questions for you

1. Is "kernel" the word you want, or would "host" or "platform" read better to contributors?
2. "Backend / main / spare": does that match what you meant by "a main engine and a spare one"?
3. Should the two trash mechanisms stay in one `.trash/` folder (as in v1), or be split into separate folders?
4. Which v1 metric names can we rename in the UI now, and which must stay frozen?
