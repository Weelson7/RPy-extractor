"""L0 static checks (doc 17.2): import direction between layers, GPL/AGPL backends run as
subprocesses, every backend declares its network use and whether it parses untrusted bytes in
process, and the caps file validates against its schema."""

from __future__ import annotations

import ast
import re
import tempfile
import unittest
from pathlib import Path

from tools import caps_ini
from viwo import __version__
from viwo.backends import CORE_SLOTS, core_backends
from viwo.core.capture import SLOTS as CAPTURE_SLOTS
from viwo.core.capture import backends as capture_backends
from viwo.core.decode import SLOTS as DECODE_SLOTS
from viwo.core.decode import decoders
from viwo.core.wiring.registry import collect, load_enabled

ROOT = Path(__file__).resolve().parent.parent
# doc 17 L0 layer rule: contracts <- os <- plugins/backends <- core <- api/cli. A module may
# import only its own layer and the layers below it.
LAYERS = {"contracts": 0, "os": 1, "plugins": 2, "backends": 2, "core": 3, "api": 4, "cli": 4}
# Recorded debt (doc 17.2): the core-owned carver and ffmpeg backends are listed by backends/.
ALLOWED = {
    ("viwo/backends/__init__.py", "viwo.core.carve"),
    ("viwo/backends/__init__.py", "viwo.core.merger.ffmpeg"),
}
NETWORK = {"none", "download", "any"}
CAPS_INI = """[caps]
function = 40
class = 200
file = 250
contracts_file = 150
params = 6
line_length = 100
test_file = 400
test_function = 60
[budgets]
viwo = 100
[web]
js_file = 300
"""


def layer_of(rel: str) -> int | None:
    parts = rel.split("/")
    name = parts[1] if len(parts) > 2 else parts[1].removesuffix(".py")
    if name.startswith("cli"):
        name = "cli"
    return LAYERS.get(name)


def imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.startswith("viwo.")]
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("viwo."):
            found.append(node.module)
    return found


def all_backends():
    plugins, _ = load_enabled({})
    _, backends, _ = collect(
        CORE_SLOTS + DECODE_SLOTS + CAPTURE_SLOTS,
        core_backends() + decoders() + capture_backends(),
        plugins,
    )
    return backends


class ImportDirectionTests(unittest.TestCase):
    def test_layers_only_import_downwards(self) -> None:
        bad = []
        for path in sorted((ROOT / "viwo").rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            mine = layer_of(rel)
            if mine is None:
                continue
            for module in imports(path):
                target = layer_of(module.replace(".", "/") + ".py")
                if target is None or target <= mine:
                    continue
                if (rel, module) not in ALLOWED and not any(
                    module.startswith(a[1]) and rel == a[0] for a in ALLOWED
                ):
                    bad.append(f"{rel} -> {module}")
        self.assertEqual(bad, [])

    def test_plugins_never_import_each_other(self) -> None:
        bad = []
        for path in sorted((ROOT / "viwo" / "plugins").rglob("*.py")):
            own = path.relative_to(ROOT / "viwo" / "plugins").parts[0]
            for module in imports(path):
                parts = module.split(".")
                if len(parts) > 2 and parts[1] == "plugins" and parts[2] != own:
                    bad.append(f"{path.name}: {module}")
        self.assertEqual(bad, [])

    def test_contracts_import_nothing_from_the_app(self) -> None:
        for path in (ROOT / "viwo" / "contracts").glob("*.py"):
            for module in imports(path):
                self.assertTrue(module.startswith("viwo.contracts"), f"{path.name}: {module}")


class BackendDeclarationTests(unittest.TestCase):
    def test_gpl_backends_run_as_subprocesses(self) -> None:
        for backend in all_backends().values():
            if re.search(r"(?<!L)GPL", backend.license.upper()):  # GPL/AGPL, not LGPL
                self.assertEqual(backend.isolation, "subprocess", backend.backend_id)

    def test_every_backend_declares_network_and_untrusted_parsing(self) -> None:
        for backend in all_backends().values():
            self.assertIn(getattr(backend, "network", None), NETWORK, backend.backend_id)
            self.assertIsInstance(backend.parses_untrusted_in_process, bool, backend.backend_id)
            self.assertIn(backend.isolation, {"inprocess", "subprocess"}, backend.backend_id)


class CapsIniSchemaTests(unittest.TestCase):
    def test_repository_caps_file_is_valid(self) -> None:
        caps = caps_ini.load(ROOT / "loc_caps.ini", __version__)
        self.assertEqual(caps.problems, [])
        self.assertLessEqual(len(caps.exceptions), caps_ini.MAX_EXCEPTIONS)

    def test_schema_problems_and_exception_expiry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "loc_caps.ini"
            path.write_text(CAPS_INI + "[extra]\nx = 1\n", encoding="utf-8")
            self.assertIn(
                "loc_caps.ini: unknown section [extra]", caps_ini.load(path, "1.0.0").problems
            )
            path.write_text(CAPS_INI.replace("params = 6\n", "params = six\n"), encoding="utf-8")
            problems = caps_ini.load(path, "1.0.0").problems
            self.assertTrue(any("not an integer" in p for p in problems), problems)
            exceptions = "[exceptions]\nviwo/core/x.py = 300 | graph builder | expires at v1.2\n"
            path.write_text(CAPS_INI + exceptions, encoding="utf-8")
            ok = caps_ini.load(path, "1.1.0")
            self.assertEqual(ok.problems, [])
            self.assertEqual(ok.file_cap("viwo/core/x.py", 250), 300)
            self.assertEqual(ok.file_cap("viwo/core/y.py", 250), 250)
            expired = caps_ini.load(path, "1.2.0")
            self.assertTrue(any("expired" in p for p in expired.problems), expired.problems)
            four = "".join(
                "[exceptions]\n" * (i == 0) + f"viwo/{i}.py = 300 | r | M9\n" for i in range(4)
            )
            path.write_text(CAPS_INI + four, encoding="utf-8")
            self.assertTrue(any("> 3 active" in p for p in caps_ini.load(path, "1.0.0").problems))
            path.write_text(CAPS_INI + "[exceptions]\nviwo/a.py = big | r | M9\n", encoding="utf-8")
            self.assertTrue(
                any("use `cap | reason" in p for p in caps_ini.load(path, "1.0.0").problems)
            )


if __name__ == "__main__":
    unittest.main()
