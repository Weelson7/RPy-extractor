# 21 Content search (`viwo search`, `POST /api/search`, SEARCH)

Area code `SE`. Contract doc 6.7 (`viwo/core/search.py`, `viwo/core/search_query.py`,
`viwo/cli_search.py`, `viwo/api/handlers_search.py`, `viwo/web/js/views/search.js`). A search only
reads; it takes no workspace lock, needs no feature switch and runs nothing. SEARCH is a view of the
STATIC arm. PowerShell splits an unquoted comma list into several arguments: quote it
(`--widths "1,2"`).

Inputs, built once (no fixture builder needed):

```powershell
python -c "import struct,pathlib as P;o=P.Path(r'C:\sqc\se');o.mkdir(parents=True,exist_ok=True);(o/'a.txt').write_bytes(b'xx Health yy HEALTH zz');(o/'b.bin').write_bytes(b'\0'*7+'Health'.encode('utf-16-le')+b'\0'*5);(o/'c.bin').write_bytes(b'AA'+struct.pack('<I',100)+b'BB'+struct.pack('>H',100)+struct.pack('<f',1.5));d=bytearray(9<<20);d[(8<<20)-3:(8<<20)+7]=b'BOUNDARY!!';(o/'big.bin').write_bytes(bytes(d))"
```

`C:\sqc\se` then holds `a.txt` (22 bytes), `b.bin` (`Health` in UTF-16LE at offset 7), `c.bin`
(100 as u32le at 2, 100 as u16be at 8, 1.5 as f32le at 10) and `big.bin` (9 MiB, `BOUNDARY!!` at
`0x7ffffd`, across the first 8 MiB chunk). The executable is `<repo>\Test-games\chocolate-doom\engine\chocolate-doom.exe`
(games.md, Chocolate Doom 3.1.0, 32-bit PE).

## SQC-SE-01 (P0) Text: UTF-8 and UTF-16, case, the report said

Steps:
1. `viwo search C:\sqc\se --text Health`
2. `viwo search C:\sqc\se --text health -i --quiet`

Expected:
- 1: stderr `Searching 4 file(s), 9.4 MB in C:\sqc\se (folder): text 'Health' as utf-8, utf-16le, utf-16be`
  and `Searched 4 of 4 file(s), 9.4 MB in 0 s: 3 hit(s) in 2 file(s)`; the warning
  `the results were not saved: give --workspace <folder>`; stdout one block per hit
  (`a.txt @ 0x3 [utf-8]`, `b.bin @ 0x7 [utf-16le]`, and `b.bin @ 0x6 [utf-16be]`: a UTF-16 needle
  also matches one byte off, doc 6.7 / HANDOFF open item), each with the context bytes, the match in
  brackets and `sig <pattern> at <n>`; last line `3 hit(s) in 2 of 4 file(s) searched for text
  'Health' as utf-8, utf-16le, utf-16be`; exit 0.
- 2: 4 hits: `HEALTH` at `0xd` too, encodings `utf-8 (any case)`, `utf-16le (any case)`,
  `utf-16be (any case)`.

## SQC-SE-02 (P0) Numbers and floats, widths, what was not tried

Steps:
1. `viwo search C:\sqc\se\c.bin --number 100 --quiet`
2. `viwo search C:\sqc\se\c.bin --number 0x64 --widths "1,2" --quiet`
3. `viwo search C:\sqc\se\c.bin --number 1.5 --quiet`
4. `viwo search C:\sqc\se\c.bin --number 0.1 --quiet`
5. `viwo search C:\sqc\se --number 70000 --widths 2`; `... --number 5 --widths 3`; `... --number abc`

Expected:
- 1: 4 hits (`0x2` u16le and u32le, `0x8` u16be, `0x9` u16le: overlapping matches all count); tried
  `u16le, u16be, u32le, u32be, u64le, u64be`; `note: 1-byte forms not tried (ask for width 1)`.
