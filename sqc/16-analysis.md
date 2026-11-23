# 16 Static analysis (ANALYSIS, `viwo analyze`, `viwo diff`)

Area code `AN`. Contract doc 6.1-6.6. Preconditions: `analysis` in `[startup] features` (SETTINGS >
FEATURES > STATIC ANALYSIS, apply), Ghidra and the JDK (`viwo install ghidra`, about 800 MB, or
SYSTEM > INSTALL), Detect It Easy (`viwo install die`), GDRE (`gdre`, installed with the Godot
tools). Nothing in the static arm runs the game; every analyzer reads a copy. Game:
`<repo>\Test-games\chocolate-doom\engine` (games.md; a MinGW 32-bit PE). Content search, the other
static analysis tool, is 21-search.

## SQC-AN-01 (P1) Targets listed per engine

Steps:
1. `viwo --json analyze <repo>\Test-games\chocolate-doom\engine --list`
2. On a Unity game (`Test-games\ultrakill-prelude`) and an Unreal one (`Test-games\voids-cave`): `--list`.
3. `viwo analyze C:\sqc\_ws\d\.runtime\dump\<pid>-<stamp> --list` (a folder `viwo dump` wrote, 19-dynamic).

Expected: 1: `chocolate-doom-setup-exe` and `chocolate-doom-exe`, kind `native_binary`, owner
`generic`, each with `handoffs [ghidra-gui / handoff.native]` and `extras [analysis.protector / die]`;
the DLLs are not targets. 2: `ultrakill-exe` (native_binary, generic), `gameassembly` (il2cpp, unity)
on IL2CPP or `assembly-csharp` (dotnet_assembly) on Mono, crash handlers absent; `shipping-exe`
(unreal) with the Shipping exe. 3: `<pid>-dmp`, kind `memory_image`, label `memory dump <pid>.dmp`.

## SQC-AN-02 (P1) Feature switch, and the other refusals by name

Steps:
1. `viwo --features extraction analyze <game> --target chocolate-doom-exe --workspace C:\sqc\_ws\an`
2. `viwo analyze <dump folder of AN-01 step 3> --target <pid>-dmp --workspace C:\sqc\_ws\d` (the workspace that holds the dump)

Expected: 1: `viwo: refused: static analysis is off`, hint `add analysis to [startup] features in
the ini (SETTINGS); you are responsible for having the right to analyse the binaries`, exit 3, no
workspace made. 2: `viwo: refused: the game folder (...) is inside the workspace (C:\sqc\_ws\d)`,
hint `choose a workspace that does not hold the game`, exit 3. No game, binary or intent check
blocks a run.

## SQC-AN-03 (P0) Ghidra headless writes the artifacts and nothing else

Steps:
1. `viwo analyze <game> --target chocolate-doom-exe --workspace C:\sqc\_ws\an`
2. Hash `chocolate-doom.exe` before and after.
3. Start another run and cancel it (Ctrl+C, or JOBS > CANCEL JOB for a run started in ANALYSIS).

