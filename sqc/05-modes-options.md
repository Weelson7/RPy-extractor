# 05 Modes and options

Area code `MODE`. Fixtures: `renpy`, `doom`, `zip-basic`, `carve`. Mixed-mode game: copy
`C:\sqc\renpy\game` to `C:\sqc\_mixed\game` and add `C:\sqc\doom\game\doom2.wad` into it.

## SQC-MODE-01 (P0) AUTO picks the best detection

Steps: `viwo extract C:\sqc\_mixed\game --workspace C:\sqc\_ws\m1 --on-existing replace`

Expected: `Selected plugin(s): renpy` (highest confidence); `doom2.wad` is still unpacked by the
core `unarchive.wad` slot (`OK doom2.wad`), because container slots serve every run.

## SQC-MODE-02 (P0) SINGLE forces one plugin

Steps: `viwo extract C:\sqc\_mixed\game --workspace C:\sqc\_ws\m2 --on-existing replace --plugin doom`

Expected: `Selected plugin(s): doom`; the Ren'Py source root is not copied; `images.rpa` is still
unpacked (container slot). `--plugin nosuch` fails with `invalid_request` listing the known ids.

## SQC-MODE-03 (P0) MIXED with the three policies

Steps:
1. `... --mixed renpy,doom --policy selected`
2. `... --mixed renpy --policy detected`
3. `... --mixed renpy --policy all`

Expected: 1: both run, in priority order (`rpgmaker 16 > bethesda 12 > renpy 10 > doom`...: the
log names the order). 2: every plugin whose detection fired (renpy, doom, generic) runs. 3: every
enabled plugin runs, including `overwatch` and `quickbms`, each reporting 0 files where nothing
matches; no plugin crashes the run (a plugin error becomes a warning).

## SQC-MODE-04 (P0) UI: 01.C MODE mirrors the CLI

Steps: `01 EXTRACT`, target `C:\sqc\_mixed\game`, in `01.C MODE` try `AUTO`, `SINGLE` (pick
`Doom engine`), `MIXED` (tick `Ren'Py` and `Doom engine`, `POLICY` = `only the plugins picked
below`), run each.

Expected: the action bar explains the choice (`AUTO: Ren'Py`, `SINGLE: Doom engine`, `MIXED: 2
plugins · only the plugins picked below`); each run's `Selected plugin(s)` line in `01.E LIVE
FEED` matches; `04 JOBS` shows three `EXTRACTION` jobs.

## SQC-MODE-05 (P0) Carve modes

Steps on `C:\sqc\carve\game`:
1. default (`--carve unknown`)
2. `--carve off`
3. `--carve all`

Expected: 1: `Carved 16 file(s)`. 2: no CARVE stage, `assets.bin` lands in `bin\` untouched.
3: every file is carved including recognized ones (the log says `carving all files`); same 16.
In the UI the three radio choices read `in files nothing else recognizes`, `in every file,
executables included`, `nowhere (off)`.

## SQC-MODE-06 (P0) Extension filter

Steps:
1. `viwo extract C:\sqc\zip-basic\game --workspace C:\sqc\_ws\f1 --on-existing replace --exts .png`
2. UI: `01.D FILTER + OUTPUT > EXTENSION FILTER (OPTIONAL)` click the preset `IMAGES`, run; then
   `CLEAR`, type `.ogg .txt`, run.

Expected: 1: only `png\` exists (2 files); the run record lists `extensions: [".png"]`. 2: the
preset fills `.png .jpg .jpeg .webp .gif .bmp .dds`; the second run gives `ogg\` and `txt\` only.

## SQC-MODE-07 (P0) `--on-existing` ask / new / replace / cancel

Steps (same workspace `C:\sqc\_ws\exist` each time):
1. first run without the flag (empty folder): ok.
2. second run without the flag.
3. `--on-existing new`
4. `--on-existing replace`
5. `--on-existing cancel`

Expected: 2: exit 2, `viwo: needs_decision: ... workspace is not empty` with the hint listing
`new | replace | cancel`. 3: a sibling `C:\sqc\_ws\exist (2)` (or `-2`) is created and used. 4:
the extension groups in `exist` are replaced; the marker and metadata stay. 5: exit 130,
`cancelled`. In the UI the same situation opens a modal `WORKSPACE NOT EMPTY` with the three
buttons `NEW`, `REPLACE`, `CANCEL`.

## SQC-MODE-08 (P1) Plugin options: bool, string, secret

Steps:
1. `--option doom.raw_lumps=true` on the doom fixture.
2. UI `01.C MODE > ENGINE OPTIONS` for Godot: the key field is a password field with the badge
   `SECRET`; for Overwatch `modes` is a text field with the default
   `extract-unlocks,extract-general,extract-maps`.
3. In `startup.ini` add `[options.godot] encryption_key = 00` and run `viwo config check startup.ini`.

Expected: 1: `lmp\` group appears. 2: as described; the secret value is sent with the request and
never shown in 04 JOBS or the run record (`<secret>`). 3: the check refuses secret-looking keys
in the ini: `options.godot.encryption_key looks like a secret` (exit 2).

## SQC-MODE-09 (P1) Replay a run record

Steps: `viwo replay C:\sqc\_ws\renpy\.extraction_metadata\runs\<latest>.json --workspace C:\sqc\_ws\replay --on-existing replace`

Expected: identical extension groups and file hashes as the original workspace (compare with
`Get-FileHash`); a run whose record stored a `<secret>` option fails with `needs_key` until the
option is passed again with `--option`.

## SQC-MODE-10 (P2) Cancel a running extraction

Steps: start the `deep-nesting` or a large real game extraction from the UI, click `CANCEL JOB`
in the action bar within 2 s.

Expected: the feed ends with `CANCELLED`, the job state is `cancelled`, the partial workspace
keeps its marker; the game folder is unchanged.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-MODE-01 | | version: | | |
| SQC-MODE-02 | | | | |
| SQC-MODE-03 | | | | |
| SQC-MODE-04 | | | | |
| SQC-MODE-05 | | | | |
| SQC-MODE-06 | | | | |
| SQC-MODE-07 | | | | |
| SQC-MODE-08 | | | | |
| SQC-MODE-09 | | | | |
| SQC-MODE-10 | | | | |