- 2: 5 hits, tried `u8, u16le, u16be`, no note.
- 3: 1 hit `c.bin @ 0xa [f32le]`; tried `f32le, f32be, f64le, f64be`.
- 4: 0 hits and `note: f32 is the nearest single-precision value (an exact bit match only)`.
- 5: `viwo: invalid_request: 70000 fits none of the widths [2]`, `integer widths are 1, 2, 4 or 8
  bytes, not '3'`, `not a number: 'abc'`; each exit 2.

## SQC-SE-03 (P0) Byte patterns with wildcards; bad input

Steps:
1. `viwo search C:\sqc\se\c.bin --bytes "41 41 64 ?? 00 00 42" --quiet`
2. `viwo search C:\sqc\se --bytes "4G 11"`
3. `viwo search C:\nope --text x`
4. `viwo search C:\sqc\se --text x --number 1`

Expected: 1: `c.bin @ 0x0 [bytes]`, 1 hit. 2: `viwo: invalid_request: bad byte '4G' in '4G 11'`,
exit 2. 3: `viwo: not_found: nothing to search at C:\nope` with the hint `a workspace, a game folder
or one file (an exe, a dll); only read`, exit 1. 4: argparse `argument --number: not allowed with
argument --text`, exit 2.

## SQC-SE-04 (P0) A match across two 8 MB chunks is found once

Steps: `viwo search C:\sqc\se\big.bin --text "BOUNDARY!!"`

Expected: exactly 1 hit, `big.bin @ 0x7ffffd [utf-8]`; `Searched 1 of 1 file(s), 9.4 MB`.

## SQC-SE-05 (P0) Caps are said only when they drop a hit

Steps:
1. `viwo search C:\sqc\se --text a --per-file 1 --quiet`
2. `viwo search C:\sqc\se --bytes "00 00" --max-hits 2 --quiet`

Expected:
- 1: `viwo: warning: b.bin: hits capped at 1 per file; the hit at 0xb and the rest were not kept`;
  `2 hit(s) in 2 of 4 file(s)` (`a.txt` has one `a`: no warning for it).
- 2: `b.bin: hits capped at the overall cap of 2; the hit at 0x2 and the rest were not kept` and
  `2 file(s) after b.bin not searched (overall cap)`; `2 hit(s) in 1 of 2 file(s) searched`.

## SQC-SE-06 (P0) An executable: section, RVA, VA and a unique signature per hit

Steps: `viwo search <repo>\Test-games\chocolate-doom\engine\chocolate-doom.exe --text "Chocolate Doom" --max-hits 3 --quiet`

Expected: 3 hits in `.rdata`, the first `chocolate-doom.exe @ 0x7bf39 [utf-8] .rdata rva 0x7e339
va 0x47e339` with `sig 43 68 6F 63 6F 6C 61 74 65 20 44 6F 6F 6D 20 33 2E 31 2E 30 00 2D 2D 76 at 0`;
the cap of 3 said (`the hit at 0x7f540 and the rest were not kept`). The game folder is unchanged.

## SQC-SE-07 (P0) Where the report lands, and where it never does

Steps:
1. `viwo search C:\sqc\se --text Health --workspace C:\sqc\_ws\se1 --quiet` (folder absent)
2. `mkdir C:\sqc\_ws\se-other; Set-Content C:\sqc\_ws\se-other\mine.txt x`, then the same with
   `--workspace C:\sqc\_ws\se-other`
3. The same with `--workspace C:\sqc\se\res`
4. `viwo search C:\sqc\_ws\se1 --text Health`

