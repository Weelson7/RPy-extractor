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
  info() -> DistroInfo                       # effective ini, kernel, plugins, slots, problems
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
- **Concurrency** ❓: jobs that write the same workspace are serialized; read-only jobs (detect, sanitize plan, analysis) can run in parallel. Is a simple per-workspace lock enough for the prototype? Probably yes.
- **Cancellation** uses the CancelToken (doc 1.1 kills the process tree).

## 12.4 CLI sketch

The command name is a placeholder (`rpyx`). The name "RPy Extractor"
undersells a multi-engine framework; renaming is your call ❓.

```
rpyx info                         distro, kernel, plugins, slot bindings, dependency status
rpyx detect <game>                detections + chosen plugin(s) per mode
rpyx extract <game> [--plugin ID | --mixed ID,ID | --policy selected|detected|all]
                    [--exts .png,.ogg] [--workspace DIR] [--option plugin.key=value]
rpyx unpack <archive> [--slot unarchive.7z] [--backend main|spare|ID]
rpyx slots [--check]              bindings; --check runs each backend's self-test
rpyx sanitize plan|apply|undo ...
rpyx merge ...                    media merger, same options as the UI
rpyx analyze <target> ...         (feature flag)
rpyx capture ...                  (doc 11, feature flag)
rpyx serve [--host --port]        starts the HTTP API + web UI (what Start.py does today)
global: --ini PATH --kernel K --profile P --json --quiet --verbose
exit codes: 0 ok, 1 job failed, 2 bad config/usage, 3 unsupported kernel, 4 preflight, 130 cancelled
```

`Start.py` keeps working, as `rpyx serve` with the default ini.

## 12.5 HTTP as a client of the core

- v1 routes (doc 4.1) become thin adapters. `/api/extract` submits a job and **waits** for it (as v1 does), so the existing UI is unchanged.
- New: `POST /api/jobs` (submit), `GET /api/jobs/<id>`, `GET /api/jobs/<id>/events?from=N` (polling; Server-Sent Events later), `POST /api/jobs/<id>/cancel`.
- Curation actions (sorting, trash, rename) are small and synchronous, and they stay as direct calls, not jobs.

## 12.6 Open questions

1. Should a job run in a worker thread or a separate process? A process isolates crashes in third-party Python libraries (UnityPy, native decoders) but makes cancellation and event streaming harder. My suggestion: threads for the prototype, with process isolation as an option per backend later.
2. Should run records be visible in the UI (history, "re-run with the same settings")?
3. Is a CLI name change acceptable now, or later?
