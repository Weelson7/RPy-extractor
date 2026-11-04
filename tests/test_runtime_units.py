"""L3: the small runtime pieces, as properties: the loopback recorder writes exactly the clipped
samples it heard (channels, frame count, honest peak) and says when soundcard is missing; a
worker pin installs into a fresh folder and swaps in whole, or leaves the old one untouched;
the BepInEx agent only takes IL2CPP builds, never reuses a finished log and collects what it
wrote; `python -m viwo` is the CLI; the system routes answer or name why not."""

from __future__ import annotations

import random
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.helpers import runtime
from viwo.contracts import ViwoError
from viwo.core import workers
from viwo.core.capture import audio


class Frames:
    """The few numpy operations record() uses, over rows of float samples."""

    def __init__(self, rows):
        self.rows = [tuple(r) for r in rows]
        self.ndim = 2
        self.shape = (len(self.rows), len(self.rows[0]) if self.rows else 0)
        self.size = self.shape[0] * self.shape[1]

    def __mul__(self, k):
        return Frames([[v * k for v in r] for r in self.rows])

    def astype(self, kind):
        return Frames([[int(v) for v in r] for r in self.rows])

    def tobytes(self):
        return b"".join(struct.pack("<h", v) for r in self.rows for v in r)

    def max(self):
        return max(v for r in self.rows for v in r)


fake_numpy = SimpleNamespace(
    clip=lambda f, lo, hi: Frames([[min(hi, max(lo, v)) for v in r] for r in f.rows]),
    abs=lambda f: Frames([[abs(v) for v in r] for r in f.rows]),
)


class RecorderTests(unittest.TestCase):
    def test_the_wav_holds_exactly_what_was_heard(self) -> None:
        rng = random.Random(6)
        with tempfile.TemporaryDirectory() as tmp:
            rt = runtime(Path(tmp), "[startup]\nfeatures = extraction, capture\n")
            for _ in range(6):
                channels, count = rng.choice([1, 2]), rng.randint(1, 200)
                rows = [[rng.uniform(-1.5, 1.5) for _ in range(channels)] for _ in range(count)]
                heard = Frames(rows)
                speaker = SimpleNamespace(name="Speakers (Realtek)")
                loop = SimpleNamespace(record=lambda samplerate, numframes: heard)
                card = SimpleNamespace(
                    default_speaker=lambda: speaker,
                    get_microphone=lambda id, include_loopback: loop,
                )
                with mock.patch.dict(sys.modules, {"numpy": fake_numpy, "soundcard": card}):
                    done = audio.record(rt, Path(tmp) / "ws", 0.5)
                with wave.open(done["wav"]) as fh:
                    self.assertEqual((fh.getnchannels(), fh.getnframes()), (channels, count))
                    raw = fh.readframes(count)
                got = struct.unpack(f"<{count * channels}h", raw)
                want = [int(min(1, max(-1, v)) * 32767) for r in rows for v in r]
                self.assertEqual(list(got), want)  # clipped, never wrapped around
                self.assertAlmostEqual(done["peak"], max(abs(v) for r in rows for v in r), 3)
                self.assertEqual(done["device"], "Speakers (Realtek)")
            with mock.patch.dict(sys.modules, {"soundcard": None}):
                with self.assertRaises(ViwoError) as err:
                    audio.record(rt, Path(tmp) / "ws", 0.5)
            self.assertEqual(err.exception.code, "unavailable")


class WorkerInstallTests(unittest.TestCase):
    def test_a_pin_swaps_in_whole_or_not_at_all(self) -> None:
        dep = next(iter(workers.entries()))
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            lib = workers.folder(home, dep)
            lib.mkdir(parents=True)
            (lib / "old.py").write_text("old")
            (lib / workers.MARK).write_text("old-pin")

            def pip(dep_id, target, runner):
                if runner == "fail":
                    (target / "half.py").parent.mkdir(parents=True, exist_ok=True)
                    (target / "half.py").write_text("half")
                    raise ViwoError("failed", "pip broke")
                target.mkdir(parents=True, exist_ok=True)
                (target / "new.py").write_text("new")

            with mock.patch("viwo.core.thirdparty.pip_install", pip):
                with self.assertRaises(ViwoError):
                    workers.install(dep, home, "fail")
                self.assertEqual({p.name for p in lib.iterdir()}, {"old.py", workers.MARK})
                self.assertFalse(lib.with_name(f".{dep}-new").exists())  # nothing half kept
                workers.install(dep, home, "ok")
            self.assertEqual({p.name for p in lib.iterdir()}, {"new.py", workers.MARK})
            self.assertEqual((lib / workers.MARK).read_text(), workers.entries()[dep]["pin"])
            self.assertIsNotNone(workers.argv(dep, home))  # the pin now runs


