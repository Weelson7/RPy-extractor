"""L0: the va.b.c version scheme (tools/version.py) and the single source of the version."""

from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path

import viwo

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("version_tool", ROOT / "tools" / "version.py")
version_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(version_tool)


class VersionSchemeTests(unittest.TestCase):
    def test_bump_kinds(self) -> None:
        self.assertEqual(version_tool.next_version("0.2.0", "tweak"), "0.2.1")
        self.assertEqual(version_tool.next_version("0.2.7", "feature"), "0.3.0")
        self.assertEqual(version_tool.next_version("0.9.3", "major"), "1.0.0")

    def test_one_version_everywhere(self) -> None:
        self.assertEqual(version_tool.current(), viwo.__version__)
        self.assertTrue(re.fullmatch(r"\d+\.\d+\.\d+", viwo.__version__))
        notes = (ROOT / "docs" / "release-notes.md").read_text(encoding="utf-8")
        self.assertIn(viwo.__version__.split(".")[0] + ".", notes.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
