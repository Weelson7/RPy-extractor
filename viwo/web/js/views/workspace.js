// 02 WORKSPACE: extension groups (kept / trashed), group actions, retain-selected, clear trash.
import { api } from "../api.js";
import { h, btn, panel, badge, viewHead, empty, errorBox, toast, toastErr, confirmBox, busy, fmtNum, bus, emit, stat, goBtn, openBtn } from "../ui.js";
import { withSkeleton } from "../progress.js";

const S = { status: null, selected: new Set() };
const el = {};

function mount(root) {
  el.totals = h("div", { class: "stats" }, ["TYPES", "KEPT FILES", "IN TRASH", "SELECTED"].map((l) => stat(l, "…")));
  el.body = h("div", {});
  el.retain = btn("KEEP ONLY SELECTED", retain, "primary");
  el.clear = btn("CLEAR TRASH", clearTrash, "danger");
  root.append(
    viewHead("02", "WORKSPACE", "Your extracted files, grouped by file type. Trash a whole type you do not need; it stays recoverable until you delete it or clear the trash.",
      btn("REFRESH", (e) => busy(e.currentTarget, load), "ghost"),
      btn("OPEN FOLDER", () => (bus.ws?.path ? openBtn(bus.ws.path).click() : toast("No workspace yet.", "warn")), "ghost")),
    el.totals,
    el.panel = panel("02.A", "FILE TYPES", h("div", { class: "row" }, el.retain, el.clear), el.body));
  bus.addEventListener("workspace", (e) => { if (e.detail?.switched) S.status = null; if (!root.hidden) load(); });
}

async function load() {
  el.panel.classList.add("syncing");
  try {
    const status = await (S.status ? api.status() : withSkeleton(el.body, "READING WORKSPACE…", api.status, 6));
    S.status = status;
    const exts = new Set(status.allExtensions || []);
    S.selected = new Set([...S.selected].filter((e) => exts.has(e)));
    render();
  } catch (err) {
    el.body.replaceChildren(errorBox(err, "WORKSPACE UNAVAILABLE"));
  } finally {
    el.panel.classList.remove("syncing");
  }
}

function render() {
  const st = S.status;
  const exts = st.allExtensions || [];
  el.totals.replaceChildren(
    stat("TYPES", fmtNum(exts.length), "file extensions"), stat("KEPT FILES", fmtNum(st.totalKept), "", "ok"),
    stat("IN TRASH", fmtNum(st.totalTrashed), "recoverable", st.totalTrashed ? "warn" : ""), stat("SELECTED", fmtNum(S.selected.size), "tick types below"));
  el.retain.disabled = !S.selected.size;
  el.clear.disabled = !st.totalTrashed;
  if (!exts.length) {
    el.body.replaceChildren(empty("WORKSPACE EMPTY", "Nothing extracted here yet. Extract a game, or use SWITCH (top right) to open another workspace.",
      goBtn("#extract", "GO TO 01 EXTRACT")));
    return;
  }
  el.body.replaceChildren(h("table", { class: "tbl groups" },
    h("thead", {}, h("tr", {}, h("th", { class: "chk" }, selectAll(exts)), [["TYPE"], ["KEPT", "num"], ["IN TRASH", "num"], ["STATE"], ["ACTIONS", "num"]].map(([c, k]) => h("th", { class: k }, c)))),
    h("tbody", {}, exts.map(row))));
}

function selectAll(exts) {
  const all = exts.length > 0 && exts.every((e) => S.selected.has(e));
  return h("input", { type: "checkbox", "aria-label": "Select all types", checked: all,
    onchange: (e) => { S.selected = e.target.checked ? new Set(exts) : new Set(); render(); } });
}

function row(ext) {
  const kept = S.status.kept?.[ext] || 0;
  const trashed = S.status.trashed?.[ext] || 0;
  const state = kept && trashed ? badge("PARTLY TRASHED", "warn") : kept ? badge("KEPT", "ok") : badge("IN TRASH", "mute");
  const toggle = (e) => { e.target.checked ? S.selected.add(ext) : S.selected.delete(ext); render(); };
  return h("tr", { class: S.selected.has(ext) ? "sel" : "" },
    h("td", { class: "chk" }, h("input", { type: "checkbox", "aria-label": `Select .${ext}`, checked: S.selected.has(ext), onchange: toggle })),
    h("td", {}, h("b", { class: "mono ext-name" }, `.${ext}`)),
    h("td", { class: "mono num" }, fmtNum(kept)),
    h("td", { class: "mono num" }, fmtNum(trashed)),
    h("td", {}, state),
    h("td", {}, h("div", { class: "actions" },
      btn("TRASH", (e) => groupAction(e, "trash", ext), "sm ghost", { disabled: !kept, "aria-label": `Trash all .${ext}` }),
      btn("RESTORE", (e) => groupAction(e, "restore", ext), "sm ghost", { disabled: !trashed, "aria-label": `Restore all .${ext}` }),
      btn("DELETE", (e) => groupAction(e, "delete", ext), "sm danger", { disabled: !trashed, "aria-label": `Delete trashed .${ext} forever` }))));
}

async function groupAction(e, action, ext) {
  if (action === "delete" && !(await confirmBox("DELETE TRASHED GROUP",
    `Permanently delete every trashed .${ext} file? This cannot be undone.`, { ok: "DELETE FOREVER", danger: true }))) return;
  await busy(e.currentTarget, async () => {
    try {
      const res = await api.group(action, ext);
      toast(res.message || `.${ext}: ${action} done`, "ok");
    } catch (err) {
      toastErr(err);
    }
  });
  emit("workspace");
}

async function retain() {
  const keep = [...S.selected];
  const drop = (S.status.allExtensions || []).filter((x) => !S.selected.has(x) && S.status.kept?.[x]);
  if (!(await confirmBox("KEEP ONLY SELECTED TYPES", `Keep ${keep.map((x) => `.${x}`).join(" ")} and move the ${drop.length} other type(s) to the trash? You can restore them later.`, { ok: "KEEP ONLY THESE" }))) return;
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

export default { mount, show: load };
