"""L1: the Linux OS layer on any host, against a fake /proc tree: a memory dump holds exactly the
readable mappings with regions.json saying where each starts, the process list survives a
process exiting mid-read, module spans cover every mapping of their file, perf output parses
whatever junk surrounds it, and each perf failure says why."""

from __future__ import annotations

import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from viwo.os import _linux_probe as probe
from viwo.os import linux


def _maps(rng: random.Random, size: int) -> tuple[list[str], list[tuple[int, int, str]]]:
    lines, regions, at = [], [], 0x100
    while at < size - 0x100:
        start = at + rng.randrange(0, 0x80)
        end = min(size, start + rng.randrange(0x10, 0x200))
        perms = rng.choice(["r-xp", "rw-p", "---p", "r--s"])
        path = rng.choice(["", "/usr/lib/libc.so.6", "/opt/game/Game", "[heap]"])
        offset = rng.randrange(0, 0x1000, 0x100)
        lines.append(f"{start:x}-{end:x} {perms} {offset:08x} 08:01 1234 {path}".rstrip())
        regions.append((start, end, perms))
        at = end
    return lines, regions


class ProcTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.proc = Path(self._tmp.name) / "proc"
        self.proc.mkdir()
        for module in (linux, probe):
            patcher = mock.patch.object(module, "PROC", self.proc)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_dump_holds_exactly_the_readable_mappings(self) -> None:
        rng = random.Random(3)
        for pid in range(10, 16):
            size = rng.randrange(0x400, 0x4000)
            mem = rng.randbytes(size)
            lines, regions = _maps(rng, size)
            (self.proc / str(pid)).mkdir()
            (self.proc / str(pid) / "maps").write_text("\n".join(lines) + "\n")
            (self.proc / str(pid) / "mem").write_bytes(mem)
            out = Path(self._tmp.name) / f"out{pid}"
            out.mkdir()
            dump = linux._proc_dump(pid, out).read_bytes()
            listed = json.loads((out / "regions.json").read_text(encoding="utf-8"))
            readable = [(s, e) for s, e, p in regions if "r" in p]
            self.assertEqual([(int(r["start"], 16), int(r["end"], 16)) for r in listed], readable)
            self.assertEqual(len(dump), sum(e - s for s, e in readable))
            for r in listed:  # each region sits where regions.json says, byte for byte
                s, e = int(r["start"], 16), int(r["end"], 16)
                self.assertEqual(dump[r["at"] : r["at"] + e - s], mem[s:e])

    def test_a_mapping_the_kernel_refuses_is_left_out_not_fatal(self) -> None:
        import builtins
        import io

        real = builtins.open
        (self.proc / "9").mkdir()
        lines = [
            "1000-1100 r--p 0 0:0 0",
            "2000-2100 r--p 0 0:0 0 [vvar]",
            "3000-3010 rw-p 0 0:0 0",
        ]
        (self.proc / "9" / "maps").write_text("\n".join(lines) + "\n")
        (self.proc / "9" / "mem").write_bytes(b"")

        class Mem(io.BytesIO):  # [vvar]-like: reading it fails with EIO
            def seek(self, at, whence=0):
                if at == 0x2000:
                    raise OSError(5, "Input/output error")
                return super().seek(at, whence)

        def fake_open(path, *a, **k):
            if str(path).endswith("mem") and "proc" in str(path):
                return Mem(bytes(0x4000))
            return real(path, *a, **k)

        out = Path(self._tmp.name) / "o9"
        out.mkdir()
        with mock.patch.object(builtins, "open", fake_open):
            linux._proc_dump(9, out)
        starts = [r["start"] for r in json.loads((out / "regions.json").read_text())]
        self.assertEqual(starts, ["0x1000", "0x3000"])
        with mock.patch.object(probe, "sample_threads", return_value=([], [])) as sample:
            self.assertEqual(linux.LinuxOS._sample(9, 1.0), ([], []))
        sample.assert_called_once_with(9, 1.0, None)
        self.assertTrue(linux.PosixFs().case_sensitive)

    def test_processes_and_modules(self) -> None:
        rng = random.Random(8)
        alive = {}
        for pid in rng.sample(range(2, 999), 12):
            (self.proc / str(pid)).mkdir()
            if rng.random() < 0.2:  # exited while listed: comm cannot be read
                (self.proc / str(pid) / "comm").mkdir()
                continue
            alive[pid] = rng.choice(["Game", "steam", "bash"])
            (self.proc / str(pid) / "comm").write_text(alive[pid] + "\n")
        (self.proc / "self").mkdir()
        self.assertEqual(dict(linux._processes()), {p: n.lower() for p, n in alive.items()})
        lines, _ = _maps(rng, 0x8000)
        (self.proc / "7").mkdir()
        (self.proc / "7" / "maps").write_text("\n".join(lines) + "\n")
        modules = {path: (base, span) for base, span, path in probe.modules_of(7)}
        for line in lines:
            parts = line.split(maxsplit=5)
            if len(parts) < 6 or not parts[5].startswith("/"):
                self.assertNotIn(parts[-1], modules)  # anonymous and [heap] are no module
                continue
            start, end = (int(x, 16) for x in parts[0].split("-"))
            base, span = modules[parts[5]]
            self.assertLessEqual(base, start - int(parts[2], 16))
            self.assertGreaterEqual(base + span, end)


