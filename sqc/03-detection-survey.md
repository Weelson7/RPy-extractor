# 03 Detection and survey

Area codes `DET` (detection) and `SUR` (survey). Fixtures: `renpy`, `godot`, `unreal`, `doom`,
`rpgmaker`, `kirikiri`, `electron`, `source-vpk`, `bethesda`, `overwatch`, `unity-markers`,
`quickbms`, `library`, `carve`.

## SQC-DET-01 (P0) `viwo detect` names the right engine for every fixture

Steps: run each line and read the first row (highest confidence):
```powershell
viwo detect C:\sqc\renpy\game
viwo detect C:\sqc\godot\standalone
viwo detect C:\sqc\unreal\plain
viwo detect C:\sqc\doom\game
viwo detect C:\sqc\rpgmaker\xp
viwo detect C:\sqc\rpgmaker\mv
viwo detect C:\sqc\kirikiri\plain
viwo detect C:\sqc\electron\game
viwo detect C:\sqc\source-vpk\game
viwo detect C:\sqc\bethesda\game
viwo detect C:\sqc\overwatch\Overwatch
viwo detect C:\sqc\unity-markers\game
viwo detect C:\sqc\zip-basic\game
```

Expected: a table `ENGINE CONFIDENCE EVIDENCE`; the first row is, in order: `renpy`, `godot`,
`unreal`, `doom`, `rpgmaker`, `rpgmaker`, `kirikiri`, `electron`, `source`, `bethesda`,
`overwatch`, `unity`, `generic`, each with confidence >= 0.50 and at least one evidence item
(`renpy/ folder`, `.pck`, `Paks/`, `IWAD`, `Game.rgssad`, `System.json`, `.xp3`, `app.asar`,
`_dir.vpk`, `Data/*.bsa`, `.build.info`, `UnityPlayer.dll`). `generic` is always present with
confidence 0.00 or a low value. `quickbms` never leads (`any`, 0.00).

## SQC-DET-02 (P0) 01 EXTRACT > 01.B DETECT shows the same result

Steps:
1. `01 EXTRACT > 01.A TARGET GAME FOLDER`: paste `C:\sqc\renpy\game`, press Enter (or `DETECT
   ENGINE`).
2. Repeat with `C:\sqc\overwatch\Overwatch`.

Expected:
- Step 1: `01.B DETECT` lists the engines with a confidence meter; `Ren'Py` first; `01.C MODE`
  preselects `AUTO` with `Ren'Py` as the planned plugin; the action bar reads the target and
  `RUN EXTRACTION` is enabled.
- Step 2: `Overwatch (DataTool)` first with the badge `TOS-SENSITIVE`; it IS the auto choice
  (no refusal, no exclusion); the reminder text `Overwatch: personal, offline use of your own
  install; respect Blizzard's terms` is shown next to the plugin.

## SQC-DET-03 (P1) Detection on a folder that is not a game

Steps: `viwo detect C:\Windows\Fonts`; in the UI paste `C:\Windows\Fonts` and detect.

Expected: only `generic` (and `quickbms` at 0.00); the UI shows the plain-words note that no
engine matched and still allows an extraction (generic: archives + carver). No error.

## SQC-DET-04 (P1) Detection of a missing folder

Steps: `viwo detect C:\nope`; UI: paste `C:\nope`, Enter.

Expected: CLI `viwo: invalid_request: game folder not found: C:\nope`, exit 2. UI: error box
`CHECK YOUR INPUT` with the message and `NEXT A path or option is not valid...`.

## SQC-SUR-01 (P0) `viwo survey` on the library fixture

Steps:
1. `viwo survey C:\sqc\library\lib`
2. `viwo survey C:\sqc\library\lib --deep`
3. `viwo --json survey C:\sqc\library\lib > C:\sqc\_survey.json`

Expected:
- Step 1: two games `Doomish` and `Odd`; per game: engine, file counts per class (`asset`,
  `container`, `code`, `unknown`, `small`), the unknown blobs with a density label (`Odd\secret.pak`
  = `DENSE`, `Odd\assets.bin` = `STRUCTURED`), a coverage percentage. Progress lines
  `[SURVEY] 1/2 Doomish` on stderr.
- Step 2: `assets.bin` is reported `CARVABLE` with the number of embedded files the carver
  found; `secret.pak` stays `DENSE` with 0 carvable.
- Step 3: JSON envelope `ok: true`, `data.games` with 2 entries, same numbers as step 1.
- The folder `C:\sqc\library` is byte-identical before and after (`Get-ChildItem -Recurse |
  Get-FileHash` compare). Nothing is created inside it.

## SQC-SUR-02 (P0) 07 SURVEY in the UI

Steps:
1. `07 SURVEY > 07.A GAME OR LIBRARY FOLDER`: `C:\sqc\library\lib`, depth `QUICK`, click `SURVEY`.
2. On the `Odd` card click `RUN DEEP SURVEY`.

Expected:
- Step 1: `07.B SURVEY RUN` shows the progress block `SURVEYING`, one rail node per game, counter
  `GAMES 2`, then `COMPLETE`. Stats row: `GAMES 2`, `FULLY COVERED 1`, `TOTAL DATA <bytes>`. Two
  cards with the badges `ENGINE <name>` / `NO ENGINE MATCH`, class counts and the unknown blob
  list with `DENSE` / `STRUCTURED` / `SMALL` badges and `NO TOOL` where a slot is unbound.
- Step 2: the card re-runs with `DEEP` and shows `CARVABLE <n>` on `assets.bin`.
- `07.C HOW TO READ A SURVEY` explains every badge used above.

## SQC-SUR-03 (P1) Survey of a single game folder and of an empty folder

Steps: survey `C:\sqc\doom\game` (one game), then an empty folder.

Expected: one card for the game itself (the folder is the game, not a library); the empty folder
gives `NO GAMES FOUND` with the hint to pick a game or a folder of games, no error toast.

## SQC-SUR-04 (P2) Survey on a large real library (optional)

Steps: survey your own games folder (10+ games), quick mode.

Expected: progress advances game by game; cancelling from 04 JOBS stops within 5 s with state
`CANCELLED`; no file is created inside any game folder.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-DET-01 | | version: | | |
| SQC-DET-02 | | | | |
| SQC-DET-03 | | | | |
| SQC-DET-04 | | | | |
| SQC-SUR-01 | | | | |
| SQC-SUR-02 | | | | |
| SQC-SUR-03 | | | | |
| SQC-SUR-04 | | | | |
