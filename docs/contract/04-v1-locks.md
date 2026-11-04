# 4. HTTP API, workspace layout and configuration

The web UI and saved workspaces depend on what this document fixes. A change to a route shape or
to the workspace layout bumps the contract major.

## 4.1 HTTP API

`viwo serve` (`viwo/api/server.py`) serves the UI, the API, `/preview/<rel path>` and
`/plugins/<id>/ui.js`. Two response shapes exist:

- **Legacy-shaped routes** (`viwo/api/handlers*.py`): plain JSON; an expected failure is HTTP 200
  with `{success: false, error, code, hint}`; the UI reads them with `v1()` in `js/api.js`.
- **Envelope routes** (`viwo/api/routes.py`): the doc 12.3b envelope with the HTTP status from
  the error code (`invalid_request` 400, `refused` 403, `not_found` 404, `busy` 409, `offline`
  503, `internal` 500); the UI reads them with `v2()`.

An unknown route is 404; an uncaught exception is 500 `{"error": "internal error"}` (the trace
goes to the log); invalid JSON is 400.

| Area | GET | POST |
|------|-----|------|
| envelope | `/api/distro`, `/api/plugins`, `/api/jobs`, `/api/jobs/<id>`, `/api/jobs/<id>/events?from=N` | `/api/detect`, `/api/jobs/<id>/cancel` |
| jobs | | `/api/jobs` `{kind, params}` (doc 12.5) |
| extraction | | `/api/extract` |
| workspace | `/api/status`, `/api/workspace`, `/api/assets-window?offset&limit`, `/api/assets-window-preview?path`, `/api/browse-folder?initialPath`, `/api/browse-file?initialPath` | `/api/workspace`, `/api/trash`, `/api/restore`, `/api/delete`, `/api/clear-trash`, `/api/keep-selected`, `/api/sort-keep`, `/api/sort-trash`, `/api/sort-undo`, `/api/sort-rename`, `/api/save-remaining-assets`, `/api/open-folder` |
| merger | `/api/media-merger/state` | `/api/media-merger/list`, `/api/media-merger/build`, `/api/media-merger/browse-overlay` |
| survey, cleanup, repack | `/api/surveys`, `/api/survey-report?id`, `/api/sanitizer/recipes` | `/api/survey`, `/api/sanitizer/plan`, `/api/sanitizer/apply`, `/api/sanitizer/undo`, `/api/repack` |
| analysis | `/api/analysis/targets?gamePath` | `/api/analysis/run`, `/api/analysis/open`, `/api/analysis/diff` |
| dynamic | | `/api/capture/warnings`, `/api/capture`, `/api/runtime/dump`, `/api/runtime/trace`, `/api/runtime/agent`, `/api/runtime/record` |
| system | `/api/dependencies`, `/api/settings`, `/api/updates`, `/api/ui-modules`, `/api/logs` | `/api/preflight`, `/api/preflight/install`, `/api/settings`, `/api/diag`, `/api/indexes/update`, `/api/logs/clear` |

Patch sets and mods are job kinds of `POST /api/jobs` (`patch`, `mod`); they have no route of
their own (CONFORMANCE: the 14 PATCHES + MODS view calls `/api/patch` and `/api/mod`).

`POST /api/detect {gamePath}` answers every plugin's detection (`detections`), the auto pick
(`auto`) and the selection per mode (`modes.auto`, `modes.single`, `modes.mixed.{detected, all,
selected}`). `GET /api/plugins` lists id, name, version, engineType, builtin, tosSensitive,
description, capabilities, options, slots, dependencies, error, loaded.

`/api/extract` accepts the fields of doc 3.2. When the workspace is owned and not empty and no
`onExisting` was sent, it answers `{success: false, needsDecision: true, options: [...]}`.

**Security model** (`tests/test_server.py`):

1. **Per-start token:** generated at startup, injected into the served `index.html` as `<meta
   name="viwo-token">`; every `/api/*` request sends it as `X-VIWO-Token` (compared in constant
   time). Missing or wrong: 403.
2. **JSON only:** a POST without `Content-Type: application/json` gets 415; a body over 16 MiB
   or a malformed length gets 413.
