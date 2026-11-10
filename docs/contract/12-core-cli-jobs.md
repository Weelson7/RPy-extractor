# 12. Headless core, jobs and CLI

ViWo is a headless core with two clients: the CLI (`viwo`) and the web UI over HTTP. Every
capability is reachable from the CLI; the server is one front end.

## 12.1 Shape

- The core boots from the ini without a server (`viwo/core/wiring/boot.py` -> `Runtime`).
- Long work runs as a **job** with an event stream and a result; clients submit, follow events
  and read the result.
- Every CLI command has `--json` output (the envelope, 12.3b).

## 12.2 Core facade

```text
boot(ini_path, os_id, temp_root, profile, features) -> Runtime
Runtime
  config, os, plugins, slots, backends, bindings, temp_root, problems, disabled
  info() -> {os, osName, ini, contract, iniContract, features, sources, plugins, slots, problems, ...}
  dependency_report() -> [dependency item]          doc 4.2
```

Features (extraction, analysis, capture, repack, patch sets, mods, sanitizer, merger, survey,
installer) are module functions taking the runtime (`extract` in `core/pipeline/runner.py`,
`analyze` in `core/analysis/__init__.py`, `capture` in `core/capture/__init__.py`, `repack` in
`core/roundtrip.py`, ...); the API and the CLI call the same functions.

## 12.3 Jobs (`viwo/core/jobs.py`)

```text
Job       { id, kind, state, events[], result, error, created, started, finished }
state     queued -> running -> succeeded | failed | cancelled
summary   { id, kind, state, events (count), error, created, started, finished, elapsed }
kinds     extract survey repack patch mod preflight install capture dump trace agent record
          analyze cleanup merge indexes
```

- Jobs run in worker threads; the server keeps the last 200 finished jobs in memory (run
  records stay on disk). The CLI runs the same code in the foreground (`JobRunner`).
- **Run record:** a finished extraction writes the request (secrets as `<secret>`), the effective
  ini, the slot bindings, each tool's version and the result to
  `.extraction_metadata/runs/<job id>.json` (`viwo/core/records.py`). `viwo replay RECORD` re-runs
  it; with the same tools it gives the same workspace.
- **Concurrency:** one lock per workspace (doc 4.3). Writing jobs (extract, merge, cleanup apply,
  repack, patch, mod, capture, analyze) hold it for their run; a short curation call takes it
  with a timeout and answers `busy` (409) otherwise.
- **Cancellation:** the job's `CancelToken`; the OS layer kills the tool's process tree.

## 12.3b Result envelope

Used by the envelope routes, `viwo --json` and job errors (`viwo/contracts/errors.py`).

```text
Envelope { ok, data, error, warnings[] }
Error    { code, message, owner, hint }        owner: "core" | plugin id | backend id
code     invalid_request | not_found | busy | unavailable | needs_key | needs_decision
         | failed | cancelled | refused | offline | internal
```

- Backend outcomes map onto `unavailable`, `failed`, `needs_key`.
- `refused` is for engineering refusals (workspace ownership, a path outside its root, a switch
  that is off); `needs_decision` asks for a choice (re-extraction, capture confirmation).
- `internal` is a programming error: the trace goes to the log, never into the response.

## 12.4 CLI (`viwo/cli.py`, `cli_args.py`, `cli_arms.py`, `cli_check.py`, `cli_extra.py`, `cli_dynamic.py`, `cli_patch.py`, `cli_format.py`)

Commands are grouped by arm; `viwo -h` lists them, `viwo <arm>` lists one arm, and
`viwo <arm> <command> ...` is the same as `viwo <command> ...`.

