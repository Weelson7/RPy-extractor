// 01 EXTRACT: target, detection, mode, plugin options, filter, run + live feed.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, meter, viewHead, toast, toastErr, busy, pref, logLine, emit, modal, errorBox, pad, fmtNum } from "../ui.js";
import { renderResult, renderFailure } from "./extract-result.js";

const PRESETS = {
  IMAGES: ".png .jpg .jpeg .webp .gif .bmp",
  AUDIO: ".ogg .mp3 .wav .opus .flac .m4a",
  VIDEO: ".webm .mp4 .mkv .mov .avi",
  TEXT: ".txt .json .rpy .xml .csv",
};
const POLICIES = {
  selected: "only the plugins picked below",
  detected: "every plugin whose detection fired",
  all: "every enabled plugin",
};
const S = { plugins: [], detect: null, mode: "auto", single: "", mixed: new Set(), policy: "selected", options: {}, running: false };
const el = {};

function mount(root) {
  el.path = h("input", { class: "input mono grow", id: "game-path", placeholder: "/path/to/game  (folder containing the game executable)",
    value: pref("gamePath") || "", spellcheck: "false", onkeydown: (e) => e.key === "Enter" && detect() });
  el.detect = h("div", { class: "detect" });
  el.mode = h("div", {});
  el.options = h("div", { class: "opts" });
  el.exts = h("input", { class: "input mono grow", id: "ext-filter", placeholder: "all extensions — or e.g. .png .ogg .webm", spellcheck: "false" });
  el.feed = h("pre", { class: "log feed", "aria-live": "off" });
  el.progress = h("div", { class: "progress" });
  el.result = h("div", { class: "result-host" });
  el.run = btn("RUN EXTRACTION", () => run(), "primary lg");
  el.cancel = btn("CANCEL JOB", cancelJob, "ghost", { hidden: true });
  root.append(
    viewHead("01", "EXTRACT", "Pull assets from a game folder into a ViWo workspace. The game folder is opened read-only and never modified."),
    h("div", { class: "grid2" },
      h("div", { class: "col" }, targetPanel(), detectPanel(), modePanel(), runPanel()),
      h("div", { class: "col" }, feedPanel(), el.result)));
  renderIdleFeed();
  loadPlugins();
}

function targetPanel() {
  const browse = btn("BROWSE", (e) => busy(e.currentTarget, browseFolder), "ghost");
  return panel("01.A", "TARGET GAME FOLDER", badge("READ-ONLY SOURCE", "ok"),
    h("label", { class: "lbl", for: "game-path" }, "GAME FOLDER PATH"),
    h("div", { class: "row" }, el.path, browse),
    h("p", { class: "note" }, "ViWo copies assets out into its workspace. Nothing inside this folder is written, moved or deleted."));
}

async function browseFolder() {
  try {
    const res = await api.browse(el.path.value.trim());
    el.path.value = res.path;
    pref("gamePath", res.path);
    detect();
  } catch (err) {
    if (err.payload?.cancelled) return;
    toast("Folder picker unavailable on this host — type the path instead.", "warn", err.message);
  }
}

function detectPanel() {
  el.detectBtn = btn("DETECT ENGINE", (e) => busy(e.currentTarget, detect), "");
  el.detect.append(h("p", { class: "dim" }, "Run detection to see how confident each engine plugin is about this folder."));
  return panel("01.B", "DETECT", el.detectBtn, el.detect);
}

async function detect() {
  const path = el.path.value.trim();
  if (!path) return toast("Enter a game folder first.", "warn");
  pref("gamePath", path);
  try {
    S.detect = await api.detect(path);
    if (S.mixed.size === 0) S.detect.auto.forEach((p) => S.mixed.add(p));
    if (!S.single) S.single = S.detect.auto[0] || "";
    renderDetect();
    renderMode();
  } catch (err) {
    S.detect = null;
    el.detect.replaceChildren(errorBox(err, "DETECTION FAILED"));
  }
}

