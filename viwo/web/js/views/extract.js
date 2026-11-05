// EXTRACT: target, detection, mode, plugin options, filter, run + live feed.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, meter, viewHead, toast, toastErr, pref, logLine, emit, errorBox, pct, fmtNum, bus, browseBtn } from "../ui.js";
import { setGame, followGame } from "../game.js";
import { slotText } from "./system.js";
import { jobProgress, withSkeleton } from "../progress.js";
import { renderResult, renderFailure, renderIdle, askDecision } from "./extract-result.js";
import { openWorkspaceDialog } from "../workspace-dialog.js";

const PRESETS = { IMAGES: ".png .jpg .jpeg .webp .gif .bmp .dds", AUDIO: ".ogg .mp3 .wav .opus .flac .m4a .wem .fsb",
  VIDEO: ".webm .mp4 .mkv .mov .avi .bik", TEXT: ".txt .json .rpy .xml .csv" };
const POLICIES = { selected: "only the plugins picked below", detected: "every plugin whose detection fired", all: "every enabled plugin" };
const CARVE = { unknown: "in files nothing else recognizes", all: "in every file, executables included", off: "nowhere (off)" };
const S = { plugins: [], detect: null, mode: "auto", single: "", mixed: new Set(), policy: "selected", options: {}, running: false, carve: "unknown" };
const el = {};

function mount(root) {
  el.path = h("input", { class: "input mono grow", id: "game-path", placeholder: "/path/to/game",
    value: pref("gamePath") || "", spellcheck: "false", onkeydown: (e) => e.key === "Enter" && detect(), oninput: () => updateBar() });
  el.detect = h("div", { class: "detect" });
  el.mode = h("div", {});
  el.options = h("details", { class: "optgroup", open: true });
  el.exts = h("input", { class: "input mono grow", id: "ext-filter", placeholder: "all extensions — or e.g. .png .ogg .webm", spellcheck: "false", oninput: () => updateBar() });
  el.prog = jobProgress("extract", { onStatus: (text) => { if (S.running && text) el.sum.textContent = text; } });
  el.result = h("div", { class: "result-host" });
  el.idle = h("div", { class: "idle" });
  el.sum = h("div", { class: "ab-sum mono" });
  el.why = h("span", { class: "ab-why" });
  el.run = btn("RUN EXTRACTION", () => run(), "primary lg");
  el.target = h("code", { class: "mono path" }, "—");
  el.cancel = btn("CANCEL JOB", () => el.prog.cancel(), "ghost", { hidden: true });
  followGame(el.path, forget);
  root.append(
    viewHead(code("extract"), "EXTRACT", "Pull assets from a game folder into a ViWo workspace. The game folder is opened read-only and never modified."),
    h("div", { class: "grid2" },
      h("div", { class: "col" }, targetPanel(), detectPanel(), modePanel(), runPanel()),
      h("div", { class: "col" }, feedPanel(), el.result)),
    h("div", { class: "actionbar" }, el.sum, el.why, el.cancel, el.run));
  renderIdleFeed();
  loadPlugins();
  const showWs = (path) => { el.target.textContent = path || "—"; updateBar(); };
  showWs(bus.ws?.path);
  bus.addEventListener("wspath", (e) => showWs(e.detail.path));
}

function targetPanel() {
  const browse = browseBtn(el.path, (path) => { setGame(path); detect(); });
  return panel(`${code("extract")}.A`, "TARGET GAME FOLDER", badge("READ-ONLY SOURCE", "ok"),
    h("label", { class: "lbl", for: "game-path" }, "GAME FOLDER PATH"),
    h("div", { class: "row" }, el.path, browse),
    h("p", { class: "note" }, "ViWo copies assets out into its workspace. Nothing inside this folder is written, moved or deleted."));
}

function detectPanel() {
  el.detectBtn = btn("DETECT ENGINE", detect, "");
  el.detect.append(h("p", { class: "dim" }, "Pick a game folder, then DETECT ENGINE (or press Enter in the path) to see which engine it uses."));
  return panel(`${code("extract")}.B`, "DETECT", el.detectBtn, el.detect);
}

