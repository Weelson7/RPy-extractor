# 4. v1 locks: what the v1 UI depends on (and the fixes that override them)

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
| `POST /api/detect` | dry run: `{gamePath}` → every plugin's detection plus the selection for each mode |
| `POST /api/sanitizer/plan`, `/apply`, `/undo`; `GET /api/sanitizer/recipes` | doc 5 |
| `GET /api/analysis/targets`, `POST /api/analysis/run`, `GET /api/analysis/jobs` | doc 6 |
| `POST /api/jobs`, `GET /api/jobs/<id>`, `GET /api/jobs/<id>/events?from=N`, `POST /api/jobs/<id>/cancel` | jobs (doc 12.5). The only cancellation route |

New *optional* fields on `/api/extract`: `extractionType` (already accepted
in v1 but never sent), `plugins`, `mixedPolicy`, `pluginOptions`,
`sanitizeRecipe`, `sanitizeAutoApply`.

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
  .viwo-workspace            ownership marker (JSON: workspace id, created by, contract version)
  <ext>/...                  files grouped by lowercased extension, no dot
  noext/...                  files without an extension
  .trash/groups/<ext>[_N]/   trashed extension groups ("group trash")
  .trash/items/<rel path>    files trashed in the sorting window ("item trash")
  .trash/merger/...          inputs trashed after a merger build
  .extraction_metadata/      reports; runs/<job_id>.json run records
  .sanitizer/                plans, cache, journal
  .analysis/<analyzer>/<target>/
```

- **Ownership (fixes H2):** the framework only ever **clears or replaces** content inside a folder that holds a `.viwo-workspace` marker it wrote. Pointing Step 2 at an arbitrary folder makes it a *read/curate* target only; extracting into it is refused unless it's empty, in which case the marker is created.
- **Re-extraction policy (decided: ask every time).** When the target workspace is owned and not empty, the user chooses: **new** (a new workspace folder `<name>-<n>`), **replace** (replace the extension groups, keep `.extraction_metadata/runs/`, `.sanitizer/journal/` and `.trash/`), or **cancel**. HTTP: `/api/extract` takes an optional `onExisting: new|replace|cancel`. Without it, the response is `{success:false, needsDecision:true, options:[...]}` and the UI shows a dialog (a small v1 UI addition in M3). CLI: `--on-existing` is required in that situation; without it the command exits with code 2 and an explanation.
- **Three trash layouts, made explicit** (fixes F18): `groups/`, `items/`, `merger/`. v1 trees with the old layout are migrated once, on first open.
- **All top-level folders starting with `.` are reserved:** never listed, counted, sorted, merged, or trashed by "keep selected" (fixes F3).
- Collision naming stays as it is: `name__N.ext`; undo uses `name__undoN.ext`; group trash copies `<ext>_N`; restored groups `<ext>__N`.
- COLLECT dedupe: same size **and** same content hash means the file is skipped (v1 used mtime instead: F6).
- The active workspace is still the session's `assetPath`, falling back to `<tempPath>/<outputDir>`.

## 4.4 Progress and log format

- Plugins and core send `ProgressEvent { message, level, source, stage, current, total }`.
- These are shown in the v1 UI as `[SOURCE:STAGE] message`, for example `[UNITY:EXPORT] UnityPy exported 120 asset(s)`. That matches lines v1 already prints, such as `[UNITY:DISCOVERY]` and `[PHASE 1]`.
- Lines are still added to the session log (`/api/logs`, which the UI polls) and to the daily log file `rpy-extractor-YYYY-MM-DD.log`.
- `secret` option values are masked before anything is sent.

## 4.5 Configuration: one source of truth for each concern

| File | Holds | Changes |
|------|-------|---------|
| `config.json` | server and paths **only**: `host`, `port`, `tempPath`, `outputDir`, `mergerDir`, `webDir`, `logDir` | **unchanged from v1**; no new keys |
| startup ini (doc 9) | everything that wires the framework: OS layer, plugins, slot bindings, tool locations (`[tools]`, keyed by **backend id**), plugin options, features | new |

Secrets (AES keys, encryption keys) are never stored in either file. They're
passed per request or CLI call. Run records store only a **fingerprint** of
which key was used (a salted hash), so a replay asks for the key again.

## 4.6 Sessions

The `SESSIONS` store keeps its `__current__` session with `assetPath`,
`sortingHistory` (actions `keep`, `trash`, `rename` with v1 fields) and
`logs`. Contract change: appending to the log becomes a single locked
operation on the store. In v1, `progress_callback` reads the log, appends
and writes it back, which can lose lines when two requests run at once under
`ThreadingHTTPServer` (doc 7, F15; narrow in practice).

Prototype assumption, stated explicitly: **one local user**. There is one global UI session shared by every browser tab and the CLI. Multi-user or multi-session support is out of scope.
