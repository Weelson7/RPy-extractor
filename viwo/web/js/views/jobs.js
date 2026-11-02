// 04 JOBS: job registry with state badges, detail, live event stream and cancel.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, viewHead, empty, errorBox, toast, toastErr, logLine, fmtNum, emit, goBtn } from "../ui.js";

const STATE_KIND = { running: "live", queued: "warn", succeeded: "ok", failed: "err", cancelled: "mute" };
/** Job kind -> [name shown to people, view that runs it]. */
export const KIND = { extract: ["EXTRACTION", "#extract", "01"], survey: ["SURVEY", "#survey", "07"], merge: ["MERGER BUILD", "#merger", "06"],
  repack: ["PATCHED COPY", "#repack", "09"] };
const kindName = (k) => KIND[k]?.[0] || String(k).toUpperCase();
const when = (j) => `${new Date(j.started * 1000).toLocaleTimeString()} · ${Number(j.elapsed || 0).toFixed(1)} s`;
const human = (k) => k.replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase();
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
    viewHead("04", "JOBS", "Every extraction, survey, merger build and patched copy runs as a job. Pick one to read its log and result.",
      btn("REFRESH", () => refresh(), "ghost")),
    h("div", { class: "jobs-grid" },
      panel("04.A", "JOB REGISTRY", el.count, el.list),
      panel("04.B", "JOB DETAIL", el.cancel, el.head, h("h4", { class: "sub-h" }, "// LOG"), el.events)));
  renderDetailEmpty();
}

function renderDetailEmpty() {
  el.head.replaceChildren(empty("NO JOB SELECTED", "Pick a job on the left to read its log and result."));
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
    el.list.replaceChildren(empty("NO JOBS YET", "Jobs appear here when you extract, survey, build a merger video or a patched copy.",
      goBtn("#extract", "GO TO 01 EXTRACT")));
    return;
  }
  el.list.replaceChildren(...S.list.map((j) => h("button", {
    type: "button", class: "job", role: "listitem", "aria-current": j.id === S.sel ? "true" : null, onclick: () => pick(j.id),
    title: `job ${j.id}`,
  }, h("span", { class: "kind" }, kindName(j.kind)), stateBadge(j.state),
    h("span", { class: "mono dim small" }, when(j)), h("span", { class: "mono dim ev" }, `${fmtNum(j.events)} events`))));
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
  const rows = Object.entries(result).filter(([k, v]) => k !== "success" && (v === null || typeof v !== "object")).slice(0, 12);
  if (!rows.length) return null;
  return h("dl", { class: "facts" }, rows.map(([k, v]) => [h("dt", {}, human(k)), h("dd", { class: "mono" }, String(v))]));
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
      h("div", { class: "job-h" }, h("b", {}, kindName(job.kind)), stateBadge(job.state), h("span", { class: "mono dim small" }, when(job)),
        KIND[job.kind] ? goBtn(KIND[job.kind][1], `OPEN ${KIND[job.kind][2]} ${KIND[job.kind][0]} →`, "sm ghost") : null),
      h("p", { class: "mono dim small" }, `job id ${job.id}`),
      job.error ? errorBox(job.error, `${kindName(job.kind)} ${String(job.state).toUpperCase()}`) : null,
      facts(job.result));
    const stick = el.events.scrollHeight - el.events.scrollTop - el.events.clientHeight < 40;
    S.from = page.next;
    page.events.forEach((e) => el.events.append(logLine(e.line, e.level)));
    if (!el.events.childNodes.length && !live) el.events.append(h("span", { class: "ln dim" }, "// this job wrote no log lines\n"));
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
