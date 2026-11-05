// RUNBOOKS (global): named, editable sequences of steps (doc 19.2). An action step runs as a
// job through the same handler as POST /api/jobs; a step you do pauses the run until DONE,
// CONTINUE (a workbook says how, in the child tool). A failed step stops the run where it is.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, viewHead, empty, errorBox, pref, toast, toastErr, bus, emit, goBtn, confirmBox, browseBtn } from "../ui.js";
import { registerView, code } from "../registry.js";
import { gameField, setGame } from "../game.js";
import { workbookBtn } from "./workbooks.js";

const S = { books: [], problems: [], sel: "", state: {}, result: {}, running: false, stop: false, resume: null, editing: false };
const el = {};
const STATE = { run: ["RUNNING", "live"], done: ["DONE", "ok"], fail: ["FAILED", "err"], wait: ["YOUR TURN", "warn"] };
const TEMPLATE = { id: "my-runbook", title: "My runbook", summary: "What it does.", inputs: [],
  steps: [{ title: "Survey the game", do: "survey", with: { folder: "{game}" } }, { title: "Look at the report", text: "Open SURVEY." }] };

function mount(root) {
  el.list = h("div", { class: "joblist", role: "list" });
  el.book = h("div", {});
  el.count = h("span", { class: "mono dim" });
  el.game = gameField("rb-game");
  el.new = btn("NEW", () => edit(TEMPLATE), "ghost");
  root.append(
    viewHead(code("runbooks"), "RUNBOOKS", "Named sequences of steps: ViWo's own actions run as jobs, and the steps you do in a child tool pause the run until you say they are done. Tweak a runbook and save your copy; yours go in viwo-data/runbooks/.", el.new),
    h("div", { class: "jobs-grid" },
      panel(`${code("runbooks")}.A`, "RUNBOOKS", el.count, el.list),
      panel(`${code("runbooks")}.B`, "RUNBOOK", null, el.book)));
  bus.addEventListener("wspath", () => S.sel && !S.editing && renderBook());
}

async function show() {
  if (S.running) return;
  try {
    const res = await api.runbooks();
    S.books = res.runbooks || [];
    S.problems = res.problems || [];
  } catch (err) { return fill(el.list, errorBox(err, "RUNBOOKS UNAVAILABLE")); }
  if (!current()) S.sel = S.books[0]?.id || "";
  renderList();
  if (!S.editing) renderBook();
}

const current = () => S.books.find((b) => b.id === S.sel);

function renderList() {
  el.count.textContent = `${S.books.length}`;
  el.new.disabled = S.running; // a run in progress keeps its runbook on screen until it ends
  fill(el.list, S.books.length ? S.books.map((b) => h("button", {
    type: "button", class: "job", role: "listitem", "aria-current": b.id === S.sel ? "true" : null, disabled: S.running,
    onclick: () => { S.sel = b.id; S.state = {}; S.result = {}; S.editing = false; renderList(); renderBook(); },
  }, h("span", { class: "kind" }, b.title), b.source === "yours" ? badge("YOURS", "ok") : h("span", {}),
    h("span", { class: "mono dim small" }, `${b.steps.length} steps · ${b.steps.filter((s) => !s.do).length} yours to do`)))
    : empty("NO RUNBOOK", "NEW writes one."),
  S.problems.map((p) => h("p", { class: "note warn-text" }, p))); // never silent: unusable files are named
}

/** The run's values: the game of the top bar and each input (remembered per runbook). */
function values(b) {
  const out = { game: el.game.value.trim() };
  b.inputs.forEach((i) => { out[i.name] = (pref(`rb.${b.id}.${i.name}`) ?? i.default) || ""; });
  return out;
}

function inputRow(b, i) {
  const id = `rb-in-${i.name}`;
  const field = h("input", { class: "input mono grow", id, value: pref(`rb.${b.id}.${i.name}`) ?? i.default, spellcheck: "false",
    oninput: (e) => pref(`rb.${b.id}.${i.name}`, e.target.value) });
  return [h("label", { class: "lbl", for: id }, i.label.toUpperCase()), h("div", { class: "row" }, field)];
}

function renderBook() {
  const b = current();
  if (!b) return fill(el.book, empty("NO RUNBOOK SELECTED", "Pick a runbook on the left, or write a NEW one."));
  fill(el.book,
    h("div", { class: "job-h" }, h("b", {}, b.title), b.source === "yours" ? badge("YOURS", "ok") : null,
      btn("EDIT", () => edit(b), "sm ghost", { disabled: S.running }),
      b.source === "yours" ? btn("DELETE MY COPY", () => remove(b), "sm ghost", { disabled: S.running }) : null),
    h("p", { class: "dim" }, b.summary),
    h("label", { class: "lbl", for: "rb-game" }, "GAME FOLDER (THE TOP BAR'S GAME)"),
    h("div", { class: "row" }, el.game, browseBtn(el.game, setGame)),
    b.inputs.map((i) => inputRow(b, i)),
    h("p", { class: "note" }, "Runs in the active workspace: ", h("code", { class: "mono" }, bus.ws?.path || "—"), "."),
    h("div", { class: "row" }, btn("RUN", () => run(0), "primary", { disabled: S.running }),
      S.running ? btn("STOP", stop, "danger") : null),
    h("ol", { class: "path-steps" }, b.steps.map((s, i) => stepRow(b, s, i))));
}

