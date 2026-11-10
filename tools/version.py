"""Version scheme (owner's rule, strictly automated): va.b.c

a = product version, bumped when a roadmap is finished (public release, CI runs on its tag);
b = feature version, bumped for every new feature or feature overhaul;
c = tweak version, bumped by one on every single commit.
Every commit goes through `python tools/version.py commit -m "..." [--feature|--major]`, which
runs the checks, bumps the version, commits and tags va.b.c. A pre-commit hook (installed by
this script) refuses any commit whose version was not bumped past the latest tag.
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = {
    ROOT / "pyproject.toml": re.compile(r'^(version = ")(\d+\.\d+\.\d+)(")', re.M),
    ROOT / "viwo" / "__init__.py": re.compile(r'^(__version__ = ")(\d+\.\d+\.\d+)(")', re.M),
}
CHECKS = (
    [sys.executable, "-m", "ruff", "format", "viwo", "tests", "tools", "packaging"],
    [sys.executable, "-m", "ruff", "check", "viwo", "tests", "tools", "packaging"],
    [sys.executable, "tools/loc_count.py"],
)
SUITE = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."]
HOOK = "#!/bin/sh\n# ViWo: every commit must bump the version (tools/version.py)\n"
HOOK += 'exec "${VIWO_PYTHON:-python}" tools/version.py verify\n'


def read(path: Path) -> str:
    match = FILES[path].search(path.read_text(encoding="utf-8"))
    if match is None:
        sys.exit(f"version: no version line in {path.name}")
    return match.group(2)


def current() -> str:
    return read(ROOT / "pyproject.toml")


def next_version(version: str, kind: str) -> str:
    a, b, c = (int(x) for x in version.split("."))
    if kind == "major":
        return f"{a + 1}.0.0"
    if kind == "feature":
        return f"{a}.{b + 1}.0"
    return f"{a}.{b}.{c + 1}"


def write(version: str) -> None:
    for path, pattern in FILES.items():
        text = pattern.sub(lambda m: f"{m.group(1)}{version}{m.group(3)}", path.read_text("utf-8"))
        path.write_text(text, encoding="utf-8", newline="\n")


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and result.returncode:
        sys.exit(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def latest_tag() -> str:
    tags = [
        t for t in git("tag", "--list", "v*").splitlines() if re.fullmatch(r"v\d+\.\d+\.\d+", t)
    ]
    return max(tags, key=lambda t: tuple(int(x) for x in t[1:].split("."))) if tags else ""


def verify() -> None:
    version, init = current(), read(ROOT / "viwo" / "__init__.py")
    if version != init:
        sys.exit(f"version: pyproject.toml says {version}, viwo/__init__.py says {init}")
    tag = latest_tag()
    if tag and tuple(map(int, version.split("."))) <= tuple(map(int, tag[1:].split("."))):
        sys.exit(
            f"version: {version} is not past the latest tag {tag}. "
            'Commit with: python tools/version.py commit -m "..." [--feature|--major]'
        )
    print(f"version {version} ok (latest tag {tag or 'none'})")


def install_hook() -> None:
    hook = ROOT / ".git" / "hooks" / "pre-commit"
    if hook.parent.is_dir() and (not hook.exists() or hook.read_text() != HOOK):
        hook.write_text(HOOK, encoding="utf-8", newline="\n")
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def tests_argv(full: bool) -> list[str] | None:
    """The whole suite, or only the tests the change can affect (tools/affected.py); None when
    no test can see the change."""
    if full:
        return SUITE
    sys.path.insert(0, str(ROOT / "tools"))
    import affected  # noqa: PLC0415 (a sibling script, found through the path set above)

    picked = affected.select(affected.changed())
    if picked is None:
        return SUITE
    print(f"tests affected by the change: {', '.join(picked) or 'none'}", flush=True)
    return [sys.executable, "-m", "unittest", *picked] if picked else None


def run_checks(full: bool = False) -> None:
    suite = tests_argv(full)
    for argv in (*CHECKS, *([suite] if suite else [])):
        print("+", " ".join(argv[1:]), flush=True)
        code = subprocess.run(argv, cwd=ROOT).returncode
        if code:  # say which check, so the cause is in the last line of the output
            sys.exit(f"version: `{' '.join(argv[1:])}` failed (exit {code}), nothing committed")


def commit(args: argparse.Namespace) -> None:
    install_hook()
    if git("status", "--porcelain") == "":
        sys.exit("version: nothing to commit")
    if not args.no_checks:
        run_checks(args.full)
    version = next_version(
        current(), "major" if args.major else "feature" if args.feature else "tweak"
    )
    write(version)
    git("add", "-A")
    env = {**os.environ, "VIWO_PYTHON": sys.executable}
    subprocess.run(["git", "commit", "-q", "-m", args.message], cwd=ROOT, env=env, check=True)
    git("tag", "-a", f"v{version}", "-m", args.message)
    print(f"committed and tagged v{version}")
    if args.push:
        git("push", "origin", "HEAD", "--tags")
        print("pushed branch and tags")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="print the current version")
    sub.add_parser("verify", help="pre-commit check: version bumped past the latest tag")
    sub.add_parser("install-hook", help="install the pre-commit hook")
    bp = sub.add_parser("bump", help="bump the version in pyproject.toml and viwo/__init__.py")
    bp.add_argument("kind", choices=["tweak", "feature", "major"])
    cp = sub.add_parser("commit", help="checks, bump, commit, tag (the only way to commit)")
    cp.add_argument("-m", "--message", required=True)
    cp.add_argument("--feature", action="store_true", help="bump b (new feature or overhaul)")
    cp.add_argument("--major", action="store_true", help="bump a (roadmap finished)")
    cp.add_argument("--no-checks", action="store_true", help="skip format/lint/caps/tests")
    cp.add_argument("--full", action="store_true", help="run the whole suite, not the affected")
    cp.add_argument("--push", action="store_true", help="push the branch and all tags")
    args = ap.parse_args(argv)
    if args.cmd == "show":
        print(current())
    elif args.cmd == "verify":
        verify()
    elif args.cmd == "install-hook":
        install_hook()
    elif args.cmd == "bump":
        write(next_version(current(), args.kind))
        print(current())
    else:
        commit(args)


if __name__ == "__main__":
    main()
