// 03 SORT: keyboard-first triage of workspace assets with a large preview stage.
import { api } from "../api.js";
import { h, fill, btn, panel, meter, viewHead, empty, errorBox, toast, toastErr, promptBox, modal, fmtBytes, fmtNum, pad, bus, emit } from "../ui.js";
import { audioStage } from "./sort-audio.js";

const LIMIT = 100;
const TAG = { image: "IMG", audio: "AUD", video: "VID", text: "TXT", binary: "BIN" };
const KEYS = [["↑ ↓", "NAVIGATE"], ["→", "KEEP"], ["←", "TRASH"], ["CTRL+Z", "UNDO"], ["F2", "RENAME"], ["SPACE", "PLAY / PAUSE"]];
const S = { offset: 0, total: 0, items: [], idx: 0, seq: 0, kept: new Set(), trashed: 0, done: [], types: new Set(), loaded: false, busy: false };
const el = {};

function mount(root) {
  el.root = root;
  el.list = h("ol", { class: "alist", role: "listbox", "aria-label": "Assets", tabindex: "0" });
  el.pager = h("div", { class: "pager" });
  el.filters = h("div", { class: "chipset tfilter", role: "group", "aria-label": "Filter this page by type" });
  el.review = h("div", { class: "review" });
  el.meta = h("div", { class: "pmeta" });
  el.stage = h("div", { class: "stage" });
  el.acts = h("div", { class: "acts" },
    h("div", { class: "acts-main" }, btn("← TRASH", trash, "danger"), btn("KEEP →", keep, "primary")),
    h("div", { class: "acts-sub" }, btn("UNDO", undo, "ghost undo"), btn("RENAME", rename, "ghost"), btn("SAVE REMAINING…", saveRemaining, "ghost")));
  root.append(
    viewHead("03", "SORT", "Triage one asset at a time. KEEP marks it reviewed; TRASH moves it to the workspace trash (undo-able).",
      h("ul", { class: "legend", "aria-label": "Keyboard shortcuts" }, KEYS.map(([k, v]) => h("li", {}, h("kbd", {}, k), v)))),
    h("div", { class: "sort-grid" },
      panel("03.A", "QUEUE", el.pager, el.filters, el.list, el.review),
      panel("03.B", "PREVIEW", el.meta, el.stage, el.acts)));
  document.addEventListener("keydown", onKey);
  bus.addEventListener("workspace", () => { S.loaded = false; S.kept.clear(); S.trashed = 0; S.done = []; });
}

async function load(keepIdx = false, last = false) {
  try {
    const res = await api.assets(S.offset, LIMIT);
    S.items = res.assets || [];
    S.total = res.totalCount || 0;
    if (!S.items.length && S.offset > 0) { S.offset = Math.max(0, S.offset - LIMIT); return load(); }
    S.idx = last ? S.items.length - 1 : keepIdx ? Math.min(S.idx, Math.max(0, S.items.length - 1)) : 0;
    if (!shown().includes(S.idx)) S.idx = (last ? shown().pop() : shown()[0]) ?? 0;
    S.loaded = true;
    renderList();
    preview();
  } catch (err) {
    el.list.replaceChildren();
    el.stage.replaceChildren(errorBox(err, "ASSETS UNAVAILABLE"));
  }
}

function renderPager() {
  const from = S.items.length ? S.offset + 1 : 0;
  const to = S.offset + S.items.length;
  el.pager.replaceChildren(
    btn("‹", () => page(-1), "sm ghost", { disabled: S.offset === 0, "aria-label": "Previous page" }),
    h("span", { class: "mono" }, `${pad(from, 4)}–${pad(to, 4)} / ${fmtNum(S.total)}`),
    btn("›", () => page(1), "sm ghost", { disabled: to >= S.total, "aria-label": "Next page" }));
}

function page(dir, last = false) {
  S.offset = Math.max(0, S.offset + dir * LIMIT);
  load(false, last);
}

/** Indexes of the loaded items that pass the type filter. */
const shown = () => S.items.map((_, i) => i).filter((i) => !S.types.size || S.types.has(S.items[i].type));
const row = (i) => el.list.querySelector(`[data-i="${i}"]`);

