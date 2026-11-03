// Workspace switcher: shows the active workspace and opens another existing folder.
import { api } from "./api.js";
import { h, badge, modal, toast, toastErr, emit } from "./ui.js";

export async function openWorkspaceDialog() {
  let cur = { path: "", isDefault: false, owned: false };
  try { cur = await api.workspace(); } catch (err) { toastErr(err); }
  const body = [
    h("p", {}, "Extraction, sorting, groups and the merger all work on the active workspace. Open another existing folder to switch."),
    h("div", { class: "kv" }, h("span", { class: "lbl" }, "ACTIVE"), h("code", { class: "mono path" }, cur.path || "—"),
      h("div", { class: "row" }, cur.isDefault ? badge("DEFAULT", "mute") : null,
        cur.owned ? badge("VIWO WORKSPACE", "ok") : badge("NOT CREATED BY VIWO", "warn"))),
  ];
  const res = await modal({ title: "SWITCH WORKSPACE", tag: "// WORKSPACE", body,
    input: { value: cur.path, label: "FOLDER TO OPEN", browse: true },
    actions: [{ label: "CANCEL", value: false, kind: "ghost" }, { label: "OPEN", value: true, kind: "primary", primary: true }] });
  const path = res.text.trim();
  if (!res.value || !path || path === cur.path) return;
  const chip = document.getElementById("ws-btn"), label = document.getElementById("ws-path"), was = label.textContent;
  chip.dataset.state = "loading";
  chip.setAttribute("aria-busy", "true");
  chip.querySelector(".ws-edit").textContent = "OPENING…";
  label.textContent = `\u200e${path}\u200e`;
  try {
    const next = await api.setWorkspace(path);
    toast(`Workspace: ${next.path}`, "ok", next.owned ? "" : "Not created by ViWo: extraction will refuse it unless it is empty.");
    emit("workspace", { switched: true });
  } catch (err) {
    label.textContent = was;
    toastErr(err);
  } finally {
    delete chip.dataset.state;
    chip.querySelector(".ws-edit").textContent = "SWITCH";
    chip.removeAttribute("aria-busy");
  }
}
