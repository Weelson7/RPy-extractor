"""L4: mixed mode, pairwise pipeline runs over the real plugins (doc 3.6)."""

from __future__ import annotations

import itertools
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import make_zip, runtime, tree_hashes
from tests.test_godot import embed, fake_tools, make_pck
from tests.test_renpy import make_rpa
from tests.test_unity import fake_unitypy
from viwo.contracts import CancelToken, ExtractionMode, ExtractionRequest
from viwo.core.pipeline.runner import extract

PLUGINS = ("generic", "renpy", "unity", "godot")


def make_mixed_game(root: Path) -> Path:
    game = root / "mixed"
    (game / "game").mkdir(parents=True)
    make_rpa(game / "game" / "images.rpa", {"images/vn.png": b"vn"})
    (game / "UnityPlayer.dll").write_bytes(b"MZ")
    (game / "Mixed_Data").mkdir()
    (game / "Mixed_Data" / "globalgamemanagers").write_bytes(b"\0" * 8)
    embed(game / "Mixed.exe", make_pck())
    make_zip(game / "dlc.zip", {"dlc/readme.txt": b"dlc"})
    return game


@unittest.skipIf(sys.platform == "win32", "uses the POSIX fake Godot tools")
class MixedPairwiseTests(unittest.TestCase):
    def test_pairs_and_singles(self) -> None:
        combos = [(p,) for p in PLUGINS] + list(itertools.combinations(PLUGINS, 2))
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(sys.modules, {"UnityPy": fake_unitypy()}),
        ):
            root = Path(tmp)
            game = make_mixed_game(root)
            before = tree_hashes(game)
            rt = runtime(root, fake_tools(root))  # every built-in plugin is on by default
            for index, combo in enumerate(combos):
                request = ExtractionRequest(
                    str(game), str(root / f"ws{index}"), mode=ExtractionMode.MIXED, plugins=combo
                )
                result = extract(rt, request, f"j{index}", lambda e: None, CancelToken())
                with self.subTest(combo=combo):
                    self.assertEqual({r.plugin_id for r in result.runs}, set(combo))
                    self.assertEqual(result.to_legacy_dict()["extractorType"], "mixed")
                    self.assertGreater(result.copied_files, 0)
            self.assertEqual(tree_hashes(game), before)
            first = tree_hashes(root / "ws0", skip_reserved=True)
            again = extract(
                rt,
                ExtractionRequest(
                    str(game), str(root / "again"), mode=ExtractionMode.MIXED, plugins=("generic",)
                ),
                "jx",
                lambda e: None,
                CancelToken(),
            )
            self.assertEqual(tree_hashes(Path(again.workspace), skip_reserved=True), first)


if __name__ == "__main__":
    unittest.main()
