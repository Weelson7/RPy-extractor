# 13 CLI

Area code `CLI`. Contract doc 12.4. Every `viwo` command once, with and without `--json`, plus
`tools/version.py` and `tools/affected.py`. Exit codes: 0 ok, 1 failed or not found, 2 invalid
request / bad config / needs decision, 3 refused, 4 strict preflight failed (serve), 130 cancelled.
Errors print `viwo: <code>: <message>` and a hint. PowerShell splits an unquoted comma list into
separate arguments: quote lists (`--features "extraction,capture"`).

## SQC-CLI-01 (P0) `viwo extract --json` envelope and exit codes

Steps:
1. `viwo --json extract C:\sqc\zip-basic\game --workspace C:\sqc\_ws\cli1 --on-existing replace > C:\sqc\_cli1.json 2> C:\sqc\_cli1.err`
2. `viwo extract C:\nope --workspace C:\sqc\_ws\cli2; $LASTEXITCODE`
3. `viwo extract C:\sqc\zip-basic\game --workspace C:\sqc\zip-basic\game\x; $LASTEXITCODE`

Expected: 1: `_cli1.json` is one JSON document: `ok: true`, `data.workspace`, `data.plugins[0].id` =
`generic`, `data.copiedFiles` 5, `warnings: []`; the progress lines are in `_cli1.err` only. 2:
`viwo: invalid_request: game folder not found: C:\nope`, exit 2. 3: `viwo: refused: the workspace
(C:\sqc\zip-basic\game\x) is inside the game folder (C:\sqc\zip-basic\game)`, hint `choose a
location outside the game; ViWo never writes there`, exit 3, `x` not created.

## SQC-CLI-02 (P0) `viwo` (guide), `viwo -h`, `viwo <arm>`, `viwo <command> -h`

Steps: `viwo`; `viwo -h`; `viwo static`; `viwo dynamic`; `viwo patching`; `viwo system`; `viwo
static detect C:\sqc\doom\game` and `viwo detect C:\sqc\doom\game` (both `--json`); `viwo <command>
-h` for every command; `viwo --json slots` and `viwo slots --json`.

Expected: the guide (commands, the three arms, the philosophy paragraph); `-h` lists the commands by
arm: static `survey detect extract replay unpack search sanitize analyze diff`; dynamic `capture
dump trace hook profile agent record attach`; patching `repack patch mod isolate`; system `serve
info slots install config indexes diag workbook runbook`; add-ons `qt-resources [qt]`; then the
global flags and exit codes. `viwo <arm>` lists only that arm. The two detects give the same
document. Each command's `-h` lists the options of doc 12.4 (`search` the mutually exclusive
`--text | --number | --bytes`; `isolate` the actions `list | start | status | pause | resume |
snapshot | rollback | dump | patch | undo | stop, or an executable`). `--json` works before and
after the command.

## SQC-CLI-03 (P0) `viwo info` and `viwo slots`

Steps: `viwo info`; `viwo --json info`; `viwo slots`.

Expected: `info` prints `OS layer`, `Startup`, the plugins, slot bindings and problems; JSON
`data.os`, `osName`, `ini`, `contract`, `iniContract`, `features`, `sources`, `plugins`, `slots`,
`problems`; `slots` prints `SLOT MAIN SPARE` then `DEPENDENCY STATUS VERSION WHERE LOCATION / HOW`
and a warning per slot whose backend is unavailable, naming its install hint.

## SQC-CLI-04 (P0) `viwo detect`

Steps: `viwo --json detect C:\sqc\doom\game`.

Expected: `data.doom.confidence` 0.9, `data.doom.evidence` `["IWAD (Doom engine game data)", "PWAD
(Doom engine add-on data)"]`.

## SQC-CLI-05 (P0) `viwo unpack`

Steps:
1. `viwo unpack C:\sqc\nested-traversal\game\outer.zip --out C:\sqc\_unpack`
2. `viwo unpack C:\sqc\nested-traversal\game\extra.tar.gz --out C:\sqc\_unpack2` (and `--json`)
3. Step 1 again into the now non-empty `C:\sqc\_unpack`.

