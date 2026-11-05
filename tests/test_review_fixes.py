"""L3: the backend review's fixes (1.15.6). A preview from another machine needs the token's
cookie; attended capture (0 seconds) stays attended; a key cut across the output limit is
still masked; a QuickBMS script never takes a format a reader claims; a cancelled run never
starts the spare; repack and mod packing refuse the game folder before writing anything there;
GDRE recovers the main pack with the key; a handoff never edits the user's own tool install;
the job table holds under concurrent submits."""

from __future__ import annotations

import os
import random
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.helpers import runtime, tree_hashes
from viwo.contracts import ViwoError
from viwo.contracts.plugin import masked
from viwo.contracts.slots import Match, SlotDefinition
from viwo.contracts.types import CancelToken, Outcome, OutcomeKind


class PreviewCookieTests(unittest.TestCase):
    def test_a_lan_peer_needs_the_cookie_this_machine_does_not(self) -> None:
        from viwo.api import server

        mine = f"{server.COOKIE}_8081"  # the port in the name: another server's is not ours
        for peer, cookie, want in (
            ("127.0.0.1", "", True),
            ("192.168.1.9", "", False),
            ("192.168.1.9", f"{mine}=PREV", True),
            ("192.168.1.9", f"{mine}=nope", False),
            ("192.168.1.9", f"{mine}=T0KEN", False),  # the API token is never a preview cookie
            ("192.168.1.9", f"{server.COOKIE}_9999=PREV", False),
            ("192.168.1.9", "other=1; " + f"{mine}=PREV", True),
            ("192.168.1.9", f'{mine}="\\351"', False),  # non-ASCII: refused, never a traceback
            ("192.168.1.9", "\x00;;=", False),
        ):
            fake = SimpleNamespace(token="T0KEN", preview="PREV", client_address=(peer, 1))
            fake.headers, fake.server = (
                {"Cookie": cookie},
                SimpleNamespace(server_address=("h", 8081)),
            )
            fake._cookie_name = lambda fake=fake: server.Handler._cookie_name(fake)
            self.assertEqual(server.Handler._cookie_ok(fake), want, (peer, cookie))
        from viwo.api.peers import same

        self.assertFalse(same("\xe9", "T0KEN"))  # a non-ASCII header or key
        self.assertEqual(server.byte_range("bytes=" + "9" * 5000 + "-", 10), None)  # no crash


class MaskTests(unittest.TestCase):
    def test_a_key_anywhere_in_a_long_line_never_shows(self) -> None:
        rng = random.Random(6)
        for _ in range(200):
            key = rng.randbytes(32).hex()
            line = "x" * rng.randint(0, 220) + rng.choice([key, key.upper()]) + "y" * 30
            said = []
            ctx = SimpleNamespace(log=lambda m, *a: said.append(m))
            from viwo.contracts.plugin import ExtractionContext

            relay = ExtractionContext.tool_output(ctx, "unpack", every=0, mask=key)
            relay(line)
            for prefix in (key[:12], key.upper()[:12]):
                self.assertNotIn(prefix, said[0])
            self.assertLessEqual(len(said[0]), 200)
        self.assertEqual(masked("a KEY b key", "key"), "a <secret> b <secret>")


class CaptureAfterTests(unittest.TestCase):
    def test_zero_means_attended_and_nothing_means_the_default(self) -> None:
        from viwo.api import handlers_capture
        from viwo.core.capture.policy import DEFAULT_AUTO

        seen = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "g").mkdir()
            (root / "g" / "Game.exe").write_bytes(b"MZ")
            app = SimpleNamespace(workspace=root / "ws", rt=None)
            (root / "ws").mkdir()
            (root / "ws" / "x").write_text("x")
            app.locked_job = lambda *a, **k: {}
            with mock.patch.object(handlers_capture, "CaptureRequest", lambda *a: seen.append(a)):
                for raw, want in ((0, 0.0), ("0", 0.0), (None, DEFAULT_AUTO), (12, 12.0)):
                    body = {"gamePath": str(root / "g"), "exePath": str(root / "g" / "Game.exe")}
                    handlers_capture.run_capture(app, {**body, "captureAfter": raw})
                    self.assertEqual(seen[-1][4], want, raw)


