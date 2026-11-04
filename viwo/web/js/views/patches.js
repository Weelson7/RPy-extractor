// PATCHES (patching arm): T1 patch sets (byte, RVA and AOB patches, assembly) checked against
// the game and written into a marked patched copy; T2 mods packed from a copy, checked against a
// game version (the update check) and applied in load order. The game folder is only read.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, viewHead, kv, table, seg, toast, toastErr, pref, emit, browseBtn, errorBox, openBtn, assure } from "../ui.js";
import { jobProgress } from "../progress.js";
import { currentGame, setGame, gameField } from "../game.js";

const S = { running: false, action: pref("modAction") || "check" };
const el = {};
const input = (id, placeholder, key) => h("input", { class: "input mono grow", id, placeholder, value: pref(key) || "",
  spellcheck: "false", oninput: (e) => pref(key, e.target.value.trim()) });
const pickFile = (field, key) => browseBtn(field, (p) => pref(key, p), (p) => api.browseFile(p || currentGame()).then((r) => r.path));

function mount(root) {
  el.game = gameField("pt-game");
  el.set = input("pt-set", "/path/to/fix.patch.json", "patchSet");
  el.out = input("pt-out", "patched copy folder (APPLY writes there)", "patchOut");
  el.mods = input("pt-mods", "one or more mod zips, comma-separated", "modZips");
  el.copy = input("pt-copy", "patched copy folder", "modCopy");
  el.name = input("pt-name", "the mod's name", "modName");
  el.modsLbl = h("label", { class: "lbl", for: "pt-mods" });
  el.copyLbl = h("label", { class: "lbl", for: "pt-copy" });
  el.nameRow = h("div", {}, h("label", { class: "lbl", for: "pt-name" }, "NAME"), h("div", { class: "row" }, el.name));
  el.progHost = h("div", {});
  el.result = h("div", {});
  root.append(
    viewHead(code("patches"), "PATCHES + MODS", "Byte, RVA and AOB patches (assembly through Keystone) into a marked patched copy; a copy's changes packed as a mod, checked against another game version and applied with others in load order."),
    assure([["GAME FOLDER READ-ONLY", "patches and mods only ever write a marked patched copy"],
      ["READ BACK", "every patch is re-read after writing; the whole file is compared"],
      ["UPDATE CHECK", "a mod's AOB patches are searched in the new version before it is applied"]]),
    h("label", { class: "lbl", for: "pt-game" }, "GAME FOLDER (THE TOP BAR'S GAME)"), h("div", { class: "row" }, el.game, browseBtn(el.game, setGame)),
    h("div", { class: "grid2" },
      h("div", { class: "col" },
        panel(`${code("patches")}.A`, "PATCH SET", badge("PATCHED COPY", "ok"),
          h("label", { class: "lbl", for: "pt-set" }, "PATCH SET FILE"), h("div", { class: "row" }, el.set, pickFile(el.set, "patchSet")),
          h("label", { class: "lbl", for: "pt-out" }, "PATCHED COPY (AN EXISTING ONE IS PATCHED IN PLACE)"), h("div", { class: "row" }, el.out, browseBtn(el.out, (p) => pref("patchOut", p))),
          h("div", { class: "row" }, btn("CHECK", () => patch(true), ""), btn("APPLY", () => patch(false), "primary"))),
        panel(`${code("patches")}.B`, "MOD PACKAGE", seg([["check", "CHECK"], ["pack", "PACK"], ["apply", "APPLY"]], S.action, (v) => { S.action = v; pref("modAction", v); modLabels(); }, { class: "seg sm" }),
          el.modsLbl, h("div", { class: "row" }, el.mods, pickFile(el.mods, "modZips")),
          el.copyLbl, h("div", { class: "row" }, el.copy, browseBtn(el.copy, (p) => pref("modCopy", p))),
          el.nameRow,
          h("div", { class: "row" }, btn("RUN", mod, "primary")))),
      h("div", { class: "col" }, el.progHost, el.result)));
  modLabels();
}

