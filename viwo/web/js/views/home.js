// The three arm homes: each opens on its end-to-end path, every step marked SHIPPED or ROADMAP,
// with a link to the view that runs it. The paths follow doc 16.2b (rungs A, D, T).
import { h, panel, badge, viewHead, goBtn } from "../ui.js";
import { registerView } from "../registry.js";

const S = "shipped", R = "roadmap";
/** [step, what it does, view hash or "", state, rung] per arm, in the order a user walks it. */
const PATHS = {
  static: ["S", "STATIC", "The game is not running: look at what it ships, pull it into a workspace, curate it, read its code.", [
    ["SURVEY", "what each game or a whole library holds, read-only", "#survey", S, ""],
    ["EXTRACT", "the engine plugins unpack, export and decode into a workspace", "#extract", S, ""],
    ["WORKSPACE", "the files grouped by type, previews", "#workspace", S, ""],
    ["SORT", "keep or trash, one by one", "#sort", S, ""],
    ["CLEANUP", "empty, junk, duplicate, mislabeled and broken files", "#cleanup", S, ""],
    ["MERGER", "frame sequences to video", "#merger", S, ""],
    ["ANALYSIS", "Ghidra, ILSpy, Cpp2IL, unrpyc, GDRE, unluac, Detect It Easy, version diff", "#analysis", S, "A1-A3"],
    ["EMULATE + SOLVE", "run one isolated routine (Unicorn) or solve its inputs (angr)", "#analysis", S, "A4"]]],
  dynamic: ["D", "DYNAMIC", "The game is running: capture what it draws and plays, read its memory and calls, load an agent into a copy.", [
    ["CAPTURE", "GPU frames through RenderDoc: textures, meshes, shaders", "#capture", S, "D1"],
    ["AGENTS", "UE4SS (Unreal) or BepInEx (Unity IL2CPP) in a patched copy: mappings, dumps", "#runtime", S, "D2"],
    ["RECORD", "the game's sound from the system output, to WAV", "#runtime", S, "D2"],
    ["DUMP + TRACE", "process memory through the OS, API calls through Frida", "#runtime", S, "D3"],
    ["DEBUGGER + MEMORY", "continue in x64dbg or Cheat Engine (attached to the game)", "#analysis", S, "D3"],
    ["CPU PROFILE", "where the running game spends its CPU time: hot spots by export, module, thread", "#runtime", S, "D4"],
    ["HOOKS + NETWORK", "a hook loader with hot reload, own-traffic tooling", "", R, "D4"]]],
  patching: ["P", "PATCHING", "You change its content: always in a marked patched copy, the game folder stays read-only.", [
    ["PATCHED COPY", "your workspace edits repacked into a copy of the game, verified", "#repack", S, ""],
    ["PATCH SETS", "byte, RVA and AOB patches, assembly through Keystone, export", "#patches", S, "T1"],
    ["MODS", "pack a copy's changes, check them against a game update, apply several in order", "#patches", S, "T2"],
    ["CHEAT ENGINE TABLE", "the game opened in Cheat Engine with a ViWo table", "#analysis", S, "D3"]]],
};

function step([name, what, hash, state, rung], i) {
  return h("li", { "data-state": state === S ? "done" : "wait" },
    h("b", { class: "mono" }, String(i + 1).padStart(2, "0")), h("b", {}, name), h("span", { class: "dim" }, what),
    h("div", { class: "row" }, rung ? h("span", { class: "mono dim small" }, rung) : null,
      badge(state === S ? "SHIPPED" : "ROADMAP", state === S ? "ok" : "mute"), hash ? goBtn(hash, "OPEN", "sm ghost") : null));
}

for (const [arm, [num, title, sub, steps]] of Object.entries(PATHS)) {
  const mount = (root) => root.append(viewHead(num, title, sub),
    panel(`${num}.A`, "END-TO-END PATH", badge(`${steps.filter((s) => s[3] === S).length}/${steps.length} SHIPPED`, "ok"),
      h("ol", { class: "path-steps" }, steps.map(step))));
  registerView({ id: arm, arm, order: 0, num, title: `${title} HOME`, subtitle: "the path, step by step", mount });
}
