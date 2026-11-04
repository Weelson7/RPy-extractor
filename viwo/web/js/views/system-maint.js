// 05.E MAINTENANCE: update check (only on click), diagnostics bundle, indexes update job.
import { code } from "../registry.js";
import { api } from "../api.js";
import { h, fill, btn, panel, badge, busy, toast, toastErr, openBtn, errorBox } from "../ui.js";
import { jobProgress } from "../progress.js";

const el = {};
const parent = (p) => String(p).replace(/[\\/][^\\/]*$/, "");

function line(label, info) {
  const fresh = info.latest && info.latest !== info.current;
  return h("div", { class: "kv" }, h("span", { class: "lbl" }, label),
    h("span", { class: "mono" }, `current ${info.current || "none"}`),
    h("div", { class: "row" }, fresh
      ? [badge(`NEW: ${info.latest}`, "warn"), info.url ? h("a", { href: info.url, target: "_blank", rel: "noopener" }, "release page →") : null]
      : badge(info.latest ? "UP TO DATE" : "NO RELEASE YET", info.latest ? "ok" : "mute")));
}

async function checkUpdates() {
  fill(el.updates, h("p", { class: "dim" }, "Asking GitHub…"));
  try {
    const res = await api.updates();
    fill(el.updates, line("VIWO", res.app || {}), line("INDEXES", res.indexes || {}));
  } catch (err) {
    fill(el.updates, h("p", { class: "warn-text" }, `offline: ${err.message}`), err.code !== "offline" ? errorBox(err, "UPDATE CHECK FAILED") : null);
  }
}

async function diag() {
  try {
    const res = await api.diag();
    fill(el.diag, h("div", { class: "kv" }, h("span", { class: "lbl" }, "BUNDLE"), h("code", { class: "mono path" }, res.path),
      h("div", { class: "row" }, openBtn(parent(res.path)))),
      h("p", { class: "note" }, "Attach this zip to a bug report. Logs, run records and tool versions; secrets stripped."));
    toast("Diagnostics bundle written.", "ok", res.path);
  } catch (err) {
    fill(el.diag, errorBox(err, "BUNDLE FAILED"));
    toastErr(err);
  }
}

async function updateIndexes() {
  if (el.busy) return;
  el.busy = true;
  el.idxBtn.disabled = true;
  el.prog = jobProgress("indexes", { logClass: "feed short" });
  fill(el.progHost, el.prog.el);
  el.progHost.hidden = false;
  await el.prog.start();
  try {
    const res = await api.updateIndexes();
    await el.prog.finish("ok", `INDEXES ${res.version || res.tag || ""} INSTALLED`.trim());
    fill(el.idx, h("p", { class: "ok-text" }, `Indexes ${res.version || res.tag || ""} installed${res.where ? ` into ${res.where}` : ""}.`));
    toast("Indexes updated.", "ok");
  } catch (err) {
    await el.prog.finish("fail", err.message);
    fill(el.idx, errorBox(err, "INDEXES NOT UPDATED", err.code === "offline" ? "No connection, or no release for this ViWo version yet." : ""));
    toastErr(err, "Indexes: ");
  } finally {
    el.busy = false;
    el.idxBtn.disabled = false;
  }
}

/** The panel; nothing here calls the network until a button is pressed. */
export function maintenancePanel() {
  el.updates = h("div", {}, h("p", { class: "dim" }, "Not checked. Nothing is called automatically."));
  el.diag = h("div", {});
  el.idx = h("div", {});
  el.progHost = h("div", { class: "install-prog", hidden: true });
  el.idxBtn = btn("UPDATE INDEXES", (e) => busy(e.currentTarget, updateIndexes), "");
  return panel(`${code("system")}.E`, "MAINTENANCE", null,
    h("div", { class: "maint" },
      h("div", { class: "maint-row" }, btn("CHECK FOR UPDATES", (e) => busy(e.currentTarget, checkUpdates), ""), h("span", { class: "small dim" }, "latest ViWo and indexes releases on GitHub"), el.updates),
      h("div", { class: "maint-row" }, btn("DIAGNOSTICS BUNDLE", (e) => busy(e.currentTarget, diag), ""), h("span", { class: "small dim" }, "zip of logs, run records and tool versions for a bug report"), el.diag),
      h("div", { class: "maint-row" }, el.idxBtn, h("span", { class: "small dim" }, "latest per-game indexes for this ViWo version, sha256 verified"), el.progHost, el.idx)));
}