Expected:
- 1: `Saved: C:\sqc\_ws\se1\.search\<yyyymmdd-hhmmss>-text.json`; the folder now holds
  `.viwo-workspace` and `.search\`.
- 2: `viwo: refused: C:\sqc\_ws\se-other is not a ViWo workspace: no search results are written
  there`, hint `give an empty folder or a ViWo workspace`, exit 3, nothing written.
- 3: `viwo: refused: the results folder (C:\sqc\se\res) is inside the game folder (C:\sqc\se)`,
  exit 3, `C:\sqc\se\res` not created.
- 4: `Searching 0 file(s) ... (workspace)`: its dot entries (`.search`, the marker) are left out; the
  report is saved into it (a second file under `.search\`).

## SQC-SE-08 (P1) An unreadable file is named, never skipped silently

Steps (PowerShell, the file held open without sharing):
`$f=[IO.File]::Open("C:\sqc\se\a.txt",'Open','Read','None'); viwo search C:\sqc\se --text Health --quiet; $f.Close()`

Expected: `viwo: warning: Cannot read a.txt: Permission denied`; `2 hit(s) in 1 of 3 file(s)`
(4 files, 3 searched); `--json` lists it under `data.unreadable`.

## SQC-SE-09 (P0) `--json` keeps stdout clean

Steps: `viwo --json search C:\sqc\se\c.bin --number 1.5 > C:\sqc\_se.json 2> C:\sqc\_se.err`; `Get-Content C:\sqc\_se.json -Raw | ConvertFrom-Json`

Expected: one JSON document: `ok: true`, `data.hitCount` 1, `warnings` = `[the results were not
saved: give --workspace <folder>]`; the two progress lines only in `_se.err`.

## SQC-SE-10 (P0) API: `POST /api/search` as a job, its errors, the report in the active workspace

Preconditions: `viwo serve`; the active workspace is an extraction of `C:\sqc\zip-basic\game`
(`C:\sqc\_ws\api1`). Calls with the token (14-security).

Steps:
1. `{"target": "C:\\sqc\\_ws\\api1", "kind": "text", "value": "readme"}`
2. `{"target": "C:\\sqc\\zip-basic\\game", "kind": "bytes", "value": "89 50 4E 47"}`
3. `{"target": "C:\\nope", ...}`; `{"kind": "regex", ...}`; `{"perFile": "many", ...}`; `{"value": "  ", ...}`
4. `{"target": "C:\\sqc\\_ws", "kind": "text", "value": "readme", "maxHits": 5}` (a folder that holds the active workspace)
5. `GET /api/jobs`; `POST /api/jobs {"kind": "search", "params": {"target": "C:\\sqc\\_ws\\api1", "kind": "number", "value": "100"}}`

Expected:
- 1: `success: true`, a `jobId`, `kind: "workspace"`, `files: 5` (dot entries left out),
  `hitCount: 2`, `saved` = `C:\sqc\_ws\api1\.search\<stamp>-text.json`, `warnings: []`.
- 2: `kind: "folder"`, 2 hits in 2 files, saved in the active workspace.
- 3: `not_found` `nothing to search at C:\nope` (hint `an absolute path to a file or a folder`);
  `invalid_request` `search for text, a number or bytes, not 'regex'`; `invalid_request`
  `perFile must be a whole number, not 'many'`; `invalid_request` `give the text to search for`;
  each also a `[FAILED] POST /api/search: ...` line in `GET /api/logs`.
- 4: the search runs (`success: true`), `saved: null`, the first warning `the results are not saved
  in C:\sqc\_ws\api1: the results folder (...) is inside the game folder (C:\sqc\_ws)`, then the
  overall-cap warnings.
- 5: the jobs of kind `search` listed; the `/api/jobs` route answers the same report shape.

## SQC-SE-11 (P0) SEARCH view

Preconditions: `viwo serve`, any active workspace.

Steps: STATIC arm > SEARCH.
1. Empty WHERE and WHAT: read the action bar.
2. Switch the kind with `TEXT` / `NUMBER` / `BYTES`.
3. WHERE `C:\nope`, WHAT `x`, `SEARCH`; then wait ten seconds; open another view.
4. `NUMBER`, WHERE `C:\sqc\se`, WHAT `abc`, `SEARCH`.
5. `TEXT`, WHAT `Health`, `SEARCH`; `COPY PATCH` on a hit.

Expected:
- 1: `SEARCH` disabled with `enter where to search` beside it; the kinds read `TEXT NUMBER BYTES`.
- 2: the label follows (`NUMBER (AN INTEGER AS 2/4/8 BYTES, LE AND BE; WITH A POINT: A 32/64-BIT
  FLOAT)`); `ANY CASE` shows only for text, the widths only for numbers.
- 3: error box `SEARCH FAILED // NOT FOUND`, the message, `NEXT` `The file or folder is gone, or the
  path has a typo. Check it, or refresh this view.`, `code: not_found`; an `ERROR` toast with
  `DISMISS` that is still there after ten seconds and goes when the view changes; one
  `[FAILED] POST /api/search: ...` line in the activity console.
- 4: `SEARCH FAILED // CHECK YOUR INPUT`, `not a number: 'abc'`, `code: invalid_request`.
- 5: panel `HITS` with badge `3 IN 2 FILE(S)`, columns `FILE OFFSET AS IN THE EXECUTABLE BYTES AROUND
  IT`, `SEARCHED 4 of 4 file(s), 9,437,244 bytes`, `TRIED utf-8, utf-16le, utf-16be`, `SAVED <path>`;
  the action bar `3 hit(s) in 2 of 4 file(s)`. `COPY PATCH` puts a patch-set entry on the clipboard
  (`{"file", "pattern", "at", "patched": ""}`) and toasts `Patch entry copied: fill in "patched" ...`.

