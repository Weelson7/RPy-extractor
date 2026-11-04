"""L3: hostile input (doc 17.3): every built-in reader that parses archive bytes in the ViWo
process, handed files that start with its own magic and continue with random bytes, answers
with an Outcome (a named failure, or what it could read), never an exception, and writes only
inside its destination."""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime
from viwo.contracts.slots import Unarchiver
from viwo.contracts.types import Outcome
from viwo.core.context import core_context

PLUGINS = (
    "generic renpy unity godot unreal doom rpgmaker kirikiri electron source bethesda genie "
    "warscape redengine taleworlds"
).split()


class HostileInputTests(unittest.TestCase):
    def test_every_in_process_reader_answers_and_stays_inside(self) -> None:
        rng = random.Random(1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = runtime(root, "[plugins]\n" + "".join(f"{p} = on\n" for p in PLUGINS))
            readers = []
            for slot_id, slot in sorted(rt.slots.items()):
                binding = rt.bindings.get(slot_id)
                for backend_id in (binding.main, binding.spare) if binding else ():
                    backend = rt.backends.get(backend_id)
                    if isinstance(backend, Unarchiver) and backend.isolation == "inprocess":
                        readers.append((slot, backend))
            self.assertGreater(len(readers), 10)  # the built-in readers are all here
            for n, (slot, backend) in enumerate(readers):
                for i in range(40):
                    magic = rng.choice(slot.magic) if slot.magic else b""
                    path = root / "in" / f"{n}-{i}{(slot.suffixes or ('.bin',))[0]}"
                    path.parent.mkdir(exist_ok=True)
                    path.write_bytes(magic + rng.randbytes(rng.randint(0, 600)))
                    dest = root / "out" / f"{n}-{i}"
                    dest.mkdir(parents=True)
                    ctx = core_context(rt, slot.owner, root, root / "work", None)
                    try:
                        outcome = backend.extract(path, dest, ctx)
                    except Exception as exc:  # noqa: BLE001
                        self.fail(f"{backend.backend_id} raised {type(exc).__name__}: {exc}")
                    self.assertIsInstance(outcome, Outcome, backend.backend_id)
                    if not outcome.ok:
                        self.assertTrue(outcome.error, backend.backend_id)  # a named failure
            outside = (
                {p for p in root.rglob("*") if p.is_file()}
                - set((root / "in").rglob("*"))
                - set((root / "out").rglob("*"))
                - set((root / "work").rglob("*"))
            )
            self.assertEqual({p for p in outside if p.suffix != ".ini"}, set())


if __name__ == "__main__":
    unittest.main()
