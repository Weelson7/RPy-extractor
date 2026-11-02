// 08 CLEANUP: asset sanitizer, phase 1. Scan (read-only), tick findings, apply moves/renames, undo.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, viewHead, assure, empty, errorBox, toast, toastErr, confirmBox, pref, fmtNum, bus, emit, stat, goBtn } from "../ui.js";
import { withSkeleton } from "../progress.js";

/** Rule -> [title, action label, badge kind, what it means]. Object order = display order. */
const RULES = {
  "core.zero_byte": ["EMPTY FILES", "TRASH", "", "0-byte files hold nothing. They move to the workspace trash."],
  "core.junk": ["ENGINE / OS JUNK", "TRASH", "", "Import caches, .meta sidecars, Thumbs.db, desktop.ini and similar leftovers. They move to the workspace trash."],
  "core.extension": ["WRONG EXTENSION", "RENAME", "ok", "The bytes say another format (a PNG named .jpg, say). Only the name changes; the content is untouched."],
  "core.duplicate": ["EXACT DUPLICATES", "TRASH", "", "Byte-identical copies. The cleanest copy stays put; the extra copies move to the workspace trash."],
  "core.health": ["HEALTH", "REPORT ONLY", "mute", "Truncated, corrupt or padded files. Listed so you can check them; ViWo changes nothing."],
};
const MEDIA = { image: /\.(png|jpe?g|gif|webp|bmp|avif)$/i, audio: /\.(ogg|mp3|wav|opus|flac|m4a|aac)$/i };
const S = { groups: [], recipe: null, plan: null, sel: new Set(), applied: new Set(), done: null, busy: false, ws: null, files: null };
const el = {};
const KEEP = 200; // moved entries remembered with the undo token

function mount(root) {
  el.recipe = h("div", { class: "recipe" });
  el.stats = h("div", { class: "stats" });
  el.scan = btn("SCAN", () => scan(), "primary");
  el.find = h("div", { class: "fgroups" });
  el.count = h("span", { class: "mono dim" });
  el.done = h("div", {});
  el.sum = h("div", { class: "ab-sum mono" });
  el.why = h("span", { class: "ab-why" });
  el.apply = btn("APPLY SELECTED", apply, "primary lg");
  root.append(
    viewHead("08", "CLEANUP", "Find empty files, engine junk, mislabeled extensions and exact duplicates in the active workspace. Scan first; only the findings you tick are applied."),
    assure([["NOTHING IS DELETED", "trashed files move to the workspace trash — see 02 WORKSPACE"],
      ["NOTHING LOSSY", "no file content is rewritten: only moves and renames"],
      ["UNDO", "every apply is journaled and can be reversed"]]),
    h("div", { class: "tool-grid" },
      h("div", { class: "col" }, panel("08.A", "SCAN", el.scan, el.recipe, el.stats, ruleKey()), el.done),
      panel("08.B", "FINDINGS", el.count, el.find)),
    h("div", { class: "actionbar" }, el.sum, el.why, el.apply));
  loadRecipe();
  bus.addEventListener("wspath", (e) => switchTo(e.detail.path || ""));
  switchTo(bus.ws?.path || "");
}

const ruleKey = () => h("details", { class: "optgroup rulekey" }, h("summary", {}, "WHAT EACH RULE DOES"),
  h("dl", {}, Object.values(RULES).map(([t, a, k, why]) => [h("dt", {}, t, " ", badge(a, k)), h("dd", {}, why)])));

async function loadRecipe() {
  try {
    const r = (await api.recipes()).recipes.find((x) => !x.lossy);
    S.recipe = r;
    fill(el.recipe, h("span", { class: "lbl" }, "RECIPE"), h("b", {}, r.name), badge("LOSSLESS", "ok"),
      h("span", { class: "dim small" }, `${r.rules.length} rules`));
  } catch { fill(el.recipe, h("span", { class: "dim small" }, "Phase-1 safe rules.")); }
}

