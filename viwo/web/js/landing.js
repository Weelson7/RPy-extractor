// Landing: full-screen boot screen driven by the real preflight job (POST /api/preflight).
// One line per check/install event as it arrives, a determinate bar from the "(i/N)" and
// "X / Y" counts, a summary, then a hand-off into the app. Shown once per browser tab.
import { api } from "./api.js";
import { h, logLine, emit } from "./ui.js";

const RM = window.matchMedia("(prefers-reduced-motion: reduce)");
const FRAC = /(\d[\d,]*)\s*\/\s*(\d[\d,]*)/;
const num = (s) => Number(String(s).replace(/,/g, ""));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const MIN_HOLD = 1200;

const store = (set) => { try { if (set) sessionStorage.setItem("viwo-landed", "1"); return sessionStorage.getItem("viwo-landed"); } catch { return "1"; } };
/** Once per browser tab; when storage is unavailable the landing is skipped rather than shown on every reload. */
export const landingWanted = () => !store(false);

function logo() {
  const mark = document.querySelector(".brand .mark")?.cloneNode(true) || h("span", { class: "mark" }); // a real SVG node, not innerHTML
  return h("div", { class: "land-logo", "aria-hidden": "true" }, mark,
    h("span", { class: "word" }, "VIWO"), h("span", { class: "sub" }, "// VIDYA WORMHOLE"));
}

/** Progress model: checks fill the bar; each install owns one slice, downloads fill it. */
function progress(t, e) {
  const m = e.message;
  let hit;
  if ((hit = /^Checking .*\((\d+)\/(\d+)\): (.+)$/.exec(m))) {
    t.stage = "CHECKING TOOLS";
    t.pct = (num(hit[1]) / num(hit[2])) * 100;
    t.frac = `${hit[1]} / ${hit[2]}`;
    t.found += hit[3].startsWith("found") ? 1 : 0;
    t.missing += hit[3] === "missing" ? 1 : 0;
  } else if ((hit = /^Installing missing tools \((\d+)\/(\d+)\)/.exec(m))) {
    t.stage = "INSTALLING";
    t.slice = [num(hit[1]) - 1, num(hit[2])];
    t.pct = (t.slice[0] / t.slice[1]) * 100;
    t.frac = `${hit[1]} / ${hit[2]}`;
  } else if (t.slice && (hit = FRAC.exec(m)) && /^Downloading/.test(m)) {
    const part = Math.min(1, num(hit[1]) / Math.max(1, num(hit[2])));
    t.pct = ((t.slice[0] + part) / t.slice[1]) * 100;
    t.frac = `${m.replace(/^Downloading /, "").replace(/, KB:.*/, "")} · ${hit[1]} / ${hit[2]} KB`;
  } else if (/^Installed /.test(m)) t.installed += 1;
  else if (/^Could not install/.test(m)) t.failed += 1;
  else if (/^Ready: /.test(m)) { t.stage = "READY"; t.pct = 100; t.frac = ""; }
}

/** Show the landing, run the preflight, resolve with the report (or null on failure). */
export async function runLanding() {
  const el = {
    stage: h("b", { class: "land-stage" }, "STARTING"),
    frac: h("span", { class: "land-frac mono" }),
    bar: h("div", { class: "land-bar", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": "0" }, h("i", {})),
    lines: h("pre", { class: "land-lines log" }),
    sum: h("p", { class: "land-sum", "aria-live": "polite" }, "Checking the tools ViWo can use on this machine…"),
  };
  const root = h("div", { class: "landing", role: "dialog", "aria-modal": "true", "aria-label": "ViWo is starting" },
    h("div", { class: "land-box" }, logo(), h("div", { class: "land-head" }, el.stage, el.frac), el.bar, el.lines, el.sum),
    h("p", { class: "land-foot mono" }, "LOCAL-FIRST // 127.0.0.1 // THE GAME FOLDER IS NEVER WRITTEN"));
  document.body.append(root);
  const app = document.querySelector(".app");
  if (app) app.inert = true; // nothing behind the landing takes focus or clicks
  const t = { stage: "STARTING", pct: 0, frac: "", found: 0, missing: 0, installed: 0, failed: 0, slice: null,
    known: new Set((await api.jobs().catch(() => [])).map((j) => j.id)), id: null, from: 0, busy: false, n: 0 };
  const t0 = Date.now();
  const paint = () => {
    el.stage.textContent = t.stage;
    el.frac.textContent = t.frac;
    el.bar.classList.toggle("det", t.n > 0);
    el.bar.style.setProperty("--p", `${Math.round(t.pct)}%`);
    el.bar.setAttribute("aria-valuenow", String(Math.round(t.pct)));
  };
  const poll = async () => {
    if (t.busy) return;
    t.busy = true;
    try {
      if (!t.id) t.id = (await api.jobs()).filter((j) => j.kind === "preflight" && !t.known.has(j.id)).pop()?.id || null;
      if (t.id) {
        const page = await api.events(t.id, t.from);
        t.from = page.next;
        for (const e of page.events) {
          t.n += 1;
          progress(t, e);
          el.lines.append(logLine(e.message, e.level));
          while (el.lines.childElementCount > 14) el.lines.firstChild.remove();
        }
        if (page.events.length) paint();
      }
    } catch { /* the blocking call reports failures */ } finally { t.busy = false; }
  };
  const timer = setInterval(poll, 350);
  let report = null, failure = null;
  try { report = await api.preflight(); } catch (err) { failure = err; }
  clearInterval(timer);
  while (t.busy) await sleep(30);
  await poll();
  if (report) {
    t.stage = "READY"; t.pct = 100; t.frac = "";
    const failed = report.failed?.length ? `, ${report.failed.length} could not be installed (see 05 SYSTEM)` : "";
    const inst = report.installed.length ? `, ${report.installed.length} installed just now` : "";
    el.sum.textContent = (report.ready >= report.total ? `All ${report.total} tools ready` : `${report.ready}/${report.total} tools ready`) + inst + failed + ".";
  } else {
    t.stage = "CHECK FAILED"; t.pct = 100;
    el.sum.textContent = `The startup check did not finish: ${failure?.message || "unknown error"}. ViWo still runs; 05 SYSTEM shows what is missing.`;
    root.classList.add("bad");
  }
  paint();
  await sleep(Math.max(0, MIN_HOLD - (Date.now() - t0)));
  store(true);
  emit("preflight", report);
  root.classList.add("out");
  if (!RM.matches) await sleep(460);
  if (app) app.inert = false;
  root.remove();
  return report;
}
