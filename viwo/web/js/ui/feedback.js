// Feedback components: error blocks, toasts, modal dialogs, the BROWSE picker button.
import { api } from "../api.js";
import { h, $, busy } from "./dom.js";
import { btn } from "./components.js";

/** Error code -> [plain title, what to do next, optional [hash, view] link]. Every server code is covered. */
export const ERRORS = {
  offline: ["ViWo is not reachable", "Start ViWo again (viwo serve, or Start.py), then reload this page."],
  http: ["Unexpected server reply", "Reload the page. If it keeps happening, check the terminal ViWo runs in."],
  invalid_request: ["Check your input", "A path or option is not valid. Correct it and try again."],
  not_found: ["Not found", "The file or folder is gone, or the path has a typo. Check it, or refresh this view."],
  busy: ["Workspace busy", "Another job is using this workspace. Wait for it to finish, then try again.", ["#jobs", "JOBS"]],
  unavailable: ["Tool not installed", "A tool this needs is missing. Install it with one click in SYSTEM, then try again.", ["#system", "SYSTEM"]],
  needs_key: ["Encryption key needed", "These files are encrypted. Enter the key under ENGINE OPTIONS, then run again.", ["#extract", "EXTRACT"]],
  needs_decision: ["Your choice is needed", "Answer the question ViWo asked, then run again."],
  failed: ["It did not work", "The message above says why. The full log is in JOBS.", ["#jobs", "JOBS"]],
  cancelled: ["Cancelled", "Stopped on request. Run it again whenever you are ready."],
  refused: ["Refused for safety", "ViWo only writes into an empty folder or one it created, never into a game folder. Pick another folder."],
  internal: ["Something broke inside ViWo", "This is a bug, not your mistake. JOBS has the details; please report it.", ["#jobs", "JOBS"]],
};
const errInfo = (err) => ERRORS[err?.code] || ["Something went wrong", "Try again. The activity console at the bottom has details."];

/** Error block: what happened (server message + hint), in plain words, and what to do next. */
export function errorBox(err, title = "", next = "") {
  const [label, todo, link] = errInfo(err);
  return h("div", { class: "alert", "data-kind": "err", role: "alert" },
    h("b", {}, title && title !== label.toUpperCase() ? `${title} // ${label.toUpperCase()}` : label.toUpperCase()),
    h("p", {}, err.message || String(err)),
    err.hint ? h("p", { class: "hint" }, "HINT: ", err.hint) : null,
    h("p", { class: "next" }, h("b", {}, "NEXT"), next || todo, link ? [" ", h("a", { href: link[0] }, `Open ${link[1]} →`)] : null),
    err.code ? h("small", { class: "mono dim" }, `code: ${err.code}`) : null);
}

export function toast(message, kind = "info", detail = "") {
  const label = { ok: "DONE", warn: "NOTE", err: "ERROR", info: "INFO" }[kind] || "INFO";
  const box = h("div", { class: "toast", "data-kind": kind, role: kind === "err" ? "alert" : null },
    h("b", {}, label), h("span", {}, message), detail ? h("small", {}, detail) : null);
  $("#toasts").append(box);
  const life = kind === "err" ? 8000 : 4200;
  setTimeout(() => { box.dataset.state = "out"; }, life);
  setTimeout(() => box.remove(), life + 300);
  return box;
}

export const toastErr = (err, prefix = "") =>
  toast(`${prefix}${err.message || err}`, err.code === "cancelled" ? "warn" : "err", err.hint || errInfo(err)[1]);

export const openBtn = (path, label = "OPEN FOLDER", kind = "sm ghost") =>
  btn(label, () => api.openFolder(path).then(() => toast("Opened in your file manager.", "ok"), toastErr), kind);

function trapTab(e, root) {
  const items = [...root.querySelectorAll("button, input, select, textarea, a[href]")].filter((n) => !n.disabled);
  if (!items.length) return;
  const first = items[0], last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

/** BROWSE button: the server's native folder picker fills `field` (silent when cancelled). */
export function browseBtn(field, after = null, pick = (p) => api.browse(p).then((r) => r.path)) {
  return btn("BROWSE", (e) => busy(e.currentTarget, async () => {
    try { field.value = (await pick(field.value.trim())) || field.value; after?.(field.value); } catch (err) {
      if (!err.payload?.cancelled) toast("No folder picker on this computer: type or paste the path instead.", "warn", err.message);
    }
    field.focus();
  }), "ghost");
}

/** Modal dialog. actions: [{label, value, kind, primary}]. Resolves {value, text}. */
export function modal({ title, body, actions, input, tag = "// SYS" }) {
  return new Promise((resolve) => {
    const prev = document.activeElement;
    const field = input ? h("input", { class: "input mono grow", value: input.value || "", placeholder: input.placeholder || null, "aria-label": input.label || title, spellcheck: "false" }) : null;
    const buttons = actions.map((a) => btn(a.label, () => close(a.value), a.kind || ""));
    const primary = actions.findIndex((a) => a.primary);
    const dlg = h("div", { class: "modal panel", role: "dialog", "aria-modal": "true", "aria-labelledby": "modal-t" },
      h("header", { class: "panel-h" }, h("span", { class: "idx" }, tag), h("h3", { id: "modal-t" }, title)),
      h("div", { class: "panel-b" }, body, input?.label ? h("label", { class: "lbl" }, input.label) : null,
        input?.browse ? h("div", { class: "row" }, field, browseBtn(field)) : field),
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
    // a destructive confirm starts on CANCEL, so a stray Enter never deletes anything
    actions: [{ label: "CANCEL", value: false, kind: "ghost" }, { label: ok, value: true, kind: danger ? "danger" : "primary", primary: !danger }] });
  return res.value === true;
}

export async function promptBox(title, message, value = "", ok = "APPLY", label = "") {
  const res = await modal({ title, body: message ? h("p", {}, message) : null, input: { value, label },
    actions: [{ label: "CANCEL", value: false, kind: "ghost" }, { label: ok, value: true, kind: "primary", primary: true }] });
  return res.value ? res.text : null;
}
