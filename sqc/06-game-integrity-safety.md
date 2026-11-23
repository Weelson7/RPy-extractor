# 06 Game integrity and data safety

Area code `SAFE`. These are engineering properties (how the features work), not policy: the
game folder is copied from and never written to; only folders carrying the marker
`.viwo-workspace` are ever cleared; names from archives cannot escape the workspace; secrets never
reach the disk.

Hash helper (PowerShell), run before and after each check:
```powershell
function Snap($p) { Get-ChildItem $p -Recurse -File | ForEach-Object { "$($_.FullName)=$((Get-FileHash $_.FullName).Hash)=$($_.LastWriteTimeUtc.Ticks)" } | Sort-Object }
$before = Snap C:\sqc\renpy\game
# ... run the check ...
Compare-Object $before (Snap C:\sqc\renpy\game)      # must print nothing
```

## SQC-SAFE-01 (P0) Game folder byte-identical after extraction, survey and repack

Steps: snapshot `C:\sqc\renpy\game`; run SQC-EXT-04, SQC-SUR-03 on that folder, SQC-RT-02 (the
`roundtrip\rpa` game) and, where it runs, SQC-CAP-02; snapshot again. Repeat the snapshot around
every check of 04, 05 and 09.

Expected: `Compare-Object` prints nothing each time (hash and modification time); the folder has
no new files (no `.viwo-workspace`, no `.extraction_metadata`, no `.trash`, no temp files).

## SQC-SAFE-02 (P0) Workspace or temp inside the game folder is refused

Steps:
1. `viwo extract C:\sqc\renpy\game --workspace C:\sqc\renpy\game\out`
2. `viwo extract C:\sqc\renpy\game --workspace C:\sqc\renpy`
3. UI: top bar `SWITCH`, enter `C:\sqc\renpy\game`, `OPEN`, then extract that game.

Expected: 1: `viwo: refused: the workspace (C:\sqc\renpy\game\out) is inside the game folder
(C:\sqc\renpy\game)`, hint `choose a location outside the game; ViWo never writes there`, exit 3,
`out` not created. 2: `viwo: refused: the game folder (C:\sqc\renpy\game) is inside the workspace
(C:\sqc\renpy)`, hint `choose a workspace that does not hold the game`, exit 3. 3: the error box
`REFUSED FOR SAFETY` with `NEXT ViWo only writes into an empty folder or one it created, never
into a game folder. Pick another folder.`

## SQC-SAFE-03 (P0) Hostile archive names are contained

Steps: `viwo extract C:\sqc\hostile-names\game --workspace C:\sqc\_ws\hostile --on-existing replace`,
then `Get-ChildItem C:\sqc\_ws\hostile -Recurse -Force`, `Get-ChildItem C:\sqc -Filter *escape*
-Recurse`, `Test-Path C:\drive-abs.txt`, `Test-Path C:\abs-root.txt`.

Expected: warnings `game:evil.tar: 1 entr(ies) whose name leads out of the folder skipped`,
`game:evil.tar: 2 link or device member(s) skipped`, `game:evil.zip: 7 member name(s) Windows
cannot write altered (originals recorded for the round trip)`, `game:evil.zip: 3 entr(ies) whose
name leads out of the folder skipped`. Skipped: `../escape-dotdot.txt`,
`..\escape-backslash.txt`, `/abs-root.txt`, `../tar-escape.txt`, the symlink and the hardlink.
Altered and kept inside the workspace: `aux.txt` -> `txt\_aux.txt`, `sub/CON` -> `noext\_CON`,
`trailing-dot.` -> `noext\trailing-dot_`, `trailing-space ` -> `noext\trailing-space_`,
`stream.txt:hidden` -> `txt_hidden\stream.txt_hidden`, `C:drive-rel.txt` ->
`txt\C_drive-rel.txt`, `C:/drive-abs.txt` -> `txt\drive-abs.txt`. Kept as is: `txt\normal.txt`,
`txt\tar-normal.txt`, `txt\画像.txt`. Nothing outside the workspace; no `escape` file anywhere;
the run succeeds (exit 0).

## SQC-SAFE-04 (P0) Only marked folders are cleared

Steps:
1. Create `C:\sqc\_ws\mine` with a file `keep.txt`. `viwo extract C:\sqc\zip-basic\game --workspace C:\sqc\_ws\mine --on-existing replace`
2. `viwo sanitize C:\sqc\_ws\mine --apply`
3. UI: `SWITCH` to `C:\sqc\_ws\mine`; `WORKSPACE > CLEAR TRASH` (or `POST /api/clear-trash`).

