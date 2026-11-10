"""L1: the analysis target's layout contract (doc 6.1). Core rebuilds the folder a tool expects
from the layout the target's plugin declares; it knows no engine's structure itself.
Properties: every input lands at its declared place with its bytes; a place that would leave
the folder, a missing layout or one of another length is refused before anything moves; the
Unity plugin declares the player's own layout."""

import random
import tempfile
import unittest
from pathlib import Path

from viwo.contracts.analysis import AnalysisTarget
from viwo.core.analysis.managed import laid_out
from viwo.plugins.unity import il2cpp_layout


def inputs(root: Path, count: int, rng: random.Random) -> tuple[Path, ...]:
    root.mkdir(parents=True, exist_ok=True)
    out = []
    for i in range(count):
        path = root / f"in{i}.bin"
        path.write_bytes(rng.randbytes(rng.randint(0, 30)))
        out.append(path)
    return tuple(out)


class LayoutTests(unittest.TestCase):
    def test_every_input_lands_where_its_plugin_says(self) -> None:
        rng = random.Random(61)
        parts = ["a", "b_Data", "il2cpp_data", "Metadata", "x y", "deep"]
        for case in range(80):
            with tempfile.TemporaryDirectory() as tmp:
                paths = inputs(Path(tmp) / "copies", rng.randint(1, 4), rng)
                layout = tuple(
                    "/".join([*rng.sample(parts, rng.randint(0, 3)), f"f{i}.dat"])
                    for i in range(len(paths))
                )
                data = [p.read_bytes() for p in paths]
                folder = Path(tmp) / "tool"
                target = AnalysisTarget("k", "il2cpp", paths, "p", layout=layout)
                self.assertEqual(laid_out(target, folder), folder, case)
                for rel, blob in zip(layout, data):
                    self.assertEqual(folder.joinpath(*rel.split("/")).read_bytes(), blob)

    def test_a_place_outside_or_a_missing_layout_moves_nothing(self) -> None:
        rng = random.Random(5)
        for bad in (("../up.dat",), ("/abs.dat",), ("C:/drive.dat",), (), ("a", "b")):
            with tempfile.TemporaryDirectory() as tmp:
                paths = inputs(Path(tmp) / "copies", 1, rng)
                target = AnalysisTarget("k", "il2cpp", paths, "p", layout=bad)
                self.assertIsNone(laid_out(target, Path(tmp) / "tool"), bad)
                self.assertTrue(paths[0].is_file(), bad)  # refused before anything moved

    def test_unity_declares_the_players_own_layout(self) -> None:
        self.assertEqual(
            il2cpp_layout(Path("x") / "My Game.exe"),
            (
                "GameAssembly.dll",
                "My Game_Data/il2cpp_data/Metadata/global-metadata.dat",
                "My Game.exe",
            ),
        )


if __name__ == "__main__":
    unittest.main()
