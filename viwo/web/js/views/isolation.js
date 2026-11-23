// RUNTIME > ISOLATION PATCHER (doc 11.8, T4): a guest behind VirtualBox, QEMU or DRAKVUF/LibVMI,
// started with its options (memory, CPUs, accelerator, network, UEFI + TPM, a shared folder), the
// program found inside it (LOCATE), the same patch set as PATCHES written live and undone, and
// the guest's RAM or the located program dumped. Every option of `viwo isolate` is here.
import { api } from "../api.js";
import { h, fill, btn, panel, badge, kv, toast, pref, fileBtn, browseBtn, prefInput as input, errorBox, busy, table, toggle } from "../ui.js";

const el = {};
const FLAGS = [["network", "NETWORK", "NAT; off by default"], ["headless", "NO WINDOW", "the guest runs unseen"],
  ["efi", "UEFI + TPM", "VirtualBox adds a virtual TPM 2.0"], ["gpu", "3D", "VirtualBox: the host GPU"], ["snapshot", "SNAPSHOT", "at start, and before each patch"],
  ["fresh", "FRESH DISK", "discard the earlier session's disk"]];

function choice(id, key, values) {
  return h("select", { class: "input", id, onchange: (e) => pref(key, e.target.value) },
    values.map(([v, label]) => h("option", { value: v, selected: (pref(key) || "") === v }, label)));
}

function number(id, key, fallback, min = "1") {
  return h("input", { class: "input mono", id, type: "number", min, value: pref(key) || fallback, oninput: (e) => pref(key, e.target.value) });
}

const label = (id, text) => h("label", { class: "lbl", for: id }, text);

export function isolationPanel(tag) {
  el.tiers = h("div", {}, h("p", { class: "dim" }, "LIST TIERS shows the isolation boundaries (VirtualBox, QEMU, DRAKVUF/LibVMI) and whether each can run here."));
  el.tier = choice("iso-tier", "isoTier", [["", "first ready"], ["vbox", "T1 VirtualBox"], ["qemu", "T2 QEMU"], ["libvmi", "T3 DRAKVUF/LibVMI"]]);
  el.accel = choice("iso-accel", "isoAccel", [["", "picked (hardware, else TCG)"], ["whpx", "WHPX"], ["kvm", "KVM"], ["tcg", "TCG"]]);
  el.image = input("iso-image", "/path/to/guest-disk.qcow2 or an installer .iso", "rtImage");
  el.memory = number("iso-memory", "isoMemory", "4096");
  el.cpus = number("iso-cpus", "isoCpus", "2");
  el.share = input("iso-share", "a folder the guest reads (optional)", "isoShare");
  el.domain = input("iso-domain", "T3: the running Xen/KVM domain to attach", "isoDomain");
  el.kvmi = input("iso-kvmi", "T3 on KVM: its KVMi socket", "isoKvmi");
  el.process = input("iso-process", "Game.exe or a pid (empty: list them)", "isoProcess");
  el.exe = input("iso-exe", "/path/to/the program the patch set is located in", "isoExe");
  el.patch = input("iso-patch", "/path/to/set.patch.json", "isoPatch");
  el.base = input("iso-base", "module base (optional: LOCATE gives it)", "isoBase");
  el.name = input("iso-name", "snapshot / dump name (optional)", "isoName");
  el.guestDir = input("iso-gdir", "the program's folder inside the guest", "isoGuestDir");
  el.guestUser = input("iso-guser", "guest account (VirtualBox)", "isoGuestUser");
  el.guestPass = h("input", { class: "input mono", id: "iso-gpass", type: "password", autocomplete: "off", placeholder: "its password (not kept)" });
  el.wait = number("iso-wait", "isoWait", "0", "0");
  el.hold = number("iso-hold", "isoHold", "0", "0");
  el.flags = Object.fromEntries(FLAGS.map(([k]) => [k, pref(`iso_${k}`) === "1"]));
  el.out = h("div", {});
  const act = (a, text, kind = "") => btn(text || a.toUpperCase(), (e) => busy(e.currentTarget, () => session(a)), kind);
  return panel(`${tag}.F`, "ISOLATION PATCHER", badge("COLD + LIVE", "warn"),
    h("p", { class: "note" }, "Run the target in a guest behind an isolation boundary: the image you give is never written (the guest boots an overlay or a copy), the guest has no network unless you start it with one, LOCATE finds the program inside the guest (its modules and their live addresses), and the same patch set you apply cold (PATCHES) is written live into that program (suspend, write, verify, resume) and journalled, so UNDO puts every byte back. A tier that cannot run here says what it needs."),
    h("div", { class: "row" }, btn("LIST TIERS", (e) => busy(e.currentTarget, listTiers), "")), el.tiers,
    label("iso-image", "GUEST IMAGE (DISK, OR AN INSTALLER .ISO)"), h("div", { class: "row" }, el.image, fileBtn(el.image, (p) => pref("rtImage", p))),
    h("div", { class: "row" }, h("div", { class: "col" }, label("iso-tier", "TIER"), el.tier), h("div", { class: "col" }, label("iso-accel", "ACCELERATOR (QEMU)"), el.accel),
      h("div", { class: "col" }, label("iso-memory", "MEMORY (MB)"), el.memory), h("div", { class: "col" }, label("iso-cpus", "CPUS"), el.cpus)),
    h("div", { class: "row wrap" }, FLAGS.map(([k, title, hint]) => toggle(`iso-${k}`, title, hint, el.flags[k], (on) => { el.flags[k] = on; pref(`iso_${k}`, on ? "1" : "0"); }))),
    label("iso-domain", "DOMAIN (T3 ATTACHES TO A RUNNING ONE)"), h("div", { class: "row" }, el.domain, el.kvmi),
    label("iso-share", "SHARED FOLDER (READ-ONLY IN THE GUEST)"), h("div", { class: "row" }, el.share, browseBtn(el.share, (p) => pref("isoShare", p))),
    h("div", { class: "row" }, act("start", "START", "primary"), ...["status", "pause", "resume", "snapshot", "rollback", "stop"].map((a) => act(a))),
    label("iso-name", "NAME"), h("div", { class: "row" }, el.name),
    label("iso-process", "PROGRAM IN THE GUEST"), h("div", { class: "row" }, el.process, act("locate"), act("dump", "DUMP RAM"), act("program", "DUMP PROGRAM")),
    label("iso-exe", "PATCH SET AND THE PROGRAM IT IS LOCATED IN"), h("div", { class: "row" }, el.exe, fileBtn(el.exe, (p) => pref("isoExe", p))),
    h("div", { class: "row" }, el.patch, fileBtn(el.patch, (p) => pref("isoPatch", p))),
    h("div", { class: "row" }, h("div", { class: "col" }, label("iso-wait", "WAIT FOR PAGES (S)"), el.wait),
      h("div", { class: "col" }, label("iso-hold", "HOLD AGAINST REVERTS (S)"), el.hold)),
    h("div", { class: "row" }, el.base, act("patch", "PATCH", "primary"), act("undo")),
    label("iso-gdir", "COLD, INSIDE THE GUEST: THE SAME SET WRITTEN INTO THE GUEST'S OWN FILES"),
    h("div", { class: "row" }, el.guestDir), h("div", { class: "row" }, el.guestUser, el.guestPass),
    h("div", { class: "row" }, act("deploy", "PATCH GUEST FILES"), act("restore", "RESTORE GUEST FILES")), el.out);
}

