// RUNBOOKS: the structured step editor (doc 19.2). Edit a runbook without hand-writing JSON: its
// id/title/summary, its inputs, and its steps (add, remove, reorder; an action step's job and its
// target and options as typed key/value, a value that is a secret input masked; or a step you do
// with its text and a workbook). The JSON escape hatch stays, editable and kept in sync through
// one working copy. SAVE validates on the server (core/runbooks.py); a rule error shows inline and
// no step is dropped.
import { h, fill, btn, badge } from "../ui.js";

const TARGETS = ["gamePath", "folder", "path", "targetKey", "pid", "name"];
const NAME = /^\{([a-z][a-z0-9_]*)\}$/;
const asText = (v) => (typeof v === "string" ? v : JSON.stringify(v));
const secretNames = (W) => new Set((W.inputs || []).filter((i) => i.secret).map((i) => i.name));

/** A field's text back to a value: a bare true/false/null, a number or an object/array becomes
 * that; anything else (a `{name}`, a path, plain text) stays the string. */
function typed(t) {
  try {
    const v = JSON.parse(t);
    return typeof v === "string" ? t : v;
  } catch {
    return t;
  }
}

/** A loaded runbook as an editable working copy: each step tagged action|you, its options an
 * ordered [{k, v}] list (v as text) so keys can be typed and the rows reordered. */
function working(book) {
  const step = (s) =>
    s.do !== undefined
      ? { t: "action", title: s.title || "", do: s.do, expect: s.expect,
          opts: Object.entries(s.with || {}).map(([k, v]) => ({ k, v: asText(v) })) }
      : { t: "you", title: s.title || "", text: s.text || "", workbook: s.workbook || "" };
  const input = (i) => ({ name: i.name || "", label: i.label || "", default: i.default || "", secret: Boolean(i.secret) });
  return { id: book.id || "", title: book.title || "", summary: book.summary || "",
    inputs: (book.inputs || []).map(input), steps: (book.steps || []).map(step) };
}

/** The clean runbook JSON a working copy stands for (what SAVE sends, what the JSON view shows). */
function serialize(W) {
  const steps = W.steps.map((s) => {
    if (s.t !== "action") return s.workbook ? { title: s.title, text: s.text, workbook: s.workbook } : { title: s.title, text: s.text };
    const w = {};
    s.opts.forEach(({ k, v }) => { if (k.trim()) w[k.trim()] = typed(v); });
    const base = { title: s.title, do: s.do, with: w };
    return s.expect !== undefined ? { ...base, expect: s.expect } : base;
  });
  const inputs = W.inputs.map((i) => ({ name: i.name, label: i.label || i.name, default: i.secret ? "" : i.default, secret: i.secret }));
  return { id: W.id, title: W.title, summary: W.summary, inputs, steps };
}

const input = (cls, value, placeholder, set, extra = {}) =>
  h("input", { class: `input mono ${cls}`, value, placeholder: placeholder || null, spellcheck: "false", oninput: (e) => set(e.target.value), ...extra });

/** A labelled text field (or a 2-row textarea); typing mutates the working copy, no redraw. */
const textField = (lbl, value, set, { id, area = false } = {}) =>
  h("div", { class: "field" }, h("label", { class: "lbl", for: id }, lbl),
    area
      ? h("textarea", { class: "input mono", id, rows: "2", spellcheck: "false", value, oninput: (e) => set(e.target.value) })
      : input("grow", value, "", set, { id }));

/** One option: KEY and VALUE, the value masked when it is one secret input alone; TARGET marks a
 * key ViWo reads as what the step works on. */
function optRow(opt, secret, drop) {
  const hit = (opt.v.trim().match(NAME) || [])[1];
  const masked = Boolean(hit && secret.has(hit));
  return h("div", { class: "row rb-opt" },
    input("rb-opt-key", opt.k, "option", (x) => { opt.k = x; }),
    input("grow rb-opt-val", opt.v, "", (x) => { opt.v = x; }, { type: masked ? "password" : "text", autocomplete: masked ? "off" : null }),
    TARGETS.includes(opt.k.trim()) ? badge("TARGET", "mute") : null,
    btn("REMOVE", drop, "sm ghost"));
}

const kindSelect = (step, kinds, redraw) =>
  h("select", { class: "input rb-do", "aria-label": "job", onchange: (e) => { step.do = e.target.value; redraw(); } },
    kinds.map((k) => h("option", { value: k, selected: k === step.do }, k.toUpperCase())));

function setType(step, t, kinds, redraw) {
  if (step.t === t) return;
  step.t = t;
  if (t === "action") { step.do = step.do || kinds[0] || "survey"; step.opts = step.opts || []; }
  else { step.text = step.text || ""; step.workbook = step.workbook || ""; }
  redraw();
}

function stepAction(step, kinds, secret, redraw) {
  return [
    h("div", { class: "field" }, h("label", { class: "lbl" }, "JOB"), kindSelect(step, kinds, redraw)),
    h("label", { class: "lbl" }, "TARGET AND OPTIONS"),
    h("div", { class: "col rb-opts" }, step.opts.length
      ? step.opts.map((o, j) => optRow(o, secret, () => { step.opts.splice(j, 1); redraw(); }))
      : h("p", { class: "note dim" }, "No options. ADD OPTION writes one (a job needs its target).")),
    h("div", { class: "row" }, btn("ADD OPTION", () => { step.opts.push({ k: "", v: "" }); redraw(); }, "sm ghost")),
  ];
}

