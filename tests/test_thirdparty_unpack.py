"""L3: the third_party installer's unpack and failure paths, as properties over random tools:
every archive kind the manifest uses lands the tool where `find` says and nothing outside it,
a reinstall leaves no stale file, every failure is named (short read, cancel, quarantine, a
locked folder, a failed unpacker) and leaves no half-installed tool behind."""

from __future__ import annotations

import gzip
import hashlib
import io
import os
import random
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from viwo.contracts import ViwoError
from viwo.core import downloads, thirdparty, workers

P = thirdparty.PLATFORM


def _tree(rng: random.Random) -> dict[str, bytes]:
    names = {f"d{rng.randrange(3)}/f{i}.bin" for i in range(rng.randint(1, 6))}
    return {"bin/tool.exe": rng.randbytes(40), **{n: rng.randbytes(30) for n in names}}


def _zip(members: dict[str, bytes]) -> bytes:
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        for name, blob in members.items():
            z.writestr(name, blob)
        z.writestr("../escape.txt", b"no")
    return data.getvalue()


def _tar(members: dict[str, bytes]) -> bytes:
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as t:
        for name, blob in {**members, "../escape.txt": b"no"}.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(blob), 0o755
            t.addfile(info, io.BytesIO(blob))
        link = tarfile.TarInfo("bin/link")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        t.addfile(link)
    return data.getvalue()


def _pin(root: Path, name: str, blob: bytes, **spec) -> dict:
    file = root / name
    file.write_bytes(blob)
    sha = hashlib.sha256(blob).hexdigest()
    return {"url": file.as_uri(), "sha256": sha, "size": len(blob), **spec}


def _manifest(tools: dict) -> dict:
    return {"python": {"pkg": "1.0"}, "tools": {k: {P: v} for k, v in tools.items()}}


def _files(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in folder.rglob("*")
        if p.is_file() and p.name != thirdparty.CACHE
    }


class Runner:
    """A 7-Zip stand-in for sfx installers: it unpacks the zip the stub carries."""

    def __init__(self, ok: bool = True) -> None:
        self.ok, self.calls = ok, []

    def run(self, argv, timeout=None):
        self.calls.append(argv)
        if self.ok:
            out = next(a[2:] for a in argv if a.startswith("-o"))
            with zipfile.ZipFile(argv[-1]) as z:
                for info in z.infolist():
                    if ".." not in info.filename:
                        z.extract(info, out)
        return SimpleNamespace(ok=self.ok, stderr="7z broke" if not self.ok else "")


class UnpackKindTests(unittest.TestCase):
    def test_every_kind_lands_the_tree_and_a_reinstall_leaves_nothing_stale(self) -> None:
        rng = random.Random(17)
        with tempfile.TemporaryDirectory() as tmp:
            root, home = Path(tmp), Path(tmp) / "home"
            seven = _pin(root, "7z.zip", _zip({"7z.exe": b"7"}), kind="zip", find="7z.exe")
            for i in range(12):
                kind = rng.choice(["zip", "tar", "gz", "raw", "sfx"])
                tree = _tree(rng)
                if kind in ("gz", "raw"):
                    tree = {"tool.exe": tree["bin/tool.exe"]}
                    blob = gzip.compress(tree["tool.exe"]) if kind == "gz" else tree["tool.exe"]
                else:
                    blob = (_tar if kind == "tar" else _zip)(tree)
                extra = {"save_as": "tool.exe"} if kind in ("gz", "raw") else {}
                spec = _pin(root, f"t{i}.{kind}", blob, kind=kind, find="tool.exe", **extra)
                runner = Runner()
                with mock.patch.object(
                    thirdparty, "manifest", lambda s=spec: _manifest({"t": s, "sevenzip": seven})
                ):
                    path = thirdparty.install_tool("t", home, runner)
                    self.assertEqual(thirdparty.tool_argv("t", home), (path,))
                folder = home / "third_party" / "t"
                self.assertEqual(_files(folder), tree)  # exactly the tree: older files gone
                self.assertFalse(list(home.rglob("escape.txt")))
                self.assertFalse((folder / "bin" / "link").exists())  # links never extracted
                self.assertEqual(bool(runner.calls), kind == "sfx")

    def test_msi_runs_an_administrative_install_and_names_its_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, home = Path(tmp), Path(tmp) / "home"
            spec = _pin(root, "t.msi", b"msi", kind="msi", find="tool.exe")
            seen = []

            def msiexec(command, timeout):
                seen.append(command)
                target = Path(command.split('TARGETDIR="')[1].rstrip('"'))
                (target / "tool.exe").write_bytes(b"x")
                return SimpleNamespace(returncode=0 if len(seen) == 1 else 1603)

            with (
                mock.patch.object(thirdparty, "manifest", lambda: _manifest({"t": spec})),
                mock.patch.object(thirdparty.subprocess, "run", msiexec),
            ):
                thirdparty.install_tool("t", home, None)
                self.assertTrue(seen[0].startswith('msiexec /a "'))  # quoted paths reach it
                with self.assertRaises(ViwoError) as err:
                    thirdparty.install_tool("t", root / "other", None)
            self.assertIn("1603", err.exception.message)
            self.assertFalse((root / "other" / "third_party" / "t").exists())


