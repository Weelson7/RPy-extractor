// ASSETS: the way back for what ViWo decoded (PNG, WAV, glTF, text). The edited files of the
// active workspace by container: what each becomes (member, encoder, packer), MOD or OVERWRITE
// for the run, what cannot go back and why; PLAN and WRITE call the API of `viwo repack`.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, seg, viewHead, assure, toast, toastErr, busy, pref, logLine, fmtNum, bus, emit, stat, browseBtn, empty } from "../ui.js";
import { jobProgress, withSkeleton } from "../progress.js";
import { issueList, noExtraction, resultBody, failure, SHORT } from "./repack-plan.js";
import { registerView, code } from "../registry.js";

const S = { plan: null, err: null, running: false, ws: null, mode: pref("assetsMode") || "mod" };
const el = {};
const MODES = {
  mod: ["MOD", "the game's own files stay as they are: an override archive or loose files the engine loads over them, where the engine has one"],
  overwrite: ["OVERWRITE", "the container itself is rewritten in the patched copy with your edits"],
};

function mount(root) {
  el.planBtn = btn("PLAN", (e) => busy(e.currentTarget, plan), "primary");
  el.mode = seg(Object.entries(MODES).map(([v, [label]]) => [v, label]), S.mode, pick, { "aria-label": "Mod or overwrite" });
  el.modeNote = h("p", { class: "note" });
  el.target = h("input", { class: "input mono grow", id: "assets-target", placeholder: "/path/to/empty-folder", spellcheck: "false",
    oninput: () => { pref(`repackOut:${S.ws}`, el.target.value.trim()); bar(); } });
  el.stats = h("div", { class: "stats" });
  el.plan = h("div", {});
  el.gone = h("div", {});
  el.prog = jobProgress("repack", { logClass: "mini" });
  el.progPanel = panel(`${code("assets")}.D`, "WRITE", null, el.prog.el);
  el.progPanel.hidden = true;
  el.result = h("div", {});
  el.sum = h("div", { class: "ab-sum mono" });
  el.why = h("span", { class: "ab-why" });
  el.write = btn("WRITE", write, "primary lg");
  root.append(
    viewHead(code("assets"), "ASSETS", "Every file ViWo decoded can go back: edit the PNG, the glTF or the text table, and it is encoded into the game's own format, then packed into its container in a patched copy."),
    assure([["TWO WAY", "an edited decoded file is encoded back into the member it came from"],
      ["NEVER SILENT", "a file that cannot go back is listed with the reason"],
      ["VERIFIED", "each packed member is read back and compared with the encoded bytes"]]),
    h("div", { class: "grid2" },
      h("div", { class: "col" }, panel(`${code("assets")}.A`, "MOD OR OVERWRITE", null, el.mode, el.modeNote),
        panel(`${code("assets")}.B`, "EDITED FILES BY CONTAINER", el.planBtn, el.stats, el.plan)),
      h("div", { class: "col" }, panel(`${code("assets")}.C`, "CANNOT GO BACK", null, el.gone), targetPanel(), el.progPanel, el.result)),
    h("div", { class: "actionbar" }, el.sum, el.why, el.write));
  bus.addEventListener("wspath", (e) => switchTo(e.detail.path || ""));
  switchTo(bus.ws?.path || "");
}

function targetPanel() {
  const browse = browseBtn(el.target, (path) => { pref(`repackOut:${S.ws}`, path); bar(); });
  return panel(`${code("assets")}.E`, "PATCHED COPY", badge("SAME AS PATCHED COPY", "mute"),
    h("label", { class: "lbl", for: "assets-target" }, "WRITTEN TO"), h("div", { class: "row" }, el.target, browse),
    h("p", { class: "note" }, "An empty folder or a patched copy ViWo made (it is rebuilt). The game folder is only read."));
}

function pick(mode) {
  S.mode = mode;
  pref("assetsMode", mode);
  if (S.plan) plan();
  else render();
}

function switchTo(path) {
  if (path === S.ws) return;
  Object.assign(S, { ws: path, plan: null, err: null });
  el.target.value = pref(`repackOut:${path}`) || "";
  fill(el.result);
  el.progPanel.hidden = true;
  render();
}

async function plan() {
  try {
    S.plan = await withSkeleton(el.plan, "FINDING YOUR EDITS AND THEIR WAY BACK…", () => api.repack({ plan: true, mode: S.mode }), 5);
    S.err = null;
  } catch (err) {
    Object.assign(S, { plan: null, err });
    if (err.code !== "not_found") toastErr(err, "Plan failed: ");
  }
  render();
}

/** One edited file's way back: file -> member, through encoder; or the member itself. */
const wayRow = (w) => h("li", {}, h("code", { class: "mono" }, w.file), " → ", h("code", { class: "mono" }, w.member),
  h("span", { class: "dim" }, ` · ${w.encoder} (${w.backend})`), w.replaces ? h("span", { class: "dim" }, ` · replaces ${w.replaces}`) : null);

