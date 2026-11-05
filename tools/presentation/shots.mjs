// Presentation frames: a user's walk through every view on a real game, one PNG per step.
// node shots.mjs <app url> <cdp port> <out folder> <width> <height> <game folder>
// Prints one JSON line per frame ({file, name, caption, detail, hold, pdf}): the video shows
// every frame for `hold` seconds with its caption, the PDF the frames marked `pdf` with detail.
import { writeFileSync, mkdirSync } from "node:fs";

const [APP, PORT, OUT, W, H, GAME] = process.argv.slice(2);
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" })).json();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let seq = 0;
const pending = new Map();
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
};
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const n = ++seq;
  pending.set(n, (msg) => (msg.error ? reject(new Error(`${method}: ${msg.error.message}`)) : resolve(msg.result)));
  ws.send(JSON.stringify({ id: n, method, params }));
});
const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result.value;
let index = 0;
const shot = async (name, caption, detail = "", { hold = 0, pdf = true } = {}) => {
  const file = `${String(++index).padStart(3, "0")}-${name}`;
  const png = (await send("Page.captureScreenshot", { format: "png" })).data;
  writeFileSync(`${OUT}/${file}.png`, Buffer.from(png, "base64"));
  const words = (caption.match(/\S+/g) || []).length;
  console.log(JSON.stringify({ file, name, caption, detail, pdf, hold: hold || Math.max(3.5, words / 2.6) }));
};
const until = async (expr, ms = 900000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await ev(expr)) return true; await sleep(1000); } return false; };
// a view reading a large workspace shows a skeleton first: the frame waits for its content
const go = async (hash, wait = 1800) => { await ev(`location.hash = '#${hash}'`); await sleep(wait); await until("!document.querySelector('#main .skel')", 600000); await ev("document.querySelector('#main').scrollTop = 0"); };
const press = (view, label) => ev(`(() => { const b = [...document.querySelectorAll('#view-${view} button')].find((x) => x.textContent.trim().startsWith(${JSON.stringify(label)}) && !x.disabled); if (!b) return false; b.click(); return true; })()`);
const live = "!!document.querySelector('#status-chips [data-kind=live]')";
const idle = () => until(`!${live}`);
const into = (selector) => ev(`document.querySelector(${JSON.stringify(selector)})?.scrollIntoView({ block: "start" })`);

await send("Emulation.setDeviceMetricsOverride", { width: +W, height: +H, deviceScaleFactor: 1, mobile: false });
await send("Page.navigate", { url: APP });
await sleep(2500);
await shot("landing", "First start: ViWo checks itself and installs what is missing, nothing to answer.",
  "The landing screen runs the preflight. Every missing tool is fetched from its pinned release (HTTPS, size and sha256 checked) into third_party/, Python packages from their hash locks; nothing is asked and nothing is installed anywhere else.");
for (let i = 0; i < 120 && !(await ev("!!document.querySelector('#mods li')")); i++) await sleep(500);
await ev("document.querySelector('.landing button, #landing button')?.click()");
await ev(`localStorage.setItem('viwo.gamePath', ${JSON.stringify(GAME)})`);
await send("Page.reload");
await sleep(3500);
await go("static");
await shot("static-home", "STATIC: the game is not running. The path, step by step.",
  "Each arm opens on its end-to-end path. The top bar holds the shared game selector and the workspace, SYSTEM, JOBS, WORKBOOKS, RUNBOOKS and SETTINGS (00 to 04); the rail lists the arm's views, numbered S0, S1... as plugins add them.");
await go("survey"); await press("survey", "SURVEY"); await sleep(1500); await idle(); await sleep(1500);
await shot("survey", "SURVEY: what ViWo can pull from this game, read-only.",
  "A read-only coverage report: the engine found, which files each tool can open, what needs a key, and the dense unknown blobs the carver would scan. It runs on one game or a whole library.");
await go("extract"); await press("extract", "DETECT ENGINE"); await sleep(3000);
await shot("extract-detect", "EXTRACT: the engine is detected; the game folder is opened read-only.",
  "Detection scores every plugin on the folder's evidence; the mode (auto, one engine, or mixed for a game that bundles several), the extension filter and the embedded-file carver are chosen here.");
await press("extract", "RUN EXTRACTION"); await sleep(1500);
for (let n = 0; n < 40 && (await ev(live)); n++) {
  await shot("extract-running", "Every stage of the run is live: unpack, carve, collect, decode.",
    "The job block shows every stage (probe, detect, unpack, export, carve, collect, decode) with counters, a ticker and the log of every tool, live.", { hold: 0.7, pdf: n === 2 });
  await sleep(1200);
}
await until(`!${live}`, 4 * 3600000); await sleep(3000); // the whole run (the demo subset: 2 h 20 min): the result and the browse views need it
await into("#view-extract .result-host");
await shot("extract-result", "The result: every file out, every format decoded, every tool named.",
  "RESULT: files copied by type, archives found and extracted, the backend that handled each, every fallback to a spare and every skipped entry said as a warning. The provenance map records where every file came from.");
await go("workspace", 2500);
await shot("workspace", "WORKSPACE: the files grouped by type; trash and restore by group.",
  "The workspace groups files by extension; whole groups go to the trash and back. Nothing is deleted until the trash is cleared, and only in a folder ViWo owns.");
await go("sort", 2500);
await shot("sort", "SORT: one file at a time, previews first, keep or trash, undo.",
  "SORT walks the files one by one with a preview (images, audio, video, text), keep, trash, rename and undo.");
