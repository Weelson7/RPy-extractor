# 16 Static analysis (12 ANALYSIS, `viwo analyze`)

Preconditions: a workspace, a game folder (any of `Test-games/`), `analysis` in
`[startup] features` (11 SETTINGS > FEATURES > STATIC ANALYSIS, apply), Ghidra and the JDK
installed (`viwo install ghidra`, about 800 MB, or 05 SYSTEM > INSTALL on `ghidra`).

## SQC-AN-01 (P1) Targets listed per engine
1. `viwo analyze Test-games/ultrakill-prelude --list`.
2. Expected: `ultrakill-exe` (native_binary, generic), `gameassembly` (il2cpp, unity) when the
   game is IL2CPP or `assembly-csharp` (dotnet_assembly) when Mono; crash handlers absent.
3. `viwo analyze Test-games/voids-cave --list`: `shipping-exe` (unreal) with the Shipping exe.

## SQC-AN-02 (P1) Feature switch and refusal-free messages
1. With `analysis` absent from features: `viwo analyze <game> --target <key> --workspace W`.
2. Expected: exit 3, `refused: static analysis is off`, hint names the ini key and the
   responsibility notice. No other condition blocks a run (no game, binary or intent check).

## SQC-AN-03 (P0) Headless run writes the artifacts and nothing else
1. `viwo analyze Test-games/ultrakill-prelude --target ultrakill-exe --workspace <ws>`.
2. Expected: progress lines prefixed INFO/ERROR from Ghidra; on success
   `<ws>/.analysis/ghidra-headless/ultrakill-exe/` holds `functions.csv`, `decompiled.c`,
   `strings.txt`, `symbols.tsv`, `record.json` (context with tool versions); the Ghidra project is
   `<ws>.ghidra/ultrakill-exe/viwo.gpr` beside the workspace (Ghidra refuses dot folders).
3. Game folder hashes unchanged (`tools/integration_games.py` style check or `viwo diag`).
4. Cancel mid-run (Ctrl+C or 04 JOBS > CANCEL): the Ghidra process tree is gone within seconds.

## SQC-AN-04 (P1) Continue in Ghidra
1. 12 ANALYSIS > LIST TARGETS > CONTINUE IN GHIDRA on the analysed target.
2. Expected: Ghidra opens the `viwo` project with the binary imported; the toast shows the pid.
3. Stop `viwo serve` (Ctrl+C): Ghidra closes with it (tracked child).
4. Before any run: the button answers "no Ghidra project yet: run the analysis first".

## SQC-AN-05 (P0) Managed code: Assembly-CSharp to C#, IL2CPP to stub assemblies
Preconditions: `viwo install ilspycmd cpp2il` (25 MB).
1. `viwo analyze Test-games\baldi-cr --workspace C:\sqc\_ws\an --target assembly-csharp`
2. Expected: `ilspycmd: decompiling Assembly-CSharp.dll into a C# project`, the record names
   `ilspycmd`, `.analysis\ilspycmd\assembly-csharp\` holds `Assembly-CSharp.csproj` and
   hundreds of `.cs` files (646 for Baldi), the note says `N C# files (project mode)`.
