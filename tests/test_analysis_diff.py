"""L3: A3 version diff on two functions.csv exports: names pair first, unique fingerprints pair
the unnamed functions across relocation, the rest is added or removed; CLI and API."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from viwo.core.analysis import diff

OLD = """address,name,size,fingerprint
00401000,main,40,aaaa
00401100,FUN_00401100,20,bbbb
00401200,parse_save,64,cccc
00401300,FUN_00401300,8,dddd
00401400,operator,(int, int),12,eeee
"""
NEW = """address,name,size,fingerprint
00402000,main,44,a0a0
00402200,FUN_00402200,20,bbbb
00402300,parse_save,64,cccc
00402400,FUN_00402400,30,ffff
00402500,operator,(int, int),12,eeee
"""


def exports(root: Path) -> tuple[Path, Path]:
    old, new = root / "ghidra-headless" / "v1", root / "ghidra-headless" / "v2"
    for folder, text in ((old, OLD), (new, NEW)):
        folder.mkdir(parents=True)
        (folder / "functions.csv").write_text(text, encoding="utf-8")
    return old, new


class DiffTests(unittest.TestCase):
    def test_pairs_by_name_then_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old, new = exports(Path(tmp))
            report = diff.diff(old, new)
            self.assertEqual(report["summary"], {"changed": 1, "same": 3, "removed": 1, "added": 1})
            moved = next(r for r in report["functions"] if r["old"] == "00401100")
            self.assertEqual((moved["status"], moved["new"]), ("same", "00402200"))
            comma = next(r for r in report["functions"] if r["name"] == "operator,(int, int)")
            self.assertEqual(comma["status"], "same")
            out = diff.write(report, Path(tmp) / "out")
            text = (out / "diff.txt").read_text(encoding="utf-8")
            self.assertIn("changed", text)
            self.assertNotIn("parse_save", text)  # same functions are not listed
            self.assertEqual(json.loads((out / "diff.json").read_text())["summary"]["added"], 1)

    def test_cli_and_api(self) -> None:
        from viwo.api.handlers_analysis import diff_analyses
        from viwo.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            old, new = exports(Path(tmp))
            self.assertEqual(main(["--json", "diff", str(old), str(new)]), 0)
            self.assertTrue((Path(tmp) / "diff" / "v1--v2" / "diff.txt").is_file())

            class App:
                workspace = Path(tmp) / "ws"

            res = diff_analyses(App(), {"old": str(old), "new": str(new)})
            self.assertTrue(res["success"])
            self.assertEqual(res["summary"]["same"], 3)
            self.assertFalse(diff_analyses(App(), {"old": tmp, "new": tmp})["success"])


if __name__ == "__main__":
    unittest.main()
