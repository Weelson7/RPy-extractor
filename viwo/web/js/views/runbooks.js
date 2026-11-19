// RUNBOOKS (global): named, editable sequences of steps (doc 19.2). An action step runs as a
// job through the same handler as POST /api/jobs; a step you do pauses the run until DONE,
// CONTINUE (a workbook says how, in the child tool). A failed step stops the run where it is.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, listItem, viewHead, empty, errorBox, pref, toast, toastErr, bus, emit, goBtn, confirmBox, browseBtn } from "../ui.js";
import { registerView, code } from "../registry.js";
import { gameField, setGame } from "../game.js";
import { workbookBtn } from "./workbooks.js";
import { recordingPanel, refreshRecording } from "./recording.js";
import { stepDetail } from "./runbook-step.js";
import { editor } from "./runbook-edit.js";

const S = { books: [], problems: [], sel: "", state: {}, result: {}, running: false, stop: false, resume: null, editing: false, kinds: [] };
const el = {};
const STATE = { run: ["RUNNING", "live"], done: ["DONE", "ok"], fail: ["FAILED", "err"], wait: ["YOUR TURN", "warn"], differs: ["DIFFERS: YOUR CALL", "warn"] };
const secrets = {}; // secret input values: this page only, never kept (doc 19.3)
const TEMPLATE = { id: "my-runbook", title: "My runbook", summary: "What it does.", inputs: [],
  steps: [{ title: "Survey the game", do: "survey", with: { folder: "{game}" } }, { title: "Look at the report", text: "Open SURVEY." }] };

function mount(root) {
  el.list = h("div", { class: "joblist", role: "list" });
  el.book = h("div", {});
  el.count = h("span", { class: "mono dim" });
  el.game = gameField("rb-game");
  el.new = btn("NEW", () => edit(TEMPLATE), "ghost");
  root.append(
    viewHead(code("runbooks"), "RUNBOOKS", "Named sequences of steps: ViWo's own actions run as jobs, and the steps you do in a child tool pause the run until you say they are done. Tweak a runbook and save your copy; yours go in viwo-data/runbooks/. A recorded workflow is a runbook too.", el.new),
    recordingPanel((id) => { if (!S.running) { S.sel = id; S.editing = false; show(); } }),
    h("div", { class: "jobs-grid" },
      panel(`${code("runbooks")}.A`, "RUNBOOKS", el.count, el.list),
      panel(`${code("runbooks")}.B`, "RUNBOOK", null, el.book)));
  bus.addEventListener("wspath", () => S.sel && !S.editing && renderBook());
  const again = () => current() && !S.editing && el.steps && fillSteps(current());
  el.game.addEventListener("input", again);
  bus.addEventListener("game", again);
}

async function show() {
  refreshRecording();
  if (S.running) return;
  try {
    const res = await api.runbooks();
    S.books = res.runbooks || [];
    S.problems = res.problems || [];
    S.kinds = res.kinds || [];
  } catch (err) { return fill(el.list, errorBox(err, "RUNBOOKS UNAVAILABLE")); }
  if (!current()) S.sel = S.books[0]?.id || "";
  renderList();
  if (!S.editing) renderBook();
}

const current = () => S.books.find((b) => b.id === S.sel);

function renderList() {
  el.count.textContent = `${S.books.length}`;
  el.new.disabled = S.running; // a run in progress keeps its runbook on screen until it ends
  fill(el.list, S.books.length ? S.books.map((b) => listItem(b.id === S.sel, () => { S.sel = b.id; S.state = {}; S.result = {}; S.editing = false; renderList(); renderBook(); },
    { disabled: S.running }, h("span", { class: "kind" }, b.title), b.source === "yours" ? badge("YOURS", "ok") : h("span", {}),
    h("span", { class: "mono dim small" }, `${b.steps.length} steps · ${b.steps.filter((s) => !s.do).length} yours to do`)))
    : empty("NO RUNBOOK", "NEW writes one."),
  S.problems.map((p) => h("p", { class: "note warn-text" }, p))); // never silent: unusable files are named
}

/** The run's values: the game of the top bar and each input (remembered per runbook). */
function values(b) {
  const out = { game: el.game.value.trim() };
  b.inputs.forEach((i) => { out[i.name] = (i.secret ? secrets[`${b.id}.${i.name}`] : pref(`rb.${b.id}.${i.name}`) ?? i.default) || ""; });
  return out;
}

