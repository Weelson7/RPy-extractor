# 6. Static analysis domain (code and data)

**Status (normative; rung A1 shipped in 1.3).** `analysis.native` (Ghidra headless, main) and the
`handoff.native` "Continue in Ghidra" handoff exist (`viwo/core/analysis/`,
`viwo/contracts/analysis.py`), with `EnginePlugin.analysis_targets(probe)`, the `analysis`
feature value (off by default), `viwo analyze`, `GET /api/analysis/targets`,
`POST /api/analysis/run` (job kind `analyze`), `POST /api/analysis/open` and the 12 ANALYSIS
view. The other slots of 6.2 are the normative shape of rungs A2-A4 (doc 16.2b). There is no
`Stage.ANALYZE`: analysis is its own job kind, never a stage of an extraction. The analyzer and
the handoff take the `ExtractionContext` (`staging` = the output folder): one context type per
arm rather than a second record (doc 6.1 `AnalysisContext` is implemented by it). Decompilers that only turn one file into a readable one (unrpyc for
Ren'Py `.rpyc`) ship as DECODE slots (`decode.rpyc`, doc 8) and run inside extraction; the analysis
domain is for whole-binary and whole-program work (Ghidra, IL2CPP, signature matching, version
diffing) that is never part of an extraction.

This is one of the three arms of the orchestrator (doc README): **static** (extraction + this
domain), **dynamic/runtime** (doc 11), **authoring** (doc 18). Everything here is a **static job**:
it reads a copy of a binary or asset and never launches, attaches to, or writes into the game. So
it carries the same low-risk profile as extraction, runs read-only, and needs no runtime opt-in.

## 6.0 Philosophy here

ViWo refuses nothing because of what a binary is or what the user intends (README "Philosophy",
D22). The analysis arm adds no gate. The one project-level rule is unchanged: **ViWo authors no
first-party borderline code.** It wires and pins community tools and runs them as the orchestrator
runs every other backend. Where a capability is borderline (recognising a protector, reconstructing
the imports of a dump the user took of their own process), ViWo supplies the orchestration and pins
a third-party tool under the disclaimer; the responsibility is the user's.

## 6.1 Split: what vs how

```text
AnalysisTarget  (WHAT; from engine plugins via analysis_targets(probe), or user-supplied)
  key            stable, filesystem-safe id
  kind           native_binary | dotnet_assembly | il2cpp | python_bytecode | gdscript_bytecode
                 | lua_bytecode | squirrel_bytecode | script_vm | memory_image | save_blob
  paths          primary file first, companions after (e.g. GameAssembly.dll + global-metadata.dat)
  owner, label, hints { arch, engine_version, base_address, middleware?, ... }

CodeAnalyzer    (HOW; a backend in an analysis.* slot, doc 8)
  analyzer_id    "ghidra-headless", "ilspycmd", "il2cppdumper", "die", "bindiff", "unicorn", ...
  kinds          target kinds it accepts
  dependencies() -> [DependencySpec]
  analyze(target, ctx) -> AnalysisOutcome { ok, output_dir, artifacts[], error, duration_s }

AnalysisContext  output_dir, scratch, OS layer, progress, cancel, timeout_s, options, prior_db?
```

`prior_db` lets an analyzer load an earlier project (annotations, types) so a re-run or a diff
builds on it rather than starting cold.

Which plugin proposes which targets:

| Plugin | Targets |
|--------|---------|
| unity | `GameAssembly.dll` + `global-metadata.dat` (il2cpp), `Managed/Assembly-CSharp.dll` (dotnet) |
| unreal | `<Game>-Win64-Shipping.exe` (native), `*.usmap` companions when present |
| godot | game executable (native), `*.gdc` (gdscript_bytecode) |
| renpy | `*.rpyc`, `*.pyc` (python_bytecode) |
| generic | top-level executables (native), loose `*.luac` / script-VM blobs, user-supplied memory images |

## 6.2 Slot families in this domain (doc 8)

All belong to the `analysis` family; the sub-name says the job. Every backend declares `license`
(GPL/AGPL ⇒ `isolation: subprocess`), `network` (default `none`, offline) and
`parses_untrusted_in_process`.

| Slot | What it produces | Main | Spare | temp.md |
|------|------------------|------|-------|---------|
| `analysis.native` | project with CFG, decompiled pseudo-C, xrefs, recovered types, strings, consts | `ghidra-headless` (Apache-2.0, JDK 25 for 12.2) | — | §1, §2, §3 |
| `analysis.dotnet` | decompiled C# / IL, type tree | `ilspycmd` (MIT, .NET) | dnSpyEx (GUI, manual) | §5 |
| `analysis.il2cpp` | symbol scripts + type headers fed into `analysis.native` | `cpp2il` (MIT) | `il2cppdumper` (≤ Unity 2022.2) | §5 |
| `analysis.python` | `.rpyc`/`.pyc` to source | `unrpyc` v2 (MIT) | `rpycdec` (isolated env) | §13 |
| `analysis.gdscript` | `.gdc` to GDScript | `gdre-tools --decompile` (MIT) | — | §13 |
| `analysis.script` | Lua/Squirrel/AngelScript bytecode to source; generic VM opcode tables | `unluac` (MIT) | community decompiler per VM | §13 |
| `analysis.signatures` | library/middleware/compiler names onto functions (FLIRT/FID style); middleware fingerprints (PhysX, Havok, Wwise, FMOD, Bink, Oodle, zlib, LZ4, Lua) | Ghidra FID | community signature sets | §4 |
| `analysis.diff` | name/type port between two builds; stable signatures for update resilience | `bindiff` (Apache-2.0) | `diaphora` (AGPL, subprocess) | §16 |
| `analysis.protector` | packer/protector identification so the user knows what they are looking at | `die` (Detect It Easy, MIT) | — | §14 |
| `analysis.emulate` | run one isolated routine (decoder, checksum, hash) outside the game: result.json (status returned/limit/import/fault, return value) + the dumped buffers | `unicorn-emulate` (Unicorn 2.1.4, GPL: a worker process) | — | §15 |
| `analysis.symbolic` | solve the inputs that make one routine reach an address: result.json + the solved buffers | `angr-symbolic` (angr 9.2.223, BSD; a worker process: its engine is Unicorn) | — | §15 |

**Worker tools (A4).** Unicorn and angr are pip pins ViWo never imports (`tools.json` `workers`):
installed into `third_party/<id>/`, run as `python -I viwo/data/workers/<script> --lib <folder>
<spec.json> <out>`. Options come as `viwo analyze ... --slot analysis.emulate --set start=... --set
args=...` (or the API's `options`): `start` (0x<va> | rva:0x<rva> | export:<name>), `args`
(int | hex:<bytes> | file:<path> | zeros:<n> | sym:<n>), `dump` (argN:<size>), `max_insns`;
`find` and `avoid` for symbolic runs. The image is mapped at its preferred base, calls into imports
stop the run and name the import (an isolated routine has no OS). angr 10's native claripy crashes
in its solver on Windows, hence the 9.2 pin.

`dnSpyEx`, `x64dbg` and other GUI-first tools are not headless backends. Instead each target offers
an **interactive handoff** (doc 8.3a): a "continue in Ghidra", "open in dnSpyEx" action that imports
the project (or builds a launch spec) and opens the tool as a tracked child subprocess. The headless
`analysis.native` run and the Ghidra-GUI handoff share one prepared project, so batch analysis and
hand work are the same artifact.

## 6.3 Capabilities carried by `analysis.native` (Ghidra)

The native analyzer is a driven Ghidra project, so its capabilities are Ghidra's, surfaced through
ViWo's job and artifact model rather than reimplemented:

- function boundaries, control-flow and call-graph recovery; switch/jump-table and tail-call
  handling; SIMD/AVX decoding (temp.md §2);
- struct/union/enum/class editors, auto-struct from access patterns, C++ RTTI (MSVC and Itanium),
  vtable and virtual-call resolution, multiple/virtual inheritance, STL container recognition,
  type propagation through the decompiler (temp.md §3);
- header import (C/C++ headers into the type DB) and **header export** out to a mod SDK (temp.md §3,
  §17);
- string search with encodings (ASCII, UTF-16, game-specific) and constant/magic-number search
  (CRC tables, crypto constants) (temp.md §2).

Annotations (renames, comments, bookmarks, types) live in the project DB under `.analysis/` and are
versioned with the workspace; sharing them is the knowledge-management story (temp.md §18): a Ghidra
Server or a committed project file, plus the per-game indexes (`indexes/`) that already carry
community data. Export artifacts: C/C++ headers, JSON symbol/offset maps, and a generated mod SDK
(temp.md §17), which the authoring arm (doc 18) consumes.

## 6.4 Ghidra specifics (for the backend)

- **Invocation:** `analyzeHeadless <projectDir> <projectName> -import <bin> -postScript <ExportScript> <out> -scriptPath <dir> -deleteProject`.
- **OS differences:** on Windows `analyzeHeadless.bat` through `cmd /c` (the ToolLocation's `argv_prefix`); on Linux a shell script. Install dir from `GHIDRA_INSTALL_DIR` or ini `[tools]`.
- **Dependencies:** Ghidra (`executable`) and a JDK (`runtime`); the JDK version follows the pinned Ghidra release (Ghidra 12.2 needs JDK 25, doc 13.4).
- **Runtime:** analysis takes minutes to hours; always a background job with `timeout_s`, tree-kill cancellation (doc 1.1), and the Ghidra project folder under `scratch` deleted when the job ends.
- **IL2CPP chain:** `analysis.il2cpp` (Cpp2IL or Il2CppDumper) produces symbol scripts, passed as an extra input to `analysis.native` (Ghidra). Modeled as one job with two steps.
- **Diff chain:** `analysis.diff` takes two native projects (old annotated, new raw) and writes a port report plus stable signatures that the authoring arm turns into update-resilient addresses.

## 6.5 Rules

- Analysis is **never** part of an extraction request. It is its own job type (`Stage.ANALYZE`),
  behind the `analysis` feature flag, **off by default** in every distro (a capability switch, not a
  moral gate: it keeps a heavy, slow, large-dependency arm out of the default install).
- Output goes only to `<workspace>/.analysis/<analyzer_id>/<target_key>/`, never into the
  per-extension asset layout.
- The first time analysis is enabled, the UI shows the one-time disclaimer notice (README "Legal and
  disclaimer"): the user is responsible for having the right to analyse the binaries. This is
  information and one opt-in, never a refusal.
- Input is a copy; the game folder and the original binary are never written. `memory_image` targets
  are files the user supplies (a dump they took of their own process); ViWo does not produce them in
  this arm (that is a dynamic job, doc 11).

## 6.6 API (additive, later)

`GET /api/analysis/targets` → proposed targets with matching analyzers ·
`POST /api/analysis/run {targetKey, analyzerId, options}` → job id ·
`GET /api/analysis/jobs` → status, progress, artifacts · cancellation through
`POST /api/jobs/<id>/cancel` (doc 12.5).
