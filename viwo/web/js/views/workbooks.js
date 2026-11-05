// WORKBOOKS (global): how to do one thing in a child tool's own interface, one step at a time
// (doc 19.1). ViWo opens the tool pre-loaded; the workbook says what to do in it. Teaching, never
// automation. The step reached is remembered per workbook.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, viewHead, empty, errorBox, pref, seg, goBtn, alert, kv } from "../ui.js";
import { registerView, code, tab } from "../registry.js";

const S = { books: [], problems: [], tool: "", sel: "" };
const el = {};
/** A workbook's `opens` slot family -> the view whose button opens the tool pre-loaded. */
const OPENS = { handoff: "analysis", attach: "runtime" };

/** The HOW TO button beside a tool (ANALYSIS, RUNTIME): this view, showing that tool's workbooks. */
export const howToBtn = (tool, label = "HOW TO") => btn(label, () => { pref("wbTool", tool); location.hash = "#workbooks"; },
  "sm ghost", { title: `Step-by-step workbooks for ${tool}` });
/** Open one workbook by id (a runbook step that says how). */
export const workbookBtn = (id) => btn("HOW, STEP BY STEP", () => { pref("wbOpen", id); location.hash = "#workbooks"; }, "sm ghost");

function mount(root) {
  el.tools = h("div", {});
  el.list = h("div", { class: "joblist", role: "list" });
  el.book = h("div", {});
  el.count = h("span", { class: "mono dim" });
  root.append(
    viewHead(code("workbooks"), "WORKBOOKS", "How to do one thing in a child tool's own interface, step by step: ViWo opens the tool pre-loaded, the workbook says what to do in it. Teaching, never automation. Your own workbooks go in viwo-data/workbooks/."),
    h("div", { class: "jobs-grid" },
      panel(`${code("workbooks")}.A`, "WORKBOOKS", el.count, el.tools, el.list),
      panel(`${code("workbooks")}.B`, "STEPS", null, el.book)));
}

async function show() {
  try {
    const res = await api.workbooks();
    S.books = res.workbooks || [];
    S.problems = res.problems || [];
  } catch (err) { return fill(el.list, errorBox(err, "WORKBOOKS UNAVAILABLE")); }
  S.tool = S.books.some((b) => b.tool === pref("wbTool")) ? pref("wbTool") : "";
  const want = S.books.find((b) => b.id === pref("wbOpen"));
  if (want) { pref("wbOpen", ""); S.sel = want.id; S.tool = want.tool; }
  renderList();
  const shown = S.books.filter((b) => !S.tool || b.tool === S.tool);
  renderBook(shown.find((b) => b.id === S.sel) || shown[0]);
}

function pickTool(tool) {
  S.tool = tool;
  pref("wbTool", tool);
  renderList();
}

function renderList() {
  const tools = [...new Set(S.books.map((b) => b.tool))];
  fill(el.tools, tools.length > 1 ? seg([["", "ALL"], ...tools.map((t) => [t, t.toUpperCase()])], S.tool, pickTool, { "aria-label": "Tool" }) : null);
  const shown = S.books.filter((b) => !S.tool || b.tool === S.tool);
  el.count.textContent = `${shown.length} OF ${S.books.length}`;
  fill(el.list, shown.length ? shown.map((b) => h("button", {
    type: "button", class: "job", role: "listitem", "data-id": b.id, "aria-current": b.id === S.sel ? "true" : null, onclick: () => renderBook(b),
  }, h("span", { class: "kind" }, b.title), badge(b.tool.toUpperCase(), b.stale ? "warn" : ""),
    h("span", { class: "mono dim small" }, `${b.steps.length} steps${b.source === "yours" ? " · yours" : ""}`)))
    : empty("NO WORKBOOK", "None is shipped or saved yet; a JSON file in viwo-data/workbooks/ adds one (doc 19.1)."),
  // never silent: a file that could not be used is named
  S.problems.map((p) => h("p", { class: "note warn-text" }, p)));
}

function renderBook(b) {
  if (!b) return fill(el.book, empty("NO WORKBOOK SELECTED", "Pick a workbook on the left."));
  S.sel = b.id;
  el.list.querySelectorAll(".job").forEach((n) => (n.dataset.id === b.id ? n.setAttribute("aria-current", "true") : n.removeAttribute("aria-current")));
  const at = Math.min(Number(pref(`wb.${b.id}`)) || 0, b.steps.length - 1);
  const go = (i) => { pref(`wb.${b.id}`, String(i)); renderBook(b); };
  const step = b.steps[at], last = at === b.steps.length - 1;
  const opener = OPENS[(b.opens || "").split(".")[0]];
  fill(el.book,
    h("div", { class: "job-h" }, h("b", {}, b.title), badge(b.tool.toUpperCase(), ""), b.source === "yours" ? badge("YOURS", "ok") : null,
      opener ? goBtn(`#${opener}`, `OPEN THE TOOL IN ${tab(opener)} →`, "sm ghost") : null),
    h("p", { class: "dim" }, b.summary),
    b.stale ? alert("warn", "WRITTEN FOR ANOTHER VERSION", `These steps were checked on ${b.tool} ${b.writtenFor}; the pinned ${b.tool} is ${b.pinned}. Menus and keys may differ.`) : null,
    h("h4", { class: "sub-h" }, `// STEP ${at + 1} OF ${b.steps.length}`),
    h("h3", {}, step.title),
    h("p", {}, step.text),
    step.keys.length ? h("p", {}, step.keys.map((k) => h("kbd", {}, k))) : null,
    step.expect ? kv("YOU SHOULD SEE", h("span", {}, step.expect)) : null,
    h("div", { class: "row" }, btn("← PREVIOUS", () => go(at - 1), "ghost", { disabled: at === 0 }),
      btn(last ? "DONE: START OVER" : "NEXT →", () => go(last ? 0 : at + 1), "primary")),
    h("h4", { class: "sub-h" }, "// ALL STEPS"),
    h("ol", { class: "list" }, b.steps.map((s, i) => h("li", {}, i === at ? h("b", {}, s.title)
      : h("a", { href: "#workbooks", onclick: (e) => { e.preventDefault(); go(i); } }, s.title)))));
}

const VIEW = { mount, show };
registerView({ id: "workbooks", arm: "global", order: 25, title: "WORKBOOKS", subtitle: "how-tos for the child tools", ...VIEW });
export default VIEW;