class IdentifyOrderTests(unittest.TestCase):
    def test_a_fallback_identifier_never_takes_a_claimed_format(self) -> None:
        bms = SlotDefinition(
            "unarchive.bms", "unarchive", "quickbms", "q",
            identify=lambda p, h, t: Match("unarchive.bms", p), fallback=True,
        )  # fmt: skip
        pak = SlotDefinition("unarchive.upak", "unarchive", "unreal", "r", suffixes=(".pak",))
        wad = SlotDefinition("unarchive.wad", "unarchive", "doom", "w", magic=(b"PWAD",))
        from viwo.core.pipeline.identify import identify

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, head, want in (
                ("a.pak", b"xx", "unarchive.upak"),
                ("b.bin", b"PWAD....", "unarchive.wad"),
                ("c.dat", b"????", "unarchive.bms"),
            ):
                (root / name).write_bytes(head + bytes(40))
                self.assertEqual(identify(root / name, [bms, pak, wad]).slot_id, want, name)


class CancelTests(unittest.TestCase):
    def test_a_cancelled_run_never_starts_the_spare(self) -> None:
        from viwo.core.pipeline.failover import run_with_failover

        binding = SimpleNamespace(bound=True, main="m", spare="s", reasons=())
        calls = []

        def call(backend):
            calls.append(backend)
            token.cancel()
            return Outcome(OutcomeKind.FAILED, error="killed")

        token = CancelToken()
        out, used = run_with_failover(binding, {"m": "m", "s": "s"}, call, cancel=token)
        self.assertEqual((calls, used, out.fallback), (["m"], "m", ""))
        token = CancelToken()
        calls.clear()

        def fails(backend):
            calls.append(backend)
            return Outcome(OutcomeKind.FAILED, error="bad")

        run_with_failover(binding, {"m": "m", "s": "s"}, fails, cancel=token)
        self.assertEqual(calls, ["m", "s"])  # not cancelled: the spare still runs


class GameFolderGuardTests(unittest.TestCase):
    def test_repack_and_a_mod_never_write_into_the_game(self) -> None:
        from viwo.core import mods, roundtrip

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game"
            game.mkdir()
            (game / "data.bin").write_bytes(b"d")
            before = tree_hashes(game)
            item = [roundtrip.PlanItem("data.bin", "pack.zip", {"a": game / "data.bin"})]
            with (
                mock.patch.object(roundtrip, "source_game", return_value=game),
                mock.patch.object(roundtrip, "edit_set", return_value=([], [])),
                mock.patch.object(roundtrip, "plan", return_value=(item, [])),
            ):
                for target in (game, game / "sub"):
                    with self.assertRaises(ViwoError) as err:
                        roundtrip.repack(runtime(root), root / "ws", target)
                    self.assertEqual(err.exception.code, "refused")
            copy = root / "copy"
            (copy / roundtrip.MARKER).mkdir(parents=True)
            with self.assertRaises(ViwoError) as err:
                mods.pack(game, copy, game / "mod.zip")
            self.assertEqual(err.exception.code, "refused")
            self.assertEqual(tree_hashes(game), before)  # not even a lock file


class GodotRecoverTests(unittest.TestCase):
    def test_the_main_pack_beside_the_executable_is_recovered_with_the_key(self) -> None:
        from viwo.plugins.godot import pck

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("addons/a.pck", "dlc.pck", "Game.exe", "Game.pck"):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_bytes(b"GDPC" + bytes(64))
            self.assertEqual(pck._recover_target(root), root / "Game.pck")
            (root / "Game.pck").unlink()
            self.assertEqual(pck._recover_target(root), root / "addons" / "a.pck")
            seen = []
            tool = SimpleNamespace(argv_prefix=("gdre",))
            ctx = SimpleNamespace(
                os=SimpleNamespace(
                    tools=SimpleNamespace(locate=lambda s: tool),
                    process=SimpleNamespace(
                        run=lambda argv, **k: (
                            seen.append(argv),
                            SimpleNamespace(ok=False, stderr="bad key ABCD1234", stdout=""),
                        )[1]
                    ),
                ),
                game_root=root, staging=root / "st", cancel=None,
                options={"encryption_key": "ABCD1234"},
                tool_output=lambda stage, mask="": None,
            )  # fmt: skip
            out = pck.GdreRecover().export(ctx)
            self.assertIn("--key=ABCD1234", seen[0])
            self.assertNotIn("ABCD1234", out.error)


class HandoffTests(unittest.TestCase):
    def test_only_vivos_own_copy_is_pre_answered(self) -> None:
        from viwo.core.capture import handoffs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "game.exe"
            exe.write_bytes(b"MZ" + bytes(0x40) + b"PE\0\0\x64\x86")
            target = SimpleNamespace(paths=(exe,))
            for place, edits in (("third_party/x64dbg/release/x64", True), ("mine/x64", False)):
                debugger = root / place / "x64dbg.exe"
                debugger.parent.mkdir(parents=True)
                debugger.write_bytes(b"MZ")
                tool = SimpleNamespace(path=str(debugger))
                logs = []
                ctx = SimpleNamespace(
                    os=SimpleNamespace(tools=SimpleNamespace(locate=lambda s: tool)),
                    log=lambda *a, **k: logs.append(a),
                    options={},
                )
                with mock.patch.object(handoffs, "_bits", return_value=64):
                    handoffs.X64dbgGui().prepare(target, ctx)
                self.assertEqual(debugger.with_suffix(".ini").exists(), edits, place)
                self.assertEqual(bool(logs), not edits)  # said when left alone


