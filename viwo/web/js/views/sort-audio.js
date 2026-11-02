// SORT audio stage: themed player (play/pause, scrub, time) + real waveform via the Web Audio API.
import { h, fill } from "../ui.js";

const BARS = 64;
const MAX_BYTES = 20 * 1024 * 1024; // larger files keep the flat line instead of being decoded
let decoder = null;

const clock = (s) => `${Math.floor((s || 0) / 60)}:${((s || 0) % 60).toFixed(1).padStart(4, "0")}`;

/** Peak amplitude per bar, normalised to 0..1. Throws when the file is too large or undecodable. */
async function peaks(url) {
  const res = await fetch(url);
  if (!res.ok || Number(res.headers.get("content-length") || 0) > MAX_BYTES) throw new Error("not decodable here");
  const buf = await res.arrayBuffer();
  if (buf.byteLength > MAX_BYTES) throw new Error("too large");
  decoder ||= new OfflineAudioContext(1, 1, 44100);
  const data = (await decoder.decodeAudioData(buf)).getChannelData(0);
  const step = Math.max(1, Math.floor(data.length / BARS));
  const out = Array.from({ length: BARS }, (_, b) => {
    let peak = 0;
    for (let i = b * step, end = Math.min(data.length, i + step); i < end; i += 8) peak = Math.max(peak, Math.abs(data[i]));
    return peak;
  });
  const top = Math.max(...out, 1e-6);
  return out.map((v) => v / top);
}

export function audioStage(url, cap) {
  const audio = h("audio", { src: url, preload: "metadata" });
  const wave = h("div", { class: "wave flat", role: "img", "aria-label": "Waveform loading" });
  const play = h("button", { type: "button", class: "btn primary play", "aria-label": "Play" }, "▶");
  const scrub = h("input", { type: "range", class: "scrub", min: 0, max: 1000, value: 0, "aria-label": "Seek" });
  const time = h("span", { class: "mono time" }, "0:00 / 0:00");
  const sync = () => {
    const d = audio.duration || 0;
    const p = d ? audio.currentTime / d : 0;
    time.textContent = `${clock(audio.currentTime)} / ${clock(d)}`;
    if (document.activeElement !== scrub) scrub.value = String(Math.round(p * 1000));
    wave.style.setProperty("--p", `${p * 100}%`);
  };
  const state = () => {
    play.textContent = audio.paused ? "▶" : "❚❚";
    play.setAttribute("aria-label", audio.paused ? "Play" : "Pause");
  };
  const seek = (frac) => { if (audio.duration) audio.currentTime = Math.min(1, Math.max(0, frac)) * audio.duration; };
  play.addEventListener("click", () => (audio.paused ? audio.play().catch(() => {}) : audio.pause()));
  scrub.addEventListener("input", () => seek(scrub.value / 1000));
  wave.addEventListener("click", (e) => { const r = wave.getBoundingClientRect(); seek((e.clientX - r.left) / r.width); });
  ["timeupdate", "loadedmetadata", "seeked"].forEach((ev) => audio.addEventListener(ev, sync));
  ["play", "pause", "ended"].forEach((ev) => audio.addEventListener(ev, state));
  peaks(url).then((list) => {
    wave.classList.remove("flat");
    wave.setAttribute("aria-label", "Waveform");
    fill(wave, list.map((v) => h("i", { style: `height:${Math.max(3, Math.round(v * 100))}%` })));
  }, () => wave.setAttribute("aria-label", "Waveform unavailable for this file"));
  return h("figure", { class: "media aud" }, wave, h("div", { class: "player" }, play, scrub, time), audio, cap);
}
