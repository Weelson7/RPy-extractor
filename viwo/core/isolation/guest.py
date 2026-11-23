"""Programs inside a guest (doc 11.8): find a process in the guest OS, address its memory whichever
process the vCPU runs, and dump its program as files. The OS knowledge is Volatility 3's (a
worker: a pinned package run as its own process over a RAM image of the guest, with ViWo's
`viwo_guest.Guest` plugin); the address translation is the x86 page walk (paging.py) done live
over the tier's physical memory. `locate` dumps the guest RAM, asks Volatility for the processes,
their page-table roots and every file mapped in them, and keeps the chosen one as the session's
view (`view.json`); later patches go through that process's address space and take each module's
live base from it (ASLR), so `--base` is no longer needed. Nothing here depends on what language
the program is written in: every file-backed mapping is a module."""

import json
import time
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.contracts.patcher import MemoryFault, PatchSession, Wall, WallReport
from viwo.contracts.types import DependencySpec, OutcomeKind

from . import paging

WORKER = "volatility3"
HEADERS = (b"MZ", bytes.fromhex("7f45"))  # the first bytes of a PE and an ELF image
VOLATILITY = DependencySpec.of(WORKER)  # declared by every tier: `viwo install volatility3`
DUMPERS = {"windows": "windows.dlllist", "linux": "linux.elfs"}  # Volatility's own module dumps
VIEW = "view.json"
NO_PHYS = "this tier cannot reach guest physical memory, so no guest process can be addressed"


class ProcessView(PatchSession):
    """One guest process's address space over a session's physical memory. Everything but the
    memory I/O is the session's own."""

    def __init__(self, inner: PatchSession, view: dict) -> None:
        self.inner, self.view = inner, view
        self.dtb, self.mode = int(view["dtb"]), str(view.get("mode") or "x64")
        self._wall = WallReport()

    def tag(self) -> dict:
        """What a journal entry keeps so undo reaches the same address space later."""
        return {"pid": self.view.get("pid"), "dtb": self.dtb, "mode": self.mode}

    def _access(self, act):
        phys = self.inner.physical()
        if phys is None:
            return WallReport(Wall.NOT_READY, NO_PHYS), None
        try:
            with phys as mem:
                return WallReport(), act(mem)
        except paging.NotResident as exc:
            hint = "use that part of the program in the guest so it is loaded, then retry"
            return WallReport(Wall.NOT_READY, f"{exc}; {hint}"), None
        except MemoryFault as exc:
            return WallReport(Wall.NOT_READY, f"process {self.view.get('pid')}: {exc}"), None

    def read_mem(self, addr: int, size: int) -> bytes:
        def read(mem):
            spans = paging.spans(mem.read, self.dtb, addr, size, self.mode)
            return b"".join(mem.read(pa, n) for pa, n in spans)

        self._wall, data = self._access(read)
        return data or b""

    def write_mem(self, addr: int, data: bytes) -> WallReport:
        def write(mem):
            at = 0
            for pa, n in paging.spans(mem.read, self.dtb, addr, len(data), self.mode):
                mem.write(pa, data[at : at + n])
                at += n

        self._wall, _ = self._access(write)
        return self._wall

    def suspend(self) -> None:
        self.inner.suspend()

    def resume(self) -> None:
        self.inner.resume()

    def snapshot(self, name: str):
        return self.inner.snapshot(name)

    def rollback(self, name: str):
        return self.inner.rollback(name)

    def dump(self, out: Path):
        return self.inner.dump(out)

    def wall(self) -> WallReport:
        return self._wall

    def physical(self):
        return self.inner.physical()

    def record(self) -> dict:
        return self.inner.record()

    def alive(self) -> bool:
        return self.inner.alive()

    def release(self) -> None:
        self.inner.release()

    def close(self) -> None:
        self.inner.close()


