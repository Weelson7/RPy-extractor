"""L0: the tests a commit runs (tools/affected.py). Properties over the real import graph: a
changed module picks every test that imports it, directly or not, and no test that cannot reach
it; a plugin change reaches every test that boots the registry; a test file picks itself; a
change no test can see picks none; the pipeline and pyproject.toml pick everything."""

import importlib.util
import random
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("affected", ROOT / "tools" / "affected.py")
affected = importlib.util.module_from_spec(spec)
spec.loader.exec_module(affected)
EDGES, TEXT = affected.graph()
TESTS = sorted(m for m in EDGES if m.startswith("tests.test_"))


def path_of(module: str) -> str:
    rel = module.replace(".", "/")
    return f"{rel}/__init__.py" if (ROOT / rel).is_dir() else f"{rel}.py"


class AffectedTests(unittest.TestCase):
    def test_a_module_picks_exactly_the_tests_that_reach_it(self) -> None:
        rng = random.Random(7)
        viwo = sorted(m for m in EDGES if m.startswith("viwo.") and "." in m[5:])
        for module in rng.sample(viwo, 25):
            picked = set(affected.select([path_of(module)]))
            reach = {t for t in TESTS if module in affected.closure(t, EDGES)}
            self.assertTrue(reach <= picked, module)  # every test that imports it
            named = Path(path_of(module)).name
            for test in picked - reach:  # the rest name the file (a script run as a process)
                mods = affected.closure(test, EDGES)
                self.assertTrue(any(named in TEXT[m] for m in mods), (module, test))

    def test_a_plugin_reaches_every_test_that_boots_the_registry(self) -> None:
        picked = set(affected.select(["viwo/plugins/renpy/__init__.py"]))
        boots = {t for t in TESTS if affected.REGISTRY in affected.closure(t, EDGES)}
        self.assertTrue(boots and boots <= picked)

    def test_a_test_picks_itself_and_docs_pick_only_their_readers(self) -> None:
        for test in random.Random(3).sample(TESTS, 10):
            self.assertIn(test, affected.select([path_of(test)]))
        for doc in ("README.md", "docs/HANDOFF.md", "docs/release-notes.md", "CHANGELOG.md"):
            name = Path(doc).name  # read by name: the tests whose code names the file
            readers = [t for t in TESTS if any(name in TEXT[m] for m in affected.closure(t, EDGES))]
            self.assertEqual(affected.select([doc]), readers, doc)
        self.assertIn("tests.test_version", affected.select(["docs/release-notes.md"]))
        for path in ("pyproject.toml", "tools/version.py", "tools/affected.py"):
            self.assertIsNone(affected.select(["README.md", path]))

    def test_relative_imports_resolve_to_their_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "mod.py"
            src.write_text("from . import sib\nfrom ..up import thing\nimport a.b.c\n")
            modules = {"p", "p.q", "p.q.sib", "p.up", "p.up.thing", "a", "a.b"}
            found = affected._imports(src, "p.q.mod", modules)
            self.assertEqual(found, {"p", "p.q", "p.q.sib", "p.up", "p.up.thing", "a", "a.b"})


if __name__ == "__main__":
    unittest.main()