class PerfTests(unittest.TestCase):
    def test_parse_keeps_only_tid_ip_pairs(self) -> None:
        rng = random.Random(2)
        want, lines = [], []
        for _ in range(200):
            if rng.random() < 0.6:
                tid, ip = rng.randrange(1, 9999), rng.randrange(1 << 48)
                want.append((tid, ip))
                lines.append(f"  {tid}  {ip:x}")
            else:
                lines.append(rng.choice(["", "perf: lost 3 samples", "# header", "x 12"]))
        self.assertEqual(probe.parse("\n".join(lines)), want)

    def test_each_perf_failure_says_why(self) -> None:
        with mock.patch.object(probe.shutil, "which", return_value=None):
            with self.assertRaisesRegex(OSError, "perf is not installed"):
                probe.sample_threads(1, 0.1)

        def record(argv, **kw):
            if argv[1] == "record" and ok:
                Path(argv[argv.index("-o") + 1]).write_bytes(b"data")
            text = "1 7f00\n2 7f10\n" if argv[1] == "script" else ""
            return SimpleNamespace(returncode=0 if ok else 1, stderr="paranoid", stdout=text)

        with (
            mock.patch.object(probe.shutil, "which", return_value="/usr/bin/perf"),
            mock.patch.object(probe, "modules_of", return_value=[(0, 10, "/g")]),
            mock.patch.object(probe.subprocess, "run", record),
        ):
            ok = False
            with self.assertRaisesRegex(OSError, "perf_event_paranoid"):
                probe.sample_threads(1, 0.1)
            ok = True
            self.assertEqual(
                probe.sample_threads(1, 0.1), ([(1, 0x7F00), (2, 0x7F10)], [(0, 10, "/g")])
            )


class HostTests(unittest.TestCase):
    def test_host_answers(self) -> None:
        host = linux.LinuxOS()
        self.assertEqual(host.is_supported_host(), sys.platform.startswith("linux"))
        for env, name in (
            ({"XDG_CONFIG_HOME": "/x/cfg"}, "cfg"),
            ({"XDG_CONFIG_HOME": ""}, ".config"),
        ):
            with mock.patch.dict(linux.os.environ, env):  # unset or empty: ~/.config
                self.assertEqual(host.config_home().name, name)
        with mock.patch.dict(linux.os.environ, {"XDG_DATA_HOME": "/x/data"}):
            self.assertEqual(host.data_home(), Path("/x/data"))
        for effect, alive in ((None, True), (ProcessLookupError, False), (PermissionError, True)):
            with mock.patch.object(linux.os, "kill", side_effect=effect):
                self.assertEqual(linux.LinuxOS.pid_alive(4), alive)
        proc = mock.Mock(pid=5)
        kill9 = mock.patch.object(linux.signal, "SIGKILL", 9, create=True)  # absent on Windows
        kill9.start()
        self.addCleanup(kill9.stop)
        with mock.patch.object(linux.os, "killpg", side_effect=ProcessLookupError, create=True):
            linux._kill_group(proc)  # the group is gone: the process itself is killed
        proc.kill.assert_called_once()
        with mock.patch.object(linux.os, "killpg", create=True) as killpg:
            linux._kill_group(proc)
        killpg.assert_called_once()
        shell = linux.LinuxShell()
        self.assertFalse(shell.open_folder(Path("/no/such/folder"))[0])
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(linux, "open_with") as opened:
            opened.return_value = (True, "")
            self.assertEqual(shell.open_folder(Path(tmp)), (True, ""))
        self.assertEqual(opened.call_args[0][0][0], "xdg-open")
        self.assertIn(Path("/usr/bin"), linux._install_roots())


if __name__ == "__main__":
    unittest.main()
