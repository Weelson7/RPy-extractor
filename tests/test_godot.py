"""L3: Godot plugin: PCK identification, carving, failover and keys (fake CLI tools)."""

from __future__ import annotations

import stat
import struct
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import runtime, tree_hashes
from viwo.contracts import CancelToken, ExtractionRequest, OnExisting
from viwo.core.pipeline.identify import carve, identify
from viwo.core.pipeline.probe import FolderProbe
from viwo.core.pipeline.runner import extract
from viwo.plugins.godot import NO_DATA, PCK_SLOT, GodotPlugin


def fake_pe(sections: tuple[str, ...]) -> bytes:
    """A minimal PE image: MZ stub, COFF header without optional header, named sections."""
    pe = 0x80
    head = bytearray(b"MZ" + b"\0" * (0x3C - 2)) + struct.pack("<I", pe)
    head += b"\0" * (pe - len(head))
    head += b"PE\0\0" + struct.pack("<HHIIIHH", 0x8664, len(sections), 0, 0, 0, 0, 0)
    for name in sections:
        head += name.encode().ljust(8, b"\0") + b"\0" * 32
    return bytes(head) + b"\0" * 512


FAKE_TOOL = """#!{python}
import sys
from pathlib import Path
args = sys.argv[1:]
opt = lambda name: next((a.split("=", 1)[1] for a in args if a.startswith(name + "=")), None)
pck = opt("--extract") or args[args.index("--pack") + 1]
out = opt("--output") or args[args.index("--output") + 1]
data = Path(pck).read_bytes()
if data[:4] != b"GDPC":
    sys.exit("not a pck")
if b"ENC" in data and opt("--key") != "ab" * 32:
    sys.exit("pck is encrypted")
if b"BROKEN" in data and "{name}" == "gdre":
    sys.exit("unsupported pck version")
target = Path(out) / "res" / "icon.png"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(b"PNG-" + data[-6:])
print("fake tool progress: 1 file written")
"""


def make_pck(marker: bytes = b"") -> bytes:
    return b"GDPC" + struct.pack("<IIII", 2, 4, 3, 0) + marker + b"payload"


def embed(exe: Path, pck: bytes) -> Path:
    exe.write_bytes(b"MZ" + b"\0" * 64 + pck + struct.pack("<Q", len(pck)) + b"GDPC")
    return exe


def fake_tools(folder: Path) -> str:
    """Python stand-ins for the CLI tools; a .cmd wrapper makes them runnable on Windows."""
    lines = []
    for name, dep in (("gdre", "gdre"), ("pcktool", "godotpcktool")):
        script = folder / f"fake_{name}.py"
        script.write_text(FAKE_TOOL.format(python=sys.executable, name=name))
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        tool = script
        if sys.platform == "win32":
            tool = folder / f"fake_{name}.cmd"
            tool.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
        lines.append(f"{dep} = {tool}")
    return "[plugins]\ngodot = on\n[tools]\n" + "\n".join(lines) + "\n"


class IdentifyTests(unittest.TestCase):
    def test_standalone_and_embedded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pck = make_pck()
            (root / "data.pck").write_bytes(pck)
            exe = embed(root / "Game.exe", pck)
            self.assertEqual(identify(root / "data.pck", [PCK_SLOT]).slot_id, "unarchive.pck")
            match = identify(exe, [PCK_SLOT])
            self.assertTrue(match.embedded)
            self.assertEqual(carve(match, root / "scratch").read_bytes(), pck)
            self.assertEqual(GodotPlugin().detect(FolderProbe(root)).confidence, 0.9)
            (root / "Game.exe").unlink()
            (root / "data.pck").unlink()
            (root / "project.godot").write_text("[application]")
            self.assertEqual(GodotPlugin().detect(FolderProbe(root)).confidence, 0.7)


class GodotPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.game = self.root / "game"
        self.game.mkdir()
        self.rt = runtime(self.root, fake_tools(self.root))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_it(self, **kw):
        request = ExtractionRequest(str(self.game), str(self.root / "ws"), **kw)
        self.events = []
        return extract(self.rt, request, "j", self.events.append, CancelToken())

    def test_embedded_and_failover(self) -> None:
        embed(self.game / "Game.exe", make_pck())
        (self.game / "extra.pck").write_bytes(make_pck(b"BROKEN"))
        result = self.run_it()
        self.assertTrue(any("fake tool progress" in e.message for e in self.events))
        self.assertEqual(result.runs[0].plugin_id, "godot")
        self.assertEqual(dict(result.by_backend), {"gdre-tools": 1, "godotpcktool": 1})
        self.assertIn("png/icon.png", tree_hashes(self.root / "ws", skip_reserved=True))

    def test_godot_executable_without_data_is_named(self) -> None:
        """A bare export template (PE "pck" section, nothing embedded, no .pck beside it) is a
        Godot game with its data missing, not a generic folder."""
        (self.game / "Game.exe").write_bytes(fake_pe(("text", "pck", "rsrc")))
        det = GodotPlugin().detect(FolderProbe(self.game))
        self.assertEqual((det.confidence, det.evidence), (0.6, (NO_DATA,)))
        result = self.run_it()
        self.assertEqual(result.runs[0].plugin_id, "godot")
        self.assertTrue(any("no PCK data" in w for w in result.runs[0].warnings), result.runs)
        self.assertFalse(result.runs[0].verify_passed)

    def test_encrypted_needs_key_and_spare_is_not_tried(self) -> None:
        (self.game / "data.pck").write_bytes(make_pck(b"ENC"))
        result = self.run_it()
        self.assertEqual(result.archives_extracted, 0)
        self.assertTrue(any("needs_key" in w for w in result.warnings))
        keyed = self.run_it(
            plugin_options={"godot": {"encryption_key": "ab" * 32}}, on_existing=OnExisting.REPLACE
        )
        self.assertEqual(dict(keyed.by_backend), {"gdre-tools": 1})


def _ctx(root: Path, run, located=True):
    from types import SimpleNamespace

    tool = SimpleNamespace(argv_prefix=("tool",), path="tool")
    host = SimpleNamespace(
        tools=SimpleNamespace(locate=lambda spec: tool if located else None),
        process=SimpleNamespace(run=run),
    )
    return SimpleNamespace(
        os=host,
        cancel=None,
        game_root=root / "game",
        staging=root / "staging",
        scratch=root / "scratch",
        options={},
        tool_output=lambda *a, **k: None,
    )


def _result(ok: bool, text: str = ""):
    from types import SimpleNamespace

    return SimpleNamespace(ok=ok, stderr=text, stdout="", returncode=0 if ok else 1)


LISTING = (
    "4.3.0-stable (77dcf97 / 2024-08-14 / Bytecode version: 100)\n"
    "3.5.0-stable (991bb6a / 2022-08-05 / Bytecode version: 13)\n"
)


def _gdre(staging: Path, options: dict, writes: bool, located: bool = True):
    """A fake GDRE (lists its bytecode revisions, writes one .gd per --decompile when `writes`)
    and the analysis context around it; returns (ctx, the argv of every run)."""
    from types import SimpleNamespace

    runs = []

    def run(argv, timeout=None, cancel=None):
        runs.append(argv)
        if "--list-bytecode-versions" in argv:
            return SimpleNamespace(stdout=LISTING, stderr="", ok=True)
        for a in argv if writes else ():
            if a.startswith("--decompile="):
                (staging / (Path(a[12:]).stem + ".gd")).write_text("x")
        return SimpleNamespace(stdout="", stderr="gdre: bad bytecode", ok=writes)

    tool = SimpleNamespace(argv_prefix=("gdre",))
    host = SimpleNamespace(
        tools=SimpleNamespace(locate=lambda spec: tool if located else None),
        process=SimpleNamespace(run=run),
    )
    ctx = SimpleNamespace(
        os=host, options=options, staging=staging, cancel=None, log=lambda *a, **k: None
    )
    return ctx, runs


def _scripts(root: Path, n: int, magic: bytes, number: int) -> tuple:
    files = []
    for i in range(n):
        f = root / f"s{i}.gdc"
        f.write_bytes(magic + struct.pack("<I", number) + b"code")
        files.append(f)
    return tuple(files)


