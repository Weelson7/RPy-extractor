// Live job progress: stage rail, typed log ticker, counters parsed from events, job clock, warnings.
// Everything shown comes from the job's own event stream (/api/jobs + /api/jobs/<id>/events).
import { api } from "./api.js";
import { h, fill, logLine, emit } from "./ui.js";

const RM = window.matchMedia("(prefers-reduced-motion: reduce)");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const clock = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${(s % 60).toFixed(1).padStart(4, "0")}`;
const add = (n = 1) => (m, v) => v + (typeof n === "function" ? n(m) : n);

/**
 * Per job kind: the stages in execution order (none = one rail node per new stage key),
 * how an event maps to a stage, and the counters parsed from event messages:
 * [label, regex, (match, current) -> next, start value].
 */
const KINDS = {
  extract: {
    verb: "EXTRACTING",
    stages: ["prepare", "detect", "unpack", "export", "carve", "collect", "verify", "report"],
    counters: [
      ["PLUGINS", /^Selected plugin\(s\): (.+)/, (m) => m[1], "—"],
      ["ARCHIVES OK", /^OK [^:]+: \d+ file/, add()],
      ["ARCHIVES FAILED", /^FAILED /, add()],
      ["FILES UNPACKED", /^OK [^:]+: (\d+) file/, add((m) => Number(m[1]))],
      ["FILES CARVED", /^Carved (\d+) file/, add((m) => Number(m[1]))],
    ],
  },
  merge: {
    verb: "RENDERING",
    cycle: true,
    stages: ["probe", "encode", "write"],
    stageOf: (e) => ({ Probing: "probe", Encoding: "encode", Wrote: "write" })[e.message.split(" ")[0]] || "",
    counters: [
      ["VIDEOS WRITTEN", /^Wrote /, add()],
      ["SECONDS ENCODED", /^Encoding ([\d.]+) s/, add((m) => Number(m[1]))],
    ],
  },
  survey: {
    verb: "SURVEYING",
    stageOf: (e) => (e.stage === "survey" ? e.message.replace(/^Surveying /, "") : ""),
    counters: [["GAMES", /^Surveying /, add()]],
  },
};

/** Build a progress block for one job kind. start() before the blocking POST, finish() after it. */
export function jobProgress(kind, { logClass = "feed", onStatus = null } = {}) {
  const K = KINDS[kind];
  const el = {
    verb: h("span", { class: "lbl live" }, K.verb),
    stage: h("b", { class: "jp-stage" }),
    quiet: h("span", { class: "jp-quiet" }),
    clock: h("span", { class: "jp-clock mono", title: "elapsed (job clock)" }, "00:00.0"),
    rail: h("ol", { class: "jp-rail", "aria-label": "Stages" }),
    bar: h("div", { class: "scan-bar jp-bar", "aria-hidden": "true" }, h("i", {})),
    tick: h("div", { class: "jp-tick mono", "aria-hidden": "true" }),
    counts: h("div", { class: "jp-counts" }),
    warns: h("ul", { class: "jp-warns", "aria-label": "Warnings" }),
    sr: h("p", { class: "sr", "aria-live": "polite" }),
    log: h("pre", { class: `log ${logClass}` }),
  };
  const root = h("div", { class: "jp", "data-state": "idle" },
    h("div", { class: "jp-head" }, el.verb, el.stage, el.quiet, el.clock),
    el.rail, el.bar, el.tick, el.counts, el.warns, el.sr, el.log);
  let t = null;

  const elapsed = () => (t.final ?? (t.started ? Date.now() / 1000 - t.started : (Date.now() - t.t0) / 1000));
  const stageText = () => {
    if (!t.cur) return t.id ? "WAITING FOR FIRST EVENT" : "STARTING JOB";
    return `${t.cur}${K.cycle && t.total > 1 ? ` · ${Math.min(t.round, t.total)}/${t.total}` : ""}`.toUpperCase();
  };

  /** Screen readers hear stage changes and the outcome at once, log lines at most every 8 s. */
  function say(text, now = false) {
    if (!now && Date.now() - t.said < 8000) return;
    t.said = Date.now();
    el.sr.textContent = text;
  }

  function paintClock() {
    const secs = elapsed();
    el.clock.textContent = clock(secs);
    const idle = (Date.now() - t.lastEv) / 1000;
    el.quiet.textContent = !t.ended && t.cur && idle >= 5 ? `no new events for ${Math.floor(idle)} s — still working` : "";
    onStatus?.(t.ended ? `${el.verb.textContent} · ${el.stage.textContent} · ${t.n} events · ${secs.toFixed(1)}s`
      : `${K.verb} · ${stageText()} · ${t.n} events · ${Math.round(secs)}s`);
  }

  function railState(s, i) {
    if (s === t.cur) return !t.ended ? "on" : t.outcome === "ok" ? "done" : "fail";
    if (t.seen.has(s)) return "done";
    const furthest = Math.max(-1, ...[...t.seen].map((k) => t.order.indexOf(k)));
    return i < furthest || (t.ended && t.outcome === "ok") ? "skip" : "wait";
  }

  function paintRail() {
    const hide = Math.max(0, t.order.length - 10);
    const label = { on: "in progress", done: "done", skip: "no events reported", wait: "not reached", fail: "stopped here" };
    fill(el.rail, hide ? h("li", { class: "more", "data-s": "done" }, h("i", {}), h("span", {}, `+${hide} EARLIER`)) : null,
      t.order.slice(hide).map((s, j) => {
        const st = railState(s, j + hide);
        return h("li", { "data-s": st, style: `--i:${j}`, title: `${s}: ${label[st]}`, "aria-current": st === "on" ? "step" : null },
          h("i", {}), h("span", {}, s), h("span", { class: "sr" }, ` (${label[st]})`));
      }));
    el.stage.textContent = stageText();
  }

  function enter(s) {
    if (!s) return;
    if (!t.order.includes(s)) {
      if (K.stages) return;
      t.order.push(s);
    }
    if (K.cycle && t.order.indexOf(s) < t.order.indexOf(t.cur)) { t.round += 1; t.seen.clear(); }
    if (s === t.cur) return;
    t.cur = s;
    t.seen.add(s);
    say(`${K.verb.toLowerCase()}: ${s}`, true);
  }

  function paintCounts() {
    const rows = [...K.counters.map(([label]) => [label, t.counts[label]]), ["EVENTS", t.n], ["WARNINGS", t.warns.length]];
    for (const [label, value] of rows) {
      const text = typeof value === "number" && !Number.isInteger(value) ? value.toFixed(1) : String(value);
      let box = t.boxes[label];
      if (!box) {
        box = t.boxes[label] = h("div", { class: "jc" }, h("b", { class: "mono" }, text), h("span", {}, label));
        el.counts.append(box);
      } else if (box.firstChild.textContent !== text) {
        box.firstChild.textContent = text;
        box.classList.remove("bump");
        void box.offsetWidth; // restart the flash
        box.classList.add("bump");
      }
      box.classList.toggle("warn", label.includes("FAIL") || label === "WARNINGS" ? value > 0 : false);
      box.title = text;
    }
  }

  function ingest(events) {
    const stick = el.log.scrollHeight - el.log.scrollTop - el.log.clientHeight < 40;
    for (const e of events) {
      t.n += 1;
      t.lastEv = Date.now();
      el.log.append(logLine(e.line, e.level));
      if (e.level === "warn" || e.level === "error") t.warns.push(e.message);
      for (const [label, re, next] of K.counters) {
        const m = re.exec(e.message);
        if (m) t.counts[label] = next(m, t.counts[label]);
      }
      enter((K.stageOf || ((x) => x.stage))(e));
    }
    const last = events.slice(-3);
    t.lines = [...t.lines, ...last].slice(-3);
    fill(el.tick, t.lines.map((e, i) => i === t.lines.length - 1
      ? h("span", { class: `jp-line now ${e.level === "warn" ? "l-warn" : ""}`, style: `--n:${Math.min(90, e.message.length)}` }, e.message)
      : h("span", { class: "jp-line" }, e.message)));
    const w = t.warns;
    fill(el.warns, w.slice(-4).map((m) => h("li", {}, m)), w.length > 4 ? h("li", { class: "more" }, `+${w.length - 4} earlier warning(s) in the log`) : null);
    if (stick) el.log.scrollTop = el.log.scrollHeight;
    say(last[last.length - 1].message);
    paintRail();
    paintCounts();
  }

  async function tick(forceJobs = false) {
    if (t.busy) return;
    t.busy = true;
    try {
      if (!t.id || forceJobs || ++t.polls % 3 === 0) {
        const jobs = await api.jobs();
        const job = t.id ? jobs.find((j) => j.id === t.id) : jobs.filter((j) => j.kind === kind && !t.known.has(j.id)).pop();
        if (job && !t.id) { t.id = job.id; emit("jobs"); paintRail(); }
        if (job) { t.started = job.started; t.final = ["running", "queued"].includes(job.state) ? null : job.elapsed; }
      }
      if (t.id) {
        const page = await api.events(t.id, t.from);
        t.from = page.next;
        if (page.events.length) ingest(page.events);
      }
    } catch { /* keep polling; the blocking call reports failures */ } finally { t.busy = false; }
  }

  function stop() {
    if (!t) return;
    clearInterval(t.timer);
    clearInterval(t.clockTimer);
  }

  async function start({ total = 0 } = {}) {
    if (t) stop();
    const known = new Set((await api.jobs().catch(() => [])).map((j) => j.id));
    t = { known, total, id: null, from: 0, n: 0, polls: 0, round: 1, cur: "", seen: new Set(), order: [...(K.stages || [])],
      counts: Object.fromEntries(K.counters.map((c) => [c[0], c[3] ?? 0])), boxes: {}, warns: [], lines: [],
      t0: Date.now(), lastEv: Date.now(), said: 0, ended: false, busy: false };
    root.dataset.state = "running";
    el.verb.className = "lbl live";
    el.verb.textContent = K.verb;
    fill(el.counts);
    fill(el.warns);
    fill(el.log);
    fill(el.tick, h("span", { class: "jp-line now", style: "--n:24" }, "waiting for the job to start"));
    paintRail();
    paintCounts();
    paintClock();
    say(`${K.verb.toLowerCase()} started`, true);
    t.timer = setInterval(tick, 500);
    t.clockTimer = setInterval(paintClock, RM.matches ? 1000 : 100);
    tick();
  }

  /** Flush the last events, settle the rail and resolve once the end transition has played. */
  async function finish(outcome = "ok", note = "") {
    if (!t || t.ended) return;
    stop();
    while (t.busy) await sleep(40);
    await tick(true);
    t.ended = true;
    t.outcome = outcome;
    root.dataset.state = outcome === "ok" ? "done" : "fail";
    el.verb.className = `lbl ${outcome === "ok" ? "done" : "bad"}`;
    el.verb.textContent = { ok: "COMPLETE", fail: "FAILED", cancel: "CANCELLED" }[outcome] || "STOPPED";
    paintRail();
    if (note) el.stage.textContent = note;
    paintClock();
    say(`${el.verb.textContent.toLowerCase()}${note ? `: ${note}` : ""}`, true);
    if (!RM.matches) await sleep(450 + 70 * Math.min(10, t.order.length));
  }

  return { el: root, log: el.log, start, finish, stop, get id() { return t?.id || null; } };
}

/** Skeleton placeholder with a scanline, for short waits (detect, view loads, previews). */
export function skeleton(label, rows = 4) {
  return h("div", { class: "skel", role: "status" }, h("span", { class: "lbl live" }, label),
    Array.from({ length: rows }, (_, i) => h("i", { style: `--w:${[94, 72, 86, 58, 80][i % 5]}%` })));
}

/** Run `work`; if it takes longer than 150 ms, show a skeleton in `host` meanwhile (no flash on fast loads). */
export async function withSkeleton(host, label, work, rows = 4) {
  const timer = setTimeout(() => host.replaceChildren(skeleton(label, rows)), 150);
  try { return await work(); } finally { clearTimeout(timer); }
}
