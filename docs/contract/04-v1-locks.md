# 4. v1 locks: what must not change

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
| `GET /api/distro` | active distro manifest, kernel, contract version, features |
| `GET /api/plugins` | plugins with manifest, options schema, capabilities, load errors, dependency status |
| `POST /api/detect` | dry run: `{gamePath}` → every plugin's detection plus the selection for each mode |
| `POST /api/sanitizer/plan`, `/apply`, `/undo`; `GET /api/sanitizer/recipes` | doc 5 |
| `GET /api/analysis/targets`, `POST /api/analysis/run`, `GET /api/analysis/jobs` | doc 6 |
| `POST /api/cancel` | `{requestId}`, uses the cancel token |

New *optional* fields on `/api/extract`: `extractionType` (already accepted
in v1 but never sent), `plugins`, `mixedPolicy`, `pluginOptions`,
`sanitizeRecipe`, `sanitizeAutoApply`.

## 4.2 `/api/dependencies` item shape

v1: `{id, label, required, available, category}`. All five keys stay. New
keys: `requirement` (required|recommended|optional), `location`, `hint`.
`category` now holds the owner id (`core`, `renpy`, `unity`, …). v1 used
`required` / `optional` / `unity`. The UI only displays this value, so the
change is safe.

## 4.3 Workspace layout

```
<workspace>/
  <ext>/...                  files grouped by lowercased extension, no dot
  noext/...                  files without an extension
  .trash/<ext>[_N]/...       trashed extension folders (folder-level trash)
  .trash/<rel path>          files trashed one by one in the sorting window
  .extraction_metadata/      manifests and reports (JSON)
  .sanitizer/                sanitizer plans, cache and reports      (new)
  .analysis/<analyzer>/<target>/   decompiler output              (new)
```

- **All top-level folders starting with `.` are reserved.** They are never listed as extensions or counted, never shown in the sorting window, and never picked up by the merger.
- Collision naming stays as it is: `name.ext` → `name__1.ext` → `name__2.ext`. Undo uses `name__undoN.ext`. Trash folder copies use `<ext>_N`, and restored folders use `<ext>__N`.
- COLLECT dedupe stays as it is: same size and same whole-second mtime means the file is skipped.
- The active workspace is still the session's `assetPath`, falling back to `<tempPath>/<outputDir>` (v1 `api.common.assets_dir`).

## 4.4 Progress and log format

- Plugins and core send `ProgressEvent { message, level, source, stage, current, total }`.
- These are shown in the v1 UI as `[SOURCE:STAGE] message`, for example `[UNITY:EXPORT] UnityPy exported 120 asset(s)`. That matches lines v1 already prints, such as `[UNITY:DISCOVERY]` and `[PHASE 1]`.
- Lines are still added to the session log (`/api/logs`, which the UI polls) and to the daily log file `rpy-extractor-YYYY-MM-DD.log`.
- `secret` option values are masked before anything is sent.

## 4.5 Config (`config.json`)

v1 keys stay: `host`, `port`, `tempPath`, `outputDir`, `mergerDir`, `webDir`,
`logDir`. New optional keys:

```json
{
  "distro": "auto-mixed",
  "pluginDirs": ["./plugins"],
  "tools": { "sevenzip": "C:/Tools/7z.exe", "ghidra": "/opt/ghidra" },
  "pluginOptions": { "unreal": { "engineVersion": "UE5.3" } }
}
```

Secrets are **not** saved in `config.json`. They are only sent with each request.

## 4.6 Sessions

The `SESSIONS` store keeps its `__current__` session with `assetPath`,
`sortingHistory` (actions `keep`, `trash`, `rename` with v1 fields) and
`logs`. Contract change: appending to the log becomes a single locked
operation on the store. In v1, `progress_callback` reads the log, appends
and writes it back, which can lose lines when two requests run at once under
`ThreadingHTTPServer` (doc 7, F7).
