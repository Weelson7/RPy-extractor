"""L3: Ren'Py archives as properties: any RPA-2.0/3.0 archive (any key, prefixed chunks, byte
or text names) reads back byte for byte, a repack keeps every untouched member and carries every
edit, a malformed index is a named failure, and the unrpa and unrpyc processes name a missing
tool and a run that wrote nothing."""

from __future__ import annotations

import pickle
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.test_renpy import make_rpa
from viwo.contracts.types import OutcomeKind
from viwo.plugins.renpy import rpa
from viwo.plugins.renpy.decompile import UnrpycAnalyzer, UnrpycCli
from viwo.plugins.renpy.pack import RpaWriter

CTX = SimpleNamespace(cancel=SimpleNamespace(cancelled=False))


def _members(rng: random.Random) -> dict[str, bytes]:
    names = {f"{rng.choice(['images', 'audio'])}/f{i}.bin" for i in range(rng.randint(1, 7))}
    return {n: rng.randbytes(rng.randint(0, 120)) for n in names}


def _read(path: Path) -> dict[str, bytes]:
    out = {}
    with open(path, "rb") as fh:
        for name, chunks in rpa.read_index(fh).items():
            data = b""
            for offset, length, prefix in chunks:
                fh.seek(offset)
                data += prefix + fh.read(max(0, length - len(prefix)))
            out[name] = data
    return out


class RpaPropertyTests(unittest.TestCase):
    def test_any_archive_reads_back_and_a_repack_keeps_everything(self) -> None:
        rng = random.Random(10)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in range(15):
                files = _members(rng)
                version = rng.choice(["2.0", "3.0"])
                archive = make_rpa(
                    root / f"a{case}.rpa",
                    files,
                    version,
                    key=rng.getrandbits(32),
                    prefix_len=rng.choice([0, 0, 3]),
                )
                self.assertEqual(_read(archive), files)
                edits = {}
                for name in rng.sample(sorted(files), rng.randint(0, len(files))) + ["new/x.txt"]:
                    src = root / f"e{case}-{len(edits)}"
                    src.write_bytes(rng.randbytes(30))
                    edits[name] = src
                out = RpaWriter().pack(archive, edits, None)
                self.assertEqual(
                    (out.kind, out.files), (OutcomeKind.OK, len(set(files) | set(edits)))
                )
                want = {**files, **{n: p.read_bytes() for n, p in edits.items()}}
                self.assertEqual(_read(archive), want)

    def test_names_in_any_encoding_and_every_malformed_index_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = {
                "plain.txt".encode(): [(40, 1, b"")],
                "caf\xe9.txt".encode("latin-1"): [(40, 1, b"")],
            }
            archive = make_rpa(root / "names.rpa", {}, "2.0", payload=pickle.dumps(raw, protocol=2))
            with open(archive, "rb") as fh:
                self.assertEqual(sorted(rpa.read_index(fh)), ["café.txt", "plain.txt"])
            for payload, why in (
                (pickle.dumps([1, 2]), "not a mapping"),
                (pickle.dumps({"a": [7]}), "entry malformed"),
                (pickle.dumps({"a": [(1,)]}), "entry malformed"),
            ):
                bad = make_rpa(root / "bad.rpa", {}, "3.0", payload=payload)
                out = rpa.RpaSafe().extract(bad, root / "o", CTX)
                self.assertEqual(out.kind, OutcomeKind.FAILED)
                self.assertIn(why, out.error)
            cut = root / "cut.rpa"
            cut.write_bytes(b"RPA-3.0 0000000000000022\n")  # no key: cut short
            self.assertIn("cut short", rpa.RpaSafe().extract(cut, root / "o", CTX).error)
            big = make_rpa(root / "big.rpa", {"a": b"x" * 5000})
            with mock.patch.object(rpa, "INDEX_LIMIT", 16):
                self.assertIn("inflates past", rpa.RpaSafe().extract(big, root / "o", CTX).error)
            broken = root / "broken.rpa"
            broken.write_bytes(b"not an rpa")
            self.assertEqual(RpaWriter().pack(broken, {}, None).kind, OutcomeKind.FAILED)
            self.assertFalse(list(root.glob("*.viwo-tmp")))  # nothing half written
            short = make_rpa(root / "short.rpa", {"a": b"abcdef"})
            with open(short, "rb") as fh:  # a chunk past the end stops, never loops
                index = rpa.read_index(fh)
            index["a"] = [(index["a"][0][0], 10_000, b"")]
            with mock.patch("viwo.plugins.renpy.pack.read_index", return_value=index):
                self.assertEqual(RpaWriter().pack(short, {}, None).kind, OutcomeKind.OK)


def _ctx(root: Path, run, located=True):
    tool = SimpleNamespace(argv_prefix=("tool",))
    host = SimpleNamespace(
        tools=SimpleNamespace(locate=lambda spec: tool if located else None),
        process=SimpleNamespace(run=run),
    )
    return SimpleNamespace(os=host, cancel=None, staging=root / "staging", log=lambda *a, **k: None)


class ProcessBackendTests(unittest.TestCase):
    def test_missing_tools_and_runs_that_wrote_nothing_are_named(self) -> None:
        from viwo.contracts.analysis import AnalysisTarget

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "staging").mkdir()
            script = root / "in" / "script.rpyc"
            script.parent.mkdir()
            script.write_bytes(b"RENPY RPC2")

            def fail(argv, **k):
                return SimpleNamespace(ok=False, stderr="bad pickle", stdout="", returncode=1)

            for backend, call in (
                (UnrpycCli(), lambda b, c: b.decode(script, root / "d", c)),
                (
                    UnrpycAnalyzer(),
                    lambda b, c: b.analyze(
                        AnalysisTarget("s", "python_bytecode", (script,), "renpy"), c
                    ),
                ),
                (rpa.Unrpa(), lambda b, c: b.extract(root / "a.rpa", root / "u", c)),
            ):
                self.assertEqual(
                    call(backend, _ctx(root, None, False)).kind, OutcomeKind.UNAVAILABLE
                )
                out = call(backend, _ctx(root, fail))
                self.assertEqual(out.kind, OutcomeKind.FAILED)
                self.assertIn("bad pickle", out.error)
            done = lambda argv, **k: SimpleNamespace(ok=True, stderr="", stdout="")  # noqa: E731
            (root / "u").mkdir()
            (root / "u" / "x.png").write_bytes(b"x")
            self.assertEqual(
                rpa.Unrpa().extract(root / "a.rpa", root / "u", _ctx(root, done)).files, 1
            )


if __name__ == "__main__":
    unittest.main()