class FailureTests(unittest.TestCase):
    def _install(self, spec: dict, home: Path, runner=None, **kw):
        with mock.patch.object(thirdparty, "manifest", lambda: _manifest({"t": spec})):
            return thirdparty.install_tool("t", home, runner, **kw)

    def test_every_failure_is_named_and_installs_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = _pin(root, "t.zip", _zip({"tool.exe": b"t"}), kind="zip", find="tool.exe")
            cancel = SimpleNamespace(cancelled=True)
            cases = {
                "short": ({**good, "size": good["size"] + 9}, {}, "failed", "incomplete"),
                "cancel": (good, {"cancel": cancel}, "cancelled", "cancelled"),
                "find": ({**good, "find": "other.exe"}, {}, "failed", "not found after"),
                "sfx": ({**good, "kind": "sfx"}, {}, "failed", "7-Zip could not"),
            }
            for name, (spec, kw, code, text) in cases.items():
                said = []
                with self.assertRaises(ViwoError) as err:
                    self._install(spec, root / name, Runner(ok=False), say=said.append, **kw)
                self.assertEqual(err.exception.code, code, name)
                self.assertIn(text, err.exception.message, name)
                self.assertFalse((root / name / "third_party" / "t").exists(), name)
                if name == "short":  # three attempts, each retry said
                    self.assertEqual(sum("retrying" in str(s) for s in said), 3)

    def test_quarantine_and_a_locked_folder_keep_the_installed_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, home = Path(tmp), Path(tmp) / "home"
            good = _pin(root, "t.zip", _zip({"tool.exe": b"t"}), kind="zip", find="tool.exe")
            self._install(good, home)
            before = _files(home / "third_party" / "t")
            gone = OSError(13, "quarantined")
            with mock.patch.object(thirdparty, "_unpack", side_effect=gone):
                with self.assertRaises(ViwoError) as err:
                    self._install(good, home)
            self.assertIn("antivirus", err.exception.hint)
            real = os.replace

            def locked(src, dst):  # the fresh folder cannot move in (Windows: a held handle)
                if Path(src).name == "out":
                    raise PermissionError(32, "in use")
                real(src, dst)

            with mock.patch.object(downloads.os, "replace", locked):
                with self.assertRaises(ViwoError) as err:
                    self._install(good, home)
            self.assertEqual(err.exception.code, "busy")
            self.assertEqual(_files(home / "third_party" / "t"), before)  # whole, not half gone
            with self.assertRaises(ViwoError):
                self._install({**good, "find": "other.exe"}, home)
            self.assertEqual(_files(home / "third_party" / "t"), before)  # a bad build: kept
            with mock.patch.object(thirdparty, "manifest", lambda: _manifest({})):
                with self.assertRaises(ViwoError) as err:
                    thirdparty.install_tool("t", home, None)
            self.assertEqual(err.exception.code, "unavailable")

    def test_edges_of_install_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, home = Path(tmp), Path(tmp) / "home"
            good = _pin(root, "t.zip", _zip({"tool.exe": b"t"}), kind="zip", find="tool.exe")
            with self.assertRaises(ViwoError) as err:
                self._install({**good, "kind": "cab"}, root / "cab")
            self.assertIn("unknown archive kind", err.exception.message)
            (home / "third_party" / ".t.old" / "x").mkdir(parents=True)  # a leftover swap
            with self.assertRaises(ViwoError):  # a short read without a progress line to say
                self._install({**good, "size": good["size"] + 1}, home)
            self._install(good, home)
            self.assertFalse((home / "third_party" / ".t.old").exists())
            alias = {"t": good, "a": {"from": "t", "needs": ["t"], "find": "missing.exe"}}
            with mock.patch.object(thirdparty, "manifest", lambda: _manifest(alias)):
                with self.assertRaises(ViwoError) as err:  # t is there: not fetched again
                    thirdparty.install_tool("a", home, None)
            self.assertIn("missing.exe not found", err.exception.message)
            worker = next(iter(workers.entries()))
            with mock.patch.object(workers, "install", return_value="ran") as install:
                self.assertEqual(thirdparty.install_tool(worker, home, "R"), "ran")
            install.assert_called_once_with(worker, home, "R")

    def test_posix_unpack_keeps_the_exec_bit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chmod = []
            with (
                mock.patch.object(downloads, "POSIX", True),
                mock.patch.object(downloads.os, "chmod", lambda p, m: chmod.append((p, m))),
            ):
                downloads.write(io.BytesIO(b"x"), Path(tmp) / "run", 0o755)
                downloads.write(io.BytesIO(b"x"), Path(tmp) / "data", 0o644)
            self.assertEqual([Path(p).name for p, m in chmod], ["run"])
            self.assertTrue(chmod[0][1] & 0o111)