/** Another game: the last detection and the plugins it chose no longer apply. */
function forget() {
  if (S.running) return;
  S.detect = null; S.detectedFor = ""; S.single = ""; S.mixed.clear();
  fill(el.detect, h("p", { class: "dim" }, "Another game: DETECT ENGINE runs again when you open EXTRACT."));
  updateBar();
}

async function detect() {
  const path = el.path.value.trim();
  if (!path) return toast("Enter a game folder first.", "warn");
  if (el.detectBtn.disabled) return;
  if (S.detectedFor && S.detectedFor !== path) forget();
  setGame(path);
  S.detectedFor = path;
  el.detectBtn.disabled = true;
  try {
    S.detect = await withSkeleton(el.detect, "PROBING ENGINE SIGNATURES…", () => api.detect(path), 3);
    if (S.mixed.size === 0) S.detect.auto.forEach((p) => S.mixed.add(p));
    if (!S.single) S.single = S.detect.auto[0] || "";
    renderDetect();
    renderMode();
  } catch (err) {
    S.detect = null;
    el.detect.replaceChildren(errorBox(err, "DETECTION FAILED", err.code === "invalid_request" ? "Check the folder path: it must be the game's own folder." : ""));
  } finally { el.detectBtn.disabled = false; }
}

/** Formats the picked plugins handle that need a tool which is not installed (links to SYSTEM). */
function missingTools() {
  const slots = bus.distro?.slots || {};
  const gaps = pluginsInPlay().flatMap((p) => p.slots.filter((s) => slots[s] && !slots[s].main).map((s) => [p.name, s]));
  if (!gaps.length) return null;
  const how = [...new Set(gaps.flatMap(([, s]) => slots[s].reasons.map((r) => r.replace(/^[^(]*\(|\)$/g, ""))))];
  return h("div", { class: "alert", "data-kind": "warn" }, h("b", {}, "OPTIONAL TOOLS NOT INSTALLED"),
    h("p", {}, `${gaps.map(([n, s]) => `${n}: ${slotText(s)}`).join(" · ")}. Extraction still runs and copies everything else.`),
    h("ul", { class: "small" }, how.map((x) => h("li", {}, x))),
    h("p", {}, h("a", { href: "#system" }, "Open SYSTEM to install them (one click) →")));
}

function renderDetect() {
  const all = Object.entries(S.detect.detections).sort((a, b) => b[1].confidence - a[1].confidence);
  const rows = all.filter(([, d]) => d.confidence > 0);
  const name = (id) => S.plugins.find((p) => p.id === id)?.name || id;
  el.detect.replaceChildren(missingTools() || "", ...rows.map(([id, d]) => {
    const auto = S.detect.auto.includes(id);
    const kind = d.confidence >= 0.7 ? "hi" : d.confidence >= 0.35 ? "mid" : "lo";
    return h("div", { class: "det", "data-state": auto ? "auto" : null },
      h("div", { class: "det-h" }, h("b", {}, name(id)), auto ? badge("AUTO PICK", "red") : null,
        h("span", { class: "mono pct" }, pct(d.confidence))),
      meter(d.confidence, kind),
      h("ul", { class: "evidence mono" }, d.evidence.length ? d.evidence.map((e) => h("li", {}, e)) : h("li", { class: "dim" }, "no signature found")));
  }), all.length > rows.length ? h("p", { class: "dim small det" }, `${all.length - rows.length} other engine plugins found no match.`) : "");
}

function modePanel() {
  el.seg = h("div", { class: "seg", role: "group", "aria-label": "Extraction mode" },
    ["auto", "single", "mixed"].map((m) => h("button", { type: "button", "data-mode": m, onclick: () => { S.mode = m; renderMode(); } }, m.toUpperCase())));
  renderMode();
  return panel(`${code("extract")}.C`, "MODE", el.seg, el.mode, el.options);
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
  const auto = S.detect?.auto?.length ? h("b", { class: "mono" }, S.detect.auto.join(", ")) : "none yet (run DETECT ENGINE)";
  const parts = {
    auto: [h("p", { class: "note" }, "ViWo picks the engine plugin(s) from detection. Current pick: ", auto)],
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
  updateBar();
}

/** The plugins that will run under the current mode and policy (their options are shown). */
function pluginsInPlay() {
  if (S.mode === "single") return S.plugins.filter((p) => p.id === S.single);
  if (S.mode === "mixed" && S.policy === "all") return S.plugins;
  if (S.mode === "mixed" && S.policy === "detected") return S.plugins.filter((p) => (S.detect?.detections?.[p.id]?.confidence || 0) > 0);
  if (S.mode === "mixed") return S.plugins.filter((p) => S.mixed.has(p.id));
  return S.plugins.filter((p) => S.detect?.auto?.includes(p.id));
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
  el.options.hidden = !list.length;
  fill(el.options, h("summary", {}, `ENGINE OPTIONS · ${list.map((p) => p.name).join(", ")}`), list.map((p) => h("fieldset", { class: "optset" },
    h("legend", {}, `${p.name} OPTIONS`, p.tosSensitive ? badge("TOS-SENSITIVE", "warn") : null),
    p.options.map((o) => optionField(p.id, o)))));
}

function renderCarve() {
  el.carve.replaceChildren(...Object.keys(CARVE).map((k) => h("button", { type: "button", "aria-pressed": String(S.carve === k),
    onclick: () => { S.carve = k; renderCarve(); } }, k.toUpperCase())));
  el.carveNote.textContent = `find PNG, OGG, WAV, DDS, Bink, FSB, zip… hidden ${CARVE[S.carve]}`;
}

function runPanel() {
  el.carve = h("div", { class: "seg sm", role: "group", "aria-label": "Carve embedded files" });
  el.carveNote = h("span", { class: "dim" });
  renderCarve();
  const presets = Object.entries(PRESETS).map(([k, v]) => btn(k, () => addExts(v), "sm ghost"));
  return panel(`${code("extract")}.D`, "FILTER + OUTPUT", null,
    h("label", { class: "lbl", for: "ext-filter" }, "EXTENSION FILTER (OPTIONAL)"),
    h("div", { class: "row" }, el.exts, btn("CLEAR", () => { el.exts.value = ""; updateBar(); }, "sm ghost")),
    h("div", { class: "row presets" }, h("span", { class: "dim" }, "ADD"), presets),
    h("div", { class: "row policy" }, h("span", { class: "lbl" }, "EMBEDDED FILES"), el.carve, el.carveNote),
    h("div", { class: "kv target" }, h("span", { class: "lbl" }, "OUTPUT →"), el.target,
      h("div", { class: "row" }, h("span", { class: "dim small" }, "Extraction always writes into the active workspace."), btn("SWITCH", openWorkspaceDialog, "sm ghost"))));
}

function addExts(list) {
  const set = new Set([...parseExts(el.exts.value), ...parseExts(list)]);
  el.exts.value = [...set].join(" ");
  updateBar();
}

/** Why RUN cannot start yet ("" when it can). */
function blocker() {
  if (S.running) return "extraction running…";
  if (!el.path.value.trim()) return "pick a game folder";
  if (S.mode === "single" && !S.single) return "pick a plugin for SINGLE";
  if (S.mode === "mixed" && S.policy === "selected" && !S.mixed.size) return "pick plugins for MIXED";
  return "";
}

function updateBar() {
  if (!el.run) return;
  const name = el.path.value.trim().split(/[\\/]/).filter(Boolean).pop() || "no game folder";
  const plugins = S.mode === "single" ? S.single : S.mode === "mixed" ? [...S.mixed].join("+") : S.detect?.auto?.join("+") || "";
  const exts = parseExts(el.exts.value);
  el.sum.textContent = `${name} · ${S.mode.toUpperCase()}${plugins ? ` ${plugins}` : ""} · ${exts.length ? exts.join(" ") : "all types"} → ${(bus.ws?.path || "").split(/[\\/]/).pop() || "workspace"}`;
  el.why.textContent = blocker();
  el.run.disabled = Boolean(el.why.textContent);
}

const parseExts = (text) => text.split(/[\s,;]+/).filter(Boolean).map((e) => (e.startsWith(".") ? e : `.${e}`).toLowerCase());

function buildPayload(onExisting) {
  const gamePath = el.path.value.trim();
  if (blocker()) return toast(`Cannot run: ${blocker()}.`, "warn"), null;
  const pluginOptions = {};
  for (const p of pluginsInPlay()) {
    const vals = Object.entries(S.options[p.id] || {}).filter(([, v]) => v !== "" && v != null);
    if (vals.length) pluginOptions[p.id] = Object.fromEntries(vals);
  }
  const exts = parseExts(el.exts.value);
  const payload = { gamePath, selectedExts: exts.length ? exts : null, mixedPolicy: S.policy, pluginOptions,
    extractionType: S.mode === "auto" ? "auto" : S.mode === "single" ? S.single : "mixed",
    plugins: S.mode === "mixed" ? [...S.mixed] : [], carve: S.carve };
  if (onExisting) payload.onExisting = onExisting;
  return payload;
}

function feedPanel() {
  return panel(`${code("extract")}.E`, "LIVE FEED", null, el.idle, el.prog.el);
}

function renderIdleFeed() {
  el.prog.el.hidden = true;
  el.idle.hidden = false;
  renderIdle(el.idle);
}

function setRunning(on) {
  S.running = on;
  el.run.textContent = on ? "EXTRACTING…" : "RUN EXTRACTION";
  el.cancel.hidden = !on;
  if (on) el.idle.hidden = !(el.prog.el.hidden = false);
  updateBar();
}

async function run(onExisting) {
  const payload = buildPayload(onExisting);
  if (!payload || S.running) return;
  let next = null;
  setRunning(true);
  fill(el.result);
  await el.prog.start();
  el.prog.log.append(logLine(`// RUN ${payload.extractionType.toUpperCase()} · CARVE ${payload.carve.toUpperCase()} :: ${payload.gamePath}`));
  el.prog.el.closest(".panel").scrollIntoView({ block: "nearest" });
  try {
    const res = await api.extract(payload);
    el.cancel.hidden = true;
    await el.prog.finish("ok", `${fmtNum(res.result.copiedFiles)} FILES COPIED`);
    setRunning(false);
    renderResult(el.result, res);
    reveal();
    toast(`Extraction complete: ${fmtNum(res.result.copiedFiles)} files copied.`, "ok");
  } catch (err) {
    if (err.payload?.needsDecision) {
      el.prog.stop();
      renderIdleFeed();
      setRunning(false);
      next = await askDecision(err);
    } else {
      el.cancel.hidden = true;
      await el.prog.finish(err.code === "cancelled" ? "cancel" : "fail", err.message);
      renderFailure(el.result, err);
      reveal();
      err.code === "cancelled" ? toast("Extraction cancelled.", "warn") : toastErr(err, "Extraction failed: ");
    }
  } finally {
    setRunning(false);
    emit("jobs");
    emit("workspace");
    renderIdle(el.idle);
  }
  if (next) run(next);
}

function reveal() {
  if (el.result.firstElementChild) el.result.firstElementChild.dataset.reveal = "1";
  el.result.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
}

/** SURVEY hands over a game folder (or the top bar's game changed): detect straight away. */
function show() {
  if (bus.gamePath) {
    el.path.value = bus.gamePath;
    bus.gamePath = null;
  }
  const path = el.path.value.trim();
  if (path && path !== S.detectedFor && !S.running) detect();
}

async function loadPlugins() {
  try {
    S.plugins = await api.plugins();
    renderMode();
  } catch (err) {
    el.mode.replaceChildren(errorBox(err, "PLUGINS UNAVAILABLE"));
  }
}

import { registerView, code } from "../registry.js";

const VIEW = { mount, show };
registerView({ id: "extract", arm: "static", order: 20, title: "EXTRACT", subtitle: "pull assets from a game", ...VIEW });
export default VIEW;
