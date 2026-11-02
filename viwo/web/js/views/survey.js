// 07 SURVEY: read-only coverage check of one game or a whole library — what ViWo can pull, and what stays locked.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, viewHead, empty, errorBox, toast, toastErr, busy, pref, logLine, fmtBytes, fmtNum, emit, bus } from "../ui.js";
import { jobProgress } from "../progress.js";
import { stat } from "./extract-result.js";
import { gameCard, categoryKey, dataBytes, coveredBytes, pct, covKind } from "./survey-card.js";

const S = { games: null, deep: pref("surveyDeep") === "1", ranDeep: false, running: false };
const el = {};

function mount(root) {
  el.path = h("input", { class: "input mono grow", id: "survey-path", placeholder: "/path/to/game — or a folder of games",
    value: pref("surveyPath") || pref("gamePath") || "", spellcheck: "false", onkeydown: (e) => e.key === "Enter" && run(), oninput: bar });
  el.deep = h("button", { type: "button", class: "pick tgl", "aria-describedby": "survey-deep-note", onclick: () => setDeep(!S.deep) }, "DEEP");
  el.prog = jobProgress("survey", { logClass: "mini", onStatus: (text) => { if (S.running && text) el.sum.textContent = text; } });
  el.progPanel = panel("07.B", "SURVEY RUN", null, el.prog.el);
  el.progPanel.hidden = true;
  el.summary = h("div", { class: "sv-sum" });
  el.cards = h("div", { class: "sv-grid" });
  el.sum = h("div", { class: "ab-sum mono" });
  el.why = h("span", { class: "ab-why" });
  el.run = btn("SURVEY", () => run(), "primary lg");
  root.append(
    viewHead("07", "SURVEY", "What can ViWo pull? Survey one game or a folder of games: every file is sorted by what extraction would do with it. Read-only — nothing is copied or written."),
    panel("07.A", "GAME OR LIBRARY FOLDER", badge("READ-ONLY", "ok"),
      h("label", { class: "lbl", for: "survey-path" }, "FOLDER"),
      h("div", { class: "row" }, el.path, btn("BROWSE", (e) => busy(e.currentTarget, browse), "ghost")),
      h("div", { class: "row policy" }, h("span", { class: "lbl" }, "DEPTH"), el.deep,
        h("span", { class: "dim", id: "survey-deep-note" }, "also try the carver on unknown files — slower")),
      h("p", { class: "note" }, "A folder that looks like a game is surveyed as one game; otherwise each sub-folder is one game.")),
    el.progPanel, el.summary, el.cards,
    h("div", { class: "actionbar" }, el.sum, el.why, el.run));
  setDeep(S.deep);
  renderIdle();
}

function setDeep(on) {
  S.deep = on;
  pref("surveyDeep", on ? "1" : "0");
  el.deep.setAttribute("aria-pressed", String(on));
  bar();
}

async function browse() {
  try {
    el.path.value = (await api.browse(el.path.value.trim())).path;
    bar();
  } catch (err) {
    if (!err.payload?.cancelled) toast("Folder picker unavailable on this host — type the path instead.", "warn", err.message);
  }
}

function bar() {
  if (!el.run) return;
  const name = el.path.value.trim().split(/[\\/]/).filter(Boolean).pop();
  if (!S.running) el.sum.textContent = `${name || "no folder"} · ${S.deep ? "DEEP (carver on unknown files)" : "QUICK"} · read-only`;
  el.why.textContent = S.running ? "survey running…" : !name ? "pick a folder" : "";
  el.run.disabled = Boolean(el.why.textContent);
  el.run.textContent = S.running ? "SURVEYING…" : "SURVEY";
}

function renderIdle() {
  fill(el.cards, panel("07.C", "HOW TO READ A SURVEY", null,
    empty("NO SURVEY YET", "Pick a game or library folder and press SURVEY. Each game gets a card, worst coverage first."),
    h("h4", { class: "sub-h" }, "// CATEGORIES"), categoryKey(),
    h("p", { class: "note" }, "Coverage = asset + container + engine + carvable, as a share of data bytes (code and tiny files excluded).")));
}

async function run() {
  const folder = el.path.value.trim();
  if (!folder || S.running) return;
  pref("surveyPath", folder);
  S.running = true;
  bar();
  fill(el.summary);
  fill(el.cards);
  el.progPanel.hidden = false;
  await el.prog.start();
  el.prog.log.append(logLine(`// SURVEY ${S.deep ? "DEEP" : "QUICK"} :: ${folder}`));
  el.progPanel.scrollIntoView({ block: "nearest" });
  try {
    const res = await api.survey(folder, S.deep);
    await el.prog.finish("ok", `${fmtNum(res.games.length)} GAME(S) SURVEYED`);
    S.games = res.games;
    S.ranDeep = S.deep;
    render();
  } catch (err) {
    await el.prog.finish("fail", err.message);
    fill(el.cards, errorBox(err, "SURVEY FAILED"));
    toastErr(err, "Survey failed: ");
  } finally {
    S.running = false;
    bar();
    emit("jobs");
  }
}

function render() {
  const games = [...S.games].sort((a, b) => a.coverage - b.coverage);
  const data = games.reduce((s, g) => s + dataBytes(g), 0);
  const covered = games.reduce((s, g) => s + coveredBytes(g), 0);
  const full = games.filter((g) => g.coverage >= 0.999).length;
  const locked = games.filter((g) => g.coverage < 0.5).length;
  fill(el.summary, h("div", { class: "stats reveal" },
    stat("GAMES", fmtNum(games.length), S.ranDeep ? "deep survey" : "quick survey"),
    h("div", { class: `stat ${full === games.length ? "ok" : "warn"}` }, h("span", { class: "lbl" }, "FULLY COVERED"),
      h("b", { class: "mono" }, `${full}/${games.length}`), h("small", {}, "games at 100%")),
    stat("TOTAL DATA", fmtBytes(data), "code + tiny files excluded"),
    h("div", { class: `stat ${covKind(data ? covered / data : 1) === "ok" ? "ok" : ""}` }, h("span", { class: "lbl" }, "COVERED"),
      h("b", { class: "mono" }, pct(data ? covered / data : 1)), h("small", {}, `${fmtBytes(covered)} pullable`)),
    stat("UNDER 50%", fmtNum(locked), "games that need work")));
  const onExtract = (path) => {
    pref("gamePath", path);
    bus.gamePath = path;
    location.hash = "#extract";
  };
  const onDeep = () => { setDeep(true); run(); };
  fill(el.cards, games.length ? games.map((g, i) => gameCard(g, i, { deep: S.ranDeep, onExtract, onDeep }))
    : empty("NO GAMES FOUND", "The folder holds no sub-folders or files to survey."));
}

export default { mount };