function stepRow(b, s, i) {
  const [label, kind] = STATE[S.state[i]] || ["", ""];
  const res = S.result[i];
  return h("li", { "data-state": S.state[i] === "done" ? "done" : "wait" },
    h("b", { class: "mono" }, String(i + 1)), h("b", {}, s.title),
    h("div", { class: "col" },
      s.do ? h("span", { class: "mono dim small" }, `${s.do} ${JSON.stringify(s.with)}`) : h("span", {}, s.text),
      s.workbook ? h("div", { class: "row" }, workbookBtn(s.workbook)) : null,
      jobLink(res instanceof Error ? res.payload?.jobId : res?.jobId),
      res instanceof Error ? errorBox(res, `STEP ${i + 1} FAILED`, `Fix it, then RUN FROM HERE.`) : answer(res)),
    h("div", { class: "row" }, label ? badge(label, kind) : badge(s.do ? s.do.toUpperCase() : "YOU", s.do ? "" : "mute"),
      S.state[i] === "wait" ? btn("DONE, CONTINUE", () => S.resume?.(true), "sm primary") : null,
      S.running ? null : btn("RUN FROM HERE", () => run(i), "sm ghost")));
}

const jobLink = (id) => (id ? h("div", { class: "row" }, h("span", { class: "mono dim small" }, `job ${id}`), goBtn("#jobs", "OPEN JOBS →", "sm ghost")) : null);

/** What an action answered (a plan, a report): what the next step you do reads. */
function answer(res) {
  if (!res) return null;
  const { success, jobId, step, ...rest } = res;
  const text = JSON.stringify(rest, null, 1);
  return h("details", {}, h("summary", { class: "mono small" }, "ANSWER"),
    h("pre", { class: "log mini" }, text.length > 6000 ? `${text.slice(0, 6000)}\n… (the whole answer is in JOBS)` : text));
}

/** A step you do: the run waits here until DONE, CONTINUE (true) or STOP (false). */
const yourTurn = () => new Promise((resolve) => { S.resume = resolve; });

async function run(from) {
  const b = current();
  if (!b) return;
  Object.assign(S, { running: true, stop: false, state: {}, result: {} });
  renderList();
  renderBook();
  for (let i = from; i < b.steps.length && !S.stop; i++) {
    S.state[i] = b.steps[i].do ? "run" : "wait";
    renderBook();
    if (!b.steps[i].do) {
      if (!(await yourTurn())) { delete S.state[i]; break; }
      S.state[i] = "done";
      continue;
    }
    try {
      S.result[i] = await api.runbookStep({ id: b.id, step: i, values: values(b) });
      S.state[i] = "done";
    } catch (err) {
      S.state[i] = "fail";
      S.result[i] = err;
      toastErr(err, `Step ${i + 1} failed: `);
      break;
    } finally { emit("jobs"); emit("workspace"); }
  }
  const finished = b.steps.every((_, i) => i < from || S.state[i] === "done");
  S.running = false;
  S.resume = null;
  if (finished) toast(`${b.title}: every step done.`, "ok");
  renderList();
  renderBook();
}

function stop() {
  S.stop = true;
  S.resume?.(false);
  toast("The run stops after the current step.", "warn");
}

/** EDIT / NEW: the runbook as JSON; SAVE validates it on the server and writes your copy. */
function edit(b) {
  if (S.running) return;
  S.editing = true;
  const raw = { id: b.id, title: b.title, summary: b.summary, inputs: b.inputs, steps: b.steps };
  const area = h("textarea", { class: "input mono", id: "rb-json", rows: "24", spellcheck: "false", value: JSON.stringify(raw, null, 1) });
  fill(el.book, h("div", { class: "job-h" }, h("b", {}, "EDIT"), h("span", { class: "dim" }, b.source === "viwo" ? "saved as your copy, which replaces the shipped one" : "")),
    h("label", { class: "lbl", for: "rb-json" }, "RUNBOOK (JSON, DOC 19.2)"), area,
    h("div", { class: "row" }, btn("SAVE", () => save(area.value), "primary"), btn("CANCEL", () => { S.editing = false; renderBook(); }, "ghost")));
}

async function save(text) {
  if (S.running) return toast("A runbook is running: save when it ends.", "warn");
  let raw;
  try { raw = JSON.parse(text); } catch (err) { return toast(`Not valid JSON: ${err.message}`, "warn"); }
  try {
    await api.saveRunbook(raw);
    toast(`Saved ${raw.id}.`, "ok");
    Object.assign(S, { editing: false, sel: raw.id, state: {}, result: {} });
    await show();
  } catch (err) { toastErr(err, "Not saved: "); }
}

async function remove(b) {
  if (!(await confirmBox("DELETE YOUR COPY", `Delete ${b.id} from viwo-data/runbooks/? A shipped runbook with this id comes back.`, { danger: true, ok: "DELETE" }))) return;
  try { await api.deleteRunbook(b.id); toast(`Deleted ${b.id}.`, "ok"); await show(); } catch (err) { toastErr(err); }
}

const VIEW = { mount, show };
registerView({ id: "runbooks", arm: "global", order: 27, title: "RUNBOOKS", subtitle: "step sequences, run and saved", ...VIEW });
export default VIEW;
