// 07 SURVEY cards: one game's engine, coverage meter, category bar + legend, unknown blobs, missing tools.
import { h, btn, panel, badge, meter, fmtBytes, fmtNum, pad } from "../ui.js";

/** Category -> [label, what it means]. Order = stacked bar order (covered first). */
export const CATS = {
  asset: ["ASSET", "plain media files, copied as-is"],
  container: ["CONTAINER", "archives ViWo can unpack"],
  engine: ["ENGINE", "decoded by the engine plugin's exporter"],
  carvable: ["CARVABLE", "the carver finds embedded files (deep)"],
  "container-no-tool": ["NO TOOL", "known archive format, unpacker not installed"],
  unknown: ["UNKNOWN", "structured data in a format nothing recognizes"],
  "unknown-dense": ["DENSE", "encrypted or compressed blob"],
  unreadable: ["UNREADABLE", "could not be read"],
  code: ["CODE", "scripts and executables — not counted"],
  small: ["SMALL", "tiny files — not counted"],
};
export const COVERED = ["asset", "container", "engine", "carvable"];

const bytesOf = (g, keys) => keys.reduce((s, k) => s + (g.categories?.[k]?.bytes || 0), 0);
export const dataBytes = (g) => bytesOf(g, Object.keys(CATS).filter((k) => k !== "code" && k !== "small"));
export const coveredBytes = (g) => bytesOf(g, COVERED);
/** Floor, so a game is never shown as 100% unless it is fully covered. */
export const pct = (v) => `${Math.floor(Number(v || 0) * 100)}%`;
export const covKind = (v) => (v >= 0.999 ? "ok" : v >= 0.5 ? "hi" : "lo");

function stackBar(cats, total) {
  const label = cats.map(([k, c]) => `${CATS[k]?.[0] || k} ${Math.round((c.bytes / (total || 1)) * 100)}%`).join(", ");
  return h("div", { class: "sbar", role: "img", "aria-label": `Bytes by category: ${label}` },
    cats.filter(([, c]) => c.bytes > 0).map(([k, c]) => h("i", { class: `c-${k}`, style: `flex-grow:${c.bytes}`,
      title: `${CATS[k]?.[0] || k}: ${fmtBytes(c.bytes)} in ${fmtNum(c.files)} file(s)` })));
}

const legend = (cats) => h("ul", { class: "sv-legend" }, cats.map(([k, c]) =>
  h("li", { class: `c-${k}`, title: CATS[k]?.[1] || k }, h("b", {}, CATS[k]?.[0] || k),
    h("span", { class: "mono" }, `${fmtNum(c.files)} · ${fmtBytes(c.bytes)}`))));

/** Every category with its meaning: the idle-state key. */
export const categoryKey = () => h("ul", { class: "sv-legend key" }, Object.entries(CATS).map(([k, [label, what]]) =>
  h("li", { class: `c-${k}` }, h("b", {}, label), h("span", {}, what))));

function unknownBlock(list, deep, onDeep) {
  if (!list?.length) return null;
  const why = (u) => (u.dense ? "encrypted or compressed — needs a key, a decoder or runtime capture"
    : deep ? "structured, but the carver found nothing it recognizes" : "carver may find files: run DEEP");
  return [h("h4", { class: "sub-h" }, `// UNKNOWN BLOBS · LARGEST ${list.length}`),
    h("table", { class: "tbl sv-unk" }, h("tbody", {}, list.map((u) => h("tr", {},
      h("td", { class: "mono" }, u.file), h("td", { class: "mono num" }, fmtBytes(u.bytes)),
      h("td", {}, u.dense ? badge("DENSE", "err") : badge("STRUCTURED", "warn")), h("td", { class: "small" }, why(u)))))),
    !deep && list.some((u) => !u.dense) ? h("div", { class: "row sv-deep" }, btn("RUN DEEP SURVEY", onDeep, "sm"),
      h("span", { class: "dim small" }, "tries the carver on these blobs — slower")) : null];
}

const missingBlock = (tools) => (tools?.length ? h("div", { class: "alert warn" }, h("b", {}, "OPTIONAL TOOLS NOT INSTALLED · WOULD COVER MORE"),
  h("ul", { class: "mono" }, tools.map((t) => h("li", {}, t))),
  h("p", {}, h("a", { href: "#system" }, "Open 05 SYSTEM →"), " for what to install. Restart ViWo afterwards.")) : null);

export function gameCard(g, i, { deep, onExtract, onDeep }) {
  const name = g.path.split(/[\\/]/).filter(Boolean).pop() || g.path;
  const order = Object.keys(CATS);
  const cats = Object.entries(g.categories || {}).sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]));
  const total = cats.reduce((s, [, c]) => s + c.bytes, 0);
  const data = dataBytes(g);
  const cov = Number(g.coverage || 0);
  const engine = g.engine === "generic" ? badge("NO ENGINE MATCH", "mute")
    : badge(`${g.engine.toUpperCase()} · ${Math.round(g.confidence * 100)}%`, "red");
  const card = panel(`07.${pad(i + 1)}`, name, [engine, btn("EXTRACT →", () => onExtract(g.path), "sm", { "aria-label": `Extract ${name}` })],
    h("code", { class: "mono path dim" }, g.path),
    h("div", { class: "cov" }, h("b", { class: `mono ${covKind(cov)}` }, pct(cov)),
      h("div", {}, h("span", {}, "of its data ViWo can pull"),
        h("small", { class: "dim block" }, data ? `${fmtBytes(coveredBytes(g))} of ${fmtBytes(data)} · code and tiny files not counted` : "no data files found"))),
    meter(Math.floor(cov * 100) / 100, covKind(cov)),
    total ? [stackBar(cats, total), legend(cats)] : null,
    g.evidence?.length ? h("ul", { class: "evidence mono" }, g.evidence.map((e) => h("li", {}, e))) : null,
    unknownBlock(g.unknown, deep, onDeep),
    missingBlock(g.missingTools));
  card.classList.add("sv-card", "reveal");
  card.style.setProperty("--i", String(Math.min(i, 12)));
  return card;
}
