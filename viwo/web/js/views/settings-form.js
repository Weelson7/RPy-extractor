// Form renderers for 11 SETTINGS: switches, plugin toggles, tool paths, options, slots.
import { api } from "../api.js";
import { h, add, badge, browseBtn, toggle } from "../ui.js";
import { slotText } from "./system.js";

const FEATURES = [
  ["extraction", "EXTRACTION", "01 EXTRACT, 07 SURVEY, 09 PATCHED COPY"],
  ["sorting", "SORTING", "02 WORKSPACE, 03 SORT, 08 CLEANUP"],
  ["merger", "MERGER", "06 MERGER (needs ffmpeg)"],
  ["capture", "RUNTIME CAPTURE (OPT-IN)", "10 CAPTURE: runs on any game; anti-cheat and online titles only produce warnings; you are responsible"],
];
const STARTUP = [
  ["auto_install", "AUTO-INSTALL TOOLS", "missing pinned tools are downloaded into third_party/ at startup"],
  ["strict_preflight", "STRICT PREFLIGHT", "viwo serve exits (code 4) when a plugin format has no tool; the web UI ignores it"],
];

export function featuresForm(startup, touch) {
  const has = (f) => startup.features.includes(f);
  const set = (f, on) => { startup.features = FEATURES.map(([k]) => k).filter((k) => (k === f ? on : has(k))); touch(); };
  return [
    h("p", { class: "note first" }, "Features switch whole parts of ViWo on or off. Capture is off until you opt in."),
    FEATURES.map(([k, t, hint]) => toggle(`feat-${k}`, t, hint, has(k), (on) => set(k, on))),
    h("h4", { class: "sub-h" }, "// STARTUP"),
    STARTUP.map(([k, t, hint]) => toggle(`st-${k}`, t, hint, Boolean(startup[k]), (on) => { startup[k] = on; touch(); })),
    h("div", { class: "kv" }, h("span", { class: "lbl" }, "OS / PROFILE"), h("code", { class: "mono" }, `${startup.os} / ${startup.profile}`),
      h("div", { class: "row" }, h("span", { class: "small dim" }, "set in the ini; informational"))),
  ];
}

export function pluginsForm(plugins, info, effective, touch) {
  const loaded = new Set(effective?.plugins || []);
  return [
    h("p", { class: "note first" }, "Every engine plugin ViWo found, built-in or dropped in. Off = never detects, never runs. GENERIC always stays on."),
    Object.keys(plugins).sort().map((id) => {
      const p = info?.[id] || { name: id };
      const hint = [p.engineType ? `engine ${p.engineType}` : "", p.custom ? "drop-in" : "", p.problem ? `problem: ${p.problem}` : ""].filter(Boolean).join(" · ");
      const row = toggle(`pl-${id}`, p.name || id, hint, id === "generic" ? true : plugins[id] !== false, (on) => { plugins[id] = on; touch(); }, id === "generic");
      add(row, p.tosSensitive ? badge("TOS-SENSITIVE", "warn") : null, loaded.has(id) ? badge("LOADED", "ok") : badge("NOT LOADED", "mute"));
      return row;
    }),
  ];
}

export function toolsForm(tools, touch) {
  return [
    h("p", { class: "note first" }, "Empty = automatic: the pinned copy in third_party/ or the tool on PATH. Set a path only to force one tool."),
    Object.keys(tools).sort().map((dep) => {
      const id = `tool-${dep}`;
      const input = h("input", { class: "input mono grow", id, value: tools[dep] || "", placeholder: "auto", spellcheck: "false",
        oninput: () => { tools[dep] = input.value.trim(); touch(); } });
      const browse = browseBtn(input, (path) => { tools[dep] = path; touch(); }, (p) => api.browseFile(p).then((r) => r.path));
      return h("div", { class: "kv" }, h("label", { class: "lbl", for: id }, dep.toUpperCase()), input, h("div", { class: "row" }, browse));
    }),
  ];
}

function optionInput(pid, opt, options, touch) {
  const cur = options[pid]?.[opt.key] ?? opt.default ?? "";
  const set = (v) => { (options[pid] ||= {})[opt.key] = v; touch(); };
  const id = `opt-${pid}-${opt.key}`;
  if (opt.kind === "bool") {
    return toggle(id, opt.label || opt.key, "", /^(on|true|yes|1)$/i.test(String(cur)), (on) => set(on ? "on" : "off"));
  }
  return h("div", { class: "kv" }, h("label", { class: "lbl", for: id }, (opt.label || opt.key).toUpperCase()),
    h("input", { class: "input mono grow", id, value: String(cur), spellcheck: "false", type: opt.kind === "int" ? "number" : "text", oninput: (e) => set(e.target.value) }));
}

export function optionsForm(options, plugins, touch) {
  const withOptions = plugins.filter((p) => p.options.some((o) => o.kind !== "secret"));
  if (!withOptions.length) return h("p", { class: "dim" }, "No loaded plugin has options that can live in the ini (secrets never do: they are asked per run).");
  return [
    h("p", { class: "note first" }, "Defaults for loaded plugins. Secrets (keys, passwords) are never stored here; 01 EXTRACT asks for them per run."),
    withOptions.map((p) => h("div", { class: "optgroup" }, h("h4", { class: "sub-h" }, `// ${p.name.toUpperCase()}`),
      p.options.filter((o) => o.kind !== "secret").map((o) => optionInput(p.id, o, options, touch)))),
  ];
}

export function slotsTable(slots, overrides) {
  const rows = Object.values(slots || {});
  return [
    h("p", { class: "note first" }, "Which tool is main and spare for each format. Read-only here: change them under [slots] in startup.ini, or install tools in 05 SYSTEM."),
    h("table", { class: "tbl slots" },
      h("thead", {}, h("tr", {}, ["FORMAT", "MAIN", "SPARE", "STATE"].map((c) => h("th", {}, c)))),
      h("tbody", {}, rows.map((s) => h("tr", {},
        h("td", {}, h("b", {}, slotText(s.slot_id)), h("small", { class: "mono dim block" }, s.slot_id, overrides?.[s.slot_id] ? " · set in the ini" : "")),
        h("td", { class: "mono small" }, s.main || "—"),
        h("td", { class: "mono small" }, s.spare || "—"),
        h("td", {}, s.main ? badge(s.promoted ? "FALLBACK" : "READY", s.promoted ? "warn" : "ok") : badge("NEEDS TOOL", "mute")))))),
  ];
}
