"""L0: the tests a commit runs (tools/affected.py). Properties over the real import graph: a
changed module picks every test whose reach (what it imports and what those import, hubs not
passed through) holds it, and every other pick is explained (it names the file, or the plugin,
or is a plugin-wide check); a plugin change picks the plugin-wide checks; a test picks itself; a
doc picks exactly the tests whose code (not a docstring) names it; only pyproject.toml runs
everything; the reach stays narrow (a module deep in core never pulls in the whole suite)."""

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
REACH = {t: affected.reach(t, EDGES) for t in TESTS}


def path_of(module: str) -> str:
    rel = module.replace(".", "/")
    return f"{rel}/__init__.py" if (ROOT / rel).is_dir() else f"{rel}.py"


def explained(test: str, rel: str) -> bool:
    """Why a test that does not reach a changed file may still be picked: its code names the
    plugin, or it is a plugin-wide check, or a string in its reach names the file or folder."""
    parts, own = Path(rel).parts, TEXT[test]
    if parts[:2] == ("viwo", "plugins") and len(parts) > 3:
        pid = parts[2]
        if test in affected.PLUGIN_WIDE or any(s == pid or f"{pid} = on" in s for s in own):
            return True
    folder = ""
    if parts[:2] in (("viwo", "data"), ("viwo", "web")) and len(parts) > 2:
        folder = parts[2] if parts[1] == "data" and len(parts) > 3 else parts[1]
    strings = [s for m in REACH[test] for s in TEXT.get(m, ())]
    return any(Path(rel).name in s or (folder and s == folder) for s in strings)


class AffectedTests(unittest.TestCase):
    def test_a_module_picks_the_tests_that_reach_it_and_only_explained_others(self) -> None:
        rng = random.Random(7)
        viwo = sorted(m for m in EDGES if m.startswith("viwo.") and "." in m[5:])
        for module in rng.sample(viwo, 40):
            rel = path_of(module)
            picked = set(affected.select([rel]))
            reach = {t for t in TESTS if module in REACH[t]}
            self.assertTrue(reach <= picked, module)  # every test that reaches it
            for test in picked - reach:
                self.assertTrue(explained(test, rel), (module, test))

    def test_a_plugin_picks_the_plugin_wide_checks_and_its_own_tests(self) -> None:
        picked = set(affected.select(["viwo/plugins/renpy/__init__.py"]))
        self.assertTrue(set(affected.PLUGIN_WIDE) <= picked)
        self.assertIn("tests.test_renpy", picked)

    def test_a_test_picks_itself_docs_pick_their_readers_and_only_pyproject_all(self) -> None:
        for test in random.Random(3).sample(TESTS, 10):
            self.assertIn(test, affected.select([path_of(test)]))
        for doc in ("README.md", "docs/HANDOFF.md", "docs/release-notes.md", "CHANGELOG.md"):
            name = Path(doc).name
            readers = [
                t for t in TESTS if any(name in s for m in REACH[t] for s in TEXT.get(m, ()))
            ]
            self.assertEqual(affected.select([doc]), readers, doc)
        self.assertIn("tests.test_version", affected.select(["docs/release-notes.md"]))
        self.assertIsNone(affected.select(["README.md", "pyproject.toml"]))
        for tool in ("tools/version.py", "tools/affected.py", "tools/run_tests.py"):
            self.assertIsNotNone(affected.select([tool]), tool)  # the pipeline's own tests

    def test_the_reach_stays_narrow(self) -> None:
        deep = affected.select(["viwo/core/analysis/managed.py"])
        self.assertLess(len(deep), len(TESTS) // 4, deep)  # not the whole suite

    def test_relative_imports_resolve_to_their_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "mod.py"
            src.write_text("from . import sib\nfrom ..up import thing\nimport a.b.c\n")
            modules = {"p", "p.q", "p.q.sib", "p.up", "p.up.thing", "a", "a.b"}
            found = affected._imports(src, "p.q.mod", modules)
            self.assertEqual(found, {"p.q.sib", "p.up.thing", "a.b"})


if __name__ == "__main__":
    unittest.main()
