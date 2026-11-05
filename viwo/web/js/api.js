// ViWo API client: token header, JSON bodies, envelope + legacy response handling.
const TOKEN = document.querySelector('meta[name="viwo-token"]')?.content || "";

export const hasToken = () => Boolean(TOKEN);

export class ApiError extends Error {
  constructor(message, info = {}) {
    super(message || "Request failed");
    this.code = info.code || "";
    this.hint = info.hint || "";
    this.owner = info.owner || "";
    this.payload = info.payload || null;
  }
}

async function request(method, url, body) {
  const opts = { method, headers: { "X-VIWO-Token": TOKEN } };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(url, opts);
  } catch {
    throw new ApiError("Server unreachable", { code: "offline", hint: "Is ViWo running? Start it with `viwo serve` (or Start.py), then reload." });
  }
  let json = null;
  try { json = await res.json(); } catch { /* non-JSON body */ }
  if (!json) throw new ApiError(`HTTP ${res.status} ${res.statusText}`, { code: "http" });
  return json;
}

/** New routes: {ok, data, error, warnings} envelope. Resolves to data. */
export async function v2(method, url, body) {
  const json = await request(method, url, body);
  if (json.ok === false || (json.error && json.ok === undefined)) {
    const err = json.error && typeof json.error === "object" ? json.error : { message: String(json.error || "") };
    throw new ApiError(err.message, { ...err, payload: json });
  }
  return json.data;
}

/** Legacy routes: plain JSON, {success:false, error} means failure. */
export async function v1(method, url, body) {
  const json = await request(method, url, body);
  if (json.success === false || (json.error && json.success === undefined)) {
    throw new ApiError(json.error, { code: json.code, hint: json.hint, payload: json });
  }
  return json;
}

export const api = {
  distro: () => v2("GET", "/api/distro"),
  plugins: () => v2("GET", "/api/plugins"),
  detect: (gamePath) => v2("POST", "/api/detect", { gamePath }),
  jobs: () => v2("GET", "/api/jobs"),
  job: (id) => v2("GET", `/api/jobs/${encodeURIComponent(id)}`),
  events: (id, from) => v2("GET", `/api/jobs/${encodeURIComponent(id)}/events?from=${from}`),
  cancel: (id) => v2("POST", `/api/jobs/${encodeURIComponent(id)}/cancel`, {}),
  extract: (payload) => v1("POST", "/api/extract", payload),
  survey: (folder, deep) => v1("POST", "/api/survey", { folder, deep }),
  browse: (initialPath = "") => v1("GET", `/api/browse-folder?initialPath=${encodeURIComponent(initialPath)}`),
  openFolder: (path) => v1("POST", "/api/open-folder", { path }),
  status: () => v1("GET", "/api/status"),
  group: (action, folder) => v1("POST", `/api/${action}`, { folder }),
  clearTrash: () => v1("POST", "/api/clear-trash", {}),
  keepSelected: (selectedExts) => v1("POST", "/api/keep-selected", { selectedExts }),
  assets: (offset, limit) => v1("GET", `/api/assets-window?offset=${offset}&limit=${limit}`),
  preview: (path) => v1("GET", `/api/assets-window-preview?path=${encodeURIComponent(path)}`),
  sort: (action, body = {}) => v1("POST", `/api/sort-${action}`, body),
  saveRemaining: (paths, destinationPath) => v1("POST", "/api/save-remaining-assets", { paths, destinationPath }),
  saveAll: (destinationPath) => v1("POST", "/api/save-remaining-assets", { all: true, destinationPath }),
  workspace: () => v1("GET", "/api/workspace"),
  setWorkspace: (path) => v1("POST", "/api/workspace", { path }),
  mergerState: () => v1("GET", "/api/media-merger/state"),
  mergerList: (body) => v1("POST", "/api/media-merger/list", body),
  mergerBuild: (body) => v1("POST", "/api/media-merger/build", body),
  mergerOverlay: (initialPath) => v1("POST", "/api/media-merger/browse-overlay", { initialPath }),
  logs: () => v1("GET", "/api/logs"),
  clearLogs: () => v1("POST", "/api/logs/clear", {}),
  deps: () => v1("GET", "/api/dependencies"),
  preflight: () => v1("POST", "/api/preflight", {}),
  installTool: (id) => v1("POST", "/api/preflight/install", { id }),
  recipes: () => v1("GET", "/api/sanitizer/recipes"),
  sanitize: (op, body = {}) => v1("POST", `/api/sanitizer/${op}`, body),
  repack: (body) => v1("POST", "/api/repack", body),
  browseFile: (initialPath = "") => v1("GET", `/api/browse-file?initialPath=${encodeURIComponent(initialPath)}`),
  captureWarnings: (gamePath) => v1("POST", "/api/capture/warnings", { gamePath }),
  capture: (body) => v1("POST", "/api/capture", body),
  analysisTargets: (gamePath) => v1("GET", `/api/analysis/targets?gamePath=${encodeURIComponent(gamePath)}`),
  analyze: (body) => v1("POST", "/api/analysis/run", body),
  openHandoff: (body) => v1("POST", "/api/analysis/open", body),
  diffAnalyses: (old, newer) => v1("POST", "/api/analysis/diff", { old, new: newer }),
  settings: () => v1("GET", "/api/settings"),
  saveSettings: (changes) => v1("POST", "/api/settings", changes),
  updates: () => v1("GET", "/api/updates"),
  workbooks: () => v1("GET", "/api/workbooks"),
  runbooks: () => v1("GET", "/api/runbooks"),
  runbookStep: (body) => v1("POST", "/api/runbooks/step", body),
  saveRunbook: (runbook) => v1("POST", "/api/runbooks/save", { runbook }),
  deleteRunbook: (id) => v1("POST", "/api/runbooks/delete", { id }),
  diag: () => v1("POST", "/api/diag", {}),
  updateIndexes: () => v1("POST", "/api/indexes/update", {}),
  surveys: () => v1("GET", "/api/surveys"),
  surveyReport: (id) => v1("GET", `/api/survey-report?id=${encodeURIComponent(id)}`),
  uiModules: () => v1("GET", "/api/ui-modules"),
  runtime: (kind, body) => v1("POST", `/api/runtime/${kind}`, body),
  attachTargets: (gamePath) => v1("GET", `/api/runtime/attach?gamePath=${encodeURIComponent(gamePath)}`),
  attach: (body) => v1("POST", "/api/runtime/attach", body),
  patch: (body) => v1("POST", "/api/patch", body),
  mod: (body) => v1("POST", "/api/mod", body),
};