3. **Host check:** the Host header must name this machine (`127.0.0.1`, `localhost`, `[::1]`, or
   the address the server was bound to) and the peer must be this machine unless the server was
   bound to one LAN address on purpose; otherwise 403 (DNS rebinding).
4. **Binding:** `[server] host` defaults to `127.0.0.1`; `viwo serve --host` overrides it.
5. **Path containment:** static files, `/preview/` (relative to the active workspace, byte ranges
   supported) and `/plugins/<id>/ui/<file>` resolve inside their root or answer 404.

## 4.2 `/api/dependencies` item

`{id, label, kind, available, required, category, requirement, location, hint, installable,
onDemand}`; `category` is the owning plugin or `core`.

## 4.3 Workspace layout and ownership

```
<workspace>/
  .viwo-workspace            ownership marker (JSON: app, id, created_by, created, contract;
                             an empty or {"app": "viwo"} marker also counts)
  <ext>/...                  files grouped by lowercased extension, no dot
  noext/...                  files without an extension
  .trash/groups/<ext>[_N]/   group trash
  .trash/items/<rel path>    item trash (sorting window)
  .trash/merger/...          merger inputs trashed after a build
  .extraction_metadata/      provenance.jsonl; runs/<job id>.json and capture-<stamp>.json
  .sanitizer/                plans and journals (doc 5)
  .analysis/<analyzer>/<target key>/    analyzer output (doc 6); .analysis/diff/<old>--<new>/
  .runtime/{dump,trace,audio,agent}/... dynamic-arm output (doc 11)
```

- **Ownership:** ViWo clears or replaces content only inside a folder holding a marker it wrote.
  Extracting into a non-empty folder without the marker is refused; an empty folder is claimed.
  The configured default workspace (`[server] workspace`) is claimed without the check.
- **Re-extraction (ask every time):** into an owned, non-empty workspace the user chooses **new**
  (`<name>-<n>`), **replace** (the extension groups are replaced; `.extraction_metadata/runs/`,
  `.sanitizer/` and `.trash/` stay) or **cancel**. CLI: `--on-existing`; without it the command
  exits 2 with the explanation.
- **Reserved:** every top-level folder starting with `.` is never listed, counted, sorted,
  merged, or trashed by retain groups.
- **Names:** collisions `name__N.ext`; undo `name__undoN.ext`; group trash `<ext>_N`; restored
  groups `<ext>__N`. v1 trash trees are migrated to the three areas on first open.
- **Lock:** one lock per workspace, in-process and across processes
  (`.extraction_metadata/lock`); writing jobs hold it (doc 12.3). A workspace folder created for
  a job gets the lock too and is removed again when left empty.
- **Active workspace:** starts as `[server] workspace` and follows `POST /api/workspace` and the
  last extraction for the server's lifetime.
- The Ghidra project of an analysis lives beside the workspace in `<workspace>.ghidra/<key>/`
  (Ghidra refuses project paths with a dot folder).

## 4.4 Progress and log lines

- Core and plugins emit `ProgressEvent { message, level, source, stage }`. Counts travel in the
  message as `done / total` or a running count; `web/js/progress.js` parses both.
- A line reads `[SOURCE:STAGE] message`, e.g. `[UNITY:EXPORT] UnityPy exported 120 asset(s)`.
- Lines go to the job's event stream, the server's ring buffer (`/api/logs`) and the daily log
  file `viwo-YYYY-MM-DD.log` under `[server] logs`. The CLI prints them on stderr (`--quiet`
  removes them; `--json` keeps them on stderr).
- `secret` option values and found keys are masked before anything is emitted.

## 4.5 Configuration

Everything is in the startup ini (doc 9). `[server]`: `host`, `port`, `workspace`, `merged`,
`logs`, `temp`, relative to the ini. Secrets are never stored in the ini or anywhere on disk;
they travel per request or CLI call, and run records store `<secret>` so a replay asks again.

## 4.6 UI session

One local user: one in-memory UI state (active workspace, sorting history for undo, log ring
buffer) shared by every browser tab and lost on restart. Anything that must survive a restart
has its own store (run records, sanitizer journals, survey reports in `viwo-data/surveys/`).
