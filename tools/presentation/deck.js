// The technical deck (PowerPoint), built by tools/presentation/deck.py:
//   node deck.js <data.json> <frames dir> <out.pptx> <pptxgen.bundle.js>
// The data (counts, CTF results, engines) comes from the code and the passes; the prose is
// here. pptxgenjs is one pinned file (viwo/data/tools.json), loaded as it is: it brings its
// own zip writer and needs nothing installed.
const fs = require("fs");
const path = require("path");
const [DATA, FRAMES, OUT, BUNDLE] = process.argv.slice(2);
const pptxgen = new Function(fs.readFileSync(BUNDLE, "utf8") + "\n;return PptxGenJS;")();
const D = JSON.parse(fs.readFileSync(DATA, "utf8"));
const K = D.kpis;

// the product's own look: near-black, one red, a teal for "ok"
const THEME = {
  name: "ViWo",
  headFontFace: "Arial",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "F4ECEC", lt1: "0C0A0B", dk2: "B3A4A6", lt2: "191113",
    accent1: "FF3B3B", accent2: "2DD4BF", accent3: "FFB020", accent4: "3B2125",
    accent5: "7A2A2E", accent6: "5E5356", hlink: "FF3B3B", folHlink: "B3A4A6",
  },
};
const H = THEME.colors;
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = `ViWo technical overview ${K.version}`;
pres.author = "ViWo";
const C = { text1: H.dk1, text2: H.dk2, background1: H.lt1, background2: H.lt2, accent1: H.accent1, accent2: H.accent2, accent3: H.accent3, accent4: H.accent4, accent5: H.accent5, accent6: H.accent6 };

const footer = [
  { text: { text: `VIWO  //  ${K.version}`, options: { x: 0.5, y: 5.2, w: 4, h: 0.25, fontSize: 10, color: C.accent6, charSpacing: 2, margin: 0 } } },
];
const number = { x: 9.0, y: 5.2, w: 0.5, h: 0.25, fontSize: 10, color: C.accent6, align: "right" };
const tag = { name: "tag", type: "body", x: 0.5, y: 0.38, w: 9, h: 0.26, fontSize: 11, bold: true, color: C.accent1, charSpacing: 3, margin: 0 };
const title = { name: "title", type: "title", x: 0.5, y: 0.64, w: 9, h: 0.7, fontSize: 32, bold: true, color: C.text1, charSpacing: 1, margin: 0, valign: "middle", align: "left" };

pres.defineSlideMaster({
  title: "COVER", background: { color: H.lt1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 1.45, w: 4.1, h: 1.0, fontSize: 60, bold: true, color: C.accent1, charSpacing: 8, margin: 0, valign: "middle", align: "left" }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.5, y: 2.55, w: 4.0, h: 1.7, fontSize: 16, color: C.text1, margin: 0, valign: "top" }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT", background: { color: H.lt1 }, slideNumber: number,
  objects: [{ placeholder: { options: tag, text: "" } }, { placeholder: { options: title, text: "" } }, ...footer],
});
pres.defineSlideMaster({
  title: "DIVIDER", background: { color: H.lt2 }, slideNumber: number,
  objects: [
    { placeholder: { options: { ...tag, y: 2.0 }, text: "" } },
    { placeholder: { options: { ...title, y: 2.3, h: 0.9, fontSize: 40 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.5, y: 3.3, w: 8, h: 1.4, fontSize: 16, color: C.text2, margin: 0, valign: "top" }, text: "" } },
    ...footer,
  ],
});

