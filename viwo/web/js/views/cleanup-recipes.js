// CLEANUP's recipes (doc 5.1): phase 1 (safe), phase 2 (lossless open-format copies), phase 3
// (opt-in: LOSSY transcodes, marked; renumbered sequences). The picked one is what SCAN runs.
import { api } from "../api.js";
import { h, fill, badge, pref } from "../ui.js";

/** Rule -> [title, action label, badge kind, what it means] for the rules past phase 1. */
export const MORE_RULES = {
  "core.convert": ["OPEN-FORMAT COPIES", "COPY", "ok", "The lossless decoder an extraction runs writes an open-format copy (PNG, WAV, glTF...) into the extension's folder. The original stays."],
  "core.convert_replace": ["OPEN FORMATS, ORIGINALS TO TRASH", "COPY + TRASH", "", "The same lossless copy, then the original moves to the workspace trash. UNDO removes the copy and brings the original back."],
  "core.transcode_audio": ["AUDIO TO OPUS", "LOSSY COPY", "warn", "WAV, FLAC and AIFF re-encoded by ffmpeg to Opus (128 kb/s, .ogg). LOSSY: the copy holds less than the original, which stays."],
  "core.transcode_video": ["VIDEO TO H.264 MP4", "LOSSY COPY", "warn", "Videos re-encoded by ffmpeg to H.264/AAC MP4 for web players and MERGER. LOSSY: the original stays."],
  "core.renumber": ["RENUMBER SEQUENCES", "RENAME", "ok", "name1, name3, name10 become name01, name02, name03: contiguous, zero-padded, in their order. UNDO restores the names."],
};

/** What a finding's action became once applied (the row's badge). */
export const DONE = { rename: "RENAMED", trash: "IN TRASH", convert: "COPY MADE", replace: "COPY MADE · ORIGINAL IN TRASH", transcode: "LOSSY COPY MADE" };

/** The recipe picker: one radio per recipe, LOSSY or LOSSLESS marked, why one cannot act said. */
export function recipePicker(onPick) {
  const root = h("div", { class: "recipe", role: "radiogroup", "aria-label": "Recipe" });
  load(root, onPick);
  return root;
}

async function load(root, onPick) {
  let list;
  try { list = (await api.recipes()).recipes; } catch { return fill(root, h("span", { class: "dim small" }, "Phase-1 safe rules.")); }
  const pick = list.find((r) => r.id === pref("cleanupRecipe")) || list[0];
  fill(root, h("span", { class: "lbl" }, "RECIPE"), h("div", { class: "col" }, list.map((r) => option(r, r === pick, onPick))));
  onPick(pick);
}

function option(r, on, onPick) {
  const input = h("input", { type: "radio", name: "cleanup-recipe", value: r.id, checked: on,
    onchange: () => { pref("cleanupRecipe", r.id); onPick(r); } });
  const note = r.unready ? `cannot act now: ${r.unready}` : `phase ${r.phase} · ${r.rules.length} rule(s)`;
  return h("label", { class: "row", title: r.rules.join(", ") }, input, h("b", {}, r.name),
    badge(r.lossy ? "LOSSY" : "LOSSLESS", r.lossy ? "warn" : "ok"), h("span", { class: r.unready ? "small" : "dim small" }, note));
}
