// App shell: hash router, top-bar status chips, workspace path, activity console dock.
import { api, hasToken } from "./api.js";
import { h, $, pref, logLine, bus, toastErr } from "./ui.js";
import extract from "./views/extract.js";
import workspace from "./views/workspace.js";
import sort from "./views/sort.js";
import jobs from "./views/jobs.js";
import system from "./views/system.js";

const VIEWS = { extract, workspace, sort, jobs, system };
const state = { current: "", distro: null, dockOpen: pref("dock") === "1", logCount: -1, lastLog: "" };

function route() {
  const want = location.hash.slice(1);
  const id = want in VIEWS ? want : "extract";
  if (state.current === id) return;
  if (state.current) {
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
  $("#status-chips").replaceChildren(
    chip("OS", d ? String(d.os).toUpperCase() : "…", d ? "ok" : ""),
    chip("PLUGINS", d ? String(d.plugins.length) : "…", d ? "ok" : ""),
    chip("SLOTS", d ? `${bound}/${slots.length} BOUND` : "…", d && bound < slots.length ? "warn" : "ok", "#system"),
    running.length
      ? chip("JOB", `${running[0].kind.toUpperCase()} ${running[0].state.toUpperCase()}`, "live", "#jobs")
      : chip("JOB", jobList ? "IDLE" : "…", "", "#jobs"),
  );
}

async function pollStatus() {
  try {
    if (!state.distro) state.distro = await api.distro();
    renderChips(await api.jobs());
  } catch (err) {
    $("#status-chips").replaceChildren(chip("LINK", err.code === "offline" ? "OFFLINE" : "ERROR", "err"));
  }
}

async function refreshWorkspacePath() {
  try {
    const res = await api.assets(0, 1);
    $("#ws-path").textContent = res.assetPath || "—";
    $("#ws-path").title = res.assetPath || "";
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
      h("p", {}, "This page was not served by the ViWo server, so API calls will be rejected. Open http://127.0.0.1:8081/ instead.")));
  }
  $("#dock-toggle").addEventListener("click", () => setDock(!state.dockOpen));
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