let section = "";
const sec = (name) => { section = name; pres.addSection({ title: name }); };
const slide = (code, heading, notes, master = "CONTENT") => {
  const s = pres.addSlide({ masterName: master, sectionTitle: section });
  s.addText(code, { placeholder: "tag" });
  s.addText(heading, { placeholder: "title" });
  if (notes) s.addNotes(notes);
  return s;
};
let n = 0;
const name = (what) => `${what} ${++n}`;
/** A panel as in the UI: dark card, hairline border, a red corner bracket top right. */
const card = (s, x, y, w, h) => {
  s.addShape(pres.ShapeType.rect, { x, y, w, h, fill: { color: C.background2 }, line: { color: C.accent4, width: 0.75 }, objectName: name("Panel") });
  s.addShape(pres.ShapeType.line, { x: x + w - 0.18, y, w: 0.18, h: 0, line: { color: C.accent1, width: 1.5 }, objectName: name("Bracket") });
  s.addShape(pres.ShapeType.line, { x: x + w, y, w: 0, h: 0.18, line: { color: C.accent1, width: 1.5 }, objectName: name("Bracket") });
};
const text = (s, t, o) => s.addText(t, { isTextBox: true, margin: 0, color: C.text1, fontSize: 14, valign: "top", objectName: name("Text"), ...o });
const shot = (s, file, x, y, w) => {
  const h = (w * 9) / 16;
  s.addImage({ path: path.join(FRAMES, file), x, y, w, h, altText: file.replace(/^\d+-|\.png$/g, "").replace(/-/g, " "), objectName: name("Screenshot") });
  s.addShape(pres.ShapeType.rect, { x, y, w, h, fill: { type: "none" }, line: { color: C.accent4, width: 0.75 }, objectName: name("Frame") });
};
const stat = (s, x, y, w, big, label, color = C.accent1) => {
  card(s, x, y, w, 1.5);
  text(s, big, { x: x + 0.2, y: y + 0.18, w: w - 0.4, h: 0.75, fontSize: 40, bold: true, color, valign: "middle", fit: "shrink" });
  text(s, label, { x: x + 0.2, y: y + 0.95, w: w - 0.4, h: 0.45, fontSize: 12, color: C.text2 });
};
const num = (v) => Number(v).toLocaleString("en-US");

// ---------------------------------------------------------------- cover
sec("Overview");
{
  const s = pres.addSlide({ masterName: "COVER", sectionTitle: section });
  s.addText("VIWO", { placeholder: "title" });
  s.addText([
    { text: "Vidya Wormhole", options: { bold: true, breakLine: true } },
    { text: "Look inside any game: extract it, analyse it, change it.", options: { color: C.text2, breakLine: true } },
    { text: " ", options: { breakLine: true } },
    { text: `Technical overview  ·  v${K.version}  ·  ${K.date}`, options: { fontSize: 12, color: C.text2 } },
  ], { placeholder: "body" });
  shot(s, "002-static-home.png", 4.75, 1.45, 4.75);
  s.addNotes("ViWo is a local-first orchestrator for game reverse engineering. This deck covers what it is, how it is built, what it does on a real game, and how far each claim is proven.");
}
{
  const s = slide("// 01 · WHAT IT IS", "One tool, three arms", "The four numbers are counted from the code at build time.");
  text(s, "A community-owned orchestrator. Point it at a game folder: it recognises the engine, sends every container to the best tool it has, and records where every file came from. The game folder is never written to.", { x: 0.5, y: 1.5, w: 9, h: 0.9, fontSize: 16, color: C.text2 });
  const w = 2.1, g = 0.2;
  [[K.plugin_count, `engine plugins (+ ${K.game_count} game plugins)`], [K.slot_count, "slots: formats and jobs"], [K.tool_count, "pinned third-party tools"], [K.test_count, "tests"]]
    .forEach(([big, label], i) => stat(s, 0.5 + i * (w + g), 2.7, w, big, label));
  text(s, "MIT, forkable, Python 3.11+, a web UI with no build step.", { x: 0.5, y: 4.5, w: 9, h: 0.35, fontSize: 14 });
}
{
  const s = slide("// 02 · PHILOSOPHY", "Rules the code is held to", "These are the owner's rules. Each one is enforced by tests, not by convention.");
  const items = [
    ["For everyone", "Modders, artists, translators, researchers, preservationists, the curious. The tool judges neither the user nor the purpose."],
    ["No gates in the tool", "Nothing is refused because of what a game is. Anti-cheat and online titles give a warning and one opt-in."],
    ["Game folder is read-only", "Extraction copies. Repack, patches and agents write a separate, marked patched copy."],
    ["Never silent", "A fallback, a skipped file or a failure is said in the console and the CLI, with the file and the reason."],
  ];
  const w = 4.4, h = 1.55;
  items.forEach(([head, body], i) => {
    const x = 0.5 + (i % 2) * (w + 0.2), y = 1.55 + Math.floor(i / 2) * (h + 0.2);
    card(s, x, y, w, h);
    text(s, head, { x: x + 0.25, y: y + 0.2, w: w - 0.5, h: 0.35, fontSize: 16, bold: true });
    text(s, body, { x: x + 0.25, y: y + 0.6, w: w - 0.5, h: 0.85, fontSize: 14, color: C.text2 });
  });
}

