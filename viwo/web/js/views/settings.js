// 11 SETTINGS: the startup ini as a form (features, plugins, tool paths, options, slots).
// APPLY writes only what changed and reloads the runtime: no restart.
import { api } from "../api.js";
import { h, fill, btn, panel, viewHead, toast, toastErr, busy, emit, errorBox } from "../ui.js";
import { withSkeleton } from "../progress.js";
import { featuresForm, pluginsForm, toolsForm, optionsForm, slotsTable } from "./settings-form.js";

const S = { data: null, form: null, plugins: [], busy: false };
const el = {};
const clone = (v) => JSON.parse(JSON.stringify(v));

function mount(root) {
  el.features = h("div", {});
  el.plugins = h("div", {});
  el.tools = h("div", {});
  el.options = h("div", {});
  el.slots = h("div", {});
  el.sum = h("div", { class: "ab-sum mono" });
  el.why = h("span", { class: "ab-why" });
  el.apply = btn("APPLY + RELOAD", (e) => busy(e.currentTarget, apply), "primary lg");
  el.revert = btn("REVERT", (e) => busy(e.currentTarget, load), "ghost");
  root.append(
    viewHead("11", "SETTINGS", "Everything here is written to startup.ini and applied by reloading ViWo's tool bindings: no restart, no ini editing.",
      btn("RELOAD FORM", (e) => busy(e.currentTarget, load), "ghost")),
    h("div", { class: "grid2" },
      h("div", { class: "col" }, panel("11.A", "FEATURES + STARTUP", null, el.features), panel("11.B", "ENGINE PLUGINS", null, el.plugins), panel("11.D", "PLUGIN OPTIONS", null, el.options)),
      h("div", { class: "col" }, panel("11.C", "TOOL PATHS", null, el.tools), panel("11.E", "FORMATS (SLOTS)", null, el.slots))),
    h("div", { class: "actionbar" }, el.sum, el.why, el.revert, el.apply));
}

async function load() {
  try {
    const [data, plugins] = await withSkeleton(el.features, "READING STARTUP.INI…", () => Promise.all([api.settings(), api.plugins()]), 4);
    S.data = data;
    S.form = clone({ startup: data.startup, plugins: data.plugins, tools: data.tools, options: data.options });
    S.plugins = plugins;
  } catch (err) {
    S.data = null;
    fill(el.features, errorBox(err, "SETTINGS UNAVAILABLE", "startup.ini could not be read. Fix it by hand, then RELOAD FORM."));
    return;
  }
  render();
}

function render() {
  const d = S.data, f = S.form;
  const touch = () => bar();
  fill(el.features, featuresForm(f.startup, touch));
  fill(el.plugins, pluginsForm(f.plugins, d.pluginInfo, d.effective, touch));
  fill(el.tools, toolsForm(f.tools, touch));
  fill(el.options, optionsForm(f.options, S.plugins.filter((p) => f.plugins[p.id] !== false), touch));
  fill(el.slots, slotsTable(d.effective.slots, d.slots));
  bar();
}

/** Only the keys that differ from what the server read. */
function changes() {
  if (!S.data) return null;
  const out = {};
  const d = S.data, f = S.form;
  const startup = {};
  for (const k of Object.keys(f.startup)) if (JSON.stringify(f.startup[k]) !== JSON.stringify(d.startup[k])) startup[k] = f.startup[k];
  if (Object.keys(startup).length) out.startup = startup;
  for (const sec of ["plugins", "tools"]) {
    const diff = {};
    for (const k of Object.keys(f[sec])) if (f[sec][k] !== d[sec][k]) diff[k] = f[sec][k];
    if (Object.keys(diff).length) out[sec] = diff;
  }
  const options = {};
  for (const [pid, opts] of Object.entries(f.options)) {
    for (const [k, v] of Object.entries(opts)) if (String(v) !== String(d.options[pid]?.[k] ?? "")) (options[pid] ||= {})[k] = v;
  }
  if (Object.keys(options).length) out.options = options;
  return out;
}

function bar() {
  const c = changes();
  const n = c ? Object.values(c).reduce((s, sec) => s + Object.keys(sec).length, 0) : 0;
  el.sum.textContent = S.data ? `${S.data.ini} · ${n} change(s) pending` : "settings not loaded";
  el.why.textContent = S.busy ? "applying…" : !S.data ? "reload the form" : n ? "" : "nothing changed";
  el.apply.disabled = Boolean(el.why.textContent);
  el.revert.disabled = S.busy || !n;
}

async function apply() {
  const c = changes();
  if (!c || !Object.keys(c).length) return;
  S.busy = true;
  bar();
  try {
    const res = await api.saveSettings(c);
    const problems = res.problems || [];
    toast(problems.length ? `Applied with ${problems.length} note(s): ${problems[0]}` : "Applied. Tool bindings reloaded.", problems.length ? "warn" : "ok");
    emit("preflight");
    S.busy = false;
    await load();
  } catch (err) {
    S.busy = false;
    bar();
    toastErr(err, "Not applied: ");
  }
}

export default { mount, show: load };
