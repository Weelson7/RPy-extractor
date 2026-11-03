// Theme = one stylesheet of tokens (css/themes/<name>.css) on top of css/base.css (structure).
// The choice is a client preference; nothing in the views knows which theme is active.
import { $, pref, emit } from "./ui/dom.js";

export const THEMES = { wormhole: "WORMHOLE", plain: "PLAIN" };

export function setTheme(name) {
  const theme = name in THEMES ? name : "wormhole";
  document.documentElement.dataset.theme = theme;
  const link = $("#theme-link");
  if (link) link.href = `css/themes/${theme}.css`;
  pref("theme", theme);
  emit("theme", theme);
  return theme;
}

export const currentTheme = () => document.documentElement.dataset.theme || pref("theme") || "wormhole";