class GdscriptTests(unittest.TestCase):
    """analysis.gdscript: the bytecode option wins, then the engine version hint, then GDRE's own
    listing for the header number; files go in batches; every failure is named."""

    def test_bytecode_choice_batches_and_failures(self) -> None:
        import random

        from viwo.contracts.analysis import AnalysisTarget
        from viwo.contracts.types import OutcomeKind
        from viwo.plugins.godot.gdscript import BATCH, GdreDecompile

        rng = random.Random(5)
        for case in range(14):
            with tempfile.TemporaryDirectory() as tmp:
                root, n = Path(tmp), rng.randint(1, 250)
                magic, number = rng.choice([b"GDSC", b"GDSC", b"JUNK"]), rng.choice([100, 13, 7])
                option, hint = rng.choice(["", "4.2.0"]), rng.choice(["", "3.6.1"])
                writes = rng.random() < 0.8
                (root / "out").mkdir()
                ctx, runs = _gdre(root / "out", {"bytecode": option} if option else {}, writes)
                hints = {"engine_version": hint} if hint else {}
                files = _scripts(root, n, magic, number)
                target = AnalysisTarget("s", "gdscript_bytecode", files, "godot", hints=hints)
                out = GdreDecompile().analyze(target, ctx)
                listed = {100: "4.3.0", 13: "3.5.0"}.get(number, "") if magic == b"GDSC" else ""
                chosen = option or hint or listed
                if not chosen:
                    self.assertIn("bytecode option", out.error)
                    continue
                work = [a for a in runs if "--list-bytecode-versions" not in a]
                self.assertEqual(len(work), -(-n // BATCH))  # ceil: no run over the batch size
                self.assertTrue(all(f"--bytecode={chosen}" in a for a in work))
                per_run = [sum(x.startswith("--decompile=") for x in a) for a in work]
                self.assertEqual((sum(per_run), max(per_run) <= BATCH), (n, True))
                if writes:
                    self.assertEqual((out.kind, out.files), (OutcomeKind.OK, n))
                else:
                    self.assertIn("bad bytecode", out.error)

    def test_engine_version_and_a_missing_tool(self) -> None:
        from viwo.contracts.analysis import AnalysisTarget
        from viwo.contracts.types import OutcomeKind
        from viwo.plugins.godot.gdscript import GdreDecompile, engine_version

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "game.exe"
            exe.write_bytes(b"MZ ... 3.3.2.stable.official ...")
            self.assertEqual(engine_version(exe), "3.3.2")
            self.assertEqual(engine_version(root / "gone.exe"), "")
            from viwo.plugins.godot.gdscript import _from_header

            junk = _scripts(root, 1, b"JUNK", 100)[0]
            self.assertEqual(_from_header(None, junk, None), "")  # no header: GDRE never asked
            ctx, _ = _gdre(root, {}, True, located=False)
            target = AnalysisTarget("s", "gdscript_bytecode", (), "godot")
            self.assertEqual(GdreDecompile().analyze(target, ctx).kind, OutcomeKind.UNAVAILABLE)


class ParserPropertyTests(unittest.TestCase):
    def test_trailers_and_pe_headers_never_lie_or_raise(self) -> None:
        import random

        from viwo.plugins.godot.pck import embedded_chunk, pe_sections

        rng = random.Random(1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Game.exe"
            for _ in range(300):
                body = bytearray(rng.randbytes(rng.randint(0, 200)))
                if rng.random() < 0.5:  # a trailer, honest or not
                    claimed = rng.choice([len(body), 0, len(body) + 50, rng.randrange(300)])
                    body += struct.pack("<Q", claimed) + b"GDPC"
                if rng.random() < 0.3 and len(body) > 16:
                    body[:4] = b"GDPC"
                path.write_bytes(bytes(body))
                chunk = embedded_chunk(path, bytes(body[-64:]))
                if chunk:
                    offset, size = chunk
                    self.assertEqual(offset + size + 12, len(body))
                    self.assertEqual(bytes(body[offset : offset + 4]), b"GDPC")
            names = tuple(rng.choice(["text", "pck", "data", "rsrc"]) for _ in range(5))
            head = fake_pe(names)
            self.assertEqual(tuple(pe_sections(head)), names)
            for cut in range(0, len(head), 7):  # a truncated header gives a prefix, never junk
                got = tuple(pe_sections(head[:cut]))
                self.assertEqual(got, names[: len(got)])
            for _ in range(200):
                noise = bytearray(head)
                for _ in range(rng.randint(1, 6)):
                    noise[rng.randrange(len(noise))] = rng.randrange(256)
                pe_sections(bytes(noise))  # never raises

    def test_cli_unpackers_name_a_missing_tool_and_an_empty_result(self) -> None:
        from viwo.contracts.types import OutcomeKind
        from viwo.plugins.godot.pck import GodotPckTool

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = GodotPckTool().extract(root / "a.pck", root / "d", _ctx(root, None, False))
            self.assertEqual(out.kind, OutcomeKind.UNAVAILABLE)
            (root / "d").mkdir()
            out = GodotPckTool().extract(
                root / "a.pck", root / "d", _ctx(root, lambda a, **k: _result(True))
            )
            self.assertEqual(out.kind, OutcomeKind.FAILED)
            self.assertIn("wrote no file", out.error)


class RecoverAndPackTests(unittest.TestCase):
    """export.godot and pack.pck over random game folders and edit sets (fake process layer)."""

    def test_recover_finds_the_first_pck_and_says_a_partial_run(self) -> None:
        import random

        from viwo.contracts.types import OutcomeKind
        from viwo.plugins.godot.pck import GdreRecover

        rng = random.Random(4)
        for i in range(12):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                game = root / "game"
                (game / "sub").mkdir(parents=True)
                (game / "readme.txt").write_text("x")
                layout = rng.choice(["none", "pck", "embedded", "both"])
                if layout in ("pck", "both"):
                    (game / "sub" / "data.pck").write_bytes(make_pck())
                if layout in ("embedded", "both"):
                    embed(game / "Game.exe", make_pck())
                wrote, ok = rng.randint(0, 3), rng.random() < 0.6
                seen = []

                def run(argv, wrote=wrote, ok=ok, **kw):
                    seen.append(argv)
                    for n in range(wrote):
                        (root / "staging" / f"res/f{n}.tres").parent.mkdir(
                            parents=True, exist_ok=True
                        )
                        (root / "staging" / f"res/f{n}.tres").write_text("t")
                    (root / "staging").mkdir(exist_ok=True)
                    (root / "staging" / "gdre_export.log").write_text("tool noise")
                    return _result(ok, "gdre: broken resource")

                out = GdreRecover().export(_ctx(root, run))
                if layout == "none":
                    self.assertEqual(
                        (out.kind, out.notes), (OutcomeKind.OK, ("no PCK to recover",))
                    )
                    self.assertEqual(seen, [])
                    continue
                first = "Game.exe" if layout == "embedded" else "data.pck"
                if layout == "both":  # sorted walk: Game.exe sorts before sub/
                    first = "Game.exe"
                self.assertTrue(seen[0][2].endswith(first), seen[0])
                if not ok and not wrote:
                    self.assertEqual(out.kind, OutcomeKind.FAILED)
                    self.assertIn("broken resource", out.error)
                    continue
                self.assertEqual((out.kind, out.files), (OutcomeKind.OK, wrote))  # logs not counted
                self.assertEqual(bool(out.notes), not ok)  # a partial recovery is said
        out = GdreRecover().export(_ctx(Path(tmp), None, located=False))
        self.assertEqual(out.kind, OutcomeKind.UNAVAILABLE)

    def test_pack_hands_the_tool_exactly_the_safe_members(self) -> None:
        import random

        from viwo.contracts.types import OutcomeKind
        from viwo.plugins.godot.pck import GodotPckPacker

        rng = random.Random(9)
        for _ in range(8):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                src = root / "src.bin"
                src.write_bytes(b"edited")
                names = [f"res/{rng.choice(['a', 'b'])}/f{i}.png" for i in range(rng.randint(1, 5))]
                names += rng.sample(["../evil.png", "/abs.png", "C:/x.png"], rng.randint(0, 2))
                members = {n: src for n in names}
                seen, ok = [], rng.random() < 0.7
                out = GodotPckPacker().pack(
                    root / "game.pck",
                    members,
                    _ctx(root, lambda argv, **kw: seen.append(argv) or _result(ok, "pck locked")),
                )
                argv = seen[0]
                prefix = Path(argv[argv.index("--remove-prefix") + 1])
                staged = [
                    Path(a).relative_to(prefix).as_posix()
                    for a in argv[argv.index("--remove-prefix") + 2 :]
                ]
                safe = sorted({n for n in names if n.startswith("res/")})
                self.assertEqual(sorted(staged), safe)  # unsafe names never reach the tool
                if ok:
                    self.assertEqual((out.kind, out.files), (OutcomeKind.OK, len(safe)))
                else:
                    self.assertEqual((out.kind, out.error), (OutcomeKind.FAILED, "pck locked"))
            out = GodotPckPacker().pack(root / "g.pck", {}, _ctx(root, None, located=False))
            self.assertEqual(out.kind, OutcomeKind.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
