// Semantic components. Every view is built from these; the look lives in css/base.css (structure)
// and css/themes/*.css (tokens). A component takes data and callbacks, never colours or sizes.
import { h, fill, cssVar } from "./dom.js";

export const btn = (label, onclick, kind = "", extra = {}) =>
  h("button", { class: `btn ${kind}`, type: "button", onclick, ...extra }, label);

export const goBtn = (hash, label, kind = "primary") => h("a", { class: `btn ${kind}`, href: hash }, label);

/** Panel with a "// idx" tag, title and optional header tools. */
export function panel(idx, title, tools, ...body) {
  return h("section", { class: "panel", "data-panel": idx },
    h("header", { class: "panel-h" }, h("span", { class: "idx" }, idx), h("h3", {}, title), h("div", { class: "tools" }, tools)),
    h("div", { class: "panel-b" }, body));
}

export function viewHead(idx, title, sub, ...tools) {
  return h("header", { class: "view-h" },
    h("div", {}, h("span", { class: "idx" }, `// ${idx}`), h("h2", {}, title), h("p", { class: "sub" }, sub)),
    h("div", { class: "row" }, tools));
}

export const badge = (text, kind = "") => h("span", { class: "badge", "data-kind": kind || null }, text);

export const stat = (label, value, sub = "", kind = "") =>
  h("div", { class: "stat", "data-kind": kind || null }, h("span", { class: "lbl" }, label), h("b", { class: "mono" }, value), sub ? h("small", {}, sub) : null);

/** 0..1 meter; `kind` is a semantic grade (ok | hi | mid | lo). */
export function meter(value, kind = "") {
  const pct = Math.max(0, Math.min(100, Math.round(Number(value || 0) * 100)));
  return h("div", { class: "meter", "data-kind": kind || null, role: "img", "aria-label": `${pct} percent` }, cssVar(h("i", {}), "p", `${pct}%`));
}

/** Proportional stacked bar: parts = [{key, weight, title}]. */
export function stackBar(parts, label = "") {
  return h("div", { class: "sbar", role: "img", "aria-label": label },
    parts.filter((p) => p.weight > 0).map((p) => cssVar(h("i", { "data-key": p.key, title: p.title || null }), "w", p.weight)));
}

/** Vertical bar series (waveform): values 0..1. */
export const bars = (values) => values.map((v) => cssVar(h("i", {}), "h", `${Math.max(3, Math.round(v * 100))}%`));

/** Determinate/indeterminate progress bar; setProgress(el, pct|null). */
export const progressBar = (extra = {}) => h("div", { class: "bar", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", ...extra }, h("i", {}));
export function setProgress(el, pct) {
  const det = pct !== null && pct !== undefined;
  el.dataset.state = det ? "det" : "scan";
  cssVar(el, "p", `${det ? Math.round(pct) : 0}%`);
  el.setAttribute("aria-valuenow", String(det ? Math.round(pct) : 0));
}

export function empty(title, text, ...actions) {
  return h("div", { class: "empty" }, h("b", {}, title), h("p", {}, text), actions.length ? h("div", { class: "row" }, actions) : null);
}

/** Alert block: kind = err | warn | info. */
/** A notice: the title, then each text part as its own paragraph (never run into the title). */
export const alert = (kind, title, ...body) => h("div", { class: "alert", "data-kind": kind, role: kind === "err" ? "alert" : null }, h("b", {}, title),
  body.map((part) => (typeof part === "string" ? h("p", {}, part) : part)));

/** Definition-style pair: LABEL value [extras]. */
export const kv = (label, value, ...extras) => h("div", { class: "kv" }, h("span", { class: "lbl" }, label), value, extras.length ? h("div", { class: "row" }, extras) : null);

/** Plain list (ol | ul) of nodes. */
export const list = (items, { ordered = false, kind = "" } = {}) => h(ordered ? "ol" : "ul", { class: "list", "data-kind": kind || null }, items.map((x) => h("li", {}, x)));

/** Segmented control: options = [[value, label]], value = current, pick(value). */
export function seg(options, value, pick, extra = {}) {
  const root = h("div", { class: "seg", role: "group", ...extra });
  const paint = (cur) => root.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.value === cur)));
  fill(root, options.map(([v, label]) => h("button", { type: "button", "data-value": v, onclick: () => { pick(v); paint(v); } }, label)));
  paint(value);
  root.set = paint;
  return root;
}

