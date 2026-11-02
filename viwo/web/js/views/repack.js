// 09 PATCHED COPY: round trip. Plan the edit set, pick a target, build + verify a patched copy of the game.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, viewHead, assure, toast, toastErr, busy, pref, logLine, fmtNum, bus, emit, stat, browseBtn } from "../ui.js";
import { jobProgress, withSkeleton } from "../progress.js";
import { planCard, issueList, howTo, noExtraction, noEdits, resultBody, failure, SHORT } from "./repack-plan.js";

const S = { plan: null, err: null, running: false, ws: null, files: null };
const el = {};

function mount(root) {
  el.target = h("input", { class: "input mono grow", id: "repack-target", placeholder: "/path/to/empty-folder", spellcheck: "false",
    oninput: () => { pref(`repackOut:${S.ws}`, el.target.value.trim()); bar(); } });
  el.planBtn = btn("PLAN", (e) => busy(e.currentTarget, plan), "primary");
  el.stats = h("div", { class: "stats" });
  el.plan = h("div", {});
  el.prog = jobProgress("repack", { logClass: "mini", onStatus: (text) => { if (S.running && text) el.sum.textContent = text; } });
  el.progPanel = panel("09.C", "BUILD", null, el.prog.el);
  el.progPanel.hidden = true;
  el.result = h("div", {});
  el.sum = h("div", { class: "ab-sum mono" });
  el.why = h("span", { class: "ab-why" });
  el.build = btn("BUILD PATCHED COPY", build, "primary lg");
  root.append(
    viewHead("09", "PATCHED COPY", "Put the files you edited in the workspace back into the game, as a separate patched copy. Each patched container is re-extracted to verify your edits."),
    assure([["ORIGINAL GAME NEVER MODIFIED", "it is only read; the copy goes to a folder you choose"],
      ["EDITS = CHANGED FILES", "workspace files whose content changed since extraction"],
      ["VERIFIED", "every patched container is unpacked again and compared"]]),
    h("div", { class: "grid2" },
      h("div", { class: "col" }, panel("09.A", "EDIT SET + STRATEGY", el.planBtn, el.stats, el.plan)),
      h("div", { class: "col" }, targetPanel(), el.progPanel, el.result)),
    h("div", { class: "actionbar" }, el.sum, el.why, el.build));
  bus.addEventListener("wspath", (e) => switchTo(e.detail.path || ""));
  switchTo(bus.ws?.path || "");
}

function targetPanel() {
  const browse = browseBtn(el.target, (path) => { pref(`repackOut:${S.ws}`, path); bar(); });
  return panel("09.B", "TARGET FOLDER", badge("NEW COPY", "ok"),
    h("label", { class: "lbl", for: "repack-target" }, "PATCHED COPY GOES TO"),
    h("div", { class: "row" }, el.target, browse),
    h("p", { class: "note" }, "Use an empty folder, or a patched copy ViWo made earlier (it is replaced). Never inside the game folder: the original stays exactly as it is."));
}

function switchTo(path) {
  if (path === S.ws) return;
  Object.assign(S, { ws: path, plan: null, err: null, files: null });
  el.target.value = pref(`repackOut:${path}`) || "";
  fill(el.result);
  el.progPanel.hidden = true;
  show();
}

async function show() {
  if (S.plan || S.running) return;
  try { S.files = (await api.status()).totalKept || 0; } catch { S.files = null; }
  render();
}

async function plan() {
  try {
    S.plan = await withSkeleton(el.plan, "HASHING WORKSPACE AGAINST THE EXTRACTION RECORD…", () => api.repack({ plan: true }), 5);
    S.err = null;
  } catch (err) {
    S.plan = null;
    S.err = err;
    if (err.code !== "not_found") toastErr(err, "Plan failed: ");
  }
  render();
}

