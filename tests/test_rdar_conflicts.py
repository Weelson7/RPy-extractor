"""L3: Cyberpunk 2077 mod-over-base conflicts. For random installs the report counts exactly the
game members the mods replace and the members a later mod loses to an earlier one (first by name
in `archive/pc/mod`, then REDmod's `mods/*/archives`), names an archive it cannot read and says
nothing without mods; an extraction carries the findings in its warnings. Verified on a real
install: 15 mod archives replace 63 members of the game's archives."""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime
from tests.test_redengine import rdar
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.core.pipeline.runner import extract
from viwo.plugins.redengine import conflicts


def write(path: Path, hashes: set[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rdar({h: [b"x"] for h in hashes}))


class ReportTests(unittest.TestCase):
    def test_the_counts_are_exact_and_the_first_mod_wins(self) -> None:
        rng = random.Random(6)
        for _ in range(25):
            with tempfile.TemporaryDirectory() as tmp:
                game = Path(tmp)
                pool = list(range(1, 60))
                base = set(rng.sample(pool, 25))
                write(game / "archive/pc/content/basegame_1.archive", base)
                mods = []
                for i in range(rng.randint(0, 4)):
                    found = set(rng.sample(pool, rng.randint(0, 10)))
                    redmod = rng.random() < 0.3
                    path = (
                        game / f"mods/m{i}/archives/m{i}.archive"
                        if redmod
                        else game / f"archive/pc/mod/{rng.choice('abcxyz')}{i}.archive"
                    )
                    write(path, found)
                    mods.append((not redmod, path.name if not redmod else f"m{i}", path, found))
                order = sorted(mods, key=lambda m: (not m[0], m[1]))
                lines = conflicts.report(game)
                if not mods:
                    self.assertEqual(lines, [])
                    continue
                seen, lost = set(), 0
                for *_, found in order:
                    lost += len(found & seen)
                    seen |= found
                self.assertEqual(
                    lines[0],
                    f"mods: {len(mods)} archive(s) replace {len(seen & base)} member(s) "
                    "of the game's archives",
                )
                if lost:
                    self.assertIn(f"{lost} member(s) carried by more than one mod", lines[1])
                    if order[1][3] & order[0][3]:  # the first loser is the second mod
                        self.assertIn(f"(loses to {order[0][2].name})", lines[1])
                else:
                    self.assertEqual(len(lines), 1)

    def test_an_unreadable_archive_is_named_and_names_are_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            write(game / "archive/pc/ep1/ep1_1.archive", {7})
            write(game / "archive/pc/mod/a.archive", {7, 8})
            write(game / "archive/pc/mod/b.archive", {8})
            (game / "archive/pc/mod/broken.archive").write_bytes(b"RDAR" + b"\xff" * 20)
            (game / "archive/pc/content").mkdir(parents=True)
            (game / "archive/pc/content/damaged.archive").write_bytes(b"nope")
            lines = conflicts.report(game, lambda h: f"base/thing{h}.mesh")
            self.assertIn("replace 1 member(s)", lines[0])
            self.assertIn("base/thing8.mesh in b.archive (loses to a.archive)", lines[1])
            self.assertIn(
                "2 archive(s) could not be read: damaged.archive, broken.archive", lines[2]
            )


class PluginTests(unittest.TestCase):
    def test_the_path_list_names_the_conflict_and_is_closed(self) -> None:
        from types import SimpleNamespace
        from unittest import mock

        import viwo.plugins.redengine as plugin

        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            write(game / "archive/pc/mod/a.archive", {5})
            write(game / "archive/pc/mod/b.archive", {5})
            names = mock.Mock(get=lambda h: "base/v.mesh" if h == 5 else None)
            ctx = SimpleNamespace(game_root=game, os=SimpleNamespace())
            with mock.patch.object(plugin, "_names", return_value=(names, [])):
                said = plugin.RedenginePlugin().verify_report(ctx, [], None, 0)
            self.assertIn("base/v.mesh in b.archive (loses to a.archive)", said.warnings[1])
            names.close.assert_called_once()


class PipelineTests(unittest.TestCase):
    def test_an_extraction_says_what_the_mods_replace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "cp"
            (game / "REDprelauncher.exe").parent.mkdir(parents=True)
            (game / "REDprelauncher.exe").write_bytes(b"MZ")
            write(game / "archive/pc/content/basegame_1.archive", {0x10, 0x11})
            write(game / "archive/pc/mod/mymod.archive", {0x11, 0x12})
            request = ExtractionRequest(str(game), str(root / "ws"))
            result = extract(runtime(root), request, "j", lambda e: None, CancelToken())
            said = [w for w in result.warnings if w.startswith("mods:")]
            self.assertEqual(
                said, ["mods: 1 archive(s) replace 1 member(s) of the game's archives"]
            )


if __name__ == "__main__":
    unittest.main()
