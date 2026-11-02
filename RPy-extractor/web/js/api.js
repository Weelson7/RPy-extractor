// ViWo API client: token header, JSON bodies, envelope + legacy response handling.
const TOKEN = document.querySelector('meta[name="rpyx-token"]')?.content || "";

export const hasToken = () => Boolean(TOKEN);

export class ApiError extends Error {
  constructor(message, info = {}) {
    super(message || "Request failed");
    this.code = info.code || "";
    this.hint = info.hint || info.details || "";
    this.owner = info.owner || "";
    this.payload = info.payload || null;
  }
}

async function request(method, url, body) {
  const opts = { method, headers: { "X-RPYX-Token": TOKEN } };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(url, opts);
  } catch {
    throw new ApiError("Server unreachable", { code: "offline", hint: "Is ViWo running? Start it with python3 Start.py" });
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
    throw new ApiError(json.error, { code: json.code, details: json.details, payload: json });
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
  logs: () => v1("GET", "/api/logs"),
  clearLogs: () => v1("POST", "/api/logs/clear", {}),
  deps: () => v1("GET", "/api/dependencies"),
};