function renderFilters() {
  const counts = {};
  S.items.forEach((a) => { counts[a.type] = (counts[a.type] || 0) + 1; });
  fill(el.filters, Object.keys(TAG).filter((t) => counts[t]).map((t) => h("button", { type: "button", class: "pick", "aria-pressed": String(S.types.has(t)),
    onclick: () => { S.types.has(t) ? S.types.delete(t) : S.types.add(t); renderList(); if (!shown().includes(S.idx)) select(shown()[0] ?? -1); } },
  TAG[t], h("small", {}, ` ${counts[t]}`))));
}

function renderReview() {
  const done = S.kept.size + S.trashed;
  const all = S.total + S.trashed;
  fill(el.review, h("span", { class: "lbl" }, "REVIEWED"), h("span", { class: "mono" }, `${fmtNum(done)} / ${fmtNum(all)}`),
    meter(all ? done / all : 0, "hi"), h("small", { class: "dim" }, "this session · ✓ = kept"));
}

function renderList() {
  renderPager();
  renderFilters();
  renderReview();
  fill(el.list, shown().map((i) => {
    const a = S.items[i];
    return h("li", { role: "option", "aria-selected": String(i === S.idx), class: S.kept.has(a.path) ? "kept" : "", "data-i": i, onclick: () => select(i) },
      h("span", { class: `tag t-${a.type}` }, TAG[a.type] || "BIN"), h("span", { class: "nm", title: a.name }, a.name),
      S.kept.has(a.path) ? h("span", { class: "ok-mark", title: "kept this session" }, "✓") : null, h("span", { class: "sz mono" }, fmtBytes(a.size)));
  }));
  row(S.idx)?.scrollIntoView({ block: "nearest" });
}

function select(i) {
  S.idx = i;
  el.list.querySelectorAll("li").forEach((li) => li.setAttribute("aria-selected", String(Number(li.dataset.i) === i)));
  row(i)?.scrollIntoView({ block: "nearest" });
  preview();
}

function move(dir) {
  const vis = shown();
  const pos = vis.indexOf(S.idx);
  const next = vis[pos < 0 ? (dir > 0 ? 0 : vis.length - 1) : pos + dir];
  if (next !== undefined) return select(next);
  if (dir > 0 && S.offset + S.items.length < S.total) return page(1);
  if (dir < 0 && S.offset > 0) return page(-1, true);
}

async function preview() {
  const a = shown().includes(S.idx) ? S.items[S.idx] : null;
  const seq = ++S.seq;
  el.acts.querySelectorAll("button:not(.undo)").forEach((b) => { b.disabled = !a; });
  if (!a) {
    el.meta.replaceChildren();
    el.stage.replaceChildren(S.items.length ? empty("NO MATCH", "No asset of the selected types on this page. Clear a type filter or page on.")
      : empty("QUEUE EMPTY", S.total ? "Nothing on this page." : "No assets in the workspace yet. Extract a game first.",
        h("a", { class: "btn primary", href: "#extract" }, "GO TO 01 EXTRACT")));
    return;
  }
  el.meta.replaceChildren(h("span", { class: "mono" }, `${pad(S.offset + S.idx + 1, 4)} / ${pad(S.total, 4)}`),
    h("span", { class: `tag t-${a.type}` }, TAG[a.type]), h("span", { class: "mono dim" }, fmtBytes(a.size)));
  try {
    const p = await api.preview(a.path);
    if (seq === S.seq) el.stage.replaceChildren(stageFor(p, a));
  } catch (err) {
    if (seq === S.seq) el.stage.replaceChildren(errorBox(err, "PREVIEW FAILED"));
  }
}

function stageFor(p, a) {
  const cap = h("div", { class: "cap" }, h("b", {}, p.name || a.name), h("code", { class: "mono dim" }, decodeURIComponent(a.path)));
  if (p.type === "image") return h("figure", { class: "media img" }, h("img", { src: p.url, alt: p.name }), cap);
  if (p.type === "audio") return audioStage(p.url, cap);
  if (p.type === "video") return h("figure", { class: "media vid" }, h("video", { src: p.url, controls: true, preload: "metadata" }), cap);
  if (p.type === "text") return h("figure", { class: "media txt" }, h("pre", { class: "mono" }, p.content || ""),
    h("div", { class: "cap" }, h("b", {}, p.name), h("span", { class: "dim mono" }, `${p.lineCount} LINES${p.truncated && p.lineCount >= 50 ? " · FIRST 50 SHOWN" : ""}`)));
  return h("figure", { class: "media bin" }, empty("NO PREVIEW", p.message || "Binary file — keep or trash it by name."), cap);
}

