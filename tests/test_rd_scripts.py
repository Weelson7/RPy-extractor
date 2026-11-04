"""L3: the RenderDoc helper scripts (rd_harvest.py, rd_trigger.py) run as the separate processes
they are, against a fake `renderdoc` module that plays a random capture: every texture comes out
once as PNG, every shader object a draw or dispatch used (nested actions too) is disassembled
once, the newest target is the one triggered, and each exit code means what the script says."""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from viwo.core.capture.renderdoc import SCRIPTS

FAKE = """
import json, os, time
PLAN = json.load(open(os.environ["FAKE_RD_PLAN"], encoding="utf-8"))
CALLS = []


def _log(*a):
    with open(os.environ["FAKE_RD_LOG"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps(a) + chr(10))


class ActionFlags:
    Drawcall, Dispatch, Clear = 1, 2, 4


class ShaderStage:
    Vertex, Hull, Domain, Geometry, Pixel, Compute = range(6)


class FileType:
    PNG = "png"


class AlphaMapping:
    Preserve = "keep"


class ResultCode:
    Succeeded = 0


class TextureSave:
    pass


class ReplayOptions:
    pass


class GlobalEnvironment:
    pass


class _Action:
    def __init__(self, node):
        self.eventId, self.flags = node["id"], node["flags"]
        self.children = [_Action(c) for c in node["children"]]


class _Refl:
    def __init__(self, rid):
        self.resourceId = rid


class _State:
    def __init__(self, stages):
        self.stages = stages

    def GetShaderReflection(self, stage):
        rid = self.stages.get(str(stage))
        return _Refl(rid) if rid is not None else None

    def GetComputePipelineObject(self):
        return "compute"

    def GetGraphicsPipelineObject(self):
        return "graphics"


class _Tex:
    def __init__(self, rid):
        self.resourceId = rid


class _Controller:
    event = None

    def GetTextures(self):
        return [_Tex(r) for r in PLAN["textures"]]

    def SaveTexture(self, save, path):
        open(path, "wb").write(b"PNG" + str(save.resourceId).encode())

    def GetRootActions(self):
        return [_Action(n) for n in PLAN["actions"]]

    def SetFrameEvent(self, event, force):
        self.event = event

    def GetPipelineState(self):
        return _State(PLAN["stages"].get(str(self.event), {}))

    def GetDisassemblyTargets(self, pipeline):
        return ["DXIL"]

    def DisassembleShader(self, pipe, refl, target):
        _log("disasm", self.event, refl.resourceId, pipe)
        return f"; shader {refl.resourceId} via {pipe}"

    def Shutdown(self):
        pass


class _Capture:
    def OpenFile(self, path, kind, progress):
        return 0 if PLAN.get("open", True) else 1

    def OpenCapture(self, options, progress):
        return (0 if PLAN.get("replay", True) else 1), _Controller()

    def Shutdown(self):
        pass


def InitialiseReplay(env, args):
    pass


def ShutdownReplay():
    pass


def OpenCaptureFile():
    return _Capture()


class TargetControlMessageType:
    Noop, NewCapture = 0, 1


class _Msg:
    def __init__(self, kind, path=""):
        self.type = kind
        self.newCapture = type("C", (), {"path": path})()


class _Conn:
    def __init__(self, ident):
        self.ident, self.polls = ident, 0

    def TriggerCapture(self, frames):
        _log("trigger", self.ident, frames)

    def ReceiveMessage(self, progress):
        self.polls += 1
        if PLAN.get("capture_after") is not None and self.polls > PLAN["capture_after"]:
            return _Msg(TargetControlMessageType.NewCapture, "frame.rdc")
        return _Msg(TargetControlMessageType.Noop)

    def Shutdown(self):
        _log("shutdown", self.ident)


def EnumerateRemoteTargets(host, after):
    idents = PLAN.get("targets", [])
    later = [i for i in idents if i > after]
    return min(later) if later else 0


def CreateTargetControl(host, ident, name, force):
    return _Conn(ident) if PLAN.get("connect", True) else None
"""


def _tree(rng: random.Random, next_id: list[int], depth: int = 0) -> list[dict]:
    nodes = []
    for _ in range(rng.randint(1, 4)):
        next_id[0] += 1
        children = _tree(rng, next_id, depth + 1) if depth < 2 and rng.random() < 0.4 else []
        nodes.append({"id": next_id[0], "flags": rng.choice([1, 2, 4, 0]), "children": children})
    return nodes


