// Real-browser smoke of the ViWo web UI over the Chrome DevTools Protocol (no npm packages).
// Usage: node smoke.mjs <app url> <cdp port> <game folder> <out folder>   -> prints one JSON report.
import { writeFileSync, mkdirSync } from "node:fs";

const [APP, PORT, GAME, OUT] = process.argv.slice(2);
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const report = { console: [], views: {}, checks: {} };
let step = "startup";

// a fresh tab of our own, so a stale page from another run never pollutes the console log
const target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" })).json();
const ws = new WebSocket(target.webSocketDebuggerUrl);
const ours = (url) => !url || String(url).startsWith(APP);
await new Promise((r) => (ws.onopen = r));
let seq = 0;
const pending = new Map();
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); return; }
  if (msg.method === "Runtime.exceptionThrown") {
    const d = msg.params.exceptionDetails;
    if (ours(d.url)) report.console.push({ step, kind: "exception", text: d.exception?.description || d.text, url: d.url, line: d.lineNumber });
  } else if (msg.method === "Runtime.consoleAPICalled" && ["error", "assert"].includes(msg.params.type)) {
    report.console.push({ step, kind: msg.params.type, text: msg.params.args.map((a) => a.value ?? a.description).join(" ") });
  } else if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error" && ours(msg.params.entry.url)) {
    report.console.push({ step, kind: "log-error", text: msg.params.entry.text, url: msg.params.entry.url });
  }
};
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const n = ++seq;
  pending.set(n, (msg) => (msg.error ? reject(new Error(`${method}: ${msg.error.message}`)) : resolve(msg.result)));
  ws.send(JSON.stringify({ id: n, method, params }));
});
const evaluate = async (expr) => {
  const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(`evaluate failed: ${r.exceptionDetails.exception?.description || r.exceptionDetails.text}`);
  return r.result.value;
};
const shot = async (name) => writeFileSync(`${OUT}/${name}.png`, Buffer.from((await send("Page.captureScreenshot", { format: "png" })).data, "base64"));
const waitFor = async (expr, timeout = 30000, every = 250) => {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) { if (await evaluate(expr)) return true; await sleep(every); }
  return false;
};
const click = (view, label) => evaluate(`(() => { const b = [...document.querySelectorAll('#view-${view} button')].find((x) => x.textContent.trim().startsWith(${JSON.stringify(label)})); if (!b) return 'no button ${label}'; b.click(); return 'clicked'; })()`);
const setInput = (sel, value) => evaluate(`(() => { const i = document.querySelector(${JSON.stringify(sel)}); if (!i) return 'no input'; i.value = ${JSON.stringify(value)}; i.dispatchEvent(new Event('input', { bubbles: true })); return 'set'; })()`);
/** Literal "null"/"undefined" text nodes anywhere in a view: the sign of an append(null). */
const nullText = (view) => evaluate(`(() => { const w = document.createTreeWalker(document.querySelector('#view-${view}'), NodeFilter.SHOW_TEXT); const bad = []; while (w.nextNode()) { const t = w.currentNode.textContent.trim(); if (t === 'null' || t === 'undefined') bad.push(w.currentNode.parentElement.outerHTML.slice(0, 80)); } return bad; })()`);

