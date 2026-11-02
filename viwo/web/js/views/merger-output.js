// 06.C RENDER: transition / end / overlay / output settings, build as a "merge" job, results.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, errorBox, toast, toastErr, busy, emit, logLine } from "../ui.js";
import { jobProgress } from "../progress.js";

const O = { transitionType: "diapo", diapoDelay: 3, fadeCrossTime: 0.7, endFadeoutTime: 0, endLastImageTime: 0,
  overlaySound: "", overlayVolume: 0.35, outputName: "", trashAfterBuild: false };
const el = {};
let ctx = null;
let st = null;
let seeded = false;
let running = false;

export function applyState(state) {
  st = state;
  if (!seeded) {
    seeded = true;
    Object.assign(O, { transitionType: state.defaultTransition || "diapo", diapoDelay: state.defaultDiapoDelay, fadeCrossTime: state.defaultFadeCrossTime,
      endFadeoutTime: state.defaultEndFadeoutTime, endLastImageTime: state.defaultEndLastImageTime });
  }
  renderForm();
}

export function outputPanel(context) {
  ctx = context;
  el.form = h("div", { class: "mform" });
  el.build = btn("BUILD TIMELINES", build, "primary lg");
  el.prog = jobProgress("merge", { logClass: "mini", onStatus: (text) => { if (running && text) el.sum.textContent = text; } });
  el.prog.el.hidden = true;
  el.results = h("div", {});
  el.sum = h("div", { class: "ab-sum mono" });
  el.why = h("span", { class: "ab-why" });
  el.bar = h("div", { class: "actionbar" }, el.sum, el.why, el.build);
  renderForm();
  return panel("06.C", "RENDER", null, el.form, el.prog.el, el.results);
}

export const actionBar = () => el.bar;

/** Sticky bar: what will be rendered, an estimate, and why BUILD is blocked. */
export function refreshBar() {
  if (!el.sum || !ctx) return;
  const s = ctx.stats();
  const fade = O.transitionType === "fade";
  const est = (s.clips - s.videos) * O.diapoDelay - (fade ? Math.max(0, s.clips - s.timelines) * O.fadeCrossTime : 0) + s.timelines * (O.endLastImageTime || 0);
  el.sum.textContent = s.timelines ? `${s.timelines} TIMELINE(S) · ${s.clips} CLIPS · ≈${Math.max(0, est).toFixed(1)} s${s.videos ? ` + ${s.videos} video clip(s)` : ""} · ${fade ? "CROSSFADE" : "CUT"}` : "no timeline selected";
  el.why.textContent = !st?.encoder ? "ffmpeg missing" : running ? "rendering…" : !s.timelines ? "select a candidate"
    : fade && O.fadeCrossTime >= O.diapoDelay ? "crossfade ≥ image hold" : "";
  el.build.disabled = Boolean(el.why.textContent);
}

function field(label, key, opts = {}) {
  return h("label", { class: "nfield" }, h("span", { class: "lbl" }, label),
    h("input", { class: "input mono", type: "number", min: 0, step: opts.step || 0.1, value: String(O[key] ?? 0), disabled: opts.disabled || null,
      oninput: (e) => { O[key] = Math.max(0, parseFloat(e.target.value) || 0); refreshBar(); } }));
}

function overlayRow() {
  const input = h("input", { class: "input mono grow", value: O.overlaySound, placeholder: "optional looping audio (absolute path)", "aria-label": "Overlay audio path",
    oninput: (e) => { O.overlaySound = e.target.value.trim(); } });
  const pick = (e) => busy(e.currentTarget, async () => {
    try { O.overlaySound = input.value = (await api.mergerOverlay(O.overlaySound)).path; } catch (err) {
      if (!err.payload?.cancelled) toast("Picker unavailable on this host — type the path.", "warn", err.message);
    }
  });
  const vol = h("output", { class: "mono" }, `${Math.round(O.overlayVolume * 100)}%`);
  return [h("span", { class: "lbl" }, "OVERLAY AUDIO"),
    h("div", { class: "row" }, input, btn("BROWSE", pick, "ghost"), btn("CLEAR", () => { O.overlaySound = input.value = ""; }, "sm ghost")),
    h("div", { class: "row vol" }, h("span", { class: "lbl" }, "VOLUME"),
      h("input", { type: "range", min: 0, max: 1, step: 0.05, value: String(O.overlayVolume), "aria-label": "Overlay volume",
        oninput: (e) => { O.overlayVolume = Number(e.target.value); vol.textContent = `${Math.round(O.overlayVolume * 100)}%`; } }), vol),
    st ? h("p", { class: "dim small" }, `Formats: ${st.supportedOverlayAudioExts.join(" ")}. Native clip audio is kept and mixed.`) : null];
}

