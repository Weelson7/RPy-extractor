// 06 MERGER: pick candidates (numbered frame/clip groups), tune loops + conflict order, render MP4s.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, viewHead, empty, errorBox, busy, fmtNum, bus } from "../ui.js";
import { outputPanel, applyState } from "./merger-output.js";

const LIMIT = 300;
const PATTERNS = { "number-to-name": "01_NAME", "name-to-number": "NAME_01" };
const S = { st: null, pattern: "number-to-name", exts: new Set(), query: "", list: [], extList: [], total: 0, files: 0, offset: 0, sel: new Map() };
const el = {};

function mount(root) {
  el.root = root;
  el.banner = h("div", { class: "mbanner" });
  el.filters = h("div", { class: "mfilters" });
  el.list = h("div", { class: "clist" });
  el.count = h("span", { class: "mono dim" });
  el.timeline = h("div", { class: "tline" });
  el.selCount = h("span", { class: "mono dim" });
  root.append(
    viewHead("06", "MERGER", "Stitch numbered frames and clips from the active workspace into MP4 timelines — one video per candidate.",
      btn("REFRESH", (e) => busy(e.currentTarget, load), "ghost")),
    el.banner,
    h("div", { class: "merge-grid" },
      panel("06.A", "CANDIDATES", el.count, el.filters, el.list),
      h("div", { class: "col" }, panel("06.B", "TIMELINE", el.selCount, el.timeline),
        outputPanel({ specs, pattern: () => S.pattern, count: () => S.sel.size }))));
  bus.addEventListener("workspace", () => { S.sel.clear(); S.offset = 0; if (!root.hidden) load(); });
}

async function load() {
  try {
    S.st = await api.mergerState();
    applyState(S.st);
    fill(el.banner,
      S.st.encoder ? null : h("div", { class: "alert err", role: "alert" }, h("b", {}, "ENCODER MISSING // BUILD DISABLED"),
        h("p", {}, "ffmpeg (with ffprobe) was not found, so timelines cannot be rendered."),
        h("p", { class: "hint" }, "HINT: install ffmpeg (Linux: apt install ffmpeg · Windows: winget install ffmpeg) or set its path in startup.ini [tools], then restart ViWo.")),
      h("div", { class: "kv" }, h("span", { class: "lbl" }, "SOURCE"), h("code", { class: "mono path" }, S.st.workingDir)),
      h("div", { class: "kv" }, h("span", { class: "lbl" }, "OUTPUT"), h("code", { class: "mono path" }, S.st.mergerDir)));
    await list();
  } catch (err) {
    fill(el.list, errorBox(err, "MERGER UNAVAILABLE"));
  }
}

async function list() {
  const res = await api.mergerList({ namingPattern: S.pattern, allowedExts: S.exts.size ? [...S.exts] : null, offset: S.offset, limit: LIMIT });
  Object.assign(S, { list: res.candidates || [], extList: res.extensions || [], total: res.totalCount || 0, files: res.fileCount || 0 });
  for (const c of S.list) if (S.sel.has(c.name)) S.sel.get(c.name).cand = c;
  renderFilters();
  renderList();
  renderTimeline();
}

const reload = () => list().catch((err) => fill(el.list, errorBox(err, "LIST FAILED")));

function renderFilters() {
  const seg = h("div", { class: "seg sm", role: "group", "aria-label": "Naming pattern" }, Object.entries(PATTERNS).map(([k, label]) =>
    h("button", { type: "button", "aria-pressed": String(S.pattern === k),
      onclick: () => { S.pattern = k; S.sel.clear(); S.offset = 0; reload(); } }, label)));
  const exts = S.extList.map(({ ext, count }) => h("button", { type: "button", class: "pick", "aria-pressed": String(S.exts.has(ext)),
    onclick: () => { S.exts.has(ext) ? S.exts.delete(ext) : S.exts.add(ext); S.offset = 0; reload(); } }, ext, h("small", {}, ` ${fmtNum(count)}`)));
  const search = h("input", { class: "input mono grow", placeholder: "filter by name", value: S.query, "aria-label": "Filter candidates",
    oninput: (e) => { S.query = e.target.value.toLowerCase(); renderList(); } });
  fill(el.filters,
    h("div", { class: "row" }, h("span", { class: "lbl" }, "PATTERN"), seg),
    h("div", { class: "row" }, h("span", { class: "lbl" }, "TYPES"), exts.length ? exts : h("span", { class: "dim small" }, "no timeline media"),
      S.exts.size ? h("span", { class: "dim small" }, "(only ticked types)") : null),
    h("div", { class: "row" }, search, btn("ALL", () => pickAll(true), "sm ghost"), btn("NONE", () => pickAll(false), "sm ghost")));
}

const visible = () => S.list.filter((c) => c.name.toLowerCase().includes(S.query));
const span = (c) => (c.indexes.length ? `#${c.indexes[0]}–${c.indexes[c.indexes.length - 1]}` : "no index");

