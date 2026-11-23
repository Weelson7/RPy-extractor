# 09 Round trip (patched copy)

Area code `RT`. Fixture: `roundtrip` (`loose\`, `rpa\`, `zip\`, `mv\`), the engine fixtures of 04
(their workspaces from SQC-EXT-23 to -31), and `real-containers` (a pak and a PCK written by the
real repak and GodotPckTool). Flow for each game: extract into a workspace, edit a file there,
then `PATCHED COPY` (or `viwo repack`) builds a separate copy of the game with the edit, verified
by re-extraction. `--mode mod` (default) prefers what leaves the game's files untouched (loose
files, override paks); `--mode overwrite` rewrites the container; where an engine has one form
the plan says which and why (doc 18.3). The copy carries `.viwo-patched\report.json` (`game`,
`target`, `mode`, `edits`, `plan`, `skipped`, `warnings`, `results`, `verified`). The CLI prints
`Game`, `Edits`, `Mode`, `Plan` (one line per container, then `MOD:` / `OVERWRITE:` and why, then
one line per decoded file going back), `Packed`, `Skipped`, `Result <copy> (verified | NOT
verified)`.

## SQC-RT-01 (P0) Plan shows the edit set and the strategy

Steps:
1. `viwo extract C:\sqc\roundtrip\rpa --workspace C:\sqc\_ws\rt-rpa --on-existing replace`
2. In `C:\sqc\_ws\rt-rpa\txt\script.txt` change `original` to `patched`, save.
3. `viwo repack C:\sqc\_ws\rt-rpa --plan`; then `--plan --mode overwrite`.
4. UI: `SWITCH` to that workspace; `PATCHED COPY > EDIT SET + STRATEGY > PLAN`.

Expected: 3: `Edits : 1 file(s)`, `Mode : mod (asked)`, `Plan : loose files -> override (1
member(s))`, `MOD: loose files in game/, loaded over game/images.rpa` (the member
`game/script.txt`); with overwrite: `game/images.rpa -> pack.rpa (1 member(s))`, `OVERWRITE:
game/images.rpa rewritten in the copy`. Unchanged files are not listed; nothing is written. 4:
the same plan; stats `EDITS 1`, `TARGETS 1`.

## SQC-RT-02 (P0) Build the patched copy; the original is UNTOUCHED; verified

Steps:
1. Snapshot `C:\sqc\roundtrip\rpa` (see 06).
2. `viwo repack C:\sqc\_ws\rt-rpa --out C:\sqc\_patched\rpa`; UI: `TARGET FOLDER` =
   `C:\sqc\_patched\rpa`, `BUILD PATCHED COPY`.
3. Compare the snapshot.
4. `viwo extract C:\sqc\_patched\rpa --workspace C:\sqc\_ws\rt-check --on-existing replace`; read
   `txt\script.txt`.
5. Steps 2 and 4 with `--mode overwrite` into `C:\sqc\_patched\rpa-ow`.

Expected: 2: `[CORE:REPACK] Copying the game to ...`, `Patched copy ready (verified)`, `Packed :
loose files verified`, `Result : C:\sqc\_patched\rpa (verified)`; the copy holds
`.viwo-patched\report.json`, `game\script.txt` (loose) and the untouched `game\images.rpa`. UI:
progress, `PATCHED COPY READY · VERIFIED`, `RESULT` with `VERIFIED ✓`, the card `ORIGINAL:
UNTOUCHED`, the target path, `OPEN FOLDER`. 3: nothing differs. 4: the file reads `patched`. 5:
`Packing game/images.rpa (pack.rpa, 1 member(s))`, `Verify images.rpa: verified`; re-extracted it
reads `patched`.

## SQC-RT-03 (P0) Loose, zip and RPG Maker MV

Steps: SQC-RT-01/02 for `C:\sqc\roundtrip\loose` (edit `txt\readme.txt`), `...\zip` (edit
`txt\settings.txt`), `...\mv` (replace `png\Actor2.png` with another PNG, e.g. re-saved by any
editor).

Expected: `loose files -> override` with `OVERWRITE: loose game files, replaced in the copy`;
`data.zip -> pack.zip` and `www/img/faces/Actor2.rpgmvp -> pack.rpgmaker`, each `OVERWRITE: ...
rewritten in the copy: the engine loads nothing over it, so there is no mod form`; every copy
`verified`; the copy's `readme.txt` and `data.zip!cfg/settings.txt` read the edit; the copy's
`Actor2.rpgmvp` decrypts to the edited PNG byte for byte when re-extracted.

## SQC-RT-04 (P0) Godot PCK and Unreal `_P.pak` with the real tools

Preconditions: the real tools; the workspaces of SQC-EXT-06 step 4 (`godot-real`) and SQC-EXT-09
(`ue-real`).

Steps:
1. Edit `C:\sqc\_ws\godot-real\txt\notes.txt`; `viwo repack C:\sqc\_ws\godot-real --out C:\sqc\_patched\godot-real`.
2. Edit `C:\sqc\_ws\ue-real\ini\DefaultGame.ini`; `viwo repack C:\sqc\_ws\ue-real --out C:\sqc\_patched\unreal-real`.
3. `viwo repack C:\sqc\_ws\ue-real --plan --mode overwrite`.

Expected: 1: `data.pck -> pack.pck` (no mod form), `Packing data.pck`, GodotPckTool's `Target pck
exists, loading it before adding new files`, `Verify data.pck: verified`. 2: `MOD: a separate file
the engine loads over Game/Content/Paks/pakchunk0-Windows.pak`, `Packed 1 files to
...\pakchunk0-Windows_P.pak`, `Packed : Game/Content/Paks/pakchunk0-Windows_P.pak verified`; the
original pak stays in the copy beside the new `_P.pak`. 3: `Mode : overwrite (asked)` but `MOD:
... this engine has no rewrite of it`. The fake-tool ini (`godot-fake.ini`, `unreal-fake.ini`)
are for extraction only: their fake GodotPckTool and repak do not pack.

## SQC-RT-05 (P0) Target folder rules

Steps (workspace `rt-rpa`):
1. `viwo repack <ws> --out C:\sqc\roundtrip\rpa` (the game itself)
2. `--out C:\sqc\roundtrip\rpa\copy` (inside the game)
3. `--out C:\sqc\_patched\rpa` a second time (an existing patched copy)
4. `--out C:\sqc\_ws\zip` (a non-empty folder that is not a patched copy)

Expected: 1: `viwo: refused: the patched copy (C:\sqc\roundtrip\rpa) is the game folder (...)`,
exit 3. 2: `... is inside the game folder (...)`, exit 3. 3: the copy is rebuilt (the marker
allows it), `verified`. 4: `viwo: refused: C:\sqc\_ws\zip is not empty and is not a ViWo patched
copy`, exit 3, nothing written there. In the UI the error box is `TARGET REFUSED`.

## SQC-RT-06 (P1) Unity strategy on a real game

Steps: extract a Unity game you own, edit a `TextAsset` (`txt\`) or a `Texture2D` PNG, build the
copy, run the game from the copy.

Expected: the Unity container is rewritten with UnityPy (`pack.unity`, `unitypy-pack`; no mod
form); the copy verifies (`untouched members were not re-verified` noted); the game shows the
edit; the original install is unchanged.

## SQC-RT-07 (P1) No edits, no provenance

Steps: `viwo repack <a fresh workspace> --plan`, then `--out C:\sqc\_patched\none`; `viwo repack
C:\sqc\_ws\mine --plan` (not a workspace).

Expected: `Edits : 0 file(s)`, exit 0, and no copy is made (`C:\sqc\_patched\none` absent); the UI
shows `NOTHING TO PATCH` / `NO EDITS YET`. The second: `viwo: not_found: no extraction run record:
extract into this workspace first`, exit 1 (UI `NO EXTRACTION RECORD`).

## SQC-RT-08 (P1) Terms-of-service-sensitive plugin: reminder, not refusal

Steps: with `C:\sqc\ini\overwatch-fake.ini` extract the overwatch fixture (SQC-EXT-17), edit
`info\.build.info` (a loose game file) and `txt\extract-maps.txt` (an export), plan and build a
patched copy.

Expected: the plan and the report's `warnings` carry the reminder `Overwatch: personal, offline
use of your own install; respect Blizzard's terms` (doc 18.3 WARN); the export is skipped with
`txt/extract-maps.txt: export file, writing it back is not supported yet`; the loose file goes
back (`OVERWRITE: loose game files, replaced in the copy`) and verifies. No refusal.

## SQC-RT-09 (P1) Containers of the newer engines

Steps (each: edit, `viwo repack <ws> --out C:\sqc\_patched\<name>`, re-extract the copy):
1. AGS `ags`: `crm\room1.crm` -> `room one, repainted`.
2. Defold `defold`: `txt\title.txt` -> `Jumper, edited`.
3. LÖVE `love-fused`: `txt\title.txt` -> `Blob Quest, edited`.
4. Wolf RPG `wolf`: `mps\map001.mps` -> `NEW MAP DATA` and `txt\_con.txt` -> `edited con`.
5. TyranoScript `tyrano`: `ks\first.ks`.

Expected: 1: `Quest.exe -> pack.clib`, verified; `game28.dta` unchanged. 2: `game.arci ->
pack.arci`, verified; `main.luac` unchanged. 3: `Blob.exe -> pack.love` (note `zip rebuilt after
the executable's own bytes`), verified. 4: `Data.wolf -> pack.wolf (2 member(s))` with the
members `con.txt` (the original name, from the names record) and `mapdata/map001.mps`, verified;
both read back. 5: `loose files -> override`, the copy's `data\scenario\first.ks` holds the edit.
Each says `OVERWRITE: ... rewritten in the copy: the engine loads nothing over it, so there is no
mod form` (TyranoScript: `loose game files, replaced in the copy`).

## SQC-RT-10 (P0) Android: APK manifest and resources, OBB, bundle

Steps:
1. In the `apk` workspace: in `xml\AndroidManifest.text.xml` set `android:versionName="2"`; in
   `json\resources.arsc.json` change `"World"` to `"Edited"`; `viwo repack <ws> --out
   C:\sqc\_patched\apk`.
2. The same with `--ini C:\sqc\ini\android-signer-fake.ini` (a fake uber-apk-signer).
3. In the `obb` workspace edit `bin\level1.bin`; repack.
4. In the `xapk` workspace edit `txt\readme.txt` (inside the bundle's APK); plan.

Expected: 1: `game.apk -> pack.apk (2 member(s))`, `xml/AndroidManifest.text.xml ->
AndroidManifest.xml (decode.axml)`, `json/resources.arsc.json -> resources.arsc (decode.arsc)`,
verified; the copy's APK passes `zipfile.testzip()`, its manifest reads `versionName="2"`, its
`resources.arsc` holds `Edited` (UTF-16), `META-INF/CERT.RSA` is gone; the notes say `3 old v1
signature file(s) left out (META-INF)`, `stored members aligned (4 bytes)` and "left UNSIGNED:
Android refuses to install it until it is signed (`viwo install uber-apk-signer`, or sign it
with your own apksigner)". 2: `Signing game.apk (uber-apk-signer)`; the note `signed with a debug
key: Android installs it only after the original app is uninstalled ...`. 3: `... .obb ->
pack.obb`, verified, `bin\level1.bin` reads the edit. 4: `Skipped : txt/readme.txt: derived file,
writing it back is not supported yet` (a bundle's APK is a nested container), `Edits : 0`.

## SQC-RT-11 (P1) Same-size rules: GameMaker and .NET

Steps:
1. `gm`: `bin\CODE.bin` -> `SOME BYTECODE HERE, FIXED LENGTH!` (same length); repack.
2. `gm`: `bin\CODE.bin` -> 999 bytes; repack. Then `json\strings.json` -> `[]`; repack.
3. `fw-dotnet`: `resources\App.Strings.resources` -> `NAME=max_connections;VALUE=00128` (same
   length); repack. Then also `resources\Other.resources` -> a longer text; repack.

Expected: 1: `data.win -> pack.gamemaker`, verified, read back. 2: `Packed : data.win FAILED:
chunks/CODE.bin`, `NOT verified`, error `data.win: chunks/CODE.bin: size changed (999 vs 33);
re-chunk not done`; `strings.json`: `not a writable member (strings.json is a read-only view)`.
3: `App.dll -> pack.resources`, verified, read back; the longer one: the note `1 resource(s)
whose size changed: not written (Other.resources)`, said on the console (SQC-RT-14).

## SQC-RT-12 (P1) Qt, Chromium, Java, frozen Python

Steps: `fw-qt` `json\d.json` -> `{"n":128}`; `fw-chromium` `dat\20.dat` -> `BETA!!`; `fw-java`
`properties\config.properties` -> `max.connections=128`; `fw-pyfrozen` `txt\data.txt` ->
`max_connections=128`; repack each, re-extract the copy.

Expected: `app.rcc -> pack.rcc`, `resources.pak -> pack.pak`, `app.jar -> pack.jar`, `app.exe ->
pack.pyi`, each verified (rcc, pak: `untouched members were not re-verified: this packer checks
the edited members only`); each edit reads back and the untouched members are as they were
(`qml\main.qml`, `dat\10.dat`, `class\Main.class`).

## SQC-RT-13 (P1) A decoded file goes back: XNA texture

Steps: in `xna` replace `png\logo.png` with a 6x2 RGBA PNG; repack; re-extract the copy.

Expected: `loose files -> override`, `png/logo.png -> Content/logo.xnb (decode.xnb)`, `Encoding
png/logo.png -> Content/logo.xnb (decode.xnb)`, verified; re-extracted, `png\logo.png` is 6x2 with
exactly the edited pixels.

## SQC-RT-14 (P0) What a packer notes is said on the console

Steps: the builds of SQC-RT-10 steps 1-2 and SQC-RT-11 step 3 (longer resource); read the CLI
output and the UI's `RESULT`.

Expected: every packer note of `report.json` (`results[].notes`) is printed: the APK's `left
UNSIGNED: ...` or `signed with a debug key: ...`, the .NET `1 resource(s) whose size changed: not
written (Other.resources)`; an edit that was not written makes the item fail (or at least a
warning), never a plain `verified` (rule: never silent).

## SQC-RT-15 (P1) Defold: an edited encrypted resource goes back encrypted

Steps: in `defold-enc` edit `luac\enc.luac` (`return 2`); repack; re-extract the copy.

Expected: `game.arci -> pack.arci`, verified; the copy's `enc.luac` is re-encrypted with the same
key (doc 2: `an edited encrypted resource re-encrypted`) and re-extracts to the edit.

## SQC-RT-16 (P1) A user keystore signs the rebuilt APK

Steps: put `[options.android] keystore = C:\sqc\android\my.jks` and `key_alias = me` in an ini
(base `android-signer-fake.ini`), give the passwords (`--option android.keystore_password=...` or
the UI's secret fields), repack the `apk` workspace.

Expected: the signer is called with `--ks <file> --ksAlias me --ksPass <secret> ...` and the note
says `signed with the keystore my.jks`; the passwords appear in no log, record or report.

## SQC-RT-LOAD (P0) The game loads the change

Steps, per engine (a free title of `games.md`, from a worktree at a committed version):
1. `viwo extract <game> --workspace W`; paint a clear mark on an image the game shows on its first
   screen (the title or menu background), in `W`.
2. `viwo repack W --out P`; read `Result: ... (verified)`.
3. `powershell -File tools\game_shot.ps1 -Exe P\<game exe> -Out shot.png -Wait 15`; a dialog in
   front of the menu is dismissed with `-Keys "{ENTER}"` (SendKeys syntax, several separated by
   `|`, one wait per key); a game drawing full screen through DirectX prints black, `-Screen`
   copies the screen instead.

Expected: the patched copy starts and `shot.png` (the game's own window) shows the mark; the game
folder is unchanged. Recorded: `sqc/proof/renpy-ddlc.jpg`, `sqc/proof/unity-baldi.jpg`,
`sqc/proof/rpgmaker-mv.jpg`, `sqc/proof/kirikiri-ubu.jpg`, `sqc/proof/genie-aoe2hd.jpg`,
`sqc/proof/doom-freedoom.jpg` (Chocolate Doom started with `-Arguments "-iwad
<P>\freedoom2.wad -window"`; run the tool with `&` from PowerShell, since `-File` splits a quoted
path), `sqc/proof/unreal-voids-cave.jpg` (Unreal: the mark is `ProjectDisplayedTitle` in
`DefaultGame.ini`, read in the window title `game_shot.ps1` prints). On KiriKiri pick an image the
scripts name without its folder (`storage="sky0"`).

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-RT-01 | PASS CLI; NOT RUN UI | version: 1.36.0+search+apk (unreleased). Both plans as written; JSON plan item `container ""`, `slot override`, `members ["game/script.txt"]`, `mode mod` | agent | 2026-11-23 |
| SQC-RT-02 | PASS CLI; NOT RUN UI | mod: verified, copy holds `.viwo-patched\report.json`, `game\script.txt`, `game\images.rpa`; re-extract reads `patched`; overwrite: `Verify images.rpa: verified`, reads `patched`; game unchanged | agent | 2026-11-23 |
| SQC-RT-03 | PASS | three copies verified; readme, zip member and MV image (byte-equal PNG) read back | agent | 2026-11-23 |
| SQC-RT-04 | PASS | real GodotPckTool 2.3 and repak 0.2.3: both verified, `pakchunk0-Windows_P.pak` beside the original; overwrite on Unreal: `this engine has no rewrite of it`. With the fake-tool ini both packs fail (`ValueError: '--output' is not in list` from the fakes of `tests/test_godot.py`, `tests/test_unreal.py`): the fakes do not model packing | agent | 2026-11-23 |
| SQC-RT-05 | PASS CLI; NOT RUN UI | 1-2 refused exit 3 with the messages; 3 rebuilt, verified; 4 refused exit 3, `_ws\zip` unchanged (the line `Copying the game to C:\sqc-a\_ws\zip` is printed before the refusal) | agent | 2026-11-23 |
| SQC-RT-06 | NOT RUN | no Unity game installed | | |
| SQC-RT-07 | PASS CLI; NOT RUN UI | `Edits : 0 file(s)`, exit 0, no copy; `not_found: no extraction run record: ...`, exit 1 | agent | 2026-11-23 |
| SQC-RT-08 | FAIL | no reminder anywhere: plan and build print none, `report.json` `warnings: []`; the export skipped as written; `.build.info` back and verified | agent | 2026-11-23 |
| SQC-RT-09 | PASS | all five verified and read back; Wolf plan members `con.txt`, `mapdata/map001.mps` | agent | 2026-11-23 |
| SQC-RT-10 | PASS | as written (in `report.json`: the three notes; with the fake signer `Signing game.apk (uber-apk-signer)` and the debug-key note); OBB verified; bundle edit skipped with the reason. That the notes are not printed is SQC-RT-14 | agent | 2026-11-23 |
| SQC-RT-11 | PASS | GameMaker: same size verified, 999 bytes refused by name, strings.json refused; .NET: same size verified; the longer one not written (note only, see SQC-RT-14) | agent | 2026-11-23 |
| SQC-RT-12 | PASS | four copies verified, edits and untouched members read back | agent | 2026-11-23 |
| SQC-RT-13 | PASS | `Encoding png/logo.png -> Content/logo.xnb (decode.xnb)`, verified; back 6x2, pixels equal | agent | 2026-11-23 |
| SQC-RT-14 | FAIL | `viwo repack` prints `Packed : game.apk verified` / `Result : ... (verified)` and none of the notes (`left UNSIGNED ...`, `signed with a debug key ...`); with the longer .NET resource: `Packed : App.dll verified`, `Result : ... (verified)`, while `report.json` notes `1 resource(s) whose size changed: not written (Other.resources)` | agent | 2026-11-23 |
| SQC-RT-15 | FAIL | `Verify game.arci: 1 member(s) FAILED`, `Packed : game.arci FAILED: enc.luac`, `NOT verified`; re-extracting the copy: `game.arci: 1 encrypted resource(s) not decrypted (no verified key): enc.luac` | agent | 2026-11-23 |
| SQC-RT-16 | FAIL | `[options.android] keystore` and `key_alias` are dropped as `secrets are not allowed in the ini` (the ini's secret-word filter matches "key"), so the debug key signed it; `viwo repack` has no `--option` (`unrecognized arguments`), and `POST /api/repack` takes no options: the passwords have no way in | agent | 2026-11-23 |
| SQC-RT-LOAD | NOT RUN | needs a game window and eyes. Earlier: PASS for Ren'Py, Unity, RPG Maker MV, KiriKiri, Genie, Doom, Unreal (`sqc/proof/`, 1.20.72 and later) | | |