class BepInExTests(unittest.TestCase):
    def test_only_il2cpp_a_fresh_log_and_what_it_wrote(self) -> None:
        from viwo.plugins.unity.agent import READY, BepInExAgent

        agent = BepInExAgent()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bepinex"
            (source / "BepInEx" / "core").mkdir(parents=True)
            (source / "winhttp.dll").write_bytes(b"MZ")
            copy = root / "copy"
            copy.mkdir()
            exe = copy / "Game.exe"
            exe.write_bytes(b"MZ")
            self.assertIn("Mono", agent.accepts(copy, exe))
            (copy / "GameAssembly.dll").write_bytes(b"MZ")
            self.assertEqual(agent.accepts(copy, exe), "")
            log = copy / "BepInEx" / "LogOutput.log"
            log.parent.mkdir(parents=True)
            log.write_text(READY)  # a reused copy: the last run's log
            ctx = SimpleNamespace(
                os=SimpleNamespace(
                    tools=SimpleNamespace(
                        locate=lambda s: SimpleNamespace(path=str(source / "winhttp.dll"))
                    )
                )
            )
            args = agent.install(copy, exe, ctx)
            self.assertIn("-screen-fullscreen", args)
            self.assertFalse(agent.finished(copy, exe))  # the old log never counts
            cfg = copy / "BepInEx" / "config" / "BepInEx.cfg"
            self.assertIn("Enabled = false", cfg.read_text())  # no console window
            cfg.write_text("[Logging.Console]\nEnabled = true\n")  # the user's own choice
            agent.install(copy, exe, ctx)
            self.assertIn("true", cfg.read_text())  # kept
            self.assertEqual(agent.outputs(copy, exe), [])
            (copy / "BepInEx" / "interop").mkdir()
            (copy / "BepInEx" / "interop" / "Assembly-CSharp.dll").write_bytes(b"MZ")
            log.write_text("... " + READY)
            self.assertTrue(agent.finished(copy, exe))
            self.assertEqual(
                [p.name for p in agent.outputs(copy, exe)], ["Assembly-CSharp.dll", "LogOutput.log"]
            )


