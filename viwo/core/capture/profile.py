"""profile.sample (doc 11.2, rung D4): where a running game spends its CPU time. The OS layer
samples every thread's instruction pointer (Windows: SuspendThread + GetThreadContext, no
administrator rights; Linux: perf); each sample is placed in its module and named after the
nearest export below it. Writes `.runtime/profile/<pid>-<time>/hotspots.json` and `.txt`:
the hottest addresses, modules and threads, as shares of all samples."""

import bisect
import json
import struct
from collections import Counter
from pathlib import Path

from viwo.contracts.errors import ViwoError

from ..patch_tools import pe, rva_to_offset


def exports(path: Path) -> list[tuple[int, str]]:
    """(rva, name) of a PE's named exports, sorted; [] when unreadable or not a PE."""
    try:
        data = path.read_bytes()
        head = struct.unpack_from("<I", data, 0x3C)[0]
        wide = struct.unpack_from("<H", data, head + 24)[0] == 0x20B
        rva = struct.unpack_from("<I", data, head + 24 + (112 if wide else 96))[0]
        if pe(data) is None or not rva:
            return []
        # IMAGE_EXPORT_DIRECTORY from +20: function count, name count, the three table RVAs
        _, count, funcs, names, ords = struct.unpack_from(
            "<5I", data, rva_to_offset(data, rva) + 20
        )
        out = []
        for i in range(count):
            at = rva_to_offset(
                data, struct.unpack_from("<I", data, rva_to_offset(data, names) + 4 * i)[0]
            )
            index = struct.unpack_from("<H", data, rva_to_offset(data, ords) + 2 * i)[0]
            func = struct.unpack_from("<I", data, rva_to_offset(data, funcs) + 4 * index)[0]
            out.append((func, data[at : data.index(b"\0", at)].decode("ascii", "replace")))
        return sorted(out)
    except (OSError, ValueError, ViwoError, struct.error):
        return []


def place(pc: int, modules: list[tuple[int, int, str]], names: dict) -> str:
    """module!export+0xoff, module+0xrva below every export, or the raw address."""
    for base, size, path in modules:
        if base <= pc < base + size:
            rva, table = pc - base, names.setdefault(path, exports(Path(path)))
            i = bisect.bisect_right(table, (rva, "￿")) - 1
            name = Path(path).name
            return f"{name}!{table[i][1]}+{rva - table[i][0]:#x}" if i >= 0 else f"{name}+{rva:#x}"
    return f"{pc:#x}"


def report(samples: list[tuple[int, int]], modules: list, top: int = 40) -> dict:
    names: dict = {}
    spots = Counter(place(pc, modules, names) for _, pc in samples)
    total = max(len(samples), 1)
    share = lambda n: round(100 * n / total, 2)  # noqa: E731
    by_module = Counter(spot.split("!")[0].split("+")[0] for spot in spots.elements())
    return {
        "samples": len(samples),
        "hotspots": [{"where": w, "percent": share(n)} for w, n in spots.most_common(top)],
        "modules": [{"module": m, "percent": share(n)} for m, n in by_module.most_common(top)],
        "threads": [
            {"tid": t, "percent": share(n)} for t, n in Counter(t for t, _ in samples).most_common()
        ],
    }


def text(rep: dict) -> str:
    lines = [f"{rep['samples']} samples"]
    for title, key in (("HOT SPOTS", "where"), ("MODULES", "module"), ("THREADS", "tid")):
        rows = rep[{"where": "hotspots", "module": "modules", "tid": "threads"}[key]]
        lines += ["", title, *(f"{r['percent']:6.2f}%  {r[key]}" for r in rows)]
    return "\n".join(lines) + "\n"


def profile(rt, req, cancel=None) -> dict:
    """Sample the process (req.pid or req.name) for req.seconds."""
    from .runtime import _enabled, resolve_pid, run_dir

    _enabled(rt)
    pid = resolve_pid(rt, req.pid, req.name)
    try:
        samples, modules = rt.os.sample_threads(pid, req.seconds, cancel)
    except OSError as exc:
        raise ViwoError("failed", f"cannot sample process {pid}: {exc}") from exc
    if not samples:
        raise ViwoError("failed", f"no sample of process {pid}: it exited or refused access")
    rep = report(samples, modules)
    out = run_dir(req.workspace, "profile", pid)
    (out / "hotspots.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    (out / "hotspots.txt").write_text(text(rep), encoding="utf-8")
    top = rep["hotspots"][0]
    return {"pid": pid, "samples": rep["samples"], "top": f"{top['where']} ({top['percent']}%)",
            "outputDir": str(out)}  # fmt: skip
