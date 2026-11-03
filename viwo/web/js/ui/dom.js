// DOM layer of the component library: element builder (text-only, never innerHTML), fills,
// preferences, formatting, the cross-view event bus. Views never touch `.style` or classes for
// visual state: `cssVar` and `state` are the only doors, and they live here.

/** Build an element. Strings become text nodes, so server data is never parsed as HTML. */
export function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k in el && typeof v !== "string") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  el.append(...kids.flat(9).filter((c) => c != null && c !== false).map((c) => (c instanceof Node ? c : String(c))));
  return el;
}

export const $ = (sel, root = document) => root.querySelector(sel);

/** replaceChildren that flattens arrays and skips null/false. */
export function fill(node, ...kids) {
  node.replaceChildren(...kids.flat(9).filter((k) => k != null && k !== false));
  return node;
}

/** append that skips null/false (a raw `node.append(null)` renders the word "null"). */
export function add(node, ...kids) {
  node.append(...kids.flat(9).filter((k) => k != null && k !== false));
  return node;
}

/** Numeric visual input for a component (progress, stagger, proportion): a CSS custom property. */
export const cssVar = (el, name, value) => { el.style.setProperty(`--${name}`, String(value)); return el; };
/** Stagger index for reveal animations (0..8). */
export const stagger = (el, i) => cssVar(el, "i", Math.min(Number(i) || 0, 8));
/** Visual state of a component: `data-state` (idle | running | done | fail | on | off ...). */
export const state = (el, value) => { el.dataset.state = value; return el; };

/** Disable a button while an async action runs. */
export async function busy(button, fn) {
  if (button) { button.disabled = true; button.dataset.busy = "1"; }
  try { return await fn(); } finally { if (button) { button.disabled = false; delete button.dataset.busy; } }
}

export function fmtBytes(n) {
  const v = Number(n) || 0;
  if (v < 1024) return `${v} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let x = v / 1024, i = 0;
  while (x >= 1024 && i < units.length - 1) { x /= 1024; i += 1; }
  return `${x.toFixed(x < 10 ? 1 : 0)} ${units[i]}`;
}

export const fmtNum = (n) => Number(n || 0).toLocaleString("en-US");
export const pad = (n, w = 2) => String(n).padStart(w, "0");
/** Whole percent, never zero-padded: 0.4 -> "40%". */
export const pct = (v) => `${Math.round(Number(v || 0) * 100)}%`;

export function pref(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(`viwo.${key}`);
    localStorage.setItem(`viwo.${key}`, value);
  } catch { /* storage unavailable: preferences are optional */ }
  return null;
}

/** Cross-view events: "workspace" (contents/path changed), "jobs" (job list changed), "preflight". */
export const bus = new EventTarget();
export const emit = (type, detail) => bus.dispatchEvent(new CustomEvent(type, { detail }));
