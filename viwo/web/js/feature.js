// An opt-in feature that is off, said where it is needed, with the switch right there: TURN ON writes
// the feature into startup.ini exactly as SETTINGS does (no restart), then the view carries on.
import { api } from "./api.js";
import { h, btn, busy, emit, toast, toastErr, alert } from "./ui.js";

export async function turnOn(feature) {
  const s = await api.settings();
  const features = [...new Set([...(s.startup?.features || []), feature])];
  const res = await api.saveSettings({ startup: { features } });
  if (res.success === false) throw Object.assign(new Error(res.error), res);
  emit("preflight");
  return res;
}

/** The "X IS OFF" notice with its switch; after(): what the view does once it is on. */
export function featureOff(title, why, feature, after = () => {}) {
  const on = btn("TURN ON", (e) => busy(e.currentTarget, async () => {
    try {
      await turnOn(feature);
      toast(`${title.replace(/ IS OFF$/, "")} is on.`, "ok", "Written to startup.ini; SETTINGS can turn it off again.");
      await after();
    } catch (err) { toastErr(err, "Not turned on: "); }
  }), "sm primary");
  return alert("warn", title, why, h("div", { class: "row" }, on, h("a", { href: "#settings", class: "small" }, "or open SETTINGS")));
}
