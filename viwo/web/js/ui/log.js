// Log components: coloured lines and a scrolling log view that sticks to the bottom.
import { h } from "./dom.js";

/** Map a log line to a level for console colouring (data-level on the line). */
export function lineLevel(line, level = "") {
  const s = `${level} ${line}`.toLowerCase();
  if (/game folder changed|error|fail|refused/.test(s)) return "err";
  if (/warn|unavailable|skip/.test(s)) return "warn";
  if (/✓|complete|done|succeeded|success/.test(s)) return "ok";
  return "";
}

export const logLine = (text, level = "") => h("span", { class: "ln", "data-level": lineLevel(text, level) || null }, text, "\n");

/** A <pre> log; `kind` = feed | mini | short | events. push(text, level) keeps it scrolled when at the bottom. */
export function logView(kind = "feed", extra = {}) {
  const pre = h("pre", { class: "log", "data-kind": kind, ...extra });
  pre.push = (text, level = "") => {
    const stick = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 40;
    pre.append(logLine(text, level));
    if (stick) pre.scrollTop = pre.scrollHeight;
  };
  pre.clear = () => pre.replaceChildren();
  return pre;
}