def load(where: Path) -> dict | None:
    try:
        return json.loads((where / VIEW).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def drop(where: Path) -> None:
    (where / VIEW).unlink(missing_ok=True)


def view(session: PatchSession, where: Path) -> PatchSession:
    """The located process's view of `session`, or the session itself when none was located."""
    found = load(where)
    return ProcessView(session, found) if found else session


def pinned(session: PatchSession) -> PatchSession:
    """`session` itself when it is a process view or cannot say its vCPU's paging; else vCPU 0's
    address space as it is now, so an edit, its readbacks and its undo stay in one process."""
    if isinstance(session, ProcessView):
        return session
    cpu = session.cpu_paging()
    return ProcessView(session, {"pid": 0, **cpu}) if cpu else session


def bound(session: PatchSession, entry: dict) -> PatchSession:
    """The address space a journal entry was written in (its own dtb), for undo."""
    if "dtb" not in entry:
        return session
    inner = session.inner if isinstance(session, ProcessView) else session
    return ProcessView(inner, {"pid": entry.get("pid"), "dtb": entry["dtb"], "mode": entry["mode"]})


def bases(where: Path) -> dict[str, int]:
    """Module file name (lower case) -> live base in the located process; {} when none."""
    found = load(where) or {}
    return {m["name"].lower(): int(m["base"]) for m in found.get("modules", ()) if m.get("name")}


def _worker(rt, log) -> tuple[str, ...]:
    from .. import workers
    from ..thirdparty import home_of

    home = home_of(rt.config)
    argv = workers.argv(WORKER, home)
    if argv is None:
        log(
            "Installing Volatility 3 (pinned, into third_party/) for the first guest lookup", "info"
        )
        workers.install(WORKER, home, rt.os.process)
        argv = workers.argv(WORKER, home)
    if argv is None:
        raise ViwoError("unavailable", "Volatility 3 could not be installed", hint="viwo install")
    return (*argv, "--cache", str(workers.folder(home, WORKER) / "cache"))


def volatility(rt, session, where: Path, args: list[str], log) -> list:
    """Dump the guest's RAM beside the session, run Volatility on it, remove the image."""
    argv = _worker(rt, log)
    ram = where / "guest-ram.elf"
    where.mkdir(parents=True, exist_ok=True)
    ram.unlink(missing_ok=True)  # one left by a run that died (a tier may refuse to overwrite)
    log(f"Dumping the guest's RAM to {ram}", "info")
    done = session.dump(ram)
    if done.kind is not OutcomeKind.OK or not ram.is_file():
        ram.unlink(missing_ok=True)
        raise ViwoError("failed", f"the guest RAM dump failed: {done.error or 'no file'}")
    began = time.monotonic()
    log(f"Volatility reads {ram.stat().st_size >> 20} MB of guest RAM ({args[0]}); a kernel "
        "seen for the first time has its symbols fetched from Microsoft", "info")  # fmt: skip
    try:
        result = rt.os.process.run([*argv, "-q", "-r", "json", "-f", str(ram), *args], timeout=3600)
    finally:
        ram.unlink(missing_ok=True)
    log(f"Volatility done in {time.monotonic() - began:.0f} s; the RAM image is removed", "info")
    try:
        return json.loads(result.stdout or "") if result.ok else _failed(result)
    except ValueError:
        return _failed(result)


def _failed(result):
    tail = (result.stderr or result.stdout or "no output").strip()[-300:]
    hint = "the guest's OS must be one Volatility knows (its kernel symbols)"
    raise ViwoError("failed", f"Volatility could not read the guest: {tail}", hint=hint)


def processes(rows: list) -> list[dict]:
    """Volatility's rows (one per module) grouped into processes."""
    out: dict[int, dict] = {}
    for row in rows:
        pid = int(row["PID"])
        head = {"pid": pid, "process": row["Process"], "os": row["OS"], "mode": row["Mode"]}
        proc = out.setdefault(pid, {**head, "dtb": int(row["DTB"]), "modules": []})
        if row.get("Module"):
            module = {"name": row["Module"], "base": int(row["Base"]), "size": int(row["Size"])}
            proc["modules"].append({**module, "path": row.get("Path") or ""})
    return list(out.values())


def main(proc: dict) -> str:
    """The process's own program file: the first module the loader lists."""
    return proc["modules"][0]["name"] if proc["modules"] else proc["process"]


def pick(procs: list[dict], want: str) -> dict:
    """The one process `want` names: a pid, or a program name (the kernel keeps 14 characters
    of it, so a longer name matches its start)."""
    low = want.lower()
    hits = [p for p in procs if str(p["pid"]) == want] if want.isdigit() else [
        p for p in procs if low in (p["process"].lower(), main(p).lower())
        or (len(p["process"]) >= 14 and low.startswith(p["process"].lower()))
    ]  # fmt: skip
    if len(hits) == 1:
        return hits[0]
    if not hits:
        names = ", ".join(sorted({main(p) for p in procs})[:30])
        raise ViwoError("not_found", f"no process {want!r} in the guest", hint=names)
    pids = ", ".join(str(p["pid"]) for p in hits)
    raise ViwoError("invalid_request", f"{len(hits)} processes match {want!r}: pid {pids}",
                    hint="give the pid")  # fmt: skip


def _shared(proc: dict, procs: list[dict]) -> dict:
    """Each module of `proc` with how many other processes map the same file."""
    users: dict[str, int] = {}
    for other in procs:
        if other is not proc:
            for path in {m["path"].lower() for m in other["modules"] if m.get("path")}:
                users[path] = users.get(path, 0) + 1
    for module in proc["modules"]:
        module["shared"] = users.get((module.get("path") or "").lower(), 0)
    return proc


def present(session, view: dict) -> bool:
    """Whether the located program's own image still starts where it was located (an image
    header at its base): False once it exited or restarted somewhere else."""
    if not view.get("modules"):
        return True
    head = ProcessView(session, view).read_mem(int(view["modules"][0]["base"]), 2)
    return head in HEADERS


def locate(rt, session, where: Path, want: str, log) -> dict:
    """List the guest's processes (no `want`), or keep the one `want` names as the view."""
    if session.physical() is None:
        raise ViwoError("unavailable", NO_PHYS)
    procs = processes(volatility(rt, session, where, ["viwo_guest.Guest"], log))
    if not want:
        drop(where)
        brief = [{"pid": p["pid"], "program": main(p), "modules": len(p["modules"])} for p in procs]
        return {"processes": brief}
    proc = _shared(pick(procs, want), procs)
    (where / VIEW).write_text(json.dumps(proc, indent=1), encoding="utf-8")
    log(f"Located {main(proc)} (pid {proc['pid']}, {len(proc['modules'])} modules)", "info")
    first = proc["modules"][0] if proc["modules"] else {"base": 0}
    head = {"pid": proc["pid"], "program": main(proc), "os": proc["os"], "mode": proc["mode"]}
    return {"located": {**head, "base": hex(first["base"]), "modules": len(proc["modules"])}}


def program(rt, session, where: Path, out: Path, log) -> dict:
    """Every module of the located process written out as files (Volatility's own dumper)."""
    found = load(where)
    if found is None:
        raise ViwoError("invalid_request", "locate the program first", hint="isolate locate NAME")
    out.mkdir(parents=True, exist_ok=True)
    pid = str(found["pid"])
    dumper = DUMPERS[found.get("os", "windows")]
    volatility(rt, session, where, ["-o", str(out), dumper, "--pid", pid, "--dump"], log)
    files = sorted(p.name for p in out.iterdir() if p.is_file())
    if not files:
        log(f"Volatility wrote no module of pid {pid} (pages not resident?)", "warn")
    return {"program": main(found), "pid": found["pid"], "folder": str(out), "files": files}