function inputRow(b, i) {
  const id = `rb-in-${i.name}`, key = `${b.id}.${i.name}`;
  const field = i.secret
    ? h("input", { class: "input mono grow", id, type: "password", autocomplete: "off", value: secrets[key] || "", oninput: (e) => { secrets[key] = e.target.value; } })
    : h("input", { class: "input mono grow", id, value: pref(`rb.${key}`) ?? i.default, spellcheck: "false", oninput: (e) => { pref(`rb.${key}`, e.target.value); fillSteps(b); } });
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
    (el.steps = h("ol", { class: "path-steps" })));
  fillSteps(b);
}

/** The step rows alone: an input typed in shows at once in the steps that use it. */
const fillSteps = (b) => fill(el.steps, b.steps.map((s, i) => stepRow(b, s, i)));

function stepRow(b, s, i) {
  const [label, kind] = STATE[S.state[i]] || ["", ""];
  const res = S.result[i];
  return h("li", { "data-state": S.state[i] === "done" ? "done" : "wait" },
    h("b", { class: "mono" }, String(i + 1)), h("b", {}, s.title),
    h("div", { class: "col" },
      stepDetail(s, { ...values(b), workspace: bus.ws?.path || "" }, new Set(b.inputs.filter((x) => x.secret).map((x) => x.name))),
      s.workbook ? h("div", { class: "row" }, workbookBtn(s.workbook)) : null,
      jobLink(res instanceof Error ? res.payload?.jobId : res?.jobId),
      res?.differs?.length ? h("ul", { class: "list" }, res.differs.map((d) => h("li", { class: "mono small warn-text" }, `differs from the recording: ${d}`))) : null,
      s.expect && !res ? h("span", { class: "mono dim small" }, "recorded: a replay stops here only if the answer differs") : null,
      res instanceof Error ? errorBox(res, `STEP ${i + 1} FAILED`, `Fix it, then RUN FROM HERE.`) : answer(res)),
    h("div", { class: "row" }, label ? badge(label, kind) : badge(s.do ? s.do.toUpperCase() : "YOU", s.do ? "" : "mute"),
      S.state[i] === "wait" ? btn("DONE, CONTINUE", () => S.resume?.(true), "sm primary") : null,
      S.state[i] === "differs" && S.running ? btn("CONTINUE ANYWAY", () => S.resume?.(true), "sm primary") : null,
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
  const carry = {}; // what earlier steps of this run answered: a later step names it (doc 19.3)
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
      S.result[i] = await api.runbookStep({ id: b.id, step: i, values: { ...carry, ...values(b) } });
      Object.entries(S.result[i]).forEach(([k, v]) => {
        if (/^[A-Za-z][A-Za-z0-9_]*$/.test(k) && (typeof v === "string" || Number.isInteger(v))) carry[`step${i + 1}_${k.toLowerCase()}`] = String(v);
      });
      S.state[i] = S.result[i].differs?.length ? "differs" : "done";
      if (S.state[i] === "differs") { // a workflow step answered otherwise than recorded: your call
        renderBook();
        if (S.stop || !(await yourTurn())) break;
        S.state[i] = "done";
      }
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

/** EDIT / NEW: the structured step editor (runbook-edit.js), with a JSON escape hatch. SAVE
 * validates on the server (core/runbooks.py) and writes your copy; a rule error shows inline. */
function edit(b) {
  if (S.running) return;
  S.editing = true;
  fill(el.book, editor(b, S.kinds, { onSave: save, onCancel: () => { S.editing = false; renderBook(); } }));
}

/** SAVE from the editor: the already-built runbook object (the editor surfaces a rejection
 * inline, so this rethrows instead of toasting a dropped step away). */
async function save(raw) {
  if (S.running) throw new Error("A runbook is running: save when it ends.");
  await api.saveRunbook(raw);
  toast(`Saved ${raw.id}.`, "ok");
  Object.assign(S, { editing: false, sel: raw.id, state: {}, result: {} });
  await show();
}

async function remove(b) {
  if (!(await confirmBox("DELETE YOUR COPY", `Delete ${b.id} from viwo-data/runbooks/? A shipped runbook with this id comes back.`, { danger: true, ok: "DELETE" }))) return;
  try { await api.deleteRunbook(b.id); toast(`Deleted ${b.id}.`, "ok"); await show(); } catch (err) { toastErr(err); }
}

registerView({ id: "runbooks", arm: "global", order: 27, title: "RUNBOOKS", subtitle: "step sequences, run and saved", mount, show });