function renderList() {
  el.count.textContent = `${fmtNum(S.total)} GROUPS · ${fmtNum(S.files)} FILES`;
  const rows = visible();
  if (!rows.length) {
    fill(el.list, empty(S.files ? "NO MATCH" : "NOTHING TO MERGE", S.files ? "No candidate matches these filters."
      : "The active workspace has no images or videos. Extract a game or switch workspace.", S.files ? null : h("a", { class: "btn primary", href: "#extract" }, "GO TO 01 EXTRACT")));
    return;
  }
  fill(el.list, rows.map((c) => h("label", { class: `cand ${S.sel.has(c.name) ? "on" : ""}` },
    h("input", { type: "checkbox", checked: S.sel.has(c.name), onchange: (e) => toggle(c, e.target.checked) }),
    h("b", {}, c.name), h("span", { class: "mono dim" }, span(c)),
    c.conflicts.length ? badge(`${c.conflicts.length} CONFLICT`, "warn") : null, badge(`${c.count}`, "mute"))),
  S.total > LIMIT ? h("div", { class: "row pager" },
    btn("‹ PREV", () => { S.offset -= LIMIT; reload(); }, "sm ghost", { disabled: S.offset === 0 }),
    h("span", { class: "mono" }, `${S.offset + 1}–${Math.min(S.total, S.offset + LIMIT)} / ${S.total}`),
    btn("NEXT ›", () => { S.offset += LIMIT; reload(); }, "sm ghost", { disabled: S.offset + LIMIT >= S.total })) : null);
}

function toggle(c, on) {
  if (!on) S.sel.delete(c.name);
  else S.sel.set(c.name, { cand: c, spec: { name: c.name, entiretyTimes: 1, partLoops: [],
    conflictResolutions: Object.fromEntries(c.conflicts.map((k) => [k.index, k.options.map((o) => o.path)])) } });
  renderList();
  renderTimeline();
}

function pickAll(on) {
  visible().forEach((c) => { if (on !== S.sel.has(c.name)) toggle(c, on); });
}

function specs() {
  return [...S.sel.values()].map(({ spec }) => ({ ...spec, partLoops: spec.partLoops.filter((l) => l.indexes.trim()) }));
}

const num = (label, value, set, min = 1) => h("label", { class: "nfield" }, h("span", { class: "lbl" }, label),
  h("input", { class: "input mono", type: "number", min, step: 1, value: String(value), oninput: (e) => set(Math.max(min, parseInt(e.target.value, 10) || min)) }));

function renderTimeline() {
  el.selCount.textContent = `${S.sel.size} SELECTED`;
  if (!S.sel.size) return fill(el.timeline, empty("NO CANDIDATE SELECTED", "Tick candidates on the left. Each one becomes its own MP4."));
  fill(el.timeline, [...S.sel.values()].map(card));
}

function card({ cand, spec }) {
  const loops = h("div", { class: "loops" });
  const drawLoops = () => fill(loops, spec.partLoops.map((l, i) => h("div", { class: "row loop" },
    h("input", { class: "input mono grow", value: l.indexes, placeholder: "indexes, e.g. 02, 03", "aria-label": "Indexes to loop", oninput: (e) => { l.indexes = e.target.value; } }),
    num("×", l.times, (v) => { l.times = v; }),
    btn("✕", () => { spec.partLoops.splice(i, 1); drawLoops(); }, "sm ghost", { "aria-label": "Remove loop" }))),
  btn("+ PART LOOP", () => { spec.partLoops.push({ indexes: "", times: 2 }); drawLoops(); loops.querySelector(".loop:last-of-type input")?.focus(); }, "sm ghost"));
  drawLoops();
  return h("article", { class: "tcard" },
    h("header", {}, h("b", {}, cand.name), h("span", { class: "mono dim" }, `${cand.count} FILES · ${span(cand)}`),
      btn("✕", () => toggle(cand, false), "sm ghost", { "aria-label": `Remove ${cand.name}` })),
    h("div", { class: "row" }, num("PLAY WHOLE TIMELINE ×", spec.entiretyTimes, (v) => { spec.entiretyTimes = v; })),
    h("span", { class: "lbl" }, "PART LOOPS"), loops,
    cand.conflicts.length ? [h("span", { class: "lbl" }, "SAME-INDEX CONFLICTS · PLAY ORDER"), cand.conflicts.map((k) => conflictList(spec, k.index))] : null);
}

function conflictList(spec, index, focusAt = -1) {
  const order = spec.conflictResolutions[index];
  const move = (i, d) => {
    [order[i], order[i + d]] = [order[i + d], order[i]];
    const next = conflictList(spec, index, i + d);
    ol.replaceWith(next);
  };
  const ol = h("ol", { class: "conflict", "aria-label": `Index ${index} order` }, h("li", { class: "ci mono" }, `#${index}`),
    order.map((p, i) => h("li", {}, h("code", { class: "mono" }, p),
      btn("↑", () => move(i, -1), "sm ghost", { disabled: i === 0, "aria-label": `Move ${p} earlier`, "data-at": `${i}u` }),
      btn("↓", () => move(i, 1), "sm ghost", { disabled: i === order.length - 1, "aria-label": `Move ${p} later`, "data-at": `${i}d` }))));
  if (focusAt >= 0) requestAnimationFrame(() => (ol.querySelector(`[data-at="${focusAt}u"]:not(:disabled)`) || ol.querySelector(`[data-at="${focusAt}d"]`))?.focus());
  return ol;
}

export default { mount, show: () => { if (!S.st) load(); } };
