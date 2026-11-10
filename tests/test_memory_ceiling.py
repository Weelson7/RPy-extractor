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

    def test_export_runs_are_small_and_every_file_is_in_one(self) -> None:
        from viwo.plugins.redengine import export

        rng = random.Random(20)
        for _ in range(30):
            paths = [Path(f"f{i}{rng.choice(export.SUFFIXES)}") for i in range(rng.randint(0, 400))]
            runs = export.commands(paths, Path("game"))
            exported = [a for r in runs if r[0] == "export" for a in r[1:-2]]
            self.assertEqual(
                exported, [str(p) for p in paths if p.suffix.lower() in export.EXPORTS]
            )
            self.assertTrue(
                all(len(r) - 3 <= export.EXPORT_BATCH for r in runs if r[0] == "export")
            )
            serialized = [a for r in runs if r[0] == "convert" for a in r[2:]]
            self.assertEqual(serialized, [str(p) for p in paths])


class UnityExhaustedTests(unittest.TestCase):
    def test_an_exhausted_read_is_counted_and_the_layouts_go_off_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = objects.Dump(Path(tmp))

            def obj(i, error=None):
                def read():
                    if error:
                        raise error
                    return {"m_Name": f"o{i}"}

                return SimpleNamespace(
                    path_id=i, assets_file=SimpleNamespace(name="level0"), read_typetree=read
                )

            env = SimpleNamespace(typetree_generator="rebuilt layouts")
            shared = {"generator": "rebuilt layouts"}
            dump.add(obj(1), "MonoBehaviour")
            dump.add(obj(2, ValueError("stripped")), "MonoBehaviour")
            self.assertEqual(objects.layouts_off(env, dump, shared), [])  # nothing exhausted yet
            dump.add(obj(3, MemoryError()), "MonoBehaviour")
            self.assertTrue(dump.exhausted)
            said = objects.layouts_off(env, dump, shared)
            self.assertEqual(len(said), 1)
            self.assertIn("memory_limit", said[0])
            self.assertIsNone(env.typetree_generator)
            self.assertIsNone(shared["generator"])
            self.assertEqual(objects.layouts_off(env, dump, shared), [])  # said once
            self.assertEqual(objects.layouts_off(env, None, shared), [])
            self.assertEqual(dump.no_layout, {"MonoBehaviour": 2})
            summary, _ = dump.close()
            self.assertIn("3 object(s)", summary)  # every object is still listed


if __name__ == "__main__":
    unittest.main()
