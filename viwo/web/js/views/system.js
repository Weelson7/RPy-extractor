// 05 SYSTEM: optional tools by engine (what each enables), formats (slots), plugins, startup ini and notes.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, viewHead, errorBox, busy, fmtNum, stat } from "../ui.js";
import { withSkeleton } from "../progress.js";

/** Tool id -> what it enables, in plain words. */
const ENABLES = {
  ffmpeg: "06 MERGER videos, and decoding game images, audio and video",
  ffprobe: "06 MERGER (reads clip lengths); ships with ffmpeg",
  py7zr: "opening .7z archives",
  sevenzip: "opening .7z, .rar and .unitypackage files",
  unrar: "opening .rar archives",
  vgmstream: "turning game audio (Wwise .wem, FMOD .fsb, CRI…) into playable WAV",
  renderdoccmd: "runtime GPU capture (advanced)",
  rdpython: "runtime GPU capture (advanced)",
  gdre: "opening Godot .pck packs, encrypted ones too",
  godotpcktool: "opening Godot .pck packs and Godot patched copies",
  datatool: "Overwatch extraction",
  quickbms: "archives handled by QuickBMS scripts",
  unrpa: "a second Ren'Py .rpa unpacker (the built-in one already works)",
  assetstudiomod: "Unity asset export (alternative to UnityPy)",
  unitypy: "Unity asset export and Unity patched copies",
  repak: "opening Unreal .pak files and Unreal patched copies",
  retoc: "Unreal Engine 5 IoStore files (.utoc/.ucas)",
};
const NAMES = { upak: ".pak", unity: "Unity bundles", rpgmaker: "RPG Maker files", bms: "QuickBMS archives", utoc: ".utoc/.ucas" };
const FIXED = { "carve.signatures": "find files hidden inside unknown data", "capture.gpu": "runtime GPU capture", "media.encode": "encode MP4 videos (06 MERGER)" };

/** Slot id -> plain words: unarchive.pck -> "open .pck archives". */
export function slotText(id) {
  const [verb, what] = String(id).split(".");
  const obj = NAMES[what] || `.${what}`;
  return FIXED[id] || { unarchive: `open ${obj} archives`, pack: `patched copies: ${obj}`, export: `export ${what} assets`,
    decode: `decode game ${what}` }[verb] || id;
}

const el = {};

function mount(root) {
  el.stats = h("div", { class: "stats" }, ["OS", "TOOLS FOUND", "FORMATS READY", "PLUGINS", "STARTUP NOTES"].map((l) => stat(l, "…")));
  el.tools = h("div", {});
  el.slots = h("div", {});
  el.plugins = h("div", { class: "cards" });
  el.startup = h("div", {});
  root.append(
    viewHead("05", "SYSTEM", "What this ViWo install can do, and which optional tools unlock more formats. Install a tool, then restart ViWo.",
      btn("REFRESH", (e) => busy(e.currentTarget, load), "ghost")),
    el.stats,
    panel("05.A", "OPTIONAL TOOLS BY ENGINE", null, el.tools),
    h("div", { class: "grid2 sys" },
      h("div", { class: "col" }, panel("05.B", "FORMATS (BACKEND SLOTS)", null, el.slots)),
      h("div", { class: "col" }, panel("05.C", "ENGINE PLUGINS", null, el.plugins), panel("05.D", "STARTUP", null, el.startup))));
}

async function load() {
  const [distro, plugins, deps] = await withSkeleton(el.tools, "CHECKING INSTALLED TOOLS…",
    () => Promise.allSettled([api.distro(), api.plugins(), api.deps()]), 5);
  const show = (target, res, fn, title) => fill(target, res.status === "fulfilled" ? fn(res.value) : errorBox(res.reason, title));
  const names = Object.fromEntries((plugins.value || []).map((p) => [p.id, p.name]));
  show(el.tools, deps, (d) => toolGroups(d, names), "TOOL CHECK FAILED");
  show(el.slots, distro, slotsTable, "FORMATS UNAVAILABLE");
  show(el.startup, distro, startup, "STARTUP INFO UNAVAILABLE");
  show(el.plugins, plugins, (list) => list.map(pluginCard), "PLUGINS UNAVAILABLE");
  if (distro.status === "fulfilled") renderStats(distro.value, deps.value);
}

function renderStats(d, deps) {
  const slots = Object.values(d.slots || {});
  const bound = slots.filter((s) => s.main).length;
  const list = deps?.dependencies || [];
  el.stats.replaceChildren(
    stat("OS", String(d.os).toUpperCase(), `contract ${d.contract || "?"}`, "ok"),
    stat("TOOLS FOUND", deps ? `${list.filter((x) => x.available).length}/${list.length}` : "?", "all optional"),
    stat("FORMATS READY", `${bound}/${slots.length}`, "the rest need a tool", bound < slots.length ? "warn" : "ok"),
    stat("PLUGINS", fmtNum(d.plugins.length), "engines ViWo knows"),
    stat("STARTUP NOTES", fmtNum(d.problems.length), "mostly tools not installed", d.problems.length ? "warn" : "ok"));
}

