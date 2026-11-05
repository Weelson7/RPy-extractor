# 19 Dynamic arm: debugger, memory, trace (`viwo attach`, `viwo dump`, `viwo trace`)

Area code `DYN`. Preconditions: `capture` in `[startup] features` (or `--features
extraction,capture`), `viwo install x64dbg cheatengine frida-tools`. Nothing in this file may
show a first-run dialog: a dialog is a FAIL (owner's rule).

## SQC-DYN-01 (P0) Continue in x64dbg, on the game's own process
1. Game not running: `viwo --features extraction,capture attach Test-games\ultrakill-prelude
   --workspace C:\sqc\_ws\d --target ultrakill-exe --confirm`
2. Expected: x64dbg opens with `ULTRAKILL.exe - PID ... - Module: ntdll.dll` in its title, paused at
   the system breakpoint, the path in its title the game folder's own `ULTRAKILL.exe` (no
   `.debug-copy`); no release-notes window (also on a fresh `third_party\x64dbg`).
3. Start the game yourself, then the same command: x64dbg attaches to the running process
   (`attached` in the result is its pid); a byte patched in x64dbg's memory view changes the
   running game.
4. Without `capture` (`--features extraction,analysis`): `refused`; ANALYSIS offers only
   Continue in Ghidra.

## SQC-DYN-02 (P0) Continue in Cheat Engine
1. The same with `--tool cheatengine-gui`.
2. Expected: Cheat Engine opens `.runtime\cheatengine-gui\ultrakill-exe\ULTRAKILL.CT` with no
   CEShare setup and no "execute this table's Lua" question; start the game: Cheat Engine attaches
   to it within a second (its process label shows ULTRAKILL.exe).

## SQC-DYN-03 (P1) Memory dump and API trace
1. Start the game windowed, then `viwo --features extraction,capture dump --name ULTRAKILL.exe
   --workspace C:\sqc\_ws\d`: `.runtime\dump\<pid>-<time>\<pid>.dmp`, hundreds of MB.
2. `viwo --features extraction,capture trace --name ULTRAKILL.exe --workspace C:\sqc\_ws\d
   --functions CreateFileW,ReadFile --seconds 10`: `trace.log` with thousands of lines.
3. Without the feature: `refused: the dynamic arm is off`.

## SQC-DYN-04 (P0) Unreal runtime agent: mappings and object dump
1. `viwo install ue4ss`, then `viwo --features extraction,capture agent Test-games\voids-cave
   --exe "Test-games\voids-cave\Void's Cave.exe" --workspace C:\sqc\_ws\ag --timeout 150`
2. Expected: the game opens windowed (640x360) with no UE4SS console, closes by itself after
   about 25 s; `finished: true`; `.runtime\agent\ue4ss-agent\` holds `Mappings.usmap` (about
   1.3 MB) and `UE4SS_ObjectDump.txt`; `C:\sqc\_ws\ag.agent-copy` is the patched copy; the game
   folder hashes are unchanged.

## SQC-DYN-05 (P1) Unity IL2CPP runtime agent
1. `viwo install bepinex`; on an IL2CPP game whose own files Windows Defender does not hold:
   `viwo --features extraction,capture agent <game> --exe <game>\<Game>.exe --workspace W`.
2. Expected: windowed, no BepInEx console; `.runtime\agent\bepinex-agent\` holds the interop
   assemblies (Assembly-CSharp.dll among them) and LogOutput.log. A Mono game answers
   `unavailable: ... a Mono build`. Files Defender holds are listed under `notCopied`.

## SQC-DYN-06 (P1) Audio loopback
1. `viwo install soundcard`; play any sound; `viwo --features extraction,capture record
   --workspace W --seconds 5`: a WAV under `.runtime\audio\`, `peak` above 0.

| ID | Result | Version | Notes |
|----|--------|---------|-------|
| SQC-DYN-01 | NOT RUN | 1.17.0 | steps changed in 1.17.0 (`viwo attach`, the game's own process); passed 1.4.7 as `analyze --open` on a debug copy |
| SQC-DYN-02 | NOT RUN | 1.17.0 | steps changed in 1.17.0 (`viwo attach`, table under `.runtime`); passed 1.4.7 (pid 28036) |
| SQC-DYN-03 | PASS | 1.4.7 | agent, 2026-11-03: 635 MB dump, 28,250 calls |
| SQC-DYN-04 | PASS | 1.4.7 | agent, 2026-11-03: Void's Cave, 1.3 MB usmap, 12 MB dump |
| SQC-DYN-05 | BLOCKED | 1.4.7 | both IL2CPP titles here are online-fix builds Defender holds; tests cover the agent |
| SQC-DYN-06 | PASS | 1.4.7 | agent, 2026-11-03: peak 0.48 |