| Arm | Command | What it does |
|-----|---------|--------------|
| static | `survey FOLDER [--deep]` | read-only coverage report for a game or a library (a folder holding only folders, two or more of which hold a program of their own, or none does; one program in one subfolder is one game, as `bin/x64/`) |
| static | `detect GAME` | every plugin's detection |
| static | `extract GAME --workspace W [--plugin ID \| --mixed A,B] [--policy selected\|detected\|all] [--exts .png,.ogg] [--on-existing new\|replace\|cancel] [--option plugin.key=value] [--carve off\|unknown\|all]` | extraction run |
| static | `replay RECORD --workspace W [--on-existing ...] [--option ...]` | re-run a run record (secrets asked again) |
| static | `unpack ARCHIVE --out DIR [--slot SLOT] [--backend main\|spare\|ID] [--option ...]` | one archive (nested too; `--slot` forces one slot, no nesting) |
| static | `sanitize WORKSPACE [--apply] [--undo TOKEN]` | cleanup plan, apply, undo (doc 5) |
| static | `analyze GAME [--list] [--workspace W --target KEY] [--slot SLOT] [--set KEY=VALUE] [--open [HANDOFF]] [--timeout S]` | static analysis (doc 6) |
| static | `diff OLD NEW [--out DIR]` | function-level diff of two analyses |
| dynamic | `capture GAME --exe EXE --workspace W [--confirm] [--auto SECONDS]` | RenderDoc capture (doc 11) |
| dynamic | `dump (--pid PID \| --name NAME) --workspace W` | memory dump |
| dynamic | `trace (--pid \| --name) --workspace W [--functions GLOBS] [--seconds S]` | frida-trace (comma-separated globs, default `CreateFileW`; an empty list is refused) |
| dynamic | `agent GAME --exe EXE --workspace W [--copy DIR] [--timeout S]` | the engine's runtime agent |
| dynamic | `record --workspace W [--seconds S]` | system sound to WAV |
| patching | `repack WORKSPACE [--out DIR] [--plan]` | patched copy with the edited files (doc 18) |
| patching | `patch GAME PATCHSET [--out DIR] [--plan]` | apply a patch set to a patched copy |
| patching | `mod pack\|check\|apply GAME MOD... [--copy DIR] [--name N] [--requires A,B] [--after A,B]` | mod packages |
| system | `serve [--host H] [--port P] [--no-browser]` | web UI (also `python Start.py`) |
| system | `info`, `slots [--check]` | configuration, bindings, dependency status, backend self-tests |
| system | `install [ID... \| --all \| --game SLUG [--game-version V]]` | pinned tools (doc 10) |
| system | `config generate [DIR]`, `config check FILE...` | distros |
| system | `indexes update` | latest per-game indexes release |
| system | `diag [--out ZIP]` | logs, run records and tool status for a bug report, secrets stripped |

Global flags: `--ini PATH`, `--os auto|linux|windows`, `--profile P`, `--features a,b`,
`--json` (envelope on stdout and nothing else there: while the command runs, the process's
stdout is pointed at stderr, so a native library or a child tool that prints cannot break the
document; progress stays on stderr), `--quiet` (no progress lines),
`--verbose` (also the effective ini and bindings). Bare `viwo` prints a short guide with the
philosophy paragraph. Plugins add commands (`cli_commands()`; drop-ins only with `"cli": true`).

Exit codes: 0 ok; 1 failed or not found; 2 bad request, bad config or a decision needed; 3
refused (containment, switch off, unsupported OS layer); 4 strict preflight failed; 130
cancelled (Ctrl+C). Errors print `viwo: <code>: <message>` and a hint; every envelope warning is
printed in text mode.

## 12.5 HTTP as a client of the core

- `/api/extract` submits an `extract` job and waits for it (the UI's request stays open).
- `POST /api/jobs {kind, params}` runs the same handler as the kind's own route for every kind of
  12.3 except `merge` and `indexes` (`viwo/api/handlers_jobs.py`); unknown kinds answer
  `invalid_request` with the list.
- `GET /api/jobs`, `GET /api/jobs/<id>`, `GET /api/jobs/<id>/events?from=N` (polling),
  `POST /api/jobs/<id>/cancel` (the only cancellation route).
- Curation actions (sorting, trash, rename) are synchronous calls under the workspace lock.

## 12.6 Packaging

- Python 3.11+ (`requires-python`), `pyproject.toml` with the `viwo` console script; optional
  extras `unity`, `sevenzip`, `renpy`, `lz4`, `patch` (capstone), `runtime` (frida-tools,
  soundcard), `dev` (ruff). Without them the same packages install as hash-locked pins into
  `third_party/python` (doc 10).
- Release artifacts (built by `.github/workflows/release.yml` on a `vN.0.0` tag or by hand):
  wheel, sdist and the portable Windows bundle `ViWo-<version>-windows-x64.zip`
  (`packaging/build_portable.py`: `viwo.exe`, no Python needed; tools install next to it).
