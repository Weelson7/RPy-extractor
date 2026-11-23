# 03 Detection and survey

Area codes `DET` (detection) and `SUR` (survey). Fixtures: `renpy`, `godot`, `unreal`, `doom`,
`rpgmaker`, `kirikiri`, `electron`, `source-vpk`, `bethesda`, `overwatch`, `unity-markers`,
`zip-basic`, `ags`, `android`, `defold`, `gamemaker`, `love2d`, `tyranoscript`, `wolfrpg`, `xna`,
`frameworks`, `kaitai`, `library`. Detection and survey only read: no tool is needed.

## SQC-DET-01 (P0) `viwo detect` names the right engine for every fixture

Steps: run `viwo detect C:\sqc\<folder>` for each folder below and read the first row.

Expected: a table `ENGINE  CONFIDENCE  EVIDENCE` with one row per enabled plugin (33), highest
first; the first row and its evidence:

| Folder | First row | Evidence (contains) |
|---|---|---|
| `renpy\game` | `renpy 0.95` | `renpy/ engine folder, .rpa archives, .rpy/.rpyc scripts` |
| `godot\standalone` | `godot 0.90` | `PCK archive (GDPC)` |
| `unreal\plain` | `unreal 0.92` | `Unreal .pak archives` |
| `doom\game` | `doom 0.90` | `IWAD (Doom engine game data), PWAD (Doom engine add-on data)` |
| `rpgmaker\xp` | `rpgmaker 0.90` | `RPG Maker runtime / archive files` |
| `rpgmaker\mv` | `rpgmaker 0.90` | `RPG Maker MV/MZ encrypted media, RPG Maker data/System.json + img/` |
| `kirikiri\plain` | `kirikiri 0.90` | `XP3 archives` |
| `electron\game` | `electron 0.80` | `app.asar archive, Electron / NW.js runtime` |
| `source-vpk\game` | `source 0.90` | `Valve VPK archives` |
| `bethesda\game` | `bethesda 0.90` | `BSA/BA2 archives` |
| `overwatch\Overwatch` | `overwatch 0.95` | `Overwatch executable, Blizzard CASC storage` |
| `unity-markers\game` | `unity 0.92` | `Unity player/data marker files, *_Data folder pattern` |
| `zip-basic\game` | `generic 0.40` | `No strong engine-specific signature needed` |
| `ags\game` | `ags 0.90` | `AGS packfile behind the game's executable, AGS setup and runtime files` |
| `android\apk` | `android 0.90` | `Android packages (APK or bundle)` |
| `android\bundle` | `android 0.90` | `Android packages (APK or bundle)` |
| `android\obb` | `android 0.60` | `Android expansion files (.obb)` |
| `defold\plain` | `defold 0.90` | `Defold bundle (game.arci, game.arcd), Defold manifest and project settings` |
| `gamemaker\game` | `gamemaker 0.90` | `GameMaker data file (FORM/GEN8 container)` |
| `love2d\fused` | `love2d 0.90` | `LÖVE game fused onto its executable, LÖVE runtime (love.dll)` |
| `love2d\archive` | `love2d 0.90` | `LÖVE game archive (.love)` |
| `tyranoscript\MyNovel` | `tyranoscript 0.90` | `TyranoScript engine (tyrano/), scenario scripts (*.ks), TyranoScript config (Config.tjs)` |
| `wolfrpg\plain` | `wolfrpg 0.90` | `Wolf RPG / DXArchive .wolf files, Wolf RPG runtime / archive files` |
| `xna\game` | `xna 0.90` | `XNB content files, XNA, FNA or MonoGame framework` |
| `frameworks\qt` | `qt 0.85` | `Qt resource collections (.rcc)` |
| `frameworks\chromium` | `chromium 0.85` | `Chromium .pak resource packs` |
| `frameworks\dotnet` | `dotnet 0.80` | `managed .NET assemblies` |
| `frameworks\java` | `java 0.85` | `Java archives (.jar/.war/.ear)` |
| `frameworks\pyfrozen` | `pyfrozen 0.85` | `PyInstaller onefile executable` |
| `kaitai\game` | `generic 0.40` | `kaitai` is listed at `0.00` (a plugin form, never an engine) |

`generic` is present at `0.40` everywhere; `quickbms` and `kaitai` never lead (`0.00`).

## SQC-DET-02 (P0) EXTRACT > DETECT shows the same result

Steps:
1. `EXTRACT > TARGET GAME FOLDER`: paste `C:\sqc\renpy\game`, press Enter (or `DETECT ENGINE`).
2. Repeat with `C:\sqc\overwatch\Overwatch`, then `C:\sqc\android\apk`.

Expected:
- Step 1: `DETECT` lists the engines with a confidence meter, `Ren'Py` first; `MODE` preselects
  `AUTO` with `Ren'Py` as the planned plugin (`AUTO PICK`); `RUN EXTRACTION` is enabled.
- Step 2: `Overwatch (DataTool)` first with the badge `TOS-SENSITIVE`; it IS the auto choice (no
  refusal, no exclusion); the reminder `Overwatch: personal, offline use of your own install;
  respect Blizzard's terms` is shown next to the plugin. The Android folder picks the Android
  plugin; its `ENGINE OPTIONS` show `keystore`, `key_alias` and the two passwords with the badge
  `SECRET · NEVER STORED`.

