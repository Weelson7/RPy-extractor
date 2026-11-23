"""L3: content search (doc 6.7). Text as UTF-8, UTF-16LE and UTF-16BE, case-sensitive or in any
case; integers in every width and byte order that fits, floats as 32 and 64 bits, the encodings
tried named; byte patterns with `??` through the patch sets' own parser. A hit in a PE carries
its section, RVA and VA and the unique signature `patch.sig` computes; the caps are said when
they drop a hit; an unreadable file or folder is named; the target is never written. Properties:
over random data, any chunk size finds exactly the matches a brute force finds (a match across
two chunks once), and the mapped-file signature is the one `signature()` gives on bytes."""

from __future__ import annotations

import io
import json
import os
import random
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tests.helpers import runtime, tree_hashes
from tests.test_patchsets import _brute, make_pe
from viwo.contracts import ViwoError
from viwo.contracts.types import CancelToken
from viwo.core import search
from viwo.core.patch_tools import signature
from viwo.core.search_query import build


def hits(target: Path, query, **caps) -> dict:
    events = []
    report = search.search(target, query, search.Limits(**caps), events.append)
    report["events"] = [e.message for e in events]
    return report


def where(report: dict) -> list[tuple[str, int, str]]:
    return [(h["file"], h["offset"], h["encoding"]) for h in report["hits"]]


class TextTests(unittest.TestCase):
    def test_each_encoding_case_sensitive_and_in_any_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "t.bin"
            body = b"..Hello.." + "héLLo".encode("utf-16-le") + b"#" + "HELLO".encode("utf-16-be")
            f.write_bytes(body)
            exact = hits(f, build("text", "Hello"))
            self.assertEqual(where(exact), [("t.bin", 2, "utf-8")])
            self.assertEqual(exact["query"]["tried"], ["utf-8", "utf-16le", "utf-16be"])
            loose = hits(f, build("text", "HÉllo", ignore_case=True))  # é/É: any script
            labels = [h["encoding"] for h in loose["hits"]]
            self.assertEqual(labels, ["utf-16le (any case)"])
            self.assertEqual(loose["hits"][0]["offset"], 9)
            every = hits(f, build("text", "hello", ignore_case=True))
            self.assertEqual(
                [(o, e.split()[0]) for _, o, e in where(every)],
                [(2, "utf-8"), (20, "utf-16be")],  # héLLo has an é, not an e
            )
            self.assertEqual(every["hits"][0]["match"], "48 65 6c 6c 6f")
            self.assertIn("Hello", every["hits"][0]["text"])

    def test_bad_queries_are_refused_by_name(self) -> None:
        for kind, value in (("text", ""), ("pixels", "x"), ("number", "abc"), ("bytes", "7G")):
            with self.assertRaises(ViwoError) as err:
                build(kind, value)
            self.assertEqual(err.exception.code, "invalid_request", (kind, value))
        for widths in ("3", "a", [16]):
            with self.assertRaises(ViwoError):
                build("number", "5", widths=widths)
        with self.assertRaises(ViwoError):
            build("text", "x" * 70000)  # longer than two chunks may share
        with self.assertRaises(ViwoError):
            build("number", str(1 << 70))  # fits no width
        with self.assertRaises(ViwoError):
            search.Limits(per_file=0)
        with self.assertRaises(ViwoError):
            search.Limits(signatures=-1)