class EntryAndSystemTests(unittest.TestCase):
    def test_python_dash_m_viwo_is_the_cli(self) -> None:
        done = subprocess.run(
            [sys.executable, "-m", "viwo", "--help"], capture_output=True, text=True, timeout=120
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("viwo", done.stdout.lower())

    def test_system_routes_answer_or_name_why_not(self) -> None:
        from viwo.api.app import App
        from viwo.api.handlers import GET, POST

        with tempfile.TemporaryDirectory() as tmp:
            app = App(runtime(Path(tmp)))
            app.set_workspace(Path(tmp) / "ws")
            with mock.patch("viwo.core.diag.check_updates", return_value={"latest": "v9"}):
                self.assertEqual(GET["/api/updates"](app, {})["latest"], "v9")
            out = Path(tmp) / "diag.zip"
            done = POST["/api/diag"](app, {"out": str(out)})
            self.assertTrue(done["success"] and out.is_file())
            with mock.patch("viwo.core.diag.bundle", side_effect=OSError("disk full")):
                self.assertEqual(POST["/api/diag"](app, {})["error"], "disk full")
            self.assertEqual(POST["/api/diag"](app, {"out": "diag.zip"})["code"], "invalid_request")
            with mock.patch(
                "viwo.api.handlers_system.update_indexes", return_value={"tag": "v1.0.0"}
            ):
                self.assertEqual(POST["/api/indexes/update"](app, {})["tag"], "v1.0.0")


class DynamicRunTests(unittest.TestCase):
    """trace, dump, profile and agent waits over a faked OS layer: what ran follows the request,
    and every way it ends is named."""

    def rt(self, root: Path):
        return runtime(root, "[startup]\nfeatures = extraction, capture\n")

    def test_trace_runs_every_function_and_counts_the_log(self) -> None:
        from viwo.core.capture.runtime import RuntimeRequest, trace

        rng = random.Random(3)
        with tempfile.TemporaryDirectory() as tmp:
            rt = self.rt(Path(tmp))
            for _ in range(5):
                funcs = tuple(
                    rng.sample(["CreateFileW", "ReadFile", "send", "Nt*"], rng.randint(1, 4))
                )
                lines = rng.randint(0, 20)
                seen = []

                def run(argv, cwd=None, timeout=None, cancel=None, env=None, lines=lines):
                    seen.append((argv, env))
                    Path(argv[argv.index("-o") + 1]).write_text("event\n" * lines)
                    return SimpleNamespace(ok=True, stderr="", stdout="")

                with mock.patch.object(rt.os.process, "run", run):
                    done = trace(rt, RuntimeRequest(Path(tmp) / "ws", pid=42, functions=funcs))
                argv, env = seen[0]
                self.assertEqual(
                    [argv[i + 1] for i, a in enumerate(argv) if a == "-i"], list(funcs)
                )
                self.assertIn("third_party", env["PYTHONPATH"])  # Frida from the pinned folder
                self.assertEqual((done["pid"], done["events"]), (42, lines))
            folders = sorted((Path(tmp) / "ws" / ".runtime" / "trace").iterdir())
            self.assertEqual(len(folders), 5)  # one fresh folder per run, even within a second
            quiet = SimpleNamespace(ok=False, stderr="frida: unable to attach", stdout="")
            with mock.patch.object(rt.os.process, "run", return_value=quiet):
                with self.assertRaises(ViwoError) as err:
                    trace(rt, RuntimeRequest(Path(tmp) / "ws", pid=42))
            self.assertIn("unable to attach", err.exception.hint)

    def test_dump_and_profile_name_why_they_could_not(self) -> None:
        from viwo.core.capture.profile import exports, profile
        from viwo.core.capture.runtime import RuntimeRequest, dump, resolve_pid

        with tempfile.TemporaryDirectory() as tmp:
            rt = self.rt(Path(tmp))
            with mock.patch.object(rt.os, "pids_of", return_value=[77]):
                self.assertEqual(resolve_pid(rt, 0, "Game.exe"), 77)
            with mock.patch.object(rt.os, "dump_process", side_effect=OSError("access denied")):
                with self.assertRaisesRegex(ViwoError, "access denied"):
                    dump(rt, Path(tmp) / "ws", 5)
            req = RuntimeRequest(Path(tmp) / "ws", pid=5, seconds=0.1)
            for effect, why in ((OSError("perf missing"), "perf missing"), (None, "no sample")):
                kw = {"side_effect": effect} if effect else {"return_value": ([], [])}
                with mock.patch.object(rt.os, "sample_threads", **kw):
                    with self.assertRaisesRegex(ViwoError, why):
                        profile(rt, req)
            plain = Path(tmp) / "not.dll"
            plain.write_bytes(b"MZ" + bytes(400))  # a PE stub without an export table
            self.assertEqual(exports(plain), [])

    def test_agent_waits_report_progress_and_stop_on_cancel(self) -> None:
        from viwo.core.capture import agents
        from viwo.core.capture.runtime import RuntimeRequest

        with tempfile.TemporaryDirectory() as tmp:
            rt = self.rt(Path(tmp))
            with self.assertRaises(ViwoError) as err:
                agents.agent_for(rt, Path(tmp))  # a folder with no engine agent
            self.assertEqual(err.exception.code, "unavailable")
            said, polls = [], []
            agent = SimpleNamespace(backend_id="fake-agent", finished=lambda c, e: len(polls) > 3)
            child = SimpleNamespace(alive=lambda: polls.append(1) or True)
            ctx = SimpleNamespace(
                cancel=SimpleNamespace(cancelled=False), log=lambda m, **k: said.append(m)
            )
            req = RuntimeRequest(Path(tmp), timeout=30)
            with (
                mock.patch.object(agents, "REPORT_EVERY", 0),
                mock.patch.object(agents.time, "sleep"),
            ):
                self.assertTrue(agents._wait(agent, Path(tmp), Path(tmp), child, req, ctx))
                self.assertTrue(any("Waiting for fake-agent" in m for m in said))
                ctx.cancel.cancelled = True
                never = SimpleNamespace(backend_id="slow", finished=lambda c, e: False)
                self.assertFalse(agents._wait(never, Path(tmp), Path(tmp), child, req, ctx))


class AnalyzerFailureTests(unittest.TestCase):
    def test_a_timeout_is_named_as_one(self) -> None:
        from viwo.core.analysis._process import failed

        late = SimpleNamespace(timed_out=True, stderr="partial", stdout="")
        self.assertIn("timed out", failed(late, "x").error)
        broke = SimpleNamespace(timed_out=False, stderr="", stdout="")
        self.assertEqual(failed(broke, "no output").error, "no output")


if __name__ == "__main__":
    unittest.main()
