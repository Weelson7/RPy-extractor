# 07 Workspace, sort, trash

Area codes `WS` (WORKSPACE) and `SORT` (SORT). Fixture: `sort-game`, extracted first:
`viwo extract C:\sqc\sort-game\game --workspace C:\sqc\_ws\sort --on-existing replace`, then in
the UI `WORKSPACE > SWITCH` to `C:\sqc\_ws\sort` > `OPEN`.

Trash layout under the workspace: `.trash\groups\<ext>[_N]\` (whole types), `.trash\items\<rel>`
(single files from SORT), `.trash\merger\` (merger inputs).

## SQC-WS-01 (P0) File types, counts, open folder

Steps: `WORKSPACE`.

Expected: `FILE TYPES` lists `png 3`, `wav 2`, `txt 1`, `bin 1`, `jpg 1` with sizes; the stats
row shows `FILES 8`, `TYPES 5`, `IN TRASH 0`; `OPEN FOLDER` opens the workspace in Explorer
(toast `Opened in your file manager.`).

## SQC-WS-02 (P0) Trash a type, restore it, delete it forever

Steps:
1. Row `bin` > `TRASH`.
2. Row `bin` (now in the trash section) > `RESTORE`.
3. `TRASH` again, then `DELETE` > confirm `DELETE FOREVER`.

Expected: 1: `blob.bin` moves to `.trash\groups\bin\`; stats `IN TRASH 1`; the game folder is
untouched. 2: it is back in `bin\`. 3: the confirm modal names the type and count; after
confirming the files are gone from disk and the `bin` row disappears.

## SQC-WS-03 (P0) KEEP ONLY SELECTED and CLEAR TRASH

Steps:
1. Tick `png` and `wav`, click `KEEP ONLY SELECTED`.
2. `CLEAR TRASH` > confirm `CLEAR FOREVER`.

Expected: 1: `txt`, `jpg` (and `bin` if restored) move to `.trash\groups\`; a toast reports the
count. 2: `.trash\groups\` is emptied; the marker and `.extraction_metadata\` remain; `IN TRASH 0`.

## SQC-WS-04 (P1) Switch workspace dialog

Steps: top bar `WORKSPACE > SWITCH`; `BROWSE` picks a folder with the native dialog; `CANCEL`;
then empty the field and `OPEN`; the unchanged path and `OPEN`; a non-existent path and `OPEN`;
then `C:\sqc\_ws\renpy` and `OPEN`.

Expected: the modal `SWITCH WORKSPACE` with the field `FOLDER TO OPEN OR CONVERT`, the `ACTIVE`
path with its badge (`VIWO WORKSPACE` or `NOT CREATED BY VIWO`) and the actions `CANCEL`, `CONVERT
INTO WORKSPACE`, `OPEN`; cancel keeps the old path; an empty field gives the toast `Enter a
folder first.`; the unchanged path gives `That folder is already the active workspace.`; a
missing folder gives an error toast with the server's message, which stays until `DISMISS`; a
valid one shows `OPENING…` on the top-bar chip, then the new path, WORKSPACE and SORT reload for
it, and the sort undo history is cleared. A folder ViWo did not create opens with the note `Not
created by ViWo: CONVERT INTO WORKSPACE makes it one; extraction refuses it until then unless it
is empty.`

## SQC-WS-05 (P0) CONVERT INTO WORKSPACE

Preconditions: a folder of your own files that ViWo did not create, for example `C:\sqc\_own`
with `a\pic.png`, `a\b\song.wav`, `notes.txt` and a second copy of the picture as `copy\pic.png`.

Steps:
1. `WORKSPACE > SWITCH`, type `C:\sqc\_own`, `CONVERT INTO WORKSPACE`; read the dialog; `CANCEL`.
2. The same, then `CONVERT`.
3. The same on `C:\`, then on your home folder.
4. The same on `C:\sqc\_own` again.

Expected:
- 1: the dialog `CONVERT INTO WORKSPACE` says `<n> of <m> file(s) move into <g> group(s) by type
  (...)` and `Nothing is deleted.`; after `CANCEL` the folder is unchanged and the active
  workspace is the old one.
- 2: the top-bar chip shows `CONVERTING…`; toast `Workspace: C:\sqc\_own`, `<n> file(s) moved
  into <g> group(s).`; every file sits in the group of its type (`png\`, `wav\`, `txt\`), both
  copies of the picture kept; `a\`, `a\b\` and `copy\` (emptied by the moves) are gone; the
  workspace marker exists; `.extraction_metadata\provenance.jsonl` has one line per file with
  `kind: adopted`, its original path, sha256 and size; WORKSPACE lists the groups; an extraction
  into it is no longer refused.
- 3: an error toast `a drive root or the home folder is never converted` (hint `pick a folder of
  your own files`) that stays until `DISMISS`; nothing is walked or moved.
- 4: no confirmation dialog (it is a workspace already); it becomes the active workspace and no
  file moves.

## SQC-WS-06 (P0) Group RESTORE and DELETE cover the files trashed in SORT

Steps:
1. The fixture workspace, extracted again. SORT: trash two `png` files, one by one.
2. WORKSPACE: read the `png` row's trashed count; `RESTORE` on it.
3. SORT: trash the two again; WORKSPACE row `png` > `TRASH` (the whole type), then `RESTORE`.
4. SORT: trash one `png`; WORKSPACE row `png` > `DELETE` > confirm.

Expected: 2: the count includes the two files; `RESTORE` never answers `No trashed folder`: both
are back in `png\`, each at its own place, their provenance entries following; `IN TRASH 0`. 3:
the newest trashed version of the group and the two files trashed in SORT all come back. 4: the
confirmation names the type and the count; afterwards nothing of `png` is left under `.trash\`
(`groups\` and `items\`), as the confirmation said; the other types are untouched.

## SQC-SORT-01 (P0) Queue, preview, keep and trash with the mouse

Steps: `SORT`; wait for `QUEUE`; select `pic1.png`; `KEEP →`; select `beep1.wav`,
`TRASH`.

Expected: the queue lists 8 items with the kind badges `IMG`, `AUD`, `TXT`, `BIN`; `PREVIEW`
shows the image with its dimensions and size, the audio with a player, `notes.txt` as text, the
bin as `NO PREVIEW` with a hex note; `KEEP` marks `REVIEWED` and advances; `TRASH` moves the file
to `.trash\items\snd\beep1.wav` and advances.

## SQC-SORT-02 (P0) Keyboard: arrows, F2, space, Ctrl+Z

Steps: click on empty space in the view (focus the page body), then press: `↓` twice, `→`
(keep), `←` (trash), `F2`, type `renamed.png`, Enter, `Space` on a wav item, `Ctrl+Z` twice.

Expected: `↓` moves the selection; `→` keeps, `←` trashes; `F2` opens `RENAME ASSET` with the
field `FILE NAME`; the file is renamed on disk and in provenance; `Space` plays/pauses the audio;
each `Ctrl+Z` reverts the last action (rename, then trash) with the toast `Undid <ACTION>.`. The shortcut
legend under the queue lists `NAVIGATE`, `KEEP`, `TRASH`, `RENAME F2`, `PLAY / PAUSE SPACE`,
`UNDO CTRL+Z`.

## SQC-SORT-03 (P1) Keys are ignored while typing in a field or in a modal

Steps: open `RENAME ASSET`, press `←`, `→`, `Space` inside the field; press Escape.

Expected: the caret moves and a space is typed; no keep/trash happens; Escape closes the modal.

## SQC-SORT-04 (P0) Undo is per workspace and survives view changes

Steps: trash two items, go to `WORKSPACE` and back to `SORT`, `Ctrl+Z`; switch workspace
and back, `Ctrl+Z`.

Expected: the first undo restores the last trashed item; after switching workspaces the history
is empty (toast `Nothing to undo`).

## SQC-SORT-05 (P1) Pagination and SAVE REMAINING

Steps: a workspace with more than 60 files (extract `C:\sqc\doom\game`); `‹` / `›` page buttons;
`SAVE REMAINING…` > `DESTINATION FOLDER` = `C:\sqc\_saved` > confirm.

Expected: pages of 60 with the counter; `SAVE REMAINING FILES` copies every not-reviewed file to
the destination keeping the extension folders; the workspace is unchanged.

## SQC-SORT-06 (P1) Video preview with range requests

Preconditions: `merger` fixture with ffmpeg (`03_walk.mp4`); extract it into a workspace.

Steps: select the mp4 in SORT; seek inside the player.

Expected: the video plays and seeking works (the server answers `206` with `Content-Range`;
check the browser's network tab).

## SQC-SORT-07 (P2) Empty workspace states

Steps: switch to an empty marked workspace.

Expected: WORKSPACE shows `WORKSPACE EMPTY` with `GO TO EXTRACT`; SORT shows `QUEUE EMPTY` with the same
link; no error toast.

## SQC-SORT-08 (P0) A preview never holds the file it shows

Preconditions: a workspace with a WAV and an audio file over 20 MB (a game with a long music
track, or a folder holding one converted with SQC-WS-05).

Steps:
1. SORT: select the WAV, `Space`, and while it plays `←` (trash).
2. `Ctrl+Z`; play it again; `F2` and rename it while it plays.
3. Select the file over 20 MB (no waveform is drawn for it); trash it; `Ctrl+Z`; rename it.
4. Play a file, then WORKSPACE: `TRASH` its whole type; `RESTORE`; then CLEANUP: `SCAN`, `APPLY
   SELECTED`.

Expected: every move succeeds at once: the preview stops, the file moves, no error toast, no `in
use` and no Windows error 32 in the activity console. When another program really holds the file
(a player, an editor), the error names that file and says it is `in use by another program (a
preview playing it, a player or an editor)`; it never names the whole workspace folder.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-WS-01 | | version: | | |
| SQC-WS-02 | | | | |
| SQC-WS-03 | | | | |
| SQC-WS-04 | | | | |
| SQC-WS-05 | NOT RUN | added at 1.20.40 | | |
| SQC-WS-06 | NOT RUN | added at 1.20.40 | | |
| SQC-SORT-01 | | | | |
| SQC-SORT-02 | | | | |
| SQC-SORT-03 | | | | |
| SQC-SORT-04 | | | | |
| SQC-SORT-05 | | | | |
| SQC-SORT-06 | | | | |
| SQC-SORT-07 | | | | |
| SQC-SORT-08 | NOT RUN | added at 1.20.40 | | |