function renderDetect() {
  const rows = Object.entries(S.detect.detections).sort((a, b) => b[1].confidence - a[1].confidence);
  const name = (id) => S.plugins.find((p) => p.id === id)?.name || id;
  el.detect.replaceChildren(...rows.map(([id, d]) => {
    const auto = S.detect.auto.includes(id);
    const kind = d.confidence >= 0.7 ? "hi" : d.confidence >= 0.35 ? "mid" : "lo";
    return h("div", { class: `det ${auto ? "auto" : ""}` },
      h("div", { class: "det-h" }, h("b", {}, name(id)), auto ? badge("AUTO PICK", "red") : null,
        h("span", { class: "mono pct" }, `${pad(Math.round(d.confidence * 100), 3)}%`)),
      meter(d.confidence, kind),
      h("ul", { class: "evidence mono" }, d.evidence.length ? d.evidence.map((e) => h("li", {}, e)) : h("li", { class: "dim" }, "no signature found")));
  }));
}

function modePanel() {
  el.seg = h("div", { class: "seg", role: "group", "aria-label": "Extraction mode" },
    ["auto", "single", "mixed"].map((m) => h("button", { type: "button", "data-mode": m, onclick: () => { S.mode = m; renderMode(); } }, m.toUpperCase())));
  renderMode();
  return panel("01.C", "MODE", el.seg, el.mode, el.options);
}

function chips(ids, isOn, onPick, role) {
  return h("div", { class: "chipset", role }, ids.map((id) => {
    const p = S.plugins.find((x) => x.id === id) || { id, name: id };
    return h("button", { type: "button", class: "pick", "aria-pressed": String(isOn(id)), onclick: () => onPick(id) },
      p.name, p.tosSensitive ? h("small", {}, " TOS") : null);
  }));
}

function renderMode() {
  el.seg?.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === S.mode)));
  const ids = S.plugins.map((p) => p.id);
  const auto = S.detect?.auto?.length ? S.detect.auto.join(", ") : "run DETECT to preview";
  const parts = {
    auto: [h("p", { class: "note" }, "ViWo picks the plugin(s) from detection. Current pick: ", h("b", { class: "mono" }, auto))],
    single: [h("p", { class: "note" }, "Force one engine plugin."), chips(ids, (id) => id === S.single, (id) => { S.single = id; renderMode(); })],
    mixed: [h("p", { class: "note" }, "Run several plugins into one workspace."),
      chips(ids, (id) => S.mixed.has(id), (id) => { S.mixed.has(id) ? S.mixed.delete(id) : S.mixed.add(id); renderMode(); }),
      h("div", { class: "row policy" }, h("span", { class: "lbl" }, "POLICY"),
        h("div", { class: "seg sm" }, Object.keys(POLICIES).map((k) => h("button", { type: "button", "aria-pressed": String(S.policy === k),
          onclick: () => { S.policy = k; renderMode(); } }, k.toUpperCase()))),
        h("span", { class: "dim" }, POLICIES[S.policy]))],
  };
  el.mode.replaceChildren(...parts[S.mode]);
  renderOptions();
}

function pluginsInPlay() {
  if (S.mode === "single") return S.plugins.filter((p) => p.id === S.single);
  if (S.mode === "mixed" && S.policy === "selected") return S.plugins.filter((p) => S.mixed.has(p.id));
  if (S.mode === "auto" && S.detect?.auto?.length) return S.plugins.filter((p) => S.detect.auto.includes(p.id));
  return S.plugins;
}