await go("cleanup", 1500); await press("cleanup", "SCAN"); await sleep(1500); await idle(); await sleep(2000);
await shot("cleanup", "CLEANUP: empty files, junk, wrong extensions and exact duplicates, all reversible.",
  "The sanitizer plans first: empty files, junk, mislabeled extensions (by magic bytes) and exact duplicates; apply writes an undo token.");
await go("merger", 2500);
await shot("merger", "MERGER: numbered frames and clips become one video.",
  "The media merger finds numbered frame sequences and clip runs and builds one video per candidate through the pinned ffmpeg.");
await go("analysis", 1500); await press("analysis", "LIST TARGETS"); await sleep(5000);
await shot("analysis", "ANALYSIS: the game's code (Ghidra, ILSpy, Cpp2IL, unrpyc, GDRE, unluac, version diff).",
  "Code analysis of a copy: Ghidra headless (functions, decompiled C) and the Continue in Ghidra handoff, ilspycmd for .NET, Cpp2IL for IL2CPP, unrpyc, GDRE Tools, unluac, Detect It Easy, Unicorn and angr on isolated routines and a function-by-function version diff. Nothing here runs the game.");
await go("dynamic");
await shot("dynamic-home", "DYNAMIC: the game is running. Capture, agents, dumps, traces.",
  "The dynamic arm is a feature switch with warnings and one confirmation: anti-cheat and online titles are said, never refused.");
await go("capture", 2000);
await shot("capture", "CAPTURE: GPU frames through RenderDoc, harvested into the workspace.",
  "RenderDoc captures a frame (unattended by default), the harvest pulls its textures and shader disassembly, and the diff says what was new against the static extraction.");
await go("runtime", 2000);
await shot("runtime", "RUNTIME: an engine agent in a patched copy, memory dumps, API traces, sound, debugger.",
  "The engine's runtime agent runs in a marked patched copy (UE4SS for Unreal mappings and object dumps, BepInEx for Unity IL2CPP), memory dumps, Frida API traces, the game's sound to WAV, and x64dbg attached to the game's own process (live patching) or Cheat Engine with a ViWo table, as tracked children.");
await press("runtime", "LIST TARGETS"); await sleep(4000); await into("#view-runtime .panel:last-of-type");
await shot("runtime-debugger", "DEBUGGER AND MEMORY: x64dbg on the game's own process, Cheat Engine with a table.",
  "The game's executables x64dbg and Cheat Engine can take. x64dbg attaches to the running game (or starts its own executable), so a byte patched live lands in the real process; HOW TO opens the tool's workbook.");
await go("patching");
await shot("patching-home", "PATCHING: you change the game's content, always in a marked copy.",
  "Nothing writes into the game folder: repack, patch sets and mods all write a separate, marked patched copy (.viwo-patched).");
await go("repack", 1500); await press("repack", "PLAN"); await sleep(4000);
await shot("repack", "PATCHED COPY: workspace edits repacked into the game's own containers, verified.",
  "Edited workspace files are traced back to their container through the provenance map, repacked by the engine's packer (an override archive where the game loads one) and verified by reading the result back.");
await go("patches", 2000);
await shot("patches", "PATCHES + MODS: byte and AOB patch sets, mod packages, update checks.",
  "Patch sets by offset, RVA or AOB pattern (assembly through Keystone) with a byte diff; mod packages built from a patched copy, checked against another game version and applied in order.");
await go("system", 3500);
await shot("system", "SYSTEM: every optional tool by engine, pinned and installed by itself.",
  "Every optional tool by engine: what it enables, its pinned version, whether it is installed; diagnostics and update checks.");
await go("system@formats", 3500);
await shot("formats", "Every format and the backend that handles it, with its spare.",
  "Every slot (a format or a job) with its main and spare backend and why a backend is unavailable; a spare is promoted when the main is missing.");
await go("jobs", 2500);
await shot("jobs", "JOBS: every run, its log and its result.",
  "Every job with its state, its log and its result; each extraction also leaves a run record that `viwo replay` re-runs.");
await go("settings", 2500);
await shot("settings", "SETTINGS: features, plugins, tool paths and options, applied at once.",
  "Features, plugins, slot bindings, tool paths and plugin options, written to startup.ini and applied without a restart.");
await go("workbooks", 2500); await ev("[...document.querySelectorAll('#view-workbooks .job')].find((b) => b.textContent.includes('Patch a byte'))?.click()"); await sleep(1200);
await shot("workbooks", "WORKBOOKS: how to do one thing in a child tool's own interface, step by step.",
  "Teaching, never automation: patch a byte in x64dbg live and into a file, find the code behind a string in Ghidra, find what writes a value in Cheat Engine. Checked against the pinned versions; a workbook written for another version says so.");
await go("runbooks", 2500); await ev("[...document.querySelectorAll('#view-runbooks .job')].find((b) => b.textContent.includes('Extract a game'))?.click()"); await sleep(1200);
await shot("runbooks", "RUNBOOKS: ViWo's actions and the steps you do, run in order; record your own.",
  "An action step runs a job through the same handler as its view; a step you do pauses the run until DONE. RECORD A WORKFLOW catches every action of every view and saves it as a runbook whose replay stops only where an answer differs from the recording.");
await ev("document.querySelector('#dock-toggle').click()"); await sleep(2500);
await shot("console", "The activity console: every line every tool printed.",
  "The activity console at the bottom keeps every line of every tool, with warnings marked.");
process.exit(0);
