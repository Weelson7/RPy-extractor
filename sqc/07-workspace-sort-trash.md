# 07 Workspace, sort, trash

Area codes `WS` (WORKSPACE) and `SORT` (SORT). Fixture: `sort-game`, extracted first:
`viwo extract C:\sqc\sort-game\game --workspace C:\sqc\_ws\sort --on-existing replace`, then in
the UI top bar `SWITCH` to `C:\sqc\_ws\sort` > `OPEN`. Each check names its API form (the routes
the view calls; `00-README` "API checks" says how to call them): run that form where no browser
is at hand, and the UI form for the labels, focus and toasts.

Trash layout under the workspace: `.trash\groups\<ext>[_N]\` (whole types),
`.trash\items\<ext>\<file>` (single files from SORT and the sanitizer), `.trash\merger\` (merger
inputs, SQC-MERGE-04).

## SQC-WS-01 (P0) File types, counts, open folder

Steps: `WORKSPACE`. API form: `POST /api/workspace {"path": "C:\\sqc\\_ws\\sort"}`, `GET
/api/status`.

Expected: `FILE TYPES` lists `.bin 1`, `.jpg 1`, `.png 3`, `.txt 1`, `.wav 2` (columns `TYPE`,
`KEPT`, `IN TRASH`, `STATE`, `ACTIONS`; state `KEPT`); the stats row shows `TYPES 5`, `KEPT
FILES 8`, `IN TRASH 0`, `SELECTED 0`; `OPEN FOLDER` opens the workspace in Explorer. API: `owned:
true`; status `kept {"bin": 1, "jpg": 1, "png": 3, "txt": 1, "wav": 2}`, `totalKept 8`,
`totalTrashed 0`.

## SQC-WS-02 (P0) Trash a type, restore it, delete it forever

Steps:
1. Row `.bin` > `TRASH`.
2. Row `.bin` > `RESTORE`.
3. `TRASH` again, then `DELETE` > confirm `DELETE FOREVER`.

API form: `POST /api/trash`, `/api/restore`, `/api/delete` with `{"folder": "bin"}`.

Expected: 1: `blob.bin` moves to `.trash\groups\bin\`; toast/message `Moved bin to trash as bin (1
files)`; `IN TRASH 1`, state `IN TRASH`. 2: `Restored bin from trash as bin`, back in `bin\`. 3:
the modal `DELETE TRASHED GROUP` (`Permanently delete every trashed .bin file? This cannot be
undone.`); afterwards `Permanently deleted the trashed bin (1 files)`, no `blob.bin` anywhere,
the `.bin` row gone.

## SQC-WS-03 (P0) KEEP ONLY SELECTED and CLEAR TRASH

Steps:
1. Tick `.png` and `.wav`, click `KEEP ONLY SELECTED` > `KEEP ONLY THESE`.
2. `CLEAR TRASH` > `CLEAR FOREVER`.

API form: `POST /api/keep-selected {"selectedExts": ["png", "wav"]}`, `POST /api/clear-trash {}`.

Expected: 1: the modal `KEEP ONLY SELECTED TYPES` names the kept types and the count moved; then
`Kept 2 types, moved 2 to trash` (`.jpg`, `.txt` in `.trash\groups\`). 2: `CLEAR TRASH`
(`Permanently delete all 2 trashed file(s)?`); `.trash\` is emptied (`cleared 2`); the marker and
`.extraction_metadata\` remain; `IN TRASH 0`.

## SQC-WS-04 (P1) Switch workspace dialog

Steps: top bar `SWITCH`; `BROWSE` picks a folder with the native dialog; `CANCEL`; then empty the
field and `OPEN`; the unchanged path and `OPEN`; a non-existent path and `OPEN`; then
`C:\sqc\_ws\renpy` and `OPEN`.

API form: `POST /api/workspace` with `{"path": ""}`, a missing folder, a real one.

Expected: the modal `SWITCH WORKSPACE` with the field `FOLDER TO OPEN OR CONVERT`, the `ACTIVE`
path with its badge (`VIWO WORKSPACE` or `NOT CREATED BY VIWO`) and the actions `CANCEL`, `CONVERT
INTO WORKSPACE`, `OPEN`; cancel keeps the old path; an empty field gives the toast `Enter a
folder first.`; the unchanged path gives `That folder is already the active workspace.`; a
missing folder gives an error toast with the server's message (`Folder not found: <path>`), which
stays until `DISMISS`; a valid one shows `OPENING…` on the top-bar chip, then the new path;
WORKSPACE and SORT reload for it and the sort undo history is cleared. A folder ViWo did not
create opens with the note that CONVERT INTO WORKSPACE makes it one. API: empty -> `give the
workspace as an absolute folder` (`not_found`); missing -> `Folder not found: ...` (`not_found`);
real -> `success`, `owned: true`.

## SQC-WS-05 (P0) CONVERT INTO WORKSPACE

Preconditions: a folder of your own files that ViWo did not create, `C:\sqc\_own` with
`a\pic.png`, `a\b\song.wav`, `notes.txt` and a second copy of the picture as `copy\pic.png`.

Steps:
1. `SWITCH`, type `C:\sqc\_own`, `CONVERT INTO WORKSPACE`; read the dialog; `CANCEL`.
2. The same, then `CONVERT`.
3. The same on `C:\`, then on your home folder.
4. The same on `C:\sqc\_own` again.

API form: `POST /api/workspace/adopt {"path": ...}` (preview) and `{"path": ..., "confirm": true}`.

Expected:
- 1: the dialog says `<n> of <m> file(s) move into <g> group(s) by type (...)` and `Nothing is
  deleted.`; after `CANCEL` nothing moved. API preview: `owned: false`, `files 4`, `moves 4`,
  `groups ["png", "txt", "wav"]`, `refused: ""`.
- 2: the chip shows `CONVERTING…`; toast `Workspace: C:\sqc\_own`, `4 file(s) moved into 3
  group(s).`; `png\pic.png` and `png\pic__1.png` (both copies kept), `wav\song.wav`,
  `txt\notes.txt`; `a\`, `a\b\`, `copy\` are gone; the marker exists;
  `.extraction_metadata\provenance.jsonl` has one line per file with `"kind": "adopted"`, its
  original path (`"member": "a/b/song.wav"`), sha256 and size; an extraction into it is no longer
  refused.
- 3: `a drive root or the home folder is never converted` (hint `pick a folder of your own
  files`), as an error toast that stays until `DISMISS`; nothing is walked or moved.
- 4: no confirmation (it is a workspace already, `owned: true`, `moves 0`); it becomes the active
  workspace and no file moves.

## SQC-WS-06 (P0) Group RESTORE and DELETE cover the files trashed in SORT

Steps:
1. The fixture workspace, extracted again. SORT: trash `png\pic1.png` and `png\pic2.png`.
2. WORKSPACE: read the `.png` row; `RESTORE` on it.
3. SORT: trash the two again; WORKSPACE `.png` > `TRASH` (the whole type), then `RESTORE`.
4. SORT: trash one png; WORKSPACE `.png` > `DELETE` > confirm.

API form: `POST /api/sort-trash {"path": "png/pic1.png"}`, `GET /api/status`, `POST
/api/restore {"folder": "png"}`, `POST /api/delete {"folder": "png"}`.

Expected: 2: the row reads `KEPT 1`, `IN TRASH 2`, `PARTLY TRASHED`; `RESTORE` answers `restored 2
file(s) trashed in SORT` (never `Nothing of png in the trash`): both are back in `png\`, each at
its own place, their provenance entries following. 3: the newest trashed version of the group
and the files trashed in SORT all come back. 4: the confirmation names the type; afterwards
`Permanently deleted the trashed png (1 files)` and nothing of png is left under `.trash\`
(`groups\` and `items\`); the other types are untouched.

## SQC-SORT-01 (P0) Queue, preview, keep and trash with the mouse

Steps: `SORT`; wait for `QUEUE`; select `pic1.png`; `KEEP`; select `beep1.wav`, `TRASH`.

API form: `GET /api/assets-window?offset=0&limit=60&types=`, `GET
/api/assets-window-preview?path=png/pic3.png`, `POST /api/sort-keep {"path": "png/pic1.png"}`,
`POST /api/sort-trash {"path": "wav/beep1.wav"}`.

Expected: the queue lists 8 items with the kind badges `IMG`, `AUD`, `TXT`, `BIN`; `PREVIEW` shows
the image with its dimensions and size, the audio with a player, `notes.txt` as text, the bin as
`NO PREVIEW` with a hex note; `KEEP` marks `REVIEWED` and advances; `TRASH` moves the file to
`.trash\items\wav\beep1.wav` and advances. API: `total 8`, `typeCounts {"image": 4, "audio": 2,
"text": 1, "other": 1}`; the preview answers `type: image`, `url: /preview/png/pic3.png`.

## SQC-SORT-02 (P0) Keyboard: arrows, F2, space, Ctrl+Z

Steps: click on empty space in the view, then press: `↓` twice, `→` (keep), `←` (trash), `F2`,
type `renamed.png`, Enter, `Space` on a wav item, `Ctrl+Z` three times.

API form: `POST /api/sort-rename {"path": "png/pic2.png", "newName": "renamed.png"}`, then `POST
/api/sort-undo {}` three times.

Expected: `↓` moves the selection; `→` keeps, `←` trashes; `F2` opens `RENAME ASSET` with the
field `FILE NAME`; the file is renamed on disk and in provenance; `Space` plays/pauses the audio;
each `Ctrl+Z` reverts the last action (rename, then trash, then keep) with the toast `Undid
<ACTION>.`. The legend under the queue lists `NAVIGATE`, `KEEP`, `TRASH`, `RENAME`, `PLAY /
PAUSE`, `UNDO` with their keys. API: the undos answer `undone: rename`, `undone: trash`, `undone:
keep`, and the 8 files are back as they were.

## SQC-SORT-03 (P1) Keys are ignored while typing in a field or in a modal

Steps: open `RENAME ASSET`, press `←`, `→`, `Space` inside the field; press Escape.

Expected: the caret moves and a space is typed; no keep/trash happens; Escape closes the modal.

## SQC-SORT-04 (P0) Undo is per workspace and survives view changes

Steps: trash two items, go to `WORKSPACE` and back to `SORT`, `Ctrl+Z`; switch workspace and
back, `Ctrl+Z`.

Expected: the first undo restores the last trashed item; after switching workspaces the history
is empty (toast `Nothing to undo`).

## SQC-SORT-05 (P1) Pagination and SAVE REMAINING

Steps: a workspace with more than 60 files (Freedoom, or `C:\sqc\doom\game` with
`doom.raw_lumps=true` and copies); `‹` / `›` page buttons; `SAVE REMAINING…` >
`DESTINATION FOLDER` = `C:\sqc\_saved` > `THIS PAGE (n)` or `ALL REMAINING (n)`.

API form: `POST /api/save-remaining-assets {"all": true, "destinationPath": "C:\\sqc\\_saved"}`,
first with the folder absent, then present.

Expected: pages of 60 with the counter; the modal `SAVE REMAINING FILES` (tag `// MOVE OUT`) says
the queued files move out of the workspace into an existing folder, sub-folders kept, trashed
files staying in the trash; afterwards the toast `Moved <n> file(s) to C:\sqc\_saved.`, the files
are under `<ext>\` there and no longer in the workspace. API: a missing destination answers
`Destination folder does not exist: C:\sqc\_saved` (`invalid_request`); an existing one `moved
<n>`, `skipped 0`, `failures []`.

## SQC-SORT-06 (P1) Video preview with range requests

Preconditions: `merger` fixture made with ffmpeg (`03_walk.mp4`), extracted into a workspace.

Steps: select the mp4 in SORT; seek inside the player. API form: the preview's `url` with
`Range: bytes=100-199`.

Expected: the video plays and seeking works; the server answers `206` with `Content-Range: bytes
100-199/<size>` and 100 bytes.

## SQC-SORT-07 (P2) Empty workspace states

Steps: switch to an empty marked workspace.

Expected: WORKSPACE shows `WORKSPACE EMPTY` with `GO TO EXTRACT`; SORT shows `QUEUE EMPTY` with the
same link; no error toast. API: status `kept {}`, `totalKept 0`.

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
| SQC-WS-01 | PASS API; NOT RUN UI | version: 1.36.0+search+apk (unreleased). Status as written | agent | 2026-11-23 |
| SQC-WS-02 | PASS API; NOT RUN UI | the three messages as written; `.trash\groups\bin\blob.bin`, then gone | agent | 2026-11-23 |
| SQC-WS-03 | PASS API; NOT RUN UI | `Kept 2 types, moved 2 to trash`; `cleared 2`; marker kept | agent | 2026-11-23 |
| SQC-WS-04 | PASS API; NOT RUN UI | the three answers as written | agent | 2026-11-23 |
| SQC-WS-05 | PASS API; NOT RUN UI | preview 4/4/3 groups; convert `moved 4`, `pic__1.png` for the copy, provenance `adopted` lines; `C:\` and home refused with the sentence; again: `owned: true`, `moves 0` | agent | 2026-11-23 |
| SQC-WS-06 | PASS API; NOT RUN UI | `kept 1`, `trashed 2`; `restored 2 file(s) trashed in SORT`; delete `(1 files)`, nothing png under `.trash` | agent | 2026-11-23 |
| SQC-SORT-01 | PASS API; NOT RUN UI | 8 items, the counts; keep; trash to `.trash\items\wav\beep1.wav` | agent | 2026-11-23 |
| SQC-SORT-02 | PASS API; NOT RUN UI | rename to `png/renamed.png`; undo rename, trash, keep; 8 files back | agent | 2026-11-23 |
| SQC-SORT-03 | NOT RUN | needs a browser | | |
| SQC-SORT-04 | NOT RUN | needs a browser | | |
| SQC-SORT-05 | PASS API; NOT RUN UI | missing folder refused with the message; existing: `moved 7`, the files under their groups, the workspace left with its marker and metadata only | agent | 2026-11-23 |
| SQC-SORT-06 | PASS API; NOT RUN UI | `206`, `Content-Range: bytes 100-199/23487`, 100 bytes | agent | 2026-11-23 |
| SQC-SORT-07 | PASS API; NOT RUN UI | status `kept {}`, `totalKept 0` | agent | 2026-11-23 |
| SQC-SORT-08 | NOT RUN | needs a browser, audio playback and a file over 20 MB | | |
