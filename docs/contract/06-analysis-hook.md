# 6. Code analysis hook (Ghidra first)

**Status: contract hook only.** No analyzer ships in contract 1.0 or in the prototype (unrpyc included; it comes with the first analysis milestone). This doc
fixes the shape now so Ghidra can be added later without breaking changes.

## 6.1 Split: what vs how

```text
AnalysisTarget  (WHAT; from engine plugins via analysis_targets(probe))
  key            stable, filesystem-safe id
  kind           native_binary | dotnet_assembly | il2cpp | python_bytecode | gdscript_bytecode
  paths          primary file first, companions after (e.g. GameAssembly.dll + global-metadata.dat)
  owner, label, hints { arch, engine_version, ... }

CodeAnalyzer    (HOW; a backend in an analysis.* slot, doc 8)
  analyzer_id    "ghidra-headless", "ilspycmd", "il2cppdumper", "unrpyc"
  kinds          target kinds it accepts
  dependencies() -> [DependencySpec]
  analyze(target, ctx) -> AnalysisOutcome { ok, output_dir, artifacts[], error, duration_s }

AnalysisContext  output_dir, scratch, OS layer, progress, cancel, timeout_s, options
```

Which plugin proposes which targets:

| Plugin | Targets |
|--------|---------|
| unity | `GameAssembly.dll` + `global-metadata.dat` (il2cpp), `Managed/Assembly-CSharp.dll` (dotnet) |
| unreal | `<Game>-Win64-Shipping.exe` (native) |
| godot | game executable (native), `*.gdc` (gdscript_bytecode) |
| renpy | `*.rpyc`, `*.pyc` (python_bytecode) |
| generic | top-level executables (native) |

## 6.2 Ghidra specifics (for the future backend)

- **Invocation:** `analyzeHeadless <projectDir> <projectName> -import <bin> -postScript <ExportScript> <out> -scriptPath <dir> -deleteProject`.
- **OS differences:** on Windows the tool is `analyzeHeadless.bat`, run through `cmd /c` (the ToolLocation's `argv_prefix`); on Linux it's a shell script. Install directory comes from `GHIDRA_INSTALL_DIR` or the ini `[tools]` section.
- **Dependencies:** Ghidra itself (`executable`) and a JDK (`runtime`). The JDK version follows the pinned Ghidra release: Ghidra 12.2 needs **JDK 25** (doc 13.4).
- **Runtime:** analysis takes minutes to hours. It always runs as a background job with a timeout (`timeout_s`, set in the ini), with cancellation that kills the whole process tree (doc 1.1), and with `scratch` (the Ghidra project folder) deleted when the job ends.
- **IL2CPP chain:** `analysis.il2cpp` (Il2CppDumper or Cpp2IL) produces symbol scripts, which are then passed as an extra input to `analysis.native` (Ghidra). This is modeled as one job with two steps.

## 6.3 Rules (proposed)

- Analysis is **never** part of an extraction request. It's its own job type (`Stage.ANALYZE`), behind the `analysis` feature flag, which is **off by default** in every distro.
- Output goes only to `<workspace>/.analysis/<analyzer_id>/<target_key>/`, never into the per-extension asset layout.
- The first time analysis is enabled, the UI shows a one-time notice that the user is responsible for having the right to reverse engineer the binaries.

## 6.4 API (additive, later)

`GET /api/analysis/targets` → proposed targets with matching analyzers ·
`POST /api/analysis/run {targetKey, analyzerId, options}` → job id ·
`GET /api/analysis/jobs` → status, progress, artifacts · cancellation through
`POST /api/jobs/<id>/cancel` (doc 12.5).