const stepYou = (step) => [
  textField("TEXT (WHAT YOU DO, THEN CONFIRM)", step.text, (v) => { step.text = v; }, { area: true }),
  textField("WORKBOOK ID (OPTIONAL: HOW, IN THE CHILD TOOL)", step.workbook, (v) => { step.workbook = v; }),
];

function stepCard(W, step, i, kinds, redraw) {
  const move = (to) => { if (to >= 0 && to < W.steps.length) { W.steps.splice(to, 0, W.steps.splice(i, 1)[0]); redraw(); } };
  const kindBtn = (t, label) => btn(label, () => setType(step, t, kinds, redraw), step.t === t ? "sm" : "sm ghost", { "aria-pressed": String(step.t === t) });
  return h("div", { class: "rb-step col", "data-t": step.t },
    h("div", { class: "row rb-step-h" }, h("b", { class: "mono" }, String(i + 1)),
      h("div", { class: "row rb-steptype" }, kindBtn("action", "ACTION"), kindBtn("you", "YOU DO")),
      btn("UP", () => move(i - 1), "sm ghost", { disabled: i === 0 }),
      btn("DOWN", () => move(i + 1), "sm ghost", { disabled: i === W.steps.length - 1 }),
      btn("DELETE STEP", () => { W.steps.splice(i, 1); redraw(); }, "sm ghost")),
    textField("TITLE", step.title, (v) => { step.title = v; }),
    step.t === "action" ? stepAction(step, kinds, secretNames(W), redraw) : stepYou(step));
}

function inputRow(W, inp, i, redraw) {
  return h("div", { class: "rb-input col" },
    h("div", { class: "row" },
      input("rb-in-name", inp.name, "name", (x) => { inp.name = x; }),
      input("grow rb-in-label", inp.label, "label", (x) => { inp.label = x; }),
      btn(inp.secret ? "SECRET" : "NOT SECRET", () => { inp.secret = !inp.secret; redraw(); }, inp.secret ? "sm" : "sm ghost", { "aria-pressed": String(inp.secret) }),
      btn("REMOVE", () => { W.inputs.splice(i, 1); redraw(); }, "sm ghost")),
    inp.secret
      ? h("p", { class: "note dim" }, "A secret input has no default and is never kept.")
      : input("grow rb-in-def", inp.default, "default (optional)", (x) => { inp.default = x; }));
}

function jsonBlock(W, redraw, err) {
  const area = h("textarea", { class: "input mono rb-json-src", rows: "14", spellcheck: "false", value: JSON.stringify(serialize(W), null, 1) });
  const apply = () => {
    let parsed;
    try { parsed = working(JSON.parse(area.value)); } catch (e) { err.textContent = `Not valid JSON: ${e.message}`; return; }
    Object.assign(W, parsed);
    redraw();
  };
  return h("details", { class: "rb-json", ontoggle: (e) => { if (e.target.open) area.value = JSON.stringify(serialize(W), null, 1); } },
    h("summary", { class: "mono small" }, "JSON (THE ESCAPE HATCH, DOC 19.2)"), area,
    h("div", { class: "row" }, btn("APPLY JSON", apply, "sm ghost")));
}

export function editor(book, kinds, { onSave, onCancel }) {
  const W = working(book);
  const host = h("div", { class: "rb-edit col" });
  const err = h("p", { class: "note warn-text rb-edit-err" });
  const redraw = () => { err.textContent = ""; fill(host, body()); };
  const save = async () => {
    err.textContent = "";
    try { await onSave(serialize(W)); } catch (e) { err.textContent = e.message || "Not saved."; }
  };
  const addStep = () => { W.steps.push({ t: "action", title: "New step", do: kinds[0] || "survey", opts: [] }); redraw(); };
  const addInput = () => { W.inputs.push({ name: "", label: "", default: "", secret: false }); redraw(); };
  const body = () => [
    h("div", { class: "job-h" }, h("b", {}, "EDIT"), book.source === "viwo" ? h("span", { class: "dim" }, "saved as your copy") : null),
    textField("ID (LOWERCASE, DIGITS, DASHES)", W.id, (v) => { W.id = v; }, { id: "rb-id" }),
    textField("TITLE", W.title, (v) => { W.title = v; }, { id: "rb-title" }),
    textField("SUMMARY", W.summary, (v) => { W.summary = v; }, { id: "rb-summary", area: true }),
    h("h4", { class: "lbl" }, "INPUTS"),
    h("div", { class: "col rb-inputs" }, W.inputs.length
      ? W.inputs.map((inp, i) => inputRow(W, inp, i, redraw))
      : h("p", { class: "note dim" }, "No inputs. A step reads {game}, {workspace} and any input.")),
    h("div", { class: "row" }, btn("ADD INPUT", addInput, "sm ghost")),
    h("h4", { class: "lbl" }, "STEPS"),
    h("div", { class: "col rb-steps" }, W.steps.map((s, i) => stepCard(W, s, i, kinds, redraw))),
    h("div", { class: "row" }, btn("ADD STEP", addStep, "sm ghost")),
    jsonBlock(W, redraw, err),
    h("div", { class: "row rb-edit-actions" }, btn("SAVE", save, "primary"), btn("CANCEL", onCancel, "ghost")),
  ];
  redraw();
  return h("div", { class: "col" }, host, err);
}
