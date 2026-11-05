// ANALYSIS (static arm): the binaries a game offers (proposed by the plugins), one headless
// analysis per target into the workspace's .analysis/, and "continue in Ghidra" (doc 6, 8.3a).
import { api } from "../api.js";
import { h, fill, btn, panel, badge, viewHead, toast, toastErr, pref, busy, bus, emit, browseBtn, errorBox, logLine, assure, table, alert, kv } from "../ui.js";
import { setGame, followGame } from "../game.js";
import { featureOff } from "../feature.js";
import { jobProgress, withSkeleton } from "../progress.js";
import { registerView, code } from "../registry.js";
import { howToBtn } from "./workbooks.js";

const S = { targets: null, enabled: false, running: false, ws: "", key: "" };
const el = {};
const KIND = { native_binary: "NATIVE", dotnet_assembly: ".NET", il2cpp: "IL2CPP", python_bytecode: "PYTHON", gdscript_bytecode: "GDSCRIPT", script_vm: "SCRIPT VM", memory_image: "MEMORY" };

function mount(root) {
  el.game = h("input", { class: "input mono grow", id: "an-game", placeholder: "/path/to/game", value: pref("gamePath") || "",
    spellcheck: "false", onkeydown: (e) => e.key === "Enter" && list() });
  el.targets = h("div", {});
  el.opts = h("textarea", { class: "input mono", id: "an-opts", rows: "4", spellcheck: "false", value: pref("anOpts") || "",
    placeholder: "start=export:decode\nargs=hex:00112233,4,0x5a\ndump=arg0:4", oninput: (e) => pref("anOpts", e.target.value) });
  el.prog = jobProgress("analyze", { logClass: "mini", onStatus: (t) => { if (S.running && t) el.sum.textContent = t; } });
  el.progPanel = panel(`${code("analysis")}.C`, "RUN", null, el.prog.el);
  el.progPanel.hidden = true;
  el.result = h("div", {});
  el.sum = h("div", { class: "ab-sum mono" });
  el.why = h("span", { class: "ab-why" });
  el.cancel = btn("CANCEL", () => el.prog.cancel(), "ghost", { hidden: true });
  followGame(el.game, () => { if (!S.running) { S.targets = null; S.listedFor = ""; renderTargets(); bar(); } });
  S.ws = bus.ws?.path || ""; // before the note is built: the workspace may be known already
  root.append(
    viewHead(code("analysis"), "ANALYSIS", "Static analysis of the game's code: the plugins propose the binaries, Ghidra analyses a copy headless into the workspace, and CONTINUE IN GHIDRA opens the same project in the GUI. Nothing runs the game."),
    assure([["READ-ONLY", "the binary is copied first; the game folder is never handed to a tool"],
      ["YOUR RESPONSIBILITY", "you have the right to analyse what you analyse; ViWo refuses nothing and judges nothing"],
      ["INTO THE WORKSPACE", "projects and exports land under .analysis/ and travel with the workspace"]]),
    h("div", { class: "grid2" },
      h("div", { class: "col" },
        panel(`${code("analysis")}.A`, "GAME", badge("READ-ONLY SOURCE", "ok"),
          h("label", { class: "lbl", for: "an-game" }, "GAME FOLDER"),
          h("div", { class: "row" }, el.game, browseBtn(el.game, (p) => { setGame(p); list(); }), btn("LIST TARGETS", (e) => busy(e.currentTarget, list), "primary")),
          h("p", { class: "note" }, "Results go to the active workspace: ", (el.wsNote = h("code", { class: "mono" }, S.ws || "—")), ".")),
        panel(`${code("analysis")}.B`, "TARGETS", howToBtn("ghidra", "HOW TO: GHIDRA"), el.targets),
        diffPanel(),
        panel(`${code("analysis")}.E`, "ROUTINE OPTIONS (EMULATE / SOLVE)", null,
          h("label", { class: "lbl", for: "an-opts" }, "ONE KEY=VALUE PER LINE: START, ARGS, DUMP, MAX_INSNS; FIND, AVOID FOR SOLVE"),
          el.opts, h("p", { class: "note" }, "Unicorn runs one isolated routine of the binary; angr solves the inputs that reach FIND. Both run as their own process."))),
      h("div", { class: "col" }, el.progPanel, el.result)),
    h("div", { class: "actionbar" }, el.sum, el.why, el.cancel));
  bus.addEventListener("wspath", (e) => { S.ws = e.detail.path || ""; el.wsNote.textContent = S.ws || "—"; bar(); });
  renderTargets();
  bar();
}

