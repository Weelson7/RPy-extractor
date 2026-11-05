// RECORD A WORKFLOW (doc 19.3), a panel of RUNBOOKS: the server records the actions of every
// view while the recording runs; a step you do in a child tool is added as a note. STOP AND SAVE
// writes it as your runbook, each action with what it answered, so a replay stops only there
// where an answer differs.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, toast, toastErr, emit, confirmBox } from "../ui.js";
import { currentGame } from "../game.js";

const el = {};
let saved = () => {};

/** The panel; `onSaved(id)` runs when a recording is saved as a runbook. */
export function recordingPanel(onSaved) {
  saved = onSaved;
  el.body = h("div", {});
  el.title = h("input", { class: "input mono grow", id: "rec-title", placeholder: "e.g. Lift the connection cap", spellcheck: "false" });
  el.noteTitle = h("input", { class: "input mono grow", id: "rec-note-title", placeholder: "What you did in the tool", spellcheck: "false" });
  el.noteText = h("textarea", { class: "input mono", id: "rec-note-text", rows: "3", placeholder: "How, so the next run can do it again" });
  return panel("", "RECORD A WORKFLOW", null, el.body);
}

export async function refreshRecording() {
  try { render((await api.recording()).recording); } catch (err) { fill(el.body, h("p", { class: "note warn-text" }, err.message)); }
}

function render(r) {
  if (!r) {
    return fill(el.body, h("p", { class: "dim" }, "Record what you do in ViWo, in any view (extract, analyse, patch, clean up), and the steps you do in a child tool as notes. Saved as a runbook: a replay goes on by itself while every answer is the one recorded, and stops where one differs."),
      h("label", { class: "lbl", for: "rec-title" }, "TITLE"), h("div", { class: "row" }, el.title, btn("START RECORDING", start, "primary")));
  }
  fill(el.body,
    h("div", { class: "job-h" }, badge(r.paused ? "PAUSED" : "● REC", r.paused ? "warn" : "live"), h("b", {}, r.title), h("span", { class: "mono dim small" }, r.game),
      r.running ? badge(`${r.running} ACTION(S) RUNNING`, "live") : null),
    (r.warnings || []).map((w) => h("p", { class: "note warn-text" }, w)),
    r.steps.length ? h("ol", { class: "list" }, r.steps.map((s) => h("li", {}, s.title, h("span", { class: "mono dim small" }, s.do ? `  ${s.do}` : "  (you)"))))
      : h("p", { class: "dim" }, "Nothing yet: run an action in any view; it appears here."),
    h("div", { class: "row" }, btn(r.paused ? "CONTINUE" : "PAUSE", () => act(r.paused ? "continue" : "pause"), ""),
      btn("STOP AND SAVE", () => act("stop"), "primary"), btn("DISCARD", discard, "ghost")),
    h("label", { class: "lbl", for: "rec-note-title" }, "ADD A STEP YOU DO (IN A CHILD TOOL)"), el.noteTitle,
    h("label", { class: "lbl", for: "rec-note-text" }, "HOW"), el.noteText,
    h("div", { class: "row" }, btn("ADD THE STEP", note, "")));
}

async function act(action, extra = {}) {
  try {
    const res = await api.recordingAct({ action, ...extra });
    render(res.recording);
    emit("recording");
    if (res.saved) { toast(`Saved as the runbook ${res.saved}.`, "ok", (res.warnings || []).join(" · ")); saved(res.saved); }
    return res;
  } catch (err) { toastErr(err); return null; }
}

function start() {
  const title = el.title.value.trim();
  if (!title) return toast("Give the workflow a title first.", "warn");
  if (!currentGame()) return toast("Pick the game first (the top bar's GAME): the workflow replays on a game.", "warn");
  return act("start", { title, game: currentGame() });
}

async function note() {
  if (await act("note", { title: el.noteTitle.value.trim(), text: el.noteText.value.trim() })) {
    el.noteTitle.value = "";
    el.noteText.value = "";
  }
}

async function discard() {
  if (await confirmBox("DISCARD THE RECORDING", "Every step recorded so far is dropped; nothing is saved.", { danger: true, ok: "DISCARD" })) act("discard");
}