// ---------------------------------------------------------------- how it is built
sec("How it is built");
{
  const s = slide("// 03 · ARCHITECTURE", "A small core, plugins around it", "Imports only go left. A test adds a whole new engine plugin and shows nothing outside its folder changes.");
  const cols = [["contracts", "interfaces, value types"], ["OS layer", "Windows, Linux"], ["plugins + backends", "one folder per engine"], ["core", "wiring, pipeline, arms"], ["CLI · API + web UI", "two clients of the core"]];
  const w = 1.64, g = 0.2, y = 1.7, h = 1.25;
  cols.forEach(([head, body], i) => {
    const x = 0.5 + i * (w + g);
    card(s, x, y, w, h);
    text(s, head, { x: x + 0.12, y: y + 0.2, w: w - 0.24, h: 0.5, fontSize: 14, bold: true, valign: "middle" });
    text(s, body, { x: x + 0.12, y: y + 0.72, w: w - 0.24, h: 0.45, fontSize: 11, color: C.text2 });
    if (i) s.addShape(pres.ShapeType.line, { x: x - g + 0.03, y: y + h / 2, w: g - 0.06, h: 0, line: { color: C.accent1, width: 1.25, endArrowType: "triangle" }, objectName: name("Arrow") });
  });
  const facts = [["Sealed", "A new engine is one new folder. Core names no engine and no engine's file layout."], ["Pinned", "Every third-party tool has a version, size and sha256, and installs itself off screen."], ["Isolated", "GPL tools run only as separate processes. A broken plugin disables only itself."]];
  facts.forEach(([head, body], i) => {
    const x = 0.5 + i * 3.07;
    text(s, head.toUpperCase(), { x, y: 3.35, w: 2.85, h: 0.3, fontSize: 12, bold: true, color: C.accent1, charSpacing: 2 });
    text(s, body, { x, y: 3.68, w: 2.85, h: 1.1, fontSize: 14, color: C.text2 });
  });
}
{
  const s = slide("// 04 · ARMS", "Static, dynamic, patching", "Each arm opens on its own home view. Static never runs the game.");
  const arms = [
    ["STATIC", "the game is not running", ["Survey what can come out", "Extract and decode every file", "Sort, clean up, merge", "Analyse code: Ghidra, ILSpy, Cpp2IL"]],
    ["DYNAMIC", "the game is running", ["Capture GPU frames (RenderDoc)", "Engine agents in a patched copy", "Memory dump, API trace, CPU profile", "x64dbg and Cheat Engine on the process"]],
    ["PATCHING", "you change its content", ["Repack edits into the engine's own container", "Patch sets that survive updates", "Mod packages: pack, check, apply", "Always into a patched copy"]],
  ];
  const w = 2.87, h = 3.2;
  arms.forEach(([head, sub, lines], i) => {
    const x = 0.5 + i * (w + 0.2), y = 1.55;
    card(s, x, y, w, h);
    text(s, head, { x: x + 0.25, y: y + 0.2, w: w - 0.5, h: 0.4, fontSize: 20, bold: true, color: C.accent1, charSpacing: 3 });
    text(s, sub, { x: x + 0.25, y: y + 0.62, w: w - 0.5, h: 0.3, fontSize: 12, color: C.text2, italic: true });
    text(s, lines.map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < lines.length - 1, paraSpaceAfter: 6 } })), { x: x + 0.25, y: y + 1.05, w: w - 0.5, h: 2.0, fontSize: 14 });
  });
}
{
  const s = slide("// 05 · PIPELINE", "From game folder to workspace", "Independent work runs on one pool of workers capped at 80 percent of the processors. Results are taken in order, so every run comes out the same.");
  const steps = [["PREPARE", "claim the workspace, snapshot the game"], ["DETECT", "every plugin scores the folder"], ["UNPACK", "archives, nested to depth 10"], ["EXPORT", "each engine's own exporter"], ["CARVE", "files hidden inside blobs"], ["COLLECT", "hash, dedupe, group by type"], ["DECODE", "to PNG, WAV, glTF, JSON"], ["VERIFY", "game unchanged, run record"]];
  const w = 2.1, h = 1.05;
  steps.forEach(([head, body], i) => {
    const x = 0.5 + (i % 4) * (w + 0.2), y = 1.55 + Math.floor(i / 4) * (h + 0.2);
    card(s, x, y, w, h);
    text(s, String(i + 1).padStart(2, "0"), { x: x + 0.15, y: y + 0.14, w: 0.4, h: 0.3, fontSize: 12, bold: true, color: C.accent1 });
    text(s, head, { x: x + 0.55, y: y + 0.12, w: w - 0.7, h: 0.32, fontSize: 14, bold: true, charSpacing: 2 });
    text(s, body, { x: x + 0.15, y: y + 0.5, w: w - 0.3, h: 0.5, fontSize: 11, color: C.text2 });
  });
  text(s, [
    { text: "Parallel where the work is independent. ", options: { bold: true } },
    { text: "Nested-archive search, archive members, carving, hashing and WolvenKit's decode share one worker budget; the workspace keeps one writer.", options: { color: C.text2 } },
  ], { x: 0.5, y: 4.15, w: 9, h: 0.8, fontSize: 14 });
}