async function list() {
  const path = el.game.value.trim();
  if (!path) return toast("Enter the game folder first.", "warn");
  setGame(path);
  S.listedFor = path;
  try {
    const res = await withSkeleton(el.targets, "READING THE GAME FOLDER…", () => api.analysisTargets(path), 3);
    S.targets = res.targets || [];
    S.enabled = Boolean(res.enabled);
  } catch (err) { S.targets = null; fill(el.targets, errorBox(err, "LISTING FAILED", err.code === "not_found" ? "Check the game folder path." : "")); bar(); return; }
  renderTargets();
  bar();
}

/** VERSION DIFF: two Ghidra exports of one binary (an older and a newer game build). */
function diffPanel() {
  const folder = (id, key) => h("input", { class: "input mono grow", id, placeholder: ".analysis/ghidra-headless/<key>", value: pref(key) || "",
    spellcheck: "false", oninput: (e) => pref(key, e.target.value.trim()) });
  el.diffOld = folder("an-diff-old", "anDiffOld");
  el.diffNew = folder("an-diff-new", "anDiffNew");
  el.diffOut = h("div", {});
  return panel(`${code("analysis")}.F`, "VERSION DIFF", null,
    h("label", { class: "lbl", for: "an-diff-old" }, "OLDER BUILD (ITS GHIDRA EXPORT FOLDER)"), h("div", { class: "row" }, el.diffOld, browseBtn(el.diffOld, (p) => pref("anDiffOld", p))),
    h("label", { class: "lbl", for: "an-diff-new" }, "NEWER BUILD"), h("div", { class: "row" }, el.diffNew, browseBtn(el.diffNew, (p) => pref("anDiffNew", p))),
    h("div", { class: "row" }, btn("COMPARE", (e) => busy(e.currentTarget, runDiff), "")), el.diffOut);
}

async function runDiff() {
  try {
    const res = await api.diffAnalyses(el.diffOld.value.trim(), el.diffNew.value.trim());
    fill(el.diffOut, Object.entries(res.summary).map(([k, v]) => kv(k.toUpperCase(), h("span", { class: "mono" }, String(v)))),
      btn("OPEN FOLDER", () => api.openFolder(res.outputDir).catch(toastErr), "sm ghost"));
  } catch (err) { fill(el.diffOut, errorBox(err, "DIFF FAILED", "Give two .analysis/ghidra-headless/<key> folders.")); }
}

function renderTargets() {
  if (!S.targets) return fill(el.targets, h("p", { class: "dim" }, "Enter the game folder, then LIST TARGETS: every plugin names the binaries it knows (the player executable, IL2CPP metadata, managed assemblies, script bytecode)."));
  if (!S.enabled) fill(el.targets, featureOff("ANALYSIS IS OFF", "It stays off by default because its tools are large (Ghidra and a JDK, about 800 MB), not because anyone judges what you analyse.", "analysis", list));
  else fill(el.targets);
  if (!S.targets.length) return el.targets.append(h("p", { class: "dim" }, "No target proposed for this folder."));
  const rows = S.targets.map((t) => ({
    label: h("span", { class: "mono" }, t.label), kind: badge(KIND[t.kind] || t.kind, ""), owner: t.owner,
    state: t.analyzer ? badge(t.analyzer, "ok") : badge("NO ANALYZER YET", "mute"),
    act: h("div", { class: "row" },
      btn("ANALYZE", () => run(t), "sm primary", { disabled: !t.analyzer || !S.enabled || S.running }),
      ...(t.extras || []).map((x) => btn(x.label.toUpperCase(), () => run(t, x.slot), "sm", { disabled: !S.enabled || S.running })),
      ...(t.handoffs || []).map((hd) => btn(hd.label.toUpperCase(), () => open(t, hd), "sm ghost", { disabled: !S.enabled }))),
  }));
  el.targets.append(table([{ key: "label", label: "TARGET" }, { key: "kind", label: "KIND" }, { key: "owner", label: "PLUGIN" }, { key: "state", label: "ANALYZER" }, { key: "act", label: "" }], rows, { caption: "Analysis targets" }));
}