function optionField(pid, opt) {
  const store = (S.options[pid] ||= {});
  const cur = store[opt.key] ?? opt.default ?? "";
  const id = `opt-${pid}-${opt.key}`;
  const set = (v) => { store[opt.key] = v; };
  let input;
  if (opt.kind === "bool") input = h("input", { type: "checkbox", id, checked: Boolean(cur), onchange: (e) => set(e.target.checked) });
  else if (opt.kind === "choice") input = h("select", { class: "input", id, onchange: (e) => set(e.target.value) },
    (opt.choices || []).map((c) => h("option", { value: c, selected: c === cur }, c)));
  else input = h("input", { class: "input mono", id, value: String(cur), spellcheck: "false",
    type: opt.kind === "secret" ? "password" : opt.kind === "int" ? "number" : "text", autocomplete: opt.kind === "secret" ? "off" : null,
    oninput: (e) => set(opt.kind === "int" ? Number(e.target.value) : e.target.value) });
  return h("div", { class: `field ${opt.kind === "bool" ? "inline" : ""}` },
    h("label", { class: "lbl", for: id }, opt.label, opt.kind === "secret" ? badge("SECRET · NEVER STORED", "warn") : null), input);
}

function renderOptions() {
  const list = pluginsInPlay().filter((p) => p.options?.length);
  el.options.replaceChildren(...list.map((p) => h("fieldset", { class: "optset" },
    h("legend", {}, `${p.name} OPTIONS`, p.tosSensitive ? badge("TOS-SENSITIVE", "warn") : null),
    p.options.map((o) => optionField(p.id, o)))));
}

function runPanel() {
  const presets = Object.entries(PRESETS).map(([k, v]) => btn(k, () => addExts(v), "sm ghost"));
  return panel("01.D", "FILTER + RUN", null,
    h("label", { class: "lbl", for: "ext-filter" }, "EXTENSION FILTER (OPTIONAL)"),
    h("div", { class: "row" }, el.exts, btn("CLEAR", () => { el.exts.value = ""; }, "sm ghost")),
    h("div", { class: "row presets" }, h("span", { class: "dim" }, "ADD"), presets),
    h("div", { class: "row run-row" }, el.run, el.cancel));
}

function addExts(list) {
  const set = new Set([...parseExts(el.exts.value), ...parseExts(list)]);
  el.exts.value = [...set].join(" ");
}

const parseExts = (text) => text.split(/[\s,;]+/).filter(Boolean).map((e) => (e.startsWith(".") ? e : `.${e}`).toLowerCase());

function buildPayload(onExisting) {
  const gamePath = el.path.value.trim();
  if (!gamePath) return toast("Enter a game folder first.", "warn"), null;
  if (S.mode === "single" && !S.single) return toast("Pick a plugin for SINGLE mode.", "warn"), null;
  if (S.mode === "mixed" && S.policy === "selected" && !S.mixed.size) return toast("Pick at least one plugin for MIXED mode.", "warn"), null;
  const pluginOptions = {};
  for (const p of pluginsInPlay()) {
    const vals = Object.entries(S.options[p.id] || {}).filter(([, v]) => v !== "" && v != null);
    if (vals.length) pluginOptions[p.id] = Object.fromEntries(vals);
  }
  const exts = parseExts(el.exts.value);
  const payload = { gamePath, selectedExts: exts.length ? exts : null, mixedPolicy: S.policy, pluginOptions,
    extractionType: S.mode === "auto" ? "auto" : S.mode === "single" ? S.single : "mixed",
    plugins: S.mode === "mixed" ? [...S.mixed] : [] };
  if (onExisting) payload.onExisting = onExisting;
  return payload;
}

function feedPanel() {
  return panel("01.E", "LIVE FEED", null, el.progress, el.feed);
}

function renderIdleFeed() {
  el.progress.replaceChildren(h("span", { class: "lbl" }, "STANDBY"), h("span", { class: "dim mono" }, "no extraction running"));
  el.feed.replaceChildren(h("span", { class: "ln dim" }, "// events stream here while an extraction runs\n"));
}

function setRunning(on) {
  S.running = on;
  el.run.disabled = on;
  el.run.textContent = on ? "EXTRACTING…" : "RUN EXTRACTION";
  el.cancel.hidden = !on;
}

