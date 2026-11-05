"""L0: the tools ViWo's backends need are described once, in viwo/data/dependencies.json
(doc 2.6). Every description loads into a DependencySpec with only known fields, and every
dependency any backend of any plugin declares is either that description, byte for byte, or one
a module still builds itself (a spec two modules word differently)."""

import json
import tempfile
import unittest
from dataclasses import fields
from pathlib import Path

from tests.helpers import runtime
from viwo.contracts.types import DependencySpec, Requirement, _known

PLUGINS = "generic unity godot unreal renpy doom rpgmaker kirikiri electron source bethesda"
PLUGINS += " genie warscape redengine taleworlds quickbms overwatch cyberpunk2077 bannerlord"


class DependencyDataTests(unittest.TestCase):
    def test_every_description_loads_with_known_fields_only(self) -> None:
        allowed = {f.name for f in fields(DependencySpec)} - {"dep_id"}
        raw = json.loads((Path(__file__).parents[1] / "viwo/data/dependencies.json").read_text())
        for dep_id, described in raw.items():
            if dep_id.startswith("_"):
                continue
            self.assertLessEqual(set(described), allowed, dep_id)
            spec = DependencySpec.of(dep_id)
            self.assertEqual((spec.dep_id, bool(spec.label)), (dep_id, True))
            self.assertIsInstance(spec.requirement, Requirement)
            names = spec.executables
            self.assertTrue(
                isinstance(names, tuple) or all(isinstance(v, tuple) for v in names.values())
            )

    def test_every_backend_dependency_is_its_description(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ini = "[plugins]\n" + "".join(f"{p} = on\n" for p in PLUGINS.split())
            rt = runtime(Path(tmp), ini)
            seen = 0
            for backend in rt.backends.values():
                for spec in getattr(backend, "requires", ()):
                    if spec.dep_id in _known():
                        self.assertEqual(spec, DependencySpec.of(spec.dep_id), spec.dep_id)
                        seen += 1
            self.assertGreater(seen, 30)  # most backends' tools come from the data


if __name__ == "__main__":
    unittest.main()
