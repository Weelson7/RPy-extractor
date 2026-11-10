"""L1: the data of the presentation (tools/presentation). Properties: every game of every
games-pass report becomes one entry whose passed and missed flags add up to its flags, in the
reports' order, and the PDF's table has one row per entry; a damaged or missing report is
no entry, not a crash; the deck's generator is pinned (HTTPS, sha256, one file) and loads
nothing but that file and its data."""

import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "presentation"))

import ctf  # noqa: E402

from viwo.core import thirdparty  # noqa: E402


class CtfDataTests(unittest.TestCase):
    def test_every_game_is_one_entry_and_its_flags_add_up(self) -> None:
        rng = random.Random(46)
        with tempfile.TemporaryDirectory() as tmp:
            for round_ in range(15):
                store, want = Path(tmp) / f"d{round_}", []
                for slug in sorted(f"pass-{i}" for i in range(rng.randint(0, 6))):
                    folder = store / "games-pass" / slug
                    folder.mkdir(parents=True)
                    if rng.random() < 0.2:
                        (folder / "report.json").write_text("{ damaged", encoding="utf-8")
                        continue
                    judged = [
                        {"name": f"flag{k}", "ok": rng.random() < 0.7}
                        for k in range(rng.randint(0, 9))
                    ]
                    game = {"game": slug, "flags": judged, "gameUnchanged": rng.random() < 0.9}
                    if rng.random() < 0.8:
                        game["extract"] = {"plugins": ["unity"], "copied": rng.randint(0, 9**6)}
                    (folder / "report.json").write_text(json.dumps([game]), encoding="utf-8")
                    want.append((slug, len(judged), sum(f["ok"] for f in judged)))
                games = ctf.flags(store)
                self.assertEqual([(g["game"], g["flags"], g["ok"]) for g in games], want)
                for g in games:
                    self.assertEqual(len(g["missed"]), g["flags"] - g["ok"])
                table = ctf.passes(store)
                self.assertEqual(table.count("<tr><td>"), len(want))
                self.assertEqual("No games pass yet" in table, not want)  # said, never blank

    def test_the_deck_generator_is_one_pinned_file(self) -> None:
        pin = thirdparty.manifest()["tools"]["pptxgenjs"]
        for os_id in ("windows", "linux"):
            self.assertTrue(pin[os_id]["url"].startswith("https://"))
            self.assertIn(f"@{pin['version']}/", pin[os_id]["url"])  # the version, not "latest"
            self.assertRegex(pin[os_id]["sha256"], r"^[0-9a-f]{64}$")
        script = (ROOT / "tools" / "presentation" / "deck.js").read_text(encoding="utf-8")
        needs = {line.split('"')[1] for line in script.splitlines() if "require(" in line}
        self.assertEqual(needs, {"fs", "path"})  # nothing to install beside the pinned file


if __name__ == "__main__":
    unittest.main()
