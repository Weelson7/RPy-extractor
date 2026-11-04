// BEFORE YOU START and RESULT renderers for the capture view.
import { code } from "../registry.js";
import { featureOff } from "../feature.js";
import { h, panel, badge, stat, fmtNum, goBtn, errorBox } from "../ui.js";

const IMG = /\.(png|jpe?g|webp|gif|bmp)$/i;
const previewUrl = (rel) => `/preview/${String(rel).split("/").map(encodeURIComponent).join("/")}`;

/** Feature switch, backend, warnings and the one confirmation. Information, never a block. */
export function beforeYouStart(info, confirmed, onConfirm, recheck = () => {}) {
  const items = [];
  if (!info.enabled) items.push(featureOff("RUNTIME CAPTURE IS OFF", "It is an opt-in; turning it on applies at once, no restart.", "capture", recheck));
  if (!info.backend) {
    items.push(h("div", { class: "alert", "data-kind": "warn" }, h("b", {}, "RENDERDOC NOT INSTALLED"),
      h("p", {}, "The capture needs renderdoccmd and its Python. SYSTEM installs the pinned release with one click."),
      h("p", {}, h("a", { href: "#system" }, "Open SYSTEM →"))));
  }
  const warnings = info.warnings || [];
  items.push(h("h4", { class: "sub-h" }, `// WHAT YOU SHOULD KNOW (${warnings.length})`));
  items.push(warnings.length
    ? h("ul", { class: "warnlist" }, warnings.map((w) => h("li", {}, badge("WARNING", "warn"), " ", w)))
    : h("p", { class: "ok-text" }, "No anti-cheat markers, no known online title, no sensitive plugin."));
  const id = "cap-confirm";
  items.push(h("div", { class: "confirm-row" },
    h("input", { type: "checkbox", id, checked: confirmed, onchange: (e) => onConfirm(e.target.checked) }),
    h("label", { for: id }, h("b", {}, "I confirm: "), info.confirmation)));
  items.push(h("p", { class: "note" }, "ViWo runs RenderDoc as it would on any game and never evades or disables anti-cheat. A blocked capture or a banned account is a possible outcome, and it is yours."));
  return items;
}

function thumbs(files) {
  const images = files.filter((f) => IMG.test(f)).slice(0, 24);
  if (!images.length) return h("p", { class: "dim small" }, "No image previews (the new files are not images, or there are none).");
  return h("div", { class: "capgrid" }, images.map((rel) => h("a", { class: "capthumb", href: previewUrl(rel), target: "_blank", rel: "noopener", title: rel },
    h("img", { src: previewUrl(rel), alt: rel.split("/").pop(), loading: "lazy" }))));
}

export function renderResult(res) {
  const files = res.new || [];
  return panel(`${code("capture")}.D`, "RESULT", res.gameUnchanged === true ? badge("GAME FOLDER UNTOUCHED", "ok") : badge("GAME FOLDER RESTORED", "ok"),
    h("div", { class: "stats" },
      stat("GATHERED", fmtNum(res.gathered), "files into the workspace"),
      stat("NEW VS STATIC", fmtNum(res.newVsStatic), "not found by extraction", res.newVsStatic ? "ok" : ""),
      stat("ALREADY STATIC", fmtNum(res.alreadyStatic), "dropped as duplicates"),
      stat("BACKEND", String(res.backend || "?").toUpperCase(), "capture tool")),
    (res.warnings || []).length ? h("div", { class: "alert", "data-kind": "warn" }, h("b", {}, "NOTES"), h("ul", {}, res.warnings.map((w) => h("li", {}, w)))) : null,
    h("h4", { class: "sub-h" }, `// NEW FILES (${fmtNum(files.length)}${files.length >= 200 ? "+, first 200 listed" : ""})`),
    thumbs(files),
    files.length ? h("details", { class: "reasons" }, h("summary", {}, "FULL LIST"), h("ul", { class: "mono small" }, files.map((f) => h("li", {}, f)))) : null,
    h("div", { class: "row next-row" }, h("span", { class: "lbl" }, "NEXT"), goBtn("#workspace", `${code("workspace")} BROWSE BY TYPE →`, "sm"), goBtn("#sort", `${code("sort")} SORT →`, "sm"), goBtn("#jobs", `${code("jobs")} JOB LOG →`, "sm ghost")));
}

export function renderFailure(err) {
  const next = {
    needs_decision: "Tick the confirmation in BEFORE YOU START, then launch again.",
    refused: "The executable must be a file inside the game folder, and the workspace must be empty or one ViWo made.",
    unavailable: "Install RenderDoc from SYSTEM (one click), then try again.",
    failed: "No capture was taken, or the game did not start: press F12 in the game before quitting it.",
  }[err.code] || "";
  return panel(`${code("capture")}.D`, "RESULT", badge(err.code === "cancelled" ? "CANCELLED" : "FAILED", err.code === "cancelled" ? "warn" : "err"),
    errorBox(err, "CAPTURE DID NOT COMPLETE", next));
}
