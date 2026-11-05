"""L3: Cyberpunk 2077 resources through WolvenKit's console (decode.cr2w). Every extracted
resource reaches `convert serialize` once and only the classes `export` converts reach `export`,
in batches the command line holds; ViWo's export settings win over WolvenKit's shipped ones and
the user's other settings stay; every file WolvenKit could not convert is counted and said, and a
run that wrote nothing fails. End to end through a fake WolvenKit CLI: a texture comes out as PNG
and JSON beside the game's own file. Verified on real data: four mod archives (345 resources,
textures to PNG, meshes and animations to glTF, every resource to JSON)."""

from __future__ import annotations

import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.helpers import runtime
from tests.test_redengine import cr2w, rdar
from viwo.contracts import CancelToken, ExtractionRequest
from viwo.contracts.types import Outcome, OutcomeKind
from viwo.core import decode
from viwo.core.pipeline.runner import extract
from viwo.plugins.redengine import export
from viwo.plugins.redengine.export import BATCH, EXPORTS, SETTINGS, SUFFIXES, WolvenKitExport

FAKE = """import sys
from pathlib import Path
args = sys.argv[1:]
out = Path(args[args.index("-o") + 1])
kind = "png" if args[0] == "export" else "json"
for name in args[1:]:
    if name.endswith((".xbm", ".mesh", ".cr2w")) and Path(name).is_file():
        if kind == "png" and name.endswith(".mesh"):
            print(f"[ 0: Error ] - Failed to export {{name}}.")
            continue
        (out / f"{{Path(name).name}}.{{kind}}").write_text("{{}}")
print("[ 0: Information ] - done")
"""


def fake_wolvenkit(folder: Path) -> Path:
    """A Python stand-in for WolvenKit.CLI; a .cmd wrapper makes it runnable on Windows."""
    script = folder / "fake_wolvenkit.py"
    script.write_text(f"#!{sys.executable}\n" + FAKE.format())
    if sys.platform != "win32":
        script.chmod(0o755)
        return script
    wrapper = folder / "fake_wolvenkit.cmd"
    wrapper.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
    return wrapper


class CommandTests(unittest.TestCase):
    def test_every_resource_is_serialized_once_and_only_convertible_ones_exported(self) -> None:
        rng = random.Random(7)
        for _ in range(20):
            paths = [
                Path(f"r{i}{rng.choice(SUFFIXES)}") for i in range(rng.randint(0, 3 * BATCH + 5))
            ]
            runs = export.commands(paths, "GAME")
            serialized = [a for r in runs if r[0] == "convert" for a in r[2:]]
            exported = [a for r in runs if r[0] == "export" for a in r[1:-2]]
            self.assertEqual(serialized, [str(p) for p in paths])  # each once, in order
            self.assertEqual(exported, [str(p) for p in paths if p.suffix in EXPORTS])
            for run in runs:
                self.assertLessEqual(len(run), BATCH + 3)  # the command line stays short
                if run[0] == "export":
                    self.assertEqual(run[-2:], ["-gp", "GAME"])  # the game supplies the rest


class SettingsTests(unittest.TestCase):
    def test_viwos_values_win_and_the_users_others_stay(self) -> None:
        rng = random.Random(3)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / "appsettings.json"
            for _ in range(15):
                theirs = {f"Section{i}": {"k": rng.random()} for i in range(rng.randint(0, 3))}
                for section in SETTINGS:
                    if rng.random() < 0.5:
                        theirs[section] = {"UncookExtension": "dds", "other": rng.random()}
                prefix = "﻿" if rng.random() < 0.5 else ""  # WolvenKit writes a BOM
                path.write_text(prefix + json.dumps(theirs), encoding="utf-8")
                export.quiet_settings(folder)
                merged = json.loads(path.read_text(encoding="utf-8"))
                for section, values in SETTINGS.items():
                    self.assertEqual({**merged[section], **values}, merged[section])
                    if "other" in theirs.get(section, {}):
                        self.assertEqual(merged[section]["other"], theirs[section]["other"])
                for section in set(theirs) - set(SETTINGS):
                    self.assertEqual(merged[section], theirs[section])
                written = path.stat().st_mtime_ns
                export.quiet_settings(folder)  # nothing left to change: nothing written
                self.assertEqual(path.stat().st_mtime_ns, written)
            path.write_text("{ damaged", encoding="utf-8")
            export.quiet_settings(folder)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), SETTINGS)


