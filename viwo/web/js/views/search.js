// SEARCH (static arm): a string, a number or a byte pattern in the workspace, the game folder or
// one file (an exe, a dll), all only read; each hit with the bytes around it, its section, RVA and
// virtual address in an executable and a unique AOB signature, ready for a patch set (doc 6.7, 18.8).
import { api } from "../api.js";
import { h, fill, btn, panel, badge, viewHead, toast, toastErr, pref, emit, bus, seg, browseBtn, fileBtn, errorBox, assure, table, kv, toggle, fmtNum } from "../ui.js";
import { currentGame } from "../game.js";
import { jobProgress } from "../progress.js";
import { registerView, code } from "../registry.js";

const S = { kind: pref("seKind") || "text", running: false, ws: "", icase: pref("seCase") === "1" };
const el = {};
const KINDS = [["text", "TEXT"], ["number", "NUMBER"], ["bytes", "BYTES"]];
const HINT = {
  text: ["TEXT (TRIED AS UTF-8, UTF-16LE, UTF-16BE)", "Health, or any words"],
  number: ["NUMBER (AN INTEGER AS 2/4/8 BYTES, LE AND BE; WITH A POINT: A 32/64-BIT FLOAT)", "100, -5, 0x64, 1.5"],
  bytes: ["BYTES (?? = ANY BYTE, AS IN A PATCH SET'S PATTERN)", "48 8B ?? 05"],
};
const hex = (n) => (n === null || n === undefined ? "—" : `0x${Number(n).toString(16)}`);
const input = (id, key, value, extra = {}) => h("input", { class: "input mono", id, value: pref(key) || value, spellcheck: "false", oninput: (e) => pref(key, e.target.value.trim()), ...extra });

function mount(root) {
  el.target = input("se-target", "seTarget", "", { class: "input mono grow", placeholder: "a workspace, a game folder or one file" });
  el.value = input("se-value", "seValue", "", { class: "input mono grow", onkeydown: (e) => e.key === "Enter" && run() });
  el.valueLbl = h("label", { class: "lbl", for: "se-value" });
  el.widths = input("se-widths", "seWidths", "2,4,8");
  el.maxHits = input("se-max", "seMax", "1000", { type: "number", min: "1" });
  el.perFile = input("se-per", "sePer", "100", { type: "number", min: "1" });
  el.caseRow = h("div", {}, toggle("se-case", "ANY CASE", "Health also finds HEALTH and health, in any script", S.icase, (v) => { S.icase = v; pref("seCase", v ? "1" : "0"); }));
  el.widthRow = h("div", {}, h("label", { class: "lbl", for: "se-widths" }, "INTEGER WIDTHS IN BYTES (ADD 1 FOR SINGLE BYTES: FOUND NEARLY EVERYWHERE)"), h("div", { class: "row" }, el.widths));
  el.progHost = h("div", {});
  el.result = h("div", {});
  el.sum = h("div", { class: "ab-sum mono" });
  el.why = h("span", { class: "ab-why" });
  el.cancel = btn("CANCEL", () => el.prog?.cancel(), "ghost", { hidden: true });
  el.go = btn("SEARCH", run, "primary lg");
  S.ws = bus.ws?.path || "";
  root.append(
    viewHead(code("search"), "SEARCH", "Find the thing you want to change: a string, a number or a byte pattern in the workspace's files, the game folder or one executable. Each hit comes with the bytes around it, its address in an executable and a signature a patch set can use."),
    assure([["READ-ONLY", "files are only read, chunk by chunk; nothing is written into the game"],
      ["NOTHING SKIPPED SILENTLY", "unreadable files are named, a cap that drops hits is said"],
      ["INTO THE WORKSPACE", "every search is kept under .search/ in the active workspace"]]),
    h("div", { class: "grid2" },
      h("div", { class: "col" },
        panel(`${code("search")}.A`, "WHERE", badge("READ-ONLY SOURCE", "ok"),
          h("label", { class: "lbl", for: "se-target" }, "SEARCH IN (A FOLDER OR ONE FILE)"),
          h("div", { class: "row" }, el.target, browseBtn(el.target, keep), fileBtn(el.target, keep, currentGame)),
          h("div", { class: "row" }, btn("THE WORKSPACE", () => use(S.ws), "sm ghost"), btn("THE GAME", () => use(currentGame()), "sm ghost")),
          h("p", { class: "note" }, "Results are kept in the active workspace: ", (el.wsNote = h("code", { class: "mono" }, S.ws || "—")), ".")),
        panel(`${code("search")}.B`, "WHAT", seg(KINDS, S.kind, (v) => { S.kind = v; pref("seKind", v); kindChanged(); }, { class: "seg sm" }),
          el.valueLbl, h("div", { class: "row" }, el.value), el.caseRow, el.widthRow,
          h("label", { class: "lbl", for: "se-max" }, "AT MOST, OVERALL AND PER FILE (SAID WHEN REACHED)"),
          h("div", { class: "row" }, el.maxHits, el.perFile))),
      h("div", { class: "col" }, el.progHost, el.result)),
    h("div", { class: "actionbar" }, el.sum, el.why, el.cancel, el.go));
  bus.addEventListener("wspath", (e) => { S.ws = e.detail.path || ""; el.wsNote.textContent = S.ws || "—"; });
  for (const field of [el.target, el.value]) field.addEventListener("input", bar);
  kindChanged();
}

