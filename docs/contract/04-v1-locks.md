# 4. HTTP API, workspace layout and configuration

> **Update (Prototype A):** the v1 application was removed. Its routes that the new UI
> and the media merger need were re-implemented in `viwo/api/` with the same JSON shapes;
> the rest (`/api/state`, `/api/session`, `/api/resume`, `/api/scan`, `/api/extensions`,
> `/api/detected-extensions`, `/api/assets-preview`, `/api/open-log-dir`, `/api/logs/load`)
> were dropped (normative: they do not come back). The "v1" names below describe where each
> shape came from.

These are the parts the current UI (`web/app.js`) and saved workspaces
depend on. They stay as they are; any change here bumps the contract's
**major** version.

## 4.1 HTTP API (frozen route set)

GET:
`/api/state`, `/api/status`, `/api/extensions`, `/api/detected-extensions`,
`/api/logs`, `/api/open-log-dir`, `/api/logs/load`, `/api/dependencies`,
`/api/assets-window?offset&limit`, `/api/assets-window-preview?path`,
`/api/session`, `/api/browse-folder?initialPath`, `/api/media-merger/state`,
`/preview/<encoded rel path>`, and static files.

POST:
`/api/extract`, `/api/scan`, `/api/keep-selected`, `/api/trash`,
`/api/restore`, `/api/delete`, `/api/clear-trash`, `/api/resume`,
`/api/assets-preview`, `/api/sort-keep`, `/api/sort-trash`, `/api/sort-undo`,
`/api/sort-rename`, `/api/logs/clear`, `/api/save-remaining-assets`,
`/api/open-folder` (origin-checked), `/api/media-merger/list`,
`/api/media-merger/build`, `/api/media-merger/browse-overlay`.

Error conventions (kept): handlers return `{"success": false, "error": "..."}`
with HTTP 200 for expected failures. Uncaught exceptions return HTTP 500
`{"error": "..."}`, invalid JSON returns 400, and an unknown POST route
returns 404.

**New routes (additive, proposed):**

| Route | Purpose |
|-------|---------|
| `GET /api/distro` | effective startup configuration (ini + sources), OS layer, contract version, features |
| `GET /api/plugins` | plugins with manifest, options schema, capabilities, load errors, dependency status |
| `POST /api/detect` | dry run: `{gamePath}` → every plugin's detection (`detections`), the auto pick (`auto`) and the selection for each mode (`modes.auto`, `modes.single` candidates, `modes.mixed.{detected,all,selected}`) |
| `POST /api/sanitizer/plan`, `/apply`, `/undo`; `GET /api/sanitizer/recipes` | doc 5 |
| `GET /api/analysis/targets`, `POST /api/analysis/run`, `GET /api/analysis/jobs` | doc 6: reserved for the analysis slot family (1.x); not served in 1.1 |
| `POST /api/jobs` `{kind, params}`, `GET /api/jobs`, `GET /api/jobs/<id>`, `GET /api/jobs/<id>/events?from=N`, `POST /api/jobs/<id>/cancel` | jobs (doc 12.5): generic submit onto the kind's own handler (extract, survey, repack, preflight, install, capture, cleanup); the kind-specific routes stay. The only cancellation route |

New *optional* fields on `/api/extract`: `extractionType` (already accepted
in v1 but never sent), `plugins`, `mixedPolicy`, `pluginOptions`, `onExisting`, `carve`.
Curated error convention: legacy-shaped routes answer HTTP 200 with `success: false` and a
`code`; envelope routes map the code to an HTTP status (`busy` → 409).

**Security model (overrides v1; H3 in doc 7).** Keeping v1's routes doesn't mean keeping their holes:

1. **Per-start API token.** The server generates a random token at startup and injects it into the served `index.html`. Every `/api/*` call must send it in an `X-VIWO-Token` header. A cross-site page can't read the token, and a custom header forces a CORS preflight, which the server refuses.
2. **Only JSON is accepted:** POSTs without `Content-Type: application/json` get 415.
3. **Host header check** (`127.0.0.1`, `localhost`, the configured host) to stop DNS rebinding.
4. **Path containment** for static files and `/preview/`: resolve, then require the path to stay inside its root (`/preview/` is relative to the *active* workspace, which also fixes F20).
5. The only change in the v1 UI is that its `api()` helper sends the token header.

**v1 route → core mapping:**

| v1 route(s) | Core call | Notes |
|-------------|-----------|-------|
| `/api/extract` | submit an `extract` job and **wait** for it | response shape unchanged (3.5) |
| `/api/media-merger/build` | submit a `merge` job and wait | long ffmpeg runs no longer block other requests' locks |
| `/api/scan`, `/api/keep-selected`, `/api/trash`, `/api/restore`, `/api/delete`, `/api/clear-trash`, `/api/sort-*`, `/api/save-remaining-assets`, `/api/assets-*`, `/api/resume` | synchronous workspace calls under the **workspace lock** (doc 12.3) | short operations; they get 409 `busy` if an extract job holds the lock |
| `/api/logs` | the last N lines of the server log ring buffer (events from every job plus server messages) | same `{logs: [...]}` shape |
| `/api/logs/clear` | clears the ring buffer view, not the job histories | |
| `/api/state`, `/api/status`, `/api/session`, `/api/extensions`, `/api/detected-extensions`, `/api/dependencies` | read-only core queries | |
| `/api/browse-folder`, `/api/media-merger/browse-overlay`, `/api/open-folder`, `/api/open-log-dir` | OS layer shell | |

