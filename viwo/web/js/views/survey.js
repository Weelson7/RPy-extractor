// 07 SURVEY: read-only coverage check of one game or a whole library — what ViWo can pull, and what stays locked.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, viewHead, empty, errorBox, toast, toastErr, pref, logLine, fmtBytes, fmtNum, emit, bus, stat, browseBtn } from "../ui.js";
import { setGame } from "../game.js";
import { jobProgress } from "../progress.js";
import { gameCard, categoryKey, dataBytes, coveredBytes, pct, covKind } from "./survey-card.js";

const S = { games: null, deep: pref("surveyDeep") === "1", ranDeep: false, running: false, reportId: "" };
const el = {};

function mount(root) {
  el.path = h("input", { class: "input mono grow", id: "survey-path", placeholder: "/path/to/game — or a folder of games",
    value: pref("surveyPath") || pref("gamePath") || "", spellcheck: "false", onkeydown: (e) => e.key === "Enter" && run(), oninput: bar });
  el.deep = h("button", { type: "button", class: "pick tgl", "aria-describedby": "survey-deep-note", onclick: () => setDeep(!S.deep) }, "DEEP");
  el.prog = jobProgress("survey", { logClass: "mini", onStatus: (text) => { if (S.running && text) el.sum.textContent = text; } });
  el.progPanel = panel("07.B", "SURVEY RUN", null, el.prog.el);
  el.progPanel.hidden = true;
  el.summary = h("div", { class: "sv-sum" });
  el.reports = h("div", {});
  el.cards = h("div", { class: "sv-grid" });
  el.sum = h("div", { class: "ab-sum mono" });
  el.why = h("span", { class: "ab-why" });
  el.run = btn("SURVEY", () => run(), "primary lg");
  el.cancel = btn("CANCEL", cancelJob, "ghost", { hidden: true });
  root.append(
    viewHead("07", "SURVEY", "What can ViWo pull? Survey one game or a folder of games: every file is sorted by what extraction would do with it. Read-only — nothing is copied or written."),
    panel("07.A", "GAME OR LIBRARY FOLDER", badge("READ-ONLY", "ok"),
      h("label", { class: "lbl", for: "survey-path" }, "FOLDER"),
      h("div", { class: "row" }, el.path, browseBtn(el.path, bar)),
      h("div", { class: "row policy" }, h("span", { class: "lbl" }, "DEPTH"), el.deep,
        h("span", { class: "dim", id: "survey-deep-note" }, "also try the carver on unknown files — slower")),
      h("p", { class: "note" }, "A folder that looks like a game is surveyed as one game; otherwise each sub-folder is one game.")),
    el.progPanel, el.summary, el.cards, panel("07.D", "SURVEY REPORTS", btn("REFRESH", () => listReports(), "sm ghost"), el.reports),
    h("div", { class: "actionbar" }, el.sum, el.why, el.cancel, el.run));
  setDeep(S.deep);
  renderIdle();
  listReports();
}

/** Stored reports (newest first): each survey is kept as a numbered file, never overwritten. */
async function listReports() {
  try {
    const list = (await api.surveys()).reports || [];
    fill(el.reports, list.length ? h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["WHEN", "FOLDER", "GAMES", "DEPTH", ""].map((c) => h("th", {}, c)))),
      h("tbody", {}, list.map((r) => h("tr", { "data-state": r.id === S.reportId ? "sel" : null }, h("td", { class: "mono small" }, r.when), h("td", { class: "mono small" }, r.folder),
        h("td", { class: "mono" }, fmtNum(r.gameCount)), h("td", {}, r.deep ? "DEEP" : "QUICK"), h("td", {}, btn("OPEN", () => openReport(r.id), "sm ghost"))))))
      : h("p", { class: "dim small" }, "No stored survey yet. Each survey run is saved as a report here."));
  } catch { fill(el.reports, h("p", { class: "dim small" }, "Stored reports are not available on this server.")); }
}

async function openReport(id) {
  try {
    const res = await api.surveyReport(id);
    S.games = res.report?.games || [];
    S.ranDeep = Boolean(res.report?.deep);
    S.reportId = id;
    render();
    listReports();
  } catch (err) { toastErr(err, "Report not opened: "); }
}

function setDeep(on) {
  S.deep = on;
  pref("surveyDeep", on ? "1" : "0");
  el.deep.setAttribute("aria-pressed", String(on));
  bar();
}

function bar() {
  if (!el.run) return;
  const name = el.path.value.trim().split(/[\\/]/).filter(Boolean).pop();
  if (!S.running) el.sum.textContent = `${name || "no folder"} · ${S.deep ? "DEEP (carver on unknown files)" : "QUICK"} · read-only`;
  el.why.textContent = S.running ? "survey running…" : !name ? "pick a folder" : "";
  el.run.disabled = Boolean(el.why.textContent);
  el.run.textContent = S.running ? "SURVEYING…" : "SURVEY";
  el.cancel.hidden = !S.running;
}

async function cancelJob() {
  const id = el.prog.id;
  if (!id) return toast("Job not registered yet — try again in a moment.", "warn");
  try { await api.cancel(id); toast("Cancellation requested.", "warn"); } catch (err) { toastErr(err); }
}

function renderIdle() {
  fill(el.cards, panel("07.C", "HOW TO READ A SURVEY", null,
    empty("NO SURVEY YET", "Pick a game or library folder above and press SURVEY (bottom right). Each game gets a card, worst coverage first."),
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
    await el.prog.finish("ok", `${fmtNum(res.games.length)} GAME(S) SURVEYED${res.reportId ? ` · REPORT ${res.reportId}` : ""}`);
    S.games = res.games;
    S.ranDeep = S.deep;
    S.reportId = res.reportId || "";
    render();
    listReports();
  } catch (err) {
    await el.prog.finish(err.code === "cancelled" ? "cancel" : "fail", err.message);
    fill(el.cards, errorBox(err, err.code === "cancelled" ? "SURVEY CANCELLED" : "SURVEY FAILED", err.code === "not_found" ? "Check the folder path: pick a game folder or a folder that holds several games." : ""));
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
  fill(el.summary, h("div", { class: "stats", "data-reveal": "1" },
    stat("GAMES", fmtNum(games.length), S.ranDeep ? "deep survey" : "quick survey"),
    stat("FULLY COVERED", `${full}/${games.length}`, "games at 100%", full === games.length ? "ok" : "warn"),
    stat("TOTAL DATA", fmtBytes(data), "code + tiny files excluded"),
    stat("COVERED", pct(data ? covered / data : 1), `${fmtBytes(covered)} pullable`, covKind(data ? covered / data : 1) === "ok" ? "ok" : ""),
    stat("UNDER 50%", fmtNum(locked), "games that need work"),
    S.reportId ? stat("REPORT", S.reportId, "stored in viwo-data/surveys") : null));
  const onExtract = (path) => {
    setGame(path);
    bus.gamePath = path;
    location.hash = "#extract";
  };
  const onDeep = () => { setDeep(true); run(); };
  fill(el.cards, games.length ? games.map((g, i) => gameCard(g, i, { deep: S.ranDeep, onExtract, onDeep }))
    : empty("NO GAMES FOUND", "This folder holds no sub-folders or files to survey. Pick the game's own folder, or the folder that holds your games."));
}

import { registerView } from "../registry.js";

const VIEW = { mount };
registerView({ id: "survey", arm: "static", order: 10, num: "07", title: "SURVEY", subtitle: "what can ViWo pull?", ...VIEW });
export default VIEW;
