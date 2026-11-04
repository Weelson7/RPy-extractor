"""L1: the command bodies behind `viwo slots --check`, `viwo unpack --slot/--backend`,
`viwo patch` and `viwo mod`, checked as properties over random inputs: what the command
reports matches what it did, a refusal never writes, and the exit code follows the result."""

from __future__ import annotations

import hashlib
import json
import random
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests.helpers import make_zip, runtime, tree_hashes, write_ini
from tests.test_cli import run
from viwo.cli import EXIT
from viwo.cli_check import _backend_for, slots_check
from viwo.contracts import ViwoError


def _members(rng: random.Random) -> dict[str, bytes]:
    names = {f"d{rng.randrange(3)}/f{i}.bin" for i in range(rng.randint(1, 8))}
    return {n: rng.randbytes(rng.randint(0, 300)) for n in names}


def _hashes(folder: Path) -> dict[str, str]:
    return {
        p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in folder.rglob("*")
        if p.is_file()
    }


def _probe(fails: bool, crashes: bool):
    def check(_os):
        if crashes:
            raise RuntimeError("probe crashed")
        return (not fails), ("broken" if fails else "")

    return check


class SlotsCheckTests(unittest.TestCase):
    def test_failed_lists_exactly_the_failing_mains(self) -> None:
        rng = random.Random(7)
        with tempfile.TemporaryDirectory() as tmp:
            rt = runtime(Path(tmp))
            bound = sorted({b for x in rt.bindings.values() for b in (x.main, x.spare) if b})
            for _ in range(12):
                bad = set(rng.sample(bound, rng.randint(0, 4)))
                crash = set(rng.sample(sorted(bad), len(bad) // 2)) if bad else set()
                for bid in bound:
                    rt.backends[bid].self_check = _probe(bid in bad, bid in crash)
                failing = {s for s, b in rt.bindings.items() if b.main in bad}
                try:
                    data = slots_check(rt)
                except ViwoError as err:
                    self.assertTrue(failing)
                    self.assertEqual(err.code, "failed")
                    self.assertTrue(err.message.startswith(f"{len(failing)} bound main"))
                    continue
                self.assertFalse(failing)  # it passes only when no bound main failed
                for row in data["checks"]:
                    self.assertEqual(row["ok"], row["backend"] not in bad)
                    if row["backend"] in crash:  # a crashing self-test is a named failure
                        self.assertIn("RuntimeError", row["reason"])
                checked = {(r["slot"], r["role"]) for r in data["checks"]}
                for slot, b in rt.bindings.items():
                    self.assertEqual((slot, "main") in checked, bool(b.main))
                    self.assertEqual((slot, "spare") in checked, bool(b.spare))

    def test_cli_exit_code_follows_the_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ini = str(write_ini(Path(tmp)))
            code, out, _ = run(["--json", "--ini", ini, "slots", "--check"])
            body = json.loads(out)
            self.assertEqual(code == 0, body["ok"])
            if body["ok"]:
                self.assertEqual(body["data"]["failed"], [])
            code, out, err = run(["--ini", ini, "slots", "--check"])
            self.assertTrue("backend(s) checked" in out or "self-check" in err)


class ForcedUnpackTests(unittest.TestCase):
    def test_backend_choice_always_serves_the_slot(self) -> None:
        rng = random.Random(3)
        with tempfile.TemporaryDirectory() as tmp:
            rt = runtime(Path(tmp))
            slots = [*sorted(rt.bindings), "no.such.slot"]
            choices = ["", "main", "spare", "nobody", *sorted(rt.backends)]
            for _ in range(300):
                slot, choice = rng.choice(slots), rng.choice(choices)
                try:
                    got = _backend_for(rt, slot, choice)
                except ViwoError as err:
                    self.assertIn(err.code, {"invalid_request", "unavailable"})
                    continue
                self.assertIn(rt.slots[slot].family, rt.backends[got].families)
                if choice in ("", "main", "spare"):
                    self.assertEqual(got, getattr(rt.bindings[slot], choice or "main"))

    def test_forced_unpack_extracts_exactly_the_archive_without_nesting(self) -> None:
        rng = random.Random(11)
        forces = (
            ["--slot", "unarchive.zip"],
            ["--slot", "unarchive.zip", "--backend", "main"],
            ["--backend", "py-zipfile"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ini = str(write_ini(root))
            for i in range(6):
                members = _members(rng)
                members["inner.zip"] = make_zip(root / f"in{i}.zip", {"x.txt": b"x"}).read_bytes()
                archive = make_zip(root / f"a{i}.zip", members)
                out = root / f"out{i}"
                argv = ["--json", "--ini", ini, "unpack", str(archive), "--out", str(out)]
                code, stdout, _ = run([*argv, *rng.choice(forces)])
                self.assertEqual(code, 0, stdout)
                data = json.loads(stdout)["data"]
                self.assertEqual(data["slot"], "unarchive.zip")
                self.assertEqual(data["byBackend"], {"py-zipfile": 1})
                want = {n: hashlib.sha256(b).hexdigest() for n, b in members.items()}
                self.assertEqual(_hashes(out), want)  # inner.zip stays a file: no nesting

    def test_refusals_write_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ini = str(write_ini(root))
            archive = make_zip(root / "a.zip", {"f.txt": b"f"})
            (root / "full").mkdir()
            (root / "full" / "keep.txt").write_text("keep")
            corrupt = root / "c.zip"
            corrupt.write_bytes(b"PK" + bytes(64))
            cases = [
                (archive, "full", ["--slot", "unarchive.zip"], "refused"),
                (root / "none.zip", "o1", ["--slot", "unarchive.zip"], "invalid_request"),
                (archive, "o2", ["--slot", "no.slot"], "invalid_request"),
                (
                    archive,
                    "o3",
                    ["--slot", "unarchive.zip", "--backend", "zip-packer"],
                    "invalid_request",
                ),
                (archive, "o7", ["--slot", "unarchive.zip", "--backend", "rpa-safe"], "failed"),
                (archive, "o4", ["--backend", "nobody"], "invalid_request"),
                (archive, "o5", ["--slot", "unarchive.bms"], "unavailable"),
                (corrupt, "o6", ["--slot", "unarchive.zip"], "failed"),
            ]
            for src, out, force, code_name in cases:
                before = tree_hashes(root / "full")
                argv = ["--ini", ini, "unpack", str(src), "--out", str(root / out), *force]
                code, _, err = run(argv)
                self.assertEqual(code, EXIT.get(code_name, 1), force)
                self.assertIn(f"viwo: {code_name}", err)
                self.assertNotIn("Traceback", err)
                self.assertEqual(tree_hashes(root / "full"), before)
                if out != "full":
                    self.assertFalse((root / out).exists() and any((root / out).iterdir()))


def _game(root: Path, rng: random.Random) -> tuple[Path, list[dict]]:
    game = root / "game"
    game.mkdir()
    body = bytearray(b"MZ" + rng.randbytes(254))
    patches = []
    for off in sorted(rng.sample(range(2, 256), rng.randint(1, 5))):
        new = (body[off] + 1 + rng.randrange(255)) % 256  # always another byte
        patches.append(
            {
                "file": "Game.exe",
                "offset": hex(off),
                "original": f"{body[off]:02x}",
                "patched": f"{new:02x}",
            }
        )
    (game / "Game.exe").write_bytes(bytes(body))
    return game, patches


def _set(root: Path, patches: list[dict]) -> Path:
    path = root / "p.patch.json"
    path.write_text(json.dumps({"schema": 1, "patches": patches}))
    return path


class PatchCommandTests(unittest.TestCase):
    def test_plan_then_apply_lands_every_byte_and_never_writes_the_game(self) -> None:
        rng = random.Random(5)
        for _ in range(5):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                base = ["--json", "--ini", str(write_ini(root)), "patch"]
                game, patches = _game(root, rng)
                set_path = _set(root, patches)
                before = tree_hashes(game)
                code, out, _ = run([*base, str(game), str(set_path), "--plan"])
                self.assertEqual(code, 0, out)
                planned = json.dumps(json.loads(out)["data"])
                self.assertEqual(planned.count('"ready"'), len(patches))
                code, _, _ = run([*base, str(game), str(set_path)])
                self.assertEqual(code, EXIT["invalid_request"])  # neither --out nor --plan
                copy = root / "copy"
                code, out, _ = run([*base, str(game), str(set_path), "--out", str(copy)])
                self.assertEqual(code, 0, out)
                written = (copy / "Game.exe").read_bytes()
                for p in patches:
                    self.assertEqual(written[int(p["offset"], 16)], int(p["patched"], 16))
                self.assertEqual(tree_hashes(game), before)
                code, out, _ = run([*base, str(root / "gone"), str(set_path), "--plan"])
                self.assertEqual(code, 1)
                self.assertEqual(json.loads(out)["error"]["code"], "not_found")


class ModCommandTests(unittest.TestCase):
    def test_pack_check_apply_round_trip_with_random_needs(self) -> None:
        rng = random.Random(9)
        words = ["a", "b", " c ", "", "dee", "e f"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = ["--json", "--ini", str(write_ini(root)), "mod"]
            game, patches = _game(root, rng)
            copy = root / "copy"
            run(["--ini", str(root / "test.ini"), "patch", str(game), str(_set(root, patches)),
                 "--out", str(copy)])  # fmt: skip
            (copy / "added.txt").write_bytes(rng.randbytes(50))
            game_files = {k: v for k, v in _hashes(copy).items() if not k.startswith(".viwo")}
            for i in range(6):
                requires = ",".join(rng.sample(words, rng.randint(0, 3)))
                after = ",".join(rng.sample(words, rng.randint(0, 2)))
                zip_path = root / f"m{i}.zip"
                needs = ["--requires", requires, "--after", after]
                argv = [*base, "pack", str(game), str(zip_path), "--copy", str(copy), *needs]
                code, out, _ = run(argv)
                self.assertEqual(code, 0, out)
                manifest = json.loads(zipfile.ZipFile(zip_path).read("viwo-mod.json"))
                for key, text in (("requires", requires), ("after", after)):
                    want = [s.strip() for s in text.split(",") if s.strip()]
                    self.assertEqual(manifest.get(key, []), want)  # trimmed, blanks dropped
                code, out, _ = run([*base, "check", str(game), str(zip_path)])
                self.assertEqual(code, 0, out)
                self.assertTrue(all(m["fits"] for m in json.loads(out)["data"]["mods"]))
                target = root / f"second{i}"
                argv = [*base, "apply", str(game), str(zip_path), "--copy", str(target)]
                code, out, _ = run(argv)
                missing = manifest.get("requires", [])
                if missing:  # applied alone, a mod that needs another is refused, unwritten
                    self.assertEqual(code, EXIT["invalid_request"], out)
                    self.assertIn(f"requires {missing[0]}", out)
                    self.assertFalse(target.exists())
                    continue
                self.assertEqual(code, 0, out)
                rebuilt = {k: v for k, v in _hashes(target).items() if not k.startswith(".viwo")}
                self.assertEqual(rebuilt, game_files)  # the same copy, rebuilt from the game
            for action in ("pack", "apply"):  # both write a copy: refused without one
                code, _, err = run([*base[1:], action, str(game), str(zip_path)])
                self.assertEqual(code, EXIT["invalid_request"])
                self.assertIn("--copy", err)


class DynamicCommandTests(unittest.TestCase):
    def test_trace_functions_are_trimmed_globs_and_nothing_else_changes(self) -> None:
        rng = random.Random(13)
        pieces = ["CreateFileW", " ReadFile ", "", "  ", "Nt*", "send"]
        with tempfile.TemporaryDirectory() as tmp:
            ini = str(write_ini(Path(tmp)))
            for _ in range(20):
                text = ",".join(rng.choice(pieces) for _ in range(rng.randint(1, 5)))
                seen = []
                with mock.patch(
                    "viwo.core.capture.runtime.run",
                    side_effect=lambda rt, kind, req, sink: seen.append((kind, req)) or {},
                ):
                    argv = ["--json", "--ini", ini, "trace", "--pid", "7", "--workspace", tmp]
                    code, out, _ = run([*argv, "--functions", text, "--seconds", "1.5"])
                self.assertEqual(code, 0, out)
                kind, req = seen[0]
                self.assertEqual(kind, "trace")
                want = tuple(p.strip() for p in text.split(",") if p.strip())
                self.assertEqual(req.functions, want)
                self.assertEqual((req.pid, req.seconds, req.workspace), (7, 1.5, Path(tmp)))
        with tempfile.TemporaryDirectory() as tmp:  # a blank list would trace nothing: refused
            from viwo.core.capture.runtime import RuntimeRequest, trace

            rt = runtime(Path(tmp), "[startup]\nfeatures = extraction, capture\n")
            with self.assertRaises(ViwoError) as err:
                trace(rt, RuntimeRequest(Path(tmp), pid=7, functions=()))
            self.assertEqual(err.exception.code, "invalid_request")

    def test_every_capture_warning_is_said_before_launch_unless_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ini = str(write_ini(root, "[startup]\nfeatures = extraction, capture\n"))
            for marker in ("", "EasyAntiCheat", "BattlEye"):
                game = root / f"g{marker}"
                (game / marker).mkdir(parents=True, exist_ok=True)
                said = []

                def fake(rt, req, note, game=game):
                    from viwo.core.capture import warnings

                    said.append(warnings(rt, game))
                    return {"gathered": 0}

                argv = ["--json", "--ini", ini, "capture", str(game), "--exe", str(game / "G.exe")]
                argv += ["--workspace", str(root / "ws"), "--confirm"]
                for quiet in (False, True):
                    with mock.patch("viwo.core.capture.capture", side_effect=fake):
                        code, _, err = run(["--quiet", *argv] if quiet else argv)
                    self.assertEqual(code, 0, err)
                    lines = [x for x in err.splitlines() if x.startswith("[CAPTURE:WARN]")]
                    expected = [] if quiet else [f"[CAPTURE:WARN] {w}" for w in said[-1]]
                    self.assertEqual(lines, expected)
                    if marker and not quiet:
                        self.assertTrue(any("anti-cheat" in x for x in lines), lines)


if __name__ == "__main__":
    unittest.main()
