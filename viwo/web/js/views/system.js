// 05 SYSTEM: OS layer, slot bindings, plugins, dependencies, startup ini and problems.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, viewHead, errorBox, busy, fmtNum } from "../ui.js";
import { skeleton } from "../progress.js";

const el = {};

function mount(root) {
  el.stats = h("div", { class: "stats" });
  el.slots = h("div", {});
  el.plugins = h("div", { class: "cards" });
  el.deps = h("div", {});
  el.startup = h("div", {});
  root.append(
    viewHead("05", "SYSTEM", "How this ViWo install is wired: OS layer, backend slots, engine plugins and external tools.",
      btn("REFRESH", (e) => busy(e.currentTarget, load), "ghost")),
    el.stats,
    h("div", { class: "grid2 sys" },
      h("div", { class: "col" }, panel("05.A", "BACKEND SLOTS", null, el.slots), panel("05.D", "STARTUP", null, el.startup)),
      h("div", { class: "col" }, panel("05.B", "ENGINE PLUGINS", null, el.plugins), panel("05.C", "DEPENDENCIES", null, el.deps))));
}

async function load() {
  if (!el.stats.childElementCount) [el.slots, el.startup, el.plugins, el.deps].forEach((n) => n.replaceChildren(skeleton("PROBING INSTALL…", 4)));
  const [distro, plugins, deps] = await Promise.allSettled([api.distro(), api.plugins(), api.deps()]);
  const show = (target, res, fn, title) => fill(target, res.status === "fulfilled" ? fn(res.value) : errorBox(res.reason, title));
  show(el.slots, distro, slotsTable, "DISTRO UNAVAILABLE");
  show(el.startup, distro, startup, "DISTRO UNAVAILABLE");
  show(el.plugins, plugins, (list) => list.map(pluginCard), "PLUGINS UNAVAILABLE");
  show(el.deps, deps, depsTable, "DEPENDENCIES UNAVAILABLE");
  if (distro.status === "fulfilled") renderStats(distro.value, deps.value);
}

const stat = (label, value, kind = "") =>
  h("div", { class: `stat ${kind}` }, h("span", { class: "lbl" }, label), h("b", { class: "mono" }, value));

function renderStats(d, deps) {
  const slots = Object.values(d.slots || {});
  const bound = slots.filter((s) => s.main).length;
  const avail = deps ? deps.dependencies.filter((x) => x.available).length : 0;
  el.stats.replaceChildren(
    stat("OS LAYER", String(d.os).toUpperCase(), "ok"),
    stat("CONTRACT", String(d.contract || "?")),
    stat("PLUGINS", fmtNum(d.plugins.length)),
    stat("SLOTS BOUND", `${bound}/${slots.length}`, bound < slots.length ? "warn" : "ok"),
    stat("TOOLS FOUND", deps ? `${avail}/${deps.dependencies.length}` : "?"),
    stat("PROBLEMS", fmtNum(d.problems.length), d.problems.length ? "warn" : "ok"));
}

function slotsTable(d) {
  const rows = Object.values(d.slots || {});
  return h("table", { class: "tbl slots" },
    h("thead", {}, h("tr", {}, ["SLOT", "MAIN", "SPARE", "STATE"].map((c) => h("th", {}, c)))),
    h("tbody", {}, rows.map((s) => h("tr", {},
      h("td", {}, h("b", { class: "mono" }, s.slot_id), h("small", { class: "dim block" }, `source: ${s.source}`)),
      h("td", { class: "mono" }, s.main || "—"),
      h("td", { class: "mono" }, s.spare || "—"),
      h("td", {}, s.main ? badge(s.promoted ? "PROMOTED" : "BOUND", s.promoted ? "warn" : "ok") : badge("UNBOUND", "err"),
        s.reasons?.length ? h("details", { class: "reasons" }, h("summary", {}, `${s.reasons.length} NOTE(S)`),
          h("ul", {}, s.reasons.map((r) => h("li", {}, r)))) : null)))));
}

function pluginCard(p) {
  return h("article", { class: "card" },
    h("header", {}, h("b", {}, p.name), h("span", { class: "mono dim" }, `${p.id} · v${p.version}`)),
    h("div", { class: "row" }, badge(p.engineType.toUpperCase()), badge(p.builtin ? "BUILT-IN" : "USER", p.builtin ? "mute" : "warn"),
      p.tosSensitive ? badge("TOS-SENSITIVE", "warn") : null),
    p.slots.length ? h("p", { class: "mono small" }, "slots: ", p.slots.join(", ")) : null,
    p.options.length ? h("ul", { class: "small" }, p.options.map((o) => h("li", {}, h("code", { class: "mono" }, o.key), ` ${o.label} `,
      badge(o.kind.toUpperCase(), o.kind === "secret" ? "warn" : "mute")))) : h("p", { class: "dim small" }, "no options"));
}

function depsTable(res) {
  return h("table", { class: "tbl deps" },
    h("thead", {}, h("tr", {}, ["TOOL", "FOR", "STATUS", "LOCATION / HINT"].map((c) => h("th", {}, c)))),
    h("tbody", {}, res.dependencies.map((d) => h("tr", {},
      h("td", {}, h("b", {}, d.label)),
      h("td", { class: "mono small" }, `${d.category}${d.required ? " · required" : ""}`),
      h("td", {}, d.available ? badge("FOUND", "ok") : badge(d.required ? "MISSING" : "ABSENT", d.required ? "err" : "warn")),
      h("td", { class: "mono small" }, d.available ? d.location || "on PATH" : d.hint)))));
}

function startup(d) {
  return h("div", {},
    h("div", { class: "kv" }, h("span", { class: "lbl" }, "STARTUP INI"), h("code", { class: "mono path" }, d.ini || "(defaults)")),
    h("div", { class: "kv" }, h("span", { class: "lbl" }, "FEATURES"), h("div", { class: "row" }, (d.features || []).map((f) => badge(f.toUpperCase(), "mute")))),
    h("div", { class: "kv" }, h("span", { class: "lbl" }, "PLUGINS ON"), h("div", { class: "row" }, d.plugins.map((p) => badge(p.toUpperCase(), "mute")))),
    h("h4", { class: "sub-h" }, `// PROBLEMS (${d.problems.length})`),
    d.problems.length ? h("ul", { class: "problems mono" }, d.problems.map((p) => h("li", {}, p))) : h("p", { class: "ok-text" }, "No startup problems."));
}

export default { mount, show: load };
