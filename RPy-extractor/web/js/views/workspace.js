// 02 WORKSPACE: extension groups (kept / trashed), group actions, retain-selected, clear trash.
import { api } from "../api.js";
import { h, btn, panel, badge, viewHead, empty, errorBox, toast, toastErr, confirmBox, busy, fmtNum, bus, emit } from "../ui.js";

const S = { status: null, selected: new Set(), path: "" };
const el = {};

function mount(root) {
  el.totals = h("div", { class: "stats" });
  el.body = h("div", {});
  el.retain = btn("RETAIN SELECTED", retain, "primary");
  el.clear = btn("CLEAR TRASH", clearTrash, "danger");
  root.append(
    viewHead("02", "WORKSPACE", "Extracted files are grouped by extension. Trash is reversible until you delete or clear it.",
      btn("REFRESH", (e) => busy(e.currentTarget, load), "ghost"),
      btn("OPEN FOLDER", openFolder, "ghost")),
    el.totals,
    panel("02.A", "EXTENSION GROUPS", h("div", { class: "row" }, el.retain, el.clear), el.body));
  bus.addEventListener("workspace", () => { if (!root.hidden) load(); });
}

async function load() {
  try {
    const [status, win] = await Promise.all([api.status(), api.assets(0, 1)]);
    S.status = status;
    S.path = win.assetPath || "";
    const exts = new Set(status.allExtensions || []);
    S.selected = new Set([...S.selected].filter((e) => exts.has(e)));
    render();
  } catch (err) {
    el.body.replaceChildren(errorBox(err, "WORKSPACE UNAVAILABLE"));
  }
}

function render() {
  const st = S.status;
  const exts = st.allExtensions || [];
  el.totals.replaceChildren(
    stat("GROUPS", fmtNum(exts.length)), stat("KEPT FILES", fmtNum(st.totalKept), "ok"),
    stat("IN TRASH", fmtNum(st.totalTrashed), st.totalTrashed ? "warn" : ""), stat("SELECTED", fmtNum(S.selected.size)));
  el.retain.disabled = !S.selected.size;
  el.clear.disabled = !st.totalTrashed;
  if (!exts.length) {
    el.body.replaceChildren(empty("WORKSPACE EMPTY", "No extracted groups yet. Run an extraction to fill this workspace.",
      h("a", { class: "btn primary", href: "#extract" }, "GO TO 01 EXTRACT")));
    return;
  }
  el.body.replaceChildren(h("table", { class: "tbl groups" },
    h("thead", {}, h("tr", {}, h("th", { class: "chk" }, selectAll(exts)), ["EXTENSION", "KEPT", "TRASHED", "STATE", "ACTIONS"].map((c) => h("th", {}, c)))),
    h("tbody", {}, exts.map(row))));
}

const stat = (label, value, kind = "") =>
  h("div", { class: `stat ${kind}` }, h("span", { class: "lbl" }, label), h("b", { class: "mono" }, value));

function selectAll(exts) {
  const all = exts.length > 0 && exts.every((e) => S.selected.has(e));
  return h("input", { type: "checkbox", "aria-label": "Select all groups", checked: all,
    onchange: (e) => { S.selected = e.target.checked ? new Set(exts) : new Set(); render(); } });
}

function row(ext) {
  const kept = S.status.kept?.[ext] || 0;
  const trashed = S.status.trashed?.[ext] || 0;
  const state = kept && trashed ? badge("SPLIT", "warn") : kept ? badge("KEPT", "ok") : badge("TRASHED", "err");
  const toggle = (e) => { e.target.checked ? S.selected.add(ext) : S.selected.delete(ext); render(); };
  return h("tr", { class: S.selected.has(ext) ? "sel" : "" },
    h("td", { class: "chk" }, h("input", { type: "checkbox", "aria-label": `Select .${ext}`, checked: S.selected.has(ext), onchange: toggle })),
    h("td", {}, h("b", { class: "mono ext-name" }, `.${ext}`)),
    h("td", { class: "mono num" }, fmtNum(kept)),
    h("td", { class: "mono num" }, fmtNum(trashed)),
    h("td", {}, state),
    h("td", { class: "actions" },
      btn("TRASH", (e) => groupAction(e, "trash", ext), "sm ghost", { disabled: !kept }),
      btn("RESTORE", (e) => groupAction(e, "restore", ext), "sm ghost", { disabled: !trashed }),
      btn("DELETE", (e) => groupAction(e, "delete", ext), "sm danger", { disabled: !trashed })));
}

async function groupAction(e, action, ext) {
  if (action === "delete" && !(await confirmBox("DELETE TRASHED GROUP",
    `Permanently delete every trashed .${ext} file? This cannot be undone.`, { ok: "DELETE FOREVER", danger: true }))) return;
  await busy(e.currentTarget, async () => {
    try {
      const res = await api.group(action, ext);
      toast(res.message || `.${ext}: ${action} done`, "ok");
    } catch (err) {
      toastErr(err, err.code === "busy" ? "Workspace busy: " : "");
    }
  });
  emit("workspace");
}

async function retain() {
  const keep = [...S.selected];
  const drop = (S.status.allExtensions || []).filter((x) => !S.selected.has(x) && S.status.kept?.[x]);
  if (!(await confirmBox("RETAIN SELECTED GROUPS", `Keep ${keep.map((x) => `.${x}`).join(" ")} and move ${drop.length} other group(s) to trash? You can restore them later.`, { ok: "RETAIN" }))) return;
  try {
    const res = await api.keepSelected(keep);
    toast(res.message || "Groups updated.", "ok");
  } catch (err) { toastErr(err); }
  emit("workspace");
}

async function clearTrash() {
  if (!(await confirmBox("CLEAR TRASH", `Permanently delete all ${fmtNum(S.status.totalTrashed)} trashed file(s)? This cannot be undone.`,
    { ok: "CLEAR FOREVER", danger: true }))) return;
  try {
    await api.clearTrash();
    toast("Trash cleared.", "ok");
  } catch (err) { toastErr(err); }
  emit("workspace");
}

function openFolder() {
  if (!S.path) return toast("No workspace yet.", "warn");
  api.openFolder(S.path).then(() => toast("Opened in file manager.", "ok"), toastErr);
}

export default { mount, show: load };
