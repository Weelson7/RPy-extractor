// SORT: keyboard-first triage of workspace assets with a large preview stage.
import { api } from "../api.js";
import { h, fill, btn, panel, meter, viewHead, empty, errorBox, toast, toastErr, promptBox, modal, fmtBytes, fmtNum, pad, bus, emit, goBtn, pref } from "../ui.js";
import { audioStage } from "./sort-audio.js";
import { skeleton, withSkeleton } from "../progress.js";

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
    viewHead(code("sort"), "SORT", "Go through your files one at a time. KEEP marks a file as reviewed; TRASH moves it to the workspace trash (CTRL+Z undoes it).",
      h("ul", { class: "legend", "aria-label": "Keyboard shortcuts" }, KEYS.map(([k, v]) => h("li", {}, h("kbd", {}, k), v)))),
    h("div", { class: "sort-grid" },
      panel(`${code("sort")}.A`, "QUEUE", el.pager, el.filters, el.list, el.review),
      panel(`${code("sort")}.B`, "PREVIEW", el.meta, el.stage, el.acts)));
  document.addEventListener("keydown", onKey);
  S.kept = restoreKept();
  bus.addEventListener("workspace", (e) => {
    if (e.detail?.from === "sort") return; // SORT's own trash/undo: the session goes on
    S.loaded = false; S.kept = restoreKept(); S.trashed = 0; S.done = [];
  });
}

/** KEEP marks persist per workspace (this browser), so a reopened SORT shows what was reviewed. */
const keptKey = () => `sortKept.${bus.ws?.path || ""}`;
function restoreKept() {
  try { return new Set(JSON.parse(pref(keptKey()) || "[]")); } catch { return new Set(); }
}
const saveKept = () => pref(keptKey(), JSON.stringify([...S.kept].slice(-20000)));

async function load(keepIdx = false, last = false) {
  try {
    const pull = () => api.assets(S.offset, LIMIT);
    const res = await (S.loaded ? pull() : withSkeleton(el.stage, "INDEXING WORKSPACE ASSETS…", pull, 5));
    S.items = res.assets || [];
    S.total = res.totalCount || res.total || 0;
    S.typeCounts = res.typeCounts || null;
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

/** Type filters: whole-workspace count (from the server) and the count on this page. */
function renderFilters() {
  const counts = {};
  S.items.forEach((a) => { counts[a.type] = (counts[a.type] || 0) + 1; });
  const all = S.typeCounts || counts;
  fill(el.filters, Object.keys(TAG).filter((t) => all[t] || counts[t]).map((t) => h("button", { type: "button", class: "pick", "aria-pressed": String(S.types.has(t)),
    title: `${fmtNum(all[t] || 0)} in the workspace, ${counts[t] || 0} on this page`,
    onclick: () => { S.types.has(t) ? S.types.delete(t) : S.types.add(t); renderList(); if (!shown().includes(S.idx)) select(shown()[0] ?? -1); } },
  TAG[t], h("small", {}, ` ${fmtNum(all[t] || 0)}`, S.typeCounts ? h("span", { class: "dim" }, ` · ${counts[t] || 0} on this page`) : null))));
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
    return h("li", { role: "option", id: `asset-${i}`, "aria-selected": String(i === S.idx), class: S.kept.has(a.path) ? "kept" : "", "data-i": i, onclick: () => select(i) },
      h("span", { class: "tag", "data-type": a.type }, TAG[a.type] || "BIN"), h("span", { class: "nm", title: a.name }, a.name),
      S.kept.has(a.path) ? h("span", { class: "ok-mark", title: "kept this session" }, "✓") : null, h("span", { class: "sz mono" }, fmtBytes(a.size)));
  }));
  el.list.setAttribute("aria-activedescendant", `asset-${S.idx}`);
  row(S.idx)?.scrollIntoView({ block: "nearest" });
}

