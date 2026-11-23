# 05 Modes and options

Area code `MODE`. Fixtures: `renpy`, `doom`, `zip-basic`, `carve`, `nested-traversal`,
`unreal` (fake tools). Mixed-mode game: copy `C:\sqc\renpy\game` to `C:\sqc\_mixed\game` and
copy `C:\sqc\doom\game\doom2.wad` into it.

Two different `--plugin` flags exist: before the command, `--plugin ID=on|off` switches a plugin
on or off for the run (like `[plugins]`); after `extract`, `--plugin ID` forces SINGLE mode.

## SQC-MODE-01 (P0) AUTO picks the best detection

Steps: `viwo extract C:\sqc\_mixed\game --workspace C:\sqc\_ws\m1 --on-existing replace`

Expected: `Selected plugin(s): renpy` (highest confidence); `doom2.wad` is still unpacked
(`[DOOM:UNPACK] OK doom2.wad: 9 file(s) via wad-builtin`) because every enabled plugin's
container slots serve every run; Ren'Py's own files (`renpy\`, `MyVN.exe`) are not collected
(13 files).

## SQC-MODE-02 (P0) SINGLE forces one plugin

Steps:
1. `viwo extract C:\sqc\_mixed\game --workspace C:\sqc\_ws\m2 --on-existing replace --plugin doom`
2. The same with `--plugin nosuch` into `m2b`.

Expected:
- 1: `Extracted with: doom (single)`, `Selected plugin(s): doom`; `images.rpa` is still unpacked
  (container slot); without Ren'Py's file filter the engine's own files are collected too
  (`exe\MyVN.exe`, `py\__init__.py`): 16 files.
- 2: `viwo: invalid_request: unknown or disabled plugin(s): nosuch`, hint `enabled plugins: ags,
  android, ...` (the 33 ids), exit 2.

## SQC-MODE-03 (P0) MIXED with the three policies

Steps (each `viwo extract C:\sqc\_mixed\game --workspace C:\sqc\_ws\m3<x> --on-existing replace ...`):
1. `--mixed renpy,doom --policy selected`
2. `--mixed renpy --policy detected`
3. `--mixed renpy --policy all`

Expected: 1: `Extracted with: renpy, doom (mixed)`, both run. 2: every plugin whose detection
fired: `renpy, doom` (`generic` at 0.40 does not count as fired). 3: every enabled plugin runs
(`renpy, doom, generic, unity, unreal, ...` 33 ids); those with nothing to do report 0 files or
a warning (`export.unity: unitypy exported nothing`, `export.unreal: failed: Unreal asset export:
no .pak/.utoc`, `export.overwatch: failed: DataTool failed: ...` with the Overwatch reminder);
no plugin crashes the run; exit 0.

## SQC-MODE-04 (P0) UI: MODE mirrors the CLI

Steps: `EXTRACT`, target `C:\sqc\_mixed\game`, in `MODE` try `AUTO`, `SINGLE` (pick `Doom
engine`), `MIXED` (tick `Ren'Py` and `Doom engine`, `POLICY` = `SELECTED`: `only the plugins
picked below`), run each.

Expected: the action bar explains the choice (`AUTO: Ren'Py`, `SINGLE: Doom engine`, `MIXED: 2
plugins · only the plugins picked below`); each run's `Selected plugin(s)` line in `LIVE FEED`
matches; `JOBS` shows three `EXTRACTION` jobs.

## SQC-MODE-05 (P0) Carve modes

Steps on `C:\sqc\carve\game` (CLI), then the same three in the UI (`FILTER + OUTPUT > EMBEDDED
FILES`):
1. default (`--carve unknown`)
2. `--carve off`
3. `--carve all`
4. `--carve all` on `C:\sqc\nested-traversal\game`.

Expected: 1: `Carved 15 file(s) from assets.bin`. 2: no CARVE stage, `bin\assets.bin` untouched,
one file. 3: the same 15 (only `assets.bin` is there). 4: no CARVE stage: `all` adds
executables, code and files an exporter claims, never a file whose format is known (`.png`,
`.ogg`, `.zip`, `.md`). The UI's buttons read `UNKNOWN`, `ALL`, `OFF` with the note `find PNG,
OGG, WAV, DDS, Bink, FSB, zip… hidden in files nothing else recognizes` / `in every file,
executables included` / `nowhere (off)`.

## SQC-MODE-06 (P0) Extension filter

Steps:
1. `viwo extract C:\sqc\zip-basic\game --workspace C:\sqc\_ws\f1 --on-existing replace --exts .png`
2. UI: `FILTER + OUTPUT > EXTENSION FILTER (OPTIONAL)` click the preset `IMAGES`, run; then
   `CLEAR`, type `.ogg .txt`, run.

Expected: 1: only `png\` (2 files); the warning `extension filter: 3 file(s) of other types left
out (zip 1, ogg 1, txt 1)`; the run record's `request.selected_exts` is `[".png"]`. 2: the preset
fills `.png .jpg .jpeg .webp .gif .bmp .dds`; the second run gives `ogg\` and `txt\` only.

## SQC-MODE-07 (P0) `--on-existing` ask / new / replace / cancel

Steps (same workspace `C:\sqc\_ws\exist`, fixture `zip-basic`):
1. first run without the flag (folder absent): ok.
2. second run without the flag.
3. `--on-existing new`
4. `--on-existing replace`
5. `--on-existing cancel`

Expected: 2: exit 2, `viwo: needs_decision: C:\sqc\_ws\exist already holds an extraction`, hint
`new: a fresh folder next to it; replace: clear this workspace; or cancel; re-run with
--on-existing new | replace | cancel`. 3: a sibling `C:\sqc\_ws\exist-2` is created and used.
4: the groups in `exist` are replaced; the marker and metadata stay. 5: exit 130, `viwo:
cancelled: extraction cancelled by the re-extraction choice`. In the UI the same situation opens
a modal `WORKSPACE NOT EMPTY` with `NEW`, `REPLACE`, `CANCEL`.

## SQC-MODE-08 (P1) Plugin options: bool, string, secret

Steps:
1. `--option doom.raw_lumps=true` on the doom fixture (SQC-EXT-10 step 2).
2. UI `MODE > ENGINE OPTIONS` for Godot, Unreal, Overwatch, Wolf RPG, Defold, Android.
3. A `startup.ini` (in a folder of its own: `config check` reads any other name as a distro file)
   with `[options.godot] encryption_key = 00`; `viwo config check <it>`.

Expected: 1: the `lmp\` group grows to 10. 2: secret options (`encryption_key`, `aes_key`,
`decryption_key`, `keystore_password`, `key_password`) are password fields with `SECRET · NEVER
STORED`; Overwatch `modes` is a text field defaulting to `extract-unlocks,extract-general,extract-maps`;
the value is sent with the request and shown nowhere afterwards (`<secret>` in JOBS and the run
record). 3: `viwo: invalid_request: config check failed`, hint `...startup.ini: [options.godot]
encryption_key: secrets are not allowed in the ini`, exit 2.

## SQC-MODE-09 (P1) Replay a run record

Steps:
1. `viwo replay C:\sqc\_ws\renpy\.extraction_metadata\runs\<latest>.json --workspace C:\sqc\_ws\replay --on-existing replace`
2. `viwo --ini C:\sqc\ini\unreal-fake.ini replay C:\sqc\_ws\ue4\.extraction_metadata\runs\<latest>.json --workspace C:\sqc\_ws\replay-ue --on-existing replace`
3. Step 2 again with `--option unreal.aes_key=<key>`.

Expected: 1: identical file list and bytes as the original workspace. 2: exit 1, `viwo:
needs_key: secret option unreal.aes_key is not stored`, hint `pass --option
unreal.aes_key=VALUE`. 3: extracted (`OK pakchunk0-Windows.pak`).

## SQC-MODE-10 (P2) Cancel a running extraction

Steps: start the `zip-bomb` or a large real game extraction from the UI, click `CANCEL JOB` in the
action bar within 2 s.

Expected: the feed ends cancelled, the job state is `cancelled`, the partial workspace keeps its
marker; the game folder is unchanged.

## SQC-MODE-11 (P1) One worker budget; the same result on any count

Steps:
1. `$env:VIWO_WORKERS = "1"; viwo extract C:\sqc\nested-traversal\game --workspace C:\sqc\_ws\w1 --carve all --on-existing replace`
2. `$env:VIWO_WORKERS = "16"; ... --workspace C:\sqc\_ws\w16 ...`
3. `Remove-Item Env:VIWO_WORKERS`; compare the two workspaces (file list, bytes) and their
   `.extraction_metadata\provenance.jsonl`.
4. The same pair on a real game with thousands of files (`Test-games\freedoom`).

Expected: 3: the same files under the same names, every byte equal; the provenance files equal
line for line (they hold no times). A stage over many files says its worker count (`[CORE:CARVE]
Carving <n> unrecognized file(s) for embedded assets on <W> workers`, `[CORE:IDENTIFY] Looking
for nested archives in <n> extracted file(s) on <W> workers` with `Identified files: i / n`);
without the variable W is 80 % of the logical processors. 4:
the same, and no stretch of the run passes without a line (unpack, nested search, carve,
collect, decode each count).

## SQC-MODE-12 (P1) This run's plugins and profile

Steps:
1. `viwo --plugin renpy=off extract C:\sqc\_mixed\game --workspace C:\sqc\_ws\m12a --on-existing replace`
2. `viwo --profile renpy extract C:\sqc\_mixed\game --workspace C:\sqc\_ws\m12b --on-existing replace`
3. `viwo --profile nosuch info`

Expected: 1: `Selected plugin(s): doom`; `images.rpa` is NOT unpacked (its slot belongs to the
switched-off plugin) and stays as `rpa\images.rpa`. 2: `Selected plugin(s): renpy`; `doom2.wad`
is not unpacked (the renpy profile leaves the doom plugin out). 3: `viwo: invalid_request: unknown
profile 'nosuch'; one of ('godot', 'renpy', 'unity', 'unreal', 'custom', 'mixed')`, exit 2.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-MODE-01 | PASS | version: 1.36.0+search+apk (unreleased). renpy, doom2.wad unpacked, 13 files | agent | 2026-11-23 |
| SQC-MODE-02 | PASS | 16 files (`exe\MyVN.exe`, `py\__init__.py` among them); `nosuch` -> exit 2 with the 33 ids | agent | 2026-11-23 |
| SQC-MODE-03 | PASS | selected: renpy, doom; detected: renpy, doom; all: 33 plugins, export warnings only, exit 0 | agent | 2026-11-23 |
| SQC-MODE-04 | NOT RUN | needs a browser | | |
| SQC-MODE-05 | PASS CLI; NOT RUN UI | unknown/all: 15 carved; off: 1 file; nested-traversal with `all`: no CARVE stage (only known formats there). Doc 3.1 describes `all` as "every file ... skipping suffixes an exporter claims"; the code does the opposite on claims (see report) | agent | 2026-11-23 |
| SQC-MODE-06 | PASS CLI; NOT RUN UI | 2 png, the filter warning, `selected_exts [".png"]` | agent | 2026-11-23 |
| SQC-MODE-07 | PASS CLI; NOT RUN UI | needs_decision exit 2, `exist-2`, replace, cancel exit 130 | agent | 2026-11-23 |
| SQC-MODE-08 | PASS 1, 3; NOT RUN 2 | step 3: `[options.godot] encryption_key: secrets are not allowed in the ini`, exit 2 (a file not named startup.ini is checked as a distro: `name must be <os>-<profile>.ini`) | agent | 2026-11-23 |
| SQC-MODE-09 | PASS | identical files; needs_key exit 1 with the hint; with the key extracted | agent | 2026-11-23 |
| SQC-MODE-10 | NOT RUN | needs a browser | | |
| SQC-MODE-11 | PASS | fixture: 7 files, same names and bytes, provenance equal (too small for a worker line). Freedoom (`Test-games\freedoom`, `--carve all`): `[CORE:IDENTIFY] Looking for nested archives in 6,669 extracted file(s) on 1 workers` / `on 16 workers`, `Identified files: n / 6,669` every second, `freedoom1.wad: 500/3109 lumps`...; both runs 4,100 files, every byte equal, provenance equal (6,679 lines); game unchanged | agent | 2026-11-23 |
| SQC-MODE-12 | PASS | 1: doom only, `rpa\images.rpa` kept, 14 files; 2: renpy only, 4 files; 3: exit 2 with the list | agent | 2026-11-23 |
