// 04 JOBS: job registry with state badges, detail, live event stream and cancel.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, viewHead, empty, errorBox, toast, toastErr, logLine, fmtNum, emit } from "../ui.js";

const STATE_KIND = { running: "live", queued: "warn", succeeded: "ok", failed: "err", cancelled: "mute" };
const S = { list: [], sel: null, from: 0, timer: 0, busy: false };
const el = {};

export const stateBadge = (state) => badge(String(state).toUpperCase(), STATE_KIND[state] || "");

function mount(root) {
  el.list = h("div", { class: "joblist", role: "list" });
  el.head = h("div", {});
  el.events = h("pre", { class: "log events" });
  el.cancel = btn("CANCEL JOB", cancel, "danger", { hidden: true });
  el.count = h("span", { class: "mono dim" });
  root.append(
    viewHead("04", "JOBS", "Extractions and long operations run as jobs. Each keeps its own event stream and result.",
      btn("REFRESH", () => refresh(), "ghost")),
    h("div", { class: "jobs-grid" },
      panel("04.A", "JOB REGISTRY", el.count, el.list),
      panel("04.B", "JOB DETAIL", el.cancel, el.head, h("h4", { class: "sub-h" }, "// EVENT STREAM"), el.events)));
  renderDetailEmpty();
}

function renderDetailEmpty() {
  el.head.replaceChildren(empty("NO JOB SELECTED", "Pick a job on the left to inspect its events and result."));
  el.events.replaceChildren();
  el.cancel.hidden = true;
}

async function refresh() {
  if (S.busy) return;
  S.busy = true;
  try {
    S.list = (await api.jobs()).slice().reverse();
    renderList();
    if (S.sel) await refreshDetail();
  } catch (err) {
    el.list.replaceChildren(errorBox(err, "JOBS UNAVAILABLE"));
  } finally {
    S.busy = false;
  }
}

function renderList() {
  el.count.textContent = `${S.list.length} TOTAL`;
  if (!S.list.length) {
    el.list.replaceChildren(empty("NO JOBS YET", "Jobs appear here when you run an extraction.",
      h("a", { class: "btn primary", href: "#extract" }, "GO TO 01 EXTRACT")));
    return;
  }
  el.list.replaceChildren(...S.list.map((j) => h("button", {
    type: "button", class: "job", role: "listitem", "aria-current": j.id === S.sel ? "true" : null, onclick: () => pick(j.id),
  }, h("span", { class: "kind" }, String(j.kind).toUpperCase()), stateBadge(j.state),
    h("code", { class: "mono dim" }, j.id), h("span", { class: "mono dim ev" }, `${fmtNum(j.events)} EV`))));
}

function pick(id) {
  S.sel = id;
  S.from = 0;
  el.events.replaceChildren();
  renderList();
  refreshDetail();
}

function facts(result) {
  if (!result || typeof result !== "object") return null;
  const rows = Object.entries(result).filter(([, v]) => v === null || typeof v !== "object").slice(0, 12);
  if (!rows.length) return null;
  return h("dl", { class: "facts" }, rows.map(([k, v]) => [h("dt", {}, k), h("dd", { class: "mono" }, String(v))]));
}

async function refreshDetail() {
  const id = S.sel;
  try {
    const job = await api.job(id);
    const page = await api.events(id, S.from);
    if (id !== S.sel) return;
    const live = job.state === "running" || job.state === "queued";
    el.cancel.hidden = !live;
    fill(el.head,
      h("div", { class: "job-h" }, h("b", {}, String(job.kind).toUpperCase()), stateBadge(job.state), h("code", { class: "mono" }, job.id)),
      job.error ? errorBox(job.error, `JOB ${String(job.state).toUpperCase()}`) : null,
      facts(job.result));
    const stick = el.events.scrollHeight - el.events.scrollTop - el.events.clientHeight < 40;
    S.from = page.next;
    page.events.forEach((e) => el.events.append(logLine(e.line, e.level)));
    if (!el.events.childNodes.length && !live) el.events.append(h("span", { class: "ln dim" }, "// no events recorded\n"));
    if (stick) el.events.scrollTop = el.events.scrollHeight;
  } catch (err) {
    el.head.replaceChildren(errorBox(err, "JOB UNAVAILABLE"));
  }
}

async function cancel() {
  if (!S.sel) return;
  try {
    await api.cancel(S.sel);
    toast("Cancellation requested — the job stops at its next checkpoint.", "warn");
    emit("jobs");
    refresh();
  } catch (err) { toastErr(err); }
}

function show() {
  refresh();
  clearInterval(S.timer);
  S.timer = setInterval(() => { if (!document.hidden) refresh(); }, 2000);
}

function hide() {
  clearInterval(S.timer);
}

export default { mount, show, hide };
