# 6. Static analysis arm

Analysis of a game's code and bytecode: what the plugins propose, which analyzer runs, where the
output lands (`viwo/contracts/analysis.py`, `viwo/core/analysis/`). Every analyzer reads a
**copy** of its input and never launches, attaches to or writes into the game. Analysis is its
own job kind (`analyze`), never a stage of an extraction. A decompiler that turns one file into
one readable file inside an extraction is a DECODE slot instead (`decode.rpyc`, doc 8).

Switch: `analysis` in `[startup] features` (off by default; a capability switch because the
tools are large, not a gate). Off, a run is refused with the hint to enable it; listing targets
works either way. Entry points: `viwo analyze`, `viwo diff`, `GET /api/analysis/targets`,
`POST /api/analysis/run|open|diff`, ANALYSIS.

## 6.1 Targets and analyzers

```text
AnalysisTarget  (WHAT; from EnginePlugin.analysis_targets(probe))
  key     stable, filesystem-safe (target_key(path))
  kind    native_binary | dotnet_assembly | il2cpp | python_bytecode | gdscript_bytecode
          | script_vm | memory_image
  paths   primary file first, companions after
  owner   plugin id or "user";  label;  hints { engine_version, ... }

Analyzer (HOW; a backend in an analysis.* slot)
  kinds                 the target kinds it accepts
  analyze(target, ctx) -> Outcome      ctx: ExtractionContext, staging = the output folder
```

The kind picks the slot: `analysis.<first word of the kind>` (`native_binary` ->
`analysis.native`). A target also lists `extras`: the other bound analyzers that accept its
kind (`viwo analyze --slot analysis.protector`, one button per extra in ANALYSIS).

| Plugin | Targets |
|--------|---------|
| generic | executables up to two folders down (`native_binary`); Lua bytecode chunks (`\x1bLua`, `script_vm`) |
| unity | `GameAssembly.dll` + `global-metadata.dat` + the player exe (`il2cpp`); `Assembly-CSharp.dll` (`dotnet_assembly`) |
| unreal | `*-Shipping.exe` with any `.usmap` (`native_binary`) |
| godot | every `.gdc` (`gdscript_bytecode`), engine version from the executable |
| renpy | every `.rpyc` (`python_bytecode`) |

The output folder of one run is itself a game folder for `--list`: Cpp2IL's stub
`Assembly-CSharp.dll` becomes a `dotnet_assembly` target, so IL2CPP games get C# stubs in two runs.

## 6.2 Analysis slots

Every backend declares `license` (GPL/AGPL => `isolation = "subprocess"`), `network` and
`parses_untrusted_in_process`.

| Slot | Owner | Backend (tool) | Output |
|------|-------|----------------|--------|
| `analysis.native` | core | `ghidra-headless` (Ghidra 12.2 on Temurin JDK 25) | `functions.csv` (address, name, size, mnemonic fingerprint), `decompiled.c`, `strings.txt`, `symbols.tsv`; Ghidra's FID signatures run inside the analysis |
| `analysis.dotnet` | core | `ilspycmd` (ilspycmd 11.2 on the pinned .NET) | a C# project |
| `analysis.il2cpp` | core | `cpp2il` (Cpp2IL 2022.1 pre-release 21, Windows) | stub assemblies (`dummydll`) |
| `analysis.script` | core | `unluac` (on the pinned JDK) | Lua source |
| `analysis.python` | renpy | `unrpyc-analyze` (unrpyc 2.0.4) | `.rpy` source |
| `analysis.gdscript` | godot | `gdre-decompile` (GDRE Tools; bytecode revision from the option, the executable or the `.gdc` header) | GDScript source |
| `analysis.protector` | core | `die` (Detect It Easy 3.21 `diec`; accepts native, dotnet, il2cpp) | `identify.json`, `identify.txt`; packers and protectors named in the notes |
| `analysis.emulate` | core | `unicorn-emulate` (Unicorn 2.1.4, worker) | `result.json` (status returned/limit/import/fault, return value) and dumped buffers |
| `analysis.symbolic` | core | `angr-symbolic` (angr 9.2.223, worker, on demand) | `result.json` and solved buffers |