function select(i) {
  S.idx = i;
  el.list.setAttribute("aria-activedescendant", `asset-${i}`);
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
    el.stage.replaceChildren(S.items.length ? empty("NO MATCH", "No file of the selected types on this page. Clear a type filter or go to the next page.")
      : S.total ? empty("NOTHING ON THIS PAGE", "Go back a page to keep sorting.")
        : empty(S.trashed ? "ALL SORTED" : "QUEUE EMPTY", S.trashed ? "Every file has been kept or trashed. Review the trash, or clean up duplicates next."
          : "No files in this workspace yet. Extract a game first.",
        S.trashed ? [goBtn("#workspace", `${code("workspace")} REVIEW TRASH →`), goBtn("#cleanup", `${code("cleanup")} CLEAN UP →`, "ghost")] : goBtn("#extract", "GO TO EXTRACT")));
    return;
  }
  el.meta.replaceChildren(h("span", { class: "mono" }, `${pad(S.offset + S.idx + 1, 4)} / ${pad(S.total, 4)}`),
    h("span", { class: "tag", "data-type": a.type }, TAG[a.type]), h("span", { class: "mono dim" }, fmtBytes(a.size)));
  const slow = setTimeout(() => { if (seq === S.seq) el.stage.replaceChildren(skeleton("LOADING PREVIEW…", 3)); }, 150);
  try {
    const p = await api.preview(a.path);
    if (seq === S.seq) el.stage.replaceChildren(stageFor(p, a));
  } catch (err) {
    if (seq === S.seq) el.stage.replaceChildren(errorBox(err, "PREVIEW FAILED"));
  } finally { clearTimeout(slow); }
}

function stageFor(p, a) {
  const cap = h("div", { class: "cap" }, h("b", {}, p.name || a.name), h("code", { class: "mono dim" }, decodeURIComponent(a.path)));
  if (p.type === "image") return h("figure", { class: "media img" }, h("img", { src: p.url, alt: p.name }), cap);
  if (p.type === "audio") return audioStage(p.url, cap);
  if (p.type === "video") return h("figure", { class: "media vid" }, h("video", { src: p.url, controls: true, preload: "metadata" }), cap);
  if (p.type === "text" && !binary(p.content)) return h("figure", { class: "media txt" }, h("pre", { class: "mono" }, p.content || ""),
    h("div", { class: "cap" }, h("b", {}, p.name), h("span", { class: "dim mono" }, `${p.lineCount} LINES${p.truncated && p.lineCount >= 50 ? " · FIRST 50 SHOWN" : ""}`)));
  return h("figure", { class: "media bin" }, empty("NO PREVIEW", "ViWo cannot show this kind of file. Keep or trash it by its name and size."), cap);
}

/** The server reads unknown types as text: treat mostly-unprintable content as binary. */
const binary = (t = "") => (t.match(/[\uFFFD\x00-\x08\x0E-\x1F]/g) || []).length > Math.max(4, t.length * 0.02);

async function act(fn) {
  if (S.busy) return;
  S.busy = true;
  try { await fn(); } catch (err) { toastErr(err); } finally { S.busy = false; }
}

const current = () => (shown().includes(S.idx) ? S.items[S.idx] : null);

function keep() {
  const a = current();
  if (!a) return;
  return act(async () => {
    await api.sort("keep", { path: a.path });
    S.kept.add(a.path);
    saveKept();
    S.done.push({ kind: "keep", path: a.path });
    const last = shown().pop() === S.idx && S.offset + S.items.length >= S.total;
    renderList();
    if (last) toast("That was the last file.", "ok", "Next: review the trash in WORKSPACE, or run CLEANUP.");
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
    emit("workspace", { from: "sort" });
  });
}

function undo() {
  return act(async () => {
    const res = await api.sort("undo", {});
    toast(`Undid ${String(res.undone || "action").toUpperCase()}.`, "ok");
    const prev = S.done.pop();
    if (prev?.kind === "keep") { S.kept.delete(prev.path); saveKept(); }
    if (prev?.kind === "trash") S.trashed -= 1;
    if (res.undone === "keep") return renderList();
    await load(true);
    const back = S.items.findIndex((x) => x.path === res.path);
    if (back >= 0) select(back);
    emit("workspace", { from: "sort" });
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
  if (!S.items.length) return toast("No remaining files to save.", "warn");
  const res0 = await modal({ title: "SAVE REMAINING FILES", tag: "// MOVE OUT",
    body: h("p", {}, "Move the files still in the queue out of the workspace into an existing folder (sub-folders are kept). Trashed files stay in the trash."),
    input: { value: "", label: "DESTINATION FOLDER", placeholder: "/path/to/keep", browse: true },
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
  // Space on a focused button or link activates it; on the player it toggles; elsewhere in the view it is play/pause
  if (e.key === " " && (e.target.closest?.("audio, video, button, a, [role=\"button\"]") || (!el.root.contains(e.target) && !["BODY", "MAIN"].includes(e.target.tagName)))) return;
  e.preventDefault();
  fn();
}

import { registerView, code } from "../registry.js";

const VIEW = { mount, show: () => load(S.loaded) };
registerView({ id: "sort", arm: "static", order: 40, title: "SORT", subtitle: "keep or trash, one by one", ...VIEW });
export default VIEW;