class NumberTests(unittest.TestCase):
    def test_every_width_and_order_that_fits_and_what_was_not_tried(self) -> None:
        q = build("number", "0x1234")
        self.assertEqual(q.tried(), ["u16le", "u16be", "u32le", "u32be", "u64le", "u64be"])
        self.assertIn("1-byte forms not tried (ask for width 1)", q.notes)
        q = build("number", "70000", widths="1,2,4")
        self.assertEqual(q.tried(), ["u32le", "u32be"])
        self.assertEqual(len([n for n in q.notes if "does not fit" in n]), 2)
        self.assertEqual(build("number", "-2", widths=[2]).needles[0].literal, b"\xfe\xff")
        self.assertEqual(build("number", "-2", widths=[2]).tried(), ["i16le", "i16be"])
        self.assertEqual(build("number", "0", widths=[1, 2]).tried(), ["u8", "u16le/u16be"])
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "n.bin"
            f.write_bytes(b"\x00\x34\x12\xff" + b"\x00\x00\x12\x34" + b"\x34\x12\x00\x00\xee")
            found = [(o, e) for _, o, e in where(hits(f, build("number", "4660")))]
            self.assertEqual(
                found, [(1, "u16le"), (4, "u32be"), (6, "u16be"), (8, "u16le"), (8, "u32le")]
            )  # file order; one place may hold the value in two widths

    def test_floats_in_both_widths_and_orders(self) -> None:
        q = build("number", "1.5")
        self.assertEqual(q.tried(), ["f32le", "f32be", "f64le", "f64be"])
        self.assertEqual(q.notes, ())
        self.assertIn("nearest single-precision", " ".join(build("number", "0.1").notes))
        big = build("number", "1e300")
        self.assertEqual(big.tried(), ["f64le", "f64be"])
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "f.bin"
            f.write_bytes(b"\x01" + q.needles[0].literal + q.needles[3].literal)
            self.assertEqual(where(hits(f, q)), [("f.bin", 1, "f32le"), ("f.bin", 5, "f64be")])


class PatternTests(unittest.TestCase):
    def test_wildcards_overlaps_and_the_shared_parser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "p.bin"
            f.write_bytes(b"\x8b\x45\xfc\x90\x00\xcc\xcc\xcc\x00\x8b\x00\x91")
            find = lambda text: hits(f, build("bytes", text))  # noqa: E731
            offsets = lambda text: [o for _, o, _ in where(find(text))]  # noqa: E731
            self.assertEqual(offsets("8B ?? FC 90"), [0])
            self.assertEqual(offsets("CC CC"), [5, 6])  # overlapping, as a patch set counts them
            self.assertEqual(offsets("8B ?? ??"), [0, 9])
            self.assertEqual(offsets("8B" + " ??" * 12), [])  # longer than what is left

    def test_any_chunk_size_finds_what_a_brute_force_finds(self) -> None:
        rng = random.Random(61)
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "r.bin"
            for case in range(150):
                data = bytes(rng.choice(b"\xcc\x90\x41") for _ in range(rng.randint(0, 90)))
                f.write_bytes(data)
                size = rng.randint(1, 6)
                pattern = bytes(rng.choice(b"\xcc\x90\x41") for _ in range(size))
                mask = [rng.random() < 0.75 for _ in range(size)]
                text = " ".join(f"{b:02X}" if m else "??" for b, m in zip(pattern, mask))
                with mock.patch.object(search, "CHUNK", rng.randint(1, 12)):
                    report = hits(f, build("bytes", text), per_file=10_000, total=10_000)
                expected = _brute(data, pattern, mask)
                self.assertEqual([h["offset"] for h in report["hits"]], expected, (case, text))
            f.write_bytes(b"x" * 30 + b"needle" + b"x" * 30)
            for chunk in range(1, 40):  # the needle across every possible boundary
                with mock.patch.object(search, "CHUNK", chunk):
                    self.assertEqual(
                        where(hits(f, build("text", "needle"))), [("r.bin", 30, "utf-8")]
                    )