const store = (v) => pref(`cleanupUndo:${S.ws}`, v === undefined ? undefined : v ? JSON.stringify(v) : "");

function switchTo(path) {
  if (path === S.ws) return;
  Object.assign(S, { ws: path, plan: null, files: null });
  S.sel.clear();
  S.applied.clear();
  try { S.done = JSON.parse(store() || "null"); } catch { S.done = null; }
  show();
}

async function show() {
  if (S.plan) return;
  try { S.files = (await api.status()).totalKept || 0; } catch { S.files = null; }
  render();
}

async function scan() {
  if (S.busy) return;
  if (S.done && !(await confirmBox("SCAN AGAIN", "A new scan drops the UNDO for the last cleanup. The files stay where they are now.", { ok: "SCAN" }))) return;
  S.busy = true;
  bar();
  try {
    const plan = await withSkeleton(el.find, "READING + HASHING WORKSPACE FILES…", () => api.sanitize("plan", {}), 6);
    Object.assign(S, { plan, done: null, files: plan.scanned });
    store(null);
    S.applied.clear();
    S.sel = new Set(plan.findings.map((f, i) => (f.action === "none" ? -1 : i)).filter((i) => i >= 0));
  } catch (err) {
    S.plan = null;
    S.err = err;
  } finally {
    S.busy = false;
    render();
    S.err = null;
  }
}

function render() {
  const f = S.plan?.findings || [];
  S.groups = [];
  el.count.textContent = S.plan ? `${fmtNum(f.length)} FINDING(S)` : "";
  fill(el.find, S.err ? errorBox(S.err, "SCAN FAILED", S.err.code === "busy" ? "A job is writing to this workspace. Scan again once it has finished." : "")
    : !S.plan ? idle() : !f.length ? (S.plan.scanned ? empty("WORKSPACE IS CLEAN", `${fmtNum(S.plan.scanned)} files scanned. Nothing to clean.`,
      goBtn("#sort", "03 SORT →"), goBtn("#merger", "06 MAKE A VIDEO →", "ghost")) : noFiles())
      : groups(f));
  renderDone();
  sync();
}

/** Selection changed: update boxes, group headers, stats and the bar in place (open previews survive). */
function sync() {
  const f = S.plan?.findings || [];
  el.find.querySelectorAll(".frow[data-i]").forEach((li) => {
    const i = Number(li.dataset.i), on = S.sel.has(i) && !S.applied.has(i);
    li.classList.toggle("on", on);
    const box = li.querySelector("input");
    if (box) box.checked = on;
  });
  for (const g of S.groups) {
    const on = g.open.filter((i) => S.sel.has(i)).length;
    Object.assign(g.all, { checked: on === g.open.length, indeterminate: on > 0 && on < g.open.length });
    g.tick.textContent = `${on}/${g.open.length} ticked`;
  }
  fill(el.stats, S.plan ? [stat("SCANNED", fmtNum(S.plan.scanned), "workspace files"), stat("FINDINGS", fmtNum(f.length)),
    stat("SELECTED", fmtNum(S.sel.size), "to apply"), stat("REPORT ONLY", fmtNum(f.filter((x) => x.action === "none").length), "health")] : null);
  bar();
}

const noFiles = () => empty("WORKSPACE EMPTY", "Nothing to clean yet. Extract a game into this workspace first.", goBtn("#extract", "GO TO 01 EXTRACT"));

const idle = () => (S.files === 0 ? noFiles() : empty("NO SCAN YET",
  "ViWo reads every workspace file (read-only) and lists what could be cleaned. Nothing changes until you press APPLY SELECTED.", btn("SCAN NOW", () => scan(), "primary")));

function groups(findings) {
  const by = {};
  findings.forEach((f, i) => (by[f.rule] ||= []).push({ f, i }));
  const order = [...Object.keys(RULES), ...Object.keys(by).filter((r) => !RULES[r])];
  return order.filter((r) => by[r]).map((r) => group(r, by[r]));
}