class DecodeTests(unittest.TestCase):
    def ctx(self, tmp: Path, run, located: bool = True, home: str = "third_party"):
        where = tmp / home / "wolvenkit"
        where.mkdir(parents=True, exist_ok=True)
        tool = SimpleNamespace(argv_prefix=("wk",), path=str(where / "WolvenKit.CLI.dll"))
        host = SimpleNamespace(
            tools=SimpleNamespace(locate=lambda s: tool if located else None),
            process=SimpleNamespace(run=run),
        )
        self.logs = []
        return SimpleNamespace(os=host, game_root=tmp, cancel=None, log=self.logs.append)

    def test_every_failure_is_counted_and_an_empty_run_fails(self) -> None:
        rng = random.Random(5)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [root / f"t{i}.xbm" for i in range(9)]
            for _ in range(10):
                dest = root / f"out{rng.random()}"
                broken = rng.sample(range(len(paths)), rng.choice((0, 1, 4, 9)))

                def run(argv, cwd=None, timeout=None, cancel=None):
                    self.assertEqual(cwd, str(dest))  # nothing lands beside ViWo
                    said = ""
                    for i, p in enumerate(paths):
                        if i in broken:
                            said += f"[ 0: Error ] - Failed to export {p}.\n"
                        else:
                            (dest / f"{p.name}.{argv[1]}").write_text("x")
                    return SimpleNamespace(ok=True, stdout=said, stderr="")

                out = WolvenKitExport().decode_many(paths, dest, self.ctx(root, run))
                runs = 2  # export and convert serialize, each sees every file
                if len(broken) == len(paths):
                    self.assertEqual(out.kind, OutcomeKind.FAILED)
                    self.assertIn("Failed to export", out.error)
                    continue
                self.assertEqual((out.kind, out.files), (OutcomeKind.OK, 2 * (9 - len(broken))))
                self.assertIn(f"{len(paths)} CR2W file(s)", out.notes[0])
                if broken:
                    self.assertIn(f"could not convert {runs * len(broken)} file(s)", out.error)
                    self.assertIn(f"t{min(broken)}.xbm", out.error)  # the first one named
                else:
                    self.assertEqual(out.error, "")

    def test_a_missing_tool_and_a_silent_crash_are_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gone = WolvenKitExport().decode(root / "a.xbm", root / "o", self.ctx(root, None, False))
            self.assertEqual(gone.kind, OutcomeKind.UNAVAILABLE)
            self.assertIn("viwo install wolvenkit", gone.error)
            crash = SimpleNamespace(ok=False, stdout="", stderr="Unhandled exception")
            out = WolvenKitExport().decode(
                root / "a.xbm", root / "o", self.ctx(root, lambda *a, **k: crash)
            )
            self.assertEqual((out.kind, out.error), (OutcomeKind.FAILED, "Unhandled exception"))
            self.assertTrue((root / "third_party" / "wolvenkit" / "appsettings.json").is_file())
            mine = self.ctx(root, lambda *a, **k: crash, home="MyTools")  # the user's own install
            WolvenKitExport().decode(root / "a.xbm", root / "o", mine)
            self.assertFalse((root / "MyTools" / "wolvenkit" / "appsettings.json").exists())
            self.assertIn("settings left as they are", self.logs[0])


