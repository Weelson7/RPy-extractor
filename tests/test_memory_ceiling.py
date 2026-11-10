"""L3: the memory ceiling of ViWo's own process (doc 9.2 `memory_limit`). A Unity object read
with a layout that did not fit asked for 15 GB in three seconds and took the owner's machine
down, twice. Properties: under the real OS layer an allocation past the ceiling fails as a
MemoryError inside the process, one under it succeeds, and a child process is not capped
(Windows); the ini value is read strictly; what the guard says matches what holds; the Unity
dump counts an exhausted read, and the rebuilt layouts are switched off once, said once."""

import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import write_ini
from viwo.core.wiring.ini import load_ini
from viwo.core.wiring.memory import guard
from viwo.plugins.unity import objects

ROOT = Path(__file__).resolve().parent.parent
PROBE = """
import subprocess, sys
from viwo.os import select_os
why = select_os().limit_memory(600 << 20)
assert why == "", why
small = bytearray(64 << 20)
try:
    bytearray(3 << 30)
    print("NOT CAPPED")
except MemoryError:
    print("capped")
child = subprocess.run([sys.executable, "-c", "b = bytearray(1 << 30); print('child ok')"],
                       capture_output=True, text=True)
print(child.stdout.strip() or "child capped")
"""


class CeilingTests(unittest.TestCase):
    def test_past_the_ceiling_fails_here_and_the_machine_stays_up(self) -> None:
        done = subprocess.run(
            [sys.executable, "-c", PROBE], cwd=ROOT, capture_output=True, text=True, timeout=120
        )
        lines = done.stdout.split()
        self.assertEqual(lines[0], "capped", done.stdout + done.stderr)
        if sys.platform == "win32":  # a tool ViWo starts keeps its own needs
            self.assertIn("child ok", done.stdout)

    def test_the_guard_says_what_holds(self) -> None:
        rng = random.Random(50)
        for _ in range(40):
            percent, total = rng.choice([0, 1, 30, 50, 95]), rng.choice([0, 8 << 30, 32 << 30])
            refused = rng.choice(["", "refused by the OS"])
            asked = []
            host = SimpleNamespace(
                memory_bytes=lambda total=total: total,
                limit_memory=lambda c, asked=asked, refused=refused: asked.append(c) or refused,
            )
            rt = SimpleNamespace(os=host, config=SimpleNamespace(memory_limit=percent))
            said, holds = guard(rt)
            if not percent:
                self.assertEqual((asked, holds), ([], True))  # the owner switched it off
                self.assertIn("off", said)
            elif not total:
                self.assertEqual((asked, holds), ([], False))
            else:
                self.assertEqual(asked, [total * percent // 100])
                self.assertEqual(holds, not refused)
                self.assertIn(refused or "memory ceiling for ViWo's own process", said)

    def test_the_ini_value_is_read_strictly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for text, want, problem in (
                ("0", 0, False), ("30", 30, False), (" 40 ", 40, False), ("95", 95, False),
                ("96", 50, True), ("-5", 50, True), ("lots", 50, True),
            ):  # fmt: skip
                cfg = load_ini(write_ini(Path(tmp), f"[startup]\nmemory_limit = {text}\n"))
                self.assertEqual(cfg.memory_limit, want, text)
                self.assertEqual(any("memory_limit" in p for p in cfg.problems), problem, text)
            self.assertEqual(load_ini(None).memory_limit, 50)


class ChildCapTests(unittest.TestCase):
    def test_a_capped_tool_fails_by_itself_and_the_next_one_is_free_again(self) -> None:
        from viwo.os import select_os

        runner = select_os().process
        hungry = [sys.executable, "-c", "b = bytearray(2 << 30); print('took it')"]
        modest = [sys.executable, "-c", "b = bytearray(32 << 20); print('fine')"]
        said = []
        capped = runner.run_capped(400 << 20, hungry, on_line=said.append)
        if any("no memory cap" in line for line in said):
            self.skipTest("this OS layer could not cap the child: " + said[0])
        self.assertNotIn("took it", capped.stdout)  # the tool failed, the machine did not
        self.assertIn("fine", runner.run_capped(400 << 20, modest).stdout)
        self.assertIn("took it", runner.run(hungry).stdout)  # the cap ended with its call


ROOM_PROBE = """
from viwo.os import select_os
host = select_os()
assert host.limit_memory(6 << 30) == ""
host.memory_room(300 << 20)
try:
    bytearray(2 << 30)
    print("NOT TIGHT")
except MemoryError:
    print("tight")
host.memory_room(None)
print("restored", len(bytearray(2 << 30)) >> 30)
"""


class UnityMisfitTests(unittest.TestCase):
    def test_the_ceiling_tightens_for_one_read_and_comes_back(self) -> None:
        done = subprocess.run(
            [sys.executable, "-c", ROOM_PROBE],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if sys.platform == "win32":
            self.assertEqual(done.stdout.split(), ["tight", "restored", "2"], done.stderr)

    def test_a_misfit_script_loses_its_fields_and_every_other_keeps_them(self) -> None:
        rng = random.Random(77)
        for _ in range(25):
            with tempfile.TemporaryDirectory() as tmp:
                rooms = []
                host = SimpleNamespace(memory_room=rooms.append)
                dump = objects.Dump(Path(tmp), host)
                scripts = list(range(rng.randint(1, 6)))
                misfit = {s for s in scripts if rng.random() < 0.4}
                reads, expect_fields, n = {s: 0 for s in scripts}, 0, rng.randint(1, 40)
                for i in range(n):
                    script = rng.choice(scripts)

                    def read(script=script):
                        reads[script] += 1
                        if script in misfit:
                            raise MemoryError()
                        return {"m_Name": "x"}

                    head = SimpleNamespace(m_Script=SimpleNamespace(m_FileID=0, m_PathID=script))
                    obj = SimpleNamespace(
                        path_id=i, assets_file=SimpleNamespace(name="level0"),
                        read_typetree=read, parse_monobehaviour_head=lambda head=head: head,
                    )  # fmt: skip
                    dump.add(obj, "MonoBehaviour")
                    expect_fields += script not in misfit
                for script in misfit:  # a misfit layout is tried once, never again
                    self.assertLessEqual(reads[script], 1)
                self.assertEqual(dump.misfits, {(0, s) for s in misfit if reads[s]})
                self.assertEqual(dump.no_layout.get("MonoBehaviour", 0), n - expect_fields)
                self.assertEqual(rooms.count(None), sum(reads.values()))  # always restored
                self.assertTrue(all(r in (None, objects.ROOM) for r in rooms))
                summary, notes = dump.close()
                self.assertIn(f"{n} object(s)", summary)  # every object is still listed
                self.assertEqual(any("does not fit" in x for x in notes), bool(dump.misfits))


if __name__ == "__main__":
    unittest.main()