function group(rule, items) {
  const [title, act, kind, why] = RULES[rule] || [rule, "?", "mute", ""];
  const open = items.filter((x) => x.f.action !== "none" && !S.applied.has(x.i)).map((x) => x.i);
  const all = open.length ? h("input", { type: "checkbox", "aria-label": `Select all: ${title}`,
    onchange: (e) => { open.forEach((i) => (e.target.checked ? S.sel.add(i) : S.sel.delete(i))); sync(); } }) : h("span", { class: "nochk", "aria-hidden": "true" }, "—");
  const tick = h("span", { class: "mono dim small" });
  if (open.length) S.groups.push({ open, all, tick });
  return h("section", { class: `fgroup ${act === "REPORT ONLY" ? "report" : ""}`, "aria-label": title, title: `rule ${rule}` },
    h("header", {}, all, h("b", {}, title), badge(`${fmtNum(items.length)} FILE${items.length === 1 ? "" : "S"}`, "mute"), badge(act, kind), open.length ? tick : null),
    h("p", { class: "note" }, why),
    h("ol", { class: "flist" }, items.slice(0, 500).map(row)),
    items.length > 500 ? h("p", { class: "dim small" }, `+${fmtNum(items.length - 500)} more not listed (still selectable with the group box)`) : null);
}

function row({ f, i }) {
  const done = S.applied.has(i);
  const id = `cf-${i}`;
  const pick = f.action === "none" ? h("span", { class: "nochk", title: "report only: nothing to apply" }, "·")
    : h("input", { type: "checkbox", id, disabled: done, onchange: (e) => { e.target.checked ? S.sel.add(i) : S.sel.delete(i); sync(); } });
  return h("li", { class: `frow ${done ? "done" : ""}`, "data-i": i }, pick,
    h(f.action === "none" ? "span" : "label", { class: "fpath mono", for: f.action === "none" ? null : id, title: f.path }, f.path),
    h("span", { class: "fmsg" }, f.message, f.to ? h("b", { class: "mono" }, ` → ${f.to}`) : null),
    done ? badge(f.action === "rename" ? "RENAMED" : "IN TRASH", "ok") : previewLink(f.path));
}

function previewLink(path) {
  const kind = MEDIA.image.test(path) ? "image" : MEDIA.audio.test(path) ? "audio" : "";
  if (!kind) return h("span");
  const url = `/preview/${path.split("/").map(encodeURIComponent).join("/")}`;
  return h("a", { class: "btn sm ghost", href: url, target: "_blank", rel: "noopener", "aria-expanded": "false", "aria-label": `Preview ${path}`,
    onclick: (e) => { if (e.ctrlKey || e.metaKey || e.shiftKey || e.button) return; e.preventDefault(); togglePreview(e.currentTarget, kind, url, path); } }, "PREVIEW");
}

function togglePreview(a, kind, url, path) {
  const li = a.closest("li");
  const open = li.nextElementSibling?.classList.contains("fprev");
  if (open) li.nextElementSibling.remove();
  else li.after(h("li", { class: "fprev" }, kind === "image" ? h("img", { src: url, alt: `Preview of ${path}` })
    : h("audio", { src: url, controls: true, preload: "metadata", "aria-label": `Preview of ${path}` })));
  a.setAttribute("aria-expanded", String(!open));
  a.textContent = open ? "PREVIEW" : "HIDE";
}

function bar() {
  const f = S.plan?.findings || [];
  const sel = [...S.sel].map((i) => f[i]).filter(Boolean);
  const n = (a) => sel.filter((x) => x.action === a).length;
  el.sum.textContent = S.applied.size && !sel.length ? `${S.applied.size} APPLIED · undo in 08.C · ${f.length - S.applied.size} finding(s) left as is`
    : S.plan ? `${sel.length} SELECTED · ${n("trash")} → workspace trash · ${n("rename")} rename · ${f.length - sel.length} left as is`
    : `${(S.ws || "").split(/[\\/]/).pop() || "workspace"} · scan to list findings`;
  el.why.textContent = S.busy ? "working…" : !S.plan ? "scan first" : !sel.length ? "tick findings to apply" : "";
  el.apply.disabled = Boolean(el.why.textContent);
  el.apply.textContent = sel.length ? `APPLY SELECTED (${sel.length})` : "APPLY SELECTED";
  el.scan.disabled = S.busy;
}