class LocatorTests(unittest.TestCase):
    def test_the_cache_is_only_a_shortcut(self) -> None:
        """Whatever the cache says (stale, wrong type, unwritable), the hit is the real file."""
        rng = random.Random(2)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "t"
            (folder / "a").mkdir(parents=True)
            real = folder / "a" / "tool.exe"
            real.write_bytes(b"x")
            cache = folder / thirdparty.CACHE
            for _ in range(20):
                cache.write_text(
                    rng.choice(['["x"]', '{"tool.exe": "gone/tool.exe"}', "{}", "7", "{bad"])
                )
                self.assertEqual(thirdparty._hit(folder, "tool.exe"), real)
            with mock.patch.object(Path, "write_text", side_effect=OSError("read-only")):
                cache.unlink()
                self.assertEqual(thirdparty._hit(folder, "tool.exe"), real)
            self.assertIsNone(thirdparty._hit(folder, "absent.exe"))
            self.assertIsNone(thirdparty._hit(folder / "nowhere", "tool.exe"))

    def test_argv_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "third_party" / "t").mkdir(parents=True)
            (home / "third_party" / "t" / "t.py").write_text("")
            specs = {
                "t": {"find": "t.py", "argv": ["{python}", "{path}"]},
                "j": {"find": "t.py", "from": "t", "argv": ["{java}", "-jar", "{path}"]},
                "jdk": {"find": "java.exe"},
            }
            with mock.patch.object(thirdparty, "manifest", lambda: _manifest(specs)):
                self.assertEqual(thirdparty.tool_argv("t", home)[0], sys.executable)
                self.assertIsNone(thirdparty.tool_argv("j", home))  # its runtime is missing
                self.assertIsNone(thirdparty.tool_argv("none", home))
                self.assertEqual(thirdparty.installed_version("none", home), "")


class EnvironmentTests(unittest.TestCase):
    def test_activate_and_the_install_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            thirdparty.python_dir(home).mkdir(parents=True)
            (home / "third_party" / "dotnet").mkdir()
            with mock.patch.dict(os.environ), mock.patch.object(sys, "path", list(sys.path)):
                thirdparty.activate(home)
                thirdparty.activate(home)  # twice: still one entry
                self.assertEqual(sys.path.count(str(thirdparty.python_dir(home))), 1)
                self.assertEqual(os.environ["DOTNET_ROOT"], str(home / "third_party" / "dotnet"))
        data = thirdparty.manifest()
        worker = next(iter(workers.entries()))
        for frozen in (False, True):
            with mock.patch.object(thirdparty, "FROZEN", frozen):
                for dep in data["python"]:  # pip pins need a pip: never in the frozen bundle
                    self.assertEqual(thirdparty.installable(dep, "python"), not frozen)
                self.assertEqual(thirdparty.installable(worker, "worker"), not frozen)
        for dep in [*data["tools"], *workers.entries()]:
            entry = data["tools"].get(dep) or workers.entries()[dep]
            self.assertEqual(thirdparty.on_demand(dep), bool(entry.get("on_demand")))
        self.assertEqual(thirdparty.installed_version(worker, Path(tmp)), "")

    def test_python_pins_install_through_pip_and_name_its_failure(self) -> None:
        dep = next(iter(thirdparty.manifest()["python"]))
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            ok = SimpleNamespace(run=lambda argv, timeout: SimpleNamespace(ok=True, stderr=""))
            bad = SimpleNamespace(run=lambda argv, timeout: SimpleNamespace(ok=False, stderr="E"))
            lock = home / "lock.txt"
            lock.write_text("")
            with (
                mock.patch.object(thirdparty, "lock_file", return_value=lock),
                mock.patch.object(sys, "path", list(sys.path)),
            ):
                pin = thirdparty.install_python(dep, home, ok)
                self.assertEqual(pin, thirdparty.manifest()["python"][dep])
                with self.assertRaises(ViwoError) as err:
                    thirdparty.install_python(dep, home, bad)
            self.assertIn(dep, err.exception.message)


if __name__ == "__main__":
    unittest.main()
