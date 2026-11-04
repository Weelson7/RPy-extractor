# 12. Headless core, CLI and jobs (draft)

Decision taken: the framework is a **headless core**, driven by a **CLI**
and by the **web UI**, which becomes one client among others. This doc
sketches what that implies. All names are provisional.

## 12.1 What changes compared to v1

| v1 | Proposal |
|----|----------|
| Everything starts from `extract.py`, the HTTP server | `core` boots from the ini (doc 9) without any server. The server is just one front end |
| Extraction runs inside the HTTP request thread, so the request can stay open for minutes | Long work runs as a **job**. Clients submit a job, then follow its events and read its result |
| Progress = strings appended to an in-memory session, polled by the UI | Each job has an **event stream** (ProgressEvent, doc 4.4). The v1 `/api/logs` polling becomes an adapter over the latest events |
| Nothing can be scripted or tested without the UI | Every capability is reachable from the CLI, which also provides `--json` output |

## 12.2 Core facade

```text
boot(ini_path, overrides) -> Runtime        # doc 9 boot sequence, steps 2-10
Runtime
  info() -> DistroInfo                       # effective ini, OS layer, plugins, slots, problems
  detect(game_path) -> [DetectionResult] + selection per mode
  submit(spec: JobSpec) -> JobHandle
  jobs.get(id) / jobs.list() / jobs.cancel(id)
  workspace(path?) -> Workspace              # curation services (sorting, groups, trash)
  shutdown()
```

## 12.3 Jobs

```text
JobSpec   { kind, params, ini_digest }        # serializable JSON, can be replayed
kind      extract | unpack | sanitize.plan | sanitize.apply | merge | analyze | capture
JobHandle { id, kind, state, created, started, finished }
state     queued -> running -> succeeded | failed | cancelled
events    ordered ProgressEvent stream, replayable from offset N
result    kind-specific (ExtractionResult, SanitizePlan, ...)
```

- **Run record:** each finished job writes `JobSpec`, the effective ini, the slot bindings, each tool's version or commit, and the result to `.extraction_metadata/runs/<job_id>.json`. With the same record and the same tools, a run should give the same output (principle 7).
- **Concurrency (decided for the prototype):** one **lock per workspace**. Writing jobs (extract, merge, sanitize apply, capture) hold it for their whole run. Synchronous curation calls take it with a short timeout and return 409 `busy` otherwise. Read-only work (detect, sanitize plan, analysis) doesn't take it.
- **Cancellation** uses the CancelToken (doc 1.1 kills the process tree).

## 12.3b One result envelope

Used by the new HTTP routes, `viwo --json` and job results. v1 routes keep
their own shapes (doc 4.1).

```text
Envelope { ok: bool, data: <kind-specific> | null, error: Error | null, warnings: [Warning] }
Error    { code, message, owner, hint }        # owner: "core" | plugin id | backend id
code     invalid_request | not_found | busy | unavailable | needs_key | failed | cancelled | refused | internal
```

- Backend outcomes map onto codes: `unavailable`, `failed`, `needs_key`.
- Policy refusals (capture, workspace ownership) use `refused`.
- Programming errors use `internal`, and their trace goes to the log, never into the response.
- At the HTTP layer, expected failures are 200 with `ok:false` (as in v1); `busy` is 409, `invalid_request` 400, `refused` 403, `internal` 500.

## 12.4 CLI sketch

The command name is `viwo` (product: Vidya Wormhole). The old name "RPy Extractor"
undersold a multi-engine framework; renamed to ViWo (D15).

```
viwo info                         distro, OS layer, plugins, slot bindings, dependency status
viwo detect <game>                detections + chosen plugin(s) per mode
viwo extract <game> [--plugin ID | --mixed ID,ID | --policy selected|detected|all]
                    [--exts .png,.ogg] [--workspace DIR] [--option plugin.key=value]
viwo unpack <archive> [--slot unarchive.7z] [--backend main|spare|ID]
viwo slots [--check]              bindings; --check runs each backend's self-test
viwo sanitize plan|apply|undo ...
viwo merge ...                    media merger, same options as the UI
viwo analyze <target> ...         (feature flag)
viwo capture ...                  (doc 11, feature flag)
viwo serve [--host --port]        starts the HTTP API + web UI (what Start.py does today)
global: --ini PATH --os K --profile P --features a,b --json --quiet --verbose
arms:   viwo static | dynamic | patching | system   lists that arm's commands;
        viwo <arm> <command> ... is viwo <command> ...; viwo -h groups every command by arm
--json prints the envelope on stdout; progress lines stay on stderr (only --quiet removes them)
exit codes: 0 ok, 1 job failed, 2 bad config/usage, 3 unsupported OS layer, 4 preflight, 130 cancelled
```

`Start.py` keeps working, as `viwo serve` with the default ini.

## 12.5 HTTP as a client of the core

- v1 routes (doc 4.1) become thin adapters. `/api/extract` submits a job and **waits** for it (as v1 does), so the existing UI is unchanged.
- New: `POST /api/jobs` (submit), `GET /api/jobs/<id>`, `GET /api/jobs/<id>/events?from=N` (polling; Server-Sent Events later), `POST /api/jobs/<id>/cancel`.
- Curation actions (sorting, trash, rename) are small and synchronous, and they stay as direct calls, not jobs.

## 12.5b Packaging (prototype)

- Python **3.11+** (doc 17.5); a `pyproject.toml` with a `viwo` console entry point. Runtime dependencies are pinned in a lock file. `pytest` is a dev-only dependency.
- External tools are found by the OS layer (PATH, `[tools]`) and pinned through a **tool lock file** (name, version, download URL, checksum) used by CI. Sparse-submodule vendoring follows at M11 (doc 10).
- No installer or packaged desktop app in the prototype.

## 12.6 Open questions

1. Should a job run in a worker thread or a separate process? A process isolates crashes in third-party Python libraries (UnityPy, native decoders) but makes cancellation and event streaming harder. My suggestion: threads for the prototype, with process isolation as an option per backend later.
2. Should run records be visible in the UI (history, "re-run with the same settings")?
3. Is a CLI name change acceptable now, or later?
