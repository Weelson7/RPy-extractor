// CAPTURE: frames from a running game through RenderDoc. Pick game + executable, read the
// warnings (information, never a block), confirm once, run as a job, see what came out.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, viewHead, toast, toastErr, pref, busy, bus, emit, browseBtn, errorBox, logLine, assure } from "../ui.js";
import { setGame, followGame } from "../game.js";
import { jobProgress, withSkeleton } from "../progress.js";
import { beforeYouStart, renderResult, renderFailure } from "./capture-result.js";
import { howToBtn } from "./workbooks.js";

const S = { running: false, info: null, infoFor: "", confirmed: false, ws: "" };
const el = {};
const base = (p) => String(p || "").split(/[\\/]/).filter(Boolean).pop() || "";

function mount(root) {
  el.game = h("input", { class: "input mono grow", id: "cap-game", placeholder: "/path/to/game", value: pref("gamePath") || "",
    spellcheck: "false", oninput: () => bar(), onkeydown: (e) => e.key === "Enter" && check() });
  el.exe = h("input", { class: "input mono grow", id: "cap-exe", placeholder: "/path/to/game/Game.exe", value: pref("capExe") || "",
    spellcheck: "false", oninput: () => { pref("capExe", el.exe.value.trim()); bar(); } });
  el.auto = h("input", { class: "input mono", id: "cap-auto", type: "number", min: "0", step: "5", value: pref("capAuto") || "30",
    oninput: () => pref("capAuto", el.auto.value) });
  el.before = h("div", {});
  el.checkBtn = btn("CHECK", (e) => busy(e.currentTarget, check), "");
  el.prog = jobProgress("capture", { logClass: "mini", onStatus: (t) => { if (S.running && t) el.sum.textContent = t; } });
  el.progPanel = panel(`${code("capture")}.C`, "RUN", null, el.prog.el);
  el.progPanel.hidden = true;
  el.result = h("div", {});
  el.sum = h("div", { class: "ab-sum mono" });
  el.why = h("span", { class: "ab-why" });
  el.run = btn("LAUNCH + CAPTURE", run, "primary lg");
  el.cancel = btn("CANCEL", () => el.prog.cancel("Cancellation requested; quit the game to stop sooner."), "ghost", { hidden: true });
  followGame(el.game);
  S.ws = bus.ws?.path || ""; // before the note is built: the workspace may be known already
  root.append(
    viewHead(code("capture"), "CAPTURE", "Run the game under RenderDoc: after the delay one frame is captured and the game is stopped, nothing to press (set 0 to take captures yourself with F12 and quit when done). Every texture and shader of every capture lands in the workspace, and ViWo says which ones static extraction had missed."),
    assure([["ANY GAME", "anti-cheat and online titles only produce warnings; you decide, you are responsible"],
      ["GAME FOLDER RESTORED", "anything the capture agent writes next to the game is journaled and put back"],
      ["INTO THE WORKSPACE", "every frame is kept (it opens in RenderDoc) with its textures as PNG, collected like extracted files"]]),
    h("div", { class: "grid2" },
      h("div", { class: "col" }, targetPanel(), panel(`${code("capture")}.B`, "BEFORE YOU START", el.checkBtn, el.before)),
      h("div", { class: "col" }, el.progPanel, el.result)),
    h("div", { class: "actionbar" }, el.sum, el.why, el.cancel, el.run));
  bus.addEventListener("wspath", (e) => { S.ws = e.detail.path || ""; if (el.wsNote) el.wsNote.textContent = S.ws || "—"; bar(); });
  bus.addEventListener("preflight", () => { S.info = null; renderBefore(); bar(); });
  renderBefore();
  bar();
}