Every run also writes `record.json` beside its output: target, backend used, artifacts, notes,
fallback, finish time and the run-record context (effective ini, bindings, tool versions).

**Worker tools (A4).** Unicorn and angr are pip pins ViWo never imports (`tools.json` `workers`,
`viwo/core/workers.py`): installed into a fresh `third_party/<id>/` and swapped in, run as
`python -I viwo/data/workers/<script>`. Options (`viwo analyze --slot analysis.emulate --set
KEY=VALUE`, or the API's `options`): `start` (`0x<va>` | `rva:0x<rva>` | `export:<name>`), `args`
(`<int>` | `hex:<bytes>` | `file:<path>` | `zeros:<n>` | `sym:<n>`), `dump` (`argN:<size>`),
`max_insns` (default 1,000,000); `find` and `avoid` for symbolic runs. The image is mapped at its
preferred base; a call into an import stops the run and names the import. A worker that crashes
still reports a result.

**Version diff (A3).** `viwo diff OLD NEW` / `POST /api/analysis/diff` compares two
`.analysis/ghidra-headless/<key>/` folders of one binary from two game versions: unique names
pair first, then unique mnemonic fingerprints (unnamed and overloaded functions, across
relocation); each pair is `same` or `changed`, the rest `added` or `removed`. Output
`diff.json` and `diff.txt` in `.analysis/diff/<old>--<new>/` (the CLI derives it from NEW's
folder unless `--out` is given; the API uses the active workspace).
BinDiff has no pinnable release; the diff is ViWo's own.

## 6.3 Handoffs from a target (doc 8.3a)

A target offers every bound static handoff (`handoff.*`) that accepts its kind, the kind's own
first: `handoff.native` (Continue in Ghidra: opens the project of the headless run).
`viwo analyze --open [HANDOFF]`, `POST /api/analysis/open`. Nothing in the static arm runs the
game: x64dbg and Cheat Engine work on the game itself and are the dynamic arm's attach tools
(`attach.*`, doc 11.2), offered on the same targets from RUNTIME and `viwo attach`.

## 6.4 Ghidra specifics

- Invocation: `analyzeHeadless <projectDir> <name> -import <copy> -postScript ViwoExport.java
  <out> -scriptPath viwo/data/ghidra`; Windows batch files run through `cmd /c call`.
- The project lives beside the workspace in `<workspace>.ghidra/<key>/` (Ghidra refuses project
  paths containing a dot folder); the GUI handoff opens it by starting the JVM directly, so the
  window is a tracked child.
- Ghidra is pinned `on_demand`: installed by `viwo install ghidra`, SYSTEM, or by itself when
  the `analysis` feature is turned on (the main backends' missing tools install as one
  background job, `core/preflight.py` `feature_tools`), never by the startup preflight.
  First-run prompts (user agreement, tips) are pre-answered without overwriting a user's own
  choice; the x64dbg and Cheat Engine attach tools (doc 11.2) pre-answer theirs only in ViWo's
  own copy under `third_party/`, and say so when the tool is the user's own install.
- Timeout: `viwo analyze --timeout` (default 4 h); cancel kills the tree.

## 6.5 Rules

- Output goes only to `<workspace>/.analysis/<backend id>/<target key>/`, emptied before a rerun,
  never into the extension groups.
- The input is a copy: the game folder and the original binary are never written.
- `memory_image` targets are files the user supplies; no plugin proposes one and no analyzer
  accepts the kind yet.
- The UI states once that the user is responsible for having the right to analyse the binaries
  (information, never a refusal).

## 6.6 API

`GET /api/analysis/targets?gamePath` -> `{targets (with extras and handoffs), enabled, problems}` ·
`POST /api/analysis/run {gamePath, targetKey, slot?, options?}` -> job of kind `analyze` under the
workspace lock · `POST /api/analysis/open {gamePath, targetKey, handoff?}` · `POST
/api/analysis/diff {old, new}` (synchronous). Cancellation through `POST /api/jobs/<id>/cancel`.