async function listTiers() {
  try {
    const res = await api.isolationTiers();
    fill(el.tiers, table([{ key: "tier", label: "TIER" }, { key: "ready", label: "READY" }, { key: "need", label: "REQUIREMENT / WALL" }],
      res.tiers.map((t) => ({
        tier: h("span", { class: "mono" }, `T${t.tier} ${t.backend}`),
        ready: badge(t.ready ? "READY" : "NOT READY", t.ready ? "ok" : "warn"),
        need: h("span", { class: "note" }, t.ready ? "—" : (t.detail || t.requirement)),
      })), { caption: "Isolation tiers" }));
  } catch (err) { fill(el.tiers, errorBox(err, "LISTING FAILED")); }
}

/** The request body of one action: start carries the guest options, the rest what they act on. */
function body(action) {
  const v = (field) => field.value.trim();
  if (action === "start") {
    return { action, image: v(el.image), tier: el.tier.value, accel: el.accel.value, memory: Number(v(el.memory)) || 0,
      cpus: Number(v(el.cpus)) || 0, share: v(el.share) || null, domain: v(el.domain) || null, kvmiSocket: v(el.kvmi) || null, ...el.flags };
  }
  if (action === "program") return { action: "dump", program: true, name: v(el.name) || null };
  if (action === "locate") return { action, process: v(el.process) };
  if (action === "deploy" || action === "restore") {
    return { action, patchSet: v(el.patch), guestDir: v(el.guestDir), guestUser: v(el.guestUser), guestPassword: el.guestPass.value };
  }
  if (action === "patch") {
    return { action, exePath: v(el.exe), patchSet: v(el.patch), base: v(el.base) || null, snapshot: el.flags.snapshot,
      wait: Number(v(el.wait)) || 0, hold: Number(v(el.hold)) || 0 };
  }
  return { action, name: v(el.name) || null };
}

function why(action) {
  if (action === "start" && !el.image.value.trim() && !el.domain.value.trim()) return "enter the guest image (or a T3 domain)";
  if (action === "patch" && (!el.exe.value.trim() || !el.patch.value.trim())) return "enter the program and its patch set";
  if ((action === "deploy" || action === "restore") && !el.guestDir.value.trim()) return "enter the program's folder inside the guest";
  if (action === "deploy" && !el.patch.value.trim()) return "enter the patch set";
  return "";
}

async function session(action) {
  const blocked = why(action);
  if (blocked) return toast(`Cannot ${action}: ${blocked}.`, "warn");
  if (action === "locate" || action === "program") fill(el.out, h("p", { class: "dim" }, "Dumping the guest's RAM and reading it with Volatility; this takes a while on a large guest."));
  try {
    show(await api.isolate(body(action)));
  } catch (err) { fill(el.out, errorBox(err, `${action.toUpperCase()} FAILED`)); }
}

function show(res) {
  if (res.processes) {
    return fill(el.out, table([{ key: "pid", label: "PID", kind: "num" }, { key: "program", label: "PROGRAM" }, { key: "modules", label: "MODULES", kind: "num" }],
      res.processes.map((p) => ({ pid: String(p.pid), program: h("span", { class: "mono" }, p.program), modules: String(p.modules) })), { caption: "Processes in the guest" }));
  }
  const flat = { ...res, ...(res.located || {}) };
  const shown = Object.entries(flat).filter(([k, v]) => k !== "success" && v !== null && typeof v !== "object");
  const results = (res.results || []).map((r) => kv(String(r.name || r.id || r.offset), `${r.status}${r.written ? " · written" : ""}${r.detail ? ` · ${r.detail}` : ""}`));
  fill(el.out, shown.map(([k, v]) => kv(k.toUpperCase(), h("span", { class: "mono" }, String(v)))), results, (res.files || []).length ? h("p", { class: "note mono" }, res.files.join(", ")) : null);
}