// ---------------------------------------------------------------- on a real game
sec("On a real game");
{
  const s = slide("// 06 · CYBERPUNK 2077", "Seven archives, 183,621 files", "The demo subset: seven archives, 6.7 GB, plus the executable and the game scripts. Every archive unpacked; textures to PNG, meshes to glTF, resources to JSON.");
  shot(s, "045-extract-result.png", 0.5, 1.5, 5.9);
  const facts = [["183,621", "files in the workspace"], ["7 / 7", "archives unpacked"], ["126", "file types, grouped"]];
  facts.forEach(([big, label], i) => {
    const y = 1.5 + i * 1.13;
    text(s, big, { x: 6.7, y, w: 2.8, h: 0.6, fontSize: 34, bold: true, color: C.accent1, valign: "middle" });
    text(s, label, { x: 6.7, y: y + 0.6, w: 2.8, h: 0.35, fontSize: 14, color: C.text2 });
  });
}
{
  const s = slide("// 07 · WORKSPACE", "Your files, by type", "The workspace groups files by extension. Sort walks them one by one with a preview; trash is recoverable until cleared.");
  shot(s, "046-workspace.png", 0.5, 1.5, 4.4);
  shot(s, "047-sort.png", 5.1, 1.5, 4.4);
  text(s, "WORKSPACE: whole types to the trash and back.", { x: 0.5, y: 4.1, w: 4.4, h: 0.6, fontSize: 14, color: C.text2 });
  text(s, "SORT: one file at a time, preview first, keep or trash, undo.", { x: 5.1, y: 4.1, w: 4.4, h: 0.6, fontSize: 14, color: C.text2 });
}
{
  const s = slide("// 08 · DYNAMIC", "Debug the game's own process", "x64dbg attaches to the running game by pid, or starts the game's own executable, so a live patch lands in the real process.");
  shot(s, "054-runtime-debugger.png", 3.9, 1.5, 5.6);
  text(s, [
    { text: "x64dbg on the live process: a patch takes effect at once.", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
    { text: "Cheat Engine opens with a table that attaches when the game runs.", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
    { text: "Dumps, API traces, CPU profiles and recorded sound land in the workspace.", options: { bullet: true } },
  ], { x: 0.5, y: 1.5, w: 3.2, h: 3.1, fontSize: 14 });
}
{
  const s = slide("// 09 · GUIDES", "Native tools stay native", "ViWo teaches the child tool's own interface and sequences its own actions around it. It does not embed or drive the tool.");
  shot(s, "062-workbooks.png", 0.5, 1.5, 5.6);
  const items = [["Workbooks", "Step-by-step how-tos for x64dbg, Ghidra, Cheat Engine and RenderDoc."], ["Runbooks", "Named, editable sequences of ViWo's own actions."], ["Workflows", "Record a session; replay stops where an answer differs."]];
  items.forEach(([head, body], i) => {
    const y = 1.5 + i * 1.08;
    text(s, head, { x: 6.4, y, w: 3.1, h: 0.32, fontSize: 16, bold: true, color: C.accent1 });
    text(s, body, { x: 6.4, y: y + 0.34, w: 3.1, h: 0.65, fontSize: 14, color: C.text2 });
  });
}
{
  const s = slide("// 10 · ENGINES", `${D.engines.length} engine plugins`, "Each plugin holds for every game on its engine; what one title adds lives in a game plugin under it.");
  const w = 2.1, h = 0.5;
  D.engines.forEach((e, i) => {
    const x = 0.5 + (i % 4) * (w + 0.2), y = 1.55 + Math.floor(i / 4) * (h + 0.15);
    s.addShape(pres.ShapeType.rect, { x, y, w, h, fill: { color: C.background2 }, line: { color: C.accent4, width: 0.75 }, objectName: name("Chip") });
    text(s, e, { x: x + 0.12, y, w: w - 0.24, h, fontSize: 12, valign: "middle", fit: "shrink" });
  });
  text(s, "Game plugins today: Cyberpunk 2077 (REDengine), Bannerlord (TaleWorlds).", { x: 0.5, y: 4.9, w: 9, h: 0.25, fontSize: 12, color: C.text2 });
}

// ---------------------------------------------------------------- how far it is proven
sec("How far it is proven");
{
  const s = slide("// 11 · QUALITY", "Held to account by tests", "A commit runs format, lint, size caps and only the tests its change is close to, in parallel. The whole suite runs before a merge or a tag.");
  s.addChart(pres.charts.DOUGHNUT, [{ name: "Contract rows", labels: ["Implemented", "Partial", "Open"], values: [Number(K.conf_implemented), Number(K.conf_partial), Number(K.conf_open)] }], {
    x: 0.5, y: 1.45, w: 4.2, h: 3.5, holeSize: 62, chartColors: [H.accent2, H.accent3, H.accent5],
    showTitle: true, title: "Contract conformance (rows)", titleColor: H.dk1, titleFontSize: 14, titleFontFace: "+mn-lt",
    showLegend: true, legendPos: "b", legendColor: H.dk2, legendFontSize: 12, legendFontFace: "+mn-lt",
    showPercent: false, showValue: true, dataLabelColor: H.lt1, dataLabelFontSize: 12, dataLabelFontFace: "+mn-lt", dataBorder: { pt: 1, color: H.lt1 },
    altText: `Contract conformance: ${K.conf_implemented} implemented, ${K.conf_partial} partial, ${K.conf_open} open`,
  });
  const rows = [[K.test_count, "tests, property tests over random inputs first"], ["80%", "of the processors, the cap for tests and pipeline alike"], ["40 / 250", "lines per function and per file, enforced"]];
  rows.forEach(([big, label], i) => {
    const y = 1.55 + i * 1.12;
    text(s, big, { x: 5.1, y, w: 4.4, h: 0.55, fontSize: 30, bold: true, color: C.accent1, valign: "middle" });
    text(s, label, { x: 5.1, y: y + 0.56, w: 4.4, h: 0.45, fontSize: 14, color: C.text2 });
  });
}
{
  const s = slide("// 12 · CTF", "Flags on real installs", "Each game has a list of concrete things that must come out. The game folder is hashed before and after every run.");
  const names = { "pass-aoe": "Age of Empires II HD", "pass-approximately-up-build-25884550": "Approximately Up", "pass-cyberpunk-2077": "Cyberpunk 2077", "pass-mount-blade-2-bannerlord": "M&B II: Bannerlord", "pass-schedule-i": "Schedule I", "pass-team-fortress-2": "Team Fortress 2", "pass-total-war-rome-ii": "Total War: Rome II", "pass-zipped-game-data": "A Ren'Py title" };
  const head = (t, align = "left") => ({ text: t, options: { bold: true, color: H.accent1, fill: { color: H.lt2 }, align, fontSize: 12 } });
  const cell = (t, o = {}) => ({ text: String(t), options: { color: H.dk1, fontSize: 12, ...o } });
  const rows = [[head("GAME"), head("ENGINE"), head("FILES OUT", "right"), head("FLAGS", "right"), head("GAME FOLDER", "right")]];
  D.games.forEach((g) => {
    const all = g.flags > 0 && g.ok === g.flags;
    rows.push([cell(names[g.game] || g.game, { bold: true }), cell(g.engine, { color: H.dk2 }), cell(num(g.files), { align: "right" }),
      cell(`${g.ok} / ${g.flags}`, { align: "right", bold: true, color: all ? H.accent2 : H.accent3 }),
      cell(g.unchanged ? "unchanged" : "CHANGED", { align: "right", color: g.unchanged ? H.dk2 : H.accent1 })]);
  });
  s.addTable(rows, { x: 0.5, y: 1.5, w: 9, colW: [2.9, 1.5, 1.5, 1.4, 1.7], rowH: 0.36, border: { type: "solid", pt: 0.5, color: H.accent4 }, fill: { color: H.lt1 }, valign: "middle", objectName: name("Table") });
  const full = D.games.filter((g) => g.flags > 0 && g.ok === g.flags).length;
  text(s, `${full} of ${D.games.length} games meet every flag. An amber row is one flag short.`, { x: 0.5, y: 4.85, w: 9, h: 0.28, fontSize: 12, color: C.text2 });
}
{
  const c = D.challenges[0];
  const s = slide("// 13 · CTF CHALLENGE", "Every Cyberpunk 2077 song", `${c.how} Limits: ${c.limits}`);
  [["553", "tracks"], ["30.8 h", "of music"], ["9.9 GB", "of FLAC"], ["0", "failed"]].forEach(([big, label], i) => stat(s, 0.5 + i * 2.3, 1.55, 2.1, big, label, i === 3 ? C.accent2 : C.accent1));
  text(s, [
    { text: "How. ", options: { bold: true } },
    { text: "ViWo unpacked the three audio archives (9,387 Wwise files), read each file's length and channels, and kept the stereo tracks of 100 seconds to 15 minutes.", options: { color: C.text2, breakLine: true } },
    { text: "Limit. ", options: { bold: true } },
    { text: "Wwise names media by number, so the files carry ids, not titles.", options: { color: C.text2 } },
  ], { x: 0.5, y: 3.35, w: 9, h: 1.5, fontSize: 14, paraSpaceAfter: 8 });
}
{
  const s = slide("// 14 · STATUS", "What is proven, what is not", "Real means: done on a real install with every flag of its pass met. Edit, repack and read-back are covered by tests on the other engines, not yet by a real game.");
  const total = D.engines.length;
  const rows = [["8", `of ${total} engines`, "Extract proven on a real game", C.accent2], ["1", `of ${total} engines`, "Edit, repack and read back proven (Doom)", C.accent3], ["0", `of ${total} engines`, "The game loading a change proven", C.accent1], ["0", "real games", "Run on Linux (the test suite passes there)", C.accent1]];
  const w = 2.1;
  rows.forEach(([big, unit, label, color], i) => {
    const x = 0.5 + i * (w + 0.2), y = 1.55;
    card(s, x, y, w, 2.5);
    text(s, big, { x: x + 0.2, y: y + 0.2, w: w - 0.4, h: 0.9, fontSize: 54, bold: true, color, valign: "middle" });
    text(s, unit, { x: x + 0.2, y: y + 1.1, w: w - 0.4, h: 0.3, fontSize: 12, color: C.text2 });
    text(s, label, { x: x + 0.2, y: y + 1.5, w: w - 0.4, h: 0.9, fontSize: 14 });
  });
  text(s, "A row of the conformance matrix closes only when every cell is proven on a real game.", { x: 0.5, y: 4.3, w: 9, h: 0.5, fontSize: 14, color: C.text2 });
}
{
  const s = slide("// 15 · NEXT", "What comes next", "", "DIVIDER");
  s.addText([
    { text: "Prove repack and game-load per engine on real installs", options: { bullet: true, breakLine: true, paraSpaceAfter: 6 } },
    { text: "Time the parallel pipeline end to end", options: { bullet: true, breakLine: true, paraSpaceAfter: 6 } },
    { text: "Unity MonoBehaviour fields; a first real game on Linux", options: { bullet: true } },
  ], { placeholder: "body" });
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  console.log("written", OUT);
})();
