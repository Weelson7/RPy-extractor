// Workspace switcher: shows the active workspace, opens another existing folder, or converts a
// folder ViWo did not create into a workspace (doc 4.3).
import { api } from "./api.js";
import { h, badge, modal, toast, toastErr, emit } from "./ui.js";

/** Convert the folder after showing what moves; true when it became the active workspace. */
async function convert(path) {
  const plan = await api.adoptWorkspace(path);
  if (plan.refused) throw Object.assign(new Error(plan.refused), { hint: "pick a folder of your own files" });
  if (!plan.owned) {
    const what = `${plan.moves} of ${plan.files} file(s) move into ${plan.groups.length} group(s) by type (${plan.groups.slice(0, 8).join(", ")}${plan.groups.length > 8 ? ", …" : ""}).`;
    const ok = await modal({ title: "CONVERT INTO WORKSPACE", tag: "// WORKSPACE",
      body: [h("p", {}, what), h("p", { class: "note" }, "Each file's original path is recorded in the workspace's provenance; the folders the moves empty are removed. Nothing is deleted.")],
      actions: [{ label: "CANCEL", value: false, kind: "ghost" }, { label: "CONVERT", value: true, kind: "primary", primary: true }] });
    if (!ok.value) return false;
  }
  const done = await api.adoptWorkspace(path, true);
  toast(`Workspace: ${done.path}`, "ok", `${done.moved} file(s) moved into ${done.groups.length} group(s).`);
  return true;
}

async function busyChip(path, work, verb = "OPENING…") {
  const chip = document.getElementById("ws-btn"), label = document.getElementById("ws-path"), was = label.textContent;
  chip.dataset.state = "loading";
  chip.setAttribute("aria-busy", "true");
  chip.querySelector(".ws-edit").textContent = verb;
  label.textContent = `‎${path}‎`;
  try {
    if (await work()) emit("workspace", { switched: true });
    else label.textContent = was;
  } catch (err) {
    label.textContent = was;
    toastErr(err);
  } finally {
    delete chip.dataset.state;
    chip.querySelector(".ws-edit").textContent = "SWITCH";
    chip.removeAttribute("aria-busy");
  }
}

export async function openWorkspaceDialog() {
  let cur = { path: "", isDefault: false, owned: false };
  try { cur = await api.workspace(); } catch (err) { toastErr(err); }
  const body = [
    h("p", {}, "Extraction, sorting, groups and the merger all work on the active workspace. Open another existing folder to switch. CONVERT INTO WORKSPACE acts on the folder typed below: its files move into groups by type, nothing is deleted."),
    h("div", { class: "kv" }, h("span", { class: "lbl" }, "ACTIVE"), h("code", { class: "mono path" }, cur.path || "—"),
      h("div", { class: "row" }, cur.isDefault ? badge("DEFAULT", "mute") : null,
        cur.owned ? badge("VIWO WORKSPACE", "ok") : badge("NOT CREATED BY VIWO", "warn"))),
  ];
  const res = await modal({ title: "SWITCH WORKSPACE", tag: "// WORKSPACE", body,
    input: { value: cur.path, label: "FOLDER TO OPEN OR CONVERT", browse: true },
    actions: [{ label: "CANCEL", value: false, kind: "ghost" }, { label: "CONVERT INTO WORKSPACE", value: "convert", kind: "ghost" },
      { label: "OPEN", value: true, kind: "primary", primary: true }] });
  const path = res.text.trim();
  if (!res.value) return;
  if (!path) return toast("Enter a folder first.", "warn"); // never silent: nothing was done, and why
  if (res.value === "convert") return busyChip(path, () => convert(path), "CONVERTING…");
  if (path === cur.path) return toast("That folder is already the active workspace.", "info");
  return busyChip(path, async () => {
    const next = await api.setWorkspace(path);
    toast(`Workspace: ${next.path}`, "ok", next.owned ? "" : "Not created by ViWo: CONVERT INTO WORKSPACE makes it one; extraction refuses it until then unless it is empty.");
    return true;
  });
}