async function act(fn) {
  if (S.busy) return;
  S.busy = true;
  try { await fn(); } catch (err) { toastErr(err, err.code === "busy" ? "Workspace busy: " : ""); } finally { S.busy = false; }
}

const current = () => (shown().includes(S.idx) ? S.items[S.idx] : null);

function keep() {
  const a = current();
  if (!a) return;
  return act(async () => {
    await api.sort("keep", { path: a.path });
    S.kept.add(a.path);
    S.done.push({ kind: "keep", path: a.path });
    const last = shown().pop() === S.idx && S.offset + S.items.length >= S.total;
    renderList();
    if (last) toast("End of queue reached.", "ok");
    else move(1);
  });
}

function trash() {
  const a = current();
  if (!a) return;
  return act(async () => {
    await api.sort("trash", { path: a.path });
    S.items.splice(S.idx, 1);
    S.total -= 1;
    S.trashed += 1;
    S.done.push({ kind: "trash" });
    if (!S.items.length) return load(true);
    const vis = shown();
    S.idx = vis.find((i) => i >= S.idx) ?? vis[vis.length - 1] ?? 0;
    renderList();
    preview();
    emit("workspace");
  });
}

function undo() {
  return act(async () => {
    const res = await api.sort("undo", {});
    toast(`Undid ${String(res.undone || "action").toUpperCase()}.`, "ok");
    const prev = S.done.pop();
    if (prev?.kind === "keep") S.kept.delete(prev.path);
    if (prev?.kind === "trash") S.trashed -= 1;
    if (res.undone === "keep") return renderList();
    await load(true);
    const back = S.items.findIndex((x) => x.path === res.path);
    if (back >= 0) select(back);
    emit("workspace");
  });
}

async function rename() {
  const a = current();
  if (!a) return;
  const name = await promptBox("RENAME ASSET", "New file name (same folder):", a.name, "RENAME", "FILE NAME");
  if (!name || name === a.name) return;
  return act(async () => {
    const res = await api.sort("rename", { path: a.path, newName: name });
    await load(true);  // re-list so the type tag follows the new extension
    const at = S.items.findIndex((x) => x.path === res.newPath);
    if (at >= 0) select(at);
  });
}

async function saveRemaining() {
  if (!S.items.length) return toast("No remaining assets to save.", "warn");
  const res0 = await modal({ title: "SAVE REMAINING ASSETS", tag: "// MOVE OUT",
    body: h("p", {}, "Move remaining assets out of the workspace into an existing folder (sub-folders are kept). Trashed files stay in the trash."),
    input: { value: "", label: "DESTINATION FOLDER", placeholder: "/path/to/keep", browse: (p) => api.browse(p).then((r) => r.path) },
    actions: [{ label: "CANCEL", value: null, kind: "ghost" }, { label: `THIS PAGE (${S.items.length})`, value: "page" },
      { label: `ALL REMAINING (${fmtNum(S.total)})`, value: "all", kind: "primary", primary: true }] });
  const dest = res0.text.trim();
  if (!res0.value) return;
  if (!dest) return toast("Choose a destination folder.", "warn");
  return act(async () => {
    const res = res0.value === "all" ? await api.saveAll(dest) : await api.saveRemaining(S.items.map((x) => x.path), dest);
    toast(`Moved ${res.moved} file(s) to ${res.destinationPath}.`, "ok", res.skipped ? `${res.skipped} skipped` : "");
    await load();
    emit("workspace");
  });
}

function togglePlay() {
  const media = el.stage.querySelector("audio, video");
  if (media) media.paused ? media.play().catch(() => {}) : media.pause();
}

function onKey(e) {
  if (el.root.hidden || document.querySelector(".backdrop")) return;
  if (e.target.closest?.("input, textarea, select")) return;
  const ctrl = e.ctrlKey || e.metaKey;
  const map = {
    ArrowDown: () => move(1), ArrowUp: () => move(-1), ArrowRight: keep, ArrowLeft: trash, F2: rename, " ": togglePlay,
  };
  const fn = ctrl && e.key.toLowerCase() === "z" ? undo : !ctrl && !e.altKey ? map[e.key] : null;
  if (!fn) return;
  if (e.key === " " && (e.target.closest?.("audio, video") || !el.root.contains(e.target) && !["BODY", "MAIN"].includes(e.target.tagName))) return;
  e.preventDefault();
  fn();
}

export default { mount, show: () => { if (!S.loaded) load(true); } };
