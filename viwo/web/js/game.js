// The shared game selector in the global strip: one game folder for every arm (read-only source).
// Views read it with currentGame(), write it with setGame(), and follow the "game" bus event.
import { api } from "./api.js";
import { h, pref, emit, bus, toastErr } from "./ui.js";

export const currentGame = () => pref("gamePath") || "";

export function setGame(path) {
  const value = String(path || "").trim();
  if (!value || value === currentGame()) return;
  pref("gamePath", value);
  emit("game", value);
}

export async function pickGame() {
  try {
    const res = await api.browse(currentGame());
    if (res.path) setGame(res.path);
  } catch (err) { toastErr(err); }
}

/** A game-folder input bound to the strip: shows the shared game, sets it on change. */
export function gameField(id) {
  const input = h("input", { class: "input mono grow", id, placeholder: "/path/to/game", value: currentGame(), spellcheck: "false",
    onchange: (e) => setGame(e.target.value) });
  followGame(input);
  return input;
}

/** Keep a view's own game field in step with the strip (unless the user is typing in it). */
export function followGame(input, after = null) {
  bus.addEventListener("game", (e) => {
    if (document.activeElement === input) return;
    input.value = e.detail;
    after?.(e.detail);
  });
}
