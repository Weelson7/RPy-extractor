# 11 Runtime capture (RenderDoc pilot)

Area code `CAP`. Philosophy: no policy boundaries. The only gate is the `capture` feature switch
in the ini and one confirmation; anti-cheat markers, online titles and terms-of-service-sensitive
plugins produce **warnings, never refusals**. Fixture: `capture` (`clean\`, `anticheat\`,
`Apex Legends\`, `outside.exe`) and `C:\sqc\ini\capture-on.ini`. RenderDoc from
`third_party\renderdoccmd\` (1.47): `renderdoccmd` launches, `qrenderdoc --py` triggers
(`--auto`) and harvests; its first-run prompts are pre-answered by ViWo (minimal-prompt rule).

## SQC-CAP-01 (P0) Feature switch off: refused with the hint

Steps: `viwo capture C:\sqc\capture\clean --exe C:\sqc\capture\clean\Game.exe --workspace C:\sqc\_ws\cap1 --confirm`

Expected: `viwo: refused: runtime capture is off` with the hint `add capture to [startup]
features in the ini`; exit 3. Nothing is created.

## SQC-CAP-02 (P0) Confirmation required once; warnings list; anti-cheat and online titles run

Steps (all with `--ini C:\sqc\ini\capture-on.ini`):
1. `viwo --ini C:\sqc\ini\capture-on.ini capture C:\sqc\capture\clean --exe C:\sqc\capture\clean\Game.exe --workspace C:\sqc\_ws\cap2`
2. same with `--confirm`
3. `... capture C:\sqc\capture\anticheat --exe C:\sqc\capture\anticheat\Game.exe --workspace C:\sqc\_ws\cap3 --confirm`
4. `... capture "C:\sqc\capture\Apex Legends" --exe "C:\sqc\capture\Apex Legends\r5apex.exe" --workspace C:\sqc\_ws\cap4 --confirm`
5. `... capture C:\sqc\capture\clean --exe C:\sqc\capture\outside.exe --workspace C:\sqc\_ws\cap5 --confirm`

Expected:
- 1: `viwo: needs_decision: confirm before capturing`, hint = the confirmation text (`my own
  install, intended for offline use; I am responsible for terms of service, anti-cheat
  consequences and anything I do with the captures`); exit 2.
- 2: the capture proceeds to the launch (`Launching Game.exe under RenderDoc; one frame captured
  after 30 s`); with the fixture's fake exe the trigger finds no target and it ends with `the
  trigger helper took no capture` (`failed`) after its timeout, which is the expected outcome here
  (`--auto 0` gives the attended message `capture with F12 / PrtScn, then quit the game` and the
  quick `no capture was taken`); the warning `Go offline first if the game
  allows it...` is printed.
- 3: NOT refused. The warnings contain `anti-cheat present: Easy Anti-Cheat (EasyAntiCheat). ViWo
  does not evade it: the capture may be blocked, and running a capture tool next to it can get an
  account banned`; then the same launch as 2.
- 4: NOT refused. Warning `online/competitive title: Apex Legends (online). Intended for offline
  use of your own install`; then the launch.
- 5: `refused: the executable must be a file inside the game folder` (engineering check: the
  journal overlay needs the exe under the game root), exit 3.

## SQC-CAP-03 (P0) Journal overlay is restored, game folder unchanged

Steps: snapshot `C:\sqc\capture\clean`; run SQC-CAP-02 step 2; compare; check
`viwo-data\tmp\..\capture\` for journals.

Expected: no difference in the game folder after the run; no pending journal remains; the run
record under the workspace lists `restored: true`.

## SQC-CAP-04 (P1) Crash recovery

Steps: start a capture on a real game (SQC-CAP-06), kill `python.exe` while the game runs; start
`viwo serve` or any `viwo capture` again.

Expected: the first line `Restoring an interrupted session in <game>` (warn), the overlay files are
removed, the game folder matches its pre-capture hashes.

## SQC-CAP-05 (P1) Terms-of-service-sensitive plugin: warning, not refusal

Steps: `viwo --ini C:\sqc\ini\capture-on.ini capture C:\sqc\overwatch\Overwatch --exe C:\sqc\overwatch\Overwatch\Overwatch.exe --workspace C:\sqc\_ws\cap6 --confirm`

Expected: warnings include `online/competitive title: Overwatch (online only)` and
`terms-of-service-sensitive plugin: overwatch`; the launch happens (and fails on the fake exe with
`no capture was taken`); code never `refused`.

## SQC-CAP-06 (P1) Unattended capture and harvest on a GPU game

Preconditions: a desktop with a GPU, a D3D11/12 or Vulkan title (ULTRAKILL Prelude in
`Test-games\ultrakill-prelude`), `capture` in `[startup] features`, the pinned RenderDoc installed,
a pristine `%APPDATA%\qrenderdoc\UI.config` (delete it to check the pre-answering).

Steps:
1. `viwo --ini capture.ini capture Test-games\ultrakill-prelude --exe Test-games\ultrakill-prelude\ULTRAKILL.exe --workspace C:\sqc\_ws\real --confirm --auto 45`
2. Do nothing: no F12, no dialog, no quitting.

Expected: `Launching ULTRAKILL.exe under RenderDoc; one frame captured after 45 s`, then
`Trigger helper exit 0; stopped ULTRAKILL.exe` (the game is gone from the process list), one
`Harvested viwo_frame<N>.rdc: ok`, PNG textures in `png\` and `shader_<id>_<stage>.txt`
disassemblies in `txt\`, all with provenance `capture`; `Captured N file(s) with renderdoc; M not
found by static extraction`; `UI.config` now holds `Analytics_ManualCheck: true`; the game install
is unchanged. `--auto 30` is the default; the attended variant (`--auto 0`, press F12, quit)
harvests the same way.

## SQC-CAP-07 (P1, OPERATOR) Real capture on a game with anti-cheat, offline

Preconditions: as 06, a game with an anti-cheat marker, played offline.

Steps: as 06.

Expected: the warning about anti-cheat prints; ViWo launches anyway; the result is whatever the
anti-cheat allows (a blocked launch is reported as `failed` with the stderr tail, not as a ViWo
refusal). Record the outcome in the notes.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-CAP-01 | | version: | | |
| SQC-CAP-02 | | | | |
| SQC-CAP-03 | | | | |
| SQC-CAP-04 | | | | |
| SQC-CAP-05 | | | | |
| SQC-CAP-06 | PASS | 1.3.6: 89 textures + 30 shaders from ULTRAKILL, frame 7056, nothing pressed | agent | 2026-11-03 |
| SQC-CAP-07 | | OPERATOR | | |