function bar() {
  el.sum.textContent = S.running ? `analysing ${S.key}…` : `${S.targets ? S.targets.length : 0} target(s) → ${S.ws ? S.ws.split(/[\\/]/).pop() : "workspace"}`;
  el.why.textContent = S.running ? "" : (S.targets && !S.enabled ? "analysis is off (SETTINGS)" : "");
  el.cancel.hidden = !S.running;
}

async function run(t, slot = "") {
  S.running = true; S.key = t.key;
  bar(); renderTargets();
  fill(el.result);
  el.progPanel.hidden = false;
  await el.prog.start();
  el.prog.log.append(logLine(`// ANALYZE :: ${t.label} → ${S.ws}/.analysis`));
  try {
    const options = Object.fromEntries(el.opts.value.split("\n").map((l) => l.trim()).filter((l) => l.includes("=")).map((l) => [l.slice(0, l.indexOf("=")).trim(), l.slice(l.indexOf("=") + 1).trim()]));
    const res = await api.analyze({ gamePath: el.game.value.trim(), targetKey: t.key, slot, options });
    await el.prog.finish("ok", `${res.artifacts.length} ARTIFACT(S) · ${res.backend}`);
    fill(el.result, panel(`${code("analysis")}.D`, "RESULT", btn("OPEN FOLDER", () => api.openFolder(res.outputDir).catch(toastErr), "sm ghost"),
      kv("TARGET", res.target.label), kv("BACKEND", res.backend), kv("NOTES", (res.notes || []).join("; ") || "-"), res.fallback ? kv("FALLBACK", res.fallback) : null, kv("OUTPUT", h("code", { class: "mono" }, res.outputDir)),
      h("ul", { class: "plain mono small" }, res.artifacts.map((a) => h("li", {}, a)))));
    toast(`Analysis done: ${res.artifacts.length} artifact(s).`, "ok");
  } catch (err) {
    await el.prog.finish(err.code === "cancelled" ? "cancel" : "fail", err.code === "cancelled" ? "ANALYSIS CANCELLED" : "ANALYSIS FAILED");
    fill(el.result, errorBox(err, "ANALYSIS FAILED", err.code === "refused" ? "Switch the feature on in SETTINGS." : err.code === "unavailable" ? "Install the tool in SYSTEM (Ghidra + JDK)." : ""));
    toastErr(err, "Analysis failed: ");
  } finally { S.running = false; renderTargets(); bar(); emit("jobs"); }
}

/** A static handoff (Ghidra) opens the analysis project; the tools that run or attach to the
 * game (x64dbg, Cheat Engine) are the dynamic arm's, in RUNTIME. */
async function open(t, hd) {
  try {
    const res = await api.openHandoff({ gamePath: el.game.value.trim(), targetKey: t.key, handoff: hd.id });
    toast(`${hd.label}: started (pid ${res.pid}). It closes with ViWo.`, "ok");
  } catch (err) { toastErr(err, `${hd.label} failed: `); }
}

/** Opening ANALYSIS lists the targets of the current game when they are not listed yet. */
function show() {
  const path = el.game.value.trim();
  if (path && path !== S.listedFor && !S.running) return list();
  bar();
}

const VIEW = { mount, show };
registerView({ id: "analysis", arm: "static", order: 70, title: "ANALYSIS", subtitle: "code, headless and in Ghidra", ...VIEW });
export default VIEW;
