// 03 SORT: keyboard-first triage of workspace assets with a large preview stage.
import { api } from "../api.js";
import { h, btn, panel, viewHead, empty, errorBox, toast, toastErr, promptBox, fmtBytes, fmtNum, pad, bus, emit } from "../ui.js";

const LIMIT = 100;
const TAG = { image: "IMG", audio: "AUD", video: "VID", text: "TXT", binary: "BIN" };
const KEYS = [["↑ ↓", "NAVIGATE"], ["→", "KEEP"], ["←", "TRASH"], ["CTRL+Z", "UNDO"], ["F2", "RENAME"], ["SPACE", "PLAY / PAUSE"]];
const S = { offset: 0, total: 0, items: [], idx: 0, seq: 0, kept: new Set(), loaded: false, busy: false };
const el = {};

function mount(root) {
  el.root = root;
  el.list = h("ol", { class: "alist", role: "listbox", "aria-label": "Assets", tabindex: "0" });
  el.pager = h("div", { class: "pager" });
  el.meta = h("div", { class: "pmeta" });
  el.stage = h("div", { class: "stage" });
  el.acts = h("div", { class: "acts" },
    btn("← TRASH", trash, "danger"), btn("KEEP →", keep, "primary"), btn("UNDO", undo, "ghost"),
    btn("RENAME", rename, "ghost"), btn("SAVE REMAINING…", saveRemaining, "ghost"));
  root.append(
    viewHead("03", "SORT", "Triage assets one by one. Keep marks a file as reviewed; trash moves it to the workspace trash (undo-able).",
      h("ul", { class: "legend", "aria-label": "Keyboard shortcuts" }, KEYS.map(([k, v]) => h("li", {}, h("kbd", {}, k), v)))),
    h("div", { class: "sort-grid" },
      panel("03.A", "ASSET QUEUE", el.pager, el.list),
      panel("03.B", "PREVIEW", el.meta, el.stage, el.acts)));
  document.addEventListener("keydown", onKey);
  bus.addEventListener("workspace", () => { S.loaded = false; });
}

async function load(keepIdx = false) {
  try {
    const res = await api.assets(S.offset, LIMIT);
    S.items = res.assets || [];
    S.total = res.totalCount || 0;
    if (!S.items.length && S.offset > 0) { S.offset = Math.max(0, S.offset - LIMIT); return load(); }
    S.idx = keepIdx ? Math.min(S.idx, Math.max(0, S.items.length - 1)) : 0;
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

function page(dir) {
  S.offset = Math.max(0, S.offset + dir * LIMIT);
  load();
}

function renderList() {
  renderPager();
  el.list.replaceChildren(...S.items.map((a, i) => h("li", {
    role: "option", "aria-selected": String(i === S.idx), class: `${S.kept.has(a.path) ? "kept" : ""}`,
    onclick: () => select(i),
  }, h("span", { class: `tag t-${a.type}` }, TAG[a.type] || "BIN"), h("span", { class: "nm", title: a.name }, a.name),
    S.kept.has(a.path) ? h("span", { class: "ok-mark" }, "✓") : null, h("span", { class: "sz mono" }, fmtBytes(a.size)))));
  el.list.children[S.idx]?.scrollIntoView({ block: "nearest" });
}

function select(i) {
  if (i < 0 || i >= S.items.length) return;
  S.idx = i;
  [...el.list.children].forEach((li, n) => li.setAttribute("aria-selected", String(n === i)));
  el.list.children[i]?.scrollIntoView({ block: "nearest" });
  preview();
}

function move(dir) {
  const next = S.idx + dir;
  if (next >= S.items.length && S.offset + S.items.length < S.total) return page(1);
  if (next < 0 && S.offset > 0) return page(-1);
  select(next);
}

async function preview() {
  const a = S.items[S.idx];
  const seq = ++S.seq;
  if (!a) {
    el.meta.replaceChildren();
    el.stage.replaceChildren(empty("QUEUE EMPTY", S.total ? "Nothing on this page." : "No assets in the workspace. Extract a game first.",
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
  if (p.type === "audio") return h("figure", { class: "media aud" }, h("div", { class: "wave", "aria-hidden": "true" }, Array.from({ length: 48 }, (_, i) => h("i", { style: `height:${20 + ((i * 37) % 70)}%` }))), h("audio", { src: p.url, controls: true, preload: "metadata" }), cap);
  if (p.type === "video") return h("figure", { class: "media vid" }, h("video", { src: p.url, controls: true, preload: "metadata" }), cap);
  if (p.type === "text") return h("figure", { class: "media txt" }, h("pre", { class: "mono" }, p.content || ""),
    h("div", { class: "cap" }, h("b", {}, p.name), h("span", { class: "dim mono" }, `${p.lineCount} LINES${p.truncated ? " · TRUNCATED" : ""}`)));
  return h("figure", { class: "media bin" }, empty("NO PREVIEW", p.message || "Binary file — keep or trash it by name."), cap);
}

async function act(fn) {
  if (S.busy) return;
  S.busy = true;
  try { await fn(); } catch (err) { toastErr(err, err.code === "busy" ? "Workspace busy: " : ""); } finally { S.busy = false; }
}

const current = () => S.items[S.idx];

function keep() {
  const a = current();
  if (!a) return;
  return act(async () => {
    await api.sort("keep", { path: a.path });
    S.kept.add(a.path);
    el.list.children[S.idx]?.classList.add("kept");
    if (S.idx < S.items.length - 1 || S.offset + S.items.length < S.total) move(1);
    else { renderList(); toast("End of queue reached.", "ok"); }
  });
}

function trash() {
  const a = current();
  if (!a) return;
  return act(async () => {
    await api.sort("trash", { path: a.path });
    S.items.splice(S.idx, 1);
    S.total -= 1;
    if (!S.items.length) return load(true);
    S.idx = Math.min(S.idx, S.items.length - 1);
    renderList();
    preview();
    emit("workspace");
  });
}

function undo() {
  return act(async () => {
    const res = await api.sort("undo", {});
    toast(`Undid ${String(res.undone || "action").toUpperCase()}.`, "ok");
    if (res.undone === "keep") return;
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
    Object.assign(a, { path: res.newPath, name: res.name });
    renderList();
    preview();
  });
}

async function saveRemaining() {
  if (!S.items.length) return toast("No remaining assets on this page.", "warn");
  const dest = await promptBox("SAVE REMAINING ASSETS",
    `Move the ${S.items.length} asset(s) listed on this page out of the workspace into an existing folder (sub-folders are kept).`, "", "MOVE", "DESTINATION FOLDER");
  if (!dest?.trim()) return;
  return act(async () => {
    const res = await api.saveRemaining(S.items.map((x) => x.path), dest.trim());
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
