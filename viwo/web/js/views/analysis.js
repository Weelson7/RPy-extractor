// 12 ANALYSIS: the binaries a game offers (proposed by the plugins), one headless analysis per
// target into the workspace's .analysis/, and "continue in <tool>" handoffs (doc 6, 8.3a).
import { api } from "../api.js";
import { h, fill, btn, panel, badge, viewHead, toast, toastErr, pref, busy, bus, emit, browseBtn, errorBox, logLine, assure, table, alert, kv } from "../ui.js";
import { setGame, followGame } from "../game.js";
import { jobProgress, withSkeleton } from "../progress.js";
import { registerView } from "../registry.js";

const S = { targets: null, enabled: false, running: false, ws: "", key: "" };
const el = {};
const KIND = { native_binary: "NATIVE", dotnet_assembly: ".NET", il2cpp: "IL2CPP", python_bytecode: "PYTHON", gdscript_bytecode: "GDSCRIPT", script_vm: "SCRIPT VM", memory_image: "MEMORY" };

function mount(root) {
  el.game = h("input", { class: "input mono grow", id: "an-game", placeholder: "/path/to/game", value: pref("gamePath") || "",
    spellcheck: "false", onkeydown: (e) => e.key === "Enter" && list() });
  el.targets = h("div", {});
  el.prog = jobProgress("analyze", { logClass: "mini", onStatus: (t) => { if (S.running && t) el.sum.textContent = t; } });
  el.progPanel = panel("12.C", "RUN", null, el.prog.el);
  el.progPanel.hidden = true;
  el.result = h("div", {});
  el.sum = h("div", { class: "ab-sum mono" });
  el.why = h("span", { class: "ab-why" });
  el.cancel = btn("CANCEL", cancelJob, "ghost", { hidden: true });
  followGame(el.game);
  root.append(
    viewHead("12", "ANALYSIS", "Static analysis of the game's code: the plugins propose the binaries, Ghidra analyses a copy headless into the workspace, and CONTINUE IN GHIDRA opens the same project in the GUI. Nothing runs the game."),
    assure([["READ-ONLY", "the binary is copied first; the game folder is never handed to a tool"],
      ["YOUR RESPONSIBILITY", "you have the right to analyse what you analyse; ViWo refuses nothing and judges nothing"],
      ["INTO THE WORKSPACE", "projects and exports land under .analysis/ and travel with the workspace"]]),
    h("div", { class: "grid2" },
      h("div", { class: "col" },
        panel("12.A", "GAME", badge("READ-ONLY SOURCE", "ok"),
          h("label", { class: "lbl", for: "an-game" }, "GAME FOLDER"),
          h("div", { class: "row" }, el.game, browseBtn(el.game, (p) => { setGame(p); list(); }), btn("LIST TARGETS", (e) => busy(e.currentTarget, list), "primary")),
          h("p", { class: "note" }, "Results go to the active workspace: ", (el.wsNote = h("code", { class: "mono" }, S.ws || "—")), ".")),
        panel("12.B", "TARGETS", null, el.targets)),
      h("div", { class: "col" }, el.progPanel, el.result)),
    h("div", { class: "actionbar" }, el.sum, el.why, el.cancel));
  bus.addEventListener("wspath", (e) => { S.ws = e.detail.path || ""; el.wsNote.textContent = S.ws || "—"; bar(); });
  S.ws = bus.ws?.path || "";
  renderTargets();
  bar();
}

async function list() {
  const path = el.game.value.trim();
  if (!path) return toast("Enter the game folder first.", "warn");
  setGame(path);
  try {
    const res = await withSkeleton(el.targets, "READING THE GAME FOLDER…", () => api.analysisTargets(path), 3);
    S.targets = res.targets || [];
    S.enabled = Boolean(res.enabled);
  } catch (err) { S.targets = null; fill(el.targets, errorBox(err, "LISTING FAILED", err.code === "not_found" ? "Check the game folder path." : "")); bar(); return; }
  renderTargets();
  bar();
}

function renderTargets() {
  if (!S.targets) return fill(el.targets, h("p", { class: "dim" }, "Enter the game folder, then LIST TARGETS: every plugin names the binaries it knows (the player executable, IL2CPP metadata, managed assemblies, script bytecode)."));
  if (!S.enabled) fill(el.targets, alert("warn", "ANALYSIS IS OFF", "Switch it on in 11 SETTINGS (feature `analysis`). It stays off by default because its tools are large (Ghidra and a JDK, about 800 MB), not because anyone judges what you analyse."));
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
  el.why.textContent = S.running ? "" : (S.targets && !S.enabled ? "analysis is off (11 SETTINGS)" : "");
  el.cancel.hidden = !S.running;
}

async function cancelJob() {
  const id = el.prog.id;
  if (!id) return toast("Job not registered yet — try again in a moment.", "warn");
  try { await api.cancel(id); toast("Cancellation requested.", "warn"); } catch (err) { toastErr(err); }
}

async function run(t, slot = "") {
  S.running = true; S.key = t.key;
  bar(); renderTargets();
  fill(el.result);
  el.progPanel.hidden = false;
  await el.prog.start();
  el.prog.log.append(logLine(`// ANALYZE :: ${t.label} → ${S.ws}/.analysis`));
  try {
    const res = await api.analyze({ gamePath: el.game.value.trim(), targetKey: t.key, slot });
    await el.prog.finish("ok", `${res.artifacts.length} ARTIFACT(S) · ${res.backend}`);
    fill(el.result, panel("12.D", "RESULT", btn("OPEN FOLDER", () => api.openFolder(res.outputDir).catch(toastErr), "sm ghost"),
      kv("TARGET", res.target.label), kv("BACKEND", res.backend), kv("NOTES", (res.notes || []).join("; ") || "-"), kv("OUTPUT", h("code", { class: "mono" }, res.outputDir)),
      h("ul", { class: "plain mono small" }, res.artifacts.map((a) => h("li", {}, a)))));
    toast(`Analysis done: ${res.artifacts.length} artifact(s).`, "ok");
  } catch (err) {
    await el.prog.finish(err.code === "cancelled" ? "cancel" : "fail", err.code === "cancelled" ? "ANALYSIS CANCELLED" : "ANALYSIS FAILED");
    fill(el.result, errorBox(err, "ANALYSIS FAILED", err.code === "refused" ? "Switch the feature on in 11 SETTINGS." : err.code === "unavailable" ? "Install the tool in 05 SYSTEM (Ghidra + JDK)." : ""));
    toastErr(err, "Analysis failed: ");
  } finally { S.running = false; renderTargets(); bar(); emit("jobs"); }
}

async function open(t, hd) {
  try {
    const res = await api.openHandoff({ gamePath: el.game.value.trim(), targetKey: t.key, handoff: hd.id });
    toast(`${hd.label}: started (pid ${res.pid}). It closes with ViWo.`, "ok");
  } catch (err) { toastErr(err, `${hd.label} failed: `); }
}

const VIEW = { mount, show: bar };
registerView({ id: "analysis", arm: "static", order: 70, num: "12", title: "ANALYSIS", subtitle: "code, headless and in Ghidra", ...VIEW });
export default VIEW;
