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
/** Buttons closer than 4 px to a button beside them, or 6 px to the note, field, button or panel
 * above or below them: the spacing the CSS gives every action row. */
const tight = (view) => evaluate(`(() => { const sel = (q) => [...document.querySelectorAll(q)].filter((n) => n.getClientRects().length);
  const bs = sel('#view-${view} .btn'), near = sel('#view-${view} :is(.btn, .input, textarea, p, .panel)'), out = [];
  for (const b of bs) { const rb = b.getBoundingClientRect(); for (const o of near) { if (o === b || o.contains(b) || b.contains(o)) continue;
    if (Boolean(b.closest('.actionbar')) !== Boolean(o.closest('.actionbar'))) continue; // the pinned bar floats over the content
    const ro = o.getBoundingClientRect(), side = Math.min(rb.bottom, ro.bottom) - Math.max(rb.top, ro.top), cols = Math.min(rb.right, ro.right) - Math.max(rb.left, ro.left);
    const gx = ro.left - rb.right, gy = Math.max(rb.top - ro.bottom, ro.top - rb.bottom);
    if ((o.matches('.btn') && side > rb.height / 2 && gx > -2 && gx < 4) || (cols > 0 && side <= 0 && gy > -2 && gy < 6)) out.push([b.textContent.trim(), o.className, Math.round(Math.min(gx, gy))]); } }
  return out; })()`);
/** The codes of a view's step rows: each shown once (an arm home names a tab once). */
const stepCodes = (view) => evaluate(`[...document.querySelectorAll('#view-${view} .path-steps > li > b.mono')].map((b) => b.textContent).filter((t) => t !== '—')`);

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
// the tab codes are computed: the rail's and the strip's, and the view heads they open
report.checks.codes = { static: await evaluate("[...document.querySelectorAll('#mods a b')].map((b) => b.textContent)"),
  strip: await evaluate("[...document.querySelectorAll('#strip a b')].map((b) => b.textContent)") };
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
  report.views[v].tight = await tight(v);
  report.views[v].stepCodes = await stepCodes(v);
  await shot(`view-${v}`);
}

// toast position: top right, under the top bar (never over an action bar)
step = "toast";
await evaluate("import('./js/ui.js').then((m) => { m.toast('smoke toast', 'ok'); return true; })");
await sleep(300);
report.checks.toast = await evaluate("(() => { const t = document.querySelector('#toasts .toast'); if (!t) return null; const r = t.getBoundingClientRect(); return { topGap: r.top - document.querySelector('.topbar').getBoundingClientRect().bottom, rightGap: window.innerWidth - r.right, text: t.textContent }; })()");

// SYSTEM: gap between its first panel and the grid below
step = "system";
await evaluate("location.hash = '#system'");
await sleep(1500);
report.checks.systemGap = await evaluate("(() => { const a = document.querySelector('#view-system .panel'); const g = a && a.nextElementSibling; if (!a || !g) return null; return g.getBoundingClientRect().top - a.getBoundingClientRect().bottom; })()");

// SETTINGS: slots table fills its column; theme switch; no null text
step = "settings";
await evaluate("location.hash = '#settings'");
await waitFor("Boolean([...document.querySelectorAll('#view-settings .panel')].find((p) => p.querySelector('h3')?.textContent.startsWith('FORMATS'))?.querySelector('table'))", 15000);
report.checks.slotsTable = await evaluate("(() => { const p = [...document.querySelectorAll('#view-settings .panel')].find((p) => p.querySelector('h3')?.textContent.startsWith('FORMATS')); const t = p && p.querySelector('table'); if (!t) return null; const body = p.querySelector('.panel-b'); return { table: t.getBoundingClientRect().width, column: body.getBoundingClientRect().width }; })()");
report.checks.settingsNull = await nullText("settings");
const before = await evaluate("({ theme: document.documentElement.dataset.theme, href: document.querySelector('#theme-link').getAttribute('href') })");
await evaluate("(() => { const b = [...document.querySelectorAll('#view-settings [data-role=\"theme\"] button')].find((x) => x.dataset.value === 'plain'); if (b) b.click(); return Boolean(b); })()");
await sleep(400);
const after = await evaluate("({ theme: document.documentElement.dataset.theme, href: document.querySelector('#theme-link').getAttribute('href') })");
report.checks.theme = { before, after };
await shot("theme-plain");
await evaluate("(() => { const b = [...document.querySelectorAll('#view-settings [data-role=\"theme\"] button')].find((x) => x.dataset.value === 'wormhole'); if (b) b.click(); return Boolean(b); })()");
await sleep(300);

