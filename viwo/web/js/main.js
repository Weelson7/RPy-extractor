// App shell: theme, the global strip (SYSTEM, JOBS, SETTINGS, game, workspace), the three arms
// (STATIC, DYNAMIC, PATCHING) with a registry-driven rail per arm, router, status chips, dock.
import { api, hasToken } from "./api.js";
import * as ui from "./ui.js";
import { h, $, fill, pref, logLine, bus, emit, toastErr, seg } from "./ui.js";
import { ARMS, views, view, armViews, loadPluginModules, addonPanels } from "./registry.js";
import { currentGame, pickGame } from "./game.js";
import "./views/home.js";
import { setTheme } from "./theme.js";
import "./views/extract.js";
import "./views/workspace.js";
import "./views/sort.js";
import "./views/jobs.js";
import "./views/system.js";
import "./views/merger.js";
import "./views/survey.js";
import "./views/cleanup.js";
import "./views/repack.js";
import "./views/capture.js";
import "./views/analysis.js";
import "./views/settings.js";
import "./views/runtime.js";
import "./views/patches.js";
import { openWorkspaceDialog } from "./workspace-dialog.js";
import { landingWanted, runLanding } from "./landing.js";
import { KIND } from "./views/jobs.js";

const scroll = {};
const state = { arm: "", chips: "", current: "", distro: null, dockOpen: pref("dock") === "1", logCount: -1, lastLog: "" };

const link = (v, i) => h("a", { href: `#${v.id}`, "data-view": v.id, title: `${v.title} — ${v.subtitle}` },
  h("b", {}, v.num || String(i + 1).padStart(2, "0")), h("span", {}, v.title, h("small", {}, v.subtitle)));

/** The arm switch, the global strip and one section per registered view (core and add-ons). */
function buildShell() {
  state.armSeg = seg(ARMS.map((a) => [a.id, a.title]), "", (id) => { location.hash = `#${id}`; }, { "aria-label": "Arms" });
  fill($("#arms"), state.armSeg);
  fill($("#strip"), armViews("global").map((v) => h("a", { class: "chip", href: `#${v.id}`, "data-view": v.id, title: v.subtitle },
    h("i", {}), h("b", {}, v.title))));
  fill($("#main"), views().map((v) => h("section", { class: "view", id: `view-${v.id}`, hidden: true })));
}

/** The rail lists one arm's views; a global view keeps the arm the user was in. */
function showArm(arm) {
  if (arm === state.arm) return;
  state.arm = arm;
  state.armSeg.set(arm);
  fill($("#mods"), armViews(arm).map((v, i) => h("li", {}, link(v, i))));
}