function render() {
  const p = S.plan;
  const members = p ? p.plan.reduce((n, i) => n + i.members.length, 0) : 0;
  fill(el.stats, p ? [stat("EDITS", fmtNum(p.edits), "changed files"), stat("TARGETS", fmtNum(p.plan.length), "containers + override"),
    stat("SKIPPED", fmtNum(p.skipped.length)), stat("WARNINGS", fmtNum(p.warnings.length))] : null);
  if (S.err) fill(el.plan, S.err.code === "not_found" ? noExtraction(S.err) : failure(S.err));
  else if (!p) fill(el.plan, S.files === 0 ? noExtraction() : [h("p", { class: "note first" }, "Press PLAN to find the files you edited and see how each one goes back into the game. Planning only reads."),
    h("span", { class: "lbl" }, "// HOW THE ROUND TRIP WORKS"), howTo()]);
  else fill(el.plan,
    h("div", { class: "kv" }, h("span", { class: "lbl" }, "SOURCE GAME"), h("code", { class: "mono path" }, p.game), h("div", { class: "row" }, badge("READ-ONLY", "ok"))),
    !p.edits ? noEdits(S.ws, () => plan()) : [
      h("h4", { class: "sub-h" }, `// STRATEGY · ${fmtNum(members)} MEMBER(S) IN ${fmtNum(p.plan.length)} TARGET(S)`),
      p.plan.length ? h("div", { class: "pcards" }, p.plan.map(planCard)) : h("p", { class: "warn-text" }, "None of the edits can be written back yet (see below).")],
    issueList("SKIPPED", p.skipped), issueList("WARNINGS", p.warnings));
  bar();
}

/** Why BUILD cannot start yet ("" when it can). */
function blocker() {
  if (S.running) return "building…";
  if (!S.plan) return "plan first";
  if (!S.plan.plan.length) return S.plan.edits ? "nothing can be written back" : "no edits";
  if (!el.target.value.trim()) return "pick a target folder";
  return "";
}

function bar() {
  if (!el.build) return;
  const p = S.plan;
  const out = el.target.value.trim().split(/[\\/]/).filter(Boolean).pop();
  if (!S.running) el.sum.textContent = p ? `${String(p.game).split(/[\\/]/).pop()} · ${fmtNum(p.edits)} edit(s) · ${fmtNum(p.plan.length)} target(s) → ${out || "no target folder"} · original untouched`
    : "plan to see the edit set";
  el.why.textContent = blocker();
  el.build.disabled = Boolean(el.why.textContent);
  el.build.textContent = S.running ? "BUILDING…" : "BUILD PATCHED COPY";
  el.planBtn.disabled = S.running;
}

async function build() {
  const out = el.target.value.trim();
  if (blocker()) return;
  S.running = true;
  bar();
  fill(el.result);
  el.progPanel.hidden = false;
  await el.prog.start();
  el.prog.log.append(logLine(`// PATCHED COPY :: ${S.plan.game} → ${out}`));
  el.progPanel.scrollIntoView({ block: "nearest" });
  try {
    const res = await api.repack({ out });
    S.plan = res;
    render();
    if (!res.results) {
      await el.prog.finish("ok", "NOTHING TO PATCH");
      fill(el.result, panel("09.D", "RESULT", badge("NO CHANGES", "mute"), h("p", { class: "note" }, "No edit could be written back, so no copy was made. The skipped list in 09.A says why.")));
    } else {
      await el.prog.finish(res.verified ? "ok" : "fail", res.verified ? "PATCHED COPY READY · VERIFIED" : "COPY BUILT · NOT VERIFIED");
      fill(el.result, panel("09.D", "RESULT", badge(res.verified ? "VERIFIED ✓" : "NOT VERIFIED ✕", res.verified ? "ok" : "err"), resultBody(res)));
      toast(res.verified ? "Patched copy ready and verified." : "Patched copy built, but some edits did not verify.", res.verified ? "ok" : "warn", res.target);
    }
  } catch (err) {
    await el.prog.finish("fail", SHORT[err.code] || "BUILD FAILED");
    fill(el.result, panel("09.D", "RESULT", badge(err.code === "cancelled" ? "CANCELLED" : "FAILED", err.code === "cancelled" ? "warn" : "err"), failure(err)));
    toastErr(err, "Patched copy failed: ");
  } finally {
    S.running = false;
    bar();
    emit("jobs");
  }
  el.result.firstElementChild?.classList.add("reveal");
}

export default { mount, show };