await send("Runtime.enable");
await send("Log.enable");
await send("Page.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });

step = "landing";
await send("Page.navigate", { url: `${APP}/` });
report.checks.landingSeen = await waitFor("Boolean(document.querySelector('.landing'))", 5000, 100);
report.checks.landingDone = await waitFor("!document.querySelector('.landing') && Boolean(document.querySelector('#view-static:not([hidden])'))", 90000);
await shot("00-landing-done");

const VIEWS = await evaluate("[...document.querySelectorAll('#main > section.view')].map((s) => s.id.slice(5))");
report.checks.views = VIEWS;
// the arms: the rail lists one arm's views, a global view (strip) keeps the arm
const railNow = () => evaluate("[...document.querySelectorAll('#mods a')].map((a) => a.dataset.view)");
report.checks.arms = { static: await railNow(), strip: await evaluate("[...document.querySelectorAll('#strip a')].map((a) => a.dataset.view)") };
await evaluate("location.hash = '#capture'"); await sleep(300);
report.checks.arms.dynamic = await railNow();
await evaluate("location.hash = '#jobs'"); await sleep(300);
report.checks.arms.afterGlobal = await railNow();
await evaluate("document.querySelector('#arms button[data-value=\"patching\"]').click()"); await sleep(300);
report.checks.arms.patching = await railNow();
report.checks.arms.patchingHash = await evaluate("location.hash");
for (const v of VIEWS) {
  step = `view:${v}`;
  await evaluate(`location.hash = '#${v}'`);
  await sleep(1200);
  report.views[v] = await evaluate(`(() => { const s = document.querySelector('#view-${v}'); if (!s) return { missing: true }; const r = s.getBoundingClientRect();
    return { visible: !s.hidden && r.width > 0 && r.height > 0, heading: (s.querySelector('h2') || {}).textContent || '', overflow: document.querySelector('main').scrollWidth > document.querySelector('main').clientWidth }; })()`);
  report.views[v].nullText = await nullText(v);
  await shot(`view-${v}`);
}

// toast position: bottom right of the viewport
step = "toast";
await evaluate("import('./js/ui.js').then((m) => { m.toast('smoke toast', 'ok'); return true; })");
await sleep(300);
report.checks.toast = await evaluate("(() => { const t = document.querySelector('#toasts .toast'); if (!t) return null; const r = t.getBoundingClientRect(); return { bottomGap: window.innerHeight - r.bottom, rightGap: window.innerWidth - r.right, text: t.textContent }; })()");

// 05 SYSTEM: gap between 05.A and the grid below
step = "system";
await evaluate("location.hash = '#system'");
await sleep(1500);
report.checks.systemGap = await evaluate("(() => { const a = document.querySelector('#view-system [data-panel=\"05.A\"]'); const g = a && a.nextElementSibling; if (!a || !g) return null; return g.getBoundingClientRect().top - a.getBoundingClientRect().bottom; })()");

// 11 SETTINGS: slots table fills its column; theme switch; no null text
step = "settings";
await evaluate("location.hash = '#settings'");
await waitFor("Boolean(document.querySelector('#view-settings [data-panel=\"11.E\"] table'))", 15000);
report.checks.slotsTable = await evaluate("(() => { const p = document.querySelector('#view-settings [data-panel=\"11.E\"]'); const t = p && p.querySelector('table'); if (!t) return null; const body = p.querySelector('.panel-b'); return { table: t.getBoundingClientRect().width, column: body.getBoundingClientRect().width }; })()");
report.checks.settingsNull = await nullText("settings");
const before = await evaluate("({ theme: document.documentElement.dataset.theme, href: document.querySelector('#theme-link').getAttribute('href') })");
await evaluate("(() => { const b = [...document.querySelectorAll('#view-settings [data-role=\"theme\"] button')].find((x) => x.dataset.value === 'plain'); if (b) b.click(); return Boolean(b); })()");
await sleep(400);
const after = await evaluate("({ theme: document.documentElement.dataset.theme, href: document.querySelector('#theme-link').getAttribute('href') })");
report.checks.theme = { before, after };
await shot("theme-plain");
await evaluate("(() => { const b = [...document.querySelectorAll('#view-settings [data-role=\"theme\"] button')].find((x) => x.dataset.value === 'wormhole'); if (b) b.click(); return Boolean(b); })()");
await sleep(300);

// 01 EXTRACT: detect percent format, options panel, skipped stage after a real extraction
step = "extract";
await evaluate("location.hash = '#extract'");
await sleep(600);
await setInput("#game-path", GAME);
await click("extract", "DETECT ENGINE");
await waitFor("Boolean(document.querySelector('#view-extract .det .pct'))", 20000);
report.checks.detectPct = await evaluate("[...document.querySelectorAll('#view-extract .det .pct')].map((e) => e.textContent.trim())");
await click("extract", "RUN EXTRACTION");
report.checks.extractDone = await waitFor("(() => { const jp = document.querySelector('#view-extract .jp'); return jp && jp.dataset.state === 'done'; })()", 120000, 500);
await sleep(600);
report.checks.rail = await evaluate("[...document.querySelectorAll('#view-extract .rail-stages li')].map((li) => ({ s: li.dataset.s, label: li.querySelector('span').textContent, note: (li.querySelector('.rail-note') || {}).textContent || '', noteVisible: Boolean(li.querySelector('.rail-note') && li.querySelector('.rail-note').getBoundingClientRect().height > 0) }))");
await shot("extract-done");

// 03 SORT: type filters carry workspace-wide counts
step = "sort";
await evaluate("location.hash = '#sort'");
await waitFor("document.querySelectorAll('#view-sort .tfilter button').length > 0", 15000);
report.checks.sortFilters = await evaluate("[...document.querySelectorAll('#view-sort .tfilter button')].map((b) => b.textContent.replace(/\\s+/g, ' ').trim())");

// 08 CLEANUP: the scan runs as a visible job
step = "cleanup";
await evaluate("location.hash = '#cleanup'");
await sleep(800);
await click("cleanup", "SCAN");
await sleep(300);
report.checks.cleanupJobShown = await evaluate("(() => { const h = document.querySelector('#view-cleanup .job-host'); return h ? !h.hidden : null; })()");
report.checks.cleanupDone = await waitFor("(() => { const jp = document.querySelector('#view-cleanup .jp'); return jp && jp.dataset.state !== 'running' && jp.dataset.state !== 'idle'; })()", 60000, 500);
report.checks.cleanupState = await evaluate("document.querySelector('#view-cleanup .jp')?.dataset.state");
await shot("cleanup-done");

writeFileSync(`${OUT}/report.json`, JSON.stringify(report, null, 2));
process.stdout.write(JSON.stringify(report));
ws.close();
