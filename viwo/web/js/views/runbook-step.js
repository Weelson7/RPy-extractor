// RUNBOOKS: one step as a readable row (doc 19.2): what it does (the job kind and the tab that
// runs it), its target, its options as key/value with the run's values beside the {names}, and
// the step exactly as the file holds it, as JSON behind a toggle.
import { h } from "../ui.js";
import { tab } from "../registry.js";
import { KIND } from "./jobs.js";

/** The parameters that name what a step works on, in the order a step is read. */
const TARGETS = ["gamePath", "folder", "path", "targetKey", "pid", "name"];
const human = (k) => k.replace(/([a-z])([A-Z])/g, "$1 $2").toUpperCase();

/** A parameter as written ("{game}") and, when it names run values, what it becomes now. */
function shown(raw, vals, secret) {
  const text = typeof raw === "string" ? raw : JSON.stringify(raw);
  const now = text.replace(/\{([A-Za-z][A-Za-z0-9_]*)\}/g, (m, n) =>
    (secret.has(n) ? "<secret>" : n in vals ? vals[n] || "(not set yet)" : m));
  return h("dd", { class: "mono" }, text, now !== text ? h("span", { class: "dim" }, ` → ${now}`) : null);
}

/** The step as JSON, kept one click away (what EDIT changes). */
const raw = (s) => h("details", { class: "rb-json" }, h("summary", { class: "mono small" }, "JSON"),
  h("pre", { class: "log mini" }, JSON.stringify(s, null, 1)));

/** What a step does, its target and its options; `vals` the run's values, `secret` the names
 * of the secret inputs (their values never show). */
export function stepDetail(s, vals, secret = new Set()) {
  if (!s.do) return [h("span", {}, s.text), raw(s)];
  const params = Object.entries(s.with || {});
  const target = params.find(([k]) => TARGETS.includes(k));
  const [name, hash] = KIND[s.do] || [s.do.toUpperCase(), ""];
  return [h("span", {}, "Runs ", h("b", {}, name), hash ? h("span", { class: "dim" }, ` (as in ${tab(hash.slice(1))})`) : null),
    h("dl", { class: "facts" },
      target ? [h("dt", {}, `TARGET (${human(target[0])})`), shown(target[1], vals, secret)] : null,
      params.filter((p) => p !== target).map(([k, v]) => [h("dt", {}, human(k)), shown(v, vals, secret)]),
      params.length ? null : [h("dt", {}, "OPTIONS"), h("dd", { class: "dim" }, "none")]),
    raw(s)];
}
