"""L4: mixed mode, pairwise pipeline runs over the real plugins (doc 3.6)."""

from __future__ import annotations

import itertools
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import make_zip, runtime, tree_hashes
from tests.test_doom import make_wad
from tests.test_formats import asar, bsa, vpk, xp3
from tests.test_godot import embed, make_pck
from tests.test_godot import fake_tools as godot_tools
from tests.test_renpy import make_rpa
from tests.test_rpgmaker import rgssad_v3
from tests.test_unity import fake_unitypy
from tests.test_unreal import fake_tools as unreal_tools
from tests.test_unreal import make_pak
from viwo.contracts import CancelToken, ExtractionMode, ExtractionRequest
from viwo.core.pipeline.runner import extract
from viwo.core.wiring.registry import BUILTIN_PLUGINS

PLUGINS = tuple(BUILTIN_PLUGINS)


def tools_ini(root: Path) -> str:
    """One [tools] section with the fake Godot and Unreal tools."""
    lines = [
        line
        for text in (godot_tools(root), unreal_tools(root))
        for line in text.splitlines()
        if " = " in line and not line.startswith(("godot =", "unreal ="))
    ]
    return "[tools]\n" + "\n".join(lines) + "\n"


def make_mixed_game(root: Path) -> Path:
    game = root / "mixed"
    (game / "game").mkdir(parents=True)
    make_rpa(game / "game" / "images.rpa", {"images/vn.png": b"vn"})
    (game / "UnityPlayer.dll").write_bytes(b"MZ")
    (game / "Mixed_Data").mkdir()
    (game / "Mixed_Data" / "globalgamemanagers").write_bytes(b"\0" * 8)
    embed(game / "Mixed.exe", make_pck())
    make_zip(game / "dlc.zip", {"dlc/readme.txt": b"dlc"})
    make_wad(game / "doom2.wad", [("TITLE", b"t" * 40)], b"IWAD")
    (game / "Paks").mkdir()
    make_pak(game / "Paks" / "pakchunk0.pak")
    (game / "Game.rgss3a").write_bytes(rgssad_v3({"Graphics\\a.png": b"rgss"}))
    (game / "data.xp3").write_bytes(xp3([("bg/x.png", b"xp3", False)]))
    (game / "resources").mkdir()
    (game / "resources" / "app.asar").write_bytes(asar({"index.html": b"<html>"}))
    (game / "pak01_dir.vpk").write_bytes(vpk({"materials/m.vmt": (b"vmt", 0)})[0])
    (game / "Interface.bsa").write_bytes(bsa({"ui.txt": b"ui" * 10}))
    return game


def covering(items: list[str], size: int = 6) -> list[tuple[str, ...]]:
    """Groups of `size` in which every pair of items meets at least once (greedy, fixed order):
    the pairwise property for a fraction of the runs every pair on its own would cost."""
    left = set(itertools.combinations(items, 2))
    groups = []
    while left:
        group = list(min(left))
        while len(group) < min(size, len(items)):
            gain = lambda c: sum(tuple(sorted((c, g))) in left for g in group)  # noqa: E731
            group.append(
                max((c for c in items if c not in group), key=lambda c: (gain(c), -items.index(c)))
            )
        groups.append(tuple(sorted(group, key=items.index)))
        left -= set(itertools.combinations(groups[-1], 2))
    return groups


class MixedPairwiseTests(unittest.TestCase):
    def test_the_groups_cover_every_pair(self) -> None:
        groups = covering(list(PLUGINS))
        met = {pair for g in groups for pair in itertools.combinations(sorted(g), 2)}
        self.assertEqual(met, {tuple(sorted(p)) for p in itertools.combinations(PLUGINS, 2)})

    def test_pairs_and_singles(self) -> None:
        combos = [(p,) for p in PLUGINS] + covering(list(PLUGINS))
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(sys.modules, {"UnityPy": fake_unitypy()}),
        ):
            root = Path(tmp)
            game = make_mixed_game(root)
            before = tree_hashes(game)
            rt = runtime(root, tools_ini(root))  # every built-in plugin is on by default
            from viwo.core.pipeline.probe import FolderProbe
            from viwo.core.pipeline.runner import detect_all
            from viwo.core.pipeline.select import with_games

            found = detect_all(rt, FolderProbe(game))
            for index, combo in enumerate(combos):
                request = ExtractionRequest(
                    str(game), str(root / f"ws{index}"), mode=ExtractionMode.MIXED, plugins=combo
                )
                result = extract(rt, request, f"j{index}", lambda e: None, CancelToken())
                with self.subTest(combo=combo):
                    # a game plugin brings its engine; a chosen engine its detected games (2.10)
                    want = set(with_games(rt.plugins, combo, found))
                    self.assertEqual({r.plugin_id for r in result.runs}, want)
                    self.assertLessEqual(set(combo), want)
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