Expected: 1: `Ghidra: importing and analysing chocolate-doom.exe`, Ghidra's `INFO` lines relayed,
`ViwoExport.java> ViWo export done: ...`, `REPORT: Import succeeded`; exit 0 after a few minutes;
`C:\sqc\_ws\an\.analysis\ghidra-headless\chocolate-doom-exe\` holds `functions.csv`, `decompiled.c`,
`strings.txt`, `symbols.tsv`, `record.json`; the project is `C:\sqc\_ws\an.ghidra\chocolate-doom-exe\viwo.gpr`
beside the workspace (Ghidra refuses dot folders). 2: unchanged. 3: the Ghidra process tree is gone
within seconds; the job `CANCELLED`.

## SQC-AN-04 (P1) Continue in Ghidra

Steps:
1. Before any run of a target: `viwo analyze <game> --target chocolate-doom-setup-exe --workspace C:\sqc\_ws\an-open --open`
2. ANALYSIS > LIST TARGETS > `CONTINUE IN GHIDRA` on the target analysed in AN-03.
3. Stop `viwo serve` (Ctrl+C).

Expected: 1: `viwo: failed: no Ghidra project yet: run the analysis first`, exit 1. 2: Ghidra opens
the `viwo` project with the binary imported, no user-agreement or tips dialog; the toast shows the
pid. 3: Ghidra closes with it (tracked child).

## SQC-AN-05 (P0) Managed code: Assembly-CSharp to C#, IL2CPP to stub assemblies

Preconditions: `viwo install ilspycmd cpp2il`.

Steps:
1. `viwo analyze Test-games\baldi-cr --workspace C:\sqc\_ws\an --target assembly-csharp`
2. On an IL2CPP game: `--list`, then `--target gameassembly`; then `viwo analyze <its cpp2il output folder> --list`.
3. With `third_party\cpp2il` removed: `--target gameassembly`.

Expected: 1: `ilspycmd: decompiling Assembly-CSharp.dll into a C# project`; `.analysis\ilspycmd\assembly-csharp\`
holds `Assembly-CSharp.csproj` and hundreds of `.cs` (646 for Baldi); note `N C# files (project
mode)`. 2: `gameassembly` (il2cpp) with three paths; `.analysis\cpp2il\gameassembly\` holds the stub
assemblies, note `metadata only, no method bodies`; the stub `Assembly-CSharp.dll` is then a
`dotnet_assembly` target. 3: `unavailable` with `viwo install cpp2il`; nothing refused.

## SQC-AN-06 (P1) Lua bytecode through unluac

Preconditions: `viwo install unluac`; a folder with compiled Lua chunks (`luac -o init.luac init.lua`).

Steps: `viwo analyze <folder> --list`; `--target lua-bytecode --workspace C:\sqc\_ws\an-lua`.

Expected: `lua-bytecode` (script_vm, generic, `N Lua bytecode chunk(s)`); `<name>.lua` per chunk under
`.analysis\unluac\lua-bytecode\`; the note counts `done/total chunks`.

## SQC-AN-07 (P1) Identify the binary first (Detect It Easy)

Steps:
1. `viwo analyze <game> --target chocolate-doom-exe --workspace C:\sqc\_ws\an --slot analysis.protector`
2. The same with `--slot analysis.script`.

Expected: 1: `.analysis\die\chocolate-doom-exe\` holds `identify.json`, `identify.txt` (`file: PE32
(Header)`, `Library: SDL(2)`, `Library: Secret Rabbit Code`, `Library: libpng`) and `record.json`
whose `notes` say `no packer or protector detected`; ANALYSIS shows a `DETECT IT EASY` button beside
`ANALYZE`. On a Themida/VMProtect/Denuvo-wrapped executable the notes name the protector. 2: `viwo:
unavailable: no analyzer slot for native_binary targets yet`, exit 1.

## SQC-AN-08 (P1) Ren'Py and GDScript bytecode

Steps:
1. `viwo analyze Test-games\DDLC-1.1.1-pc --workspace C:\sqc\_ws\an --target rpyc` (with unrpyc installed).
2. A `.gdc`: in a folder with `main.gd` (`extends Node`, `var health = 100`, `func _ready():` `print("hello", health)`):
   `third_party\gdre\gdre_tools.exe --headless --compile=main.gd --bytecode=4.3.0 --output=C:\sqc\gd`;
   then `viwo analyze C:\sqc\gd --list` and `viwo analyze C:\sqc\gd --workspace C:\sqc\_ws\an-gd --target gdscript`.

Expected: 1: backend `unrpyc-analyze`, `.analysis\unrpyc-analyze\rpyc\` holds 44 `.rpy`, note `44/44
scripts`. 2: GDRE prints `Compiled main.gd to C:/sqc/gd/main.gdc`; target `gdscript`
(`gdscript_bytecode`, owner `godot`); `GDRE Tools: decompiling 1 .gdc file(s) as 4.3.0`, backend
`gdre-decompile`, note `1/1 scripts, bytecode 4.3.0`; `.analysis\gdre-decompile\gdscript\main.gd`
equals the source.

## SQC-AN-09 (P1) Version diff of two analyses

Steps:
1. Run SQC-AN-03 for both targets of the game (`chocolate-doom-setup-exe` as the "old").
2. `viwo diff C:\sqc\_ws\an\.analysis\ghidra-headless\chocolate-doom-setup-exe C:\sqc\_ws\an\.analysis\ghidra-headless\chocolate-doom-exe`
3. `viwo diff C:\sqc\se C:\sqc\gd`

Expected: 2: `summary` counts of `same`, `changed`, `added`, `removed` (a kind with none left out);
`diff.json` and `diff.txt` under `.analysis\diff\chocolate-doom-setup-exe--chocolate-doom-exe\`;
`diff.txt` starts with the counts and lists every function that is not `same` (`removed 00402d60 ->
- FUN_00402d60`). Two versions of one binary give mostly `same` and a few `changed`. 3: `viwo:
not_found: no functions.csv in C:\sqc\se`, hint `run the analysis first`, exit 1.

## SQC-AN-10 (P1) Emulate and solve an isolated routine

Preconditions: `viwo install unicorn` (and `angr` for step 3); a small PE with a known routine (an
XOR decoder; its address from `functions.csv`).

Steps:
1. `viwo analyze <game> --workspace W --target <key> --slot analysis.emulate --set start=0x<va> --set args=hex:<bytes>,<len> --set dump=arg0:<len>`
2. A routine that calls an import.
3. `--slot analysis.symbolic --set start=0x<va> --set args=sym:4 --set find=0x<success va>`
4. Without `start=`.

Expected: 1: `.analysis\unicorn-emulate\<key>\result.json` with `status: returned`, the return value,
the dumped buffer holding the decoded bytes; no first-run dialog; Unicorn never imported into
ViWo's process (the worker is its own process). 2: `status: import` and the import's name. 3:
`.analysis\angr-symbolic\<key>\result.json` with the solved 4-byte input. 4: `invalid_request: give
the routine's address: start=0x...`.

