// SORT's 3D preview: a glTF or GLB file in <model-viewer>, the pinned script this machine serves
// from third_party/ (/vendor/). Drag to orbit, wheel to zoom; a skinned model shows in its bind pose.
import { h, fill, errorBox } from "../ui.js";

let viewer = null; // the script's import, once

/** The stage for a model. A missing viewer or a file it cannot read is said in its place; a model
 * packed with Draco, Basis or meshopt (`packed`, read by the server) says the viewer goes online. */
export function modelStage(url, cap, name, packed = []) {
  const fig = h("figure", { class: "media", "data-kind": "mdl" }, cap);
  const failed = (message, hint) => fig.replaceChildren(errorBox({ code: "unavailable", message, hint }, "NO 3D PREVIEW"), cap);
  const online = packed.length ? h("p", { class: "note small dim" }, `Packed with ${packed.join(", ")}: the viewer fetches its decoder from the internet to show it.`) : null;
  viewer ||= import("/vendor/model-viewer.min.js");
  viewer.then(() => fill(fig, h("model-viewer", { src: url, alt: name, "camera-controls": true, "shadow-intensity": "0.7",
    onerror: () => failed(`The viewer could not read ${name}`, "A .gltf that keeps its buffers or textures in other files cannot load from here: a .glb holds everything") }), online, cap),
  () => { viewer = null; failed("The 3D viewer could not be loaded", "ViWo installs it by itself on first use (1 MB, pinned): check the connection and that auto_install is on in SETTINGS, then select the file again"); });
  return fig;
}
