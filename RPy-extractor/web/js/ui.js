// Shared UI helpers: DOM builder (text-only, never innerHTML), toasts, modal, formatting.

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

export const btn = (label, onclick, kind = "", extra = {}) =>
  h("button", { class: `btn ${kind}`, type: "button", onclick, ...extra }, label);

/** Panel with chamfered frame, "// idx" tag, title and optional header tools. */
export function panel(idx, title, tools, ...body) {
  return h("section", { class: "panel" },
    h("header", { class: "panel-h" }, h("span", { class: "idx" }, idx), h("h3", {}, title), h("div", { class: "tools" }, tools)),
    h("div", { class: "panel-b" }, body));
}

export const badge = (text, kind = "") => h("span", { class: `badge ${kind}` }, text);

export function meter(value, kind = "") {
  const pct = Math.max(0, Math.min(100, Math.round(Number(value || 0) * 100)));
  return h("div", { class: `meter ${kind}`, role: "img", "aria-label": `${pct} percent` }, h("i", { style: `width:${pct}%` }));
}

export function empty(title, text, ...actions) {
  return h("div", { class: "empty" }, h("b", {}, title), h("p", {}, text), actions.length ? h("div", { class: "row" }, actions) : null);
}

/** Error block that surfaces the server message, code and hint. */
export function errorBox(err, title = "ERROR") {
  return h("div", { class: "alert err", role: "alert" },
    h("b", {}, title, err.code ? ` // ${String(err.code).toUpperCase()}` : ""),
    h("p", {}, err.message || String(err)),
    err.hint ? h("p", { class: "hint" }, "HINT: ", err.hint) : null);
}

export function toast(message, kind = "info", detail = "") {
  const label = { ok: "OK", warn: "WARN", err: "ERROR", info: "SYS" }[kind] || "SYS";
  const box = h("div", { class: `toast ${kind}`, role: kind === "err" ? "alert" : null },
    h("b", {}, label), h("span", {}, message), detail ? h("small", {}, detail) : null);
  $("#toasts").append(box);
  setTimeout(() => box.classList.add("out"), kind === "err" ? 7000 : 4200);
  setTimeout(() => box.remove(), kind === "err" ? 7500 : 4700);
}

export const toastErr = (err, prefix = "") => toast(`${prefix}${err.message || err}`, "err", err.hint || "");

function trapTab(e, root) {
  const items = [...root.querySelectorAll("button, input, select, textarea, a[href]")].filter((n) => !n.disabled);
  if (!items.length) return;
  const first = items[0], last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

/** Styled modal. actions: [{label, value, kind, primary}]. Resolves {value, text}. */
export function modal({ title, body, actions, input, tag = "// SYS" }) {
  return new Promise((resolve) => {
    const prev = document.activeElement;
    const field = input ? h("input", { class: "input mono", value: input.value || "", "aria-label": input.label || title, spellcheck: "false" }) : null;
    const buttons = actions.map((a) => btn(a.label, () => close(a.value), a.kind || ""));
    const primary = actions.findIndex((a) => a.primary);
    const dlg = h("div", { class: "modal panel", role: "dialog", "aria-modal": "true", "aria-labelledby": "modal-t" },
      h("header", { class: "panel-h" }, h("span", { class: "idx" }, tag), h("h3", { id: "modal-t" }, title)),
      h("div", { class: "panel-b" }, body, input?.label ? h("label", { class: "lbl" }, input.label) : null, field),
      h("footer", { class: "modal-f" }, buttons));
    const back = h("div", { class: "backdrop", onmousedown: (e) => e.target === back && close(null) }, dlg);
    const onKey = (e) => {
      e.stopPropagation();
      if (e.key === "Escape") { e.preventDefault(); close(null); }
      else if (e.key === "Enter" && field && document.activeElement === field && primary >= 0) { e.preventDefault(); close(actions[primary].value); }
      else if (e.key === "Tab") trapTab(e, dlg);
    };
    function close(value) {
      document.removeEventListener("keydown", onKey, true);
      back.remove();
      prev?.focus?.();
      resolve({ value, text: field ? field.value : "" });
    }
    document.addEventListener("keydown", onKey, true);
    document.body.append(back);
    (field || buttons[primary] || buttons[0]).focus();
    field?.select();
  });
}

export async function confirmBox(title, message, { ok = "CONFIRM", danger = false } = {}) {
  const res = await modal({ title, tag: danger ? "// WARNING" : "// CONFIRM", body: h("p", {}, message),
    actions: [{ label: "CANCEL", value: false, kind: "ghost" }, { label: ok, value: true, kind: danger ? "danger" : "primary", primary: true }] });
  return res.value === true;
}

export async function promptBox(title, message, value = "", ok = "APPLY", label = "") {
  const res = await modal({ title, body: message ? h("p", {}, message) : null, input: { value, label },
    actions: [{ label: "CANCEL", value: false, kind: "ghost" }, { label: ok, value: true, kind: "primary", primary: true }] });
  return res.value ? res.text : null;
}

/** Disable a button while an async action runs. */
export async function busy(button, fn) {
  if (button) { button.disabled = true; button.classList.add("busy"); }
  try { return await fn(); } finally { if (button) { button.disabled = false; button.classList.remove("busy"); } }
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

export function pref(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(`viwo.${key}`);
    localStorage.setItem(`viwo.${key}`, value);
  } catch { /* storage unavailable: preferences are optional */ }
  return null;
}

/** Map a log line to a level class for console colouring. */
export function lineLevel(line, level = "") {
  const s = `${level} ${line}`.toLowerCase();
  if (/game folder changed|error|fail|refused/.test(s)) return "l-err";
  if (/warn|unavailable|skip/.test(s)) return "l-warn";
  if (/✓|complete|done|succeeded|success/.test(s)) return "l-ok";
  return "";
}

export function logLine(text, level = "") {
  return h("span", { class: `ln ${lineLevel(text, level)}` }, text, "\n");
}

/** Cross-view events: "workspace" (contents/path changed), "jobs" (job list changed). */
export const bus = new EventTarget();
export const emit = (type, detail) => bus.dispatchEvent(new CustomEvent(type, { detail }));

export function viewHead(idx, title, sub, ...tools) {
  return h("header", { class: "view-h" },
    h("div", {}, h("span", { class: "idx" }, `// ${idx}`), h("h2", {}, title), h("p", { class: "sub" }, sub)),
    h("div", { class: "row" }, tools));
}
