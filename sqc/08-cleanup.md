# 08 Cleanup (sanitizer)

Area code `CLEAN`. Fixtures: `dirty-workspace` (`C:\sqc\dirty-workspace\ws`, already a marked
workspace with an empty file, `Thumbs.db`, a `.import` junk file, a PNG named `.jpg`, two exact
duplicates of `png\copy.png` (`jpg\photo.jpg`, `png\ok.png`), a truncated PNG) and `phases`
(extract `C:\sqc\phases\game` into `C:\sqc\_ws\phases`: a sequence with gaps, a WAV, an AVI).
Recipes (`viwo sanitize --recipe`, CLEANUP > SCAN): `phase1-safe` (default: `core.junk`,
`core.zero_byte`, `renpy.cache`, `core.extension`, `core.duplicate`, `core.health`; lossless,
nothing deleted), `phase2-convert` (open-format copies), `phase2-replace` (open formats, originals
to the trash), `phase3-audio` (WAV to Opus, LOSSY), `phase3-video` (to H.264 MP4, LOSSY),
`phase3-renumber` (sequences renumbered). The lossy ones run only when named. API form of the
view: `GET /api/sanitizer/recipes`, `POST /api/sanitizer/plan {recipeId}`, `/apply {planId,
accept}`, `/undo {undoToken}` (each a `cleanup` job).

## SQC-CLEAN-01 (P0) Scan, findings by rule, apply selected, undo (UI)

Steps:
1. `SWITCH` to `C:\sqc\dirty-workspace\ws`.
2. `CLEANUP`: recipe `Safe cleanup` (badges `LOSSLESS`, `NOTHING IS DELETED`), click `SCAN`.
3. In `FINDINGS` untick the two duplicates; click `APPLY SELECTED`.
4. `LAST CLEANUP > UNDO THIS CLEANUP`.

Expected:
- 2: `FINDINGS` shows `SCANNING…` while the scan runs; findings grouped `EMPTY FILES (1)`, `ENGINE /
  OS JUNK (2)`, `WRONG EXTENSION (1)` (`jpg/other.jpg` is really `.png`, rename to `other.png`),
  `EXACT DUPLICATES (2)` (`same bytes as png/copy.png`), `HEALTH (1)` (`png truncated or
  corrupt`, `REPORT ONLY`); stats `SCANNED 8`, `FINDINGS 7`, `SELECTED 6`; `WHAT EACH RULE DOES`
  explains each rule.