Expected: 1: `outer.zip` and the nested `inner.zip` unpacked (`Unpacked 2 archive(s), 3 file(s)`,
`Backends: py-zipfile x2`), `voice\hello.ogg` under `outer.zip!nested_inner.zip\`. 2: `extra.tar.gz:
1 entr(ies) whose name leads out of the folder skipped` and `FAILED : ...` in the summary (JSON
`data.failures`); `escape.txt` written nowhere. 3: `viwo: refused: the output folder (...) holds
files and is not a ViWo workspace: ...`, exit 3.

## SQC-CLI-06 (P0) `viwo replay`

Steps: `viwo replay C:\sqc\_ws\cli1\.extraction_metadata\runs\<id>.json --workspace C:\sqc\_ws\cli6`

Expected: the same extraction again (`Files : 5 collected from 5 scanned`, same groups), a new run
record in `cli6`, exit 0. Secrets of the record are asked again (`--option`).

## SQC-CLI-07 (P0) `--json` of the other commands

Steps: `viwo --json survey C:\sqc\doom\game`; copy `C:\sqc\dirty-workspace\ws` to `C:\sqc\_ws\dirty`
and `viwo --json sanitize C:\sqc\_ws\dirty`; `viwo --json repack C:\sqc\_ws\cli1 --plan`; `viwo
--json search ...` (21-search); `viwo --json isolate --list` (22-isolation); `viwo --json patch ...
--plan` (18-patching).

Expected: each one envelope with `ok: true` and its `data`: survey `games`; sanitize `planId,
recipeId, scanned, findings (7), warnings, total, offset, limit`; repack `game, target, mode, edits,
plan, skipped, warnings, context`.

## SQC-CLI-08 (P0) `viwo install`

Steps: SQC-DEP-02/03, plus `viwo --json install repak`.

Expected: as there; JSON `data.installed = ["repak"]`, `data.failed = {}` (14-security SQC-SEC-04
checks the refusals).

## SQC-CLI-09 (P0) `viwo config generate` and `viwo config check`

Steps:
1. `viwo config generate C:\sqc\_distros`
2. `viwo config check (Get-ChildItem C:\sqc\_distros\*.ini).FullName`
3. In `C:\sqc\_distros\windows-unity.ini` change the line `export.unity = unitypy, assetstudiomod-cli`
   to `export.unity = nosuch`; check that file again.
4. Compare `C:\sqc\_distros` with `<repo>\distros` (file hashes).

Expected: 1: `Wrote 12 distro file(s) to C:\sqc\_distros`, `<os>-<profile>.ini` for linux / windows x
custom godot mixed renpy unity unreal, each starting `; Generated by \`viwo config generate\` - edit
startup.ini instead of this file.` and `; viwo contract 1.2 - distro <name>`. 2: `OK: <12 paths>`.
3: `viwo: invalid_request: config check failed`, hint `...windows-unity.ini: [slots] export.unity:
'nosuch' is not a export backend`, exit 2. 4: byte-identical (`tests.test_sealed` and
`test_shipped_distros_match_the_generator` guard this).

## SQC-CLI-10 (P0) `viwo serve` options and a port in use

Steps: `viwo serve --no-browser --port 8099`; in a second terminal `viwo serve --port 8099
--no-browser`; `netstat -ano | findstr :8099`.

Expected: first: `ViWo // Vidya Wormhole -> http://127.0.0.1:8099/` and `Workspace: ...`; second:
`viwo: cannot listen on 127.0.0.1:8099: ...Use --port or change [server] port in startup.ini.`, exit
2; one LISTENING pid.

## SQC-CLI-11 (P0) Version tool: `tools/version.py`

Preconditions: the branch tip (HEAD carries the latest `v*` tag).

Steps:
1. `python tools\version.py show`
2. `python tools\version.py verify`
3. `git tag --list v*` (latest) and `git describe --tags --abbrev=0`; compare with 1.
4. Append a blank line to README.md, then `git commit -am test`; restore README.md.
5. `python tools\version.py bump tweak; python tools\version.py show`; restore `pyproject.toml` and `viwo\__init__.py`.

Expected: 1: `a.b.c`. 2: `version a.b.c ok (latest tag va.b.c)`, exit 0. 3: equal. 4: the pre-commit
hook refuses: `version: a.b.c is not past the latest tag va.b.c. Commit with: python
tools/version.py commit -m "..." [--feature|--major]`; `git log -1` unchanged. 5: `a.b.(c+1)`, both
files changed. On a worktree behind the tip (an older tag checked out), step 2 answers `version
a.b.c is not past the latest tag v<newer>` and exit 1: that is the commit guard, not a fault.

## SQC-CLI-12 (P1) `--ini` and `--os` overrides

Steps: `viwo --ini C:\sqc\ini\godot-fake.ini slots`; `viwo --os linux info` on Windows.

Expected: the fake tools `gdre` and `godotpcktool` `found` from `PATH or ini` (config source), bound
to `unarchive.pck`, `export.godot`, `pack.pck`, `analysis.gdscript`; `viwo: refused: OS layer
'linux' cannot run on this host`, exit 3.

## SQC-CLI-13 (P2) Unicode paths and spaces