Expected: 1: `viwo: refused: C:\sqc\_ws\mine has files and was not created by ViWo`, hint
`choose an empty folder or a ViWo workspace`, exit 3, `keep.txt` alone in the folder. 2: `viwo:
refused: the workspace (...\mine) holds files and is not a ViWo workspace: it may be a game
folder; nothing is written into it`, exit 3. 3: the folder opens as `NOT CREATED BY VIWO`;
clearing answers `...\mine is not a ViWo workspace: nothing in it is moved or deleted` (hint
`extract a game into it first, or open a workspace ViWo made`); nothing is deleted.

## SQC-SAFE-05 (P1) Zip bomb is bounded

Preconditions: `python sqc\fixtures\build_fixtures.py --out C:\sqc --only zip-bomb`.

Steps: extract `C:\sqc\zip-bomb\game` into `C:\sqc\_ws\bomb` while watching the process tree's
private memory (Task Manager "Commit size", or psutil `memory_info().private`) and the free disk.

Expected: private memory of the ViWo processes stays under 300 MB (the working set may show the
1 GiB file's mapped pages); the member is streamed: `bin\zeros.bin` is 1,073,741,824 bytes;
`[CORE:CARVE] Scanning zeros.bin (1024 MB)` is said while the carver reads it; the run ends with
exit 0. Cleanup: delete the workspace.

## SQC-SAFE-06 (P1) A writing job on a locked workspace is `busy`

Steps: start a long extraction into `C:\sqc\_ws\busy` (the zip bomb, or from the UI); while it
runs, from another terminal:
1. `viwo extract C:\sqc\zip-basic\game --workspace C:\sqc\_ws\busy --on-existing replace`
2. `viwo sanitize C:\sqc\_ws\busy --apply`
3. UI: CLEANUP > `SCAN`, then `APPLY SELECTED` on that workspace.

Expected: `.extraction_metadata\lock` exists while the first run lasts. 1 and 2: `viwo: busy:
workspace C:\sqc\_ws\busy is locked by another ViWo process, which still runs`, hint `wait for it
to finish; the lock is ...\.extraction_metadata\lock`, exit 1 (doc 4.3, 12.3: cleanup apply is a
writing job). A plan (`viwo sanitize` without `--apply`) only reads and may run. 3: the error box
`WORKSPACE BUSY` with the link `Open JOBS →`.

## SQC-SAFE-07 (P1) Interrupted run leaves a consistent workspace

Steps: start an extraction from the CLI (the zip bomb), kill it mid-run (close the window or end
the process tree); list `viwo-data\tmp\`; run again with `--on-existing replace`; list
`viwo-data\tmp\` again.

Expected: the second run works; the staging folder of the killed run (`viwo-data\tmp\viwo-<job>-*`,
here 1 GB) is removed at the next start or named in a note; the game folder is unchanged.

## SQC-SAFE-08 (P1) Secrets never on disk

Steps: run SQC-EXT-07 step 2 and SQC-EXT-08 step 4, then search every run record, provenance file,
`viwo-data\logs\*.log` and `viwo-data\` for the key hex (lower and upper case) and for `abab...`.

Expected: no match anywhere; the records show `"aes_key": "<secret>"` and `"encryption_key":
"<secret>"`.

## SQC-SAFE-09 (P0) Memory ceiling: ViWo's own process and its child tools

Steps 1-2 need no game (smoke subset); 3-4 need the real games named and are run from a worktree
at a committed version (`docs/HANDOFF.md`), with the ceiling ON.

Steps:
1. Shipped `startup.ini`: `viwo --verbose info`; then `viwo serve --no-browser` and read the
   first lines of `viwo-data\logs\viwo-<date>.log` (and the activity console).
2. A copy of the ini with `[startup] memory_limit = 0`: `viwo --ini <copy> --verbose info`.
3. Unity IL2CPP (Schedule I): `viwo extract <game> --workspace W`, watching the machine's memory.
4. Cyberpunk 2077 (the `ctf.json` subset): `viwo extract <game> --workspace W` with WolvenKit
   installed, watching the WolvenKit processes' memory.

Expected:
- 1: `[CLI] memory ceiling for ViWo's own process: <n> GB (50 % of the machine)` on stderr and
  `[SERVER] memory ceiling for ViWo's own process: ...` in the server log at start. Where the OS
  layer cannot set it the line reads `no memory ceiling: <why>`, without `--verbose` too (never
  silent when unprotected); with the ceiling set, a plain `viwo info` prints no memory line.
- 2: `[CLI] memory ceiling off ([startup] memory_limit = 0)`.
- 3: the machine stays up and ViWo's process stays under the ceiling. A Unity script whose
  rebuilt layout does not fit its objects is counted and said once: `<n> script(s) have a rebuilt
  layout that does not fit their objects (it asked for the machine's memory): their
  MonoBehaviours are listed without fields, every other script keeps its fields`. The run ends
  with its assets out, not `internal`.
- 4: no WolvenKit process passes its cap (its estimate, 1.5 GB at least); together the caps never
  pass ViWo's share of the machine; the decode says how many parts, and each part its runs, their
  time and their wait for memory. A WolvenKit that reaches its cap fails by itself: one counted
  failure in the slot's warning, the rest goes on. A cap that could not be set is said (`no
  memory cap on this tool: <why>`).

## SQC-SAFE-10 (P0) No workspace inside a game ViWo was given

Steps:
1. Extract `C:\sqc\doom\game` once (SQC-EXT-10): the game is remembered in `viwo-data\games.json`.
2. `viwo extract C:\sqc\zip-basic\game --workspace C:\sqc\doom\game\out --on-existing replace`
3. `viwo sanitize C:\sqc\doom\game --apply` and `viwo repack C:\sqc\_ws\zip --out C:\sqc\doom\game\copy`.

Expected: every one is refused with exit 3 (`the workspace (...\doom\game\out) is inside the game
folder (C:\sqc\doom\game)`, hint naming `games.json`); nothing is created under
`C:\sqc\doom\game` (doc 3.1: a game ViWo was given stays read-only, whichever game the run is
about).

Cleanup: delete `C:\sqc\doom\game\out` if it was created.

## Results

| ID | Result | Notes | Tester | Date |
|----|--------|-------|--------|------|
| SQC-SAFE-01 | PASS (capture part NOT RUN) | version: 1.36.0+search+apk (unreleased). Python snapshot (sha256 + mtime_ns) around every extraction, survey and repack of 04, 05, 09: unchanged every time (renpy, roundtrip, the 9 new-engine fixtures, freedoom). SQC-CAP-02 belongs to the other half | agent | 2026-11-23 |
| SQC-SAFE-02 | PASS 1-2; NOT RUN 3 | both refusals as written, exit 3, `out` not created | agent | 2026-11-23 |
| SQC-SAFE-03 | PASS | the four warnings; 12 files, names as listed; nothing outside; `C:\drive-abs.txt` and `C:\abs-root.txt` absent | agent | 2026-11-23 |
| SQC-SAFE-04 | PASS 1-3 (step 3 through the API) | 1: refused exit 3, only `keep.txt`. 2: refused exit 3. 3: `owned: false`; clear-trash refused with the message; `keep.txt` alone | agent | 2026-11-23 |
| SQC-SAFE-05 | PASS | 52.7 s; peak private 27 MB, working set 1063 MB (mapped pages); zeros.bin 1,073,741,824 bytes; `Scanning zeros.bin (1024 MB)`; exit 0 | agent | 2026-11-23 |
| SQC-SAFE-06 | FAIL step 2; PASS step 1; NOT RUN step 3 | lock file present during the run. 1: `viwo: busy: ... locked by another ViWo process, which still runs`, exit 1. 2: `viwo sanitize --apply` ran anyway (`Applied 0 action(s)`, exit 0): the CLI cleanup apply does not take the workspace lock | agent | 2026-11-23 |
| SQC-SAFE-07 | FAIL | the rerun worked, game unchanged; but the killed run's staging folder `viwo-data\tmp\viwo-20261123-100533-0001-_11imb9e` (1.0 GB) stayed after the next run and nothing named it | agent | 2026-11-23 |
| SQC-SAFE-08 | PASS | no hit for the Unreal key or `ab`x32 in any record, provenance or `viwo-data` file; `<secret>` in the records | agent | 2026-11-23 |
| SQC-SAFE-09 | PASS 1-2; NOT RUN 3-4 | 1: `[CLI] memory ceiling for ViWo's own process: 15.8 GB (50 % of the machine)`; the log holds `[SERVER] memory ceiling ...` at each start; plain `info` prints none. 2: `[CLI] memory ceiling off ([startup] memory_limit = 0)`. 3-4: games not installed | agent | 2026-11-23 |
| SQC-SAFE-10 | FAIL | after extracting `doom\game`: step 2 `viwo extract zip-basic --workspace C:\sqc-a\doom\game\out` succeeded (exit 0) and wrote a workspace inside the Doom game folder; step 3 `viwo repack C:\sqc-a\_ws\zip --out C:\sqc-a\doom\game\copy` (one edit) built and verified a patched copy inside it (exit 0). With a game path the guard compares only with that run's own game, not with `games.json`. `viwo sanitize C:\sqc-a\doom\game --apply` was refused (exit 3, hint naming games.json): the path-less guard works. Both folders removed afterwards | agent | 2026-11-23 |
