# 11 Runtime capture (RenderDoc)

Area code `CAP`. Contract doc 11.1-11.2, 11.4-11.6. Philosophy: no policy boundaries. The only
gate is the `capture` feature switch and one confirmation per game folder; anti-cheat markers,
online titles, terms-of-service-sensitive plugins and a reachable network produce **warnings,
never refusals**. Fixtures: `capture` (`clean\Game.exe`, `anticheat\Game.exe` + `EasyAntiCheat\`,
`Apex Legends\r5apex.exe`, `outside.exe`), `overwatch` and `C:\sqc\ini\capture-on.ini`. RenderDoc
from `third_party\renderdoccmd\` (1.47): `renderdoccmd` launches, `qrenderdoc --py` (the `rdpython`
dependency, installed with it) triggers (`--auto`) and harvests; its first-run prompts are
pre-answered (minimal-prompt rule). The confirmations are kept in `viwo-data\capture\confirmed.json`.

## SQC-CAP-01 (P0) Feature switch off: refused with the hint

Steps: `viwo capture C:\sqc\capture\clean --exe C:\sqc\capture\clean\Game.exe --workspace C:\sqc\_ws\cap1 --confirm`
(the shipped `startup.ini`, `capture` not in features).

Expected: `viwo: refused: runtime capture is off`, hint `add capture to [startup] features in the
ini (SETTINGS)`; exit 3; `C:\sqc\_ws\cap1` not created.

## SQC-CAP-02 (P0) Confirmation once; warnings; anti-cheat and online titles are not refused

Steps (all with `--ini C:\sqc\ini\capture-on.ini`, `confirmed.json` deleted first):
1. `viwo --ini C:\sqc\ini\capture-on.ini capture C:\sqc\capture\clean --exe C:\sqc\capture\clean\Game.exe --workspace C:\sqc\_ws\cap2`
2. Step 1 with `--confirm`.
3. `... capture C:\sqc\capture\anticheat --exe C:\sqc\capture\anticheat\Game.exe --workspace C:\sqc\_ws\cap3 --confirm`
4. `... capture "C:\sqc\capture\Apex Legends" --exe "C:\sqc\capture\Apex Legends\r5apex.exe" --workspace C:\sqc\_ws\cap4 --confirm`
5. `... capture C:\sqc\capture\clean --exe C:\sqc\capture\outside.exe --workspace C:\sqc\_ws\cap5 --confirm`

Expected:
- 1: `viwo: needs_decision: confirm before capturing`, hint = the confirmation text (`my own
  install, intended for offline use; I am responsible for terms of service, anti-cheat consequences
  and anything I do with the captures`) plus, when online, `; the network is reachable: go offline
  before launching if the game allows it`; exit 2.
- 2: `[CAPTURE:WARN] the network is reachable: go offline before launching if the game allows it`
  (when online); then the launch: `Launching Game.exe under RenderDoc; one frame captured after
  30 s`; on the fixture's fake exe the trigger finds no target and it ends `failed` with `the trigger
  helper took no capture` after its timeout (`--auto 0`: `capture with F12 / PrtScn, then quit the
  game` and the quick `no capture was taken`). Without RenderDoc's Python (`rdpython`): `viwo:
  unavailable: no capture backend`, hint `install RenderDoc (MIT) for runtime capture`, exit 1.
- 3: NOT refused: `anti-cheat present: Easy Anti-Cheat (EasyAntiCheat). ViWo does not evade it: the
  capture may be blocked, and running a capture tool next to it can get an account banned`; then
  as 2.
- 4: NOT refused: `online/competitive title: Apex Legends (online). Intended for offline use of
  your own install`; then as 2.
- 5: `viwo: refused: the executable must be a file inside the game folder`, exit 3.

## SQC-CAP-03 (P0) The game folder is unchanged by a capture

Steps: hash every file of `C:\sqc\capture\clean` (path, size, sha256); run SQC-CAP-02 step 2;
hash again; list `viwo-data\capture\`.

Expected: no difference; `viwo-data\capture\` holds `confirmed.json` (the confirmed game folders)
and no `journal.json` (nothing writes into a game folder).

## SQC-CAP-04 (P1) A killed capture leaves the game folder untouched

Steps: start a capture on a real game (SQC-CAP-06), kill `python.exe` while the game runs (end the
game too if it stays); start `viwo capture` again on the same game.

Expected: the game folder matches its pre-capture hashes; the second capture starts normally (no
`Restoring an interrupted session` line: no journal exists).

## SQC-CAP-05 (P1) Terms-of-service-sensitive plugin: warning, not refusal

Steps: `viwo --ini C:\sqc\ini\capture-on.ini capture C:\sqc\overwatch\Overwatch --exe C:\sqc\overwatch\Overwatch\Overwatch.exe --workspace C:\sqc\_ws\cap6 --confirm`

Expected: warnings `online/competitive title: Overwatch (online only). Intended for offline use of
your own install` and `terms-of-service-sensitive plugin: overwatch`; then the launch (fails on the
fake exe); never `refused`.

## SQC-CAP-06 (P1) Unattended capture and harvest on a GPU game

Preconditions: a desktop with a GPU, a D3D11/12 or Vulkan title (ULTRAKILL Prelude in
`Test-games\ultrakill-prelude`), `capture` on, the pinned RenderDoc installed, a pristine
`%APPDATA%\qrenderdoc\UI.config` (delete it to check the pre-answering).

Steps:
1. `viwo --ini capture.ini capture Test-games\ultrakill-prelude --exe Test-games\ultrakill-prelude\ULTRAKILL.exe --workspace C:\sqc\_ws\real --confirm --auto 45`
2. Do nothing: no F12, no dialog, no quitting.

Expected: `Launching ULTRAKILL.exe under RenderDoc; one frame captured after 45 s`, then `Trigger
helper exit 0; stopped ULTRAKILL.exe` (the game is gone from the process list), one `Harvested
viwo_frame<N>.rdc: ok`, the frame kept in `rdc\`, PNG textures in `png\`, `shader_<id>_<stage>.txt`
in `txt\`, all with provenance `capture:renderdoc:<stamp>`; `Captured N file(s), M new vs static`;
`UI.config` now holds `Analytics_ManualCheck: true`; the game install unchanged. `--auto 30` is the
default; the attended variant (`--auto 0`, F12, quit) harvests the same way.

## SQC-CAP-07 (P1, OPERATOR) Real capture on a game with anti-cheat, offline

Preconditions: as 06, a game with an anti-cheat marker, played offline.

Steps: as 06.

Expected: the anti-cheat warning prints; ViWo launches anyway; the result is whatever the anti-cheat
allows (a blocked launch is `failed` with the stderr tail, not a ViWo refusal). Record the outcome.

## SQC-CAP-08 (P1) A capture keeps its frames; CAPTURE and the RenderDoc workbook

Preconditions: SQC-CAP-06 done (workspace `C:\sqc\_ws\real`).

Steps:
1. List `C:\sqc\_ws\real\rdc\`; open the frame in `third_party\renderdoccmd\qrenderdoc.exe`.
2. DYNAMIC arm > CAPTURE: read the target panel; click `HOW TO: RENDERDOC`.

Expected: 1: one `viwo_frame<N>.rdc` per capture, with its provenance line, beside the textures
harvested from it; qrenderdoc opens it with its draws and textures. 2: the view says every frame is
kept (it opens in RenderDoc) with its textures as PNG, collected like extracted files; WORKBOOKS
opens filtered to `RENDERDOC` ("Read a captured frame: draws, textures, meshes, shaders"); no ViWo
button opens qrenderdoc (the tool stays native).

## SQC-CAP-09 (P1) `POST /api/capture/warnings` before a capture

Preconditions: `viwo serve` with `capture` on.

Steps: `POST /api/capture/warnings {"gamePath": "C:\\sqc\\capture\\anticheat"}` (token header).

Expected: `success: true`, `warnings` = the anti-cheat warning (and the network one when online),
`confirmation` = the confirmation text, `enabled: true`, `backend` = the bound capture backend (`""`
when none is bound).

## Results

| ID | Result | Version | Notes | Tester | Date |
|----|--------|---------|-------|--------|------|
| SQC-CAP-01 | PASS | 1.36.0+search+apk (unreleased) | run as `--features extraction` on the test ini | agent | 2026-11-23 |
| SQC-CAP-02 | PASS (policy) / BLOCKED (launch) | 1.36.0+search+apk (unreleased) | steps 1, 3, 4, 5 warnings and answers as written; the launch half of 2-4 BLOCKED: RenderDoc's Python (`rdpython`, an argv `qrenderdoc --py`) cannot be pointed at through `[tools]`/env here (the worktree has no `third_party`), so each ended `unavailable: no capture backend` after its warnings | agent | 2026-11-23 |
| SQC-CAP-03 | PASS | 1.36.0+search+apk (unreleased) | hashes identical; `confirmed.json` only (launch half not reached, see 02) | agent | 2026-11-23 |
| SQC-CAP-04 | NOT RUN | 1.36.0+search+apk (unreleased) | needs a real GPU game | agent | 2026-11-23 |
| SQC-CAP-05 | PASS (warnings) / BLOCKED (launch) | 1.36.0+search+apk (unreleased) | both warnings, never refused; launch as in 02 | agent | 2026-11-23 |
| SQC-CAP-06 | NOT RUN | 1.36.0+search+apk (unreleased) | needs a GPU capture of a real game (passed at 1.3.6) | agent | 2026-11-23 |
| SQC-CAP-07 | NOT RUN | 1.36.0+search+apk (unreleased) | OPERATOR | agent | 2026-11-23 |
| SQC-CAP-08 | NOT RUN | 1.36.0+search+apk (unreleased) | needs SQC-CAP-06 and eyes | agent | 2026-11-23 |
| SQC-CAP-09 | PASS | 1.36.0+search+apk (unreleased) | `backend: ""` (no capture backend bound here) | agent | 2026-11-23 |