// EXTRACT: detect percent format, options panel, skipped stage after a real extraction
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

// SORT: type filters carry workspace-wide counts
step = "sort";
await evaluate("location.hash = '#sort'");
await waitFor("document.querySelectorAll('#view-sort .tfilter button').length > 0", 15000);
report.checks.sortFilters = await evaluate("[...document.querySelectorAll('#view-sort .tfilter button')].map((b) => b.textContent.replace(/\\s+/g, ' ').trim())");

// MERGER: a name with one file is listed under SINGLE FILES, after the groups, and can still be ticked
step = "merger";
await evaluate("location.hash = '#merger'");
await waitFor("Boolean(document.querySelector('#view-merger .clist :is(.cand, .msingles)'))", 15000); // the extracted files, not the empty list of before
report.checks.merger = await evaluate(`(() => { const l = document.querySelector('#view-merger .clist'), s = l.querySelector('.msingles');
  return { groupsOfOne: [...l.querySelectorAll(':scope > .cand')].filter((c) => !/\\d+ FILES/.test(c.textContent)).length, singles: s ? s.querySelectorAll('.cand input[type=checkbox]').length : 0,
    head: s ? s.querySelector('h4').textContent : '', count: document.querySelector('#view-merger .panel-h .tools').textContent }; })()`);
await shot("merger-after-extract");

// ASSETS: the mod / overwrite choice and a plan of the extracted workspace (nothing edited yet)
step = "assets";
await evaluate("location.hash = '#assets'");
await sleep(800);
report.checks.assetsModes = await evaluate("[...document.querySelectorAll('#view-assets .seg button')].map((b) => [b.textContent, b.getAttribute('aria-pressed')])");
await click("assets", "PLAN");
report.checks.assetsPlanned = await waitFor("Boolean(document.querySelector('#view-assets .stats .stat') || document.querySelector('#view-assets .empty'))", 20000);
report.checks.assetsWrite = await evaluate("(() => { const b = [...document.querySelectorAll('#view-assets button')].find((x) => x.textContent.trim() === 'WRITE'); return b ? { disabled: b.disabled, why: document.querySelector('#view-assets .ab-why').textContent } : null; })()");
report.checks.assetsNull = await nullText("assets");
await shot("assets-planned");

// CLEANUP: the scan runs as a visible job
step = "cleanup";
await evaluate("location.hash = '#cleanup'");
await sleep(800);
await click("cleanup", "SCAN");
await sleep(300);
report.checks.cleanupJobShown = await evaluate("(() => { const h = document.querySelector('#view-cleanup .job-host'); return h ? !h.hidden : null; })()");
report.checks.cleanupDone = await waitFor("(() => { const jp = document.querySelector('#view-cleanup .jp'); return jp && jp.dataset.state !== 'running' && jp.dataset.state !== 'idle'; })()", 60000, 500);
report.checks.cleanupState = await evaluate("document.querySelector('#view-cleanup .jp')?.dataset.state");
await shot("cleanup-done");

// ANALYSIS: the action bar holds ANALYZE, held back with the reason beside it
step = "analysis";
await evaluate("location.hash = '#analysis'");
await sleep(1500);
report.checks.analysisBar = await evaluate(`(() => { const b = document.querySelector('#view-analysis .actionbar .btn.primary');
  return b ? { label: b.textContent.trim(), disabled: b.disabled, why: document.querySelector('#view-analysis .ab-why').textContent } : null; })()`);

// RUNBOOKS: every step a readable row (what, target, options), its JSON behind a toggle
step = "runbooks";
await evaluate("location.hash = '#runbooks'");
await waitFor("document.querySelectorAll('#view-runbooks .path-steps > li').length > 0", 15000);
report.checks.runbookSteps = await evaluate(`[...document.querySelectorAll('#view-runbooks .path-steps > li')].map((li) => {
  const json = li.querySelector('details.rb-json'), w = document.createTreeWalker(li, NodeFilter.SHOW_TEXT); let raw = false;
  while (w.nextNode()) if (/\\{"/.test(w.currentNode.textContent) && !w.currentNode.parentElement.closest('details')) raw = true;
  return { json: Boolean(json && JSON.parse(json.querySelector('pre').textContent)), open: Boolean(json?.open), facts: li.querySelectorAll('.facts dt').length, raw }; })`);
await shot("runbook-steps");

writeFileSync(`${OUT}/report.json`, JSON.stringify(report, null, 2));
process.stdout.write(JSON.stringify(report));
ws.close();
