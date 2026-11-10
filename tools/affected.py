"""The tests a change can affect (tools/version.py runs only these): a test module is picked
when it imports, directly or through other modules, a changed module; when it is itself
changed; or when it, or a module it imports, names a changed file (a doc, a data file, a
script run as a process). The registry imports every plugin by discovery, so a module that
imports the registry depends on all of viwo/plugins. A change to the pipeline itself or to
pyproject.toml runs everything (None); a change no test can see runs nothing ([])."""

import ast
import functools
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE = ("viwo", "tests", "tools", "packaging")
EVERYTHING = {"pyproject.toml", "tools/version.py", "tools/affected.py", "tools/run_tests.py"}
REGISTRY, PLUGINS = "viwo.core.wiring.registry", "viwo.plugins."


def changed() -> list[str]:
    """Paths changed against HEAD, untracked ones included (POSIX, relative to the root)."""
    out = subprocess.run(
        ["git", "status", "--porcelain", "-uall"], cwd=ROOT, capture_output=True, text=True
    ).stdout
    return sorted({line[3:].split(" -> ")[-1].strip('"') for line in out.splitlines()})


def module_of(rel: str) -> str:
    parts = list(Path(rel).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imports(path: Path, name: str, modules: set[str]) -> set[str]:
    """The modules a file imports, its packages' __init__ included."""
    package = name if path.name == "__init__.py" else name.rpartition(".")[0]
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = package.split(".")[: len(package.split(".")) - node.level + 1]
            base = ".".join(base) if node.level else ""
            head = ".".join(p for p in (base, node.module or "") if p)
            found |= {head, *(f"{head}.{a.name}" for a in node.names)}
    out = set()
    for mod in found:
        parts = mod.split(".")
        out |= {".".join(parts[:i]) for i in range(1, len(parts) + 1)} & modules
    return out


@functools.cache
def graph() -> tuple[dict[str, set[str]], dict[str, str]]:
    """(module -> modules it imports, module -> its source text) for every code folder."""
    files = {
        module_of(p.relative_to(ROOT).as_posix()): p for d in CODE for p in (ROOT / d).rglob("*.py")
    }
    modules = set(files)
    edges = {m: _imports(p, m, modules) for m, p in files.items()}
    plugins = {m for m in modules if m.startswith(PLUGINS)}
    if REGISTRY in edges:
        edges[REGISTRY] |= plugins
    return edges, {m: p.read_text(encoding="utf-8") for m, p in files.items()}


def closure(start: str, edges: dict[str, set[str]]) -> set[str]:
    seen, todo = set(), [start]
    while todo:
        mod = todo.pop()
        if mod not in seen:
            seen.add(mod)
            todo += edges.get(mod, ())
    return seen


def _hit(rel: str, mods: set[str], text: dict[str, str]) -> bool:
    if rel.endswith(".py"):
        if module_of(rel) in mods:
            return True
        if Path(rel).name == "__init__.py":
            return False
    names, parts = {Path(rel).name}, Path(rel).parts
    if parts[:2] in (("viwo", "web"), ("viwo", "data")) and len(parts) > 2:  # read by folder
        names.add(f'"{parts[2] if parts[1] == "data" and len(parts) > 3 else parts[1]}"')
    return any(n in text[m] for m in mods for n in names)


def select(paths: list[str]) -> list[str] | None:
    """Test modules to run for these changed paths; None = all of them."""
    if any(p in EVERYTHING for p in paths):
        return None
    edges, text = graph()
    tests = {m: closure(m, edges) for m in sorted(edges) if m.startswith("tests.test_")}
    return [t for t, mods in tests.items() if any(_hit(p, mods, text) for p in paths)]


if __name__ == "__main__":
    picked = select(changed())
    print("all" if picked is None else "\n".join(picked) or "none")
