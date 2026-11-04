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


def _samples(root: Path) -> dict:
    """backend id -> (slot, suffix, a valid archive) from the format tests' builders."""
    from tests.helpers import make_tar, make_zip
    from tests.test_containers import drs, pack, tpac
    from tests.test_doom import make_wad
    from tests.test_formats import asar, bsa, xp3
    from tests.test_redengine import rdar
    from tests.test_renpy import make_rpa

    files = {"a/b.txt": b"hello" * 20, "c.png": b"\x89PNG" + bytes(50)}
    rpa = make_rpa(root / "s.rpa", files).read_bytes()
    return {
        "drs-builtin": ("unarchive.drs", ".drs", drs({"bin": {1: b"x" * 30, 2: b"y" * 40}})),
        "pack-builtin": ("unarchive.pack", ".pack", pack(files)),
        "tpac-builtin": ("unarchive.tpac", ".tpac", tpac({"t": [b"z" * 40, b"w" * 20]})),
        "asar-builtin": ("unarchive.asar", ".asar", asar(files)),
        "bsa-builtin": ("unarchive.bsa", ".bsa", bsa({"a.dds": b"d" * 60, "b.txt": b"t" * 30})),
        "rpa-safe": ("unarchive.rpa", ".rpa", rpa),
        "wad-builtin": (
            "unarchive.wad",
            ".wad",
            make_wad(root / "s.wad", [("X", b"x" * 30)]).read_bytes(),
        ),
        "rdar-builtin": ("unarchive.archive", ".archive", rdar({7: [b"KB2j" + bytes(20)]})),
        "xp3-builtin": ("unarchive.xp3", ".xp3", xp3([("bg/a.png", b"a" * 40, False)] * 2)),
        "py-zipfile": ("unarchive.zip", ".zip", make_zip(root / "s.zip", files).read_bytes()),
        "py-tarfile": ("unarchive.tar", ".tar.gz", make_tar(root / "s.tar.gz", files).read_bytes()),
    }


class MutationTests(unittest.TestCase):
    def test_damaged_archives_are_named_failures_never_exceptions(self) -> None:
        """Valid archives, randomly damaged (bytes, runs, cuts): every reader still answers."""
        rng = random.Random(2)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = runtime(root, "[plugins]\n" + "".join(f"{p} = on\n" for p in PLUGINS))
            for backend_id, (slot_id, suffix, good) in _samples(root).items():
                backend = rt.backends[backend_id]
                for i in range(150):
                    blob = bytearray(good)
                    for _ in range(rng.randint(1, 6)):
                        at = rng.randrange(len(blob))
                        blob[at : at + rng.choice((1, 8))] = rng.randbytes(rng.choice((1, 8)))
                    if rng.random() < 0.15:
                        blob = blob[: rng.randrange(1, len(blob))]
                    path = root / "in" / f"{backend_id}-{i}{suffix}"
                    path.parent.mkdir(exist_ok=True)
                    path.write_bytes(bytes(blob))
                    dest = root / "out" / f"{backend_id}-{i}"
                    dest.mkdir(parents=True)
                    ctx = core_context(rt, rt.slots[slot_id].owner, root, root / "work", None)
                    try:
                        outcome = backend.extract(path, dest, ctx)
                    except Exception as exc:  # noqa: BLE001
                        self.fail(f"{backend_id} raised {type(exc).__name__}: {exc}")
                    self.assertTrue(outcome.ok or outcome.error, backend_id)


if __name__ == "__main__":
    unittest.main()