/** Labelled switch: [checkbox] TITLE / hint. */
export function toggle(id, title, hint, checked, onChange, locked = false) {
  return h("label", { class: "switch", "data-state": locked ? "locked" : null, for: id },
    h("input", { type: "checkbox", id, checked, disabled: locked, onchange: (e) => onChange(e.target.checked) }),
    h("span", { class: "sw" }), h("span", { class: "sw-text" }, h("b", {}, title), hint ? h("small", {}, hint) : null));
}

/** Form field: kind = text | int | secret | bool | choice; onInput(value). */
export function field(id, label, { kind = "text", value = "", choices = [], mono = true, placeholder = "", onInput, extra = null } = {}) {
  let input;
  if (kind === "bool") input = h("input", { type: "checkbox", id, checked: Boolean(value), onchange: (e) => onInput?.(e.target.checked) });
  else if (kind === "choice") input = h("select", { class: "input", id, onchange: (e) => onInput?.(e.target.value) }, choices.map((c) => h("option", { value: c, selected: c === value }, c)));
  else input = h("input", { class: `input grow ${mono ? "mono" : ""}`, id, value: String(value ?? ""), placeholder: placeholder || null, spellcheck: "false",
    type: kind === "secret" ? "password" : kind === "int" ? "number" : "text", autocomplete: kind === "secret" ? "off" : null,
    oninput: (e) => onInput?.(kind === "int" ? Number(e.target.value) : e.target.value) });
  const root = h("div", { class: "field", "data-kind": kind }, h("label", { class: "lbl", for: id }, label, extra), input);
  root.input = input;
  return root;
}

/** Table: columns = [{key, label, kind?: "num"}], rows = [{key -> node|string}], plus optional class. */
export function table(columns, rows, { kind = "", caption = "" } = {}) {
  return h("table", { class: "tbl", "data-kind": kind || null },
    caption ? h("caption", { class: "sr" }, caption) : null,
    h("thead", {}, h("tr", {}, columns.map((c) => h("th", { "data-kind": c.kind || null, scope: "col" }, c.label)))),
    h("tbody", {}, rows.map((r) => h("tr", { "data-state": r._state || null }, columns.map((c) => h("td", { "data-kind": c.kind || null }, r[c.key]))))));
}

/** Stage rail node list: stages = [{id, state: wait|on|done|skip|fail, label}]. */
export function rail(stages, extra = {}) {
  const text = { on: "in progress", done: "done", skip: "skipped", wait: "not reached", fail: "stopped here" };
  return h("ol", { class: "rail-stages", "aria-label": "Stages", ...extra }, stages.map((s, j) =>
    cssVar(h("li", { "data-s": s.state, title: `${s.label || s.id}: ${text[s.state]}`, "aria-current": s.state === "on" ? "step" : null },
      h("i", {}), h("span", {}, s.label || s.id), s.state === "skip" ? h("small", { class: "rail-note" }, "skipped") : h("span", { class: "sr" }, ` (${text[s.state]})`)), "i", j)));
}

/** Safety strip: [[headline, detail], ...] — what a tool will never do. */
export const assure = (points) => h("ul", { class: "assure" }, points.map(([b, t]) => h("li", {}, h("b", {}, b), h("span", {}, t))));

/** Pointer to SYSTEM wherever a feature depends on an optional tool. */
export const toolLink = (text = "Some of this needs an optional tool.") =>
  h("p", { class: "note" }, `${text} `, h("a", { href: "#system" }, "See SYSTEM for what to install →"));