class PeTests(unittest.TestCase):
    def test_a_hit_in_an_executable_has_its_section_rva_va_and_signature(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "Game.exe"
            make_pe(exe)
            data = exe.read_bytes()
            hit = hits(exe, build("bytes", "74 05 90"))["hits"][0]
            self.assertEqual((hit["offset"], hit["section"]), (0x210, ".text"))
            self.assertEqual((hit["rva"], hit["va"]), (0x1010, 0x140001010))
            pattern, at = signature(data, 0x210)
            self.assertEqual(hit["signature"], {"pattern": pattern, "at": at})
            self.assertEqual(
                hit["patch"], {"file": "Game.exe", "offset": "0x210", "original": "74 05 90"}
            )
            head = hits(exe, build("text", "PE"))["hits"][0]  # in the headers: no section
            self.assertEqual((head["offset"], head["section"], head["rva"]), (0x40, None, None))
            first = hits(exe, build("bytes", "74 05"), signatures=0)["hits"][0]
            self.assertNotIn("signature", first)  # past the per-file count
            pad = Path(tmp) / "pad.bin"
            pad.write_bytes(b"\x90" * 200)
            nop = hits(pad, build("bytes", "90 90"), per_file=1)["hits"][0]
            self.assertIn("no unique signature", nop["signature"]["error"])  # NOP padding

    def test_a_signature_matches_once_where_a_patch_set_looks_for_it(self) -> None:
        """Mapped or in memory, the signature a hit offers is unique the way a patch set's
        pattern must be (overlapping matches count) and resolves to the hit's offset."""
        from viwo.core.patchsets import _hits

        rng = random.Random(62)
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "s.bin"
            for _ in range(80):
                data = bytes(rng.choice(b"\x00\x90") for _ in range(rng.randint(1, 300)))
                f.write_bytes(data)
                offset = rng.randrange(len(data))
                with open(f, "rb") as fh:
                    with search.mmap.mmap(fh.fileno(), 0, access=search.mmap.ACCESS_READ) as mm:
                        mapped = search._signature(mm, offset)
                try:
                    pattern, at = signature(data, offset)
                except ViwoError as exc:
                    self.assertEqual(mapped, {"error": exc.message})
                    continue
                self.assertEqual(mapped, {"pattern": pattern, "at": at})
                found = bytes.fromhex(pattern)
                self.assertEqual(_hits(data, found, [True] * len(found)), [offset - at])


class CapTests(unittest.TestCase):
    def test_per_file_and_overall_caps_are_said_when_they_drop_a_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp) / "game"
            game.mkdir()
            (game / "a.txt").write_bytes(b"ab " * 10)
            for name in ("b.txt", "c.txt", "d.txt"):
                (game / name).write_bytes(b"ab ab")
            r = hits(game, build("text", "ab"), per_file=3, total=1000)
            self.assertEqual(len([h for h in r["hits"] if h["file"] == "a.txt"]), 3)
            self.assertEqual(r["capped"], [{"file": "a.txt", "at": 9, "overall": False}])
            self.assertTrue(any("a.txt: hits capped at 3 per file" in w for w in r["warnings"]))
            r = hits(game, build("text", "ab"), per_file=2, total=6)
            self.assertEqual(r["hitCount"], 6)  # a.txt 2 (capped), b 2, c 2: d is not read
            self.assertEqual(r["capped"][-1], {"file": "d.txt", "at": 0, "overall": True})
            self.assertEqual(r["searched"], 4)
            r = hits(game, build("text", "ab"), per_file=2, total=5)
            self.assertEqual(r["capped"][-1]["file"], "c.txt")
            self.assertIn("1 file(s) after c.txt not searched (overall cap)", r["warnings"])
            exact = hits(game / "b.txt", build("text", "ab"), per_file=2)
            self.assertEqual((exact["hitCount"], exact["capped"]), (2, []))  # nothing dropped

    def test_unreadable_files_and_folders_are_named_and_cancel_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp) / "game"
            (game / "sub").mkdir(parents=True)
            for name in ("a.bin", "b.bin", "sub/c.bin"):
                (game / name).write_bytes(b"key")
            gone = lambda e: (game / "b.bin").unlink(missing_ok=True)  # noqa: E731
            report = search.search(game, build("text", "key"), sink=gone)
            self.assertEqual([u["file"] for u in report["unreadable"]], ["b.bin"])
            self.assertEqual((report["searched"], report["hitCount"]), (2, 2))
            self.assertTrue(any(w.startswith("Cannot read b.bin") for w in report["warnings"]))
            real_walk = os.walk

            def walk(top, onerror=None):
                onerror(PermissionError(13, "Access is denied", str(game / "sub")))
                yield from real_walk(top)

            with mock.patch.object(search.os, "walk", walk):
                report = search.search(game, build("text", "key"))
            self.assertEqual(report["unreadable"][0], {"file": "sub", "error": "Access is denied"})
            cancel = CancelToken()
            cancel.cancel()
            with self.assertRaises(ViwoError) as err:
                search.search(game, build("text", "key"), cancel=cancel)
            self.assertEqual(err.exception.code, "cancelled")
            with self.assertRaises(ViwoError) as err:
                search.search(game / "missing", build("text", "key"))
            self.assertEqual(err.exception.code, "not_found")