async function apply() {
  const idx = [...S.sel].sort((a, b) => a - b);
  if (!idx.length || !S.plan || S.busy) return;
  S.busy = true;
  bar();
  try {
    const res = await api.sanitize("apply", { planId: S.plan.planId, accept: idx });
    const failed = new Set((res.failed || []).map((x) => x.split(": ")[0]));
    const real = new Set((res.moved || []).map((m) => m.from)); // what the server actually moved
    const ok = idx.filter((i) => (res.moved ? real.has(S.plan.findings[i].path) : !failed.has(S.plan.findings[i].path)));
    ok.forEach((i) => S.applied.add(i));
    S.sel.clear();
    const prev = S.done?.token === res.undoToken ? S.done : { applied: 0, failed: [], moved: [], more: 0 }; // one plan = one undo journal
    const moved = [...prev.moved, ...ok.map((i) => S.plan.findings[i]).map((x) => ({ a: x.action, p: x.path, to: x.to || "" }))];
    S.done = { token: res.undoToken, applied: prev.applied + res.applied, failed: [...prev.failed, ...(res.failed || [])], at: Date.now(),
      moved: moved.slice(0, KEEP), more: prev.more + Math.max(0, moved.length - KEEP) };
    store(S.done);
    toast(`Cleanup applied: ${fmtNum(res.applied)} file(s) moved or renamed.`, failed.size ? "warn" : "ok", failed.size ? `${failed.size} failed` : "UNDO is available.");
    emit("workspace");
  } catch (err) {
    toastErr(err, "Cleanup not applied: ");
  } finally { S.busy = false; render(); }
}

async function undo(e) {
  if (!S.done || S.busy) return;
  S.busy = true;
  e.currentTarget.disabled = true;
  try {
    const res = await api.sanitize("undo", { undoToken: S.done.token });
    toast(`Undo: ${fmtNum(res.restored)} file(s) back where they were.`, "ok");
    S.done = null;
    S.applied.clear();
  } catch (err) {
    if (err.code === "not_found") { S.done = null; toast("Nothing to undo: that cleanup was already reversed.", "warn"); } else toastErr(err, "Undo failed: ");
  } finally {
    if (!S.done) store(null);
    S.busy = false;
    render();
    emit("workspace");
  }
}

function renderDone() {
  const d = S.done;
  if (!d) return fill(el.done);
  const trash = d.moved.filter((m) => m.a === "trash").length;
  fill(el.done, panel("08.C", "LAST CLEANUP", badge("UNDO AVAILABLE", "ok"),
    h("div", { class: "stats" }, stat("APPLIED", fmtNum(d.applied), new Date(d.at).toLocaleTimeString()),
      stat("TO TRASH", fmtNum(trash), "recoverable"), stat("RENAMED", fmtNum(d.moved.length - trash)), stat("FAILED", fmtNum(d.failed.length))),
    h("ol", { class: "moved mono" }, d.moved.map((m) => h("li", {}, h("b", {}, m.a === "trash" ? "TRASH" : "RENAME"), h("span", { title: m.p }, m.p),
      h("i", {}, m.a === "trash" ? "→ workspace trash" : `→ ${m.to}`))), d.more ? h("li", { class: "dim" }, `+${fmtNum(d.more)} more`) : null),
    d.failed.length ? h("div", { class: "alert warn" }, h("b", {}, "NOT APPLIED"), h("ul", {}, d.failed.map((x) => h("li", {}, x)))) : null,
    h("div", { class: "row" }, btn("UNDO THIS CLEANUP", undo, "primary"), goBtn("#workspace", "SEE TRASH IN 02 WORKSPACE →", "ghost")),
    h("p", { class: "note" }, "UNDO stays available until your next SCAN.")));
}

export default { mount, show };
