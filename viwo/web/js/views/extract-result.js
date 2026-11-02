// 01.F RESULT: counts, alarms, per-backend and per-plugin tables for one /api/extract response.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, errorBox, fmtNum, toast, toastErr } from "../ui.js";
import { stateBadge } from "./jobs.js";

const ALARM = "GAME FOLDER CHANGED";

export const stat = (label, value, sub = "") =>
  h("div", { class: "stat" }, h("span", { class: "lbl" }, label), h("b", { class: "mono" }, value), sub ? h("small", {}, sub) : null);

function table(head, rows, empty) {
  if (!rows.length) return h("p", { class: "dim" }, empty);
  return h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, head.map((c) => h("th", {}, c)))),
    h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c) => h("td", {}, c))))));
}

function alarm(lines) {
  return h("div", { class: "alarm", role: "alert" },
    h("b", {}, "⚠ ALARM // GAME FOLDER CHANGED DURING EXTRACTION"),
    h("p", {}, "ViWo never writes to the game folder. Something else did (a running game, sync tool or antivirus). Re-check the extracted assets."),
    lines.map((l) => h("p", { class: "mono" }, l)));
}

function pathRow(label, path, extra) {
  const open = btn("OPEN FOLDER", () => api.openFolder(path).then(() => toast("Opened in file manager.", "ok"), toastErr), "sm ghost");
  return h("div", { class: "kv" }, h("span", { class: "lbl" }, label),
    h("code", { class: "mono path" }, path || "—"), h("div", { class: "row" }, path ? open : null, extra));
}

function pluginRows(plugins) {
  return plugins.map((p) => [
    h("b", {}, p.id),
    h("span", { class: "mono" }, `${p.detection?.type || "?"} ${Math.round((p.detection?.confidence || 0) * 100)}%`),
    h("span", { class: "mono" }, fmtNum(p.exported)),
    h("span", { class: "mono" }, p.backend || "—"),
    p.error ? badge(p.error, "err") : p.warnings?.length ? badge(`${p.warnings.length} WARN`, "warn") : badge("OK", "ok"),
  ]);
}

function extChips(byExt) {
  const list = Object.entries(byExt || {});
  if (!list.length) return null;
  return h("div", { class: "extchips" }, list.map(([ext, n]) => h("span", { class: "ext" }, h("b", { class: "mono" }, ext), fmtNum(n))));
}

export function renderResult(host, res) {
  const r = res.result || {};
  const warnings = r.checks?.warnings || [];
  const alarms = warnings.filter((w) => w.includes(ALARM));
  const other = warnings.filter((w) => !w.includes(ALARM));
  const plugins = r.plugins || [];
  const status = alarms.length ? badge("ALARM", "err") : other.length ? badge(`${other.length} WARNINGS`, "warn") : badge("CHECKS OK", "ok");
  host.replaceChildren(panel("01.F", "RESULT", status,
    alarms.length ? alarm(alarms) : null,
    h("div", { class: "stats" },
      stat("COPIED", fmtNum(r.copiedFiles), "files to workspace"),
      stat("SCANNED", fmtNum(r.scannedFiles), "files inspected"),
      stat("ARCHIVES", `${fmtNum(r.archivesExtracted)}/${fmtNum(r.archivesFound)}`, "unpacked / found"),
      r.carvedFiles ? stat("CARVED", fmtNum(r.carvedFiles), "embedded files found") : null,
      stat("MODE", String(r.mode || "?").toUpperCase(), `extractor ${res.extractorType || r.extractorType || "?"}`)),
    extChips(r.copiedByExt),
    pathRow("WORKSPACE", res.assetPath, [h("a", { class: "btn sm", href: "#workspace" }, "GROUPS →"), h("a", { class: "btn sm", href: "#sort" }, "SORT →")]),
    other.length ? h("div", { class: "alert warn" }, h("b", {}, "WARNINGS"), h("ul", {}, other.map((w) => h("li", {}, w)))) : null,
    h("h4", { class: "sub-h" }, "// BY BACKEND"),
    table(["BACKEND", "FILES"], Object.entries(r.byBackend || {}).map(([k, v]) => [h("span", { class: "mono" }, k), h("span", { class: "mono" }, fmtNum(v))]), "No backend activity recorded."),
    h("h4", { class: "sub-h" }, "// PLUGIN RUNS"),
    table(["PLUGIN", "DETECTION", "EXPORTED", "BACKEND", "STATUS"], pluginRows(plugins), "No plugin ran."),
    plugins.flatMap((p) => (p.warnings || []).map((w) => h("p", { class: "note warn-text" }, `${p.id}: ${w}`))),
    r.runRecord ? pathRow("RUN RECORD", String(r.runRecord)) : null));
}

const EXPLAIN = {
  refused: "ViWo only writes into an empty folder or a folder it created itself, and never inside the game folder. Pick another workspace or empty this one.",
  invalid_request: "Check the game folder path and the selected mode.",
  busy: "Another job holds this workspace. Wait for it to finish (see 04 JOBS).",
  cancelled: "The extraction was cancelled. Nothing in the game folder was touched.",
};

export function renderFailure(host, err) {
  const title = { refused: "TARGET NOT OWNED BY VIWO", cancelled: "EXTRACTION CANCELLED" }[err.code] || "EXTRACTION FAILED";
  host.replaceChildren(panel("01.F", "RESULT", badge(String(err.code || "error").toUpperCase(), err.code === "cancelled" ? "warn" : "err"),
    errorBox(err, title),
    EXPLAIN[err.code] ? h("p", { class: "note" }, EXPLAIN[err.code]) : null));
}

const STEPS = [["01", "TARGET", "pick the game folder — opened read-only, never modified"],
  ["02", "DETECT", "see which engine plugin recognises it"], ["03", "RUN", "assets are copied into the active workspace"]];

function lastRun(job) {
  const r = job.result || {};
  const ws = String(r.workspace || String(r.runRecord || "").split(/[\\/]\.extraction_metadata/)[0]);
  return h("div", { class: "lastrun" },
    h("div", { class: "row" }, h("span", { class: "lbl" }, "// LAST RUN"), stateBadge(job.state), h("code", { class: "mono dim small" }, job.id)),
    job.error ? errorBox(job.error, "RUN FAILED") : h("div", { class: "stats" },
      stat("COPIED", fmtNum(r.copiedFiles)), stat("SCANNED", fmtNum(r.scannedFiles)),
      stat("ARCHIVES", `${fmtNum(r.archivesExtracted)}/${fmtNum(r.archivesFound)}`), stat("WARNINGS", fmtNum(r.checks?.warnings?.length || 0))),
    ws ? pathRow("WORKSPACE", ws) : null);
}

/** Idle LIVE FEED: last extract job summary + how it works. */
export async function renderIdle(host) {
  let last = null;
  try {
    const job = (await api.jobs()).filter((j) => j.kind === "extract").pop();
    if (job) last = await api.job(job.id);
  } catch { /* the summary is optional */ }
  fill(host, last ? lastRun(last) : h("p", { class: "dim" }, "No extraction yet in this server session."),
    h("span", { class: "lbl" }, "// HOW IT WORKS"),
    h("ol", { class: "how" }, STEPS.map(([n, t, d]) => h("li", {}, h("b", { class: "mono" }, n), h("span", {}, t), h("small", {}, d)))));
}