## SQC-DET-03 (P1) Detection on a folder that is not a game

Steps: `viwo detect C:\Windows\Fonts`; in the UI paste `C:\Windows\Fonts` and detect.

Expected: `generic 0.40` first, every other plugin at `0.00`; exit 0. The UI shows the plain-words
note that no engine matched and still allows an extraction (generic: archives + carver). No
error.

## SQC-DET-04 (P1) Detection of a missing folder

Steps: `viwo detect C:\nope`; UI: paste `C:\nope`, Enter.

Expected: CLI `viwo: invalid_request: game folder not found: C:\nope`, exit 2. UI: error box
`CHECK YOUR INPUT` with the message and `NEXT A path or option is not valid...`.

## SQC-SUR-01 (P0) `viwo survey` on the library fixture

Steps:
1. `viwo survey C:\sqc\library\lib`
2. `viwo survey C:\sqc\library\lib --deep`
3. `viwo --json survey C:\sqc\library\lib`
4. Hash the library before and after (`Get-ChildItem -Recurse -File | Get-FileHash`).

Expected:
- Step 1: two games. `...\Doomish`: `engine doom (0.90)`, coverage 100 %, `asset 1`, `code 1`,
  `container 1`. `...\Odd`: `engine generic (0.00)`, coverage 0 %, `code 1`, `container 1`,
  `unknown 1`, `unknown-dense 1`, then `? secret.pak 0.2 MB (dense: encrypted/compressed)` and
  `? assets.bin 0.1 MB (structured: try --deep)`; last line `1/2 game(s) fully covered`.
  stderr: `[SURVEY] 1/2 ...\Doomish`, `[SURVEY] 2/2 ...\Odd`.
- Step 2: `Odd` now has `carvable 1 files` (assets.bin) and coverage 30 %; `secret.pak` stays
  dense; `1/2 game(s) fully covered`.
- Step 3: envelope `ok: true`, `data.games` with 2 entries (`path`, `engine`, `confidence`,
  `evidence`, `categories`, `coverage`, `unknown`, `missingTools`), the same numbers as step 1
  (`Odd` coverage `0.0`, unknown `secret.pak` dense, `assets.bin` not dense).
- Step 4: byte-identical; nothing is created inside the library.

## SQC-SUR-02 (P0) SURVEY in the UI

Steps:
1. `SURVEY > GAME OR LIBRARY FOLDER`: `C:\sqc\library\lib`, `DEPTH` `QUICK`, click `SURVEY`.
2. On the `Odd` card click `RUN DEEP SURVEY`.
3. `SURVEY REPORTS` > `REFRESH`, `OPEN` the newest.

Expected:
- Step 1: `SURVEY RUN` shows the progress (`SURVEYING…`), one node per game, then complete.
  Stats `GAMES 2`, `FULLY COVERED 1`, `TOTAL DATA <bytes>`, `REPORT <id>` (stored in
  viwo-data/surveys). Two cards with `ENGINE <name>` / `NO ENGINE MATCH`, class counts and the
  unknown blobs with `DENSE` / `STRUCTURED` / `SMALL` badges; `NO TOOL` where a slot is unbound.
- Step 2: the card re-runs as `DEEP` and shows `CARVABLE` on `assets.bin`.
- Step 3: the stored report opens with the same cards. `HOW TO READ A SURVEY` explains every badge
  used above.

## SQC-SUR-03 (P1) Survey of a single game folder and of an empty folder

Steps: `viwo survey C:\sqc\doom\game`; `viwo survey <an empty folder>`; the same in the UI.

Expected: CLI: one entry, the folder itself (`engine doom (0.90)`, 100 %, `container 3 files`,
`1/1 game(s) fully covered`); the empty folder prints `No games found: pick a game folder or a
folder of game folders.` with exit 0. UI: one card; `NO GAMES FOUND` with the same hint, no error
toast.

## SQC-SUR-04 (P2) Survey on a large real library (optional)

Steps: survey your own games folder (10+ games), quick mode, from the UI.

Expected: progress advances game by game; `CANCEL` (or cancelling from JOBS) stops within 5 s
with `SURVEY CANCELLED`; no file is created inside any game folder.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-DET-01 | PASS | version: 1.36.0+search+apk (unreleased). All 30 folders: first row and evidence as in the table, exit 0; 33 rows each; `generic 0.40`; `kaitai` and `quickbms` 0.00 | agent | 2026-11-23 |
| SQC-DET-02 | NOT RUN | needs a browser | | |
| SQC-DET-03 | PASS CLI; NOT RUN UI | `generic 0.40`, the rest 0.00, exit 0 | agent | 2026-11-23 |
| SQC-DET-04 | PASS CLI; NOT RUN UI | `viwo: invalid_request: game folder not found: C:\nope`, exit 2 | agent | 2026-11-23 |
| SQC-SUR-01 | PASS | as written; deep: `carvable 1 files 0.1 MB`, `Odd` 30 % (`coverage: 0.302` in JSON); library hashes unchanged | agent | 2026-11-23 |
| SQC-SUR-02 | NOT RUN | needs a browser | | |
| SQC-SUR-03 | PASS CLI; NOT RUN UI | doom: one entry, `container 3 files`, `1/1`; empty folder: the sentence, exit 0 | agent | 2026-11-23 |
| SQC-SUR-04 | NOT RUN | needs a browser and a real library | | |