/** The mod fields mean something else per action: their labels and hints follow it. */
const MOD_FIELDS = {
  check: ["MOD ZIP", "the mod zip to check against this game", "PATCHED COPY (NOT USED BY CHECK)"],
  pack: ["MOD ZIP TO WRITE", "where to write the mod zip, e.g. C:\\Mods\\my-mod.zip", "PATCHED COPY TO PACK (ITS CHANGES BECOME THE MOD)"],
  apply: ["MOD ZIPS IN LOAD ORDER", "one or more mod zips, comma-separated, first applied first", "PATCHED COPY TO APPLY THEM INTO"],
};

function modLabels() {
  const [mods, hint, copy] = MOD_FIELDS[S.action] || MOD_FIELDS.check;
  el.modsLbl.textContent = mods;
  el.mods.placeholder = hint;
  el.copyLbl.textContent = copy;
  el.nameRow.hidden = S.action !== "pack";
}

/** Scalars as key/values, lists of rows as a table: every T1/T2 report has that shape. */
function report(title, res, ok) {
  const rows = Object.values(res).find((v) => Array.isArray(v) && v.length && typeof v[0] === "object") || [];
  const cols = rows.length ? Object.keys(rows[0]).filter((k) => typeof rows[0][k] !== "object").slice(0, 6) : [];
  return panel(`${code("patches")}.D`, title, h("div", { class: "row" }, badge(ok ? "OK" : "SEE BELOW", ok ? "ok" : "warn"), openBtn(res.copy || res.out || res.target || "")),
    Object.entries(res).filter(([k, v]) => k !== "success" && v !== null && typeof v !== "object").map(([k, v]) => kv(k.toUpperCase(), h("span", { class: "mono" }, String(v)))),
    cols.length ? table(cols.map((c) => ({ key: c, label: c.toUpperCase() })),
      rows.map((r) => Object.fromEntries(cols.map((c) => [c, String(r[c] ?? "")])))) : null);
}

async function job(kind, call, title) {
  if (S.running) return toast("A run is in progress.", "warn");
  if (!el.game.value.trim()) return toast("Enter the game folder first.", "warn");
  S.running = true;
  const prog = jobProgress(kind, { logClass: "mini" });
  fill(el.progHost, panel(`${code("patches")}.C`, "RUN", null, prog.el));
  fill(el.result);
  await prog.start();
  try {
    const res = await call();
    await prog.finish("ok", `${title} DONE`);
    fill(el.result, report(title, res, res.ok !== false && res.fits !== false));
  } catch (err) {
    await prog.finish("fail", `${title} FAILED`);
    fill(el.result, errorBox(err, `${title} FAILED`));
    toastErr(err, `${title.toLowerCase()} failed: `);
  } finally {
    S.running = false;
    emit("jobs");
  }
}

const patch = (plan) => (!plan && !el.out.value.trim()
  ? toast("Pick the patched copy folder APPLY writes into (CHECK only reads the game).", "warn")
  : job("patch", () => api.patch({ gamePath: el.game.value.trim(), patchSet: el.set.value.trim(),
  out: plan ? "" : el.out.value.trim(), plan }), plan ? "PATCH CHECK" : "PATCH APPLY"));

const mod = () => job("mod", () => api.mod({ action: S.action, gamePath: el.game.value.trim(), copy: el.copy.value.trim(),
  mods: el.mods.value.split(",").map((m) => m.trim()).filter(Boolean), mod: el.mods.value.split(",")[0].trim(), name: el.name.value.trim() }),
`MOD ${S.action.toUpperCase()}`);

import { registerView, code } from "../registry.js";

const VIEW = { mount };
registerView({ id: "patches", arm: "patching", order: 20, title: "PATCHES + MODS", subtitle: "patch sets, mod packages", ...VIEW });
export default VIEW;
