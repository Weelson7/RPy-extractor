// 13 RUNTIME (dynamic arm): the engine's agent in a patched copy (UE4SS, BepInEx), the game's
// sound, a memory dump and an API trace of the running game. Each run is a job; the outputs land
// in the active workspace under .runtime/.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, viewHead, kv, toast, toastErr, pref, emit, browseBtn, errorBox, openBtn, assure } from "../ui.js";
import { jobProgress } from "../progress.js";
import { setGame, gameField } from "../game.js";

const S = { running: "" };
const el = {};
const input = (id, placeholder, key) => h("input", { class: "input mono grow", id, placeholder, value: pref(key) || "",
  spellcheck: "false", oninput: (e) => pref(key, e.target.value.trim()) });

function mount(root) {
  el.game = gameField("rt-game");
  el.exe = input("rt-exe", "/path/to/game/Game.exe", "rtExe");
  el.proc = input("rt-proc", "Game.exe or a pid", "rtProc");
  el.funcs = input("rt-funcs", "CreateFileW, ReadFile", "rtFuncs");
  el.secs = h("input", { class: "input mono", id: "rt-secs", type: "number", min: "1", value: pref("rtSecs") || "10", oninput: (e) => pref("rtSecs", e.target.value) });
  el.progHost = h("div", {});
  el.result = h("div", {});
  el.buttons = [btn("RUN AGENT", () => run("agent"), "primary"), btn("DUMP MEMORY", () => run("dump"), ""),
    btn("TRACE CALLS", () => run("trace"), ""), btn("RECORD SOUND", () => run("record"), "")];
  root.append(
    viewHead("13", "RUNTIME", "The game is running: load the engine's agent into a patched copy, record what it plays, dump its memory or trace its API calls. Each run is a job; the outputs land in the workspace under .runtime/."),
    assure([["GAME FOLDER READ-ONLY", "the agent goes into a marked patched copy beside it, never into the game"],
      ["UNATTENDED", "first-run questions of the tools are answered before launch; nothing to click"],
      ["YOUR CALL", "anti-cheat and online titles only produce warnings; you are responsible"]]),
    h("div", { class: "grid2" },
      h("div", { class: "col" },
        panel("13.A", "RUNTIME AGENT", badge("PATCHED COPY", "ok"),
          h("label", { class: "lbl", for: "rt-game" }, "GAME FOLDER (THE STRIP'S GAME)"), h("div", { class: "row" }, el.game, browseBtn(el.game, setGame)),
          h("label", { class: "lbl", for: "rt-exe" }, "EXECUTABLE"), h("div", { class: "row" }, el.exe,
            browseBtn(el.exe, (p) => pref("rtExe", p), (p) => api.browseFile(p || el.game.value.trim()).then((r) => r.path))),
          h("p", { class: "note" }, "Unreal: UE4SS writes Mappings.usmap and the object dump. Unity IL2CPP: BepInEx writes the interop assemblies."),
          h("div", { class: "row" }, el.buttons[0])),
        panel("13.B", "RUNNING PROCESS", null,
          h("label", { class: "lbl", for: "rt-proc" }, "PROCESS (IMAGE NAME OR PID)"), h("div", { class: "row" }, el.proc),
          h("label", { class: "lbl", for: "rt-funcs" }, "FUNCTIONS TO TRACE (FRIDA GLOBS, COMMA-SEPARATED)"), h("div", { class: "row" }, el.funcs),
          h("label", { class: "lbl", for: "rt-secs" }, "SECONDS (TRACE AND RECORDING)"), h("div", { class: "row" }, el.secs),
          h("div", { class: "row" }, el.buttons[1], el.buttons[2], el.buttons[3]))),
      h("div", { class: "col" }, el.progHost, el.result)));
}

function body(kind) {
  const proc = el.proc.value.trim(), seconds = Number(el.secs.value) || 10;
  const target = /^\d+$/.test(proc) ? { pid: Number(proc) } : { name: proc };
  if (kind === "agent") return { gamePath: el.game.value.trim(), exePath: el.exe.value.trim() };
  if (kind === "record") return { seconds };
  return { ...target, seconds, functions: el.funcs.value.split(",").map((f) => f.trim()).filter(Boolean) };
}

/** Why a run cannot start ("" when it can). */
function blocker(kind) {
  if (S.running) return `${S.running} is running`;
  if (kind === "agent") return !el.game.value.trim() ? "enter the game folder" : !el.exe.value.trim() ? "pick the executable" : "";
  return kind !== "record" && !el.proc.value.trim() ? "enter the process name or pid" : "";
}

async function run(kind) {
  const why = blocker(kind);
  if (why) return toast(`Cannot start: ${why}.`, "warn");
  S.running = kind;
  el.buttons.forEach((b) => { b.disabled = true; });
  const prog = jobProgress(kind, { logClass: "mini" });
  fill(el.progHost, panel("13.C", "RUN", null, prog.el));
  fill(el.result);
  await prog.start();
  try {
    const res = await api.runtime(kind, body(kind));
    await prog.finish("ok", `${kind.toUpperCase()} DONE`);
    fill(el.result, panel("13.D", "RESULT", openBtn(res.outputDir || res.wav || ""),
      Object.entries(res).filter(([k, v]) => k !== "success" && typeof v !== "object").map(([k, v]) => kv(k.toUpperCase(), h("span", { class: "mono" }, String(v)))),
      res.notCopied?.length ? h("p", { class: "note" }, `Left out of the copy (the OS refused to read them): ${res.notCopied.join(", ")}`) : null));
    toast(`${kind} finished.`, "ok");
  } catch (err) {
    await prog.finish(err.code === "cancelled" ? "cancel" : "fail", `${kind.toUpperCase()} FAILED`);
    fill(el.result, errorBox(err, `${kind.toUpperCase()} FAILED`));
    toastErr(err, `${kind} failed: `);
  } finally {
    S.running = "";
    el.buttons.forEach((b) => { b.disabled = false; });
    emit("jobs");
    emit("workspace");
  }
}

import { registerView } from "../registry.js";

const VIEW = { mount };
registerView({ id: "runtime", arm: "dynamic", order: 20, num: "13", title: "RUNTIME", subtitle: "agents, dumps, traces, sound", ...VIEW });
export default VIEW;