## SQC-AN-11 (P1) ANALYSIS view and API

Preconditions: `viwo serve`.

Steps: STATIC arm > ANALYSIS with no game listed; `GET /api/analysis/targets?gamePath=C:\sqc\gd`.

Expected: the action bar holds `ANALYZE`, disabled, with its reason beside it; the API answers
`{targets: [gdscript], enabled: true, problems}`.

## Results

| ID | Result | Version | Notes | Tester | Date |
|----|--------|---------|-------|--------|------|
| SQC-AN-01 | PASS (steps 1, 3) / NOT RUN (2) | 1.36.0+search+apk (unreleased) | step 2 needs Unity/Unreal games (not installed here) | agent | 2026-11-23 |
| SQC-AN-02 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-AN-03 | PASS (steps 1-2) / NOT RUN (3) | 1.36.0+search+apk (unreleased) | Ghidra 12.2 on JDK 25 of the pinned set: 228 s for chocolate-doom.exe, 142 s for the setup exe; exe sha256 `94f627bd...` before and after. Cancel not run | agent | 2026-11-23 |
| SQC-AN-04 | PASS (step 1) / NOT RUN (2-3) | 1.36.0+search+apk (unreleased) | the GUI half needs eyes | agent | 2026-11-23 |
| SQC-AN-05 | NOT RUN | 1.36.0+search+apk (unreleased) | needs a Unity game (Mono and IL2CPP); passed at 1.4.0 | agent | 2026-11-23 |
| SQC-AN-06 | NOT RUN | 1.36.0+search+apk (unreleased) | unluac not installed in this home and no Lua chunk at hand | agent | 2026-11-23 |
| SQC-AN-07 | PASS | 1.36.0+search+apk (unreleased) | DIE 3.21 names no compiler for this MinGW build | agent | 2026-11-23 |
| SQC-AN-08 | PASS (step 2) / NOT RUN (1) | 1.36.0+search+apk (unreleased) | GDRE 4.3.0 round trip identical; DDLC not installed, unrpyc not installed | agent | 2026-11-23 |
| SQC-AN-09 | PASS | 1.36.0+search+apk (unreleased) | two different binaries: same 388, added 955, removed 165 (`changed` 0, left out of the summary) | agent | 2026-11-23 |
| SQC-AN-10 | NOT RUN | 1.36.0+search+apk (unreleased) | the Unicorn/angr workers are only found in a home's `third_party\<id>\` (no ini or env override for a worker), not installed here | agent | 2026-11-23 |
| SQC-AN-11 | PASS | 1.36.0+search+apk (unreleased) | the bar by `tests/test_ui_smoke.py`; the API on a live server | agent | 2026-11-23 |
