# 09 Round trip (patched copy)

Area code `RT`. Fixture: `roundtrip` (`loose\`, `rpa\`, `zip\`, `mv\`), plus `godot` and
`unreal` with their fake-tool ini for the PCK and `_P.pak` strategies. Flow for each game:
extract into a workspace, edit a file in the workspace with any editor, then `09 PATCHED COPY`
(or `viwo repack`) builds a separate copy of the game with the edit, verified by re-extraction.

## SQC-RT-01 (P0) Plan shows the edit set and the strategy

Steps:
1. `viwo extract C:\sqc\roundtrip\rpa --workspace C:\sqc\_ws\rt-rpa --on-existing replace`
2. Open `C:\sqc\_ws\rt-rpa\txt\script.txt` in an editor, change `original` to `patched`, save.
3. `viwo repack C:\sqc\_ws\rt-rpa --plan`
4. UI: `WORKSPACE > SWITCH` to that workspace; `09 PATCHED COPY > 09.A EDIT SET + STRATEGY > PLAN`.

Expected: 3 and 4 list one edited file `txt\script.txt` with its origin `game\images.rpa`
(provenance) and the strategy `Ren'Py RPA rebuild` (slot `pack.rpa`, backend `rpa-writer`);
unchanged files are not listed; the stats show `EDITED 1`, `CONTAINERS 1`. Nothing is written.

## SQC-RT-02 (P0) Build the patched copy; the original is UNTOUCHED; verified

Steps:
1. Snapshot `C:\sqc\roundtrip\rpa` (see 06).
2. UI: `09.B TARGET FOLDER` = `C:\sqc\_patched\rpa` (`BROWSE` or type), `09.C BUILD > BUILD
   PATCHED COPY`.
3. Compare the snapshot.
4. `viwo extract C:\sqc\_patched\rpa --workspace C:\sqc\_ws\rt-check --on-existing replace`;
   read `txt\script.txt`.

Expected: 2: progress `PATCHING` with the rail `plan › copy › pack › verify › report`, counter
`GAME FILES COPIED`, final `PATCHED COPY READY · VERIFIED`; `09.D RESULT` with the badge
`VERIFIED ✓`, the card `ORIGINAL: UNTOUCHED`, the target path, `OPEN FOLDER`. The target has the
marker `.viwo-patched-copy` (or the equivalent marker file) and a rebuilt `game\images.rpa`.
3: nothing differs. 4: the file reads `patched`.

## SQC-RT-03 (P0) Loose override, zip and RPG Maker MV strategies

Steps: repeat SQC-RT-01/02 for `C:\sqc\roundtrip\loose` (edit `txt\readme.txt`), `...\zip` (edit
`txt\settings.txt`), `...\mv` (edit `png\Actor2.png`, e.g. re-save it with any image editor).

Expected: strategies `loose override`, `zip`, `RPG Maker MV/MZ (re-encrypt)`; each copy verifies;
for `mv` the copy's `www\img\faces\Actor2.rpgmvp` decrypts to the edited PNG when re-extracted.

## SQC-RT-04 (P0) Godot PCK and Unreal `_P.pak` with fake tools, then real tools

Steps: with `--ini C:\sqc\ini\godot-fake.ini`: extract `C:\sqc\godot\standalone`, edit a text
file, `viwo --ini ... repack <ws> --out C:\sqc\_patched\godot`. With `--ini C:\sqc\ini\unreal-fake.ini`:
same for `C:\sqc\unreal\plain`. Then both again with the default ini (real GodotPckTool, real
repak from `third_party\`).

Expected: strategies `Godot PCK rebuild` (`pack.pck`, `godotpcktool`) and `Unreal patch pak`
(`pack.upak`, `repak`, a new `pakchunk0-Windows_P.pak` next to the original in the copy, original
pak kept); both `verified`. With the real tools the same result; if the real tool rejects the
synthetic container, the report says `NOT VERIFIED` with the tool's message and the original stays
untouched (record as FAIL with the message).

## SQC-RT-05 (P0) Target folder rules

Steps:
1. `viwo repack <ws> --out C:\sqc\roundtrip\rpa` (the game itself)
2. `--out C:\sqc\roundtrip\rpa\copy` (inside the game)
3. `--out C:\sqc\_patched\rpa` a second time (an existing patched copy)
4. `--out C:\sqc\_ws\sort` (a non-empty folder that is not a patched copy)

Expected: 1 and 2: `refused: ...inside the game folder...`. 3: the copy is rebuilt (the marker
allows it). 4: `refused: ... is not empty and is not a ViWo patched copy`. In the UI the error box
is `REFUSED FOR SAFETY`.

## SQC-RT-06 (P1) Unity strategy on a real game

Steps: extract a Unity game you own, edit a `TextAsset` (`txt\`) or a `Texture2D` PNG, build the
copy, run the game from the copy.

Expected: strategy `Unity (same-format save)` with UnityPy; the copy verifies; the game shows the
edit; the original install is unchanged.

## SQC-RT-07 (P1) No edits, no provenance

Steps: `viwo repack <fresh workspace> --plan`; `viwo repack C:\sqc\_ws\mine --plan` (not a
workspace).

Expected: `EDITED 0` and the note `nothing to patch` (exit 0); the second gives `not_found: no
extraction run record: extract into this workspace first`.

## SQC-RT-08 (P1) Terms-of-service-sensitive plugin: reminder, not refusal

Steps: with `C:\sqc\ini\overwatch-fake.ini` extract the overwatch fixture, edit a file, plan and
build a patched copy.

Expected: the plan carries the warning `overwatch: own install, offline use; respect the game's
terms`; the build proceeds (loose override) and verifies. No `refused`.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-RT-01 | | version: | | |
| SQC-RT-02 | | | | |
| SQC-RT-03 | | | | |
| SQC-RT-04 | | | | |
| SQC-RT-05 | | | | |
| SQC-RT-06 | | | | |
| SQC-RT-07 | | | | |
| SQC-RT-08 | | | | |