function route() {
  const want = location.hash.slice(1);
  const id = view(want) ? want : ARMS[0].id;
  const arm = view(id).arm;
  showArm(arm === "global" ? state.arm || ARMS[0].id : arm);
  if (state.current === id) return;
  if (state.current) {
    scroll[state.current] = $("#main").scrollTop;
    view(state.current).hide?.();
    $(`#view-${state.current}`).hidden = true;
  }
  state.current = id;
  const el = $(`#view-${id}`);
  if (!el.dataset.mounted) {
    view(id).mount(el);
    el.append(...addonPanels(id, { root: el, api, ui })); // plugin panels, after the view's own
    el.dataset.mounted = "1";
  }
  el.hidden = false;
  $("#main").scrollTop = scroll[id] || 0;
  view(id).show?.();
  document.querySelectorAll("#mods a, #strip a").forEach((a) => {
    if (a.dataset.view === id) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  document.title = `${view(id).title} // ViWo`;
  pref("view", id);
}

const chip = (label, value, kind = "", href = "") =>
  h(href ? "a" : "span", { class: "chip", "data-kind": kind || null, href: href || null }, h("i", {}), h("b", {}, label), h("span", {}, value));

function renderChips(jobList) {
  const d = state.distro;
  const running = (jobList || []).filter((j) => j.state === "running" || j.state === "queued");
  const slots = d ? Object.values(d.slots || {}) : [];
  const bound = slots.filter((s) => s.main).length;
  const sig = JSON.stringify([d && d.os, bound, running.map((j) => j.kind), Boolean(jobList)]);
  if (sig === state.chips) return; // the strip is a live region: re-render only on change
  state.chips = sig;
  fill($("#status-chips"),
    chip("OS", d ? String(d.os).toUpperCase() : "…", d ? "ok" : ""),
    chip("PLUGINS", d ? String(d.plugins.length) : "…", d ? "ok" : ""),
    Object.assign(chip("FORMATS", d ? `${bound}/${slots.length} READY` : "…", d && bound === slots.length ? "ok" : "", "#system"), {
      title: "Formats ViWo can handle right now. The rest need an optional tool: ViWo skips those formats until it is installed. Click for 05 SYSTEM." }),
    running.length
      ? chip("RUNNING", `${(KIND[running[0].kind]?.[0] || running[0].kind).toUpperCase()}${running.length > 1 ? ` +${running.length - 1}` : ""}`, "live", "#jobs")
      : chip("JOB", jobList ? "IDLE" : "…", "", "#jobs"));
}

async function pollStatus() {
  try {
    if (!state.distro) bus.distro = state.distro = await api.distro();
    renderChips(await api.jobs());
  } catch (err) {
    state.chips = "";
    fill($("#status-chips"), Object.assign(chip("SERVER", err.code === "offline" ? "OFFLINE" : "ERROR", "err"),
      { title: "ViWo's server does not answer. Start it again (viwo serve, or Start.py), then reload." }));
  }
}

function refreshGame() {
  const path = currentGame();
  $("#game-sel").textContent = path ? `‎${path}‎` : "—";
  $("#game-sel").title = path;
}

async function refreshWorkspacePath() {
  try {
    const res = await api.workspace();
    $("#ws-path").textContent = res.path ? `‎${res.path}‎` : "—";
    $("#ws-path").title = res.path || "";
    bus.ws = res;
    emit("wspath", res);
  } catch { /* chip shows link state */ }
}

function setDock(open) {
  state.dockOpen = open;
  pref("dock", open ? "1" : "0");
  $("#dock-body").hidden = !open;
  $("#dock").dataset.state = open ? "open" : "";
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
    fill(body, lines.slice(-500).map((l) => logLine(l)));
    if (!lines.length) body.append(h("span", { class: "ln dim" }, "// no activity yet — run an extraction or a workspace action"));
    $("#dock-count").textContent = `${lines.length} LINES`;
    if (stick) body.scrollTop = body.scrollHeight;
  } catch { /* status chip reports link problems */ }
}

async function boot() {
  setTheme(pref("theme") || "wormhole");
  if (!hasToken()) {
    $("#main").prepend(h("div", { class: "alert", "data-kind": "err" }, h("b", {}, "NO API TOKEN"),
      h("p", {}, "This page was not opened from ViWo's server, so nothing will load. Start ViWo with `viwo serve` (or Start.py) and open the address it prints.")));
  } else await loadPluginModules(api, ui); // add-on views and panels register before the shell is built
  buildShell();
  $("#dock-toggle").addEventListener("click", () => setDock(!state.dockOpen));
  $("#ws-btn").addEventListener("click", openWorkspaceDialog);
  $("#game-btn").addEventListener("click", pickGame);
  bus.addEventListener("game", refreshGame);
  refreshGame();
  $("#dock-clear").addEventListener("click", () => api.clearLogs().then(() => { state.logCount = -1; pollLogs(); }, toastErr));
  window.addEventListener("hashchange", route);
  bus.addEventListener("workspace", refreshWorkspacePath);
  bus.addEventListener("jobs", pollStatus);
  bus.addEventListener("preflight", () => { state.distro = null; state.chips = ""; pollStatus(); });
  if (!location.hash && pref("view")) location.hash = pref("view");
  route();
  setDock(state.dockOpen);
  pollStatus();
  refreshWorkspacePath();
  setInterval(pollStatus, 3000);
  setInterval(pollLogs, 1500);
  if (hasToken() && landingWanted()) runLanding(); // first load only: the real preflight, then the app
}

boot();
