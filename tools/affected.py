"""The tests a commit runs (tools/version.py): only those a change is close to, so a commit never
runs the whole suite by default (owner). A test module is picked when it is itself changed;
when it imports a changed module, or imports a module that imports it (two steps: the reach;
`tests.helpers`, `boot` and the registry are reached but not passed through, since nearly every
test goes through them); when it, or a module in its reach, names a changed file (a doc, a data
file or folder, the web UI, a script run as a process). A plugin change also picks the tests
that name the plugin and the plugin-wide checks (PLUGIN_WIDE). Only pyproject.toml, or `--full`
(before a merge or a tag), runs everything (None); a change no test is close to runs none ([])."""

import ast
import functools
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE = ("viwo", "tests", "tools", "packaging")
EVERYTHING = {"pyproject.toml"}
HUBS = {"tests.helpers", "viwo.core.wiring.boot", "viwo.core.wiring.registry"}
PLUGIN_WIDE = ("tests.test_registry", "tests.test_conformance_kit", "tests.test_config",
               "tests.test_sealed")  # fmt: skip
DEPTH = 2


def changed() -> list[str]:
    """Paths changed against HEAD, untracked ones included (POSIX, relative to the root)."""
    out = subprocess.run(
        ["git", "status", "--porcelain", "-uall"], cwd=ROOT, capture_output=True, text=True
    ).stdout
    return sorted({line[3:].split(" -> ")[-1].strip('"') for line in out.splitlines()})


def module_of(rel: str) -> str:
    parts = list(Path(rel).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _resolve(name: str, modules: set[str]) -> str | None:
    """The longest prefix of a dotted name that is one of our modules."""
    parts = name.split(".")
    return next(
        (m for i in range(len(parts), 0, -1) if (m := ".".join(parts[:i])) in modules), None
    )


def strings(tree: ast.AST) -> tuple[str, ...]:
    """The string constants of a module's code: what it may read by name. Docstrings and
    comments are prose (a docstring naming CHANGELOG.md reads nothing)."""
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and n.body and isinstance(n.body[0], ast.Expr)}  # fmt: skip
    found = (n for n in ast.walk(tree) if isinstance(n, ast.Constant) and id(n) not in docs)
    return tuple(n.value for n in found if isinstance(n.value, str))


def _imports(path: Path, name: str, modules: set[str]) -> set[str]:
    """The modules a file imports by name (their packages are added by `reach`)."""
    package = name if path.name == "__init__.py" else name.rpartition(".")[0]
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = ".".join(package.split(".")[: len(package.split(".")) - node.level + 1])
            head = ".".join(p for p in (base if node.level else "", node.module or "") if p)
            found |= {f"{head}.{a.name}" for a in node.names} or {head}
    return {m for m in (_resolve(f, modules) for f in found) if m}


@functools.cache
def graph() -> tuple[dict[str, set[str]], dict[str, tuple[str, ...]]]:
    """(module -> modules it imports, module -> its code's string constants), every code folder."""
    files = {
        module_of(p.relative_to(ROOT).as_posix()): p for d in CODE for p in (ROOT / d).rglob("*.py")
    }
    modules = set(files)
    edges = {m: _imports(p, m, modules) for m, p in files.items()}
    return edges, {m: strings(ast.parse(p.read_text(encoding="utf-8"))) for m, p in files.items()}


def _parents(module: str) -> set[str]:
    parts = module.split(".")
    return {".".join(parts[:i]) for i in range(1, len(parts))}


def reach(test: str, edges: dict[str, set[str]]) -> set[str]:
    """The test, what it imports and what those import (DEPTH steps), with their packages; a
    hub is reached but its imports are not followed."""
    seen, frontier = {test}, {test}
    for _ in range(DEPTH):
        step = set().union(*(edges.get(m, set()) for m in frontier if m == test or m not in HUBS))
        frontier = step - seen
        seen |= frontier
    return seen | set().union(*(_parents(m) for m in seen))


def _named(rel: str, mods: set[str], text: dict[str, tuple[str, ...]]) -> bool:
    """A string in the code names the file, or is the data or web folder it is read from."""
    name, parts = Path(rel).name, Path(rel).parts
    folder = ""
    if parts[:2] in (("viwo", "web"), ("viwo", "data")) and len(parts) > 2:
        folder = parts[2] if parts[1] == "data" and len(parts) > 3 else parts[1]
    return any(name in s or (folder and s == folder) for m in mods for s in text.get(m, ()))


def _plugin(rel: str, test: str, text: dict[str, tuple[str, ...]]) -> bool:
    """A plugin's file: the plugin-wide checks, and the tests whose code names the plugin (its
    id as a string, or `<id> = on` in an ini they write)."""
    parts = Path(rel).parts
    if parts[:2] != ("viwo", "plugins") or len(parts) < 4:
        return False
    pid = parts[2]
    return test in PLUGIN_WIDE or any(s == pid or f"{pid} = on" in s for s in text.get(test, ()))


def _hit(rel: str, test: str, mods: set[str], text: dict[str, tuple[str, ...]]) -> bool:
    if rel.endswith(".py") and module_of(rel) in mods or _plugin(rel, test, text):
        return True
    if rel.endswith(".py") and Path(rel).name == "__init__.py":
        return False
    return _named(rel, mods, text)


def select(paths: list[str]) -> list[str] | None:
    """Test modules to run for these changed paths; None = all of them."""
    if any(p in EVERYTHING for p in paths):
        return None
    edges, text = graph()
    tests = {m: reach(m, edges) for m in sorted(edges) if m.startswith("tests.test_")}
    return [t for t, mods in tests.items() if any(_hit(p, t, mods, text) for p in paths)]


if __name__ == "__main__":
    picked = select(changed())
    print("all" if picked is None else "\n".join(picked) or "none")