function toolGroups(res, names) {
  const groups = {};
  res.dependencies.forEach((d) => (groups[d.category] ||= []).push(d));
  const order = Object.keys(groups).sort((a, b) => (a === "core" ? -1 : b === "core" ? 1 : a.localeCompare(b)));
  return [h("p", { class: "note first" }, "Everything here is optional. Without a tool ViWo still runs; it just skips the formats that tool handles."),
    h("table", { class: "tbl deps" },
      h("thead", {}, h("tr", {}, ["TOOL", "ENABLES", "STATUS", "HOW TO GET IT"].map((c) => h("th", {}, c)))),
      order.map((cat) => h("tbody", {},
        h("tr", { class: "grp" }, h("th", { colspan: 4, scope: "rowgroup" }, cat === "core" ? "ALL ENGINES" : (names[cat] || cat).toUpperCase(),
          h("span", { class: "dim" }, ` · ${groups[cat].filter((d) => d.available).length}/${groups[cat].length} installed`))),
        groups[cat].map((d) => h("tr", {},
          h("td", {}, h("b", {}, d.label)),
          h("td", { class: "small" }, ENABLES[d.id] || d.category),
          h("td", {}, d.available ? badge("INSTALLED", "ok") : badge(d.required ? "MISSING" : "OPTIONAL", d.required ? "err" : "mute")),
          h("td", { class: "mono small" }, d.available ? d.location || "on PATH" : d.hint))))))];
}

function slotsTable(d) {
  const rows = Object.values(d.slots || {});
  return [h("p", { class: "note first" }, "A slot is one job ViWo hands to a tool, such as opening .pck archives. READY: a tool is installed. ",
    "FALLBACK: the preferred tool is missing, a second one is used. NEEDS TOOL: that format is skipped until you install one (see 05.A)."),
  h("table", { class: "tbl slots" },
    h("thead", {}, h("tr", {}, ["FORMAT", "TOOL", "STATE"].map((c) => h("th", {}, c)))),
    h("tbody", {}, rows.map((s) => h("tr", {},
      h("td", {}, h("b", {}, slotText(s.slot_id)), h("small", { class: "mono dim block" }, s.slot_id, s.source !== "default" ? ` · set in ${s.source}` : "")),
      h("td", { class: "mono small" }, s.main || "—", s.spare ? h("small", { class: "dim block" }, `spare: ${s.spare}`) : null),
      h("td", {}, s.main ? badge(s.promoted ? "FALLBACK" : "READY", s.promoted ? "warn" : "ok") : badge("NEEDS TOOL", "mute"),
        s.reasons?.length ? h("details", { class: "reasons" }, h("summary", {}, "WHY"),
          h("ul", {}, s.reasons.map((r) => h("li", {}, r)))) : null)))))];
}

function pluginCard(p) {
  return h("article", { class: "card" },
    h("header", {}, h("b", {}, p.name), h("span", { class: "mono dim" }, `v${p.version}`)),
    h("div", { class: "row" }, badge(p.builtin ? "BUILT-IN" : "ADDED BY YOU", p.builtin ? "mute" : "warn"),
      p.tosSensitive ? badge("TOS-SENSITIVE", "warn") : null),
    p.slots.length ? h("p", { class: "small" }, "handles: ", p.slots.map(slotText).join(", ")) : null,
    p.options.length ? h("ul", { class: "small" }, p.options.map((o) => h("li", {}, o.label, " ",
      badge(o.kind.toUpperCase(), o.kind === "secret" ? "warn" : "mute")))) : h("p", { class: "dim small" }, "no options"));
}

function startup(d) {
  return h("div", {},
    h("div", { class: "kv" }, h("span", { class: "lbl" }, "STARTUP INI"), h("code", { class: "mono path" }, d.ini || "(built-in defaults)")),
    h("div", { class: "kv" }, h("span", { class: "lbl" }, "FEATURES"), h("div", { class: "row" }, (d.features || []).map((f) => badge(f.toUpperCase(), "mute")))),
    h("h4", { class: "sub-h" }, `// STARTUP NOTES (${d.problems.length})`),
    d.problems.length ? [h("p", { class: "note" }, "Most notes just say an optional tool is not installed; 05.A lists them by engine."),
      h("ul", { class: "problems mono" }, d.problems.map((p) => h("li", {}, p)))] : h("p", { class: "ok-text" }, "No startup notes."));
}

export default { mount, show: load };