Steps: copy `C:\sqc\zip-basic` to `C:\sqc\ゲーム folder\`; `viwo extract "C:\sqc\ゲーム folder\game" --workspace "C:\sqc\_ws\ゲーム ws"`.

Expected: works end to end; `provenance.jsonl` and the run record store relative paths with forward
slashes (`png/title.png`).

## SQC-CLI-14 (P0) Durations: every stage, and the run's time

Steps: `viwo extract C:\sqc\doom\game --workspace C:\sqc\_ws\cli14 --on-existing replace`; then
`viwo extract <repo>\Test-games\freedoom --workspace C:\sqc\_ws\fd`.

Expected: every progress line carries the time of day; a stage of a second or more ends with
`<stage> took <t>`; the run closes with `Time: <total>: <stage> <t>, ...` (longest first, stages
under a second left out; empty on the fixture). On Freedoom no stretch passes without a line: the
carve says what it looks through, the collect counts `Scanned files: i / N (k collected)` about
once a second, `collect took 16 s`, `Time: 1 min 05 s: unpack 35 s, collect 16 s, identify 13 s`
(this machine). The same lines are in the job's log in JOBS and in the activity console.

## SQC-CLI-15 (P0) `--json` keeps stdout clean

Steps: SQC-CLI-01 step 1; `Get-Content C:\sqc\_cli1.json -Raw | ConvertFrom-Json`; the same on a
Unity IL2CPP game (UnityPy's native layout generator prints there).

Expected: one JSON document, nothing before or after it; progress lines and every native print
(`Error generating tree nodes` on IL2CPP) in the stderr file only.

## SQC-CLI-16 (P1) A commit runs only the tests close to its change

Steps (no file is edited): `python -c "import sys; from tools.affected import select; print(select(sys.argv[1:]))" <path>`
for `CHANGELOG.md`, `viwo/plugins/doom/__init__.py`, `pyproject.toml`, `viwo/core/search.py`,
`viwo/core/isolation/session.py`.

Expected: `['tests.test_affected']`; 13 modules (`test_doom`, `test_wad_pack`, the plugin-wide
`test_registry`, `test_conformance_kit`, `test_config`, `test_sealed`, ...); `None` (all);
`['tests.test_search']`; `['tests.test_isolation_bridge', 'tests.test_isolation_real']`.
`tools\version.py commit` runs that list; `--full` the whole suite (`python tools\run_tests.py`).

## SQC-CLI-17 (P2) Distro profiles come from the plugins

Steps: SQC-CLI-09 step 4; `python -m unittest tests.test_sealed`.

Expected: twelve files byte-identical to the shipped ones (renpy, unity, unreal, godot named by
their plugin's manifest `profile`, plus custom and mixed); the test green.

## SQC-CLI-18 (P1) `viwo diag` and `viwo qt-resources`

Steps: `viwo diag --out C:\sqc\diag.zip`; list the zip and read `about.json`; `viwo qt-resources <repo>\Test-games\chocolate-doom\engine\chocolate-doom.exe`.

Expected: `Diagnostics bundle written: C:\sqc\diag.zip (secrets stripped)`; members `about.json`
(`created`, `frozen`, `ini`, `os`, `os_layer`, `python`, `viwo`: the version), `info.json`,
`slots.json`, `tools.json`, `logs/viwo-<date>.log`; `qt-resources` on a non-Qt binary answers
`carved: 0`, `names: []`, exit 0.

## Results

| ID | Result | Version | Notes | Tester | Date |
|----|--------|---------|-------|--------|------|
| SQC-CLI-01 | PASS | 1.36.0+search+apk (unreleased) | 18 progress lines on stderr, none on stdout | agent | 2026-11-23 |
| SQC-CLI-02 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-CLI-03 | PASS | 1.36.0+search+apk (unreleased) | `info` has no ViWo version line (diag's `about.json` has it) | agent | 2026-11-23 |
| SQC-CLI-04 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-CLI-05 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-CLI-06 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-CLI-07 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-CLI-08 | NOT RUN | 1.36.0+search+apk (unreleased) | a real download: not allowed in this run (the refusal path ran in SQC-SEC-04) | agent | 2026-11-23 |
| SQC-CLI-09 | PASS | 1.36.0+search+apk (unreleased) | contract line now `1.2` | agent | 2026-11-23 |
| SQC-CLI-10 | FAIL | 1.36.0+search+apk (unreleased) | the second `viwo serve --port 8192 --no-browser` started (`-> http://127.0.0.1:8192/`) while the first listened; `netstat` showed two LISTENING pids on 8192 (see SQC-SEC-08) | agent | 2026-11-23 |
| SQC-CLI-11 | BLOCKED | 1.36.0+search+apk (unreleased) | not on the tip: this worktree is at `v1.36.0` and `v1.37.0` exists. Step 1 `1.36.0`; step 2 `version: 1.36.0 is not past the latest tag v1.37.0...`, exit 1; step 3 `git describe` = `v1.36.0`; steps 4-5 NOT RUN (no commits or edits allowed here) | agent | 2026-11-23 |
| SQC-CLI-12 | PASS | 1.36.0+search+apk (unreleased) | the fake tools' VERSION column reads `Traceback (mos...` (they do not answer a version probe) | agent | 2026-11-23 |
| SQC-CLI-13 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-CLI-14 | PASS | 1.36.0+search+apk (unreleased) | fixture: `Time: 0 s: ` ends on a dangling colon; Freedoom as written; `Collected 4100 file(s)` has no thousands separator where the other counts have one. JOBS and the console not looked at | agent | 2026-11-23 |
| SQC-CLI-15 | PASS (fixture) / NOT RUN (IL2CPP) | 1.36.0+search+apk (unreleased) | no Unity game here | agent | 2026-11-23 |
| SQC-CLI-16 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
| SQC-CLI-17 | PASS | 1.36.0+search+apk (unreleased) | `tests.test_sealed` OK (1 test) | agent | 2026-11-23 |
| SQC-CLI-18 | PASS | 1.36.0+search+apk (unreleased) | | agent | 2026-11-23 |
