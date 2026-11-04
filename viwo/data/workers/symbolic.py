"""ViWo worker for analysis.symbolic (doc 6.2, rung A4): the inputs that make one routine of a
binary reach an address, solved by angr. ViWo runs it as its own process and never imports it
(angr runs on Unicorn and z3):
    python -I symbolic.py --lib <third_party/angr> <spec.json> <out folder>
`sym:<n>` arguments are n symbolic bytes passed by pointer; the others are concrete. The worker
explores from `start` to `find` (never through `avoid`) and writes result.json with the solved
bytes of every symbolic argument (and one argN.bin each)."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def address(text: str, proj) -> int:
    kind, _, value = str(text).partition(":")
    if kind == "rva":
        return proj.loader.main_object.mapped_base + int(value, 0)
    if kind == "export":
        symbol = proj.loader.find_symbol(value)
        if symbol is None:
            raise ValueError(f"no export {value!r} in {Path(proj.filename).name}")
        return symbol.rebased_addr
    return int(text, 0)


def arguments(angr, claripy, args: list[dict]) -> tuple[list, list]:
    """The call's arguments (buffers by pointer) and the symbolic ones to solve."""
    values, symbolic = [], []
    for i, arg in enumerate(args):
        if "int" in arg:
            values.append(arg["int"])
            continue
        if "sym" in arg:
            bvs = claripy.BVS(f"arg{i}", arg["sym"] * 8)
            symbolic.append((i, bvs))
            values.append(angr.PointerWrapper(bvs, buffer=True))
            continue
        if "hex" in arg:
            body = bytes.fromhex(arg["hex"])
        else:
            body = Path(arg["file"]).read_bytes() if "file" in arg else b"\0" * arg["zeros"]
        values.append(angr.PointerWrapper(body, buffer=True))
    return values, symbolic


def run(spec: dict, out: Path) -> dict:
    import angr
    import claripy

    proj = angr.Project(spec["binary"], auto_load_libs=False)
    values, symbolic = arguments(angr, claripy, spec["args"])
    if not symbolic:
        raise ValueError("give at least one sym:<n> argument to solve")
    zero = {
        angr.options.ZERO_FILL_UNCONSTRAINED_MEMORY,
        angr.options.ZERO_FILL_UNCONSTRAINED_REGISTERS,
    }
    state = proj.factory.call_state(address(spec["start"], proj), *values, add_options=zero)
    simgr = proj.factory.simulation_manager(state)
    find = address(spec["find"], proj)
    simgr.explore(find=find, avoid=[address(a, proj) for a in spec["avoid"]])
    if not simgr.found:
        ended, avoided = len(simgr.deadended), len(simgr.stashes.get("avoid", []))
        reason = f"no path reaches {find:#x} ({ended} ended, {avoided} avoided)"
        return {"status": "not_found", "reason": reason}
    found, solutions, files = simgr.found[0], {}, []
    for i, bvs in symbolic:
        data = found.solver.eval(bvs, cast_to=bytes)
        (out / f"arg{i}.bin").write_bytes(data)
        solutions[f"arg{i}"], files = data.hex(), [*files, f"arg{i}.bin"]
    shown = ", ".join(f"{k}={v}" for k, v in solutions.items())
    return {"status": "found", "reason": f"reached {find:#x} with {shown}", "solutions": solutions,
            "files": files}  # fmt: skip


def main(argv: list[str]) -> int:
    lib, spec_file, out = argv[argv.index("--lib") + 1], argv[-2], Path(argv[-1])
    sys.path.insert(0, lib)
    out.mkdir(parents=True, exist_ok=True)
    try:
        report = run(json.loads(Path(spec_file).read_text(encoding="utf-8")), out)
    except Exception as exc:  # noqa: BLE001 (never silent: any failure is the report)
        report = {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}
    (out / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"symbolic: {report['status']}: {report.get('reason', '')}")
    return 0 if report["status"] == "found" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
