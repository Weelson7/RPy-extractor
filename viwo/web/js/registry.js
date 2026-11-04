// UI registry: views and panels are contributions. Core views register themselves at import;
// plugin add-ons (served through /api/ui-modules) register more, or override by id.
const VIEWS = new Map();
const PANELS = new Map();
const byOrder = (a, b) => a.order - b.order || a.id.localeCompare(b.id);

/** The three arms; each view belongs to one (or to "global": the strip above everything). */
export const ARMS = [
  { id: "static", title: "STATIC", subtitle: "the game is not running" },
  { id: "dynamic", title: "DYNAMIC", subtitle: "the game is running" },
  { id: "patching", title: "PATCHING", subtitle: "you change its content" },
];

/** Register a view: {id, arm, order, title, subtitle, mount(root), show?(), hide?()}. */
export function registerView(view, { override = false } = {}) {
  if (!view?.id || typeof view.mount !== "function") throw new Error("registerView: id and mount are required");
  if (VIEWS.has(view.id) && !override) throw new Error(`view "${view.id}" exists; pass {override: true} to replace it`);
  VIEWS.set(view.id, { order: 1000, title: view.id.toUpperCase(), subtitle: "", arm: "static", ...view });
  return view;
}

/** Register a panel inside a view: {id, order, render(ctx) -> Node}; views append them at mount. */
export function registerPanel(viewId, panel, { override = false } = {}) {
  if (!panel?.id || typeof panel.render !== "function") throw new Error("registerPanel: id and render are required");
  const list = PANELS.get(viewId) || new Map();
  if (list.has(panel.id) && !override) throw new Error(`panel "${viewId}/${panel.id}" exists; pass {override: true} to replace it`);
  list.set(panel.id, { order: 1000, ...panel });
  PANELS.set(viewId, list);
  return panel;
}

export const views = () => [...VIEWS.values()].sort(byOrder);

/**
 * A view's tab code, computed from its arm and its place in it (never written by a view):
 * S0, S1… in STATIC, D0… in DYNAMIC, P0… in PATCHING (the arm home is 0), 00, 01… for the global
 * strip (SYSTEM, JOBS, SETTINGS). Add-on views and reordering renumber everything by themselves.
 */
export function code(id) {
  const v = VIEWS.get(id);
  if (!v) return "";
  const i = armViews(v.arm).findIndex((x) => x.id === id);
  return v.arm === "global" ? String(i).padStart(2, "0") : `${v.arm[0].toUpperCase()}${i}`;
}

/** "S7 ANALYSIS": how prose names a tab, from the live numbering. */
export const tab = (id) => (VIEWS.get(id) ? `${code(id)} ${VIEWS.get(id).title}` : id.toUpperCase());
export const view = (id) => VIEWS.get(id) || null;
export const armViews = (arm) => views().filter((v) => v.arm === arm);
export const panels = (viewId) => [...(PANELS.get(viewId)?.values() || [])].sort(byOrder);

/** Render the add-on panels of a view (each render error is isolated and reported). */
export function addonPanels(viewId, ctx = {}) {
  return panels(viewId).map((p) => {
    try { return p.render(ctx); } catch (err) { console.error(`panel ${viewId}/${p.id} failed`, err); return null; }
  }).filter(Boolean);
}

/**
 * Load plugin UI modules: GET /api/ui-modules -> {modules: [{plugin, url}]}; each module exports
 * `default function install({registry, api, ui})`. A missing route or a broken module never
 * blocks the app: the failure is logged and the module skipped.
 */
export async function loadPluginModules(api, ui) {
  let modules = [];
  try { modules = (await api.uiModules()).modules || []; } catch { return []; }
  const loaded = [];
  for (const m of modules) {
    try {
      const mod = await import(m.url);
      await mod.default?.({ registry: { registerView, registerPanel, views, panels }, api, ui, plugin: m.plugin });
      loaded.push(m.plugin);
    } catch (err) { console.error(`UI module of plugin ${m.plugin} failed to load`, err); ui.toast?.(`The UI add-on of plugin ${m.plugin} failed to load: ${err.message || err}`, "warn"); }
  }
  return loaded;
}
