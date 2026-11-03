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

## SQC-AN-05 (P1) No analyzer yet
1. 12 ANALYSIS on a Unity game: the IL2CPP and Assembly-CSharp rows show NO ANALYZER YET and
   ANALYZE is disabled; `viwo analyze --target gameassembly` answers `unavailable`.

| ID | Result | Version | Notes |
|----|--------|---------|-------|
| SQC-AN-01 | | | |
| SQC-AN-02 | | | |
| SQC-AN-03 | | | |
| SQC-AN-04 | | | |
| SQC-AN-05 | | | |