## SQC-SE-12 (P1) A hit becomes a patch set entry

Steps: take the second hit of SQC-SE-06 (signature `43 68 6F 63 6F 6C 61 74 65 20 44 6F 6F 6D 20 69`,
`at 0`) and put it in `C:\sqc\cd.patch.json` as
`{"file": "chocolate-doom.exe", "pattern": "<signature>", "at": 0, "patched": "59"}` (with the
other entries of SQC-PAT-01); `viwo patch <repo>\Test-games\chocolate-doom\engine C:\sqc\cd.patch.json --plan`.

Expected: that entry `ready` at offset 507765 (`0x7bf75`, the hit's offset), `old 43`, `new 59`.

## Results

| ID | Result | Version | Notes | Tester | Date |
|----|--------|---------|-------|--------|------|
| SQC-SE-01 | PASS | 1.36.0+search+apk (unreleased) | 3 hits / 4 any-case; the off-by-one UTF-16BE hit in `b.bin` seen, as documented | agent | 2026-11-23 |
| SQC-SE-02 | PASS | 1.36.0+search+apk (unreleased) | all five steps as written; unquoted `--widths 1,2` breaks in PowerShell (argparse `unrecognized arguments: 2`) | agent | 2026-11-23 |
| SQC-SE-03 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-SE-04 | PASS | 1.36.0+search+apk (unreleased) | one hit at 0x7ffffd | agent | 2026-11-23 |
| SQC-SE-05 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-SE-06 | PASS | 1.36.0+search+apk (unreleased) | Chocolate Doom 3.1.0 exe | agent | 2026-11-23 |
| SQC-SE-07 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-SE-08 | PASS | 1.36.0+search+apk (unreleased) | `Cannot read a.txt: Permission denied` | agent | 2026-11-23 |
| SQC-SE-09 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-SE-10 | PASS | 1.36.0+search+apk (unreleased) | run against a live server on port 8192; four `[FAILED]` lines seen | agent | 2026-11-23 |
| SQC-SE-11 | PASS (but COPY PATCH) | 1.36.0+search+apk (unreleased) | headless Edge over CDP: steps 1-5 as written (the error toast checked after 6 s, not 10); COPY PATCH NOT RUN: a headless page has no focus (`Document is not focused`), needs a person | agent | 2026-11-23 |
| SQC-SE-12 | PASS | 1.36.0+search+apk (unreleased) | `ready`, offset 507765 | agent | 2026-11-23 |
