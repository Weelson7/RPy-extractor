"""L3: rung A4, analysis.emulate. Synthetic PE32+ and ELF64 binaries with hand-assembled routines
run through the real Unicorn worker (a separate process, as in production); checks are properties
over random inputs: the decoded buffer is the XOR the routine computes, the return value comes
back, a call into an import stops and is named, the budget holds, a fault says why."""

from __future__ import annotations

import json
import os
import random
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from viwo.contracts.errors import ViwoError
from viwo.core import workers
from viwo.core.analysis.emulate import worker_spec

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "third_party" / "unicorn"
SCRIPT = workers.SCRIPTS / "emulate.py"
# Win64 xor_decode(buf=rcx, len=rdx, key=r8b): buf[i] ^= key; return 42
XOR_WIN64 = bytes.fromhex("4885d2740b44300148ffc148ffca75f5b82a000000c3")
# SysV xor_decode(buf=rdi, len=rsi, key=dl): the same routine
XOR_SYSV = bytes.fromhex("4885f6740a301748ffc748ffce75f6b82a000000c3")
CALL_IMPORT = bytes.fromhex("ff151a100000c3")  # at .text+0x40: call [rip -> IAT slot]; ret
SPIN = bytes.fromhex("ebfe")  # at .text+0x60: jmp $
NULL_READ = bytes.fromhex("488b042500000000c3")  # at .text+0x70: mov rax, [0]; ret
# at .text+0x80, Win64 check(key=rcx): 1 when key[0:4] == b"VIWO" (at +0x17), else 0 (+0x1D)
CHECK = bytes.fromhex("803956751880790149751280790257750c8079034f7506b801000000c331c0c3")
BASE = 0x140000000


def pe64() -> bytes:
    """A PE32+ DLL: .text (0x1000) with the routines, .rdata (0x2000) with one import
    (KERNEL32!Sleep, IAT at 0x2060) and one export (xor_decode -> 0x1000)."""
    text = bytearray(0x200)
    for at, code in (
        (0, XOR_WIN64),
        (0x40, CALL_IMPORT),
        (0x60, SPIN),
        (0x70, NULL_READ),
        (0x80, CHECK),
    ):
        text[at : at + len(code)] = code
    rdata = bytearray(0x200)
    put = lambda at, data: rdata.__setitem__(slice(at, at + len(data)), data)  # noqa: E731
    put(0x00, struct.pack("<IIIII", 0x2040, 0, 0, 0x20A0, 0x2060))  # import descriptor
    put(0x40, struct.pack("<QQ", 0x2080, 0))  # lookup table
    put(0x60, struct.pack("<QQ", 0x2080, 0))  # address table (the slot the call reads)
    put(0x80, b"\0\0Sleep\0")
    put(0xA0, b"KERNEL32.dll\0")
    put(0x100, struct.pack("<IIHHIIIIIII", 0, 0, 0, 0, 0x2160, 1, 1, 1, 0x2130, 0x2140, 0x2150))
    put(0x130, struct.pack("<I", 0x1000) + b"\0" * 12 + struct.pack("<I", 0x2170))
    put(0x150, struct.pack("<H", 0) + b"\0" * 14 + b"test.dll\0" + b"\0" * 7 + b"xor_decode\0")
    coff = struct.pack("<HHIIIHH", 0x8664, 2, 0, 0, 0, 0xF0, 0x2022)  # x64 DLL, 2 sections
    opt = struct.pack(
        "<HBBIIIIIQIIHHHHHHIIIIHHQQQQII",
        *(0x20B, 14, 0, 0x200, 0x200, 0, 0x1000, 0x1000, BASE, 0x1000, 0x200),
        *(6, 0, 0, 0, 6, 0, 0, 0x3000, 0x200, 0, 2, 0),  # no dynamic base: loaded at BASE
        *(0x100000, 0x1000, 0x100000, 0x1000, 0, 16),
    )
    opt += b"".join(
        struct.pack("<II", *d) for d in [(0x2100, 0x80), (0x2000, 0x28)] + [(0, 0)] * 14
    )
    row = "<8sIIIIIIHHI"
    sections = struct.pack(row, b".text", 0x200, 0x1000, 0x200, 0x200, 0, 0, 0, 0, 0x60000020)
    sections += struct.pack(row, b".rdata", 0x200, 0x2000, 0x200, 0x400, 0, 0, 0, 0, 0x40000040)
    head = b"MZ" + b"\0" * 0x3A + struct.pack("<I", 0x40) + b"PE\0\0" + coff + opt + sections
    return head.ljust(0x200, b"\0") + bytes(text) + bytes(rdata)