3. On an IL2CPP game (a Unity folder with `GameAssembly.dll` and
   `<Game>_Data\il2cpp_data\Metadata\global-metadata.dat`): `--list` shows `gameassembly`
   (il2cpp) with three paths (binary, metadata, the executable);
   `--target gameassembly` runs Cpp2IL and `.analysis\cpp2il\gameassembly\` holds the stub
   assemblies (`Assembly-CSharp.dll` among them); the note says `metadata only, no method bodies`.
4. `viwo analyze <that cpp2il folder> --list` proposes the stub `Assembly-CSharp.dll` as a
   dotnet target: the chain IL2CPP -> stubs -> C# is two runs.
5. With `third_party\cpp2il` removed, `--target gameassembly` answers `unavailable` with the
   install hint (`viwo install cpp2il`); nothing is refused.

## SQC-AN-06 (P1) Lua bytecode through unluac
Preconditions: `viwo install unluac` (runs on the pinned JDK); a folder with compiled Lua
chunks (`\x1bLua` header; `luac -o init.luac init.lua` makes one).
1. `viwo analyze <folder> --list`: `lua-bytecode` (script_vm, owner generic, "N Lua bytecode
   chunk(s)"); `--target lua-bytecode` writes `<name>.lua` per chunk under
   `.analysis\unluac\lua-bytecode\`; the note counts `done/total chunks`.

## SQC-AN-07 (P1) Identify the binary before decompiling it (Detect It Easy)
Preconditions: `viwo install die` (25 MB).
1. `viwo analyze Test-games\ultrakill-prelude --list`: the `ultrakill-exe` row lists
   `extras: [analysis.protector / die]`; 12 ANALYSIS shows a DETECT IT EASY button next to ANALYZE.
2. `viwo analyze Test-games\ultrakill-prelude --workspace C:\sqc\_ws\an --target ultrakill-exe --slot analysis.protector`
3. Expected: `.analysis\die\ultrakill-exe\identify.txt` lists the linker, compiler (MSVC),
   `Library: Unity Engine` and the tool; the notes say `no packer or protector detected`; on a
   Themida/VMProtect/Denuvo-wrapped executable the notes name the protector and the run record
   keeps it (`notes`). `--slot analysis.script` on the same target answers `unavailable`.

## SQC-AN-08 (P1) Ren'Py and GDScript bytecode
1. `viwo analyze Test-games\DDLC-1.1.1-pc --workspace C:\sqc\_ws\an --target rpyc`: backend
   `unrpyc-analyze`, `.analysis\unrpyc-analyze\rpyc\` holds 44 `.rpy`, the note `44/44 scripts`.
2. Make a `.gdc`: `third_party\gdre\gdre_tools.exe --headless --compile=main.gd --bytecode=4.3.0
   --output=C:\sqc\gd`, then `viwo analyze C:\sqc\gd --workspace C:\sqc\_ws\an --target gdscript`:
   backend `gdre-decompile`, `main.gd` equals the source, the note names `bytecode 4.3.0`.

## SQC-AN-09 (P1) Version diff of two analyses
1. Run SQC-AN-03 on the same binary from two game versions (for example the
   `UnityCrashHandler64.exe` of two Unity games) into `<ws>/.analysis/ghidra-headless/<old>` and
   `<new>`.
2. `viwo diff <ws>\.analysis\ghidra-headless\<old> <ws>\.analysis\ghidra-headless\<new>`
3. Expected: a summary with `same`, `changed`, `added`, `removed` counts; `diff.json` and
   `diff.txt` under `<ws>\.analysis\diff\<old>--<new>\`; `diff.txt` lists every function that is
   not `same`. A folder without `functions.csv` answers `not_found` with `run the analysis first`.

## SQC-AN-10 (P1) Emulate and solve an isolated routine
Preconditions: `viwo install unicorn` (and `viwo install angr` for step 3); a small PE or ELF
with a known routine (an XOR decoder; its address from `functions.csv`).
1. `viwo analyze <game> --workspace W --target <key> --slot analysis.emulate --set start=0x<va>
   --set args=hex:<bytes>,<len> --set dump=arg0:<len>`
2. Expected: `.analysis\unicorn-emulate\<key>\result.json` with `status` `returned`, the return
   value, and the dumped buffer holding the decoded bytes; a call into an import stops the run
   with `status` `import` and the import's name; no first-run dialog, no Python import of
   Unicorn in the ViWo process (the worker runs as its own process).
3. `--slot analysis.symbolic --set start=0x<va> --set args=sym:4 --set find=0x<success va>`:
   `.analysis\angr-symbolic\<key>\result.json` with the solved 4-byte input.
4. Without `start=`: `invalid_request: give the routine's address: start=0x...`.

| ID | Result | Version | Notes |
|----|--------|---------|-------|
| SQC-AN-01 | | | |
| SQC-AN-02 | | | |
| SQC-AN-03 | | | |
| SQC-AN-04 | | | |
| SQC-AN-05 | PASS | 1.4.0 | agent, 2026-11-03: Baldi 646 .cs in 3 s; library IL2CPP title 80 stubs in 8 s; chain listed |
| SQC-AN-06 | | | fake-tool test only (no Lua-bytecode game in the library) |
| SQC-AN-08 | PASS | 1.4.4 | agent, 2026-11-03: DDLC 44/44; GDRE 4.3 round trip |
| SQC-AN-07 | PASS | 1.4.1 | agent, 2026-11-03: ULTRAKILL.exe (MSVC 2017, Unity Engine, no protector) and the Unreal shipping exe (Authenticode) |
| SQC-AN-09 | | | |
| SQC-AN-10 | | | |