- 3: `LAST CLEANUP` with `UNDO AVAILABLE`: `APPLIED 4` (`TO TRASH 3`, `RENAMED 1`); the
  duplicates stay; the trashed files are in `.trash\items\<ext>\`; `jpg\other.png` exists;
  `provenance.jsonl` has the rename.
- 4: every file is back with its original name; a second scan finds the same 7 findings.

API form: plan answers `planId`, `scanned 8`, `total 7`; apply with `accept` = the indexes of the
six actionable findings minus the duplicates answers `applied 4`, `trashed 3`, the `moved` list,
`undoToken`; undo answers `restored 4`, `notRestored []`.

## SQC-CLEAN-02 (P0) CLI plan, apply, undo

Steps:
1. `viwo sanitize C:\sqc\dirty-workspace\ws`
2. `viwo sanitize C:\sqc\dirty-workspace\ws --apply`
3. `viwo sanitize C:\sqc\dirty-workspace\ws --undo <the id step 2 printed>`
4. `viwo --json sanitize C:\sqc\dirty-workspace\ws`

Expected: 1: one line per finding (`<action>  <path>  (<message>)`: `trash db/Thumbs.db (engine/OS
junk (.db))`, `rename jpg/other.jpg (is really .png)`, `none png/cut.png (png truncated or
corrupt)`, `trash txt/empty.txt (empty file)`, `trash jpg/photo.jpg (same bytes as
png/copy.png)`...), then `7 finding(s) in 8 file(s), plan <id> (phase1-safe)`; nothing changed.
2: the same list, then `Applied 6 action(s); undo with --undo <id>`; the journal is
`<ws>\.sanitizer\journal\<id>.json`, the trash `.trash\items\...`. 3: `Restored 6 file(s), removed
0 made`; every file back. 4: an envelope whose `data` holds `planId`, `recipeId`, `scanned`,
`findings` (each `rule`, `path`, `message`, `action`, `severity`, `lossy`, `size`, `index`, `to`
for a rename), `warnings`, `total`, `offset`, `limit`.

## SQC-CLEAN-03 (P1) Applying a stale plan is refused

Steps:
1. Plan (UI `SCAN` or `POST /api/sanitizer/plan`); change a file the plan acts on
   (`Set-Content <ws>\txt\empty.txt "now it has content"`); `APPLY SELECTED` with that plan.
2. Plan again; change the file the duplicates are measured against (`png\copy.png`, append one
   byte); apply that plan.

Expected: 1: `plan is stale: txt/empty.txt changed; scan again` (error box `CHECK YOUR INPUT`),
nothing is moved; `SCAN AGAIN` then works. 2: the same refusal naming `png/copy.png`: the two
duplicates are no longer duplicates and must not be trashed.

## SQC-CLEAN-04 (P1) Health findings are never applied

Steps: scan; tick everything; apply (API: `accept` = every index, the health one included).

Expected: the truncated PNG is listed under `HEALTH` with `REPORT ONLY` and has no checkbox; the
apply acts on the 6 others (`applied 6`); `png\cut.png` is neither moved nor renamed.

## SQC-CLEAN-05 (P1) Clean workspace and empty workspace

Steps: scan a freshly extracted `zip-basic` workspace; scan an empty marked workspace (CLI and UI).

Expected: CLI `0 finding(s) in 5 file(s), plan <id> (phase1-safe)` and `0 finding(s) in 0
file(s)`. UI: `WORKSPACE IS CLEAN` (`APPLY SELECTED` disabled); `WORKSPACE EMPTY` with `GO TO
EXTRACT`.

## SQC-CLEAN-06 (P1) Undo with a trashed file gone, undo twice

Steps: apply; delete `.trash\items\db\Thumbs.db` by hand; undo; undo the same token again.

Expected: the first undo restores what it can and names the rest (`restored 5`, `notRestored
[".trash/items/db/Thumbs.db"]`), it does not fail; the second restores nothing and names the same
file again. A token whose journal was fully undone answers `viwo: not_found: nothing to undo for
<id>` (exit 1).

## SQC-CLEAN-07 (P1) A folder ViWo did not make is refused

Steps: `viwo sanitize C:\sqc\_ws\mine` (the folder of SQC-SAFE-04).

Expected: `refused: the workspace (...\mine) holds files and is not a ViWo workspace: it may be a
game folder; nothing is written into it`, hint `without the game's path ViWo cannot tell a game
from your files: ...`, exit 3.

## SQC-CLEAN-08 (P1) Phases 2 and 3 with the pinned ffmpeg

Steps:
1. `viwo sanitize C:\sqc\_ws\carve --recipe phase2-convert` (plan), then `--apply` on a copy.
2. `viwo sanitize C:\sqc\_ws\phases --recipe phase3-audio --apply`
3. `viwo sanitize C:\sqc\_ws\phases --recipe phase3-video --apply`
4. `viwo sanitize C:\sqc\_ws\phases --recipe phase3-renumber --apply`, then `--undo <id>`.
5. `ffprobe` the outputs.

Expected:
- 1: `convert bnk/... (BNK to an open format by decode.audio (vgmstream-cli), lossless)`, the same
  for FSB and WEM; `3 finding(s) in 18 file(s)`. The carve fixture's audio files are signature
  stubs: the apply converts none (`Applied 0 action(s)`) and says each one in a `viwo: warning:
  <file>: ffmpeg-decode: (after vgmstream-cli failed: ...)` line.
- 2: `transcode wav/tone.wav (WAV to Opus 128 kb/s in Ogg: LOSSY, the original stays)`, `transcode
  wav/tone.wav -> ogg/tone.ogg`, `Applied 1 action(s)`; `wav\tone.wav` stays.
- 3: `transcode avi/clip.avi (AVI to H.264 / AAC MP4: LOSSY, the original stays)`, `->
  mp4/clip.mp4`.
- 4: `rename png/frame1.png (sequence frame#: number 1 of 3)` and the two others; `frame01.png`,
  `frame02.png`, `frame03.png`; the undo answers `Restored 3 file(s), removed 0 made` and the old
  names are back.
- 5: `ogg\tone.ogg` is `opus`, `mp4\clip.mp4` is `h264`.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-CLEAN-01 | PASS API; NOT RUN UI | version: 1.36.0+search+apk (unreleased). Plan `scanned 8`, `total 7`; apply without duplicates `applied 4`, `trashed 3`; undo `restored 4` | agent | 2026-11-23 |
| SQC-CLEAN-02 | PASS | 7 findings; `Applied 6 action(s); undo with --undo 20261123-095404-4dcada`; `Restored 6 file(s), removed 0 made`; JSON keys as written | agent | 2026-11-23 |
| SQC-CLEAN-03 | PASS step 1; FAIL step 2 (API) | 1: `plan is stale: txt/empty.txt changed; scan again`, nothing moved. 2: with `png/copy.png` changed after the plan, the apply went through (`applied 6`): `jpg/photo.jpg` and `png/ok.png` went to the trash as duplicates of a file that no longer matched them | agent | 2026-11-23 |
| SQC-CLEAN-04 | PASS API; NOT RUN UI | every index accepted: `applied 6`, `cut.png` in place | agent | 2026-11-23 |
| SQC-CLEAN-05 | PASS CLI; NOT RUN UI | `0 finding(s) in 5 file(s)`; `0 finding(s) in 0 file(s)` | agent | 2026-11-23 |
| SQC-CLEAN-06 | PASS | `restored 5`, `notRestored [".trash/items/db/Thumbs.db"]`; again: `restored 0`, the same `notRestored`; a fully undone CLI token: `not_found: nothing to undo for <id>`, exit 1 | agent | 2026-11-23 |
| SQC-CLEAN-07 | PASS | refused, exit 3, the message and hint | agent | 2026-11-23 |
| SQC-CLEAN-08 | PASS | pinned ffmpeg 6.1.1 through `real-tools.ini`: `ogg/tone.ogg` opus, `mp4/clip.mp4` h264; renumber and its undo; the stub conversions said per file (`Applied 0 action(s)` + 3 warnings) | agent | 2026-11-23 |