function card(item) {
  const decoded = new Set(item.ways.map((w) => w.member));
  const plain = item.members.filter((m) => !decoded.has(m));
  const mode = item.mode === "mod" ? ["MOD", "ok"] : ["OVERWRITE", "warn"];
  return h("article", { class: "pcard" },
    h("header", {}, h("b", {}, item.container || "LOOSE FILES"), badge(mode[0], mode[1]), badge(item.slot, "mute")),
    h("p", { class: "note" }, item.why || ""),
    h("ul", { class: "mono" }, item.ways.map(wayRow), plain.map((m) => h("li", {}, h("code", { class: "mono" }, m), h("span", { class: "dim" }, " · as edited"))),
      item.drops.map((m) => h("li", { class: "dim" }, `✕ ${m} removed`))));
}

function render() {
  const p = S.plan;
  el.modeNote.textContent = `${MODES[S.mode][0]}: ${MODES[S.mode][1]}. Where an engine has only one of the two, each container says which one is used and why.`;
  el.mode.set(S.mode);
  const ways = p ? p.plan.reduce((n, i) => n + i.ways.length, 0) : 0;
  fill(el.stats, p ? [stat("EDITS", fmtNum(p.edits)), stat("DECODED BACK", fmtNum(ways), "through an encoder"),
    stat("CONTAINERS", fmtNum(p.plan.length)), stat("CANNOT", fmtNum(p.skipped.length), "", p.skipped.length ? "warn" : "")] : null);
  if (S.err) fill(el.plan, S.err.code === "not_found" ? noExtraction(S.err) : failure(S.err));
  else if (!p) fill(el.plan, h("p", { class: "note first" }, "Edit decoded files in the workspace (a PNG of a texture, a sprite sheet, a text table), then press PLAN. Planning only reads."));
  else if (!p.plan.length) fill(el.plan, empty("NOTHING TO WRITE BACK", p.edits ? "None of the edited files can go back yet: CANNOT GO BACK says why." : "No file of the workspace was edited since extraction."));
  else fill(el.plan, h("div", { class: "pcards" }, p.plan.map(card)));
  fill(el.gone, p ? [issueList("ONE WAY OR BLOCKED", p.skipped), issueList("WARNINGS", p.warnings),
    !p.skipped.length && !p.warnings.length ? h("p", { class: "note" }, "Every edited file has a way back.") : null]
    : h("p", { class: "note" }, "Plan to see which edited files cannot go back (audio and video stay one way: their encoders are proprietary)."));
  bar();
}

function blocker() {
  if (S.running) return "writing…";
  if (!S.plan) return "plan first";
  if (!S.plan.plan.length) return "nothing can go back";
  if (!el.target.value.trim()) return "pick a folder for the patched copy";
  return "";
}

function bar() {
  const p = S.plan;
  if (!S.running) el.sum.textContent = p ? `${fmtNum(p.edits)} edit(s) · ${MODES[S.mode][0]} · ${fmtNum(p.plan.length)} container(s)` : "plan to see the way back";
  el.why.textContent = blocker();
  el.write.disabled = Boolean(el.why.textContent);
  el.write.textContent = S.running ? "WRITING…" : "WRITE";
  el.planBtn.disabled = S.running;
}

async function write() {
  if (blocker()) return;
  const out = el.target.value.trim();
  Object.assign(S, { running: true });
  bar();
  fill(el.result);
  el.progPanel.hidden = false;
  await el.prog.start();
  el.prog.log.append(logLine(`// ASSETS :: ${MODES[S.mode][0]} → ${out}`));
  try {
    const res = await api.repack({ out, mode: S.mode });
    S.plan = res;
    render();
    await el.prog.finish(res.verified ? "ok" : "fail", res.verified ? "WRITTEN · VERIFIED" : "WRITTEN · NOT VERIFIED");
    fill(el.result, panel(`${code("assets")}.F`, "VERIFY", badge(res.verified ? "VERIFIED ✓" : "NOT VERIFIED ✕", res.verified ? "ok" : "err"), resultBody(res)));
    toast(res.verified ? "Assets written back and verified." : "Written, but some members did not verify.", res.verified ? "ok" : "warn", res.target);
  } catch (err) {
    await el.prog.finish(err.code === "cancelled" ? "cancel" : "fail", SHORT[err.code] || "WRITE FAILED");
    fill(el.result, panel(`${code("assets")}.F`, "VERIFY", badge("FAILED", "err"), failure(err)));
    toastErr(err, "Write failed: ");
  } finally {
    S.running = false;
    bar();
    emit("jobs");
  }
}

registerView({ id: "assets", arm: "patching", order: 15, title: "ASSETS", subtitle: "decoded files → the game's format", mount, show: () => { if (!S.plan && !S.running) render(); } });