const keep = (p) => { pref("seTarget", p); bar(); };

function use(path) {
  if (!path) return toast("Nothing to use yet: pick a game or open a workspace first.", "warn");
  el.target.value = path;
  keep(path);
}

/** Why SEARCH cannot run yet ("" when it can): said beside the button, as in every view. */
function bar() {
  const why = S.running ? "a search is running" : !el.target.value.trim() ? "enter where to search"
    : !el.value.value.trim() ? "enter what to look for" : "";
  el.why.textContent = why;
  el.go.disabled = Boolean(why);
}

function kindChanged() {
  const [label, hint] = HINT[S.kind] || HINT.text;
  el.valueLbl.textContent = label;
  el.value.placeholder = hint;
  el.caseRow.hidden = S.kind !== "text";
  el.widthRow.hidden = S.kind !== "number";
  bar();
}

async function run() {
  const target = el.target.value.trim(), value = S.kind === "text" ? el.value.value : el.value.value.trim();
  if (S.running || !target || !value.trim()) return bar();
  S.running = true;
  bar();
  el.cancel.hidden = false;
  el.prog = jobProgress("search", { logClass: "mini", onStatus: (t) => { if (S.running && t) el.sum.textContent = t; } });
  fill(el.progHost, panel(`${code("search")}.C`, "RUN", null, el.prog.el));
  fill(el.result);
  await el.prog.start();
  try {
    const res = await api.search({ target, kind: S.kind, value, ignoreCase: S.icase, widths: el.widths.value.trim(),
      maxHits: el.maxHits.value.trim(), perFile: el.perFile.value.trim() });
    await el.prog.finish("ok", `${fmtNum(res.hitCount)} HIT(S)`);
    fill(el.result, results(res));
    el.sum.textContent = `${fmtNum(res.hitCount)} hit(s) in ${fmtNum(res.filesWithHits)} of ${fmtNum(res.searched)} file(s)`;
  } catch (err) {
    await el.prog.finish(err.code === "cancelled" ? "cancel" : "fail", "SEARCH STOPPED");
    fill(el.result, errorBox(err, "SEARCH FAILED"));
    toastErr(err, "search failed: ");
  } finally {
    S.running = false;
    el.cancel.hidden = true;
    bar();
    emit("jobs");
  }
}

/** A hit as a patch set entry: the AOB form when a unique signature was found, else the offset form. */
function patchEntry(x) {
  const sig = x.signature?.pattern ? { file: x.file, pattern: x.signature.pattern, at: x.signature.at } : { ...x.patch };
  return { ...sig, patched: "" };
}

async function copyPatch(x) {
  try {
    await navigator.clipboard.writeText(JSON.stringify(patchEntry(x), null, 1));
    toast("Patch entry copied: fill in \"patched\" and add it to a patch set's patches (PATCHING › PATCHES + MODS).", "ok");
  } catch (err) { toastErr(err, "copy failed: "); }
}

function results(res) {
  const q = res.query;
  const rows = res.hits.map((x) => ({
    file: h("span", { class: "mono path" }, x.file),
    offset: h("span", { class: "mono" }, hex(x.offset)),
    enc: badge(x.encoding, ""),
    where: x.section !== undefined && x.section !== null ? h("span", { class: "mono" }, `${x.section} · RVA ${hex(x.rva)} · VA ${hex(x.va)}`) : "—",
    bytes: h("span", { class: "mono path" }, x.before, " [", h("b", {}, x.match), "] ", x.after),
    act: btn("COPY PATCH", () => copyPatch(x), "sm ghost", { title: x.signature?.pattern ? `signature ${x.signature.pattern}` : "offset form (no unique signature)" }),
  }));
  return panel(`${code("search")}.D`, "HITS", badge(`${fmtNum(res.hitCount)} IN ${fmtNum(res.filesWithHits)} FILE(S)`, res.hitCount ? "ok" : "mute"),
    kv("SEARCHED", h("span", { class: "mono" }, `${fmtNum(res.searched)} of ${fmtNum(res.files)} file(s), ${fmtNum(res.bytes)} bytes, ${res.seconds} s`)),
    kv("TRIED", h("span", { class: "mono" }, q.tried.join(", "))),
    ...q.notes.map((n) => kv("NOTE", h("span", {}, n))),
    ...res.warnings.slice(0, 8).map((w) => kv("WARNING", h("span", { class: "path" }, w))),
    res.unreadable.length ? kv("UNREADABLE", h("span", {}, `${fmtNum(res.unreadable.length)} file(s), all named in the report`)) : null,
    res.saved ? kv("SAVED", h("code", { class: "mono path" }, res.saved)) : null,
    rows.length ? table([{ key: "file", label: "FILE" }, { key: "offset", label: "OFFSET" }, { key: "enc", label: "AS" },
      { key: "where", label: "IN THE EXECUTABLE" }, { key: "bytes", label: "BYTES AROUND IT" }, { key: "act", label: "" }], rows, { caption: "Search hits" })
      : h("p", { class: "dim" }, "Nothing found in what was searched."));
}

registerView({ id: "search", arm: "static", order: 35, title: "SEARCH", subtitle: "a string, number or bytes", mount });