def _walk(nodes):
    for n in nodes:
        yield n
        yield from _walk(n["children"])


class Fake:
    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "fake").mkdir()
        (root / "fake" / "renderdoc.py").write_text(FAKE, encoding="utf-8")

    def run(self, script: str, plan: dict, *args: str, timeout: float = 60):
        (self.root / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        log = self.root / "log.jsonl"
        log.unlink(missing_ok=True)
        env = {
            **os.environ,
            "PYTHONPATH": str(self.root / "fake"),
            "FAKE_RD_PLAN": str(self.root / "plan.json"),
            "FAKE_RD_LOG": str(log),
        }
        done = subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        lines = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
        return done, [json.loads(x) for x in lines]


class HarvestTests(unittest.TestCase):
    def test_every_texture_once_and_every_used_shader_once(self) -> None:
        rng = random.Random(12)
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake(Path(tmp))
            for i in range(6):
                actions = _tree(rng, [0])
                stages = {}
                for node in _walk(actions):  # random shaders, often shared between draws
                    picked = rng.sample(range(6), rng.randint(0, 3))
                    stages[str(node["id"])] = {str(s): rng.randrange(100, 106) for s in picked}
                textures = rng.sample(range(1000, 1100), rng.randint(0, 8))
                plan = {"actions": actions, "stages": stages, "textures": textures}
                out = Path(tmp) / f"out{i}"
                done, calls = fake.run("rd_harvest.py", plan, "frame.rdc", str(out))
                self.assertEqual(done.returncode, 0, done.stderr)
                got = sorted(p.name for p in out.glob("tex_*.png"))
                self.assertEqual(got, sorted(f"tex_{t}.png" for t in textures))
                want = set()
                for node in _walk(actions):
                    if node["flags"] & 3:
                        want |= set(stages[str(node["id"])].values())
                disassembled = [c[2] for c in calls if c[0] == "disasm"]
                self.assertEqual(sorted(disassembled), sorted(want))  # once per shader object
                for c in calls:  # a compute shader goes through the compute pipeline
                    stage_of = {v: k for k, v in stages[str(c[1])].items()}
                    compute = stage_of[c[2]] == "5"
                    self.assertEqual(c[3], "compute" if compute else "graphics")
                names = {p.name.split("_")[1] for p in out.glob("shader_*.txt")}
                self.assertEqual(names, {str(w) for w in want})

    def test_unreadable_capture_and_failed_replay_have_their_own_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake(Path(tmp))
            base = {"actions": [], "stages": {}, "textures": [1]}
            for plan, code in (({**base, "open": False}, 2), ({**base, "replay": False}, 3)):
                done, _ = fake.run("rd_harvest.py", plan, "x.rdc", str(Path(tmp) / "o"))
                self.assertEqual(done.returncode, code)
                self.assertFalse((Path(tmp) / "o").exists())  # nothing half written


class TriggerTests(unittest.TestCase):
    def test_the_newest_target_is_captured_or_the_reason_is_the_exit_code(self) -> None:
        rng = random.Random(5)
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake(Path(tmp))
            for _ in range(5):
                targets = sorted(rng.sample(range(1, 50), rng.randint(1, 4)))
                done, calls = fake.run(
                    "rd_trigger.py", {"targets": targets, "capture_after": 2}, "0", "20"
                )
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertIn("capture frame.rdc", done.stdout)
                self.assertEqual(calls[0], ["trigger", targets[-1], 1])  # the game just launched
                self.assertEqual(calls[-1], ["shutdown", targets[-1]])  # always let go
            cases = (
                ({"targets": []}, 2, "0", "1"),  # nothing registered before the deadline
                ({"targets": [3], "connect": False}, 2, "0", "5"),
                ({"targets": [3], "capture_after": None}, 3, "0", "1"),  # no capture in time
            )
            for plan, code, delay, timeout in cases:
                done, calls = fake.run("rd_trigger.py", plan, delay, timeout)
                self.assertEqual(done.returncode, code, plan)
                if plan.get("connect", True) and plan["targets"]:
                    self.assertEqual(calls[-1][0], "shutdown")

    def test_settings_come_from_the_environment_when_qrenderdoc_passes_no_argv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake(Path(tmp))
            os.environ["VIWO_RD_DELAY"], os.environ["VIWO_RD_TIMEOUT"] = "0", "10"
            try:
                done, _ = fake.run("rd_trigger.py", {"targets": [9], "capture_after": 0})
            finally:
                del os.environ["VIWO_RD_DELAY"], os.environ["VIWO_RD_TIMEOUT"]
            self.assertEqual(done.returncode, 0, done.stderr)
            out = Path(tmp) / "env-out"
            os.environ["VIWO_RD_CAPTURE"], os.environ["VIWO_RD_OUT"] = "f.rdc", str(out)
            try:
                plan = {"actions": [], "stages": {}, "textures": [7]}
                done, _ = fake.run("rd_harvest.py", plan)
            finally:
                del os.environ["VIWO_RD_CAPTURE"], os.environ["VIWO_RD_OUT"]
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue((out / "tex_7.png").is_file())


class BackendTests(unittest.TestCase):
    """RenderDocCapture over a fake OS layer: every way a capture ends is named, and only the
    textures of harvests that succeeded are counted."""

    def ctx(self, root: Path, run, tools=True, config_ok=True):
        from types import SimpleNamespace

        located = SimpleNamespace(argv_prefix=("rd",), path="rd")
        logs = []
        home = root / ("cfg" if config_ok else "blocked")
        if not config_ok:
            home.write_text("a file where the config folder should be")
        host = SimpleNamespace(
            os_id="windows",
            config_home=lambda: home,
            data_home=lambda: home,
            tools=SimpleNamespace(locate=lambda spec: located if tools else None),
            process=SimpleNamespace(
                run=run,
                launch=lambda argv, env=None: SimpleNamespace(
                    kill=lambda: logs.append(("killed",))
                ),
            ),  # fmt: skip
        )
        ctx = SimpleNamespace(
            os=host, cancel=None, log=lambda msg, level="info", stage="": logs.append((level, msg))
        )
        return ctx, logs

    def test_every_ending_is_named(self) -> None:
        from types import SimpleNamespace

        from viwo.contracts.types import OutcomeKind
        from viwo.core.capture.renderdoc import HELPER, RenderDocCapture

        rng = random.Random(3)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = {"workdir": str(root), "exe": str(root / "Game.exe")}
            ctx, _ = self.ctx(root, None, tools=False)
            out = RenderDocCapture().capture(spec, root / "s0" / "staging", ctx)
            self.assertEqual(out.kind, OutcomeKind.UNAVAILABLE)
            for i in range(6):
                staging = root / f"s{i + 1}" / "staging"
                shots = rng.randint(1, 3) if i else 0  # the first run takes none
                ok = [rng.random() < 0.7 for _ in range(shots)]

                def run(argv, timeout=None, cancel=None, env=None, staging=staging, ok=ok):
                    if str(HELPER) in argv:  # a harvest: textures only when it succeeds
                        k = int(Path(argv[-2]).stem.split("-")[1])
                        if ok[k]:
                            Path(argv[-1]).mkdir(parents=True)
                            for t in range(k + 1):
                                (Path(argv[-1]) / f"tex_{t}.png").write_bytes(b"P")
                        return SimpleNamespace(ok=ok[k], returncode=0 if ok[k] else 1)
                    for k in range(len(ok)):  # the game ran: its captures land
                        (staging.parent / "captures" / f"viwo-{k}.rdc").write_bytes(b"R")
                    return SimpleNamespace(ok=True, stderr="", stdout="", returncode=0)

                ctx, logs = self.ctx(root, run, config_ok=i != 2)
                attended = {**spec, "capture_after": 0}
                out = RenderDocCapture().capture(attended, staging, ctx)
                if not shots:
                    self.assertEqual(
                        (out.kind, out.error), (OutcomeKind.FAILED, "no capture was taken")
                    )
                    continue
                self.assertEqual(out.kind, OutcomeKind.OK)
                self.assertEqual(out.files, sum(k + 1 for k in range(shots) if ok[k]))
                said = " ".join(m for _, m in logs)
                self.assertIn("F12", said)  # attended: the user is told what to do
                self.assertEqual(said.count(": failed"), ok.count(False))
                if i == 2:  # the first-run answers could not be written: a warning
                    self.assertIn("warn", {lv for lv, _ in logs})


if __name__ == "__main__":
    unittest.main()
