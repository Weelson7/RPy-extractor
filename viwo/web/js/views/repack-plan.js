// PATCHED COPY rendering: per-container strategy in plain words, first-run states, build result cards.
import { h, btn, badge, empty, errorBox, fmtNum, stat, goBtn, openBtn, toolLink } from "../ui.js";

const base = (p) => String(p).split(/[\\/]/).pop();
const stem = (p) => base(p).replace(/\.[^.]+$/, "");
const files = (n) => `${fmtNum(n)} file${n === 1 ? "" : "s"}`;

/** Slot -> [what ViWo does, in plain words; how]. */
const STRATEGY = {
  override: (i) => [`override: copy ${fmtNum(i.members.length)} loose file${i.members.length === 1 ? "" : "s"}`, "each edited file is placed at the same path inside the patched copy"],
  "pack.rpa": (i) => [`rebuild ${base(i.container)}`, "Ren'Py archive rewritten in the copy with your edited members"],
  "pack.pck": (i) => [`rebuild ${base(i.container)}`, "Godot pack rewritten in the copy with your edited members"],
  "pack.zip": (i) => [`rebuild ${base(i.container)}`, "zip archive rewritten in the copy with your edited members"],
  "pack.upak": (i) => [`patch pak → ${stem(i.container)}_P.pak`, "the original .pak stays as is; the engine mounts the _P patch over it"],
  "pack.unity": (i) => [`patch Unity bundle ${base(i.container)}`, "edited assets are written back into the bundle in the copy"],
  "pack.rpgmaker": (i) => [`re-encrypt ${base(i.container)} for RPG Maker`, "edited media is encrypted back to the game's own format"],
};

export function strategy(item) {
  const fn = STRATEGY[item.slot];
  return fn ? fn(item) : [`pack ${base(item.container)} with ${item.slot}`, "packed by the slot's backend"];
}

const memberList = (members) => h("details", { class: "members" }, h("summary", {}, `${fmtNum(members.length)} EDITED MEMBER(S)`),
  h("ul", { class: "mono" }, members.slice(0, 200).map((m) => h("li", {}, m)), members.length > 200 ? h("li", { class: "dim" }, `+${members.length - 200} more`) : null));

export function planCard(item) {
  const [what, how] = strategy(item);
  return h("article", { class: "pcard" },
    h("header", {}, h("b", {}, what), h("span", { title: `slot ${item.slot}` }, badge(item.slot === "override" ? "LOOSE FILES" : "ARCHIVE", item.slot === "override" ? "ok" : "mute"))),
    h("p", { class: "note" }, how),
    item.container.includes("/") ? h("code", { class: "mono path" }, item.container) : null,
    memberList(item.members));
}

/** "path: reason" strings from the server, split for display. */
export function issueList(title, lines, kind = "warn") {
  if (!lines?.length) return null;
  return h("div", { class: "alert", "data-kind": kind }, h("b", {}, `${title} (${lines.length})`),
    h("ul", {}, lines.map((l) => {
      const at = l.indexOf(": ");
      return h("li", {}, at > 0 ? [h("code", { class: "mono" }, l.slice(0, at)), ` — ${l.slice(at + 2)}`] : l);
    })), lines.some((l) => /unavailable|install|no packer|no backend/i.test(l)) ? toolLink("Writing some of these back needs an optional tool.") : null);
}

const STEPS = [["01", "EDIT", "open files in the workspace with your own tools (image editor, text editor…) and save them in place"],
  ["02", "PLAN", "come back here: ViWo finds every file whose content changed since extraction"],
  ["03", "BUILD", "pick a target folder: the game is copied there and only the copy is patched, then verified"]];

export const howTo = () => h("ol", { class: "how" }, STEPS.map(([n, t, d]) => h("li", {}, h("b", { class: "mono" }, n), h("span", {}, t), h("small", {}, d))));