class WorkspaceTests(unittest.TestCase):
    def test_a_workspace_keeps_its_results_and_the_game_is_never_written(self) -> None:
        from viwo.core.workspace import claim

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, ws = root / "game", claim(root / "ws")
            game.mkdir()
            (game / "Data.bin").write_bytes(b"\x00GOLD\x00")
            (ws / "txt").mkdir()
            (ws / "txt" / "a.txt").write_text("100 GOLD", encoding="utf-8")
            (ws / ".trash").mkdir()
            (ws / ".trash" / "old.txt").write_text("GOLD", encoding="utf-8")
            before = tree_hashes(game)
            folder = search.results_folder(game, ws)
            report = search.search(game, build("text", "GOLD"), save_to=folder)
            self.assertEqual(tree_hashes(game), before)
            saved = Path(report["saved"])
            self.assertEqual(saved.parent, ws / ".search")
            self.assertEqual(json.loads(saved.read_text(encoding="utf-8"))["hitCount"], 1)
            mine = search.search(ws, build("text", "GOLD"), save_to=search.results_folder(ws, None))
            self.assertEqual(mine["kind"], "workspace")
            self.assertEqual(where(mine), [("txt/a.txt", 4, "utf-8")])  # dot folders left out
            self.assertEqual(search.results_folder(ws / "txt" / "a.txt", None), ws.resolve())
            self.assertIsNone(search.results_folder(game, None))
            for inside in (game / "out", root):  # in the game, or holding it
                with self.assertRaises(ViwoError) as err:
                    search.results_folder(game, inside)
                self.assertEqual(err.exception.code, "refused")
            (root / "mine").mkdir()
            (root / "mine" / "notes.txt").write_text("mine")
            with self.assertRaises(ViwoError):
                search.results_folder(game, root / "mine")  # someone else's files
            self.assertTrue(
                (search.results_folder(game, root / "new") / ".viwo-workspace").is_file()
            )


class SurfaceTests(unittest.TestCase):
    def test_cli_json_and_text_and_the_api_job(self) -> None:
        from viwo.api.handlers_jobs import KINDS
        from viwo.cli import main
        from viwo.core.jobs import JobRunner

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "game" / "Game.exe"
            exe.parent.mkdir()
            make_pe(exe)
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["--json", "--quiet", "search", str(exe.parent), "--bytes", "74 05",
                             "--workspace", str(root / "ws")])  # fmt: skip
            envelope = json.loads(out.getvalue())
            self.assertEqual((code, envelope["ok"]), (0, True))
            self.assertEqual(envelope["data"]["hits"][0]["section"], ".text")
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["--quiet", "static", "search", str(exe), "--number", "0x4F4E"])
            text = out.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Game.exe @ 0x24e [u16le] .text rva 0x104e va 0x14000104e", text)
            self.assertIn("1 hit(s) in 1 of 1 file(s) searched for number '0x4F4E'", text)
            self.assertEqual(main(["--quiet", "search", str(root / "nope"), "--text", "x"]), 1)

            class App:
                rt = runtime(root)
                workspace = root / "ws"
                jobs = JobRunner()

                def job(self, kind, run, where=None):
                    job = self.jobs.submit(kind, run, background=False, where=where)
                    return {**job.result, "jobId": job.job_id} if job.result else job.error

            app = App()
            body = {"target": str(exe), "kind": "text", "value": "pe", "ignoreCase": True}
            res = KINDS["search"](app, body)
            self.assertTrue(res["success"], res)
            self.assertEqual(res["hits"][0]["offset"], 0x40)
            self.assertTrue(Path(res["saved"]).is_file())
            app.workspace = exe.parent  # the game opened as the workspace: not saved, said
            res = KINDS["search"](app, body)
            self.assertNotIn("saved", res)
            self.assertIn("not saved", res["warnings"][0])
            bad = KINDS["search"](app, {**body, "maxHits": "lots"})
            self.assertEqual((bad["success"], bad["code"]), (False, "invalid_request"))
            bad = KINDS["search"](app, {**body, "target": str(root / "nope")})
            self.assertEqual((bad["success"], bad["code"]), (False, "not_found"))


if __name__ == "__main__":
    unittest.main()