function renderForm() {
  if (!el.form) return;
  const fade = O.transitionType === "fade";
  const seg = h("div", { class: "seg sm", role: "group", "aria-label": "Transition" }, ["diapo", "fade"].map((t) =>
    h("button", { type: "button", "aria-pressed": String(O.transitionType === t), onclick: () => { O.transitionType = t; renderForm(); } },
      t === "diapo" ? "CUT (DIAPO)" : "CROSSFADE")));
  fill(el.form,
    h("div", { class: "row" }, h("span", { class: "lbl" }, "TRANSITION"), seg),
    h("div", { class: "nums" }, field("IMAGE HOLD (S)", "diapoDelay"), field("CROSSFADE (S)", "fadeCrossTime", { disabled: !fade }),
      field("END FADE-OUT (S)", "endFadeoutTime"), field("HOLD LAST FRAME (S)", "endLastImageTime")),
    overlayRow(),
    h("label", { class: "lbl", for: "merge-name" }, "OUTPUT NAME"),
    h("input", { class: "input mono", id: "merge-name", value: O.outputName, placeholder: "blank = candidate name · text = prefix (prefix_candidate.mp4)",
      oninput: (e) => { O.outputName = e.target.value; } }),
    h("label", { class: "field inline" }, h("span", { class: "lbl" }, "Move merged source files to the workspace trash after a successful build"),
      h("input", { type: "checkbox", checked: O.trashAfterBuild, onchange: (e) => { O.trashAfterBuild = e.target.checked; } })));
  refreshBar();
}

async function build() {
  const selected = ctx.specs();
  if (!selected.length) return toast("Select at least one candidate.", "warn");
  if (O.transitionType === "fade" && O.fadeCrossTime >= O.diapoDelay) return toast("Crossfade must be shorter than the image hold.", "warn");
  running = true;
  refreshBar();
  el.build.textContent = "RENDERING…";
  fill(el.results);
  el.prog.el.hidden = false;
  await el.prog.start({ total: selected.length });
  el.prog.log.append(logLine(`// BUILD ${selected.length} TIMELINE(S) · ${O.transitionType.toUpperCase()}`));
  el.prog.el.scrollIntoView({ block: "nearest" });
  try {
    const res = await api.mergerBuild({ ...O, namingPattern: ctx.pattern(), selectedCandidates: selected });
    await el.prog.finish(res.partial ? "fail" : "ok", `${res.builtCount ?? 1} VIDEO(S) BUILT${res.partial ? " · SOME FAILED" : ""}`);
    renderResults(res);
    el.results.firstElementChild?.classList.add("reveal");
    toast(`Built ${res.builtCount ?? 1} video(s).`, res.partial ? "warn" : "ok", res.partial ? "Some candidates failed." : "");
    if (O.trashAfterBuild) emit("workspace");
  } catch (err) {
    await el.prog.finish("fail", String(err.code || "error").toUpperCase());
    fill(el.results, errorBox(err, "BUILD FAILED"), failures(err.payload?.failures));
    toastErr(err, "Build failed: ");
  } finally {
    running = false;
    el.build.textContent = "BUILD TIMELINES";
    refreshBar();
    emit("jobs");
  }
}

const failures = (list) => (list?.length ? h("div", { class: "alert warn" }, h("b", {}, "FAILED CANDIDATES"),
  h("ul", {}, list.map((f) => h("li", {}, h("b", {}, f.candidateName), ": ", f.error)))) : null);

const folderOf = (p) => p.replace(/[\\/][^\\/]*$/, "") || p;

function renderResults(res) {
  const outputs = res.outputs || [res];
  fill(el.results, h("h4", { class: "sub-h" }, `// OUTPUT (${outputs.length})`),
    outputs.map((o) => h("div", { class: "outrow" },
      h("div", {}, h("b", {}, o.outputName), h("code", { class: "mono path block" }, o.outputPath)),
      h("div", { class: "row" }, badge(`${o.mergedCount} CLIPS`, "mute"), badge(`${Number(o.totalDuration || 0).toFixed(1)} S`, "ok"),
        o.trashedCount ? badge(`${o.trashedCount} TRASHED`, "warn") : null,
        btn("OPEN FOLDER", () => api.openFolder(folderOf(o.outputPath)).then(() => toast("Opened in file manager.", "ok"), toastErr), "sm ghost")))),
    failures(res.failures));
}
