# 07 Workspace, sort, trash

Area codes `WS` (02 WORKSPACE) and `SORT` (03 SORT). Fixture: `sort-game`, extracted first:
`viwo extract C:\sqc\sort-game\game --workspace C:\sqc\_ws\sort --on-existing replace`, then in
the UI `WORKSPACE > SWITCH` to `C:\sqc\_ws\sort` > `OPEN`.

Trash layout under the workspace: `.trash\groups\<ext>[_N]\` (whole types), `.trash\items\<rel>`
(single files from 03 SORT), `.trash\merger\` (merger inputs).

## SQC-WS-01 (P0) File types, counts, open folder

Steps: `02 WORKSPACE`.

Expected: `02.A FILE TYPES` lists `png 3`, `wav 2`, `txt 1`, `bin 1`, `jpg 1` with sizes; the stats
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
then type a non-existent path and `OPEN`; then `C:\sqc\_ws\renpy` and `OPEN`.

Expected: the modal `SWITCH WORKSPACE` with the field `FOLDER TO OPEN`; cancel keeps the old path;
a missing folder gives the toast error `Not found`; a valid one updates the top-bar path, 02 and 03
reload for it, and the sort undo history is cleared.

## SQC-SORT-01 (P0) Queue, preview, keep and trash with the mouse

Steps: `03 SORT`; wait for `03.A QUEUE`; select `pic1.png`; `KEEP →`; select `beep1.wav`,
`TRASH`.

Expected: the queue lists 8 items with the kind badges `IMG`, `AUD`, `TXT`, `BIN`; `03.B PREVIEW`
shows the image with its dimensions and size, the audio with a player, `notes.txt` as text, the
bin as `NO PREVIEW` with a hex note; `KEEP` marks `REVIEWED` and advances; `TRASH` moves the file
to `.trash\items\snd\beep1.wav` and advances.

## SQC-SORT-02 (P0) Keyboard: arrows, F2, space, Ctrl+Z

Steps: click on empty space in the view (focus the page body), then press: `↓` twice, `→`
(keep), `←` (trash), `F2`, type `renamed.png`, Enter, `Space` on a wav item, `Ctrl+Z` twice.

Expected: `↓` moves the selection; `→` keeps, `←` trashes; `F2` opens `RENAME ASSET` with the
field `FILE NAME`; the file is renamed on disk and in provenance; `Space` plays/pauses the audio;
each `Ctrl+Z` reverts the last action (rename, then trash) with the toast `UNDO`. The shortcut
legend under the queue lists `NAVIGATE`, `KEEP`, `TRASH`, `RENAME F2`, `PLAY / PAUSE SPACE`,
`UNDO CTRL+Z`.

## SQC-SORT-03 (P1) Keys are ignored while typing in a field or in a modal

Steps: open `RENAME ASSET`, press `←`, `→`, `Space` inside the field; press Escape.

Expected: the caret moves and a space is typed; no keep/trash happens; Escape closes the modal.

## SQC-SORT-04 (P0) Undo is per workspace and survives view changes

Steps: trash two items, go to `02 WORKSPACE` and back to `03 SORT`, `Ctrl+Z`; switch workspace
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

Steps: select the mp4 in 03 SORT; seek inside the player.

Expected: the video plays and seeking works (the server answers `206` with `Content-Range`;
check the browser's network tab).

## SQC-SORT-07 (P2) Empty workspace states

Steps: switch to an empty marked workspace.

Expected: 02 shows `WORKSPACE EMPTY` with `GO TO 01 EXTRACT`; 03 shows `QUEUE EMPTY` with the same
link; no error toast.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-WS-01 | | version: | | |
| SQC-WS-02 | | | | |
| SQC-WS-03 | | | | |
| SQC-WS-04 | | | | |
| SQC-SORT-01 | | | | |
| SQC-SORT-02 | | | | |
| SQC-SORT-03 | | | | |
| SQC-SORT-04 | | | | |
| SQC-SORT-05 | | | | |
| SQC-SORT-06 | | | | |
| SQC-SORT-07 | | | | |