export const noExtraction = (err) => [empty("NO EXTRACTION IN THIS WORKSPACE", "A patched copy starts from an extraction: ViWo needs to know which game the files came from. Extract a game into this workspace first.",
  goBtn("#extract", "GO TO EXTRACT")), err ? h("p", { class: "dim small" }, err.message) : null];

export function noEdits(wsPath, replan) {
  return [empty("NO EDITS YET", "Every workspace file still matches what extraction wrote, so there is nothing to put back. Edit a file, save it, then plan again.",
    wsPath ? openBtn(wsPath, "OPEN WORKSPACE FOLDER", "ghost") : null, btn("PLAN AGAIN", replan, "primary")),
  h("span", { class: "lbl" }, "// HOW THE ROUND TRIP WORKS"), howTo()];
}

function resultCard(r) {
  const ok = !r.failed?.length && !r.error;
  return h("article", { class: `rcard ${ok ? "ok" : "bad"}` },
    h("header", {}, h("b", { class: "mark", "aria-hidden": "true" }, ok ? "✓" : "✕"),
      h("b", { title: `slot ${r.slot}${r.backend ? ` · tool ${r.backend}` : ""}` }, r.container ? base(r.container) : "LOOSE FILES"),
      badge(ok ? "VERIFIED" : "FAILED", ok ? "ok" : "err")),
    h("p", { class: "note" }, ok ? `${files(r.members)} written and read back identical.`
      : `${fmtNum(r.failed?.length || 0)} of ${files(r.members)} did not come back with your edit.`),
    r.output ? h("div", { class: "row" }, h("span", { class: "lbl" }, "WROTE"), h("code", { class: "mono path" }, r.output)) : null,
    r.error ? h("p", { class: "warn-text" }, `✕ ${r.error}`) : null,
    r.failed?.length ? h("ul", { class: "bad-list mono" }, r.failed.slice(0, 50).map((m) => h("li", {}, `✕ ${m}`))) : null,
    (r.notes || []).map((n) => h("p", { class: "warn-text small" }, `⚠ ${n}`)));
}

export function resultBody(res) {
  const results = res.results || [];
  const alarms = (res.warnings || []).filter((w) => w.includes("GAME FOLDER CHANGED"));
  const bad = results.filter((r) => r.failed?.length || r.error).length;
  return [alarms.length ? h("div", { class: "alarm", role: "alert" }, h("b", {}, "⚠ ALARM // GAME FOLDER CHANGED DURING REPACK"),
    h("p", {}, "ViWo only reads the game folder. Something else wrote to it while the copy was made."), alarms.map((a) => h("p", { class: "mono" }, a))) : null,
  h("div", { class: "stats" }, stat("CONTAINERS", fmtNum(results.length)), stat("VERIFIED", fmtNum(results.length - bad)),
    stat("FAILED", fmtNum(bad)), stat("EDITS", fmtNum(res.edits))),
  h("div", { class: "kv" }, h("span", { class: "lbl" }, "PATCHED COPY"), h("code", { class: "mono path" }, res.target), h("div", { class: "row" }, openBtn(res.target))),
  h("div", { class: "kv" }, h("span", { class: "lbl" }, "ORIGINAL"), h("code", { class: "mono path" }, res.game),
    h("div", { class: "row" }, badge(alarms.length ? "CHANGED BY ANOTHER PROGRAM" : "UNTOUCHED", alarms.length ? "err" : "ok"))),
  h("div", { class: "rcards" }, results.map(resultCard)),
  h("p", { class: "note" }, "Run the game from the patched copy to try your edits. Building again into the same folder replaces that copy.")];
}

export const SHORT = { refused: "TARGET REFUSED", busy: "WORKSPACE BUSY", not_found: "NO EXTRACTION RECORD", invalid_request: "NO TARGET FOLDER" };

const NEXT = {
  refused: "Use an empty folder, or a patched copy ViWo made earlier (it is replaced). Never a folder inside the game.",
  invalid_request: "Choose a target folder for the patched copy in 09.B.",
};

export const failure = (err) => errorBox(err, SHORT[err.code] || "PATCHED COPY FAILED", NEXT[err.code]);
