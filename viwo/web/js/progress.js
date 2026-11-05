// Live job progress: stage rail, typed log ticker, counters parsed from events, job clock, warnings.
// Everything shown comes from the job's own event stream (/api/jobs + /api/jobs/<id>/events).
import { api } from "./api.js";
import { h, fill, logLine, emit, cssVar, rail, toast, toastErr } from "./ui.js";

const RM = window.matchMedia("(prefers-reduced-motion: reduce)");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const clock = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${(s % 60).toFixed(1).padStart(4, "0")}`;
const add = (n = 1) => (m, v) => v + (typeof n === "function" ? n(m) : n);
const num = (s) => Number(String(s).replace(/,/g, ""));
const fmt = (n) => n.toLocaleString("en-US");
/** Real progress inside a message: "Decoded files: 300 / 4,100", "x.wad: 1000/3109 lumps". */
const FRAC = /(?<![\w./])(\d[\d,]*)\s*\/\s*(\d[\d,]*)(?![\w./])/;
/** Throttled running counts with no total: "Scanned files: 12,400 (9,812 collected)". */
const COUNT = /^[A-Z][\w -]*files: [\d,]+/;

/**
 * Per job kind: the stages in execution order (none = one rail node per new stage key),
 * how an event maps to a stage, and the counters parsed from event messages:
 * [label, regex, (match, current) -> next, start value].
 */
const KINDS = {
  extract: {
    verb: "EXTRACTING",
    stages: ["prepare", "detect", "unpack", "export", "carve", "collect", "decode", "verify", "report"],
    counters: [
      ["PLUGINS", /^Selected plugin\(s\): (.+)/, (m) => m[1], "—"],
      ["FILES SCANNED", /^Scanned files: ([\d,]+)/, (m) => num(m[1])],
      ["FILES DECODED", /^Decoded files: ([\d,]+)/, (m) => num(m[1])],
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
    cycle: true, // the steps repeat for every game
    stages: ["scan", "identify", "probe", "carve", "decode"],
    stageOf: (e) => ({ Scanning: "scan", Identified: "identify", Probing: "probe", Carving: "carve", Decoders: "decode" })[e.message.split(" ")[0]] || "",
    counters: [["GAMES", /^Surveying /, add()], ["FILES SCANNED", /^Scanning files: ([\d,]+)/, add((m) => num(m[1]))],
      ["CONTAINERS", /^Identified containers: ([\d,]+)/, add((m) => num(m[1]))], ["ARCHIVES PROBED", /^Probing archives: ([\d,]+) \//, (m) => num(m[1])],
      ["BLOBS CARVED", /^Carving unknown blobs: ([\d,]+) \//, (m) => num(m[1])]],
  },
  cleanup: {
    verb: "CLEANING",
    stages: ["scan", "hash", "apply", "undo"],
    stageOf: (e) => ({ Scanning: "scan", Hashing: "hash", Applying: "apply", Undoing: "undo" })[e.message.split(" ")[0]] || e.stage,
    counters: [["FILES SCANNED", /^Scanning files: ([\d,]+)/, (m) => num(m[1])], ["HASHED", /^Hashing files: ([\d,]+)/, (m) => num(m[1])],
      ["APPLIED", /^Applying actions: ([\d,]+)/, (m) => num(m[1])], ["RESTORED", /^Undoing actions: ([\d,]+)/, (m) => num(m[1])]],
  },
  preflight: {
    verb: "CHECKING",
    stages: ["boot", "check", "install", "ready"],
    counters: [["FOUND", /^Checking .*: found/, add()], ["MISSING", /^Checking .*: missing$/, add()],
      ["INSTALLED", /^Installed /, add()], ["FAILED", /^Could not install/, add()]],
  },
  install: {
    verb: "INSTALLING",
    counters: [["DOWNLOADED KB", /^Downloading .*KB: ([\d,]+)/, (m) => num(m[1])], ["INSTALLED", /^Installed /, add()]],
  },
  capture: {
    verb: "CAPTURING",
    first: "policy", // warnings and the confirmation are checked before the first event
    stages: ["policy", "restore", "capture", "harvest", "gather", "diff", "report"],
    stageOf: (e) => (e.stage === "collect" ? "gather" : e.stage === "report" ? ["diff", "report"] : e.stage),
    counters: [["CAPTURES", /^Harvested /, add()], ["HARVESTED OK", /^Harvested .*: ok$/, add()],
      ["GATHERED", /^Captured ([\d,]+) file/, (m) => num(m[1])], ["NEW VS STATIC", /, ([\d,]+) new vs static/, (m) => num(m[1])]],
  },
  analyze: {
    verb: "ANALYSING",
    first: "copy",
    stages: ["copy", "analyze", "export", "report"],
    stageOf: (e) => (/^Ghidra: importing/.test(e.message) ? ["copy", "analyze"] : /ViWo export/.test(e.message) ? ["export", "report"] : e.stage === "analyze" ? "analyze" : ""),
    counters: [["GHIDRA LINES", /^(INFO|WARN|ERROR)\s/, add()], ["ERRORS", /^ERROR\s/, add()]],
  },
  indexes: {
    verb: "UPDATING",
    counters: [["DOWNLOADED KB", /^Downloading .*KB: ([\d,]+)/, (m) => num(m[1])], ["INSTALLED", /^Indexes .* installed/, add()]],
  },
  repack: {
    verb: "PATCHING",
    first: "plan", // the server plans (hashes the edit set) before its first event
    stages: ["plan", "copy", "pack", "verify", "report"],
    // Packers report nothing per container: the final event closes PACK + VERIFY + REPORT together.
    stageOf: (e) => (/^Copying the game/.test(e.message) ? "copy" : /^Patched copy ready/.test(e.message) ? ["pack", "verify", "report"]
      : e.stage === "repack" ? "" : /verif|unpack|extract/i.test(`${e.stage} ${e.message}`) ? "verify" : "pack"),
    counters: [["GAME FILES COPIED", /^Copied game files: ([\d,]+)/, (m) => num(m[1])],
      ["VERIFIED", /^Patched copy ready \((\w+)/, (m) => (m[1] === "verified" ? "YES" : "NO"), "—"]],
  },
};

/** Build a progress block for one job kind. start() before the blocking POST, finish() after it. */
export function jobProgress(kind, { logClass = "feed", onStatus = null } = {}) {
  const K = KINDS[kind] || { verb: `${String(kind).toUpperCase()}…`, stages: [], stageOf: () => "", counters: [] }; // a new kind needs no table entry
  const el = {
    verb: h("span", { class: "lbl", "data-state": "live" }, K.verb),
    stage: h("b", { class: "jp-stage" }),
    frac: h("span", { class: "jp-frac mono" }),
    quiet: h("span", { class: "jp-quiet" }),
    clock: h("span", { class: "jp-clock mono", title: "elapsed (job clock)" }, "00:00.0"),
    rail: h("ol", { class: "rail-stages", "aria-label": "Stages" }),
    bar: h("div", { class: "scan-bar jp-bar", "aria-hidden": "true" }, h("i", {})),
    tick: h("div", { class: "jp-tick mono", "aria-hidden": "true" }),
    counts: h("div", { class: "jp-counts" }),
    warns: h("ul", { class: "jp-warns", "aria-label": "Warnings" }),
    sr: h("p", { class: "sr", "aria-live": "polite" }),
    log: h("pre", { class: `log ${logClass}` }),
  };
  const root = h("div", { class: "jp", "data-state": "idle" },
    h("div", { class: "jp-head" }, el.verb, el.stage, el.frac, el.quiet, el.clock),
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
    el.quiet.textContent = !t.ended && t.cur && idle >= 5 ? `still working · last update ${Math.floor(idle)} s ago` : "";
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
    const nodes = rail(t.order.slice(hide).map((s, j) => ({ id: s, state: railState(s, j + hide) })));
    fill(el.rail, hide ? h("li", { class: "more", "data-s": "done" }, h("i", {}), h("span", {}, `+${hide} EARLIER`)) : null, [...nodes.children]);
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

  /** Determinate bar only while the current stage reports real counts; the scan bar everywhere else. */
  function paintBar() {
    const p = !t.ended && t.prog?.stage === t.cur ? t.prog : null;
    const pct = p?.total ? Math.min(100, Math.floor(((p.done - (K.ongoing ? 1 : 0)) / p.total) * 100)) : null;
    el.bar.dataset.state = pct !== null ? "det" : "scan";
    cssVar(el.bar, "p", `${pct ?? 0}%`);
    el.frac.textContent = !p || K.ongoing ? "" : pct !== null ? `${p.what ? `${p.what} · ` : ""}${fmt(p.done)} / ${fmt(p.total)} · ${pct}%` : p.text;
  }

  function paintCounts() {
    const rows = [...K.counters.map(([label]) => [label, t.counts[label]]), ["EVENTS", t.n], ["WARNINGS", t.warns.length]];
    for (const [label, value] of rows) {
      const text = typeof value !== "number" ? String(value) : Number.isInteger(value) ? fmt(value) : value.toFixed(1);
      let box = t.boxes[label];
      if (!box) {
        box = t.boxes[label] = h("div", { class: "jc" }, h("b", { class: "mono" }, text), h("span", {}, label));
        el.counts.append(box);
      } else if (box.firstChild.textContent !== text) {
        box.firstChild.textContent = text;
        delete box.dataset.state;
        void box.offsetWidth; // restart the flash
        box.dataset.state = "bump";
      }
      box.dataset.kind = (label.includes("FAIL") || label === "WARNINGS") && value > 0 ? "warn" : "";
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
      [].concat((K.stageOf || ((x) => x.stage))(e)).forEach(enter);
      const f = FRAC.exec(e.message);
      if (f && num(f[2]) >= num(f[1]) && num(f[2]) > 0) {
        t.prog = { stage: t.cur, done: num(f[1]), total: num(f[2]), what: e.message.slice(0, f.index).replace(/[\s:(]+$/, "") };
      }
      else if (COUNT.test(e.message)) t.prog = { stage: t.cur, text: e.message.replace(/ \(.*$/, "") };
    }
    const last = events.slice(-3);
    t.lines = [...t.lines, ...last].slice(-3);
    fill(el.tick, t.lines.map((e, i) => i === t.lines.length - 1
      ? cssVar(h("span", { class: "jp-line", "data-state": "now", "data-level": e.level === "warn" ? "warn" : null }, e.message), "n", Math.min(80, e.message.length))
      : h("span", { class: "jp-line" }, e.message)));
    const w = t.warns;
    fill(el.warns, w.slice(-4).map((m) => h("li", {}, m)), w.length > 4 ? h("li", { class: "more" }, `+${w.length - 4} earlier warning(s) in the log`) : null);
    if (stick) el.log.scrollTop = el.log.scrollHeight;
    say(last[last.length - 1].message);
    paintRail();
    paintBar();
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
      t0: Date.now(), lastEv: Date.now(), said: 0, ended: false, busy: false, prog: null };
    root.dataset.state = "running";
    el.verb.dataset.state = "live";
    el.verb.textContent = K.verb;
    fill(el.counts);
    fill(el.warns);
    fill(el.log);
    fill(el.tick, cssVar(h("span", { class: "jp-line", "data-state": "now" }, "waiting for the job to start"), "n", 24));
    enter(K.first);
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
    el.verb.dataset.state = outcome === "ok" ? "done" : "bad";
    el.verb.textContent = { ok: "COMPLETE", fail: "FAILED", cancel: "CANCELLED" }[outcome] || "STOPPED";
    paintRail();
    paintBar();
    if (note) el.stage.textContent = note;
    paintClock();
    say(`${el.verb.textContent.toLowerCase()}${note ? `: ${note}` : ""}`, true);
    if (!RM.matches) await sleep(250 + 40 * Math.min(10, t.order.length)); // lets the rail pop finish (300 ms + stagger)
  }

  /** The CANCEL button of every job view: asks the running job to stop at its next checkpoint. */
  async function cancel(note = "Cancellation requested.") {
    if (!t?.id) return toast("Job not registered yet — try again in a moment.", "warn");
    try { await api.cancel(t.id); toast(note, "warn"); } catch (err) { toastErr(err); }
  }

  return { el: root, log: el.log, start, finish, stop, cancel, get id() { return t?.id || null; } };
}

/** Skeleton placeholder with a scanline, for short waits (detect, view loads, previews). */
export function skeleton(label, rows = 4) {
  return h("div", { class: "skel", role: "status" }, h("span", { class: "lbl", "data-state": "live" }, label),
    Array.from({ length: rows }, (_, i) => cssVar(h("i", {}), "w", `${[94, 72, 86, 58, 80][i % 5]}%`)));
}

/** Run `work`; if it takes longer than 150 ms, show a skeleton in `host` meanwhile (no flash on fast loads). */
export async function withSkeleton(host, label, work, rows = 4) {
  const timer = setTimeout(() => host.replaceChildren(skeleton(label, rows)), 150);
  try { return await work(); } finally { clearTimeout(timer); }
}