def elf64(code: bytes) -> bytes:
    """An ELF64 executable: one RX PT_LOAD at 0x400000, the routine at 0x400080."""
    size = 0x80 + len(code)
    header = b"\x7fELF\x02\x01\x01" + b"\0" * 9
    header += struct.pack("<HHIQQQIHHHHHH", 2, 0x3E, 1, 0x400080, 64, 0, 0, 64, 56, 1, 0, 0, 0)
    phdr = struct.pack("<IIQQQQQQ", 1, 5, 0, 0x400000, 0x400000, size, size, 0x1000)
    return (header + phdr).ljust(0x80, b"\0") + code


@unittest.skipUnless(
    workers._installed(LIB, workers.entries()["unicorn"]["pin"]), "needs `viwo install unicorn`"
)
class EmulateWorkerTests(unittest.TestCase):
    def emulate(self, binary: bytes, options: dict) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "game.bin"
            path.write_bytes(binary)
            spec = worker_spec(path, options, symbolic=False)
            (Path(tmp) / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
            out = Path(tmp) / "out"
            argv = [
                sys.executable,
                "-I",
                str(SCRIPT),
                "--lib",
                str(LIB),
                str(Path(tmp) / "spec.json"),
                str(out),
            ]
            if os.environ.get("COVERAGE_PROCESS_START"):  # the coverage run measures the worker too
                argv[1:2] = [
                    "-m",
                    "coverage",
                    "run",
                    "-p",
                    "--rcfile",
                    os.environ["COVERAGE_PROCESS_START"],
                ]
            subprocess.run(argv, capture_output=True, timeout=120, cwd=ROOT)
            report = json.loads((out / "result.json").read_text(encoding="utf-8"))
            report["dumped"] = {f: (out / f).read_bytes() for f in report.get("files", [])}
            return report

    def test_xor_routine_decodes_like_python_in_both_abis(self) -> None:
        rng = random.Random(11)
        for binary, start in ((pe64(), "export:xor_decode"), (elf64(XOR_SYSV), "0x400080")):
            for _ in range(3):
                data, key = rng.randbytes(rng.randint(1, 64)), rng.randint(1, 255)
                r = self.emulate(
                    binary,
                    {
                        "start": start,
                        "args": f"hex:{data.hex()},{len(data)},{key}",
                        "dump": f"arg0:{len(data)}",
                    },
                )
                self.assertEqual((r["status"], int(r["return"], 16)), ("returned", 42), r)
                self.assertEqual(r["dumped"]["arg0.bin"], bytes(b ^ key for b in data))

    def test_imports_budget_and_faults_are_named(self) -> None:
        pe = pe64()
        called = self.emulate(pe, {"start": "rva:0x1040"})
        self.assertEqual(called["status"], "import")
        self.assertIn("KERNEL32.dll!Sleep", called["reason"])
        spun = self.emulate(pe, {"start": f"{BASE + 0x1060:#x}", "max_insns": "500"})
        self.assertEqual(spun["status"], "limit")
        self.assertIn("500", spun["reason"])
        fault = self.emulate(pe, {"start": "rva:0x1070"})
        self.assertEqual(fault["status"], "fault")
        missing = self.emulate(pe, {"start": "export:nope"})
        self.assertEqual(missing["status"], "error")
        self.assertIn("xor_decode", missing["reason"])  # says which exports exist


ANGR = ROOT / "third_party" / "angr"


@unittest.skipUnless(
    workers._installed(ANGR, workers.entries()["angr"]["pin"]), "needs `viwo install angr`"
)
class SymbolicWorkerTests(unittest.TestCase):
    def solve(self, options: dict) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "game.dll"
            path.write_bytes(pe64())
            spec_file = Path(tmp) / "spec.json"
            spec_file.write_text(
                json.dumps(worker_spec(path, options, symbolic=True)), encoding="utf-8"
            )
            argv = [
                sys.executable,
                "-I",
                str(workers.SCRIPTS / "symbolic.py"),
                "--lib",
                str(ANGR),
                str(spec_file),
                tmp,
            ]
            subprocess.run(argv, capture_output=True, timeout=600, cwd=ROOT)
            return json.loads((Path(tmp) / "result.json").read_text(encoding="utf-8"))

    def test_the_solved_key_passes_the_check_when_emulated(self) -> None:
        found = self.solve(
            {"start": "rva:0x1080", "args": "sym:4", "find": "rva:0x1097", "avoid": "rva:0x109d"}
        )
        self.assertEqual(found["status"], "found", found)
        key = bytes.fromhex(found["solutions"]["arg0"])
        self.assertEqual(key, b"VIWO")  # the only input that reaches the accepted branch
        blocked = self.solve(
            {"start": "rva:0x1080", "args": "sym:4", "find": "rva:0x1060", "avoid": ""}
        )
        self.assertEqual(
            blocked["status"], "not_found"
        )  # the spin routine: no path from check reaches it, and the report says so


@unittest.skipUnless(workers._installed(LIB, workers.entries()["unicorn"]["pin"]), "needs unicorn")
class EmulateCliTests(unittest.TestCase):
    def test_viwo_analyze_emulates_into_the_workspace_and_leaves_the_game_alone(self) -> None:
        from tests.helpers import tree_hashes
        from tests.test_cli import run

        rng = random.Random(2)
        data, key = rng.randbytes(16), rng.randint(1, 255)
        with tempfile.TemporaryDirectory() as tmp:
            game, ws = Path(tmp) / "game", Path(tmp) / "ws"
            game.mkdir()
            (game / "Game.exe").write_bytes(pe64())
            before = tree_hashes(game)
            base = ["--json", "--features", "extraction,analysis", "analyze", str(game)]
            listed = json.loads(run([*base, "--list"])[1])["data"]["targets"]
            target = next(t["key"] for t in listed if t["kind"] == "native_binary")
            sets = ["start=export:xor_decode", f"args=hex:{data.hex()},16,{key}", "dump=arg0:16"]
            argv = [*base, "--workspace", str(ws), "--target", target, "--slot", "analysis.emulate"]
            code, out, err = run([*argv, *[x for s in sets for x in ("--set", s)]])
            self.assertEqual(code, 0, out + err)
            folder = ws / ".analysis" / "unicorn-emulate" / target
            self.assertEqual((folder / "arg0.bin").read_bytes(), bytes(b ^ key for b in data))
            self.assertEqual(json.loads(out)["data"]["backend"], "unicorn-emulate")
            self.assertEqual(tree_hashes(game), before)
            code, out, _ = run([*argv, "--set", "nonsense"])
            self.assertEqual(code, 2)  # a malformed --set is a bad request, said before any run


class EmulateSpecTests(unittest.TestCase):
    def test_bad_requests_fail_before_any_process(self) -> None:
        bad = [
            {},
            {"start": "0x1", "args": "nonsense"},
            {"start": "0x1", "dump": "x:1"},
            {"start": "0x1", "dump": "arg0"},
        ]
        for options in bad:
            with self.assertRaises(ViwoError) as err:
                worker_spec("game.exe", options, symbolic=False)
            self.assertEqual(err.exception.code, "invalid_request", options)
        with self.assertRaises(ViwoError):
            worker_spec("game.exe", {"start": "0x1"}, symbolic=True)  # symbolic needs find=

    def test_every_argument_kind_round_trips(self) -> None:
        rng = random.Random(5)
        for _ in range(50):
            n = rng.randint(0, 4096)
            args = [
                str(n),
                f"hex:{rng.randbytes(4).hex()}",
                f"zeros:{n}",
                f"sym:{n % 64 + 1}",
                "file:x.bin",
            ]
            spec = worker_spec("g", {"start": "0x10", "args": ",".join(args)}, symbolic=False)
            kinds = [next(iter(a)) for a in spec["args"]]
            self.assertEqual(kinds, ["int", "hex", "zeros", "sym", "file"])
            self.assertEqual(spec["args"][0]["int"], n)


if __name__ == "__main__":
    unittest.main()