function targetPanel() {
  const browseGame = browseBtn(el.game, (path) => { setGame(path); check(); });
  const browseExe = browseBtn(el.exe, (path) => { pref("capExe", path); bar(); }, (p) => api.browseFile(p || el.game.value.trim()).then((r) => r.path));
  return panel(`${code("capture")}.A`, "TARGET", h("div", { class: "row" }, badge("READ-ONLY SOURCE", "ok"), howToBtn("renderdoccmd", "HOW TO: RENDERDOC")),
    h("label", { class: "lbl", for: "cap-game" }, "GAME FOLDER"),
    h("div", { class: "row" }, el.game, browseGame),
    h("label", { class: "lbl", for: "cap-exe" }, "EXECUTABLE TO LAUNCH (INSIDE THAT FOLDER)"),
    h("div", { class: "row" }, el.exe, browseExe),
    h("label", { class: "lbl", for: "cap-auto" }, "CAPTURE ONE FRAME AFTER (SECONDS; 0 = PRESS F12 YOURSELF)"),
    h("div", { class: "row" }, el.auto, h("span", { class: "dim small" }, "default: unattended, the game is stopped after the frame")),
    h("p", { class: "note" }, "The captures go to the active workspace: ", (el.wsNote = h("code", { class: "mono" }, S.ws || "—")), ". Switch it in the top bar if you want them elsewhere."));
}

async function check() {
  const path = el.game.value.trim();
  if (!path) return toast("Enter the game folder first.", "warn");
  setGame(path);
  try {
    S.info = await withSkeleton(el.before, "READING THE GAME FOLDER…", () => api.captureWarnings(path), 3);
    S.infoFor = path;
    S.confirmed = false;
  } catch (err) {
    S.info = null;
    fill(el.before, errorBox(err, "CHECK FAILED", err.code === "not_found" ? "Check the game folder path." : ""));
    bar();
    return;
  }
  renderBefore();
  bar();
}

function renderBefore() {
  fill(el.before, S.info ? beforeYouStart(S.info, S.confirmed, (v) => { S.confirmed = v; bar(); }, check)
    : h("p", { class: "dim" }, "Enter the game folder, then CHECK: ViWo lists what you should know about this game (anti-cheat, online play, sensitive plugins) and asks for one confirmation. Nothing here blocks you."));
}

/** Why LAUNCH cannot start yet ("" when it can). */
function blocker() {
  if (S.running) return "capturing…";
  if (!el.game.value.trim()) return "enter the game folder";
  if (!el.exe.value.trim()) return "pick the executable";
  if (!S.info || S.infoFor !== el.game.value.trim()) return "press CHECK";
  if (!S.info.enabled) return "capture is off (SETTINGS)";
  if (!S.info.backend) return "RenderDoc not installed (SYSTEM)";
  if (!S.confirmed) return "confirm first";
  return "";
}

function bar() {
  if (!el.run) return;
  if (!S.running) el.sum.textContent = `${base(el.game.value) || "no game"} · ${base(el.exe.value) || "no executable"} → ${base(S.ws) || "workspace"}`;
  el.why.textContent = blocker();
  el.run.disabled = Boolean(el.why.textContent);
  el.run.textContent = S.running ? "CAPTURING…" : "LAUNCH + CAPTURE";
  el.checkBtn.disabled = S.running;
  el.cancel.hidden = !S.running;
}

async function run() {
  if (blocker()) return;
  const gamePath = el.game.value.trim(), exePath = el.exe.value.trim();
  S.running = true;
  bar();
  fill(el.result);
  el.progPanel.hidden = false;
  await el.prog.start();
  el.prog.log.append(logLine(`// CAPTURE :: ${exePath} → ${S.ws}`));
  el.progPanel.scrollIntoView({ block: "nearest" });
  try {
    const res = await api.capture({ gamePath, exePath, confirmed: true, captureAfter: Number(el.auto.value) || 0 });
    await el.prog.finish("ok", `${res.gathered} FILES · ${res.newVsStatic} NEW VS STATIC`);
    fill(el.result, renderResult(res));
    toast(`Captured ${res.gathered} file(s), ${res.newVsStatic} not seen by static extraction.`, "ok");
  } catch (err) {
    const cancelled = err.code === "cancelled";
    await el.prog.finish(cancelled ? "cancel" : "fail", cancelled ? "CAPTURE CANCELLED" : "CAPTURE FAILED");
    fill(el.result, renderFailure(err));
    toastErr(err, "Capture failed: ");
  } finally {
    S.running = false;
    S.confirmed = false;
    renderBefore();
    bar();
    emit("jobs");
    emit("workspace");
  }
}

import { registerView, code } from "../registry.js";

const VIEW = { mount, show: bar };
registerView({ id: "capture", arm: "dynamic", order: 10, title: "CAPTURE", subtitle: "frames from a running game", ...VIEW });
export default VIEW;