/** Follow the running extract job: discover it via /api/jobs, then stream its events. */
function tracker(known) {
  const t = { id: null, from: 0, count: 0, stage: "", start: Date.now(), busy: false };
  const tick = async () => {
    if (t.busy) return;
    t.busy = true;
    try {
      if (!t.id) {
        t.id = (await api.jobs()).filter((j) => j.kind === "extract" && !known.has(j.id)).pop()?.id || null;
        if (t.id) emit("jobs");
      }
      if (t.id) {
        const page = await api.events(t.id, t.from);
        t.from = page.next;
        page.events.forEach((e) => { t.count += 1; t.stage = e.stage || t.stage; el.feed.append(logLine(e.line, e.level)); });
        if (page.events.length) el.feed.scrollTop = el.feed.scrollHeight;
      }
    } catch { /* keep polling; the run call reports failures */ } finally { t.busy = false; }
    const secs = Math.round((Date.now() - t.start) / 1000);
    fill(el.progress, h("span", { class: S.running ? "lbl live" : "lbl" }, S.running ? "RUNNING" : "FINISHED"),
      h("span", { class: "mono" }, `STAGE ${(t.stage || "start").toUpperCase()} · ${t.count} EVENTS · ${secs}s`),
      S.running ? h("div", { class: "scan-bar" }, h("i", {})) : null);
  };
  t.timer = setInterval(tick, 600);
  t.flush = async () => { clearInterval(t.timer); while (t.busy) await new Promise((r) => setTimeout(r, 50)); await tick(); };
  S.tracker = t;
  return t;
}

async function cancelJob() {
  const id = S.tracker?.id;
  if (!id) return toast("Job not registered yet — try again in a moment.", "warn");
  try { await api.cancel(id); toast("Cancellation requested.", "warn"); } catch (err) { toastErr(err); }
}

async function askDecision(err) {
  const res = await modal({ title: "WORKSPACE ALREADY HOLDS AN EXTRACTION", tag: "// DECISION",
    body: [h("p", {}, err.message), h("p", { class: "dim" }, "NEW keeps it and writes to a fresh sibling folder. REPLACE swaps the extracted groups. Your game folder is untouched either way.")],
    actions: [{ label: "CANCEL", value: "cancel", kind: "ghost" }, { label: "NEW FOLDER", value: "new" }, { label: "REPLACE", value: "replace", kind: "primary", primary: true }] });
  return res.value === "cancel" ? null : res.value;
}

async function run(onExisting) {
  const payload = buildPayload(onExisting);
  if (!payload || S.running) return;
  let known = new Set(), next = null;
  try { known = new Set((await api.jobs()).map((j) => j.id)); } catch { /* tracking is best-effort */ }
  setRunning(true);
  el.feed.replaceChildren(logLine(`// RUN ${payload.extractionType.toUpperCase()} :: ${payload.gamePath}`));
  el.feed.closest(".panel").scrollIntoView({ block: "nearest" });
  const t = tracker(known);
  emit("jobs");
  try {
    const res = await api.extract(payload);
    setRunning(false);
    await t.flush();
    renderResult(el.result, res);
    el.result.scrollIntoView({ block: "nearest" });
    toast(`Extraction complete: ${fmtNum(res.result.copiedFiles)} files copied.`, "ok");
  } catch (err) {
    setRunning(false);
    await t.flush();
    if (err.payload?.needsDecision) next = await askDecision(err);
    else { renderFailure(el.result, err); el.result.scrollIntoView({ block: "nearest" }); err.code === "cancelled" ? toast("Extraction cancelled.", "warn") : toastErr(err, "Extraction failed: "); }
  } finally {
    setRunning(false);
    emit("jobs");
    emit("workspace");
  }
  if (next) run(next);
}

async function loadPlugins() {
  try {
    S.plugins = await api.plugins();
    renderMode();
  } catch (err) {
    el.mode.replaceChildren(errorBox(err, "PLUGINS UNAVAILABLE"));
  }
}

export default { mount };