## 4.2 `/api/dependencies` item shape

v1: `{id, label, required, available, category}`. All five keys stay. New
keys: `requirement` (required|recommended|optional), `location`, `hint`.
`category` now holds the owner id (`core`, `renpy`, `unity`, …). v1 used
`required` / `optional` / `unity`. The UI only displays this value, so the
change is safe.

## 4.3 Workspace layout and ownership

```
<workspace>/
  .viwo-workspace            ownership marker (JSON: app, id, created_by, created, contract; an
                             older empty or `{"app": "viwo"}` marker still counts as owned)
  <ext>/...                  files grouped by lowercased extension, no dot
  noext/...                  files without an extension
  .trash/groups/<ext>[_N]/   trashed extension groups ("group trash")
  .trash/items/<rel path>    files trashed in the sorting window ("item trash")
  .trash/merger/...          inputs trashed after a merger build
  .extraction_metadata/      reports; runs/<job_id>.json run records
  .sanitizer/                plans, cache, journal
  .analysis/<analyzer>/<target>/
```

- **Ownership (fixes H2):** the framework only ever **clears or replaces** content inside a folder that holds a `.viwo-workspace` marker it wrote. Pointing Step 2 at an arbitrary folder makes it a *read/curate* target only; extracting into it is refused unless it's empty, in which case the marker is created. The configured default workspace (`[server] workspace`) is owned by configuration and is claimed without the check.
- **Re-extraction policy (decided: ask every time).** When the target workspace is owned and not empty, the user chooses: **new** (a new workspace folder `<name>-<n>`), **replace** (replace the extension groups, keep `.extraction_metadata/runs/`, `.sanitizer/journal/` and `.trash/`), or **cancel**. HTTP: `/api/extract` takes an optional `onExisting: new|replace|cancel`. Without it, the response is `{success:false, needsDecision:true, options:[...]}` and the UI shows a dialog (a small v1 UI addition in M3). CLI: `--on-existing` is required in that situation; without it the command exits with code 2 and an explanation.
- **Three trash layouts, made explicit** (fixes F18): `groups/`, `items/`, `merger/`. v1 trees with the old layout are migrated once, on first open.
- **All top-level folders starting with `.` are reserved:** never listed, counted, sorted, merged, or trashed by "keep selected" (fixes F3).
- Collision naming stays as it is: `name__N.ext`; undo uses `name__undoN.ext`; group trash copies `<ext>_N`; restored groups `<ext>__N`.
- COLLECT dedupe: same size **and** same content hash means the file is skipped (v1 used mtime instead: F6).
- The active workspace starts as `[server] workspace` from the startup ini and follows `POST /api/workspace` (and the workspace of the last extraction) for the server's lifetime.

## 4.4 Progress and log format

- Plugins and core send `ProgressEvent { message, level, source, stage }`. Counts travel inside the message as `done / total` ("Scanned files: 1,200 / 4,100") or as a running count ("Scanned files: 12,400"); the web progress component parses both (`web/js/progress.js`).
- These are shown in the v1 UI as `[SOURCE:STAGE] message`, for example `[UNITY:EXPORT] UnityPy exported 120 asset(s)`. That matches lines v1 already prints, such as `[UNITY:DISCOVERY]` and `[PHASE 1]`.
- Lines are still added to the session log (`/api/logs`, which the UI polls) and to the daily log file `viwo-YYYY-MM-DD.log` under `[server] logs`.
- `secret` option values are masked before anything is sent.

## 4.5 Configuration: one file

Everything lives in the startup ini (doc 9); v1's `config.json` is gone.

| Section | Holds |
|---------|-------|
| `[server]` | `host`, `port`, `workspace` (default extraction workspace), `merged` (merger outputs), `logs`, `temp`; paths relative to the ini |
| `[startup]`, `[plugins]`, `[slots]`, `[tools]`, `[options.*]` | wiring (doc 9) |

Secrets (AES keys, encryption keys) are never stored in the ini or anywhere on disk.
They are passed per request or CLI call; run records store `<secret>` in their place,
so a replay asks for them again.

## 4.6 Session state

The `SESSIONS` store keeps its `__current__` session with `assetPath`,
`sortingHistory` (actions `keep`, `trash`, `rename` with v1 fields) and
`logs`. Contract change: appending to the log becomes a single locked
operation on the store. In v1, `progress_callback` reads the log, appends
and writes it back, which can lose lines when two requests run at once under
`ThreadingHTTPServer` (doc 7, F15; narrow in practice).

Prototype assumption, stated explicitly: **one local user**. There is one global UI session shared by every browser tab and the CLI. Multi-user or multi-session support is out of scope.