class ExtensionFilterTests(unittest.TestCase):
    def test_decodable_sources_pass_then_only_chosen_types_stay_and_the_rest_is_said(self) -> None:
        from collections import Counter

        from viwo.core.pipeline import filters

        rng = random.Random(9)
        with tempfile.TemporaryDirectory() as tmp:
            ws_root = Path(tmp)
            run = SimpleNamespace(ctx=lambda owner: SimpleNamespace(options={}), log=lambda *a: 0)
            with mock.patch("viwo.core.decode._wanted", return_value={".dds": "decode.image"}):
                self.assertEqual(
                    filters.widened(run, frozenset({".png"})), frozenset({".png", ".dds"})
                )
            self.assertIsNone(filters.widened(run, None))
            for case in range(10):
                rows, by_ext = [], Counter()
                for i in range(rng.randint(1, 12)):
                    group = rng.choice(["png", "dds", "wav"])
                    path = ws_root / str(case) / group / f"f{i}.{group}"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"x")
                    rows.append({"path": f"{group}/f{i}.{group}"})
                    by_ext[group] += 1
                collected = SimpleNamespace(
                    provenance=rows, by_ext=by_ext, skipped_by_ext=Counter({"txt": 2})
                )
                gone = sum(1 for r in rows if not r["path"].startswith("png"))
                lines = filters.prune(run, ws_root / str(case), collected, frozenset({".png"}))
                kept = {r["path"].split("/")[0] for r in collected.provenance}
                self.assertLessEqual(kept, {"png"})
                self.assertEqual(set(collected.by_ext), kept)
                on_disk = {p.parent.name for p in (ws_root / str(case)).rglob("*.*")}
                self.assertEqual(on_disk, kept)
                self.assertIn(f"{gone + 2} file(s) of other types left out", lines[0])


class GhidraHeapTests(unittest.TestCase):
    def test_the_heap_follows_the_machine_and_the_users_setting_wins(self) -> None:
        from viwo.core.analysis import ghidra

        sizes = [ghidra.heap(gb << 30) for gb in range(0, 129, 4)]
        values = [int(s[:-1]) for s in sizes]
        self.assertEqual(values, sorted(values))  # more memory never means a smaller heap
        self.assertTrue(all(2 <= v <= 16 for v in values))
        self.assertEqual((ghidra.heap(0), ghidra.heap(32 << 30)), ("2G", "16G"))
        java = SimpleNamespace(path="C:/jdk/bin/java.exe")
        ctx = SimpleNamespace(
            os=SimpleNamespace(tools=SimpleNamespace(locate=lambda s: java),
                               memory_bytes=lambda: 24 << 30)
        )  # fmt: skip
        with mock.patch.dict("os.environ", {}, clear=False):
            for name in ("GHIDRA_MAXMEM", "GHIDRA_HEADLESS_MAXMEM"):
                os.environ.pop(name, None)
            self.assertEqual(ghidra.java_env(ctx)["GHIDRA_HEADLESS_MAXMEM"], "12G")
            os.environ["GHIDRA_MAXMEM"] = "4G"
            self.assertNotIn("GHIDRA_HEADLESS_MAXMEM", ghidra.java_env(ctx))
        from viwo.os import select_os

        self.assertGreater(select_os().memory_bytes(), 1 << 30)  # this machine says its memory


class AgentChoiceTests(unittest.TestCase):
    def test_an_engine_that_did_not_detect_the_game_never_lends_its_agent(self) -> None:
        from tests.test_doom import make_wad
        from viwo.core.capture.agents import agent_for

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "doomish"
            game.mkdir()
            make_wad(game / "doom.wad", [("X", b"x")], b"IWAD")  # Doom: no runtime agent
            with self.assertRaises(ViwoError) as err:
                agent_for(runtime(root), game)
            self.assertIn("doom", err.exception.message)  # the engine it found, named


class JobTableTests(unittest.TestCase):
    def test_submits_and_lists_from_many_threads_hold(self) -> None:
        from viwo.core.jobs import JobRunner

        runner, errors = JobRunner(), []

        def work():
            try:
                for _ in range(60):
                    runner.submit("t", lambda *a: None, background=False)
                    runner.list()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=work) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