class PipelineTests(unittest.TestCase):
    def extract(self, root: Path, archives: dict[str, dict[int, list[bytes]]]):
        game = root / "cp"
        (game / "archive" / "pc" / "content").mkdir(parents=True)
        (game / "REDprelauncher.exe").write_bytes(b"MZ")
        for name, members in archives.items():
            (game / "archive" / "pc" / "content" / name).write_bytes(rdar(members))
        body = f"[tools]\nwolvenkit = {fake_wolvenkit(root)}\n"
        events = []
        request = ExtractionRequest(str(game), str(root / "ws"))
        result = extract(runtime(root, body), request, "j", events.append, CancelToken())
        return result, events

    def test_another_engines_files_never_reach_wolvenkit(self) -> None:
        """`.json` and `.mesh` are CR2W suffixes too: only a Cyberpunk run decodes them."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "other"
            (game / "data").mkdir(parents=True)
            (game / "data" / "Actors.json").write_text("[]")
            (game / "data" / "hero.mesh").write_bytes(b"OGRE mesh")
            body = f"[tools]\nwolvenkit = {fake_wolvenkit(root)}\n"
            events = []
            request = ExtractionRequest(str(game), str(root / "ws"))
            result = extract(runtime(root, body), request, "j", events.append, CancelToken())
            self.assertFalse([e for e in events if "WolvenKit" in e.message])
            self.assertFalse([w for w in result.warnings if "cr2w" in w])
            self.assertFalse((root / "ws" / "json" / "Actors.json.json").exists())

    def test_a_clean_batch_warns_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            texture = {0x1234: [cr2w("CBitmapTexture"), b"pixels"]}
            result, _ = self.extract(Path(tmp), {"basegame_1.archive": texture})
            self.assertTrue((Path(tmp) / "ws" / "png" / "0000000000001234.xbm.png").is_file())
            self.assertFalse([w for w in result.warnings if "cr2w" in w])

    def test_a_texture_comes_out_as_png_and_json_and_a_failure_is_warned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result, events = self.extract(
                root,
                {
                    "basegame_1.archive": {0x1234: [cr2w("CBitmapTexture"), b"pixels"]},
                    "mod.archive": {0x77: [cr2w("CMesh")]},  # the fake fails on every mesh
                },
            )
            ws = root / "ws"
            self.assertTrue((ws / "xbm" / "0000000000001234.xbm").is_file())  # the game's own
            self.assertTrue((ws / "png" / "0000000000001234.xbm.png").is_file())
            self.assertTrue((ws / "json" / "0000000000001234.xbm.json").is_file())
            self.assertTrue((ws / "json" / "0000000000000077.mesh.json").is_file())
            self.assertFalse((ws / "png" / "0000000000000077.mesh.png").exists())
            self.assertTrue(any("2 CR2W file(s) through WolvenKit" in e.message for e in events))
            said = [w for w in result.warnings if w.startswith("decode.cr2w:")]
            self.assertEqual(len(said), 1)
            self.assertIn("could not convert 1 file(s), e.g. Failed to export", said[0])


class BatchTests(unittest.TestCase):
    def test_a_fallback_is_warned_and_a_failed_batch_leaves_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logs = []
            run = SimpleNamespace(
                work=Path(tmp),
                rt=SimpleNamespace(bindings={"decode.cr2w": None}, backends={}),
                log=lambda m, stage, level="info": logs.append((m, level)),
            )
            rels = ["a.xbm", "b.mesh"]
            for kind, fallback in ((OutcomeKind.OK, "main missing"), (OutcomeKind.FAILED, "")):
                outcome = Outcome(kind, error="WolvenKit crashed", fallback=fallback)
                with mock.patch.object(
                    decode, "run_with_failover", return_value=(outcome, "spare")
                ):
                    source, why = decode._decode_batch(run, None, Path(tmp), rels, "decode.cr2w")
                if kind is OutcomeKind.OK:
                    self.assertTrue(source.root.is_dir())
                    self.assertEqual(why, "WolvenKit crashed")  # partial: still said
                    self.assertIn(("decode.cr2w: main missing", "warn"), logs)
                else:
                    self.assertIsNone(source)
                    self.assertEqual(why, "2 file(s): WolvenKit crashed")
            self.assertEqual(len(list(Path(tmp).glob("dec-*"))), 1)  # the failed one is removed

    def test_parts_move_the_counter_and_say_every_failure_once(self) -> None:
        rng = random.Random(16)
        for _ in range(40):
            rels = [f"f{i}.xbm" for i in range(rng.randint(1, 3 * decode.PART + 7))]
            parts = -(-len(rels) // decode.PART)
            bad = {k for k in range(parts) if rng.random() < 0.4}
            stop = rng.choice([None, rng.randrange(parts)])
            calls = []
            run = SimpleNamespace(cancel=SimpleNamespace(cancelled=False))

            def one(run, ctx, ws, part, slot, bad=bad, stop=stop, calls=calls):
                calls.append(part)
                run.cancel.cancelled = len(calls) - 1 == stop  # the user cancels during it
                return (None, f"part {len(calls) - 1}") if len(calls) - 1 in bad else ("s", "")

            ticker = SimpleNamespace(done=0)
            ticker.tick = lambda n, t=ticker: setattr(t, "done", t.done + n)
            with mock.patch.object(decode, "_decode_batch", one):
                sources, why = decode._decode_parts(run, None, Path("ws"), rels, "s", ticker)
            ran = parts if stop is None else stop + 1
            self.assertEqual(len(calls), ran)  # nothing runs after a cancel
            self.assertEqual(sum(calls, []), rels[: sum(len(c) for c in calls)])
            self.assertTrue(all(len(c) <= decode.PART for c in calls))
            self.assertEqual(ticker.done, sum(len(c) for c in calls))  # every file counted
            failed = sorted(k for k in bad if k < ran)
            self.assertEqual(len(sources), ran - len(failed))
            if not failed:
                self.assertEqual(why, "")
                continue
            self.assertTrue(why.startswith(f"part {failed[0]}"), why)  # one warning, the first
            self.assertEqual(f"{len(failed) - 1} more part(s)" in why, len(failed) > 1, why)

    def test_a_cancelled_run_decodes_nothing_and_warns_nothing(self) -> None:
        batch = SimpleNamespace(decode_many=None)
        run = SimpleNamespace(
            rt=SimpleNamespace(
                bindings={s: SimpleNamespace(main=s) for s in ("decode.cr2w", "decode.audio")},
                backends={"decode.cr2w": batch, "decode.audio": object()},
            ),
            ctx=lambda owner: SimpleNamespace(options={}),
            cancel=SimpleNamespace(cancelled=True),
            log=lambda *a, **k: None,
        )
        collected = SimpleNamespace(provenance=[{"path": "a.xbm"}, {"path": "b.wem"}], warnings=[])
        wanted = {".xbm": "decode.cr2w", ".wem": "decode.audio"}
        with (
            mock.patch.object(decode, "_wanted", return_value=wanted),
            mock.patch.object(decode, "_decode_batch", return_value=(None, "")) as batched,
        ):
            decode.decode_all(run, Path("ws"), collected)
        self.assertEqual(batched.call_args[0][3], ["a.xbm"])  # the batch slot got its files
        self.assertEqual(collected.warnings, [])  # cancelled is not a failure
        self.assertEqual(len(collected.provenance), 2)  # nothing was added


if __name__ == "__main__":
    unittest.main()
