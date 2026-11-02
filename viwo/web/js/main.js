// App shell: hash router, top-bar status chips, workspace path, activity console dock.
import { api, hasToken } from "./api.js";
import { h, $, pref, logLine, bus, emit, toastErr } from "./ui.js";
import extract from "./views/extract.js";
import workspace from "./views/workspace.js";
import sort from "./views/sort.js";
import jobs from "./views/jobs.js";
import system from "./views/system.js";
import merger from "./views/merger.js";
import survey from "./views/survey.js";
import cleanup from "./views/cleanup.js";
import repack from "./views/repack.js";
import { openWorkspaceDialog } from "./workspace-dialog.js";
import { KIND } from "./views/jobs.js";

const VIEWS = { extract, workspace, sort, jobs, system, merger, survey, cleanup, repack };
const scroll = {};
const state = { chips: "", current: "", distro: null, dockOpen: pref("dock") === "1", logCount: -1, lastLog: "" };

function route() {
  const want = location.hash.slice(1);
  const id = want in VIEWS ? want : "extract";
  if (state.current === id) return;
  if (state.current) {
    scroll[state.current] = $("#main").scrollTop;
    VIEWS[state.current].hide?.();
    $(`#view-${state.current}`).hidden = true;
  }
  state.current = id;
  const el = $(`#view-${id}`);
  if (!el.dataset.mounted) {
    VIEWS[id].mount(el);
    el.dataset.mounted = "1";
  }
  el.hidden = false;
  $("#main").scrollTop = scroll[id] || 0;
  VIEWS[id].show?.();
  document.querySelectorAll(".mods a").forEach((a) => {
    if (a.dataset.view === id) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  document.title = `${id.toUpperCase()} // ViWo`;
  pref("view", id);
}

const chip = (label, value, kind = "", href = "") =>
  h(href ? "a" : "span", { class: `chip ${kind}`, href: href || null }, h("i", {}), h("b", {}, label), h("span", {}, value));

function renderChips(jobList) {
  const d = state.distro;
  const running = (jobList || []).filter((j) => j.state === "running" || j.state === "queued");
  const slots = d ? Object.values(d.slots || {}) : [];
  const bound = slots.filter((s) => s.main).length;
  const sig = JSON.stringify([d && d.os, bound, running.map((j) => j.kind), Boolean(jobList)]);
  if (sig === state.chips) return; // the strip is a live region: re-render only on change
  state.chips = sig;
  $("#status-chips").replaceChildren(
    chip("OS", d ? String(d.os).toUpperCase() : "…", d ? "ok" : ""),
    chip("PLUGINS", d ? String(d.plugins.length) : "…", d ? "ok" : ""),
    Object.assign(chip("FORMATS", d ? `${bound}/${slots.length} READY` : "…", d && bound === slots.length ? "ok" : "", "#system"), {
      title: "Formats ViWo can handle right now. The rest need an optional tool: ViWo skips those formats until it is installed. Click for 05 SYSTEM." }),
    running.length
      ? chip("RUNNING", `${(KIND[running[0].kind]?.[0] || running[0].kind).toUpperCase()}${running.length > 1 ? ` +${running.length - 1}` : ""}`, "live", "#jobs")
      : chip("JOB", jobList ? "IDLE" : "…", "", "#jobs"),
  );
}

async function pollStatus() {
  try {
    if (!state.distro) bus.distro = state.distro = await api.distro();
    renderChips(await api.jobs());
  } catch (err) {
    state.chips = "";
    $("#status-chips").replaceChildren(Object.assign(chip("SERVER", err.code === "offline" ? "OFFLINE" : "ERROR", "err"),
      { title: "ViWo's server does not answer. Start it again (python3 Start.py), then reload." }));
  }
}

async function refreshWorkspacePath() {
  try {
    const res = await api.workspace();
    $("#ws-path").textContent = res.path ? `\u200e${res.path}\u200e` : "—";
    $("#ws-path").title = res.path || "";
    bus.ws = res;
    emit("wspath", res);
  } catch { /* chip shows link state */ }
}

function setDock(open) {
  state.dockOpen = open;
  pref("dock", open ? "1" : "0");
  $("#dock-body").hidden = !open;
  $("#dock").classList.toggle("open", open);
  $("#dock-toggle").setAttribute("aria-expanded", String(open));
  if (open) pollLogs();
}

async function pollLogs() {
  if (!state.dockOpen || document.hidden) return;
  try {
    const lines = (await api.logs()).logs || [];
    const last = lines[lines.length - 1] || "";
    if (lines.length === state.logCount && last === state.lastLog) return;
    state.logCount = lines.length;
    state.lastLog = last;
    const body = $("#dock-body");
    const stick = body.scrollHeight - body.scrollTop - body.clientHeight < 40;
    body.replaceChildren(...lines.slice(-500).map((l) => logLine(l)));
    if (!lines.length) body.append(h("span", { class: "ln dim" }, "// no activity yet — run an extraction or a workspace action"));
    $("#dock-count").textContent = `${lines.length} LINES`;
    if (stick) body.scrollTop = body.scrollHeight;
  } catch { /* status chip reports link problems */ }
}

function boot() {
  if (!hasToken()) {
    $("#main").prepend(h("div", { class: "alert err" }, h("b", {}, "NO API TOKEN"),
      h("p", {}, "This page was not opened from ViWo's server, so nothing will load. Start ViWo with python3 Start.py and open the address it prints.")));
  }
  document.querySelectorAll(".mods a").forEach((a) => { a.title = a.querySelector("span").textContent.replace(/^([A-Z ]+)/, "$1 — "); });
  $("#dock-toggle").addEventListener("click", () => setDock(!state.dockOpen));
  $("#ws-btn").addEventListener("click", openWorkspaceDialog);
  $("#dock-clear").addEventListener("click", () => api.clearLogs().then(() => { state.logCount = -1; pollLogs(); }, toastErr));
  window.addEventListener("hashchange", route);
  bus.addEventListener("workspace", refreshWorkspacePath);
  bus.addEventListener("jobs", pollStatus);
  if (!location.hash && pref("view")) location.hash = pref("view");
  route();
  setDock(state.dockOpen);
  pollStatus();
  refreshWorkspacePath();
  setInterval(pollStatus, 3000);
  setInterval(pollLogs, 1500);
}

boot();
