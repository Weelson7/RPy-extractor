// The three arm homes: each opens on its end-to-end path, every step with a link to the view
// that runs it (planned steps marked; the steps of one view share its row, so a code is shown
// once); with no game picked yet, a START HERE first.
import { h, fill, btn, panel, badge, viewHead, goBtn, bus } from "../ui.js";
import { registerView, code, view } from "../registry.js";
import { currentGame, pickGame } from "../game.js";

const S = "shipped", R = "roadmap";
/** [step, what it does, view hash or "", state] per arm, in the order a user walks it. */
const PATHS = {
  static: ["STATIC", "The game is not running: look at what it ships, pull it into a workspace, curate it, read its code.", [
    ["SURVEY", "what each game or a whole library holds, read-only", "#survey", S],
    ["EXTRACT", "the engine plugins unpack, export and decode into a workspace", "#extract", S],
    ["WORKSPACE", "the files grouped by type, previews", "#workspace", S],
    ["SORT", "keep or trash, one by one", "#sort", S],
    ["CLEANUP", "empty, junk, duplicate, mislabeled and broken files", "#cleanup", S],
    ["MERGER", "frame sequences to video", "#merger", S],
    ["ANALYSIS", "Ghidra, ILSpy, Cpp2IL, unrpyc, GDRE, unluac, Detect It Easy, version diff", "#analysis", S],
    ["EMULATE + SOLVE", "run one isolated routine (Unicorn) or solve its inputs (angr)", "#analysis", S]]],
  dynamic: ["DYNAMIC", "The game is running: capture what it draws and plays, read its memory and calls, load an agent into a copy.", [
    ["CAPTURE", "GPU frames through RenderDoc: textures, meshes, shaders", "#capture", S],
    ["AGENTS", "UE4SS (Unreal) or BepInEx (Unity IL2CPP) in a patched copy: mappings, dumps", "#runtime", S],
    ["RECORD", "the game's sound from the system output, to WAV", "#runtime", S],
    ["DUMP + TRACE", "process memory through the OS, API calls through Frida", "#runtime", S],
    ["DEBUGGER + MEMORY", "x64dbg attached to the game's own process (live patching), Cheat Engine with a ViWo table", "#runtime", S],
    ["CPU PROFILE", "where the running game spends its CPU time: hot spots by export, module, thread", "#runtime", S],
    ["HOOKS + NETWORK", "a hook loader with hot reload, own-traffic tooling", "", R]]],
  patching: ["PATCHING", "You change its content: always in a marked patched copy, the game folder stays read-only.", [
    ["PATCHED COPY", "your workspace edits repacked into a copy of the game, verified", "#repack", S],
    ["ASSETS", "edited PNG, glTF and text tables encoded back into the game's formats, as a mod or by overwriting", "#assets", S],
    ["PATCH SETS", "byte, RVA and AOB patches, assembly through Keystone, export", "#patches", S],
    ["MODS", "pack a copy's changes, check them against a game update, apply several in order", "#patches", S],
    ["CHEAT ENGINE TABLE", "the game opened in Cheat Engine with a ViWo table", "#runtime", S]]],
};

/** The steps that one tab runs share a row, so each code is shown once on a home and names one
 * view; a planned step without a tab keeps its own row. */
function byTab(steps) {
  const rows = [];
  for (const s of steps) {
    const same = s[2] && rows.find((r) => r.hash === s[2]);
    if (same) same.steps.push(s);
    else rows.push({ hash: s[2], steps: [s] });
  }
  return rows;
}

/** One sub-line of a shared row: the step's name, what it does, PLANNED when it is. */
const sub = ([name, what, , state]) => h("li", {}, h("b", {}, name), h("span", { class: "dim" }, what), state === S ? null : badge("PLANNED", "mute"));

/** A row names the tab that runs it (its live code); one in another arm says where it opens. */
function step(arm, { hash, steps }) {
  const target = hash ? view(hash.slice(1)) : null;
  const elsewhere = target && target.arm !== arm ? ` (opens in ${target.arm.toUpperCase()})` : "";
  const shipped = steps.some((s) => s[3] === S);
  const [[name, what]] = steps;
  return h("li", { "data-state": shipped ? "done" : "wait" },
    h("b", { class: "mono" }, hash ? code(hash.slice(1)) : "—"), h("b", {}, steps.length > 1 ? target.title : name),
    steps.length > 1 ? h("div", {}, h("ul", { class: "path-sub" }, steps.map(sub)), elsewhere ? h("span", { class: "dim" }, elsewhere.trim()) : null)
      : h("span", { class: "dim" }, what + elsewhere),
    h("div", { class: "row" }, shipped ? null : badge("PLANNED", "mute"), hash ? goBtn(hash, "OPEN", "sm ghost") : null));
}

/** No game yet: the first thing to do, before the path. */
const start = () => (currentGame() ? null : panel("", "START HERE", null, // lettered by main.js
  h("p", {}, "Pick the game's folder first: every step below works on it. ViWo only reads it."),
  h("div", { class: "row" }, btn("PICK A GAME FOLDER", pickGame, "primary"))));

for (const [arm, [title, sub, steps]] of Object.entries(PATHS)) {
  const host = h("div", {});
  const show = () => fill(host, start());
  const mount = (root) => {
    root.append(viewHead(code(arm), title, sub), host,
      panel(`${code(arm)}.A`, "END-TO-END PATH", null, h("ol", { class: "path-steps" }, byTab(steps).map((x) => step(arm, x)))));
    show();
    bus.addEventListener("game", show);
  };
  registerView({ id: arm, arm, order: 0, title: `${title} HOME`, subtitle: "the path, step by step", mount, show });
}
